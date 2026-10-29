"""Encrypted SMTP settings and transactional email delivery."""
import re
from email.utils import formataddr
from django.core.mail import EmailMessage
from django.core.mail.backends.smtp import EmailBackend
from django.db import transaction
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters, sensitive_variables
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.throttling import ScopedRateThrottle

from .ai_service import SuperuserOnly, cipher, encryption_ready, CredentialStorageUnavailable
from .audit import audit
from .models import SMTPConfig


def mail_config():
    return SMTPConfig.objects.filter(pk=1).first() or SMTPConfig()


def mail_available():
    c = mail_config()
    return bool(c.enabled and c.host and c.from_email and (not c.username or c.password_ciphertext) and encryption_ready())


def safe_config(c):
    return {**{name: getattr(c, name) for name in ('enabled', 'host', 'port', 'security', 'username', 'from_email', 'from_name', 'revision')},
            'has_password': bool(c.password_ciphertext), 'encryption_ready': encryption_ready()}


@sensitive_variables()
def send_transactional_mail(recipient, subject, body, config=None):
    c = config or mail_config()
    if not c.host or not c.from_email:
        raise ValueError('SMTP is not configured')
    try:
        password = cipher().decrypt(c.password_ciphertext.encode()).decode() if c.password_ciphertext else ''
    except Exception:
        raise CredentialStorageUnavailable() from None
    connection = EmailBackend(host=c.host, port=c.port, username=c.username, password=password,
                              use_tls=c.security=='starttls', use_ssl=c.security=='ssl', timeout=15)
    with connection:
        message = EmailMessage(subject, body, formataddr((c.from_name, c.from_email)), [recipient], connection=connection)
        if message.send() != 1:
            raise OSError('Email delivery failed')


class SMTPInput(serializers.Serializer):
    revision = serializers.IntegerField(min_value=0)
    enabled = serializers.BooleanField()
    host = serializers.CharField(max_length=253, allow_blank=True)
    port = serializers.IntegerField(min_value=1, max_value=65535)
    security = serializers.ChoiceField(choices=['starttls', 'ssl'])
    username = serializers.CharField(max_length=254, allow_blank=True)
    password = serializers.CharField(max_length=1024, required=False, allow_blank=True, trim_whitespace=False, write_only=True)
    clear_password = serializers.BooleanField(default=False)
    from_email = serializers.EmailField(allow_blank=True)
    from_name = serializers.CharField(max_length=100, allow_blank=True)

    def validate(self, values):
        if set(self.initial_data)-set(self.fields):
            raise serializers.ValidationError('包含不支持的配置项。')
        if any('\r' in values[k] or '\n' in values[k] for k in ('host','username','from_name')):
            raise serializers.ValidationError('配置不能包含换行。')
        if values['host'] and not re.fullmatch(r'[A-Za-z0-9.-]+', values['host']):
            raise serializers.ValidationError('SMTP 主机请填写域名或 IPv4 地址，不包含协议和端口。')
        if values.get('password') and values.get('clear_password'):
            raise serializers.ValidationError('更换与清除授权码不能同时执行。')
        if values['enabled'] and not (values['host'] and values['from_email']):
            raise serializers.ValidationError('启用前请填写 SMTP 主机及发件邮箱。')
        return values


@method_decorator(never_cache, name='dispatch')
@method_decorator(sensitive_post_parameters('password'), name='dispatch')
class MailSettings(APIView):
    permission_classes = [SuperuserOnly]

    def get(self, request):
        return Response(safe_config(mail_config()))

    @transaction.atomic
    def patch(self, request):
        data = SMTPInput(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        c, _ = SMTPConfig.objects.select_for_update().get_or_create(pk=1)
        if c.revision != v['revision']:
            return Response({'detail': '配置已更新，请刷新后重试。'}, status=409)
        for name in ('enabled','host','port','security','username','from_email','from_name'):
            setattr(c, name, v[name])
        if v['clear_password']:
            c.password_ciphertext = ''
        elif v.get('password'):
            c.password_ciphertext = cipher().encrypt(v['password'].encode()).decode()
        if c.enabled and c.username and not c.password_ciphertext:
            raise serializers.ValidationError('请保存 SMTP 密码或授权码。')
        c.revision += 1
        c.save()
        audit(request, 'update', 'management_api.smtpconfig', c, '更新 SMTP 邮件配置（凭据不记录）')
        return Response(safe_config(c))


class MailTest(APIView):
    permission_classes = [SuperuserOnly]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'ai_connection'

    def post(self, request):
        recipient = serializers.EmailField().run_validation(request.data.get('recipient'))
        c = mail_config()
        if request.data.get('revision') != c.revision:
            return Response({'detail': '请先保存并刷新邮件配置。'}, status=409)
        try:
            send_transactional_mail(recipient, 'POPOMO 邮件配置测试 / Email test',
                                    '这是一封 SMTP 测试邮件。\nYour POPOMO SMTP settings are working.', c)
        except Exception:
            return Response({'detail': '发送失败，请检查主机、端口、加密方式、授权码及发件人权限。'}, status=503)
        return Response({'detail': 'SMTP 服务已接受测试邮件，请检查收件箱和垃圾邮件。'})

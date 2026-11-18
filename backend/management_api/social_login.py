"""Server-side social sign-in. Credentials and provider tokens never reach the H5."""
import base64
import hashlib
import hmac
import re
import secrets
import time
from datetime import timedelta
from urllib.parse import urlencode, urlsplit

import jwt
import requests
from django.conf import settings
from django.db import transaction
from django.http import HttpResponseRedirect
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters, sensitive_variables
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .ai_service import SuperuserOnly, cipher, encryption_ready
from .audit import audit
from .customer_auth import CustomerView, customer_for, rate_limit, complete_customer_login, establish_customer_session
from .mail_service import mail_available
from .models import CustomerSocialIdentity, SocialLoginAttempt, SocialLoginConfig

PROVIDERS = ('google', 'facebook')
GOOGLE_KEYS = jwt.PyJWKClient('https://www.googleapis.com/oauth2/v3/certs', timeout=10, lifespan=300)


def config_for(provider):
    if provider not in PROVIDERS:
        raise serializers.ValidationError('Unknown sign-in provider.')
    return SocialLoginConfig.objects.filter(pk=provider).first() or SocialLoginConfig(provider=provider)


def available(c):
    return bool(c.enabled and c.client_id and c.secret_ciphertext and c.site_origin and encryption_ready())


def callback_url(c):
    return c.site_origin + f'/api/v1/store/customer/social/{c.provider}/callback/' if c.site_origin else ''


def pending_identity(request):
    p = request.session.get('social_pending')
    if not isinstance(p, dict) or p.get('expires_at', 0) <= time.time():
        request.session.pop('social_pending', None)
        return None
    c = config_for(p['provider'])
    if not available(c) or c.revision != p['revision'] or c.client_id != p['client_id']:
        request.session.pop('social_pending', None)
        return None
    return p


def public_options(request):
    p = pending_identity(request)
    return {'socialProviders': [c.provider for c in SocialLoginConfig.objects.all() if available(c)],
            'socialPending': {'provider': p['provider'], 'email': p['email']} if p else None,
            'emailEnabled': mail_available()}


def safe_config(c):
    return {k: getattr(c, k) for k in ('provider', 'enabled', 'client_id', 'site_origin', 'graph_version', 'revision')} | {
        'has_secret': bool(c.secret_ciphertext), 'encryption_ready': encryption_ready(),
        'callback_url': callback_url(c), 'available': available(c)}


class ConfigInput(serializers.Serializer):
    revision = serializers.IntegerField(min_value=0)
    enabled = serializers.BooleanField()
    client_id = serializers.CharField(max_length=255, allow_blank=True)
    secret = serializers.CharField(max_length=2048, required=False, allow_blank=True, write_only=True)
    clear_secret = serializers.BooleanField(default=False)
    site_origin = serializers.CharField(max_length=255, allow_blank=True)
    graph_version = serializers.RegexField(r'^v[1-9][0-9]?\.0$', default='v27.0')

    def validate_site_origin(self, value):
        if not value:
            return ''
        try:
            u = urlsplit(value)
            valid = u.hostname and not u.username and not u.password and not u.query and not u.fragment and u.path in ('', '/')
            local = settings.DEBUG and u.hostname in ('localhost', '127.0.0.1') and u.scheme == 'http'
            if not valid or (u.scheme != 'https' and not local) or any(c.isspace() for c in value):
                raise ValueError()
            u.port
        except ValueError:
            raise serializers.ValidationError('填写完整 HTTPS 网站域名，不含路径或参数。')
        return value.rstrip('/')

    def validate(self, values):
        if set(self.initial_data) - set(self.fields):
            raise serializers.ValidationError('包含不支持的配置项。')
        if values.get('secret') and values['clear_secret']:
            raise serializers.ValidationError('更换与清除密钥不能同时执行。')
        if values['enabled'] and not (values['client_id'] and values['site_origin']):
            raise serializers.ValidationError('启用前填写应用 ID 和网站域名。')
        return values


@method_decorator(never_cache, name='dispatch')
@method_decorator(sensitive_post_parameters('secret'), name='dispatch')
class SocialSettings(APIView):
    permission_classes = [SuperuserOnly]

    def get(self, request, provider):
        return Response(safe_config(config_for(provider)))

    @transaction.atomic
    def patch(self, request, provider):
        config_for(provider)
        data = ConfigInput(data=request.data)
        data.is_valid(raise_exception=True)
        v = data.validated_data
        if v['client_id'] and not re.fullmatch(r'[A-Za-z0-9._-]+', v['client_id']):
            raise serializers.ValidationError('应用 ID 格式不正确。')
        if provider == 'facebook' and v['client_id'] and not v['client_id'].isascii():
            raise serializers.ValidationError('Facebook App ID 格式不正确。')
        if provider == 'facebook' and v['client_id'] and not v['client_id'].isdigit():
            raise serializers.ValidationError('Facebook App ID 应为数字。')
        c, _ = SocialLoginConfig.objects.get_or_create(pk=provider)
        # Serialize edits on SQLite as well as PostgreSQL, then compare revisions.
        from django.db.models import F
        SocialLoginConfig.objects.filter(pk=provider).update(revision=F('revision'))
        c = SocialLoginConfig.objects.select_for_update().get(pk=provider)
        if c.revision != v['revision']:
            return Response({'detail': '配置已更新，请刷新后重试。'}, status=409)
        if c.client_id and c.client_id != v['client_id'] and not (v.get('secret') or v['clear_secret']):
            raise serializers.ValidationError('更换应用 ID 时请同时更换或清除原密钥。')
        for key in ('enabled', 'client_id', 'site_origin', 'graph_version'):
            setattr(c, key, v[key])
        if v['clear_secret']:
            c.secret_ciphertext = ''
        elif v.get('secret'):
            c.secret_ciphertext = cipher().encrypt(v['secret'].encode()).decode()
        if c.enabled and (not c.secret_ciphertext or not encryption_ready()):
            raise serializers.ValidationError('启用前保存应用密钥，并确认服务端加密配置可用。')
        c.revision += 1
        c.save()
        audit(request, 'update', 'management_api.socialloginconfig', c, f'更新 {provider} 登录配置（不记录密钥）')
        return Response(safe_config(c))


class StartInput(serializers.Serializer):
    next = serializers.ChoiceField(choices=['choose', 'ai'], default='choose')
    language = serializers.ChoiceField(choices=['en-US', 'zh-CN'], default='en-US')
    device_id = serializers.RegexField(r'^[0-9]{1,40}$', required=False)
    shop_id = serializers.RegexField(r'^[0-9]{1,40}$', required=False)


class SocialStart(CustomerView):
    http_method_names = ['post', 'options']

    def post(self, request, provider):
        c = config_for(provider)
        rate_limit(request, 'social-start', 30)
        if customer_for(request):
            return Response({'detail': 'Sign out before choosing another sign-in method.'}, status=409)
        if not available(c):
            return Response({'detail': 'This sign-in method is temporarily unavailable. Please use email.'}, status=503)
        data = StartInput(data=request.data)
        data.is_valid(raise_exception=True)
        request.session.pop('social_pending', None)
        browser = secrets.token_urlsafe(32)
        request.session['social_browser'] = browser
        state, nonce, verifier = (secrets.token_urlsafe(32) for _ in range(3))
        SocialLoginAttempt.objects.filter(expires_at__lt=timezone.now()).delete()
        SocialLoginAttempt.objects.create(state_hash=hashlib.sha256(state.encode()).hexdigest(),
            browser_hash=hashlib.sha256(browser.encode()).hexdigest(), provider=provider,
            config_revision=c.revision, nonce=nonce, verifier=verifier,
            context=data.validated_data, expires_at=timezone.now()+timedelta(minutes=10))
        params = {'client_id': c.client_id, 'redirect_uri': callback_url(c), 'response_type': 'code', 'state': state}
        if provider == 'google':
            params.update(scope='openid email profile', nonce=nonce, prompt='select_account',
                code_challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode(), code_challenge_method='S256')
            endpoint = 'https://accounts.google.com/o/oauth2/v2/auth'
        else:
            params.update(scope='email,public_profile')
            endpoint = f'https://www.facebook.com/{c.graph_version}/dialog/oauth'
        return Response({'authorizationUrl': endpoint+'?'+urlencode(params)})


@sensitive_variables()
def provider_json(method, url, **kwargs):
    # Fixed provider endpoints only. No redirects or automatic write retries.
    r = requests.request(method, url, timeout=10, allow_redirects=False, **kwargs)
    if r.status_code != 200:
        raise ValueError('provider unavailable')
    value = r.json()
    if not isinstance(value, dict) or 'error' in value:
        raise ValueError('invalid provider response')
    return value


@sensitive_variables()
def exchange_identity(c, attempt, code):
    secret = cipher().decrypt(c.secret_ciphertext.encode()).decode()
    fields = {'client_id': c.client_id, 'client_secret': secret, 'redirect_uri': callback_url(c), 'code': code}
    if c.provider == 'google':
        fields.update(grant_type='authorization_code', code_verifier=attempt.verifier)
        tokens = provider_json('POST', 'https://oauth2.googleapis.com/token', data=fields)
        token = tokens.get('id_token', '')
        if not isinstance(token, str) or not 1 <= len(token) <= 16384:
            raise ValueError('missing identity')
        key = GOOGLE_KEYS.get_signing_key_from_jwt(token).key
        claims = jwt.decode(token, key, algorithms=['RS256'], audience=c.client_id,
            issuer=['accounts.google.com', 'https://accounts.google.com'],
            options={'require': ['sub', 'exp', 'iat', 'aud', 'iss', 'nonce'], 'strict_aud': True})
        if not constant_time_compare(str(claims.get('nonce', '')), attempt.nonce) or claims.get('azp', c.client_id) != c.client_id:
            raise ValueError('invalid identity binding')
        subject = claims['sub']
        email = str(claims.get('email', '')).strip().lower()
        trusted = claims.get('email_verified') is True and (email.endswith('@gmail.com') or bool(claims.get('hd')))
        name = str(claims.get('name', ''))[:60]
    else:
        endpoint = f'https://graph.facebook.com/{c.graph_version}'
        token = provider_json('GET', endpoint+'/oauth/access_token', params=fields).get('access_token')
        if not isinstance(token, str) or not token or len(token) > 8192:
            raise ValueError('missing token')
        checked = provider_json('GET', endpoint+'/debug_token', params={'input_token': token},
            headers={'Authorization': 'Bearer '+c.client_id+'|'+secret}).get('data', {})
        if (checked.get('is_valid') is not True or str(checked.get('app_id')) != c.client_id or
                checked.get('type') != 'USER' or checked.get('expires_at', 0) <= time.time() or
                (checked.get('data_access_expires_at') and checked['data_access_expires_at'] <= time.time())):
            raise ValueError('invalid facebook token')
        proof = hmac.new(secret.encode(), token.encode(), hashlib.sha256).hexdigest()
        claims = provider_json('GET', endpoint+'/me', params={'fields': 'id,name,email', 'appsecret_proof': proof},
            headers={'Authorization': 'Bearer '+token})
        subject = str(claims.get('id', ''))
        if subject != str(checked.get('user_id', '')):
            raise ValueError('identity mismatch')
        email, name = str(claims.get('email', '')).strip().lower(), str(claims.get('name', ''))[:60]
        trusted = False  # Facebook email is not a mailbox-ownership proof.
    if not isinstance(subject, str) or not subject or len(subject) > 255:
        raise ValueError('invalid subject')
    try:
        email = serializers.EmailField(max_length=254).run_validation(email)
    except serializers.ValidationError:
        email, trusted = '', False
    return {'subject': subject, 'email': email, 'name': name, 'trusted': trusted}


def link_identity(customer, p):
    other = CustomerSocialIdentity.objects.filter(provider=p['provider'], client_id=p['client_id'], customer=customer).first()
    if other and other.subject != p['subject']:
        raise serializers.ValidationError('This account already uses another sign-in identity. Please use email.')
    identity, _ = CustomerSocialIdentity.objects.get_or_create(provider=p['provider'], client_id=p['client_id'],
        subject=p['subject'], defaults={'customer': customer})
    if identity.customer_id != customer.pk:
        raise serializers.ValidationError('This sign-in is already linked to another account. Please sign in again.')


def link_verified_pending(request, customer):
    p = pending_identity(request)
    if p:
        c = SocialLoginConfig.objects.select_for_update().get(pk=p['provider'])
        if not available(c) or c.revision != p['revision']:
            raise serializers.ValidationError('Sign-in settings changed. Please start again.')
        link_identity(customer, p)
    request.session.pop('social_pending', None)


def finish_url(c, context, result):
    query = {'lang': context.get('language', 'en-US')}
    if context.get('device_id') and context.get('shop_id'):
        query.update(device_id=context['device_id'], shop_id=context['shop_id'])
    return c.site_origin+'/?'+urlencode(query)+'#account?'+urlencode({'social': result, 'next': context.get('next', 'choose')})


@method_decorator(never_cache, name='dispatch')
class SocialCallback(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    http_method_names = ['get', 'options']

    @sensitive_variables()
    def get(self, request, provider):
        c = config_for(provider)
        context, result = {}, 'failed'
        try:
            rate_limit(request, 'social-callback', 60)
            raw = request.query_params.get('state', '')
            browser = request.session.get('social_browser', '')
            if not raw or len(raw) > 100 or not browser:
                raise ValueError('missing state')
            query = SocialLoginAttempt.objects.filter(state_hash=hashlib.sha256(raw.encode()).hexdigest(),
                browser_hash=hashlib.sha256(browser.encode()).hexdigest(), provider=provider,
                consumed=False, expires_at__gt=timezone.now())
            with transaction.atomic():
                if query.update(consumed=True) != 1:
                    raise ValueError('expired state')
                attempt = SocialLoginAttempt.objects.get(state_hash=hashlib.sha256(raw.encode()).hexdigest())
            context = attempt.context
            if not available(c) or c.revision != attempt.config_revision or customer_for(request):
                raise ValueError('configuration or session changed')
            if request.query_params.get('error'):
                result = 'cancelled'
            else:
                code = request.query_params.get('code', '')
                if not code or len(code) > 8192:
                    raise ValueError('missing code')
                identity = exchange_identity(c, attempt, code)
                with transaction.atomic():
                    c = SocialLoginConfig.objects.select_for_update().get(pk=provider)
                    if not available(c) or c.revision != attempt.config_revision:
                        raise ValueError('configuration changed')
                    linked = CustomerSocialIdentity.objects.filter(provider=provider, client_id=c.client_id,
                        subject=identity['subject']).select_related('customer').first()
                    if linked:
                        customer, _ = complete_customer_login(customer_id=linked.customer_id)
                    elif identity['trusted']:
                        customer, _ = complete_customer_login(email=identity['email'], name=identity['name'])
                        link_identity(customer, {'provider': provider, 'client_id': c.client_id, **identity})
                    else:
                        request.session['social_pending'] = {'provider': provider, 'client_id': c.client_id,
                            'revision': c.revision, 'subject': identity['subject'], 'email': identity['email'],
                            'expires_at': time.time()+600}
                        customer = None
                    if customer:
                        establish_customer_session(request, customer)
                        result = 'success'
                    else:
                        result = 'verify_email'
        except Exception:
            # Do not return/log provider URLs, codes, tokens or exception contents.
            result = 'failed'
        response = HttpResponseRedirect(finish_url(c, context, result))
        response['Referrer-Policy'] = 'no-referrer'
        return response

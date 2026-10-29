"""Email-code customer identity, separate from staff accounts and browser order keys."""
import hashlib
import secrets
import uuid
from datetime import timedelta

from django.db import transaction
from django.db.models import F
from django.middleware.csrf import get_token, rotate_token
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from rest_framework import serializers
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import PermissionDenied, Throttled
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Customer, EmailChallenge, CustomerAuthLimit, AIAccount
from .mail_service import send_transactional_mail, mail_available, mail_config

SESSION_KEY = 'store_customer_id'


def customer_for(request):
    customer_id = request.session.get(SESSION_KEY)
    if not customer_id:
        return None
    return Customer.objects.filter(pk=customer_id, active=True, session_version=request.session.get('store_customer_version', 0)).first()


def customer_owner(request):
    customer = customer_for(request)
    if not customer:
        raise PermissionDenied('Sign in with your email to use AI generations.')
    SessionAuthentication().enforce_csrf(request)
    return hashlib.sha256(('customer:' + str(customer.pk)).encode()).hexdigest()


def signup_credits():
    return mail_config().signup_credits


def public_customer(customer):
    return {'id': str(customer.pk), 'email': customer.email, 'displayName': customer.display_name,
            'joinedAt': customer.created_at.isoformat(),
            'lastLoginAt': customer.last_login_at.isoformat() if customer.last_login_at else None} if customer else None


def code_digest(email, nonce, code):
    return salted_hmac('store-email-code', f'{email}:{nonce}:{code}', algorithm='sha256').hexdigest()


def rate_limit(request, scope, maximum):
    # Use the direct peer by default. A trusted reverse proxy can explicitly
    # overwrite X-Real-IP and enable CUSTOMER_TRUST_PROXY_IP in settings.
    from django.conf import settings
    ip = request.META.get('REMOTE_ADDR', '')
    if getattr(settings, 'CUSTOMER_TRUST_PROXY_IP', False):
        ip = request.META.get('HTTP_X_REAL_IP', ip)
    key = hashlib.sha256(f'{scope}:{ip}'.encode()).hexdigest()
    now = timezone.now()
    with transaction.atomic():
        CustomerAuthLimit.objects.get_or_create(key=key, defaults={'window_at': now})
        CustomerAuthLimit.objects.filter(pk=key).update(count=F('count') + 1)
        bucket = CustomerAuthLimit.objects.select_for_update().get(pk=key)
        if now - bucket.window_at >= timedelta(hours=1):
            bucket.window_at, bucket.count = now, 1
            bucket.save()
        blocked = bucket.count > maximum
    if blocked:
        raise Throttled(3600, 'Too many attempts. Please try again later.')


class EmailInput(serializers.Serializer):
    email = serializers.EmailField(max_length=254)
    language = serializers.ChoiceField(choices=['en-US', 'zh-CN'], default='en-US')

    def validate_email(self, value):
        return value.strip().lower()


class VerifyInput(EmailInput):
    code = serializers.RegexField(r'^\d{6}$', max_length=6)


@method_decorator(never_cache, name='dispatch')
class CustomerView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        SessionAuthentication().enforce_csrf(request)

    def get(self, request):
        return Response({'customer': public_customer(customer_for(request)),
                         'signupCredits': signup_credits(), 'emailEnabled': mail_available(),
                         'csrfToken': get_token(request)})

    def patch(self, request):
        customer = customer_for(request)
        if not customer:
            raise PermissionDenied('Sign in with your email to use AI generations.')
        if set(request.data) != {'displayName'}:
            raise serializers.ValidationError('Only your display name can be changed here.')
        name = serializers.CharField(max_length=60, allow_blank=True).run_validation(request.data['displayName'])
        Customer.objects.filter(pk=customer.pk).update(display_name=name, revision=F('revision') + 1)
        customer.refresh_from_db()
        return Response({'customer': public_customer(customer)})

    def delete(self, request):
        request.session.pop(SESSION_KEY, None)
        request.session.pop('store_customer_version', None)
        request.session.cycle_key()
        return Response({'customer': None, 'csrfToken': get_token(request)})


class SendCode(CustomerView):
    http_method_names = ['post', 'options']

    def post(self, request):
        data = EmailInput(data=request.data)
        data.is_valid(raise_exception=True)
        email, language = data.validated_data['email'], data.validated_data['language']
        rate_limit(request, 'send', 15)
        if not mail_available():
            return Response({'detail': 'Email sign-in is temporarily unavailable. Please try again later.'}, status=503)
        now = timezone.now()
        code = f'{secrets.randbelow(1000000):06d}'
        with transaction.atomic():
            challenge, _ = EmailChallenge.objects.get_or_create(email=email, defaults={
                'expires_at': now, 'sent_at': now-timedelta(minutes=1), 'window_at': now})
            # Write before reading to serialize both SQLite and PostgreSQL.
            EmailChallenge.objects.filter(pk=email).update(attempts=F('attempts'))
            challenge = EmailChallenge.objects.select_for_update().get(pk=email)
            if (now-challenge.sent_at).total_seconds() < 60:
                raise Throttled(60, 'Wait a minute before requesting another code.')
            if now-challenge.window_at >= timedelta(hours=1):
                challenge.sent_count, challenge.window_at = 0, now
            if challenge.sent_count >= 5:
                raise Throttled(3600, 'Too many codes requested. Please try again later.')
            challenge.nonce = uuid.uuid4()
            challenge.code_hash = code_digest(email, challenge.nonce, code)
            challenge.expires_at, challenge.sent_at = now+timedelta(minutes=10), now
            challenge.sent_count += 1
            challenge.attempts, challenge.delivered = 0, False
            challenge.save()
        from .email_content import verification_email
        subject, body, html = verification_email(code, language)
        try:
            send_transactional_mail(email, subject, body, html_body=html)
        except Exception:
            # Never echo SMTP credentials, verification codes or provider replies.
            return Response({'detail': 'We could not send your code. Please try again later.'}, status=503)
        EmailChallenge.objects.filter(pk=email, nonce=challenge.nonce).update(delivered=True)
        return Response({'sent': True, 'retryAfter': 60})


@method_decorator(sensitive_post_parameters('code'), name='dispatch')
class VerifyCode(CustomerView):
    http_method_names = ['post', 'options']

    def post(self, request):
        data = VerifyInput(data=request.data)
        data.is_valid(raise_exception=True)
        email, code = data.validated_data['email'], data.validated_data['code']
        rate_limit(request, 'verify', 60)
        valid, customer, created = False, None, False
        with transaction.atomic():
            EmailChallenge.objects.filter(pk=email).update(attempts=F('attempts')+1)
            challenge = EmailChallenge.objects.select_for_update().filter(pk=email).first()
            if (challenge and challenge.delivered and challenge.attempts <= 5 and
                    challenge.expires_at > timezone.now() and
                    constant_time_compare(challenge.code_hash, code_digest(email, challenge.nonce, code))):
                valid = True
                challenge.delivered, challenge.code_hash = False, ''
                challenge.save(update_fields=['delivered', 'code_hash'])
                customer, created = Customer.objects.get_or_create(email=email, defaults={'verified_at': timezone.now()})
                customer = Customer.objects.select_for_update().get(pk=customer.pk)
                if customer.active:
                    customer.last_login_at = timezone.now()
                    customer.save(update_fields=['last_login_at', 'updated_at'])
                    key = hashlib.sha256(('customer:' + str(customer.pk)).encode()).hexdigest()
                    AIAccount.objects.get_or_create(owner_hash=key, defaults={
                        'customer': customer, 'trial_granted': signup_credits()})
        if not valid:
            return Response({'detail': 'This code is invalid or expired. Request a new code.'}, status=400)
        if not customer.active:
            raise PermissionDenied('This account is unavailable. Please contact the store.')
        request.session.cycle_key()
        rotate_token(request)
        request.session[SESSION_KEY] = str(customer.pk)
        request.session['store_customer_version'] = customer.session_version
        request.session.set_expiry(30*24*60*60)
        return Response({'customer': public_customer(customer), 'created': created, 'csrfToken': get_token(request)})

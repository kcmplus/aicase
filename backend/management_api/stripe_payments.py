"""Stripe-hosted, one-time case checkout. Only verified webhooks settle orders."""
import json
import uuid
from datetime import timedelta
from urllib.parse import urlsplit

import stripe
from cryptography.fernet import InvalidToken
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters, sensitive_variables
from rest_framework import serializers
from rest_framework.exceptions import APIException
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .ai_service import SuperuserOnly, cipher, encryption_ready, CredentialStorageUnavailable
from .audit import audit
from .models import StripeConfig, PrintOrder, AuditLog
from .orders import StrictSerializer, StoreOrders, owner, order_data, Conflict

WEBHOOK_EVENTS = ('checkout.session.completed', 'checkout.session.async_payment_succeeded',
                  'checkout.session.async_payment_failed', 'checkout.session.expired')


class PaymentUnavailable(APIException):
    status_code = 503
    default_detail = 'Stripe payment is unavailable. Your order is saved; please retry later.'


def current_config():
    return StripeConfig.objects.filter(pk=1).first() or StripeConfig(pk=1)


@sensitive_variables()
def credentials(ciphertext):
    if not ciphertext:
        return {}
    try:
        return json.loads(cipher().decrypt(ciphertext.encode()).decode())
    except (InvalidToken, UnicodeError, ValueError):
        raise CredentialStorageUnavailable() from None


@sensitive_variables()
def encrypt_credentials(values):
    return cipher().encrypt(json.dumps(values).encode()).decode()


@sensitive_variables()
def payment_config(config=None):
    config = config or current_config()
    try:
        values = credentials(getattr(config, config.mode + '_credentials')) if config.enabled else {}
        ready = bool(config.storefront_url and values.get('secret_key') and values.get('webhook_secret'))
    except CredentialStorageUnavailable:
        ready = False
    return {'provider': 'stripe' if config.enabled else 'demo', 'mode': config.mode if config.enabled else 'demo',
            'available': ready if config.enabled else True}


@sensitive_variables()
def safe_config(config):
    result = {key: getattr(config, key) for key in ('enabled', 'mode', 'storefront_url', 'revision')}
    result.update(encryption_ready=encryption_ready(), webhook_events=WEBHOOK_EVENTS,
                  webhook_path='/api/v1/payments/stripe/webhook/', available=payment_config(config)['available'])
    for mode in ('test', 'live'):
        try:
            values = credentials(getattr(config, mode + '_credentials'))
            result[mode] = {key: {'configured': bool(values.get(key)), 'masked': '••••' + values[key][-4:] if values.get(key) else ''}
                            for key in ('secret_key', 'webhook_secret')}
        except CredentialStorageUnavailable:
            result['encryption_ready'] = False
            result[mode] = {key: {'configured': True, 'masked': '无法解密'} for key in ('secret_key', 'webhook_secret')}
    return result


class CredentialUpdate(StrictSerializer):
    secret_key = serializers.CharField(required=False, allow_blank=True, max_length=1024)
    webhook_secret = serializers.RegexField(r'^whsec_[A-Za-z0-9]+$', required=False, allow_blank=True, max_length=1024)
    clear = serializers.BooleanField(default=False)

    def validate(self, data):
        if data['clear'] and (data.get('secret_key') or data.get('webhook_secret')):
            raise serializers.ValidationError('清除和填写密钥不能同时执行。')
        return data


class ConfigUpdate(StrictSerializer):
    revision = serializers.IntegerField(min_value=0)
    enabled = serializers.BooleanField(required=False)
    mode = serializers.ChoiceField(choices=['test', 'live'], required=False)
    storefront_url = serializers.URLField(required=False, allow_blank=True, max_length=200)
    test = CredentialUpdate(required=False)
    live = CredentialUpdate(required=False)

    def validate_storefront_url(self, value):
        if not value:
            return value
        url = urlsplit(value)
        if (url.username or url.password or url.query or url.fragment or url.path not in ('', '/')
                or (url.scheme != 'https' and not (url.scheme == 'http' and url.hostname in ('localhost', '127.0.0.1')))):
            raise serializers.ValidationError('请填写用户端网站根地址；线上必须使用 HTTPS，本机测试可用 http://localhost:4173。')
        return value.rstrip('/') + '/'

    def validate(self, data):
        import re
        for mode in ('test', 'live'):
            key = data.get(mode, {}).get('secret_key')
            if key and not re.fullmatch(r'(sk|rk)_' + mode + r'_[A-Za-z0-9]+', key):
                raise serializers.ValidationError({mode: '请填写此模式对应的 Stripe Secret Key（sk_ 或 rk_），不要填写 Publishable Key。'})
        return data


@method_decorator(never_cache, name='dispatch')
@method_decorator(sensitive_post_parameters(), name='dispatch')
class StripeSettings(APIView):
    permission_classes = [SuperuserOnly]

    def get(self, request):
        return Response(safe_config(current_config()))

    @sensitive_variables()
    @transaction.atomic
    def patch(self, request):
        serializer = ConfigUpdate(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        config, _ = StripeConfig.objects.select_for_update().get_or_create(pk=1)
        if data['revision'] != config.revision:
            raise Conflict('配置已更新，请刷新后重试。')
        changed = []
        for key in ('enabled', 'mode', 'storefront_url'):
            if key in data and data[key] != getattr(config, key):
                setattr(config, key, data[key])
                changed.append(key)
        for mode in ('test', 'live'):
            update = data.get(mode, {})
            field = mode + '_credentials'
            if update.get('clear'):
                setattr(config, field, '')
                changed.append(mode + ' 清除密钥')
            elif update.get('secret_key') or update.get('webhook_secret'):
                values = credentials(getattr(config, field))
                values.update({key: value for key, value in update.items() if key != 'clear' and value})
                setattr(config, field, encrypt_credentials(values))
                changed.append(mode + ' 更新密钥')
        if config.enabled:
            values = credentials(getattr(config, config.mode + '_credentials'))
            if not config.storefront_url or not values.get('secret_key') or not values.get('webhook_secret'):
                raise serializers.ValidationError('启用前请填写网站地址及当前模式的 Secret Key、Webhook 签名密钥。')
            if config.mode == 'live' and not config.storefront_url.startswith('https://'):
                raise serializers.ValidationError('正式收款必须使用 HTTPS 网站地址。')
        if changed:
            config.revision += 1
            config.save()
            audit(request, 'update', 'management_api.stripeconfig', config, '修改 Stripe 配置：' + '、'.join(changed))
        return Response(safe_config(config))


@method_decorator(never_cache, name='dispatch')
class PublicPaymentConfig(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        return Response(payment_config())


@sensitive_variables()
def checkout_settings(provider, mode):
    config = current_config()
    public = payment_config(config)
    if provider != public['provider'] or mode != public['mode']:
        raise Conflict('Payment settings changed. Reload to review the payment method.')
    if provider == 'demo':
        return {'mode': 'demo', 'status': 'paid'}
    saved = getattr(config, config.mode + '_credentials')
    values = credentials(saved)
    if not public['available'] or not values.get('secret_key') or not values.get('webhook_secret'):
        raise PaymentUnavailable()
    return {'mode': 'stripe_' + config.mode, 'status': 'pending', 'payment_credentials': saved,
            'payment_return_url': config.storefront_url}


def expiry(order):
    return int((order.created_at + timedelta(hours=24)).timestamp())


@sensitive_variables()
def create_session(order):
    values = credentials(order.payment_credentials)
    client = stripe.StripeClient(values['secret_key'], max_network_retries=0,
                                 http_client=stripe.RequestsClient(timeout=12))
    # Immutable parameters and a fixed expiry keep retries safe even after a lost
    # response or transaction rollback. Never mint a second session for an order.
    url = order.payment_return_url + '#payment?order=' + str(order.reference)
    params = {'mode': 'payment', 'payment_method_types': ['card'],
              'client_reference_id': str(order.reference), 'metadata': {'order_reference': str(order.reference)},
              'line_items': [{'quantity': 1, 'price_data': {'currency': order.currency.lower(),
                              'unit_amount': int(order.amount * 100),
                              'product_data': {'name': 'POPOMO custom phone case · ' + order.model_name}}}],
              'success_url': url + '&result=success', 'cancel_url': url + '&result=cancel',
              'expires_at': expiry(order), 'adaptive_pricing': {'enabled': False}}
    if order.customer_email:
        params['customer_email'] = order.customer_email
    try:
        return client.v1.checkout.sessions.create(params, options={'idempotency_key': 'case-checkout-' + str(order.reference)}).to_dict()
    except stripe.StripeError:
        raise PaymentUnavailable() from None


class StripeCheckout(StoreOrders):
    http_method_names = ['post', 'options']

    @transaction.atomic
    def post(self, request, reference):
        order = get_object_or_404(PrintOrder.objects.select_for_update(), reference=reference, owner_hash=owner(request))
        if order.mode not in ('stripe_test', 'stripe_live') or order.status != 'pending':
            raise Conflict('This order is not awaiting Stripe payment. Refresh its status.')
        if expiry(order) <= timezone.now().timestamp():
            raise Conflict('This checkout expired. Create a new order to pay.')
        if not order.stripe_session_id:
            # Stripe requires expiry at least 30 minutes in the future. Leaving
            # the existing order intact allows delayed webhook recovery.
            if expiry(order) <= timezone.now().timestamp() + 1800:
                raise Conflict('This checkout expired. Create a new order to pay.')
            session = create_session(order)
            url = urlsplit(session.get('url') or '')
            if (url.scheme != 'https' or url.hostname != 'checkout.stripe.com' or url.username or url.password
                    or session.get('livemode') != (order.mode == 'stripe_live') or not session.get('id')):
                raise PaymentUnavailable()
            order.stripe_session_id = session['id']
            order.stripe_checkout_url = session['url']
            order.save(update_fields=['stripe_session_id', 'stripe_checkout_url', 'updated_at'])
        return Response({'checkout_url': order.stripe_checkout_url, 'order': order_data(order)})


@method_decorator(never_cache, name='dispatch')
class StripeWebhook(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = []

    @sensitive_variables()
    def post(self, request):
        payload = request.body
        # Only use the untrusted reference to find a signing secret. No order
        # data is returned or changed until the SDK verifies the raw body.
        try:
            untrusted = json.loads(payload)
            reference = uuid.UUID(untrusted['data']['object']['metadata']['order_reference'])
        except (ValueError, KeyError, TypeError, AttributeError):
            return Response({'detail': 'Invalid checkout event.'}, status=400)
        order = PrintOrder.objects.filter(reference=reference, mode__in=['stripe_test', 'stripe_live']).first()
        if not order:
            return Response({'detail': 'Unknown checkout.'}, status=400)
        values = credentials(order.payment_credentials)
        try:
            event = stripe.Webhook.construct_event(payload, request.headers.get('Stripe-Signature', ''), values['webhook_secret']).to_dict()
        except (ValueError, stripe.SignatureVerificationError):
            return Response({'detail': 'Invalid Stripe signature.'}, status=400)
        if event['type'] not in WEBHOOK_EVENTS:
            return Response({'received': True})
        session = event['data']['object']
        with transaction.atomic():
            order = PrintOrder.objects.select_for_update().get(pk=order.pk)
            expected_live = order.mode == 'stripe_live'
            if (session.get('object') != 'checkout.session' or session.get('mode') != 'payment'
                    or session.get('client_reference_id') != str(order.reference)
                    or session.get('metadata', {}).get('order_reference') != str(order.reference)
                    or session.get('amount_total') != int(order.amount * 100)
                    or session.get('currency') != order.currency.lower()
                    or session.get('livemode') != expected_live or event.get('livemode') != expected_live
                    or not session.get('id')
                    or (order.stripe_session_id and order.stripe_session_id != session['id'])):
                return Response({'detail': 'Checkout does not match this order.'}, status=400)
            target = None
            if event['type'] in WEBHOOK_EVENTS[:2] and session.get('payment_status') == 'paid' and session.get('status') == 'complete':
                if order.status in ('pending', 'cancelled'):
                    target = 'paid'
                    order.paid_at = timezone.now()
                    order.stripe_payment_intent = session.get('payment_intent') or ''
            elif event['type'] in WEBHOOK_EVENTS[2:] and order.status == 'pending':
                target = 'cancelled'
            if target:
                order.status = target
                order.stripe_session_id = session['id']
                order.revision += 1
                order.save(update_fields=['status', 'stripe_session_id', 'stripe_payment_intent', 'paid_at', 'revision', 'updated_at'])
                AuditLog.objects.create(actor_name='Stripe', action='payment' if target == 'paid' else 'cancel',
                    resource='management_api.printorder', object_id=str(order.pk),
                    summary=f'Stripe {order.mode} · {order.reference} · {target}')
        return Response({'received': True})

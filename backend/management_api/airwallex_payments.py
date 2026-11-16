"""Airwallex PaymentIntents + hosted payment page; no card data enters our API."""
import hashlib
import hmac
import json
import re
import time
import uuid
from datetime import timedelta
from decimal import Decimal, InvalidOperation

import requests
from django.core.cache import cache
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters, sensitive_variables
from rest_framework import serializers
from rest_framework.exceptions import APIException
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .ai_service import SuperuserOnly, encryption_ready, CredentialStorageUnavailable
from .audit import audit
from .models import AirwallexConfig, PrintOrder, AuditLog
from .orders import StrictSerializer, StoreOrders, owner, order_data, Conflict, require_single_print_payment
from .stripe_payments import credentials, encrypt_credentials, ConfigUpdate as StripeConfigUpdate

REQUIRED_KEYS = ('client_id', 'api_key', 'webhook_secret')
KEYS = (*REQUIRED_KEYS, 'account_id')
WEBHOOK_EVENTS = ('payment_intent.succeeded', 'payment_intent.cancelled', 'refund.received', 'refund.accepted', 'refund.settled', 'refund.failed')
API_HOSTS = {'test': 'https://api.sandbox.airwallex.com', 'live': 'https://api.airwallex.com'}


class PaymentUnavailable(APIException):
    status_code = 503
    default_detail = 'Airwallex payment is unavailable. Your order is saved; please retry later.'


def current_config():
    return AirwallexConfig.objects.filter(pk=1).first() or AirwallexConfig(pk=1)


@sensitive_variables()
def payment_config(config=None):
    config = config or current_config()
    try:
        values = credentials(getattr(config, config.mode + '_credentials')) if config.enabled else {}
        ready = config.storefront_url.startswith('https://') and all(values.get(k) for k in REQUIRED_KEYS)
    except CredentialStorageUnavailable:
        ready = False
    return {'provider': 'airwallex' if config.enabled else 'demo',
            'mode': config.mode if config.enabled else 'demo', 'available': bool(ready) if config.enabled else True}


@sensitive_variables()
def safe_config(config):
    result = {key: getattr(config, key) for key in ('enabled', 'mode', 'storefront_url', 'revision')}
    result.update(encryption_ready=encryption_ready(), webhook_events=WEBHOOK_EVENTS,
                  webhook_path='/api/v1/payments/airwallex/webhook/', available=payment_config(config)['available'])
    for mode in ('test', 'live'):
        try:
            values = credentials(getattr(config, mode + '_credentials'))
            result[mode] = {k: {'configured': bool(values.get(k)), 'masked': '••••' + values[k][-4:] if values.get(k) else ''} for k in KEYS}
        except CredentialStorageUnavailable:
            result['encryption_ready'] = False
            result[mode] = {k: {'configured': True, 'masked': '无法解密'} for k in KEYS}
    return result


class CredentialUpdate(StrictSerializer):
    client_id = serializers.CharField(required=False, allow_blank=True, max_length=1024)
    api_key = serializers.CharField(required=False, allow_blank=True, max_length=1024)
    webhook_secret = serializers.CharField(required=False, allow_blank=True, max_length=1024)
    account_id = serializers.CharField(required=False, allow_blank=True, max_length=36)
    clear = serializers.BooleanField(default=False)

    def validate_account_id(self, value):
        if not value:
            return value
        try:
            return str(uuid.UUID(value))
        except ValueError:
            raise serializers.ValidationError('请填写收款账户的 Account ID（UUID），不是 Client ID 或组织 ID。')

    def validate(self, data):
        if data['clear'] and any(data.get(k) for k in KEYS):
            raise serializers.ValidationError('清除和填写密钥不能同时执行。')
        if any('\n' in data.get(k, '') or '\r' in data.get(k, '') for k in KEYS):
            raise serializers.ValidationError('凭据不能包含换行。')
        return data


class ConfigUpdate(StripeConfigUpdate):
    test = CredentialUpdate(required=False)
    live = CredentialUpdate(required=False)

    def validate(self, data):
        return data

    def validate_storefront_url(self, value):
        value = super().validate_storefront_url(value)
        if value and not value.startswith('https://'):
            raise serializers.ValidationError('Airwallex 收银台返回地址需要 HTTPS；本机联调请使用 HTTPS 测试域名。')
        return value


@method_decorator(never_cache, name='dispatch')
@method_decorator(sensitive_post_parameters(), name='dispatch')
class AirwallexSettings(APIView):
    permission_classes = [SuperuserOnly]

    def get(self, request):
        return Response(safe_config(current_config()))

    @sensitive_variables()
    @transaction.atomic
    def patch(self, request):
        from .payments import lock_configs, disable_other
        serializer = ConfigUpdate(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        other, config = lock_configs()
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
            elif any(update.get(k) for k in KEYS):
                values = credentials(getattr(config, field))
                values.update({k: update[k] for k in KEYS if update.get(k)})
                setattr(config, field, encrypt_credentials(values))
                changed.append(mode + ' 更新密钥')
        if config.enabled:
            if not payment_config(config)['available']:
                raise serializers.ValidationError('启用前请填写 HTTPS 网站地址及当前环境的 Client ID、API Key、Webhook 签名密钥。')
            disable_other(request, other)
        if changed:
            config.revision += 1
            config.save()
            audit(request, 'update', config._meta.label_lower, config, '修改 Airwallex 配置：' + '、'.join(changed))
        return Response(safe_config(config))


@sensitive_variables()
def checkout_settings(mode):
    config = current_config()
    if not config.enabled or config.mode != mode:
        raise Conflict('Payment settings changed. Reload to review the payment method.')
    if not payment_config(config)['available']:
        raise PaymentUnavailable()
    return {'mode': 'airwallex_' + mode, 'status': 'pending',
            'payment_credentials': getattr(config, mode + '_credentials'), 'payment_return_url': config.storefront_url}


@sensitive_variables()
def api_request(order, method, path, *, body=None, params=None):
    """Fixed hosts, bounded timeouts, and environment/credential-isolated token cache."""
    mode = order.mode.removeprefix('airwallex_')
    host = API_HOSTS[mode]
    values = credentials(order.payment_credentials)
    cache_key = 'airwallex-token:' + hashlib.sha256((mode + json.dumps(values, sort_keys=True)).encode()).hexdigest()
    try:
        token = cache.get(cache_key)
        if not token:
            headers = {'x-client-id': values['client_id'], 'x-api-key': values['api_key'], 'Content-Type': 'application/json'}
            if values.get('account_id'):
                headers['x-login-as'] = values['account_id']
            response = requests.post(host + '/api/v1/authentication/login', headers=headers,
                timeout=(3, 5), allow_redirects=False)
            response.raise_for_status()
            auth = response.json()
            token = auth['token']
            expiry = parse_datetime(auth['expires_at'])
            if not isinstance(token, str) or not token or not expiry or not timezone.is_aware(expiry):
                raise ValueError()
            ttl = int((expiry - timezone.now()).total_seconds()) - 60
            if ttl > 0:
                cache.set(cache_key, token, timeout=min(ttl, 1800))
        response = requests.request(method, host + path, headers={'Authorization': 'Bearer ' + token,
            'Content-Type': 'application/json'}, json=body, params=params, timeout=(3, 5), allow_redirects=False)
        if response.status_code == 401:
            cache.delete(cache_key)
        # An interrupted create may already have succeeded. Recover exactly the
        # same intent by merchant reference, never generate a fresh request ID.
        if response.status_code == 400 and method == 'POST' and path == '/api/v1/pa/payment_intents/create' and response.json().get('code') == 'duplicate_request':
            result = api_request(order, 'GET', '/api/v1/pa/payment_intents',
                                 params={'merchant_order_id': str(order.reference), 'page_size': 10})
            matches = [item for item in result.get('items', []) if item.get('request_id') == str(order.reference)]
            if len(matches) != 1:
                raise ValueError()
            return api_request(order, 'GET', '/api/v1/pa/payment_intents/' + intent_id(matches[0].get('id')))
        if response.status_code not in (200, 201):
            raise ValueError()
        result = response.json()
        if not isinstance(result, dict):
            raise ValueError()
        return result
    except (requests.RequestException, ValueError, KeyError, TypeError, AttributeError):
        raise PaymentUnavailable() from None


def intent_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'int_[A-Za-z0-9_-]{1,240}', value):
        raise ValueError('Invalid intent ID')
    return value


def matches_order(intent, order):
    try:
        return (intent_id(intent.get('id'))
                and intent.get('merchant_order_id') == str(order.reference)
                and intent.get('metadata', {}).get('order_reference') == str(order.reference)
                and Decimal(str(intent.get('amount'))) == order.amount
                and intent.get('currency') == order.currency
                and (not order.airwallex_payment_intent or intent['id'] == order.airwallex_payment_intent))
    except (ValueError, TypeError, InvalidOperation, AttributeError):
        return False


@sensitive_variables()
def create_intent(order):
    params = {'request_id': str(order.reference), 'merchant_order_id': str(order.reference),
              'amount': float(order.amount), 'currency': order.currency,
              'return_url': order.payment_return_url + '#payment?order=' + str(order.reference),
              'metadata': {'order_reference': str(order.reference)}}
    if order.customer_email:
        params['customer'] = {'email': order.customer_email}
    return api_request(order, 'POST', '/api/v1/pa/payment_intents/create', body=params)


class AirwallexCheckout(StoreOrders):
    http_method_names = ['post', 'options']

    @sensitive_variables()
    @transaction.atomic
    def post(self, request, reference):
        order = get_object_or_404(PrintOrder.objects.select_for_update(), reference=reference, owner_hash=owner(request))
        if order.mode not in ('airwallex_test', 'airwallex_live') or order.status != 'pending':
            raise Conflict('This order is not awaiting Airwallex payment. Refresh its status.')
        require_single_print_payment(order)
        if order.airwallex_payment_intent:
            intent = api_request(order, 'GET', '/api/v1/pa/payment_intents/' + intent_id(order.airwallex_payment_intent))
        else:
            # Local checkout deadline; never rotate the provider request ID.
            if order.created_at + timedelta(hours=23) <= timezone.now():
                raise Conflict('This checkout expired. Check its payment status before creating a new order.')
            intent = create_intent(order)
        if not matches_order(intent, order):
            raise PaymentUnavailable()
        order.airwallex_payment_intent = intent['id']
        order.save(update_fields=['airwallex_payment_intent', 'updated_at'])
        if intent.get('status') not in ('REQUIRES_PAYMENT_METHOD', 'REQUIRES_CUSTOMER_ACTION'):
            raise Conflict('Payment is processing or closed. Refresh payment status before trying again.')
        if not isinstance(intent.get('client_secret'), str) or not intent['client_secret']:
            raise PaymentUnavailable()
        return Response({'provider': 'airwallex', 'order': order_data(order), 'checkout': {
            'env': 'prod' if order.mode == 'airwallex_live' else 'demo', 'mode': 'payment',
            'intent_id': intent['id'], 'client_secret': intent['client_secret'], 'currency': order.currency,
            'successUrl': order.payment_return_url + '#payment?order=' + str(order.reference) + '&result=success'}})


def valid_signature(request, payload, secret):
    timestamp, signature = request.headers.get('x-timestamp', ''), request.headers.get('x-signature', '')
    if not secret or not re.fullmatch(r'\d{13}', timestamp) or not re.fullmatch(r'[0-9a-f]{64}', signature):
        return False
    expected = hmac.new(secret.encode(), timestamp.encode() + payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected) and abs(time.time() * 1000 - int(timestamp)) <= 300_000


@method_decorator(never_cache, name='dispatch')
class AirwallexWebhook(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = []

    @sensitive_variables()
    def post(self, request):
        payload = request.body
        # The untrusted reference selects a frozen secret only. Nothing is
        # returned or mutated based on it until verification of the raw bytes.
        try:
            event = json.loads(payload)
            from .refunds import AIRWALLEX_EVENTS, refund_webhook
            if event.get('name') in AIRWALLEX_EVENTS:
                return refund_webhook(request, payload, 'airwallex')
            obj = event['data']['object']
            reference = uuid.UUID(obj['merchant_order_id'])
        except (ValueError, TypeError, KeyError, AttributeError):
            return Response({'detail': 'Invalid payment event.'}, status=400)
        order = PrintOrder.objects.filter(reference=reference, mode__in=['airwallex_test', 'airwallex_live']).first()
        if not order or not valid_signature(request, payload, credentials(order.payment_credentials).get('webhook_secret', '')):
            return Response({'detail': 'Invalid payment signature.'}, status=400)
        if event.get('name') not in WEBHOOK_EVENTS:
            return Response({'received': True})
        if not isinstance(event.get('id'), str) or not 0 < len(event['id']) <= 255 or not matches_order(obj, order):
            return Response({'detail': 'Payment does not match this order.'}, status=400)
        # Resolve using the order's original account/environment, never an event
        # field or the current admin config. A signed sandbox event cannot pay a
        # live order, even if an operator reused the webhook secret.
        intent = api_request(order, 'GET', '/api/v1/pa/payment_intents/' + intent_id(obj['id']))
        if not matches_order(intent, order) or intent['id'] != obj['id']:
            return Response({'detail': 'Payment does not match this order.'}, status=400)
        if intent.get('status') == 'SUCCEEDED':
            try:
                fully_captured = Decimal(str(intent.get('captured_amount'))) == order.amount
            except InvalidOperation:
                fully_captured = False
            if not fully_captured:
                return Response({'detail': 'Captured amount does not match this order.'}, status=400)
        with transaction.atomic():
            order = PrintOrder.objects.select_for_update().get(pk=order.pk)
            if not matches_order(intent, order):
                return Response({'detail': 'Payment does not match this order.'}, status=400)
            target = 'paid' if intent.get('status') == 'SUCCEEDED' else 'cancelled' if intent.get('status') == 'CANCELLED' else None
            if target and (order.status == 'pending' or (target == 'paid' and order.status == 'cancelled')):
                order.status = target
                order.airwallex_payment_intent = intent['id']
                order.airwallex_event_id = event['id']
                if target == 'paid':
                    order.paid_at = timezone.now()
                order.revision += 1
                order.save(update_fields=['status', 'airwallex_payment_intent', 'airwallex_event_id', 'paid_at', 'revision', 'updated_at'])
                AuditLog.objects.create(actor_name='Airwallex', action='payment' if target == 'paid' else 'cancel',
                    resource='management_api.printorder', object_id=str(order.pk),
                    summary=f'Airwallex {order.mode} · {order.reference} · {target}')
        return Response({'received': True})

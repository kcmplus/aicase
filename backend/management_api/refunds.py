"""Full original-method refunds. Persist the idempotency key before any remote write."""
import json
import re
import uuid
from datetime import timedelta
from decimal import Decimal, InvalidOperation

import stripe
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework import serializers
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import APIView

from .ai_service import SuperuserOnly
from .audit import audit
from .models import PrintOrder, PrintRefund, AuditLog, SupplierOrder
from .orders import StrictSerializer, Conflict
from .stripe_payments import credentials

AIRWALLEX_EVENTS = ('refund.received', 'refund.accepted', 'refund.settled', 'refund.failed')
STRIPE_EVENTS = ('refund.created', 'refund.updated', 'refund.failed')
PAID_STATES = ('paid', 'printing', 'ready', 'completed')


class RefundUnavailable(APIException):
    status_code = 503
    default_detail = '暂时无法确认退款结果。请刷新退款状态，勿在其他页面重复退款。'


def refund_data(order, private=False):
    refund = getattr(order, 'refund', None)
    if not refund:
        return None
    data = {k: getattr(refund, k) for k in ('reference', 'status', 'amount', 'currency', 'created_at', 'completed_at')}
    if private:
        data.update(provider_id=refund.provider_id, reason=refund.reason)
    return data


def printing_in_flight(order):
    row = SupplierOrder.objects.filter(order=order).defer('print_image', 'preview_image').first()
    if not row:
        return False
    try:
        supplier_paid = Decimal(str(row.cloud_status.get('pay_money', '0'))) > 0
    except InvalidOperation:
        supplier_paid = True  # Malformed accounting history requires review.
    cancelled_before_execution = bool(row and row.cloud_status.get('phase') == 'cancelled'
        and row.cloud_status.get('phase_verified') and row.cloud_status.get('print_status') == 0
        and row.cloud_status.get('shipment_status') == 0 and row.cloud_synced_at
        and row.cloud_synced_at >= timezone.now()-timedelta(seconds=60))
    supplier_progress = (row.cloud_status.get('print_status') not in (None, 0)
                         or row.cloud_status.get('shipment_status') not in (None, 0))
    return bool(((row.print_confirmed_at and row.release_state != 'idle') or supplier_paid or supplier_progress)
        and row.native_print_status not in ('deliver_success', 'grab_failed', 'print_failed', 'deliver_failed')
        and not cancelled_before_execution
        and not row.cloud_status.get('dispensed_confirmed')
        and not (row.cloud_status.get('phase_verified') and row.cloud_status.get('phase') in ('dispensed', 'print_failed', 'delivery_failed')))


def eligible(order):
    return (order.status in PAID_STATES and order.paid_at is not None and order.amount > 0
            and not printing_in_flight(order)
            and order.currency == 'USD' and
            ((order.mode in ('airwallex_test', 'airwallex_live') and bool(order.airwallex_payment_intent))
             or (order.mode in ('stripe_test', 'stripe_live') and bool(order.stripe_payment_intent))))


def stripe_client(order):
    return stripe.StripeClient(credentials(order.payment_credentials)['secret_key'], max_network_retries=0,
                               http_client=stripe.RequestsClient(timeout=12))


def provider_call(order, operation, refund=None, remote_id=None):
    """Only fixed provider hosts and the order's frozen account/credentials."""
    from .airwallex_payments import api_request, matches_order
    try:
        airwallex = order.mode.startswith('airwallex_')
        if airwallex:
            if operation == 'list':
                result = api_request(order, 'GET', '/api/v1/pa/refunds', params={
                    'payment_intent_id': order.airwallex_payment_intent, 'page_size': 100})
                if result.get('has_more') or not isinstance(result.get('items'), list):
                    raise RefundUnavailable()
                return result['items']
            if operation == 'retrieve':
                if not re.fullmatch(r'rfd_[A-Za-z0-9_]+', remote_id or ''):
                    raise RefundUnavailable()
                return api_request(order, 'GET', '/api/v1/pa/refunds/' + remote_id)
            intent = api_request(order, 'GET', '/api/v1/pa/payment_intents/' + order.airwallex_payment_intent)
            if (not matches_order(intent, order) or intent.get('status') != 'SUCCEEDED'
                    or Decimal(str(intent.get('captured_amount'))) != refund.amount):
                raise Conflict('渠道付款记录不符合整单退款条件，请先核对。')
            return api_request(order, 'POST', '/api/v1/pa/refunds/create', body={
                'request_id': str(refund.reference), 'payment_intent_id': order.airwallex_payment_intent,
                'amount': float(refund.amount), 'reason': refund.reason,
                'metadata': {'order_reference': str(order.reference), 'refund_reference': str(refund.reference)}})
        client = stripe_client(order)
        if operation == 'list':
            result = client.v1.refunds.list({'payment_intent': order.stripe_payment_intent, 'limit': 100}).to_dict()
            if result.get('has_more') or not isinstance(result.get('data'), list):
                raise RefundUnavailable()
            return result['data']
        if operation == 'retrieve':
            if not re.fullmatch(r're_[A-Za-z0-9]+', remote_id or ''):
                raise RefundUnavailable()
            return client.v1.refunds.retrieve(remote_id).to_dict()
        intent = client.v1.payment_intents.retrieve(order.stripe_payment_intent).to_dict()
        if (intent.get('id') != order.stripe_payment_intent or intent.get('status') != 'succeeded'
                or intent.get('amount_received') != int(refund.amount * 100)
                or intent.get('currency') != refund.currency.lower()
                or intent.get('livemode') != (order.mode == 'stripe_live')):
            raise Conflict('渠道付款记录不符合整单退款条件，请先核对。')
        return client.v1.refunds.create({'payment_intent': order.stripe_payment_intent,
            'amount': int(refund.amount * 100), 'reason': 'requested_by_customer',
            'metadata': {'order_reference': str(order.reference), 'refund_reference': str(refund.reference)}},
            options={'idempotency_key': 'case-refund-' + str(refund.reference)}).to_dict()
    except Conflict:
        raise
    except (stripe.StripeError, APIException, ValueError, KeyError, TypeError, AttributeError, InvalidOperation):
        raise RefundUnavailable() from None


def apply_result(order, refund, data):
    try:
        airwallex = order.mode.startswith('airwallex_')
        identifier = data['id']
        expected_id = order.airwallex_payment_intent if airwallex else order.stripe_payment_intent
        actual_id = data.get('payment_intent_id' if airwallex else 'payment_intent')
        amount = Decimal(str(data['amount'])) if airwallex else Decimal(str(data['amount'])) / 100
        metadata = data.get('metadata') or {}
        if (not re.fullmatch(r'rfd_[A-Za-z0-9_]+' if airwallex else r're_[A-Za-z0-9]+', identifier)
                or actual_id != expected_id or amount != refund.amount
                or data['currency'].upper() != refund.currency
                or metadata.get('order_reference') != str(order.reference)
                or metadata.get('refund_reference') != str(refund.reference)
                or (refund.provider_id and refund.provider_id != identifier)):
            raise ValueError()
        states = {'RECEIVED': 'pending', 'ACCEPTED': 'succeeded', 'SETTLED': 'succeeded', 'FAILED': 'failed'} if airwallex else {
            'pending': 'pending', 'requires_action': 'pending', 'succeeded': 'succeeded', 'failed': 'failed', 'canceled': 'failed'}
        target = states[data['status']]
    except (ValueError, KeyError, TypeError, AttributeError, InvalidOperation):
        raise RefundUnavailable() from None
    # Repeated or stale notifications cannot reopen a completed refund.
    if refund.status in ('succeeded', 'failed'):
        return
    changed = refund.status != target or refund.provider_id != identifier
    refund.provider_id = identifier
    refund.status = target
    if target == 'succeeded':
        refund.completed_at = timezone.now()
    refund.save(update_fields=['provider_id', 'status', 'completed_at', 'updated_at'])
    if changed:
        order.revision += 1
        order.save(update_fields=['revision', 'updated_at'])
        AuditLog.objects.create(actor_name='Payment refund', action='refund', resource='management_api.printorder',
            object_id=str(order.pk), summary=f'{order.reference} · {refund.reference} · {target} · {refund.currency} {refund.amount}')


@transaction.atomic
def reconcile(order_pk, create=False, remote_id=None):
    order = PrintOrder.objects.select_for_update().get(pk=order_pk)
    refund = PrintRefund.objects.select_for_update().get(order=order)
    if refund.status in ('succeeded', 'failed'):
        return refund_data(order, private=True)
    identifier = refund.provider_id or remote_id
    if identifier:
        data = provider_call(order, 'retrieve', remote_id=identifier)
    else:
        items = provider_call(order, 'list')
        matches = [item for item in items if (item.get('metadata') or {}).get('refund_reference') == str(refund.reference)]
        if len(matches) > 1:
            raise RefundUnavailable()
        if matches:
            data = provider_call(order, 'retrieve', remote_id=matches[0].get('id'))
        elif not create:
            return refund_data(order, private=True)
        else:
            # An external refund must be reconciled manually, never refund the full amount twice.
            if any(item.get('status') not in ('FAILED', 'failed', 'canceled') for item in items):
                raise Conflict('该付款已有其他退款记录，请先在支付渠道核对，不能再次整单退款。')
            if refund.created_at < timezone.now() - timedelta(hours=23):
                raise Conflict('退款请求已超过安全重试期限，请在支付渠道核对；此处仅允许刷新状态。')
            if not eligible(order):
                raise Conflict('此订单不符合退款条件。')
            data = provider_call(order, 'create', refund=refund)
    apply_result(order, refund, data)
    # The reverse relation may have been populated before apply_result.
    order.refund = refund
    return refund_data(order, private=True)


class RefundRequest(StrictSerializer):
    revision = serializers.IntegerField(min_value=1)
    confirmed = serializers.BooleanField()
    reason = serializers.CharField(max_length=128)


@method_decorator(never_cache, name='dispatch')
class AdminRefund(APIView):
    permission_classes = [SuperuserOnly]

    def get(self, request, pk):
        order = get_object_or_404(PrintOrder, pk=pk)
        if not hasattr(order, 'refund'):
            return Response({'refund': None})
        return Response({'refund': reconcile(order.pk)})

    def post(self, request, pk):
        serializer = RefundRequest(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if not data['confirmed']:
            raise serializers.ValidationError('请确认退款金额及原路退回。')
        # Commit this record before contacting the provider, even if the response is lost.
        with transaction.atomic():
            order = get_object_or_404(PrintOrder.objects.select_for_update(), pk=pk)
            refund = getattr(order, 'refund', None)
            if not refund:
                if printing_in_flight(order):
                    raise Conflict('顾客已确认打印，请先核对设备执行结果后再处理退款。')
                if data['revision'] != order.revision:
                    raise Conflict('订单已更新，请刷新后再确认退款。')
                if not eligible(order):
                    raise Conflict('仅已付款的 Stripe / Airwallex 订单支持原路退款。')
                # Preserve historical in-flight claims above. Only an unclaimed
                # legacy intent may be revoked; retired endpoints cannot release it.
                SupplierOrder.objects.filter(order=order, release_state='idle').update(print_confirmed_at=None)
                refund = PrintRefund.objects.create(order=order, amount=order.amount, currency=order.currency,
                    reason=data['reason'], requested_by=request.user)
                order.revision += 1
                order.save(update_fields=['revision', 'updated_at'])
                audit(request, 'refund', 'management_api.printorder', order,
                      f'申请整单退款 {refund.currency} {refund.amount} · {refund.reference} · {refund.reason}')
        return Response({'refund': reconcile(order.pk, create=True)})


def refund_webhook(request, payload, provider):
    """Called only for refund event names; untrusted metadata just selects the original secret."""
    from .airwallex_payments import valid_signature
    try:
        event = json.loads(payload)
        obj = event['data']['object']
        reference = uuid.UUID(obj.get('metadata', {}).get('refund_reference', ''))
    except (ValueError, KeyError, TypeError, AttributeError):
        return Response({'received': True})  # External refunds are not created or attached here.
    refund = PrintRefund.objects.select_related('order').filter(reference=reference, order__mode__startswith=provider + '_').first()
    if not refund:
        return Response({'received': True})
    secret = credentials(refund.order.payment_credentials).get('webhook_secret', '')
    if provider == 'airwallex':
        if not valid_signature(request, payload, secret):
            return Response({'detail': 'Invalid refund signature.'}, status=400)
    else:
        try:
            verified = stripe.Webhook.construct_event(payload, request.headers.get('Stripe-Signature', ''), secret).to_dict()
            if verified.get('livemode') != (refund.order.mode == 'stripe_live'):
                raise ValueError()
        except (ValueError, stripe.SignatureVerificationError):
            return Response({'detail': 'Invalid refund signature.'}, status=400)
    reconcile(refund.order_id, remote_id=obj.get('id'))
    return Response({'received': True})

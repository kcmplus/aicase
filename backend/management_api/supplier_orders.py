"""Phone-selected cloud orders. Unknown remote writes are never replayed."""
import hashlib
import json
import re
import secrets
import time
import warnings
import uuid
from datetime import timedelta
from io import BytesIO
from urllib.parse import urlsplit

import requests
from PIL import Image
from django.conf import settings
from django.core import signing
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework import serializers
from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import NotFound, APIException
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from .customer_auth import customer_for
from .device_provider import DeviceProvider
from .models import PrintOrder, SupplierOrder, PrintRefund, AuditLog
from .orders import StoreOrders, StrictSerializer, Conflict, owner
from .store_catalog import available_stocks, stock_template
from .fulfillment import require_pickup, cloud_release_available

SALT = 'supplier-print-file-v1'

# Only pre-creation validation/authentication rejections are safe to offer again.
# A generic "系统异常" may occur after a remote write and remains unknown.
REJECTION_MESSAGES = frozenset(('未授权', '店铺ID必须填写', '设备ID必须填写'))


def can_retry_dispatch(row, order):
    return (row.state == 'rejected' and settings.SUPPLIER_ORDER_ENABLED
            and order.fulfillment_type == 'pickup' and can_dispatch_payment(order)
            and row.device.active and row.device.connection.active
            and not row.trade_no and not row.vendor_id and not row.print_confirmed_at
            and row.release_state == 'idle' and row.submitted_at is not None)


def digest(snapshot):
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def real_paid(order):
    return (order.status == 'paid' and order.paid_at is not None and order.amount > 0
            and order.mode in ('stripe_live', 'airwallex_live')
            and not PrintRefund.objects.filter(order=order).exclude(status='failed').exists())


def can_dispatch_payment(order):
    # Explicit server-issued no-charge orders are distinct from demo/channel tests.
    return real_paid(order) or (order.mode == 'free_test' and order.amount == 0
        and order.status == 'paid' and order.paid_at is not None
        and not PrintRefund.objects.filter(order=order).exclude(status='failed').exists())


def audit_state(row, action):
    AuditLog.objects.create(actor_name='Supplier orders', action=action,
        resource='management_api.printorder', object_id=str(row.order_id),
        summary=f'{row.order.reference} · device {row.device_id} · {action}')


def public_state(order):
    row = SupplierOrder.objects.select_related('device__connection').filter(order=order).defer('print_image', 'preview_image').first()
    if not row:
        return None
    from .device_info import public_device_identity
    identity = public_device_identity(row.device)
    return {'state': row.state, 'device_id': identity['device_id'],
            'can_retry_dispatch': can_retry_dispatch(row, order), 'submitted_at': row.submitted_at,
            'shop_id': identity['shop_id'], 'device_name': identity['name'],
            'device_location': identity['location'], 'device_number': identity['number'],
            'device_coordinates': identity['coordinates'],
            'message': row.message, 'print_confirmed': bool(row.print_confirmed_at),
            'release_state': row.release_state, 'print_status': row.native_print_status,
            'cloud_status': row.cloud_status, 'status_updated_at': row.cloud_synced_at,
            'enabled': settings.SUPPLIER_ORDER_ENABLED,
            'release_available': cloud_release_available(),
            'zero_release_unconfirmed': False,
            'can_confirm_print': (order.fulfillment_type == PrintOrder.Fulfillment.PICKUP
                                  and row.state == 'submitted' and row.release_state == 'idle' and not row.print_confirmed_at
                                  and not row.cloud_status.get('payment_recorded')
                                  and row.cloud_status.get('pay_money', '0.00') == '0.00'
                                  and row.cloud_status.get('status') != 4
                                  and row.cloud_status.get('phase') != 'cancelled'
                                  and cloud_release_available()
                                  and row.device.active and row.device.connection.active and can_dispatch_payment(order))}


class Target(StrictSerializer):
    device_id = serializers.RegexField(r'^[0-9]{1,40}$')
    shop_id = serializers.RegexField(r'^[0-9]{1,40}$')
    inventory_item_id = serializers.IntegerField(min_value=1)
    accept_template = serializers.BooleanField(default=False)


def mutable_order(request, reference):
    if customer_for(request):
        SessionAuthentication().enforce_csrf(request)
    order = get_object_or_404(PrintOrder.objects.select_for_update(), reference=reference, owner_hash=owner(request))
    require_pickup(order)
    if order.status not in ('pending', 'paid') or (not order.mode.startswith(('stripe_', 'airwallex_')) and order.mode != 'free_test'):
        raise Conflict('This order cannot be sent to a device.')
    if PrintRefund.objects.filter(order=order).exclude(status='failed').exists():
        raise Conflict('An order with an active refund cannot be printed.')
    return order


@method_decorator(never_cache, name='dispatch')
class OrderTarget(StoreOrders):
    http_method_names = ['post', 'options']

    @transaction.atomic
    def post(self, request, reference):
        order = mutable_order(request, reference)
        serializer = Target(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        stock = available_stocks().filter(pk=data['inventory_item_id'],
            device__vendor_device_id=data['device_id'], device__connection__shop_id=data['shop_id'],
            product__phone_model__name=order.model_name).first()
        if not stock or stock.product.connection_id != stock.device.connection_id:
            raise Conflict('The selected device does not have this phone model available.')
        # Bind the exact server-validated template selected in the design. Switching
        # to another template requires a new render/review, never a silent substitute.
        if order.snapshot.get('_inventory_item') != stock.pk and not data['accept_template']:
            raise Conflict('Review your design using the selected device’s template first.')
        if not stock.product.goods_id.isascii() or not stock.product.goods_id.isdecimal() or int(stock.product.goods_id) <= 0:
            raise Conflict('The supplier product ID is invalid.')
        row = SupplierOrder.objects.filter(order=order).first()
        if row:
            if row.inventory_item_id != stock.pk or row.snapshot_sha256 != digest(order.snapshot):
                raise Conflict('This order is already bound to a different device or design.')
        else:
            if order.snapshot.get('_inventory_item') != stock.pk:
                # The owner explicitly selects this device's template. Preserve all
                # artwork edits and freeze the replacement before rendering/upload.
                template = stock_template(stock)
                order.snapshot = {**order.snapshot, '_inventory_item': stock.pk,
                                  '_template': template, 'phoneTemplateId': template['id']}
                order.revision += 1
                order.save(update_fields=['snapshot', 'revision', 'updated_at'])
            row = SupplierOrder.objects.create(order=order, device=stock.device, inventory_item=stock,
                business_number=str(time.time_ns() // 1_000_000) + f'{secrets.randbelow(1_000_000):06d}',
                goods_id=int(stock.product.goods_id), order_revision=order.revision,
                snapshot_sha256=digest(order.snapshot))
            audit_state(row, 'bind_device')
        return Response(public_state(order))


def png(upload, dimensions):
    if not upload or upload.size > 4_000_000:
        raise serializers.ValidationError('Upload a PNG file up to 4 MB.')
    content = upload.read(4_000_001)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as image:
                if image.format != 'PNG' or image.size != dimensions or image.width * image.height > 16_000_000:
                    raise ValueError()
                image.verify()
    except (OSError, ValueError, Image.DecompressionBombWarning, Image.DecompressionBombError):
        raise serializers.ValidationError('The PNG must match the order’s print template dimensions.') from None
    return content


@method_decorator(never_cache, name='dispatch')
class OrderFiles(StoreOrders):
    parser_classes = [MultiPartParser]
    http_method_names = ['post', 'options']

    @transaction.atomic
    def post(self, request, reference):
        order = mutable_order(request, reference)
        row = get_object_or_404(SupplierOrder.objects.select_for_update(), order=order)
        if row.state not in ('draft', 'prepared') or row.snapshot_sha256 != digest(order.snapshot):
            raise Conflict('The print files are already frozen or the design has changed.')
        template = order.snapshot.get('_template', {})
        dimensions = (template.get('printWidth'), template.get('printHeight'))
        if not all(isinstance(n, int) and n > 0 for n in dimensions):
            raise Conflict('The order has no supplier print template.')
        if set(request.data) != {'print_image', 'preview_image'}:
            raise serializers.ValidationError('Upload both print_image and preview_image PNG files.')
        final, preview = png(request.FILES.get('print_image'), dimensions), png(request.FILES.get('preview_image'), dimensions)
        checksum = hashlib.sha256(final + preview).hexdigest()
        if row.image_sha256 and row.image_sha256 != checksum:
            raise Conflict('Print files are immutable. Create a new order for a different image.')
        row.print_image, row.preview_image, row.image_sha256, row.state = final, preview, checksum, 'prepared'
        row.save()
        return Response(public_state(order))


class RetrySupplierOrder(StoreOrders):
    http_method_names = ['post', 'options']

    @transaction.atomic
    def post(self, request, reference):
        order = mutable_order(request, reference)
        row = get_object_or_404(SupplierOrder.objects.select_for_update(), order=order)
        class Retry(StrictSerializer):
            confirm = serializers.BooleanField()
            submitted_at = serializers.DateTimeField()
        serializer = Retry(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if not data['confirm'] or row.submitted_at != data['submitted_at']:
            raise Conflict('Reload the order before confirming this submission.')
        # An identical click before the worker claims it does not create more work.
        if row.state == 'prepared':
            return Response(public_state(order))
        if not can_retry_dispatch(row, order):
            raise Conflict('The previous submission must be checked before sending again.')
        stock = available_stocks().filter(pk=row.inventory_item_id).first()
        if (not stock or stock.device_id != row.device_id
                or stock.product.connection_id != row.device.connection_id
                or str(stock.product.goods_id) != str(row.goods_id)
                or stock_template(stock) != order.snapshot.get('_template')
                or row.snapshot_sha256 != digest(order.snapshot) or not row.image_sha256):
            raise Conflict('The station stock or template changed. Contact staff before sending.')
        row.state, row.message = 'prepared', ''
        row.save(update_fields=['state', 'message', 'updated_at'])
        audit_state(row, 'supplier_retry_confirmed')
        return Response(public_state(order))


@method_decorator(never_cache, name='dispatch')
class ConfirmSupplierPrint(StoreOrders):
    http_method_names = ['post', 'options']

    def post(self, request, reference):
        with transaction.atomic():
            order = mutable_order(request, reference)
            row = get_object_or_404(SupplierOrder.objects.select_for_update(), order=order)
            if not isinstance(request.data, dict) or set(request.data) != {'confirm'} or request.data['confirm'] is not True:
                raise serializers.ValidationError('Confirm that you are at the selected device.')
            if (row.state != 'submitted' or not can_dispatch_payment(order)
                    or not row.device.active or not row.device.connection.active):
                raise Conflict('This order is not ready for print confirmation.')
            pk = row.pk
        from .supplier_payments import record_merchant_payment
        record_merchant_payment(pk)
        order.refresh_from_db()
        return Response(public_state(order))


class PrintReleaseUnavailable(APIException):
    status_code = 503
    default_detail = 'Immediate printing is not enabled at this station. Your paid order is saved; no print command was sent. Please contact staff.'


class FulfillmentConfig(StoreOrders):
    http_method_names = ['get', 'options']

    def get(self, request):
        return Response({'enabled': settings.SUPPLIER_ORDER_ENABLED,
                         'release_enabled': cloud_release_available()})


def file_url(row, kind, origin):
    if kind not in ('print', 'preview'):
        raise ValueError('Invalid image kind')
    return f'{origin}/api/v1/supplier-images/{row.file_token}/{kind}.png'


@method_decorator(never_cache, name='dispatch')
class SupplierImage(StoreOrders):
    """Supplier-compatible PNG URL, unguessable and valid only for 72 hours."""
    http_method_names = ['get', 'options']

    def get(self, request, token, kind):
        row = get_object_or_404(SupplierOrder, file_token=token,
            state__in=('submitting', 'submitted', 'unknown'),
            submitted_at__gte=timezone.now()-timedelta(hours=72))
        content = {'print': row.print_image, 'preview': row.preview_image}.get(kind)
        if not content:
            raise NotFound('This print file is unavailable.')
        response = HttpResponse(bytes(content), content_type='image/png')
        response['Cache-Control'] = 'private, no-store'
        response['Referrer-Policy'] = 'no-referrer'
        response['X-Content-Type-Options'] = 'nosniff'
        return response


@method_decorator(never_cache, name='dispatch')
class SupplierFile(StoreOrders):
    http_method_names = ['get', 'options']

    def get(self, request, token):
        try:
            data = signing.loads(token, salt=SALT, max_age=72 * 3600)
            row = SupplierOrder.objects.get(order__reference=data['reference'], image_sha256=data['sha'])
            content = {'print': row.print_image, 'preview': row.preview_image}[data['kind']]
            if not content or row.state not in ('submitting', 'submitted', 'unknown'):
                raise ValueError()
        except (signing.BadSignature, SupplierOrder.DoesNotExist, ValueError, KeyError, TypeError):
            raise NotFound('This print file is unavailable.') from None
        response = HttpResponse(bytes(content), content_type='image/png')
        response['Cache-Control'] = 'private, no-store'
        response['Referrer-Policy'] = 'no-referrer'
        response['X-Content-Type-Options'] = 'nosniff'
        return response


def dispatch_order(pk):
    """Claim before I/O; a crashed or ambiguous POST must be reconciled manually."""
    if not settings.SUPPLIER_ORDER_ENABLED:
        return False
    origin = settings.SUPPLIER_ORDER_PUBLIC_URL.rstrip('/')
    url = urlsplit(origin)
    if url.scheme != 'https' or not url.netloc or url.username or url.password or url.path or url.query or url.fragment:
        raise ValueError('Set SUPPLIER_ORDER_PUBLIC_URL to a public HTTPS origin.')
    # Lock order first, matching refunds and customer mutations.
    order_pk = SupplierOrder.objects.values_list('order_id', flat=True).get(pk=pk)
    with transaction.atomic():
        order = PrintOrder.objects.select_for_update().get(pk=order_pk)
        row = SupplierOrder.objects.select_for_update().select_related('device__connection').get(pk=pk)
        if (order.fulfillment_type != PrintOrder.Fulfillment.PICKUP
                or row.state != 'prepared' or not can_dispatch_payment(order)):
            return False
        if (row.snapshot_sha256 != digest(order.snapshot) or not row.device.active
                or not row.device.connection.active or not row.image_sha256):
            SupplierOrder.objects.filter(pk=pk).update(message='设备或订单已变更，暂不能推送，请联系工作人员。', updated_at=timezone.now())
            return False
        stock = available_stocks().filter(pk=row.inventory_item_id).first()
        if (not stock or stock.device_id != row.device_id or stock.product.connection_id != row.device.connection_id
                or stock.product.goods_id != str(row.goods_id)
                or stock_template(stock) != order.snapshot.get('_template')):
            SupplierOrder.objects.filter(pk=pk).update(message='库存或模板正在更新，暂未推送到设备。', updated_at=timezone.now())
            return False
        # Resolve credentials BEFORE claiming: local config errors are safe to retry.
        provider = DeviceProvider(row.device.connection)
        row.file_token = uuid.uuid4()
        print_url = file_url(row, 'print', origin)
        payload = {'business_number': row.business_number, 'shop_id': provider.shop_id,
            'device_id': row.device.vendor_device_id, 'goods_id': row.goods_id, 'source': 1,
            'product_pic_url': print_url, 'picture_origin_url': print_url,
            'picture_effect_url': file_url(row, 'preview', origin), 'language': 'en'}
        row.state, row.submitted_at, row.message = 'submitting', timezone.now(), ''
        row.save(update_fields=['state', 'submitted_at', 'message', 'file_token', 'updated_at'])
        audit_state(row, 'supplier_submit')
    try:
        # POST is deliberately not part of the retrying GET transport. Do not log
        # headers, signed URLs, response bodies, or provider exception text.
        with requests.post(provider.base_url + '/mp/UserOrder/saveOrder', json=payload,
            headers={'authorization': provider.authorization, 'Accept': 'application/json'},
            timeout=(3, 10), allow_redirects=False, stream=True) as response:
            content = bytearray()
            started = time.monotonic()
            for chunk in response.iter_content(8192):
                content.extend(chunk)
                if len(content) > 65536 or time.monotonic() - started > 15:
                    raise ValueError()
            result = json.loads(content)
            data = result.get('data') if isinstance(result, dict) else None
            if (response.status_code == 200 and isinstance(result, dict)
                    and result.get('code') in (400, 401) and data is None
                    and result.get('message') in REJECTION_MESSAGES):
                SupplierOrder.objects.filter(pk=pk, state='submitting').update(
                    state='rejected', message='推单未成功，订单和设备已保留。请联系工作人员修正配置后，再确认推单。',
                    updated_at=timezone.now())
                audit_state(row, 'supplier_rejected')
                return False
            # Real saveOrder verification returned HTTP 200 + code=200. The
            # documentation's code=0 examples are placeholders, not a contract.
            if response.status_code != 200 or result.get('code') != 200 or not isinstance(data, dict):
                raise ValueError()
            identifier, trade_no = str(data.get('id', '')), data.get('trade_no')
            if (not re.fullmatch(r'[1-9][0-9]{0,19}', identifier) or not isinstance(trade_no, str)
                    or not re.fullmatch(r'[A-Za-z0-9_-]{1,120}', trade_no) or trade_no.lower() in ('string', 'null', 'undefined')
                    or data.get('business_number', row.business_number) != row.business_number
                    or str(data.get('device_id', row.device.vendor_device_id)) != row.device.vendor_device_id
                    or str(data.get('goods_id', row.goods_id)) != str(row.goods_id)):
                raise ValueError()
        SupplierOrder.objects.filter(pk=pk, state='submitting').update(
            state='submitted', vendor_id=identifier, trade_no=trade_no, message='', updated_at=timezone.now())
        audit_state(row, 'supplier_submitted')
        return True
    except (requests.RequestException, ValueError, TypeError, AttributeError):
        SupplierOrder.objects.filter(pk=pk, state='submitting').update(
            state='unknown', message='推单结果待核实，请联系工作人员；请勿重复下单。', updated_at=timezone.now())
        audit_state(row, 'supplier_unknown')
        return False


def dispatch_pending(limit=20):
    # A killed worker may have sent its request. Never reset it to prepared.
    SupplierOrder.objects.filter(state='submitting', submitted_at__lt=timezone.now()-timedelta(minutes=2)).update(
        state='unknown', message='推单结果待核实，请联系工作人员；请勿重复下单。')
    ids = SupplierOrder.objects.filter(state='prepared', order__fulfillment_type=PrintOrder.Fulfillment.PICKUP,
        order__status='paid', order__paid_at__isnull=False).filter(
        Q(order__mode__in=('stripe_live', 'airwallex_live'), order__amount__gt=0) |
        Q(order__mode='free_test', order__amount=0)).filter(
        Q(order__refund__isnull=True) | Q(order__refund__status='failed')).order_by('updated_at', 'pk').values_list('pk', flat=True)[:limit]
    return sum(dispatch_order(pk) for pk in list(ids))

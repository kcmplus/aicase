"""Merchant self-payment records, not a second customer charge or a native IPC call."""
import json
import re
import time
import uuid
from datetime import timedelta
from decimal import Decimal, InvalidOperation

import requests
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import APIException

from .device_provider import DeviceProvider, ProviderError
from .fulfillment import cloud_release_available
from .models import PrintOrder, SupplierOrder
from .orders import Conflict
from .store_catalog import available_stocks, stock_template
from .case_materials import stock_material
from .supplier_orders import audit_state, digest, can_dispatch_payment


class SupplierPaymentUnavailable(APIException):
    status_code = 503
    default_detail = 'The station order could not be verified. No print command was sent. Please try again later.'


def identity(row):
    return (row.trade_no, row.device_id, row.vendor_id, row.goods_id,
            row.device.connection_id, row.device.connection.revision)


def money(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)) or len(str(value)) > 32:
        raise ValueError('Invalid amount')
    try:
        amount = Decimal(value)
        if not amount.is_finite() or amount < 0 or amount > Decimal('999999.99') or amount.as_tuple().exponent < -2:
            raise ValueError('Invalid amount')
        return amount
    except InvalidOperation:
        raise ValueError('Invalid amount') from None


def phase(record):
    if record['status'] == 4:
        return 'cancelled'  # Confirmed by the user on 2026-11-06.
    mapping = settings.SUPPLIER_ORDER_STATUS_MAP
    if not isinstance(mapping, dict):
        return 'unknown'
    allowed = {'print': {'idle', 'printing', 'printed', 'print_failed'},
               'shipment': {'idle', 'delivering', 'dispensed', 'delivery_failed'}}
    def mapped(kind, field):
        table = mapping.get(kind, {})
        value = table.get(str(record[field])) if isinstance(table, dict) else None
        return value if isinstance(value, str) and value in allowed[kind] else 'unknown'
    shipment, printing = mapped('shipment', 'shipment_status'), mapped('print', 'print_status')
    return shipment if shipment not in ('unknown', 'idle') else printing


def query_order(row):
    """Exact trade lookup, checked again even if the supplier ignores its filters."""
    if row.transport != 'supplier':
        raise ProviderError('Simulated orders cannot use supplier transport.')
    provider = DeviceProvider(row.device.connection)
    data = provider.get('/shop/order/list', device_id=row.device.vendor_device_id,
                        trade_no=row.trade_no, page=1, limit=10)
    if not isinstance(data, dict):
        raise ValueError('Invalid order list')
    lists = [data[key] for key in ('list', 'items') if key in data]
    if not lists or any(not isinstance(rows, list) or len(rows) > 100 for rows in lists):
        raise ValueError('Invalid order list')
    selected = []
    for rows in lists:
        matches = [item for item in rows if isinstance(item, dict) and item.get('trade_no') == row.trade_no]
        if len(matches) != 1:
            raise ValueError('Order missing or ambiguous')
        selected.append(matches[0])
    record = selected[0]
    fields = ('id', 'trade_no', 'shop_id', 'device_id', 'goods_id', 'pay_money', 'pay_status',
              'print_status', 'shipment_status', 'status', 'is_refund', 'is_deleted', 'currency')
    if any({key: other.get(key) for key in fields} != {key: record.get(key) for key in fields}
           for other in selected[1:]):
        raise ValueError('Conflicting order lists')
    if (str(record.get('id')) != row.vendor_id or str(record.get('shop_id')) != provider.shop_id
            or str(record.get('device_id')) != row.device.vendor_device_id
            or (record.get('goods_id') is not None and str(record['goods_id']) != str(row.goods_id))
            or record.get('business_number', row.business_number) != row.business_number):
        raise ValueError('Supplier order identity mismatch')
    for name in ('pay_status', 'print_status', 'shipment_status', 'status', 'is_refund', 'is_deleted'):
        if type(record.get(name)) is not int or not 0 <= record[name] <= 10000:
            raise ValueError('Invalid supplier status')
    supplied_currency = record.get('currency')
    currency = supplied_currency or row.device.connection.payment_currency
    currency_source = 'supplier' if supplied_currency else 'merchant_configuration'
    # Autovend returns a display symbol. Only the explicitly configured USD
    # contract disambiguates it; never infer USD from '$' alone or convert money.
    if supplied_currency == '$' and row.device.connection.payment_currency == 'USD':
        currency = 'USD'
        currency_source = 'merchant_configuration_symbol'
    if not isinstance(currency, str) or (currency and not re.fullmatch('[A-Z]{3}', currency)):
        raise ValueError('Supplier order currency is not confirmed')
    amount = money(record.get('pay_money'))
    return {name: record[name] for name in fields if name in record} | {
        'pay_money': format(amount, '.2f'), 'currency': currency, 'phase': phase(record),
        'currency_source': currency_source,
        'phase_verified': record['status'] == 4 or settings.SUPPLIER_ORDER_STATUS_VERIFIED}


def payment_recorded(order, record):
    # Zero price alone proves nothing. Live probe confirmed pay_status 0 -> 1.
    return (record['currency'] == order.currency and money(record['pay_money']) == order.amount
            and (order.amount > 0 or (order.mode == 'free_test' and order.amount == 0 and record['pay_status'] == 1))
            and record['is_refund'] == 0 and record['is_deleted'] == 0 and record['status'] != 4)


def _apply(row, order, record):
    """Called with the order and supplier row locked. Unknown codes remain unknown."""
    before = row.cloud_status
    old_phase, new_phase = before.get('phase', 'unknown'), record['phase']
    verified = record.get('phase_verified', False)
    if (new_phase != 'cancelled' and before.get('phase_verified') and
            (not verified or old_phase == 'dispensed'
             or (new_phase in ('idle', 'unknown') and old_phase not in ('idle', 'unknown')))):
        new_phase = old_phase  # Delayed zero/unknown reads never undo observed progress.
        verified = True
    matched = payment_recorded(order, record)
    snapshot = {key: record[key] for key in ('pay_money', 'pay_status', 'print_status', 'shipment_status', 'status',
                'is_refund', 'is_deleted', 'currency')}
    snapshot.update(phase=new_phase, phase_verified=verified, payment_recorded=matched)
    snapshot['dispensed_confirmed'] = bool(before.get('dispensed_confirmed')
        or (before.get('phase_verified') and before.get('phase') == 'dispensed')
        or (verified and new_phase == 'dispensed'))
    snapshot['currency_source'] = record.get('currency_source', 'supplier')
    row.cloud_status, row.cloud_synced_at = snapshot, timezone.now()
    if row.print_confirmed_at:
        if matched:
            row.release_state = 'unknown' if verified and new_phase in ('print_failed', 'delivery_failed') else 'observed'
            row.message = '设备打印或出货异常，请联系工作人员核实。' if row.release_state == 'unknown' else ''
        elif money(record['pay_money']) > 0 or record['is_refund'] or record['is_deleted']:
            row.release_state, row.message = 'unknown', '供应商订单金额或退款状态待核实，请勿重复打印。'
        # A dead worker may have sent the write. Zero is not permission to retry it.
        elif row.release_state == 'claimed' and row.print_confirmed_at < timezone.now()-timedelta(seconds=30):
            row.release_state, row.message = 'unknown', '开印确认结果待核实，请勿重复打印。'
    if (matched and verified and order.status in ('paid', 'printing') and order.paid_at
            and order.mode in ('stripe_live', 'airwallex_live', 'free_test')):
        if new_phase == 'dispensed':
            order.status = 'ready'
        elif new_phase in ('printing', 'printed', 'delivering'):
            order.status = 'printing'
        order.save(update_fields=['status', 'updated_at'])
    if record['status'] == 4:
        row.message = '供应商订单已取消，请联系工作人员核实退款；请勿重复打印。'
    # Any observed physical-field change can prompt a READ of stock, without
    # interpreting an undocumented code or doing a local inventory decrement.
    changed = any(before.get(key) != snapshot[key] for key in ('pay_money', 'print_status', 'shipment_status'))
    if changed and (matched or record['print_status'] != 0 or record['shipment_status'] != 0):
        row.inventory_refresh_pending = True
    row.save(update_fields=['cloud_status', 'cloud_synced_at', 'release_state', 'message',
                            'inventory_refresh_pending', 'updated_at'])


def sync_order(pk, force=False):
    with transaction.atomic():
        row = SupplierOrder.objects.select_for_update(of=('self',)).select_related('device__connection', 'order').defer(
            'print_image', 'preview_image').get(pk=pk)
        if (row.transport != 'supplier' or row.state != 'submitted' or not row.trade_no or row.order.fulfillment_type != 'pickup'
                or not row.device.active or not row.device.connection.active):
            return False
        if not force and row.cloud_checked_at and row.cloud_checked_at > timezone.now()-timedelta(seconds=10):
            return False
        row.cloud_checked_at = timezone.now()
        row.save(update_fields=['cloud_checked_at'])
        checked_at = row.cloud_checked_at
        expected = identity(row)
    try:
        record = query_order(row)
    except (ProviderError, ValueError):
        return False  # Preserve the last known status; no fake empty queue or success.
    with transaction.atomic():
        order = PrintOrder.objects.select_for_update().get(pk=row.order_id)
        current = SupplierOrder.objects.select_for_update(of=('self',)).select_related('device__connection').get(pk=pk)
        if (expected != identity(current)
                or current.cloud_checked_at != checked_at or order.fulfillment_type != 'pickup'):
            return False
        _apply(current, order, record)
    return True


def record_merchant_payment(pk):
    """Persist a one-shot claim before POST. Never repeat an ambiguous merchant write."""
    if SupplierOrder.objects.only('transport').get(pk=pk).transport == 'direct_debug':
        from .direct_terminal import confirm
        return confirm(pk)
    if not cloud_release_available():
        from .supplier_orders import PrintReleaseUnavailable
        raise PrintReleaseUnavailable()
    row = SupplierOrder.objects.select_related('device__connection', 'order').defer('print_image', 'preview_image').get(pk=pk)
    if row.release_state != 'idle' or row.print_confirmed_at:
        return  # Durable idempotency, including old/unknown native claims.
    try:
        record = query_order(row)
    except (ProviderError, ValueError):
        raise SupplierPaymentUnavailable() from None
    if (record['status'] == 4 or money(record['pay_money']) > 0 or record['pay_status'] != 0
            or record['print_status'] != 0 or record['shipment_status'] != 0):
        with transaction.atomic():
            order = PrintOrder.objects.select_for_update().get(pk=row.order_id)
            current = SupplierOrder.objects.select_for_update(of=('self',)).select_related('device__connection').get(pk=pk)
            if identity(current) == identity(row) and order.fulfillment_type == 'pickup':
                _apply(current, order, record)
        if record['status'] == 4:
            raise Conflict('The station order has been cancelled. Contact staff before printing.')
    with transaction.atomic():
        order = PrintOrder.objects.select_for_update().get(pk=row.order_id)
        current = SupplierOrder.objects.select_for_update().select_related('device__connection').get(pk=pk)
        if current.release_state != 'idle' or current.print_confirmed_at:
            return
        if (order.fulfillment_type != 'pickup' or not can_dispatch_payment(order) or current.state != 'submitted'
                or not current.device.active or not current.device.connection.active
                or identity(current) != identity(row)
                or current.snapshot_sha256 != digest(order.snapshot)):
            raise Conflict('This order is not ready for print confirmation.')
        if not record['currency']:
            raise Conflict('The station payment currency is not configured. Please contact staff.')
        if record['currency'] != order.currency or record['is_refund'] or record['is_deleted'] or record['status'] == 4:
            raise Conflict('The station order needs staff review before printing.')
        amount = money(record['pay_money'])
        already_recorded = payment_recorded(order, record)
        if current.cloud_status.get('status') == 4 or current.cloud_status.get('phase') == 'cancelled':
            raise Conflict('The station order has been cancelled. Contact staff before printing.')
        if amount == 0 and not already_recorded and current.cloud_status.get('payment_recorded'):
            raise Conflict('The station order changed. Refresh its status before confirming again.')
        if amount > 0 and amount != order.amount:
            raise Conflict('The station payment amount needs staff review. Do not print again.')
        provider = DeviceProvider(current.device.connection)  # Credentials before claiming.
        if not already_recorded:
            # Fresh cloud orders were observed with zero print/payment states.
            # Any changed execution field is treated as ambiguous, never overwritten.
            if record['pay_status'] != 0 or record['print_status'] != 0 or record['shipment_status'] != 0:
                raise Conflict('The station order needs staff review before printing.')
            stock = available_stocks().filter(pk=current.inventory_item_id).first()
            if (not stock or stock.device_id != current.device_id
                    or stock.product.connection_id != current.device.connection_id
                    or stock.product.goods_id != str(current.goods_id)
                    or (order.case_material and stock_material(stock) != order.case_material)
                    or stock_template(stock) != order.snapshot.get('_template')):
                raise Conflict('The station inventory or template needs updating before printing.')
        current.print_confirmed_at, current.release_claim = timezone.now(), uuid.uuid4()
        current.release_state = 'observed' if already_recorded else 'claimed'
        current.save(update_fields=['print_confirmed_at', 'release_claim', 'release_state', 'updated_at'])
        _apply(current, order, record)
        audit_state(current, 'merchant_payment_claim')
    if already_recorded:
        return  # Already recorded by supplier. Do not overwrite it or pay twice.
    accepted = False
    try:
        with requests.post(provider.base_url+'/shop/order/updatePayStatus',
                json={'trade_no': row.trade_no, 'pay_money': format(order.amount, '.2f')},
                headers={'authorization': provider.authorization, 'Accept': 'application/json'},
                timeout=(3, 8), allow_redirects=False, stream=True) as response:
            content, started = bytearray(), time.monotonic()
            for chunk in response.iter_content(8192):
                content.extend(chunk)
                if len(content) > 65536 or time.monotonic()-started > 12:
                    raise ValueError('Invalid response')
            result = json.loads(content)
            data = result.get('data') if isinstance(result, dict) else None
            accepted = (response.status_code == 200 and isinstance(result, dict) and result.get('code') == 200
                        and (data is None or (isinstance(data, dict)
                             and data.get('trade_no', row.trade_no) == row.trade_no
                             and str(data.get('id', row.vendor_id)) == row.vendor_id)))
    except (requests.RequestException, ValueError, TypeError):
        pass
    SupplierOrder.objects.filter(pk=pk, release_state='claimed', release_claim=current.release_claim).update(
        release_state='submitted' if accepted else 'unknown',
        message='' if accepted else '开印确认结果待核实，请勿重复打印。', updated_at=timezone.now())
    # Ack is not payment or printing proof. Querying may also recover a lost POST response.
    sync_order(pk, force=True)
    audit_state(current, 'merchant_payment_submitted' if accepted else 'merchant_payment_unknown')


def sync_pending(limit=20):
    if not settings.SUPPLIER_ORDER_ENABLED:
        return 0
    SupplierOrder.objects.filter(transport='supplier', state='submitted', order__fulfillment_type='pickup',
        release_state__in=['claimed', 'submitted'],
        print_confirmed_at__lt=timezone.now()-timedelta(seconds=60)).update(
            release_state='unknown', message='开印确认结果待核实，请勿重复打印。')
    ids = list(SupplierOrder.objects.filter(transport='supplier', state='submitted', order__fulfillment_type='pickup',
        order__status__in=['paid', 'printing']).filter(
        Q(cloud_checked_at__isnull=True) | Q(cloud_checked_at__lt=timezone.now()-timedelta(seconds=10))
        ).order_by('cloud_checked_at', 'pk').values_list('pk', flat=True)[:limit])
    count = sum(sync_order(pk) for pk in ids)
    refresh_inventory(limit)
    return count


def refresh_inventory(limit=20):
    from .inventory_sync import sync_device
    from .models import InventorySyncRun
    devices = list(SupplierOrder.objects.filter(inventory_refresh_pending=True,
        order__fulfillment_type='pickup', device__active=True, device__connection__active=True
        ).order_by('device_id').values_list('device_id', flat=True).distinct()[:limit])
    for device_id in devices:
        started = timezone.now()
        if InventorySyncRun.objects.filter(device_id=device_id, started_at__gte=started-timedelta(seconds=10)).exists():
            continue
        try:
            run = sync_device(device_id)
        except ProviderError:
            continue
        if run.status == 'success':
            SupplierOrder.objects.filter(device_id=device_id, inventory_refresh_pending=True,
                cloud_synced_at__lte=started).update(inventory_refresh_pending=False)

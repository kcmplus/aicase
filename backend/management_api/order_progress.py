"""Read-only presentation of order progress; never grants printing permission."""
from datetime import timedelta
from django.db.models import Case, When, Value, CharField, Q
from django.utils import timezone
from .models import PrintOrder
from .device_info import public_device_identity

GROUPS = {
    'pending': ['awaiting_payment', 'unbound', 'awaiting_dispatch', 'submitting', 'awaiting_confirmation', 'waiting_device'],
    'printing': ['printing', 'printed', 'delivering'],
    'dispensed': ['dispensed'],
    'attention': ['unverified', 'rejected', 'print_failed', 'delivery_failed'],
    'closed': ['cancelled', 'closed', 'refunded', 'refund_pending'],
}


def with_order_progress(qs):
    f = 'supplier_order__'
    def cloud(**kwargs):
        return Q(**{f + 'cloud_status__' + key: value for key, value in kwargs.items()})
    physical = Q(paid_at__isnull=False) & cloud(phase_verified=True, payment_recorded=True)
    rules = [
        (Q(fulfillment_type__in=['courier', 'air']), 'delivery'),
        (~Q(fulfillment_type='pickup'), 'unspecified'),
        (Q(mode__in=['demo', 'stripe_test', 'airwallex_test']), 'test'),
        (~Q(mode__in=['stripe_live', 'airwallex_live', 'free_test']), 'unverified'),
        (Q(status='cancelled') | cloud(status=4) | cloud(phase='cancelled'), 'cancelled'),
    ]
    rules += [(physical & cloud(phase=phase), phase) for phase in
              ('dispensed', 'delivery_failed', 'print_failed', 'delivering', 'printed', 'printing')]
    rules += [
        (Q(refund__status='succeeded'), 'refunded'),
        (Q(refund__status__in=['requested', 'pending']), 'refund_pending'),
        (Q(status='completed'), 'closed'),
        (Q(status='pending', paid_at__isnull=True), 'awaiting_payment'),
        (Q(paid_at__isnull=True), 'unverified'),
        (Q(supplier_order__isnull=True), 'unbound'),
        (Q(supplier_order__state='unknown') | Q(supplier_order__release_state='unknown'), 'unverified'),
        (Q(supplier_order__state='rejected'), 'rejected'),
        (Q(supplier_order__state__in=['draft', 'prepared']), 'awaiting_dispatch'),
        (Q(supplier_order__state='submitting'), 'submitting'),
        (Q(supplier_order__state='submitted') & ((cloud(print_status__isnull=False) & ~cloud(print_status=0)) | (cloud(shipment_status__isnull=False) & ~cloud(shipment_status=0))), 'unverified'),
        (Q(supplier_order__state='submitted') & (Q(supplier_order__print_confirmed_at__isnull=False) | cloud(payment_recorded=True)) & (cloud(phase_verified=False) | cloud(phase_verified__isnull=True)), 'unverified'),
        (Q(supplier_order__state='submitted') & (Q(supplier_order__print_confirmed_at__isnull=False) | cloud(payment_recorded=True)), 'waiting_device'),
        (Q(supplier_order__state='submitted'), 'awaiting_confirmation'),
    ]
    return qs.select_related('refund', 'supplier_order__device__connection').defer(
        'supplier_order__print_image', 'supplier_order__preview_image').annotate(
        _progress_code=Case(*[When(condition, then=Value(code)) for condition, code in rules],
                            default=Value('unverified'), output_field=CharField()))


def order_progress(order):
    code = getattr(order, '_progress_code', None)
    if code is None:
        code = with_order_progress(PrintOrder.objects.filter(pk=order.pk)).values_list('_progress_code', flat=True).get()
    row = getattr(order, 'supplier_order', None)
    device = public_device_identity(row.device) if row else None
    updated = row.cloud_synced_at if row else None
    if order.mode in ('demo', 'stripe_test', 'airwallex_test'):
        payment = 'test'
    elif order.paid_at:
        payment = 'free' if order.mode == 'free_test' else 'paid'
    else:
        payment = 'unpaid' if order.status == 'pending' else 'unverified'
    station_order_ending = ''
    if row and row.transport == 'supplier' and order.fulfillment_type == 'pickup':
        station_order_ending = row.trade_no[-6:]
    return {'code': code, 'payment': payment, 'station_order_ending': station_order_ending,
            'group': next((key for key, values in GROUPS.items() if code in values), 'other'),
            'device': {key: device[key] for key in ('device_id', 'shop_id', 'name', 'location', 'number')} if device else None,
            'updated_at': updated,
            'stale': bool(row and row.state == 'submitted' and code not in ('dispensed', 'cancelled', 'closed', 'refunded', 'test', 'delivery', 'unspecified')
                          and (not updated or updated < timezone.now() - timedelta(seconds=60))),
            'message': row.message if row and code not in ('test', 'delivery', 'unspecified') else ''}


def progress_payload(order, private=False):
    from .refunds import refund_data
    from .supplier_orders import public_state
    return {'reference': order.reference, 'status': order.status, 'updated_at': order.updated_at,
            'progress': order_progress(order), 'fulfillment': public_state(order),
            'refund': refund_data(order, private=private)}

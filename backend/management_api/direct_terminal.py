"""Local backend-to-page transport. No supplier calls or physical fulfillment writes."""
import hashlib
import secrets
from datetime import datetime

from django.conf import settings
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Device, PrintOrder, SupplierOrder
from .orders import Conflict
from .store_catalog import available_stocks, stock_template


def enabled_for(device_id):
    return settings.DIRECT_DEBUG_ENABLED and device_id == settings.DIRECT_DEBUG_DEVICE_ID


def eligible(row, order):
    from .supplier_orders import can_dispatch_payment, digest
    return (row.transport == 'direct_debug' and enabled_for(row.device_id)
            and order.mode == 'free_test' and order.amount == 0
            and order.fulfillment_type == 'pickup' and can_dispatch_payment(order)
            and row.device.active and row.device.connection.active
            and row.snapshot_sha256 == digest(order.snapshot))


def stock_matches(row, order):
    stock = available_stocks().filter(pk=row.inventory_item_id).first()
    return (stock and stock.device_id == row.device_id
            and stock.product.connection_id == row.device.connection_id
            and str(row.goods_id) == stock.product.goods_id
            and stock_template(stock) == order.snapshot.get('_template'))


def locked(pk):
    order_id = SupplierOrder.objects.values_list('order_id', flat=True).get(pk=pk)
    order = PrintOrder.objects.select_for_update().get(pk=order_id)
    row = SupplierOrder.objects.select_for_update().select_related('device__connection').get(pk=pk)
    return row, order


@transaction.atomic
def dispatch(pk):
    from .supplier_orders import audit_state
    row, order = locked(pk)
    if row.state != 'prepared' or not eligible(row, order) or not stock_matches(row, order):
        return False
    if (not row.print_image or not row.preview_image or
            hashlib.sha256(bytes(row.print_image) + bytes(row.preview_image)).hexdigest() != row.image_sha256):
        return False
    row.state, row.trade_no = 'submitted', 'DEBUG-' + str(order.reference)
    row.submitted_at = timezone.now()
    row.cloud_synced_at = row.submitted_at
    row.cloud_status = {'simulated': True, 'phase': 'awaiting_confirmation', 'phase_verified': False}
    row.native_print_status = 'idle'
    row.message = ''
    row.save()
    audit_state(row, 'direct_debug_submitted')
    return True


@transaction.atomic
def confirm(pk):
    from .supplier_orders import audit_state, PrintReleaseUnavailable
    row, order = locked(pk)
    if not enabled_for(row.device_id):
        raise PrintReleaseUnavailable()
    if row.state != 'submitted' or not eligible(row, order) or not stock_matches(row, order):
        raise Conflict('This simulation order cannot be released.')
    if row.print_confirmed_at:
        return  # Phone retries do not restart the simulation.
    row.print_confirmed_at = timezone.now()
    row.release_state = 'simulated'
    row.cloud_status = {'simulated': True, 'phase': 'queued', 'phase_verified': False}
    row.cloud_synced_at = timezone.now()
    row.save(update_fields=['print_confirmed_at', 'release_state', 'cloud_status', 'cloud_synced_at', 'updated_at'])
    audit_state(row, 'direct_debug_confirmed')


def rows():
    return SupplierOrder.objects.filter(transport='direct_debug', device_id=settings.DIRECT_DEBUG_DEVICE_ID)


def tick():
    for pk in list(rows().filter(state='prepared').order_by('pk').values_list('pk', flat=True)[:20]):
        dispatch(pk)
    # One simulated machine, sequential processing; the physical order stays paid.
    for pk in rows().filter(state='submitted', print_confirmed_at__isnull=False).exclude(
            native_print_status='deliver_success').order_by('print_confirmed_at', 'pk').values_list('pk', flat=True):
        with transaction.atomic():
            row, order = locked(pk)
            if not eligible(row, order):
                continue
            now = timezone.now()
            started = row.cloud_status.get('simulation_started_at') or now.isoformat()
            elapsed = (now - datetime.fromisoformat(started)).total_seconds()
            phase, native, progress = ('printing', 'printing', min(99, int(elapsed / 20 * 100)))
            if elapsed >= 25:
                phase, native, progress = 'dispensed', 'deliver_success', 100
            elif elapsed >= 20:
                phase, native, progress = 'delivering', 'delivering', 100
            row.native_print_status = native
            row.cloud_status = {'simulated': True, 'phase': phase, 'phase_verified': False,
                                'simulation_started_at': started, 'progress': progress}
            row.cloud_synced_at = now
            row.save(update_fields=['native_print_status', 'cloud_status', 'cloud_synced_at', 'updated_at'])
        break


@method_decorator(never_cache, name='dispatch')
class DirectAPI(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = []

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not settings.DIRECT_DEBUG_ENABLED or not settings.DIRECT_DEBUG_DEVICE_ID:
            raise NotFound()
        token = settings.DIRECT_DEBUG_TOKEN
        if len(token) < 32 or not secrets.compare_digest(request.headers.get('Authorization', ''), 'Bearer ' + token):
            raise PermissionDenied('Direct debug token required.')


class DirectPoll(DirectAPI):
    def post(self, request):
        tick()
        device = get_object_or_404(Device.objects.select_related('connection'),
            pk=settings.DIRECT_DEBUG_DEVICE_ID, active=True, connection__active=True)
        data = []
        for row in rows().filter(state='submitted').select_related('order', 'device__connection').defer(
                'print_image', 'preview_image').order_by('-submitted_at', '-pk')[:100]:
            valid = eligible(row, row.order)
            data.append({'trade_no': row.trade_no, 'business_number': row.business_number,
                'goods_id': row.goods_id, 'model_id': row.order.model_name,
                'effect_image': f'/api/v1/debug-terminal/orders/{row.order.reference}/preview.png',
                'pay_status': 'success' if valid and row.print_confirmed_at else 'idle',
                'print_status': row.native_print_status if valid else 'idle',
                'status': 'canceled' if not valid else 'success' if row.native_print_status == 'deliver_success' else 'polling',
                'simulated': True, 'progress': row.cloud_status.get('progress')})
        current = next((row for row in reversed(data) if row['status'] != 'canceled' and
            row['print_status'] in ('printing', 'delivering')), None)
        machine = {'device_id': device.vendor_device_id, 'shop_id': device.connection.shop_id,
                   'h5_base_url': settings.DIRECT_DEBUG_H5_ORIGIN, 'is_show_contact_tel': False}
        return Response({'simulated': True, 'machine': machine,
            'options': {'device_id': device.vendor_device_id, 'device_name': device.name,
                        'device_num': device.provider_profile.get('device_num', ''), 'is_lock': False},
            'features': {'show_h5_entry': True}, 'orders': data, 'order': current,
            'progress': {'progress': current['progress']} if current and current['progress'] is not None else None,
            'stock': [{'slot': stock.pk, 'count': stock.stock, 'disabled': False,
                       'model_id': stock.product.phone_model.name} for stock in available_stocks()]})


class DirectPreview(DirectAPI):
    def get(self, request, reference):
        row = get_object_or_404(rows(), order__reference=reference, state='submitted')
        response = HttpResponse(bytes(row.preview_image), content_type='image/png')
        response['X-Content-Type-Options'] = 'nosniff'
        return response

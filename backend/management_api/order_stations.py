"""Order-specific station stock, read only: no reservation or device binding."""
from datetime import timedelta
from django.db.models import Exists, OuterRef, Prefetch, F, prefetch_related_objects
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.cache import never_cache
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import AllowAny
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from .models import Device, DeviceProduct, PrintOrder
from .orders import StoreOrders, owner
from .device_info import public_device_identity
from .device_location import device_coordinates
from .case_materials import MATERIALS, material_stocks
from .store_catalog import available_stocks


class OrderStations(StoreOrders):
    http_method_names = ['get', 'head', 'options']

    def get(self, request, reference):
        order = get_object_or_404(PrintOrder.objects.select_related('supplier_order', 'refund').defer(
            'snapshot', 'supplier_order__print_image', 'supplier_order__preview_image'),
                                 reference=reference, owner_hash=owner(request))
        target = getattr(order, 'supplier_order', None)
        refund = getattr(order, 'refund', None)
        allowed = (order.fulfillment_type == 'pickup' and order.mode in ('stripe_live', 'airwallex_live', 'free_test')
                   and order.status in ('pending', 'paid') and not (refund and refund.status != 'failed')
                   and not (target and (target.print_confirmed_at or target.state not in ('draft', 'prepared', 'rejected'))))
        result = station_options(request, order.model_name, target, order.case_material) if allowed else {'results': [], 'page': 1, 'has_more': False, 'max_age_seconds': 60}
        return Response({**result, 'reference': str(order.reference), 'model': order.model_name,
                         'case_material': order.case_material, 'applicable': allowed, 'bound': bool(target)})


def station_options(request, model_name, target=None, material=''):
    result = {'results': [], 'max_age_seconds': 60}
    try:
        page = int(request.query_params.get('page', '1'))
        if not 1 <= page <= 10000: raise ValueError()
    except ValueError:
        raise ValidationError({'detail': 'Invalid page.'})
    device_id, shop_id = request.query_params.get('device_id'), request.query_params.get('shop_id')
    if device_id is not None or shop_id is not None:
        if not all(isinstance(v, str) and v.isascii() and v.isdecimal() and len(v) <= 40 for v in (device_id, shop_id)):
            raise ValidationError({'detail': 'Invalid station.'})
    stocks = DeviceProduct.objects.filter(product__phone_model__name=model_name,
        product__connection_id=F('device__connection_id')).select_related('product__phone_model__brand')
    eligible = available_stocks().filter(product__phone_model__name=model_name,
        product__connection_id=F('device__connection_id'), product__goods_id__regex=r'^[0-9]*[1-9][0-9]*$')
    if material:
        stocks = material_stocks(stocks, material)
        eligible = material_stocks(eligible, material)
    elif not target:
        stocks, eligible = stocks.none(), eligible.none()
    if target:
        stocks = stocks.filter(pk=target.inventory_item_id)
        eligible = eligible.filter(pk=target.inventory_item_id)
    ambiguous = Device.objects.filter(vendor_device_id=OuterRef('vendor_device_id'),
        connection__shop_id=OuterRef('connection__shop_id')).exclude(pk=OuterRef('pk'))
    devices = Device.objects.select_related('connection').annotate(
        ambiguous=Exists(ambiguous), stocked=Exists(eligible.filter(device_id=OuterRef('pk'))))
    if target:
        devices = devices.filter(pk=target.device_id)  # Scanning another device never moves a bound order.
    else:
        devices = devices.filter(active=True, connection__active=True, ambiguous=False)
        if device_id is not None:
            devices = devices.filter(vendor_device_id=device_id, connection__shop_id=shop_id)
        else:
            devices = devices.filter(stocked=True)
    # Coordinates are required for nearby discovery, not for an explicitly
    # scanned device or an existing order target. Stock checks still apply.
    rows, valid_count = [], 0
    offset = (page - 1) * 20
    for device in devices.order_by('-stocked', 'pk').iterator(chunk_size=100):
        if target is None and device_id is None and device_coordinates(device) is None:
            continue
        if valid_count >= offset:
            rows.append(device)
        valid_count += 1
        if len(rows) == 21:
            break
    prefetch_related_objects(rows[:20], Prefetch('products', queryset=stocks, to_attr='model_stocks'))
    good_ids = set(eligible.filter(device_id__in=[d.pk for d in rows[:20]]).values_list('pk', flat=True))
    cutoff = timezone.now() - timedelta(minutes=15)
    for device in rows[:20]:
        candidates = device.model_stocks
        usable = [s for s in candidates if s.pk in good_ids]
        observed = min((s.observed_at for s in usable), default=None)
        if not device.active or not device.connection.active or device.ambiguous:
            status = 'unavailable'
        elif usable:
            status = 'available'
        elif not candidates:
            status = 'unsupported'
        elif any(s.observed_at is None or s.observed_at < cutoff for s in candidates):
            status = 'updating'
        elif all(s.stock <= 0 for s in candidates if s.present) and any(s.present for s in candidates):
            status = 'out_of_stock'
        else:
            status = 'unavailable'
        if observed is None:
            observed = min((s.observed_at for s in candidates if s.observed_at), default=None)
        result['results'].append({**public_device_identity(device), 'availability': status,
            'quantity': sum(s.stock for s in usable) if status == 'available' else 0 if status == 'out_of_stock' else None,
            'updated_at': observed})
    result.update(page=page, has_more=len(rows)>20)
    return result


@never_cache
@api_view(['GET'])
@permission_classes([AllowAny])
@authentication_classes([])
def public_print_stations(request):
    model = request.query_params.get('model', '')
    if not model or len(model) > 160:
        raise ValidationError({'detail': 'Please select a phone model.'})
    material = request.query_params.get('case_material', '')
    if material and material not in MATERIALS:
        raise ValidationError({'detail': 'Invalid case style.'})
    return Response({**station_options(request, model, material=material), 'case_material': material, 'model': model, 'applicable': True, 'bound': False})

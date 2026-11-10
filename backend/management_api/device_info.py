"""Public, read-only equipment identity and inventory; never a print authorization."""
from django.views.decorators.cache import never_cache
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import AllowAny
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from .models import Device
from .store_catalog import store_models
from .device_location import display_identity


def public_device_identity(device):
    # Location is maintained as the public installation address in inventory.
    # Never copy arbitrary supplier profile/contact fields to the customer page.
    return {'device_id': device.vendor_device_id, 'shop_id': device.connection.shop_id,
            'number': device.provider_profile.get('device_num', ''), **display_identity(device)}


@never_cache
@api_view(['GET'])
@permission_classes([AllowAny])
@authentication_classes([])
def public_device_info(request):
    device_id, shop_id = request.query_params.get('device_id'), request.query_params.get('shop_id')
    for value in (device_id, shop_id):
        if value is None or not value.isascii() or not value.isdecimal() or len(value) > 40:
            raise ValidationError({'detail': '请提供正确的设备编号和商家编号。'})
    matches = list(Device.objects.select_related('connection').filter(
        vendor_device_id=device_id, connection__shop_id=shop_id)[:2])
    if len(matches) != 1 or not matches[0].active or not matches[0].connection.active:
        raise NotFound('设备未开放或编号不明确，请检查设备链接。')
    device = matches[0]
    catalog = store_models({'device_id': device_id, 'shop_id': shop_id})
    config = device.provider_config
    # Do not infer online/ready from stale, undocumented vendor status codes.
    return Response({
        **public_device_identity(device), 'online_status': 'unknown',
        'currency': config.get('currency', ''), 'print_type': config.get('print_type', ''),
        'info_updated_at': device.last_success_at, 'identity_updated_at': device.provider_profile_at,
        'inventory': {'availability': catalog['availability'], 'updated_at': device.last_success_at,
                      'model_count': len(catalog['models'])},
        'models': [{'name': model['name'], 'brand': model['brand']} for model in catalog['models']],
        'fulfillment_connected': False,
    })

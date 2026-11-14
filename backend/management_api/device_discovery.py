"""Import merchant devices without publishing new devices or copying secrets."""
import math
import uuid
from datetime import timedelta
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from .device_provider import DeviceProvider, ProviderError
from .inventory_sync import identifier
from .models import Device, DeviceProviderConnection
from .device_location import coordinate_pair, coordinate_type


def device_profile(row):
    # Vendor responses also contain passwords, MACs, IPs, contacts and revenue.
    # Store only the fields needed for the public equipment information screen.
    result = {}
    for name in ('device_num', 'device_name'):
        value = row.get(name)
        if value is not None and (not isinstance(value, str) or len(value) > 120):
            raise ProviderError('设备名称或编号格式不正确，本次未更新设备。')
        result[name] = value.strip() if value else ''
    if not result['device_name']:
        result['name_warning'] = '供应商名称为空，保留上次名称或使用设备编号。'
    address = row.get('address')
    if isinstance(address, str) and address.strip() and len(address) <= 200:
        result['address'] = address.strip()
    else:
        result['address_warning'] = '供应商地址为空或格式异常，保留上次有效地址，请核实。'
    try:
        result['coordinates'] = coordinate_pair(row.get('latitude'), row.get('longitude'))
        raw_type = row.get('coordinate_type')
        kind = coordinate_type(raw_type)
        if raw_type not in (None, '') and not kind:
            result['coordinate_error'] = '供应商坐标类型无法识别，请核实。'
        result['coordinates']['coordinate_type'] = kind
        result['coordinates']['source_coordinate_type'] = raw_type if isinstance(raw_type, str) and len(raw_type) <= 32 else ''
    except ValueError:
        result['coordinate_error'] = '供应商坐标缺失或无效，暂停导航，请核实。'
    return result


def discover_devices(connection):
    """One merchant fetch per run, with a lease shared by manual and scheduled sync."""
    if not connection.active:
        raise ProviderError('连接已停用，请先启用连接。')
    now, token = timezone.now(), uuid.uuid4()
    acquired = DeviceProviderConnection.objects.filter(pk=connection.pk, active=True, revision=connection.revision).filter(
        Q(profile_sync_token__isnull=True) | Q(profile_sync_started_at__lt=now-timedelta(minutes=10))
    ).update(profile_sync_token=token, profile_sync_started_at=now, profile_sync_status='running',
             profile_sync_message='正在读取商家设备资料。')
    if not acquired:
        raise ProviderError('设备资料正在同步或连接已变更，请稍后刷新。')
    try:
        result = _discover_devices(connection, token)
    except Exception as exc:
        message = str(exc) if isinstance(exc, ProviderError) else '设备资料同步失败，保留上次有效资料。'
        DeviceProviderConnection.objects.filter(pk=connection.pk, profile_sync_token=token).update(
            profile_sync_token=None, profile_sync_status='failed', profile_sync_message=message[:300])
        raise ProviderError(message) from None
    return result


def _discover_devices(connection, token):
    provider, rows, seen, expected = DeviceProvider(connection), [], set(), None
    for page in range(1, 101):
        data = provider.devices(page=page, limit=100)
        if not isinstance(data, dict) or not isinstance(data.get('list'), list):
            raise ProviderError('设备列表格式不正确，本次未更新设备。')
        total, pages = data.get('totalNum'), data.get('totalPages')
        if (type(total) is not int or type(pages) is not int or type(data.get('page')) is not int
                or data['page'] != page or not 0 <= total <= 10000
                or pages not in ({0, 1} if total == 0 else {math.ceil(total / 100)})):
            raise ProviderError('设备分页信息不正确，本次未更新设备。')
        if expected is not None and expected != (total, pages):
            raise ProviderError('设备列表在分页期间发生变化，请重新同步。')
        expected = total, pages
        batch = data['list']
        if len(batch) > 100 or (page < pages and len(batch) != 100):
            raise ProviderError('设备列表分页不完整，请重新同步。')
        for row in batch:
            if not isinstance(row, dict) or identifier(row.get('shop_id')) != connection.shop_id:
                raise ProviderError('设备列表商家不匹配，本次未更新设备。')
            device_id = identifier(row.get('id'))
            if device_id in seen:
                raise ProviderError('设备列表包含重复编号，本次未更新设备。')
            seen.add(device_id)
            if row.get('is_deleted', 0) not in (0, 1):
                raise ProviderError('设备删除状态未知，本次未更新设备。')
            if row.get('is_deleted', 0) == 0:
                rows.append((device_id, device_profile(row)))
        if page >= pages:
            break
    if len(seen) != expected[0]:
        raise ProviderError('设备列表数量不完整，请重新同步。')
    created, updated = 0, 0
    with transaction.atomic():
        current = DeviceProviderConnection.objects.select_for_update().get(pk=connection.pk)
        if not current.active or current.revision != connection.revision or current.profile_sync_token != token:
            raise ProviderError('读取期间连接已变更，请重新同步。')
        observed = timezone.now()
        for device_id, profile in rows:
            if 'coordinates' in profile:
                profile['coordinates']['observed_at'] = observed.isoformat()
            device, new = Device.objects.select_for_update().get_or_create(
                connection=current, vendor_device_id=device_id,
                defaults={'name': profile['device_name'] or profile['device_num'] or f'打印设备 {device_id}',
                          'name_source': 'supplier', 'location_source': 'supplier', 'active': False})
            old = device.provider_profile
            for field in ('device_name', 'device_num', 'address', 'coordinates'):
                if not profile.get(field) and old.get(field):
                    profile[field] = old[field]
            if not profile.get('device_name'):
                profile['name_warning'] = '供应商名称为空，使用设备编号。'
            device.provider_profile, device.provider_profile_at = profile, observed
            device.save(update_fields=['provider_profile', 'provider_profile_at', 'updated_at'])
            created += new
            updated += not new
        message = f'新增 {created} 台设备，更新 {updated} 台设备信息。新设备默认停用，人工配置保留。'
        current.profile_sync_at, current.profile_sync_status = observed, 'success'
        current.profile_sync_message, current.profile_sync_token = message, None
        current.save(update_fields=['profile_sync_at', 'profile_sync_status', 'profile_sync_message', 'profile_sync_token'])
    return {'created': created, 'updated': updated, 'message': message}

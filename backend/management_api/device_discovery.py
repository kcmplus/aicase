"""Import merchant devices without publishing new devices or copying secrets."""
import math
from django.db import transaction
from django.utils import timezone
from .device_provider import DeviceProvider, ProviderError
from .inventory_sync import identifier
from .models import Device, DeviceProviderConnection


def device_profile(row):
    # Vendor responses also contain passwords, MACs, IPs, contacts and revenue.
    # Store only the fields needed for the public equipment information screen.
    result = {}
    for name in ('device_num', 'device_name'):
        value = row.get(name)
        if value is not None and (not isinstance(value, str) or len(value) > 120):
            raise ProviderError('设备名称或编号格式不正确，本次未更新设备。')
        result[name] = value or ''
    return result


def discover_devices(connection):
    if not connection.active:
        raise ProviderError('连接已停用，请先启用连接。')
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
        if not current.active or current.revision != connection.revision:
            raise ProviderError('读取期间连接已变更，请重新同步。')
        observed = timezone.now()
        for device_id, profile in rows:
            device, new = Device.objects.select_for_update().get_or_create(
                connection=current, vendor_device_id=device_id,
                defaults={'name': profile['device_name'] or profile['device_num'] or f'打印设备 {device_id}', 'active': False})
            device.provider_profile, device.provider_profile_at = profile, observed
            device.save(update_fields=['provider_profile', 'provider_profile_at', 'updated_at'])
            created += new
            updated += not new
    return {'created': created, 'updated': updated,
            'message': f'新增 {created} 台设备，更新 {updated} 台设备信息。新设备默认停用，已有配置保留。'}

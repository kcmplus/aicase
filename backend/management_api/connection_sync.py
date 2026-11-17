"""The same complete read-only supplier refresh for the admin and scheduler."""
from django.conf import settings
from django.db import DatabaseError
from .device_discovery import discover_devices
from .device_provider import ProviderError
from .inventory_sync import sync_device
from .models import Device


def sync_connection(connection, actor_name='管理命令', *, device_id=None):
    if getattr(settings, 'DIRECT_DEBUG_ENABLED', False):
        raise ProviderError('直连模拟模式不查询供应商设备资料或库存。')
    if not connection.active:
        raise ProviderError('连接已停用，请先启用连接。')
    try:
        profile = {**discover_devices(connection), 'status': 'success'}
    except ProviderError as exc:
        profile = {'status': 'failed', 'message': str(exc), 'created': 0, 'updated': 0}
    # A failed merchant profile fetch must not prevent an independent stock read.
    devices = Device.objects.filter(connection=connection, active=True, connection__active=True)
    if device_id is not None:
        devices = devices.filter(pk=device_id)
    results = []
    for pk, vendor_id in devices.order_by('pk').values_list('pk', 'vendor_device_id'):
        try:
            run = sync_device(pk, actor_name)
            result = {'status': run.status, 'message': run.message}
        except ProviderError as exc:
            result = {'status': 'failed', 'message': str(exc)}
        except Device.DoesNotExist:
            result = {'status': 'failed', 'message': '设备已移除，跳过同步。'}
        except DatabaseError:
            raise
        except Exception:
            result = {'status': 'failed', 'message': '机型或模板同步未完成，请查看同步记录后重试。'}
        results.append({'device_id': pk, 'vendor_device_id': vendor_id, **result})
    stages = [profile, *results]
    successes = sum(stage['status'] == 'success' for stage in stages)
    status = 'success' if successes == len(stages) else ('partial' if successes else 'failed')
    message = profile['message'] + ''.join(f' 设备 {row["vendor_device_id"]}：{row["message"]}' for row in results)
    if not results:
        message += ' 没有已启用设备，尚未同步库存与机型。'
    return {'status': status, 'message': message, 'created': profile['created'],
            'updated': profile['updated'], 'profile': profile, 'devices': results}

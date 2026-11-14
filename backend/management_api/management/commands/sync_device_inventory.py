from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections, DatabaseError
import time
from django.conf import settings
from management_api.models import DeviceProviderConnection
from management_api.connection_sync import sync_connection
from management_api.device_provider import ProviderError


class Command(BaseCommand):
    help = '同步商家设备资料、库存、机型与模板；不下单、不打印、不扣库存。'

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument('--device', type=int, help='我方后台设备记录 ID（不是供应商设备编号）')
        group.add_argument('--all', action='store_true', help='同步所有启用设备')
        parser.add_argument('--watch', action='store_true', help='持续同步，失败后下轮重试')
        parser.add_argument('--allow-empty', action='store_true', help='定时任务在尚未登记启用设备时正常退出')
        parser.add_argument('--interval', type=int, default=300, help='持续同步间隔秒数，30–600，默认 300')

    def handle(self, *args, **options):
        if not 30 <= options['interval'] <= 600:
            raise CommandError('同步间隔必须为 30–600 秒。')
        if not options['watch']:
            return self.sync_once(options)
        self.stdout.write(f"库存自动同步已启动，每 {options['interval']} 秒检查一次。")
        try:
            while True:
                close_old_connections()
                try:
                    self.sync_once(options)
                except CommandError as exc:
                    self.stderr.write(str(exc))
                except DatabaseError:
                    self.stderr.write('数据库暂不可用，将在下一轮重试库存同步。')
                time.sleep(options['interval'])
        except KeyboardInterrupt:
            self.stdout.write('库存自动同步已停止。')

    def sync_once(self, options):
        failed = False
        # Skip all supplier I/O in the isolated local simulator.
        if settings.DIRECT_DEBUG_ENABLED:
            self.stdout.write('直连模拟模式不查询供应商设备资料或库存。')
            return
        connections = DeviceProviderConnection.objects.filter(active=True)
        if options['device'] is not None:
            connections = connections.filter(device__pk=options['device'], device__active=True)
        device_count = 0
        for connection in connections:
            try:
                result = sync_connection(connection, device_id=options['device'])
                device_count += len(result['devices'])
                failed |= result['status'] != 'success'
                self.stdout.write(f'连接 {connection.pk}: {result["message"]}')
            except ProviderError as exc:
                failed = True
                self.stderr.write(f'连接 {connection.pk}: {exc}')
        if failed:
            raise CommandError('部分设备资料、库存或机型同步未成功，请查看详情；人工配置已保留。')
        if not device_count and not options['watch'] and not (options['allow_empty'] and options['all']):
            raise CommandError('没有匹配的启用设备。')

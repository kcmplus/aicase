from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections, DatabaseError
import time
from management_api.models import Device
from management_api.inventory_sync import sync_device
from management_api.device_provider import ProviderError


class Command(BaseCommand):
    help = '只读同步已登记设备库存；不下单、不打印、不扣库存。'

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument('--device', type=int, help='我方后台设备记录 ID（不是供应商设备编号）')
        group.add_argument('--all', action='store_true', help='同步所有启用设备')
        parser.add_argument('--watch', action='store_true', help='持续同步，失败后下轮重试')
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
        devices = Device.objects.filter(active=True, connection__active=True)
        if options['device'] is not None:
            devices = devices.filter(pk=options['device'])
        ids = list(devices.values_list('id', flat=True))
        if not ids:
            if options['watch']:
                return
            raise CommandError('没有匹配的启用设备。')
        failed = False
        for pk in ids:
            try:
                run = sync_device(pk)
                failed |= run.status != 'success'
                self.stdout.write(f'设备 {pk}: {run.message}')
            except ProviderError as exc:
                failed = True
                self.stderr.write(f'设备 {pk}: {exc}')
            except Device.DoesNotExist:
                failed = True
                self.stderr.write(f'设备 {pk} 已移除，跳过同步。')
        if failed:
            raise CommandError('部分设备同步未成功，原库存快照已保留。')

"""Keep the old command name so stale deployment scripts fail without creating a key."""
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = '已停用：只读终端不再使用我方 API 凭证。'

    def add_arguments(self, parser):
        parser.add_argument('device', type=int)

    def handle(self, *args, **options):
        raise CommandError('终端凭证功能已停用。终端仅读取本机 Tauri 数据，不访问我方 API。')

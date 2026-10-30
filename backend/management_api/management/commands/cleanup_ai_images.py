from django.core.management.base import BaseCommand
from django.utils import timezone

from management_api.ai_images import TERMINAL_STATUSES, cleanup_expired_images
from management_api.models import AIRender


class Command(BaseCommand):
    help = 'Clear expired uploaded and generated image bytes, preserving tasks, usage and costs (up to 10,000 tasks per run).'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Count due images without changing data.')

    def handle(self, *args, **options):
        now = timezone.now()
        if options['dry_run']:
            count = AIRender.objects.filter(status__in=TERMINAL_STATUSES, image_expires_at__lte=now, image_deleted_at__isnull=True).count()
            self.stdout.write(f'{count} image pairs due for cleanup (dry run).')
        else:
            count = cleanup_expired_images(now=now)
            self.stdout.write(f'Cleared images for {count} expired tasks; call records and costs retained.')

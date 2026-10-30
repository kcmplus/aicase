from django.core.management.base import BaseCommand
from django.utils import timezone

from management_api.ai_images import cleanup_expired_images
from management_api.models import AIRender


class Command(BaseCommand):
    help = 'Clear expired generated image bytes, preserving tasks, usage and costs (up to 10,000 per run).'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Count due images without changing data.')

    def handle(self, *args, **options):
        now = timezone.now()
        if options['dry_run']:
            count = AIRender.objects.filter(status='ready', image_expires_at__lte=now, image_deleted_at__isnull=True).count()
            self.stdout.write(f'{count} generated images due for cleanup (dry run).')
        else:
            count = cleanup_expired_images(now=now)
            self.stdout.write(f'Cleared {count} expired generated images; call records and costs retained.')

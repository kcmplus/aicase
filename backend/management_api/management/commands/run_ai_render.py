from django.core.management.base import BaseCommand
from management_api.ai_generation import run_render


class Command(BaseCommand):
    help = 'Run one durable AI image-edit job; already claimed jobs are never resubmitted.'

    def add_arguments(self, parser):
        parser.add_argument('job_id')

    def handle(self, *args, **options):
        run_render(options['job_id'])

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from management_api.models import Brand, PhoneModel
from management_api.phone_templates import ASSET_ROOT, PHONE_TEMPLATES


class Command(BaseCommand):
    help = 'Register supplied case templates without overwriting managed models or declaring print calibration.'

    def add_arguments(self, parser):
        parser.add_argument('--only-supplied', action='store_true',
                            help='Disable other phone models while preserving historical records.')

    @transaction.atomic
    def handle(self, *args, **options):
        for template in PHONE_TEMPLATES:
            for field in ('overlay', 'mask', 'previewOverlay'):
                if not (ASSET_ROOT / template[field].lstrip('/')).is_file():
                    raise CommandError(f"Missing {field}: {template['id']}")
        brand, _ = Brand.objects.get_or_create(code='apple', defaults={'name': 'Apple'})
        created_count = 0
        for template in PHONE_TEMPLATES:
            _, created = PhoneModel.objects.get_or_create(code=template['code'], defaults={
                'name': template['model'], 'brand': brand, 'preview_family': 'iphone',
                'sort_order': 20 + created_count, 'print_ready': False,
                'notes': f"已接入供应商底图 {template['id']}。本地预览及样片导出 "
                         f"{template['printWidth']}×{template['printHeight']} px / 300 DPI。"
                         "打印遮罩由底图透明区域提取，尚待供应商确认出血和打样校准；设备接口未接入。",
                'adaptation_prompt': 'Keep the main subject away from the upper-left camera cutout. '
                                     'Keep faces and important text inside the central printable area. '
                                     'Fill the portrait canvas with artwork; do not draw a phone, camera, case frame or mockup. '
                                     'The application applies the exact case template after generation.',
            })
            created_count += created
        self.stdout.write(self.style.SUCCESS(f'Registered {created_count} new phone templates; existing records preserved.'))
        if options['only_supplied']:
            count = PhoneModel.objects.exclude(code__in=[t['code'] for t in PHONE_TEMPLATES]).filter(active=True).update(active=False)
            self.stdout.write(self.style.SUCCESS(f'Disabled {count} other phone models; historical records preserved.'))

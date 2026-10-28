import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from management_api.models import AIExample, AIExampleResult, AIStyle, AuditLog, PhoneModel


class Command(BaseCommand):
    help = "Add eight image-tested English styles distilled from the supplied phone-case reference boards."

    @transaction.atomic
    def handle(self, *args, **options):
        data = json.loads((Path(__file__).resolve().parents[2] / "seed/ai-style-pack.json").read_text())
        storefront = settings.BASE_DIR.parent / "frontend/storefront"
        # Do not publish incomplete cases if assets were omitted from a checkout.
        for case in data["cases"]:
            for field in ("original_path", "image_path"):
                if not (storefront / case[field].lstrip("/")).is_file():
                    raise CommandError(f"Missing case image: {case[field]}")
        model = PhoneModel.objects.filter(code="model-3", name="iPhone 15 Pro").first()
        if not model:
            raise CommandError("Seed the iPhone 15 Pro catalog model before importing composition studies.")

        style_count = case_count = 0
        for item in data["styles"]:
            values = dict(item)
            code = values.pop("code")
            _, created = AIStyle.objects.get_or_create(code=code, defaults=values)
            style_count += created
        for item in data["cases"]:
            example, created = AIExample.objects.get_or_create(
                code=item["code"],
                defaults={key: item[key] for key in ("name", "name_zh", "subject", "subject_zh", "sort_order", "original_path")},
            )
            if not created:
                continue
            AIExampleResult.objects.create(
                example=example,
                style=AIStyle.objects.get(code=item["style"]),
                phone_model=model,
                image_path=item["image_path"],
                prompt=item["prompt"],
            )
            AuditLog.objects.create(
                actor_name="system:seed_ai_style_pack",
                action="create",
                resource="management_api.aiexample",
                object_id=str(example.pk),
                summary="新增参考图提炼案例及英文提示词：" + example.name,
            )
            case_count += 1
        self.stdout.write(self.style.SUCCESS(
            f"AI style pack: {style_count} new styles; {case_count} new cases. Existing edits, results and visibility preserved."
        ))

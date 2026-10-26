import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from management_api.models import AIExample, AIExampleResult, AIStyle, AuditLog, PhoneModel


class Command(BaseCommand):
    help = "Add three documented AI recipes and backfill unchanged legacy sample prompts once."

    @transaction.atomic
    def handle(self, *args, **options):
        data = json.loads((Path(__file__).resolve().parents[2] / "seed/ai-recipes.json").read_text())
        created = filled = 0
        for item in data["styles"]:
            values = dict(item)
            code = values.pop("code")
            AIStyle.objects.get_or_create(code=code, defaults=values)
        for item in data["cases"]:
            model = PhoneModel.objects.filter(code=item["phone_model_code"], name="iPhone 15 Pro").first()
            if not model:
                raise CommandError("The iPhone 15 Pro model must exist before importing these composition studies.")
            example, added = AIExample.objects.get_or_create(code=item["code"], defaults={key:item[key] for key in ("name", "subject", "sort_order", "original_path")})
            if added:
                AIExampleResult.objects.create(example=example, style=AIStyle.objects.get(code=item["style"]), phone_model=model, image_path=item["image_path"], prompt=item["prompt"])
                AuditLog.objects.create(actor_name="system:seed_ai_recipes", action="create", resource="management_api.aiexample", object_id=str(example.pk), summary="新增示例图片及对应提示词：" + example.name)
                created += 1
        for item in data["legacy_prompts"]:
            marker = item["code"] + ":" + item["style"]
            example = AIExample.objects.select_for_update().filter(code=item["code"]).first()
            if not example or AuditLog.objects.filter(resource="seed.ai-recipes.v1", object_id=marker).exists():
                continue
            result = example.results.filter(style__code=item["style"]).first()
            matches = result and example.original_path == item["original_path"] and result.image_path == item["image_path"] and not result.prompt and not result.phone_model_id
            if matches:
                result.prompt = item["prompt"]
                result.save(update_fields=["prompt"])
                example.revision += 1
                example.save(update_fields=["revision", "updated_at"])
                filled += 1
            AuditLog.objects.create(actor_name="system:seed_ai_recipes", action="update", resource="seed.ai-recipes.v1", object_id=marker, summary="补全原有样片提示词" if matches else "保留已管理的案例内容，跳过样片提示词补全")
        self.stdout.write(self.style.SUCCESS(f"AI recipes: {created} new cases; {filled} legacy prompts filled. Existing edits and permissions preserved."))

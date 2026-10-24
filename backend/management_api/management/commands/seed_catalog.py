import json
from pathlib import Path
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand
from django.db import transaction
from management_api.models import Brand, PhoneModel, Graphic, DesignTemplate, AIStyle, AIExample, AIExampleResult, PricingPlan

class Command(BaseCommand):
    help = "Seed current storefront catalog and initial roles without overwriting managed data."
    @transaction.atomic
    def handle(self, *args, **options):
        data = json.loads((Path(__file__).resolve().parents[2] / "seed/catalog.json").read_text())
        brands = {name: Brand.objects.get_or_create(code=name.lower(), defaults={"name": name, "sort_order": i})[0] for i, name in enumerate(["Apple", "Samsung"])}
        for item in data["models"]:
            PhoneModel.objects.get_or_create(code="model-" + str(item["legacy_index"]), defaults={"name": item["name"], "brand": brands[item["brand"]], "preview_family": "iphone" if item["brand"] == "Apple" else "samsung", "legacy_index": item["legacy_index"], "sort_order": item["legacy_index"], "notes": "示意预览机型，尚未完成实际打印校准。"})
        for item in data["designs"]:
            DesignTemplate.objects.get_or_create(code=item["id"], defaults={"name": item["name"], "description": item["category"], "background": item["color"], "layout": item["layout"], "legacy_index": item["legacy_index"], "sort_order": item["legacy_index"]})
        for i, item in enumerate(data["graphics"]):
            Graphic.objects.get_or_create(code=item["id"], defaults={"name": item["zh"], "image_path": item["src"].removeprefix("."), "license": item["license"], "sort_order": i})
        for item in data["aiStyles"]:
            AIStyle.objects.get_or_create(code=item["id"], defaults={"name": item["name"], "description": item["description"], "image_path": item["image"].removeprefix(".")})
        for i, (code, name, subject) in enumerate([
            ("portrait", "Portrait", "Seaside portrait"), ("pets", "Pets", "A little best friend"),
            ("couples", "Couples", "Better together"), ("travel", "Travel", "Somewhere worth keeping"),
        ]):
            prefix = "" if code == "portrait" else code + "-"
            example, created = AIExample.objects.get_or_create(code=code, defaults={"name": name, "subject": subject, "original_path": f"/assets/ai-styles/{prefix}original.png", "sort_order": i})
            if created:
                for style in AIStyle.objects.filter(code__in=["anime", "realism", "3d"]):
                    AIExampleResult.objects.create(example=example, style=style, image_path=f"/assets/ai-styles/{prefix}{style.code}.png")
        PricingPlan.objects.get_or_create(code="standard-print", defaults={"name": "常规打印", "kind": "print", "price": "10.00"})
        PricingPlan.objects.get_or_create(code="ai-monthly", defaults={"name": "AI Studio 月度订阅", "kind": "ai_monthly", "price": "9.90", "monthly_credits": 20, "trial_credits": 1})
        all_business = Permission.objects.filter(content_type__app_label="management_api")
        catalog_models = ["brand", "phonemodel", "graphic", "designtemplate", "aistyle", "aiexample", "pricingplan"]
        roles = {
            "运营管理员": all_business.filter(content_type__model__in=catalog_models),
            "客服人员": all_business.filter(codename__in=["view_printorder", "change_printorder", "view_phonemodel", "view_designtemplate", "view_pricingplan"]),
            "只读人员": all_business.filter(codename__startswith="view_"),
        }
        for name, permissions in roles.items():
            group, created = Group.objects.get_or_create(name=name)
            if created:
                group.permissions.set(permissions)
        self.stdout.write(self.style.SUCCESS("Catalog seeded; existing records and role grants were preserved. No orders or accounts fabricated."))

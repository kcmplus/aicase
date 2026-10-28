import json
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from rest_framework.test import APIClient

from .models import AIExample, AIExampleResult, AIStyle, PhoneModel


class AIStylePackTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", stdout=StringIO())
        call_command("seed_ai_recipes", stdout=StringIO())

    def test_import_keeps_four_originals_and_does_not_publish_prompts(self):
        call_command("seed_ai_style_pack", stdout=StringIO())
        self.assertEqual(AIStyle.objects.count(), 14)
        self.assertEqual(AIExample.objects.count(), 15)
        self.assertEqual(AIExampleResult.objects.count(), 23)
        public = APIClient().get("/api/v1/catalog/").json()
        self.assertEqual(len({row["original_path"] for row in public["ai_examples"]}), 4)
        for row in public["ai_examples"]:
            self.assertNotIn("prompt", row)
            for result in row["results"]:
                self.assertEqual(set(result), {"style_code", "image_path"})
        pack = json.loads((Path(__file__).parent / "seed/ai-style-pack.json").read_text())
        for item in pack["cases"]:
            result = AIExample.objects.get(code=item["code"]).results.get()
            self.assertEqual(result.prompt, item["prompt"])
            self.assertEqual(result.image_path, item["image_path"])
            self.assertNotIn(item["prompt"], str(public))
        self.assertFalse(PhoneModel.objects.get(code="model-3").print_ready)

    def test_repeat_import_preserves_customization_cleared_prompts_and_deleted_results(self):
        call_command("seed_ai_style_pack", stdout=StringIO())
        style = AIStyle.objects.get(code="star-collage")
        style.name = "Managed style"
        style.prompt = "Custom prompt"
        style.save()
        case = AIExample.objects.get(code="portrait-star-collage")
        case.name = "Managed case"
        case.active = False
        case.revision = 4
        case.save()
        case.results.all().delete()
        cleared = AIExampleResult.objects.get(example__code="pets-oil-pastel-pet")
        cleared.prompt = ""
        cleared.save()
        call_command("seed_ai_style_pack", stdout=StringIO())
        style.refresh_from_db()
        case.refresh_from_db()
        cleared.refresh_from_db()
        self.assertEqual((style.name, style.prompt), ("Managed style", "Custom prompt"))
        self.assertEqual((case.name, case.active, case.revision), ("Managed case", False, 4))
        self.assertFalse(case.results.exists())
        self.assertEqual(cleared.prompt, "")
        self.assertEqual(AIExample.objects.count(), 15)
        self.assertEqual(AIExampleResult.objects.count(), 22)

    def test_missing_images_prevent_partial_import(self):
        with patch("management_api.management.commands.seed_ai_style_pack.Path.is_file", return_value=False):
            with self.assertRaisesMessage(CommandError, "Missing case image"):
                call_command("seed_ai_style_pack", stdout=StringIO())
        self.assertEqual(AIStyle.objects.count(), 6)
        self.assertEqual(AIExample.objects.count(), 7)

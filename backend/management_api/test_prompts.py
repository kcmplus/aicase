from io import StringIO

from django.contrib.auth.models import Group, Permission, User
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from .models import AIStyle, AuditLog, PhoneModel


class PromptSettingsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_catalog", stdout=StringIO())
        cls.editor = User.objects.create_user("prompt-editor", is_staff=True)
        cls.editor.groups.add(Group.objects.get(name="运营管理员"))
        cls.reader = User.objects.create_user("prompt-reader", is_staff=True)
        cls.reader.groups.add(Group.objects.get(name="只读人员"))

    def setUp(self):
        self.client = APIClient()
        self.style = AIStyle.objects.get(code="anime")
        self.phone = PhoneModel.objects.first()
        self.targets = [
            (self.style, "ai-styles", "prompt"),
            (self.phone, "phone-models", "adaptation_prompt"),
        ]

    def test_prompt_updates_persist_without_changing_catalog_or_calibration(self):
        self.client.force_login(self.editor)
        for obj, resource, field in self.targets:
            before = {key: value for key, value in obj.__dict__.items() if key not in (field, "updated_at", "_state")}
            content = "保留主体外貌。\n\n镜头区域只放背景；不要绘制手机框。"
            path = f"/api/v1/admin/{resource}/{obj.pk}/"
            response = self.client.patch(path, {field: content}, format="json")
            self.assertEqual(response.status_code, 200, response.data)
            self.assertEqual(self.client.get(path).json()[field], content)
            obj.refresh_from_db()
            self.assertEqual(getattr(obj, field), content)
            self.assertEqual(before, {key: obj.__dict__[key] for key in before})
            log = AuditLog.objects.filter(object_id=str(obj.pk), resource=obj._meta.label_lower).latest("id")
            self.assertIn(field, log.summary)
            self.assertNotIn(content, log.summary)

    def test_prompt_read_and_write_permissions_are_separate(self):
        for obj, resource, field in self.targets:
            original_prompt = getattr(obj, field)
            path = f"/api/v1/admin/{resource}/{obj.pk}/"
            self.client.logout()
            self.assertEqual(self.client.get(path).status_code, 403)
            self.assertEqual(self.client.patch(path, {field: "denied"}).status_code, 403)
            self.client.force_login(self.reader)
            self.assertEqual(self.client.get(path).json()[field], original_prompt)
            self.assertEqual(self.client.patch(path, {field: "denied"}).status_code, 403)
            obj.refresh_from_db()
            self.assertEqual(getattr(obj, field), original_prompt)

    def test_model_only_permission_does_not_reveal_style_prompts(self):
        user = User.objects.create_user("model-only", is_staff=True)
        user.user_permissions.add(Permission.objects.get(codename="view_phonemodel"))
        self.client.force_login(user)
        self.assertEqual(self.client.get("/api/v1/admin/phone-models/").status_code, 200)
        self.assertEqual(self.client.get("/api/v1/admin/ai-styles/").status_code, 403)

    def test_public_catalog_does_not_expose_either_prompt(self):
        AIStyle.objects.update(prompt="PRIVATE_STYLE_PROMPT")
        PhoneModel.objects.update(adaptation_prompt="PRIVATE_MODEL_PROMPT")
        result = self.client.get("/api/v1/catalog/")
        self.assertEqual(result.status_code, 200)
        self.assertNotIn("PRIVATE_STYLE_PROMPT", result.content.decode())
        self.assertNotIn("PRIVATE_MODEL_PROMPT", result.content.decode())
        self.assertNotIn("adaptation_prompt", result.json()["phone_models"][0])
        self.assertNotIn("prompt", result.json()["ai_styles"][0])

    def test_length_validation_and_explicit_clear(self):
        self.client.force_login(self.editor)
        for obj, resource, field in self.targets:
            path = f"/api/v1/admin/{resource}/{obj.pk}/"
            self.assertEqual(self.client.patch(path, {field: "字" * 4000}, format="json").status_code, 200)
            invalid = self.client.patch(path, {field: "字" * 4001}, format="json")
            self.assertEqual(invalid.status_code, 400)
            self.assertIn(field, invalid.json())
            obj.refresh_from_db()
            self.assertEqual(len(getattr(obj, field)), 4000)
            self.assertEqual(self.client.patch(path, {field: ""}, format="json").status_code, 200)
            obj.refresh_from_db()
            self.assertEqual(getattr(obj, field), "")

    def test_seed_preserves_saved_prompts(self):
        self.style.prompt = "saved style"
        self.style.save()
        self.phone.adaptation_prompt = "saved model"
        self.phone.save()
        call_command("seed_catalog", stdout=StringIO())
        self.style.refresh_from_db()
        self.phone.refresh_from_db()
        self.assertEqual(self.style.prompt, "saved style")
        self.assertEqual(self.phone.adaptation_prompt, "saved model")

from importlib import import_module
from io import StringIO
from types import SimpleNamespace

from django.apps import apps
from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from .models import AIExample, AIStyle


class AILanguageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_catalog', stdout=StringIO())
        call_command('seed_ai_recipes', stdout=StringIO())
        cls.admin = User.objects.create_superuser('language-admin', '', 'test-only-password')

    def test_bilingual_catalog_is_editable_but_prompts_remain_private(self):
        client = APIClient()
        client.force_login(self.admin)
        style = AIStyle.objects.get(code='gouache')
        response = client.patch(f'/api/v1/admin/ai-styles/{style.pk}/', {'name': 'Warm paint', 'name_zh': '温暖手绘', 'description_zh': '宠物插画', 'prompt': 'PRIVATE ENGLISH PROMPT'}, format='json')
        self.assertEqual(response.status_code, 200)
        case = AIExample.objects.get(code='pet-gouache')
        response = client.patch(f'/api/v1/admin/ai-examples/{case.pk}/', {'name_zh': '小狗', 'subject_zh': '快乐的小狗', 'revision': case.revision}, format='json')
        self.assertEqual(response.status_code, 200)
        client.logout()
        public = client.get('/api/v1/catalog/').json()
        shown = next(row for row in public['ai_styles'] if row['code'] == 'gouache')
        self.assertEqual(shown['name'], 'Warm paint')
        self.assertEqual(shown['name_zh'], '温暖手绘')
        self.assertNotIn('PRIVATE ENGLISH PROMPT', str(public))
        self.assertNotIn('prompt', shown)
        shown_case = next(row for row in public['ai_examples'] if row['code'] == 'pet-gouache')
        self.assertEqual(shown_case['subject_zh'], '快乐的小狗')
        self.assertNotIn('prompt', shown_case['results'][0])

    def test_stock_translation_is_exact_match_only_and_does_not_overwrite_edits(self):
        migration = import_module('management_api.migrations.0007_ai_catalog_languages')
        stock = migration.STYLE_UPDATES[0]
        style = AIStyle.objects.get(code=stock['code'])
        for field, value in stock['before'].items():
            setattr(style, field, value)
        style.name_zh = style.description_zh = ''
        style.save()
        customized = AIStyle.objects.get(code='watercolor')
        customized.name = '我的定制名称'
        customized.prompt = '保留此自定义提示词'
        customized.name_zh = '独立翻译'
        customized.save()
        migration.english_defaults(apps, SimpleNamespace(connection=SimpleNamespace(alias='default')))
        style.refresh_from_db(); customized.refresh_from_db()
        self.assertEqual(style.name, stock['after']['name'])
        self.assertEqual(style.name_zh, stock['after']['name_zh'])
        self.assertEqual(style.prompt, stock['after']['prompt'])
        self.assertEqual(customized.name, '我的定制名称')
        self.assertEqual(customized.name_zh, '独立翻译')
        self.assertEqual(customized.prompt, '保留此自定义提示词')
        style.prompt = ''
        style.save()
        migration.english_defaults(apps, SimpleNamespace(connection=SimpleNamespace(alias='default')))
        style.refresh_from_db()
        self.assertEqual(style.prompt, '')

    def test_multistep_recipe_translation_preserves_images_and_invalidates_stale_revision(self):
        migration = import_module('management_api.migrations.0007_ai_catalog_languages')
        stock = next(item for item in migration.CASE_UPDATES if item['code'] == 'lake-watercolor')
        case = AIExample.objects.get(code=stock['code'])
        result = case.results.get()
        result.prompt = stock['before']['prompt']; result.save()
        original = case.original_path; image = result.image_path; revision = case.revision
        migration.english_defaults(apps, SimpleNamespace(connection=SimpleNamespace(alias='default')))
        case.refresh_from_db(); result.refresh_from_db()
        self.assertNotRegex(result.prompt, r'[\u3400-\u9fff]')
        self.assertEqual(case.original_path, original)
        self.assertEqual(result.image_path, image)
        self.assertEqual(case.revision, revision + 1)

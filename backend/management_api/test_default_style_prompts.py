import json
from importlib import import_module
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

from django.apps import apps
from django.core.management import call_command
from django.test import TestCase

from .models import AIStyle


class DefaultStylePromptTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_catalog', stdout=StringIO())

    def test_new_catalog_has_english_generation_prompts_for_every_default_style(self):
        catalog = json.loads((Path(__file__).parent / 'seed/catalog.json').read_text())
        for item in catalog['aiStyles']:
            style = AIStyle.objects.get(code=item['id'])
            self.assertTrue(style.prompt.strip())
            self.assertEqual(style.prompt, item['prompt'])
            self.assertNotRegex(style.prompt, r'[\u3400-\u9fff]')
            self.assertIn('uploaded photo', style.prompt)

    def test_seeding_preserves_custom_prompts_and_deliberately_cleared_styles(self):
        AIStyle.objects.filter(code='anime').update(prompt='My custom style', active=False)
        AIStyle.objects.filter(code='realism').update(prompt='')
        call_command('seed_catalog', stdout=StringIO())
        anime = AIStyle.objects.get(code='anime')
        self.assertEqual(anime.prompt, 'My custom style')
        self.assertFalse(anime.active)
        self.assertEqual(AIStyle.objects.get(code='realism').prompt, '')

    def test_upgrade_fills_only_missing_default_prompts_and_preserves_style_status(self):
        AIStyle.objects.filter(code='anime').update(prompt='', active=False)
        AIStyle.objects.filter(code='realism').update(prompt=' \n\t')
        AIStyle.objects.filter(code='3d').update(prompt='My custom 3D recipe')
        AIStyle.objects.create(code='custom', name='Custom style', prompt='')
        migration = import_module('management_api.migrations.0015_default_style_prompts')
        migration.fill_missing_prompts(apps, SimpleNamespace(connection=SimpleNamespace(alias='default')))
        anime = AIStyle.objects.get(code='anime')
        self.assertTrue(anime.prompt.strip())
        self.assertFalse(anime.active)
        self.assertTrue(AIStyle.objects.get(code='realism').prompt.strip())
        self.assertEqual(AIStyle.objects.get(code='3d').prompt, 'My custom 3D recipe')
        self.assertEqual(AIStyle.objects.get(code='custom').prompt, '')

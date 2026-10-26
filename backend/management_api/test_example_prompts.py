from io import StringIO
from django.contrib.auth.models import User, Permission
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient
from .models import AIExample, AIExampleResult, AIStyle, PhoneModel, AuditLog


class ExamplePromptTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_catalog', stdout=StringIO())
        cls.root = User.objects.create_superuser('recipe-root', password='Recipe-test-password-123')
        cls.reader = User.objects.create_user('recipe-reader', password='Recipe-test-password-123', is_staff=True)
        cls.reader.user_permissions.add(Permission.objects.get(codename='view_aiexample'))

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.root)
        self.case = AIExample.objects.get(code='pets')
        self.path = f'/api/v1/admin/ai-examples/{self.case.pk}/'
        self.style = AIStyle.objects.get(code='anime')
        self.model = PhoneModel.objects.get(code='model-3')
        self.result = {'style':self.style.pk, 'image_path':'/assets/ai-styles/pets-anime.png', 'phone_model':self.model.pk, 'prompt':'保留红领巾，主体下移，避开镜头。'}

    def test_save_read_privacy_and_no_implicit_template_changes(self):
        response = self.client.patch(self.path, {'revision':0,'results':[self.result]}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['revision'], 1)
        self.assertEqual(response.data['results'][0]['phone_model_name'], 'iPhone 15 Pro')
        self.assertEqual(response.data['results'][0]['prompt'], self.result['prompt'])
        self.style.prompt='New global template';self.style.save()
        self.model.adaptation_prompt='New model rules';self.model.save()
        self.assertEqual(self.client.get(self.path).data['results'][0]['prompt'], self.result['prompt'])
        public=self.client.get('/api/v1/catalog/').json()
        row=next(row for row in public['ai_examples'] if row['code']=='pets')
        self.assertEqual(set(row['results'][0]), {'style_code','image_path'})
        self.assertNotIn(self.result['prompt'],str(public))
        self.assertNotIn(self.result['prompt'],' '.join(AuditLog.objects.values_list('summary',flat=True)))

    def test_old_client_preserves_recipe_and_explicit_clear_works(self):
        self.client.patch(self.path, {'results':[self.result]}, format='json')
        legacy={'style':self.style.pk,'image_path':self.result['image_path']}
        result=self.client.patch(self.path, {'results':[legacy]}, format='json').data['results'][0]
        self.assertEqual(result['prompt'],self.result['prompt'])
        self.assertEqual(result['phone_model'],self.model.pk)
        cleared=self.client.patch(self.path, {'results':[{**legacy,'prompt':'','phone_model':None}]}, format='json').data['results'][0]
        self.assertEqual(cleared['prompt'],'');self.assertIsNone(cleared['phone_model'])

    def test_invalid_recipe_is_atomic_and_stale_update_conflicts(self):
        for invalid in ({**self.result,'prompt':'x'*8001},{**self.result,'phone_model':99999}):
            response=self.client.patch(self.path, {'subject':'Should not save','results':[invalid]},format='json')
            self.assertEqual(response.status_code,400)
            self.case.refresh_from_db();self.assertNotEqual(self.case.subject,'Should not save')
            self.assertEqual(self.case.results.count(),3)
        self.client.patch(self.path, {'revision':0,'results':[self.result]},format='json')
        self.assertEqual(self.client.patch(self.path, {'revision':0,'results':[{**self.result,'prompt':'stale'}]},format='json').status_code,409)
        self.assertEqual(self.client.get(self.path).data['results'][0]['prompt'],self.result['prompt'])

    def test_case_reader_can_view_recipe_but_cannot_edit_or_read_global_templates(self):
        self.client.patch(self.path, {'results':[self.result]},format='json')
        self.client.force_authenticate(self.reader)
        self.assertEqual(self.client.get(self.path).data['results'][0]['prompt'],self.result['prompt'])
        self.assertEqual(self.client.patch(self.path, {'results':[self.result]},format='json').status_code,403)
        self.assertEqual(self.client.get('/api/v1/admin/ai-styles/').status_code,403)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(self.path).status_code,403)

    def test_import_is_repeatable_and_preserves_managed_data_and_cleared_prompts(self):
        self.case.original_path='/media/uploads/managed.png';self.case.save()
        self.case.results.filter(style=self.style).delete()
        call_command('seed_ai_recipes',stdout=StringIO())
        self.assertEqual(AIExample.objects.count(),7)
        self.assertEqual(AIExampleResult.objects.count(),14)
        self.assertTrue(AIExample.objects.get(code='pet-gouache').results.get().prompt)
        self.case.refresh_from_db()
        self.assertEqual(self.case.results.count(),2)
        self.assertTrue(all(not result.prompt for result in self.case.results.all()))
        portrait=AIExample.objects.get(code='portrait')
        result=portrait.results.first();self.assertTrue(result.prompt)
        result.prompt='';result.save()
        new=AIExample.objects.get(code='pet-gouache');new.results.update(prompt='Managed prompt')
        call_command('seed_ai_recipes',stdout=StringIO())
        result.refresh_from_db();self.assertEqual(result.prompt,'')
        self.assertEqual(new.results.get().prompt,'Managed prompt')
        self.assertEqual(AIExample.objects.count(),7)
        self.assertFalse(PhoneModel.objects.get(code='model-3').print_ready)

    def test_nonlegacy_model_link_is_protected_from_deletion(self):
        model=PhoneModel.objects.create(code='recipe-model',name='Recipe model',brand=self.model.brand)
        self.client.patch(self.path, {'results':[{**self.result,'phone_model':model.pk}]},format='json')
        self.assertEqual(self.client.delete(f'/api/v1/admin/phone-models/{model.pk}/').status_code,409)

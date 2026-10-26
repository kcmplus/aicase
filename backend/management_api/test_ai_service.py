from io import BytesIO
import json
import urllib.error
from unittest.mock import patch, MagicMock

from cryptography.fernet import Fernet
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .ai_service import API_BASE, NoRedirect, check_openai_connection, decrypt_api_key
from .models import AIServiceConfig, AuditLog

FAKE_KEY = "sk-test-nonfunctional-" + "a" * 36
PATH = "/api/v1/admin/ai-service/"
MASTER = Fernet.generate_key().decode()


@override_settings(AI_CONFIG_ENCRYPTION_KEY=MASTER)
class AIServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.root = User.objects.create_superuser("ai-config-root")
        cls.staff = User.objects.create_user("ai-config-staff", is_staff=True)

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.client.force_login(self.root)

    def save_key(self):
        return self.client.patch(PATH, {"revision": 0, "api_key": FAKE_KEY}, format="json")

    def test_superuser_only_including_reads_and_checks(self):
        for user in (None, self.staff):
            self.client.logout()
            if user:
                self.client.force_login(user)
            self.assertEqual(self.client.get(PATH).status_code, 403)
            self.assertEqual(self.client.patch(PATH, {"revision": 0, "api_key": FAKE_KEY}).status_code, 403)
            self.assertEqual(self.client.post(PATH+"check/", {"revision": 0}).status_code, 403)
        self.assertEqual(AIServiceConfig.objects.count(), 0)

    def test_initial_read_is_non_mutating_and_uncached(self):
        result = self.client.get(PATH)
        self.assertEqual(result.status_code, 200)
        self.assertFalse(result.json()["has_api_key"])
        self.assertFalse(result.json()["generation_connected"])
        self.assertTrue(result.json()["encryption_ready"])
        self.assertIn("no-store", result["Cache-Control"])
        self.assertEqual(AIServiceConfig.objects.count(), 0)

    def test_encrypted_persistence_and_no_secret_in_responses_or_audit(self):
        result = self.save_key()
        self.assertEqual(result.status_code, 200, result.data)
        config = AIServiceConfig.objects.get(pk=1)
        self.assertNotIn(FAKE_KEY, config.api_key_ciphertext)
        self.assertEqual(decrypt_api_key(config), FAKE_KEY)
        for result in (result, self.client.get(PATH), self.client.get("/api/v1/catalog/")):
            self.assertNotIn(FAKE_KEY, result.content.decode())
            self.assertNotIn(config.api_key_ciphertext, result.content.decode())
            self.assertNotIn("api_key_ciphertext", result.content.decode())
        self.assertEqual(self.client.get(PATH).json()["masked_api_key"], "••••aaaa")
        self.assertNotIn(FAKE_KEY, str(list(AuditLog.objects.values())))
        self.assertNotIn(MASTER, str(list(AuditLog.objects.values())))

    def test_blank_keeps_key_and_explicit_clear_removes_it(self):
        self.save_key()
        previous = AIServiceConfig.objects.get().api_key_ciphertext
        response = self.client.patch(PATH, {"revision": 1, "api_key": "", "model_name": "gpt-image-1.5"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(AIServiceConfig.objects.get().api_key_ciphertext, previous)
        self.assertEqual(response.json()["revision"], 2)
        response = self.client.patch(PATH, {"revision": 2, "clear_api_key": True}, format="json")
        self.assertFalse(response.json()["has_api_key"])
        config = AIServiceConfig.objects.get()
        self.assertEqual(config.api_key_ciphertext, "")
        self.assertEqual(config.key_last_four, "")
        self.assertEqual(config.last_check_status, "untested")

    def test_invalid_key_model_and_unknown_settings_cannot_be_saved(self):
        for body in (
            {"api_key": "bad"}, {"api_key": "sk-"+"x"*1100},
            {"api_key": FAKE_KEY+"\nInjected: header"},
            {"api_key": FAKE_KEY, "clear_api_key": True},
            {"model_name": FAKE_KEY}, {"base_url": "https://example.com"},
        ):
            result = self.client.patch(PATH, {"revision": 0, **body}, format="json")
            self.assertEqual(result.status_code, 400)
            self.assertNotIn(FAKE_KEY, result.content.decode())
        self.assertFalse(AIServiceConfig.objects.exists())

    def test_concurrent_stale_updates_do_not_replace_key(self):
        self.save_key()
        result = self.client.patch(PATH, {"revision": 0, "api_key": "sk-test-other-"+"b"*36}, format="json")
        self.assertEqual(result.status_code, 409)
        self.assertEqual(decrypt_api_key(AIServiceConfig.objects.get()), FAKE_KEY)

    @override_settings(AI_CONFIG_ENCRYPTION_KEY="")
    def test_missing_master_key_fails_closed(self):
        self.assertFalse(self.client.get(PATH).json()["encryption_ready"])
        result = self.save_key()
        self.assertEqual(result.status_code, 503)
        self.assertNotIn(FAKE_KEY, result.content.decode())
        self.assertFalse(AIServiceConfig.objects.exists())

    def test_csrf_required_for_configuration_changes(self):
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.root)
        self.assertEqual(client.patch(PATH, {"revision": 0, "api_key": FAKE_KEY}).status_code, 403)
        self.assertEqual(client.post(PATH+"check/", {"revision": 0}).status_code, 403)

    @patch("management_api.ai_service.check_openai_connection")
    def test_connection_check_uses_saved_key_and_resets_after_edit(self, check):
        self.assertEqual(self.client.post(PATH+"check/", {"revision": 0}).status_code, 400)
        check.assert_not_called()
        self.save_key()
        check.return_value = (True, "连接检查通过")
        result = self.client.post(PATH+"check/", {"revision": 1})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()["last_check_status"], "ok")
        self.assertEqual(result.json()["revision"], 1)
        check.assert_called_once_with(FAKE_KEY, "gpt-image-2")
        changed = self.client.patch(PATH, {"revision": 1, "model_name": "gpt-image-1.5"}, format="json")
        self.assertEqual(changed.json()["last_check_status"], "untested")
        self.assertIsNone(changed.json()["last_check_at"])

    @patch("management_api.ai_service.check_openai_connection")
    def test_check_cannot_publish_result_for_changed_credentials(self, check):
        self.save_key()
        def changed_during_request(*args):
            AIServiceConfig.objects.filter(pk=1).update(revision=2)
            return True, "stale result"
        check.side_effect = changed_during_request
        result = self.client.post(PATH+"check/", {"revision": 1})
        self.assertEqual(result.status_code, 409)
        self.assertEqual(AIServiceConfig.objects.get().last_check_status, "untested")

    @patch("management_api.ai_service.check_openai_connection")
    def test_tampered_ciphertext_does_not_send_any_key(self, check):
        self.save_key()
        AIServiceConfig.objects.update(api_key_ciphertext="invalid ciphertext")
        result = self.client.post(PATH+"check/", {"revision": 1})
        self.assertEqual(result.status_code, 503)
        check.assert_not_called()
        self.assertNotIn("invalid ciphertext", result.content.decode())

    @patch("management_api.ai_service.urllib.request.build_opener")
    def test_network_check_is_metadata_get_to_fixed_openai_host(self, build):
        reply = MagicMock()
        reply.__enter__.return_value.read.return_value = json.dumps({"id":"gpt-image-2", "object":"model"}).encode()
        build.return_value.open.return_value = reply
        ok, _ = check_openai_connection(FAKE_KEY, "gpt-image-2")
        self.assertTrue(ok)
        args, kwargs = build.return_value.open.call_args
        self.assertEqual(args[0].full_url, API_BASE+"/models/gpt-image-2")
        self.assertEqual(args[0].get_method(), "GET")
        self.assertIsNone(args[0].data)
        self.assertEqual(kwargs["timeout"], 15)
        self.assertIsInstance(build.call_args.args[0], NoRedirect)
        self.assertIsNone(NoRedirect().redirect_request(None,None,302,"",{},"https://example.com"))

    @patch("management_api.ai_service.urllib.request.build_opener")
    def test_upstream_error_bodies_never_echo_credentials(self, build):
        for code in (401,403,404,429,500,302):
            build.return_value.open.side_effect=urllib.error.HTTPError(API_BASE,code,FAKE_KEY,{},BytesIO(FAKE_KEY.encode()))
            ok, message=check_openai_connection(FAKE_KEY,"gpt-image-2")
            self.assertFalse(ok)
            self.assertNotIn(FAKE_KEY,message)
        build.return_value.open.side_effect=TimeoutError(FAKE_KEY)
        ok, message=check_openai_connection(FAKE_KEY,"gpt-image-2")
        self.assertFalse(ok)
        self.assertNotIn(FAKE_KEY,message)

    @patch("management_api.ai_service.check_openai_connection", return_value=(True,"ok"))
    def test_connection_checks_are_throttled(self, check):
        self.save_key()
        for _ in range(6):
            self.assertEqual(self.client.post(PATH+"check/",{"revision":1}).status_code,200)
        self.assertEqual(self.client.post(PATH+"check/",{"revision":1}).status_code,429)
        self.assertEqual(check.call_count,6)

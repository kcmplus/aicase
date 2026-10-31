"""Private service configuration. No generation request is sent by these endpoints."""
import json
import re
import urllib.error
import urllib.request
from types import SimpleNamespace

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters, sensitive_variables
from rest_framework import serializers
from rest_framework.exceptions import APIException
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .audit import audit
from .models import AIServiceConfig

API_BASE = "https://api.openai.com/v1"
IMAGE_MODELS = ("gpt-image-2", "gpt-image-2.5-flare", "gpt-image-2.5-sunburst", "gpt-image-1.5", "gpt-image-1-mini", "chatgpt-image-latest")
PROVIDERS = {
    "openai": {"label": "OpenAI", "base_url": API_BASE,
               "models": IMAGE_MODELS, "model_labels": {},
               "console_url": "https://platform.openai.com/api-keys",
               "docs_url": "https://developers.openai.com/api/reference/resources/images/methods/edit"},
    "ai778": {"label": "七七八 AI", "base_url": "https://api.lk888.ai/v1",
              "models": ("tt-image-2", "tt-image-2-token"),
              "model_labels": {"tt-image-2": "TT Image 2（按次计费）", "tt-image-2-token": "TT Image 2 官转（按 token 计费）"},
              "console_url": "https://ai778.cc/api/console",
              "docs_url": "https://ai778.cc/apidoc#model/tt-image-2"},
}
PROFILE_FIELDS = ("model_name", "api_key_ciphertext", "key_last_four", "key_updated_at")


def provider_profile(config, provider):
    """Keep each credential bound to its service, including for already queued jobs."""
    if provider == config.provider:
        return config
    saved = config.provider_profiles.get(provider, {})
    return SimpleNamespace(provider=provider, model_name=saved.get("model_name", PROVIDERS[provider]["models"][0]),
                           api_key_ciphertext=saved.get("api_key_ciphertext", ""),
                           key_last_four=saved.get("key_last_four", ""), key_updated_at=saved.get("key_updated_at"))


def switch_provider(config, provider):
    profile = provider_profile(config, provider)
    previous = {field: getattr(config, field) for field in PROFILE_FIELDS}
    if previous["key_updated_at"]:
        previous["key_updated_at"] = previous["key_updated_at"].isoformat()
    config.provider_profiles = {**config.provider_profiles, config.provider: previous}
    config.provider_profiles.pop(provider, None)
    for field in PROFILE_FIELDS:
        setattr(config, field, getattr(profile, field))
    config.provider = provider


class SuperuserOnly(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_active and user.is_staff and user.is_superuser)


class CredentialStorageUnavailable(APIException):
    status_code = 503
    default_detail = "密钥存储暂不可用，请联系维护人员检查服务端加密配置。"


def cipher():
    try:
        return Fernet(settings.AI_CONFIG_ENCRYPTION_KEY.encode("ascii"))
    except (ValueError, TypeError, UnicodeError):
        raise CredentialStorageUnavailable() from None


def encryption_ready():
    try:
        cipher()
        return True
    except CredentialStorageUnavailable:
        return False


@sensitive_variables()
def encrypt_api_key(api_key):
    return cipher().encrypt(api_key.encode()).decode()


@sensitive_variables()
def decrypt_api_key(config):
    try:
        return cipher().decrypt(config.api_key_ciphertext.encode()).decode()
    except (InvalidToken, UnicodeError, ValueError):
        raise CredentialStorageUnavailable() from None


def current_config():
    return AIServiceConfig.objects.filter(pk=1).first() or AIServiceConfig(pk=1)


def safe_config(config):
    from .models import AIRender
    latest = AIRender.objects.only('provider','status','model_name','error_code','error_message','created_at','completed_at').first()
    provider = PROVIDERS[config.provider]
    available_providers = []
    for name, info in PROVIDERS.items():
        profile = provider_profile(config, name)
        available_providers.append({"id": name, **info, "model_name": profile.model_name,
                                   "has_api_key": bool(profile.api_key_ciphertext),
                                   "masked_api_key": "••••" + profile.key_last_four if profile.api_key_ciphertext else ""})
    return {
        "provider": config.provider, "provider_label": provider["label"], "base_url": provider["base_url"], "model_name": config.model_name,
        "available_providers": available_providers,
        "available_models": list(provider["models"]), "has_api_key": bool(config.api_key_ciphertext),
        "masked_api_key": "••••" + config.key_last_four if config.api_key_ciphertext else "",
        "key_updated_at": config.key_updated_at, "updated_at": config.updated_at,
        "revision": config.revision, "encryption_ready": encryption_ready(),
        "image_retention_days": config.image_retention_days,
        "last_check_at": config.last_check_at, "last_check_status": config.last_check_status,
        "last_check_message": config.last_check_message,
        "generation_connected": bool(config.api_key_ciphertext) and encryption_ready(),
        "last_generation": {"status": latest.status, "model": latest.model_name, "provider": latest.provider,
                            "provider_label": PROVIDERS[latest.provider]["label"],
                            "error_code": latest.error_code, "error_message": latest.error_message,
                            "created_at": latest.created_at, "completed_at": latest.completed_at} if latest else None,
    }


class UpdateConfigSerializer(serializers.Serializer):
    revision = serializers.IntegerField(min_value=0)
    image_retention_days = serializers.IntegerField(min_value=1, max_value=365, required=False)
    provider = serializers.ChoiceField(choices=tuple(PROVIDERS), required=False, error_messages={"invalid_choice": "请选择支持的生图服务。"})
    model_name = serializers.ChoiceField(choices=tuple(model for info in PROVIDERS.values() for model in info["models"]), required=False, error_messages={"invalid_choice": "请选择支持的图像模型。"})
    api_key = serializers.CharField(required=False, allow_blank=True, max_length=1024, write_only=True)
    clear_api_key = serializers.BooleanField(required=False, default=False)

    def validate_api_key(self, value):
        if not value:
            return value
        if value.lower().startswith("bearer ") or value.lower().startswith("authorization:"):
            raise serializers.ValidationError("请只粘贴 API Key 本身，不要包含 Bearer 或 Authorization 请求头。")
        if value.startswith(("\"", "'", "“", "‘")) or value.endswith(("\"", "'", "”", "’")):
            raise serializers.ValidationError("API Key 两侧包含引号，请只粘贴密钥本身。")
        if re.search(r"\s", value):
            raise serializers.ValidationError("API Key 中间包含空格或换行，请重新复制完整密钥；首尾空白会自动去除。")
        # Credentials are opaque: prefixes and token formats can change.
        # Only reject characters that cannot safely be sent in an HTTP header.
        if any(ord(char) < 33 or ord(char) > 126 for char in value):
            raise serializers.ValidationError("API Key 包含不支持的字符，请检查是否混入不可见字符、中文标点或省略号。")
        return value

    def validate(self, attrs):
        if set(self.initial_data) - set(self.fields):
            raise serializers.ValidationError("包含不支持的配置项。")
        if attrs.get("api_key") and attrs.get("clear_api_key"):
            raise serializers.ValidationError("更换与清除密钥不能同时执行。")
        return attrs


@method_decorator(never_cache, name="dispatch")
@method_decorator(sensitive_post_parameters("api_key"), name="dispatch")
class AIServiceSettingsView(APIView):
    permission_classes = [SuperuserOnly]

    def get(self, request):
        return Response(safe_config(current_config()))

    @sensitive_variables()
    @transaction.atomic
    def patch(self, request):
        serializer = UpdateConfigSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        config, _ = AIServiceConfig.objects.select_for_update().get_or_create(pk=1)
        if config.revision != values["revision"]:
            return Response({"detail": "配置已被其他操作更新，请刷新后重试。"}, status=409)
        provider = values.get("provider", config.provider)
        model = values.get("model_name", provider_profile(config, provider).model_name)
        if model not in PROVIDERS[provider]["models"]:
            raise serializers.ValidationError({"model_name": "请选择此服务商支持的图像模型。"})
        changed = []
        if provider != config.provider:
            switch_provider(config, provider)
            changed.append("服务商")
        if values.get("model_name", config.model_name) != config.model_name:
            config.model_name = values["model_name"]
            changed.append("图像模型")
        if values.get("clear_api_key"):
            if config.api_key_ciphertext:
                config.api_key_ciphertext = config.key_last_four = ""
                config.key_updated_at = timezone.now()
                changed.append("清除 API Key")
        elif values.get("api_key"):
            config.api_key_ciphertext = encrypt_api_key(values["api_key"])
            config.key_last_four = values["api_key"][-4:]
            config.key_updated_at = timezone.now()
            changed.append("更新 API Key")
        connection_changed = bool(changed)
        if 'image_retention_days' in values and values['image_retention_days'] != config.image_retention_days:
            config.image_retention_days = values['image_retention_days']
            changed.append('图片保留天数')
        if changed:
            config.revision += 1
            if connection_changed:
                config.last_check_status = "untested"
                config.last_check_at = None
                config.last_check_message = ""
            config.save()
            audit(request, "update", "management_api.aiserviceconfig", config, "修改生图配置：" + "、".join(changed))
        return Response(safe_config(config))


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


@sensitive_variables()
def check_openai_connection(api_key, model_name):
    """Read model metadata only. Never forward credentials through a redirect."""
    request = urllib.request.Request(
        API_BASE + "/models/" + model_name,
        headers={"Authorization": "Bearer " + api_key, "Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=15) as response:
            data = json.loads(response.read(65537))
        if data.get("id") != model_name or data.get("object") != "model":
            return False, "OpenAI 返回的模型信息不符合预期，请稍后重试。"
        return True, "已连接 OpenAI，可读取所选模型。尚未验证图片生成权限或账户余额。"
    except urllib.error.HTTPError as error:
        code = error.code
        error.close()
        messages = {
            401: "OpenAI 未接受此密钥，请检查密钥是否正确或已失效。",
            403: "OpenAI 拒绝访问。请检查项目权限、Models 读取权限及服务可用地区。",
            404: "无法读取所选模型，请确认该项目有权访问此模型。",
            429: "OpenAI 请求受限，请稍后重试并检查账户限制。",
        }
        return False, messages.get(code, "OpenAI 暂未完成连接检查，请稍后重试。")
    except (urllib.error.URLError, TimeoutError, OSError):
        return False, "服务端连接 OpenAI 超时或网络不可达，请稍后重试。"
    except (ValueError, AttributeError):
        return False, "无法读取 OpenAI 响应，请稍后重试。"


@sensitive_variables()
def check_ai778_connection(api_key, model_name):
    # The relay documents the list endpoint, not individual model retrieval.
    request = urllib.request.Request(PROVIDERS["ai778"]["base_url"] + "/models",
        headers={"Authorization": "Bearer " + api_key, "Accept": "application/json"}, method="GET")
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=15) as response:
            payload = response.read(1024 * 1024 + 1)
        if len(payload) > 1024 * 1024:
            raise ValueError()
        models = json.loads(payload)["data"]
        if not isinstance(models, list):
            raise ValueError()
        # The published relay model names replace older GPT aliases.
        aliases = {"tt-image-2": {"tt-image-2", "gpt-image-2"},
                   "tt-image-2-token": {"tt-image-2-token", "gpt-image-2-guan"}}
        if not any(isinstance(item, dict) and item.get("id") in aliases[model_name] for item in models):
            return False, "已连接七七八 AI，但模型列表未包含所选模型，请检查密钥的模型权限。"
        return True, "已连接七七八 AI，可读取所选模型。尚未验证图片生成权限或账户余额。"
    except urllib.error.HTTPError as error:
        code = error.code
        error.close()
        return False, {401: "七七八 AI 未接受此密钥，请检查密钥是否正确或已失效。",
                       403: "七七八 AI 拒绝访问，请检查密钥权限与控制台的 IP 白名单。",
                       429: "七七八 AI 请求受限，请稍后重试并检查账户限制。"}.get(code, "七七八 AI 暂未完成连接检查，请稍后重试。")
    except (urllib.error.URLError, TimeoutError, OSError):
        return False, "服务端连接七七八 AI 超时或网络不可达，请稍后重试。"
    except (ValueError, KeyError, TypeError):
        return False, "无法读取七七八 AI 的模型列表，请稍后重试。"


@method_decorator(never_cache, name="dispatch")
class AIServiceCheckView(APIView):
    permission_classes = [SuperuserOnly]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "ai_connection"

    @sensitive_variables()
    def post(self, request):
        config = current_config()
        if not isinstance(request.data, dict) or set(request.data) != {"revision"}:
            raise serializers.ValidationError({"detail": "请提交已保存配置的版本号。"})
        revision = serializers.IntegerField(min_value=0).run_validation(request.data.get("revision"))
        if revision != config.revision:
            return Response({"detail": "配置已更新，请刷新后重新检查。"}, status=409)
        if not config.api_key_ciphertext:
            raise serializers.ValidationError({"detail": "请先保存当前服务商的 API Key。"})
        check = check_ai778_connection if config.provider == "ai778" else check_openai_connection
        ok, message = check(decrypt_api_key(config), config.model_name)
        changed = AIServiceConfig.objects.filter(pk=1, revision=revision).update(
            last_check_status="ok" if ok else "error", last_check_message=message, last_check_at=timezone.now(),
        )
        if not changed:
            return Response({"detail": "检查期间配置已更新，请重新检查。"}, status=409)
        audit(request, "update", "management_api.aiserviceconfig", config, "检查 " + PROVIDERS[config.provider]["label"] + " 连接：" + ("通过" if ok else "未通过"))
        return Response(safe_config(current_config()))

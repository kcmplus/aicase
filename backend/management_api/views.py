import uuid
import warnings
from io import BytesIO
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.models import User, Group
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from django.views.decorators.cache import never_cache
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from . import models as m
from . import serializers as s
from .audit import audit
from .permissions import ModelPermissions, AccessAdministration


def identity(user):
    return {"id": user.id, "username": user.username, "name": user.first_name or user.username, "is_superuser": user.is_superuser, "roles": list(user.groups.values_list("name", flat=True)), "permissions": sorted(user.get_all_permissions())}

@ensure_csrf_cookie
@api_view(["GET"])
@permission_classes([AllowAny])
@authentication_classes([])
def csrf(request):
    return Response({"csrfToken": get_token(request)})

@method_decorator(csrf_protect, name="dispatch")
class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"
    def post(self, request):
        username, password = request.data.get("username"), request.data.get("password")
        if not isinstance(username, str) or not isinstance(password, str) or len(username) > 150 or len(password) > 1024:
            return Response({"detail": "账号或密码不正确。"}, status=400)
        user = authenticate(request, username=username, password=password)
        if user is None or not user.is_staff:
            return Response({"detail": "账号或密码不正确，或该账号没有后台访问权限。"}, status=400)
        login(request, user)
        audit(request, "login", "auth.user", user, "管理员登录")
        return Response({"user": identity(user), "csrfToken": get_token(request)})

class SessionView(APIView):
    permission_classes = [IsAdminUser]
    def get(self, request):
        return Response(identity(request.user))
    def delete(self, request):
        audit(request, "logout", "auth.user", request.user, "管理员退出")
        logout(request)
        return Response(status=204)

class PasswordView(APIView):
    permission_classes = [IsAdminUser]
    def post(self, request):
        old, new = request.data.get("old_password"), request.data.get("new_password")
        if not isinstance(old, str) or not request.user.check_password(old):
            raise serializers.ValidationError({"old_password": "当前密码不正确。"})
        if not isinstance(new, str) or len(new) > 1024:
            raise serializers.ValidationError({"new_password": "请输入有效密码。"})
        try:
            validate_password(new, request.user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"new_password": exc.messages})
        request.user.set_password(new)
        request.user.save(update_fields=["password"])
        update_session_auth_hash(request, request.user)
        audit(request, "password", "auth.user", request.user, "修改本人密码")
        return Response({"detail": "密码已更新。"})

class AuditedViewSet(viewsets.ModelViewSet):
    ordering_fields = ["id", "created_at", "updated_at", "name", "sort_order"]
    def get_queryset(self):
        qs = super().get_queryset()
        if hasattr(qs.model, "active") and self.request.query_params.get("active") in ("true", "false"):
            qs = qs.filter(active=self.request.query_params["active"] == "true")
        if qs.model == m.PhoneModel and self.request.query_params.get("brand", "").isdigit():
            qs = qs.filter(brand_id=self.request.query_params["brand"])
        return qs
    @transaction.atomic
    def perform_create(self, serializer):
        obj = serializer.save()
        audit(self.request, "create", obj._meta.label_lower, obj, f"新增 {obj}")
    @transaction.atomic
    def perform_update(self, serializer):
        obj = serializer.save()
        # Record changed field names, never passwords, session tokens or private snapshots.
        fields = ", ".join(k for k in serializer.validated_data if k != "password")
        audit(self.request, "update", obj._meta.label_lower, obj, f"修改字段: {fields}")
    @transaction.atomic
    def perform_destroy(self, instance):
        if getattr(instance, "legacy_index", None):
            raise serializers.ValidationError({"detail": "此记录关联旧版设计码，请改为停用，不能删除。"})
        audit(self.request, "delete", instance._meta.label_lower, instance, f"删除 {instance}")
        instance.delete()

class BrandViewSet(AuditedViewSet):
    queryset = m.Brand.objects.all()
    serializer_class = s.BrandSerializer
    search_fields = ["name", "code"]

class PhoneModelViewSet(AuditedViewSet):
    queryset = m.PhoneModel.objects.select_related("brand")
    serializer_class = s.PhoneModelSerializer
    search_fields = ["name", "code", "brand__name"]

class GraphicViewSet(AuditedViewSet):
    queryset = m.Graphic.objects.all()
    serializer_class = s.GraphicSerializer
    search_fields = ["name", "code", "category"]

class DesignTemplateViewSet(AuditedViewSet):
    queryset = m.DesignTemplate.objects.all()
    serializer_class = s.DesignTemplateSerializer
    search_fields = ["name", "code", "category"]

class AIStyleViewSet(AuditedViewSet):
    queryset = m.AIStyle.objects.all()
    serializer_class = s.AIStyleSerializer
    search_fields = ["name", "code"]

class AIExampleViewSet(AuditedViewSet):
    queryset = m.AIExample.objects.prefetch_related("results__style", "results__phone_model")
    serializer_class = s.AIExampleSerializer
    search_fields = ["name", "code", "subject"]

class PricingPlanViewSet(AuditedViewSet):
    queryset = m.PricingPlan.objects.all()
    serializer_class = s.PricingPlanSerializer
    search_fields = ["name", "code"]

class OrderViewSet(AuditedViewSet):
    queryset = m.PrintOrder.objects.all()
    serializer_class = s.PrintOrderSerializer
    search_fields = ["customer_email", "model_name", "reference"]
    ordering_fields = ["created_at", "amount", "status"]
    http_method_names = ["get", "patch", "head", "options"]
    def get_serializer_class(self):
        return s.PrintOrderDetailSerializer if self.action == "retrieve" else s.PrintOrderSerializer
    def get_queryset(self):
        qs = super().get_queryset()
        if self.action == "list":
            qs = qs.defer("snapshot", "owner_hash", "request_key")
        if self.request.query_params.get("status"):
            qs = qs.filter(status=self.request.query_params["status"])
        return qs
    def update(self, request, *args, **kwargs):
        if set(request.data) - {"notes"}:
            raise serializers.ValidationError({"detail": "只能修改客服备注；付款和打印状态由业务服务更新。"})
        return super().update(request, *args, **kwargs)

class AuditViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = m.AuditLog.objects.all()
    serializer_class = s.AuditLogSerializer
    search_fields = ["actor_name", "action", "resource", "summary"]
    ordering_fields = ["created_at"]

class UserViewSet(AuditedViewSet):
    queryset = User.objects.prefetch_related("groups").order_by("id")
    serializer_class = s.UserSerializer
    permission_classes = [IsAdminUser, ModelPermissions, AccessAdministration]
    search_fields = ["username", "first_name", "email"]
    ordering_fields = ["id", "username", "date_joined"]
    http_method_names = ["get", "post", "patch", "head", "options"]
    def perform_update(self, serializer):
        super().perform_update(serializer)
        if serializer.instance.pk == self.request.user.pk and "password" in serializer.validated_data:
            update_session_auth_hash(self.request, serializer.instance)

class RoleViewSet(AuditedViewSet):
    queryset = Group.objects.prefetch_related("permissions").order_by("id")
    serializer_class = s.RoleSerializer
    permission_classes = [IsAdminUser, ModelPermissions, AccessAdministration]
    search_fields = ["name"]
    ordering_fields = ["id", "name"]
    def perform_destroy(self, instance):
        if instance.user_set.exists():
            raise serializers.ValidationError({"detail": "该角色仍关联管理员，请先调整账号角色。"})
        super().perform_destroy(instance)

class PermissionsView(APIView):
    permission_classes = [IsAdminUser]
    def get(self, request):
        if not (request.user.is_superuser or request.user.has_perm("auth.view_group")):
            return Response(status=403)
        return Response(s.PermissionSerializer(s.manageable_permissions().order_by("content_type__model", "codename"), many=True).data)

class DashboardView(APIView):
    permission_classes = [IsAdminUser]
    def get(self, request):
        models = [("brands", m.Brand), ("phone_models", m.PhoneModel), ("designs", m.DesignTemplate), ("graphics", m.Graphic), ("ai_styles", m.AIStyle), ("ai_examples", m.AIExample), ("plans", m.PricingPlan), ("orders", m.PrintOrder), ("customers", m.Customer)]
        counts = {key: model.objects.count() for key, model in models if request.user.has_perm(f"management_api.view_{model._meta.model_name}")}
        logs = m.AuditLog.objects.all()[:6] if request.user.has_perm("management_api.view_auditlog") else []
        from .stripe_payments import payment_config
        payment = payment_config()
        return Response({"counts": counts, "activity": s.AuditLogSerializer(logs, many=True).data, "storefront_connected": True, "connected_resources": ["plans", "ai_styles", "ai_examples", "orders"], "payments_connected": payment["provider"] == "stripe" and payment["available"], "ai_connected": False})

class UploadView(APIView):
    permission_classes = [IsAdminUser]
    def post(self, request):
        from PIL import Image, UnidentifiedImageError
        from .image_processing import normalized_image
        from .images import save_display_variants
        if not any(request.user.has_perm(f"management_api.{action}_{model}") for action in ("add", "change") for model in ("graphic", "designtemplate", "aistyle", "aiexample")):
            return Response(status=403)
        uploaded = request.FILES.get("file")
        if not uploaded or uploaded.size > 10 * 1024 * 1024:
            raise serializers.ValidationError({"file": "请上传不超过 10 MB 的 JPG / PNG / WebP 图片。"})
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(uploaded) as img:
                    if img.format not in ("JPEG", "PNG", "WEBP") or img.width * img.height > 20_000_000:
                        raise ValueError("Unsupported image")
                    img.load()
                    safe = normalized_image(img)
                    out = BytesIO()
                    safe.save(out, format="PNG")
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
            raise serializers.ValidationError({"file": "无法读取此图片；仅支持有效的 JPG / PNG / WebP，最多 2000 万像素。"})
        path = default_storage.save(f"uploads/{uuid.uuid4().hex}.png", ContentFile(out.getvalue()))
        previews = save_display_variants(path, safe)
        audit(request, "upload", "asset", summary="上传图库图片")
        url = default_storage.url(path)
        return Response({"path": url, "image_variants": {url: previews}}, status=201)

@never_cache
@api_view(["GET"])
@permission_classes([AllowAny])
@authentication_classes([])
def public_catalog(request):
    from .images import image_variants
    from .ai_generation import generation_available
    from .ai_service import current_config
    from .customer_auth import signup_credits
    # Stable legacy indexes are never reassigned. This is an integration API, not a payment API.
    data = {
        "version": 2,
        "signupCredits": signup_credits(),
        "ai_generation_connected": generation_available(),
        "ai_provider": current_config().provider,
        "brands": s.BrandSerializer(m.Brand.objects.filter(active=True), many=True).data,
        "phone_models": s.PublicPhoneModelSerializer(m.PhoneModel.objects.filter(active=True, brand__active=True), many=True).data,
        "designs": s.DesignTemplateSerializer(m.DesignTemplate.objects.filter(active=True), many=True).data,
        "graphics": s.GraphicSerializer(m.Graphic.objects.filter(active=True), many=True).data,
        "ai_styles": list(m.AIStyle.objects.filter(active=True).values("code", "name", "name_zh", "description", "description_zh", "image_path")),
        "ai_examples": [
            {"code": example.code, "name": example.name, "name_zh": example.name_zh, "subject": example.subject, "subject_zh": example.subject_zh, "original_path": example.original_path,
             "results": [{"style_code": result.style.code, "image_path": result.image_path} for result in example.results.all() if result.style.active]}
            for example in m.AIExample.objects.filter(active=True, results__style__active=True).distinct().prefetch_related("results__style")
        ],
        "plans": s.PricingPlanSerializer(m.PricingPlan.objects.filter(active=True), many=True).data,
    }
    paths = [style["image_path"] for style in data["ai_styles"]]
    for example in data["ai_examples"]:
        paths.append(example["original_path"])
        paths.extend(result["image_path"] for result in example["results"])
    data["image_variants"] = image_variants(paths)
    return Response(data)

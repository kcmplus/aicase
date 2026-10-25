import json
import re
from django.contrib.auth.models import User, Group, Permission
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from django.db import transaction
from .models import Brand, PhoneModel, Graphic, DesignTemplate, AIStyle, AIExample, AIExampleResult, PricingPlan, PrintOrder, AuditLog
from .images import image_variants


def validate_image_path(value):
    if value and not re.fullmatch(r"/(?:assets|media)/[a-zA-Z0-9_/-]+\.(?:svg|png|jpg|jpeg|webp)", value):
        raise serializers.ValidationError("请选择本地素材路径，或上传 JPG / PNG / WebP 图片。")
    return value

class CatalogSerializer(serializers.ModelSerializer):
    active = serializers.BooleanField(default=True)
    image_variants = serializers.SerializerMethodField()
    def get_image_variants(self, instance):
        paths = [getattr(instance, field, "") for field in ("image_path", "preview_path", "original_path")]
        if isinstance(instance, AIExample):
            paths.extend(result.image_path for result in instance.results.all())
        return image_variants(paths)
    def validate(self, attrs):
        if self.instance and "code" in attrs and attrs["code"] != self.instance.code:
            raise serializers.ValidationError({"code": "标识创建后不能修改，避免破坏设计引用。"})
        for field in ("image_path", "preview_path", "original_path"):
            if field in attrs:
                validate_image_path(attrs[field])
        return attrs

class BrandSerializer(CatalogSerializer):
    class Meta:
        model = Brand
        fields = "__all__"

class PhoneModelSerializer(CatalogSerializer):
    brand_name = serializers.CharField(source="brand.name", read_only=True)
    class Meta:
        model = PhoneModel
        fields = "__all__"
    def validate(self, attrs):
        attrs = super().validate(attrs)
        if self.instance and self.instance.legacy_index and attrs.get("name", self.instance.name) != self.instance.name:
            raise serializers.ValidationError({"name": "已有二维码绑定的机型名称不能修改；请新建机型。"})
        return attrs

class GraphicSerializer(CatalogSerializer):
    class Meta:
        model = Graphic
        fields = "__all__"

class DesignTemplateSerializer(CatalogSerializer):
    class Meta:
        model = DesignTemplate
        fields = "__all__"
    def validate_layout(self, value):
        if not isinstance(value, dict) or len(json.dumps(value)) > 64000:
            raise serializers.ValidationError("布局须为 JSON 对象，且不超过 64 KB。")
        return value

class AIStyleSerializer(CatalogSerializer):
    class Meta:
        model = AIStyle
        fields = "__all__"

class AIExampleResultSerializer(serializers.ModelSerializer):
    style_code = serializers.CharField(source="style.code", read_only=True)
    style_name = serializers.CharField(source="style.name", read_only=True)
    class Meta:
        model = AIExampleResult
        fields = ["style", "style_code", "style_name", "image_path"]
    def validate_image_path(self, value):
        return validate_image_path(value)

class AIExampleSerializer(CatalogSerializer):
    results = AIExampleResultSerializer(many=True)
    class Meta:
        model = AIExample
        fields = "__all__"
    def validate_results(self, value):
        if not 1 <= len(value) <= 30:
            raise serializers.ValidationError("每个案例请添加 1–30 个风格效果。")
        if len({item["style"].pk for item in value}) != len(value):
            raise serializers.ValidationError("同一个案例不能重复添加相同风格。")
        return value
    @transaction.atomic
    def create(self, validated_data):
        results = validated_data.pop("results")
        example = super().create(validated_data)
        AIExampleResult.objects.bulk_create([AIExampleResult(example=example, **item) for item in results])
        return example
    @transaction.atomic
    def update(self, instance, validated_data):
        results = validated_data.pop("results", None)
        # Serialize simultaneous edits of the same case, including its effect list.
        instance = AIExample.objects.select_for_update().get(pk=instance.pk)
        instance = super().update(instance, validated_data)
        if results is not None:
            instance.results.all().delete()
            AIExampleResult.objects.bulk_create([AIExampleResult(example=instance, **item) for item in results])
        return instance

class PricingPlanSerializer(CatalogSerializer):
    # DRF's inferred single-field uniqueness check ignores this constraint's
    # active=True condition; validate the condition below and keep the DB guard.
    kind = serializers.ChoiceField(choices=PricingPlan._meta.get_field("kind").choices)
    class Meta:
        model = PricingPlan
        fields = "__all__"
    def validate(self, attrs):
        attrs = super().validate(attrs)
        kind = attrs.get("kind", self.instance.kind if self.instance else None)
        if attrs.get("active", self.instance.active if self.instance else True):
            others = PricingPlan.objects.filter(kind=kind, active=True)
            if self.instance:
                others = others.exclude(pk=self.instance.pk)
            if others.exists():
                raise serializers.ValidationError({"active": "此类型已有启用套餐，请先停用原套餐，或直接编辑原套餐。"})
        credits = attrs.get("monthly_credits", self.instance.monthly_credits if self.instance else 0)
        trial = attrs.get("trial_credits", self.instance.trial_credits if self.instance else 0)
        if kind == "ai_monthly" and credits < 1:
            raise serializers.ValidationError({"monthly_credits": "AI 月度套餐至少包含 1 次额度。"})
        if kind == "print" and (credits or trial):
            raise serializers.ValidationError({"monthly_credits": "打印套餐不包含 AI 次数。"})
        return attrs

class PrintOrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = PrintOrder
        fields = ["id", "reference", "customer_email", "model_name", "status", "amount", "currency", "mode", "revision", "station_id", "notes", "created_at", "updated_at"]
        read_only_fields = [f for f in fields if f != "notes"]

class PrintOrderDetailSerializer(PrintOrderSerializer):
    class Meta(PrintOrderSerializer.Meta):
        fields = PrintOrderSerializer.Meta.fields + ["snapshot"]
        read_only_fields = PrintOrderSerializer.Meta.read_only_fields + ["snapshot"]

class AuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = "__all__"
        read_only_fields = [f.name for f in AuditLog._meta.fields]

class PermissionSerializer(serializers.ModelSerializer):
    key = serializers.SerializerMethodField()
    model = serializers.CharField(source="content_type.model")
    class Meta:
        model = Permission
        fields = ["id", "name", "codename", "key", "model"]
    def get_key(self, obj):
        return f"{obj.content_type.app_label}.{obj.codename}"

def manageable_permissions():
    return Permission.objects.filter(content_type__app_label__in=["management_api", "auth"]).exclude(content_type__model="permission").select_related("content_type")

class RoleSerializer(serializers.ModelSerializer):
    permissions = serializers.PrimaryKeyRelatedField(queryset=manageable_permissions(), many=True)
    member_count = serializers.SerializerMethodField()
    class Meta:
        model = Group
        fields = ["id", "name", "permissions", "member_count"]
    def get_member_count(self, obj):
        return obj.user_set.count()

class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, trim_whitespace=False, min_length=12)
    role_names = serializers.SlugRelatedField(source="groups", many=True, read_only=True, slug_field="name")
    class Meta:
        model = User
        fields = ["id", "username", "first_name", "email", "password", "is_active", "is_staff", "is_superuser", "groups", "role_names", "last_login", "date_joined"]
        read_only_fields = ["is_superuser", "last_login", "date_joined"]
    def validate(self, attrs):
        if not self.instance and not attrs.get("password"):
            raise serializers.ValidationError({"password": "请输入至少 12 位的初始密码。"})
        # Superuser elevation/removal is a CLI-only action; this also prevents deleting the last root.
        if self.instance and self.instance.is_superuser:
            for name in ("is_active", "is_staff", "groups", "username"):
                if name in attrs and attrs[name] != getattr(self.instance, name):
                    if name == "groups" and set(attrs[name]) == set(self.instance.groups.all()):
                        continue
                    raise serializers.ValidationError({name: "不能通过管理界面变更超级管理员的身份或状态。"})
        if "password" in attrs:
            candidate = User(username=attrs.get("username", self.instance.username if self.instance else ""), email=attrs.get("email", ""))
            try:
                validate_password(attrs["password"], candidate)
            except DjangoValidationError as exc:
                raise serializers.ValidationError({"password": exc.messages})
        return attrs
    def create(self, validated_data):
        password = validated_data.pop("password")
        roles = validated_data.pop("groups", [])
        user = User.objects.create_user(password=password, **validated_data)
        user.groups.set(roles)
        return user
    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        instance = super().update(instance, validated_data)
        if password:
            instance.set_password(password)
            instance.save(update_fields=["password"])
        return instance

"""Managed, versioned phone body previews. No external image fetching or print writes."""
import hashlib
import re
import uuid
import warnings
from io import BytesIO

from PIL import Image, UnidentifiedImageError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework import viewsets

from .audit import audit
from .models import PhoneModel, PhoneColor, PhoneColorResource
from .permissions import ModelPermissions
from .phone_templates import PHONE_TEMPLATES
from .store_catalog import stock_template
from .supplier_templates import encode_png

MAX_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 8_000_000


def template_options(model):
    """Admin may prepare previews before inventory is saleable; sales rules stay separate."""
    result = [t for t in PHONE_TEMPLATES if t['code'] == model.code and t['model'] == model.name]
    for product in model.supplierproduct_set.all():
        for stock in product.device_products.filter(present=True):
            if (stock.template_image and stock.template_mask and stock.template_width and stock.template_height
                    and stock.template_imported_url == stock.template_url):
                result.append(stock_template(stock))
    return result


def validate_rgb(value):
    if (not isinstance(value, dict) or set(value) != {'r', 'g', 'b'}
            or any(type(v) is not int or not 0 <= v <= 255 for v in value.values())):
        raise serializers.ValidationError('RGB 必须恰好包含 r、g、b 三个 0–255 整数。')
    return value


def decode_png(data):
    if not data or len(data) > MAX_BYTES:
        raise serializers.ValidationError('每张资源须为不超过 10 MB 的 PNG。')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as source:
                if source.format != 'PNG' or getattr(source, 'n_frames', 1) != 1:
                    raise serializers.ValidationError('仅支持真实的单帧 PNG。')
                if not (32 <= source.width <= 4096 and 32 <= source.height <= 4096
                        and source.width * source.height <= MAX_PIXELS):
                    raise serializers.ValidationError('尺寸须为 32–4096 px，且不超过 800 万像素。')
                image = source.convert('RGBA')
                image.load()
        lo, hi = image.getchannel('A').getextrema()
        histogram = image.getchannel('A').histogram()
        if lo != 0 or hi != 255 or min(histogram[0], histogram[255]) < image.width * image.height * .01:
            raise serializers.ValidationError('覆盖图和遮罩均须包含至少 1% 的全透明及全不透明区域。')
        return image
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise serializers.ValidationError('PNG 无法真实解码。') from None


def matched_template(model, template_id):
    return next((t for t in template_options(model) if t['id'] == template_id), None)


def validate_pair(model, template_id, overlay_data, mask_data):
    template = matched_template(model, template_id)
    if not template:
        raise serializers.ValidationError('模板版本已失效或不属于当前机型，请刷新后重新上传。')
    overlay, mask = decode_png(overlay_data), decode_png(mask_data)
    expected = (template['sourceWidth'], template['sourceHeight'])
    if overlay.size != mask.size or overlay.size != expected:
        raise serializers.ValidationError('覆盖图、遮罩必须与所绑定模板像素尺寸一致。')
    return overlay, mask


def checked_resource(color):
    resource = color.current_resource
    if not resource or resource.color_id != color.pk:
        raise serializers.ValidationError('请先上传此颜色的覆盖图与遮罩。')
    data = []
    for role in ('overlay', 'mask'):
        path = getattr(resource, role)
        if not re.fullmatch(r'phone-colors/[0-9a-f]{32}/(?:overlay|mask)\.png', path):
            raise serializers.ValidationError('颜色资源路径无效，请重新上传。')
        try:
            with default_storage.open(path, 'rb') as file:
                raw = file.read(MAX_BYTES + 1)
        except (OSError, ValueError):
            raise serializers.ValidationError('颜色资源已缺失，请重新上传。') from None
        if hashlib.sha256(raw).hexdigest() != getattr(resource, role + '_sha256'):
            raise serializers.ValidationError('颜色资源内容已变化，请重新上传并核验。')
        data.append(raw)
    validate_pair(color.phone_model, resource.template_id, *data)
    return resource


class ColorSerializer(serializers.ModelSerializer):
    rgb = serializers.JSONField(validators=[validate_rgb])
    resource = serializers.SerializerMethodField()
    class Meta:
        model = PhoneColor
        fields = ['id', 'phone_model', 'code', 'name', 'rgb', 'region_note', 'source',
                  'sort_order', 'is_default', 'active', 'resource', 'created_at', 'updated_at']
        validators = []  # Checked inside the model lock, with DB constraints as a final guard.

    def get_resource(self, obj):
        r = obj.current_resource
        if not r:
            return None
        return {'version': r.version, 'template_id': r.template_id, 'width': r.width, 'height': r.height,
                'overlay': default_storage.url(r.overlay), 'mask': default_storage.url(r.mask),
                'verified_at': r.verified_at, 'verified_by': r.verified_by, 'review_note': r.review_note}

    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) - (set(self.fields) - {'id', 'resource', 'created_at', 'updated_at'}):
            raise serializers.ValidationError({'detail': '只允许编辑颜色配置字段；资源须通过上传及核验接口管理。'})
        return super().to_internal_value(data)

    def validate(self, attrs):
        if self.instance:
            if attrs.get('code', self.instance.code) != self.instance.code:
                raise serializers.ValidationError({'code': '颜色编码创建后不能修改。'})
            if attrs.get('phone_model', self.instance.phone_model).pk != self.instance.phone_model_id:
                raise serializers.ValidationError({'phone_model': '颜色不能迁移至其他机型。'})
        return attrs

    def validate_locked(self, attrs, instance=None):
        model = attrs.get('phone_model') or instance.phone_model
        others = PhoneColor.objects.filter(phone_model=model)
        if instance:
            others = others.exclude(pk=instance.pk)
        if others.filter(code=attrs.get('code', instance.code if instance else '')).exists():
            raise serializers.ValidationError({'code': '当前机型已存在此颜色编码。'})
        if attrs.get('is_default', instance.is_default if instance else False) and others.filter(is_default=True).exists():
            raise serializers.ValidationError({'is_default': '该机型已有默认颜色，请先取消原默认项。'})

    @transaction.atomic
    def create(self, validated_data):
        PhoneModel.objects.select_for_update().get(pk=validated_data['phone_model'].pk)
        self.validate_locked(validated_data)
        return super().create(validated_data)

    @transaction.atomic
    def update(self, instance, validated_data):
        PhoneModel.objects.select_for_update().get(pk=instance.phone_model_id)
        instance = PhoneColor.objects.select_for_update(of=('self',)).select_related('current_resource', 'phone_model').get(pk=instance.pk)
        self.validate_locked(validated_data, instance)
        return super().update(instance, validated_data)


class PhoneColorViewSet(viewsets.ModelViewSet):
    queryset = PhoneColor.objects.select_related('phone_model', 'current_resource')
    serializer_class = ColorSerializer
    http_method_names = ['get', 'post', 'patch', 'head', 'options']
    permission_classes = [IsAdminUser, ModelPermissions]

    def get_queryset(self):
        qs = super().get_queryset()
        model = self.request.query_params.get('phone_model')
        if model is not None:
            if not model.isascii() or not model.isdecimal():
                raise serializers.ValidationError('机型参数须为整数。')
            # PhoneModel uses BigAutoField. Validate before constructing the SQL
            # lookup: Python integers may exceed SQLite/PostgreSQL's ID range.
            model = serializers.IntegerField(
                min_value=1, max_value=2**63 - 1,
                error_messages={
                    'invalid': '机型参数无效，须为有效范围内的整数。',
                    'max_string_length': '机型参数过长。',
                    'min_value': '机型参数须大于零。',
                    'max_value': '机型参数超出有效 ID 范围。',
                },
            ).run_validation(model)
            qs = qs.filter(phone_model_id=model)
        return qs

    def get_permissions(self):
        if self.action in ('upload_resources', 'verify_resources', 'initialize_colors'):
            return [IsAdminUser()]
        return super().get_permissions()

    @action(detail=False, methods=['get', 'post'], url_path='initialize-reference')
    def initialize_colors(self, request):
        from .phone_color_initialization import initialize_reference
        perms = ['management_api.view_phonecolor']
        if request.method == 'POST':
            perms.append('management_api.add_phonecolor')
        if not request.user.has_perms(perms):
            raise PermissionDenied('预览需要颜色查看权限；初始化还需要颜色新增权限。')
        if request.method == 'GET':
            return Response(initialize_reference(request))
        if (not isinstance(request.data, dict)
                or set(request.data) != {'reference_sha256', 'confirm'}
                or request.data['confirm'] is not True
                or not isinstance(request.data['reference_sha256'], str)):
            raise serializers.ValidationError('请先预览，再提交 reference_sha256 和 confirm=true；不接受自定义资料。')
        return Response(initialize_reference(request, execute=True,
                                             expected_digest=request.data['reference_sha256']))

    @action(detail=False, methods=['get'])
    def options_catalog(self, request):
        return Response([{'id': model.pk, 'name': model.name, 'brand': model.brand.name,
                          'templates': [{'id': t['id'], 'width': t['sourceWidth'], 'height': t['sourceHeight']}
                                        for t in template_options(model)]}
                         for model in PhoneModel.objects.select_related('brand').all()])

    @transaction.atomic
    def perform_create(self, serializer):
        obj = serializer.save()
        audit(self.request, 'create', 'management_api.phonecolor', obj, '新增机型颜色（近似 RGB 预览）')

    @transaction.atomic
    def perform_update(self, serializer):
        obj = serializer.save()
        audit(self.request, 'update', 'management_api.phonecolor', obj,
              '修改颜色字段: ' + ', '.join(serializer.validated_data))

    def require_resource_permission(self, verify=False):
        perms = ['management_api.view_phonecolor', 'management_api.change_phonecolor']
        if verify:
            perms.append('management_api.verify_phonecolor')
        if not self.request.user.has_perms(perms):
            raise PermissionDenied('需要颜色查看、修改权限；人工核验还需要独立核验权限。')

    def locked_color(self):
        obj = self.get_object()
        PhoneModel.objects.select_for_update().get(pk=obj.phone_model_id)
        return self.get_queryset().select_for_update(of=('self',)).get(pk=obj.pk)

    @action(detail=True, methods=['post'], url_path='resources')
    @transaction.atomic
    def upload_resources(self, request, pk=None):
        self.require_resource_permission()
        if set(request.data) != {'overlay', 'mask', 'template_id'}:
            raise serializers.ValidationError('须同时上传 overlay、mask 并指定 template_id；不接受素材路径或远端地址。')
        files = [request.FILES.get(role) for role in ('overlay', 'mask')]
        if any(not file or file.size > MAX_BYTES for file in files):
            raise serializers.ValidationError('须上传两张不超过 10 MB 的 PNG。')
        color = self.locked_color()
        images = validate_pair(color.phone_model, request.data['template_id'], *(f.read(MAX_BYTES + 1) for f in files))
        raws = [encode_png(image) for image in images]
        if any(len(raw) > MAX_BYTES for raw in raws):
            raise serializers.ValidationError('解码后的 PNG 超过 10 MB，请优化素材后重试。')
        prefix = 'phone-colors/' + uuid.uuid4().hex
        paths = []
        try:
            for role, raw in zip(('overlay', 'mask'), raws):
                paths.append(default_storage.save(f'{prefix}/{role}.png', ContentFile(raw)))
            resource = PhoneColorResource.objects.create(color=color,
                version=(color.resources.order_by('-version').values_list('version', flat=True).first() or 0) + 1,
                template_id=request.data['template_id'], width=images[0].width, height=images[0].height,
                overlay=paths[0], mask=paths[1], overlay_sha256=hashlib.sha256(raws[0]).hexdigest(),
                mask_sha256=hashlib.sha256(raws[1]).hexdigest(), uploaded_by=request.user.username)
            color.current_resource = resource
            color.active = False
            color.save(update_fields=['current_resource', 'active', 'updated_at'])
            audit(request, 'upload', 'management_api.phonecolor', color, f'上传预览资源 v{resource.version}；停用并等待人工核验')
        except Exception:
            for path in paths:
                default_storage.delete(path)
            raise
        return Response(self.get_serializer(color).data)

    @action(detail=True, methods=['post'], url_path='verify-resources')
    @transaction.atomic
    def verify_resources(self, request, pk=None):
        self.require_resource_permission(verify=True)
        if not isinstance(request.data, dict) or set(request.data) != {'version', 'review_note'}:
            raise serializers.ValidationError('须提交当前资源 version 及人工核验说明 review_note。')
        version = request.data['version']
        note = request.data['review_note']
        if type(version) is not int or not isinstance(note, str) or not note.strip() or len(note) > 500:
            raise serializers.ValidationError('请提供整数版本及 1–500 字的核验说明。')
        color = self.locked_color()
        resource = checked_resource(color)
        if resource.version != version:
            raise serializers.ValidationError('资源版本已变化，请重新检查预览后核验。')
        resource.verified_at, resource.verified_by, resource.review_note = timezone.now(), request.user.username, note.strip()
        resource.save(update_fields=['verified_at', 'verified_by', 'review_note', 'updated_at'])
        audit(request, 'verify', 'management_api.phonecolor', color, f'人工核验预览资源 v{version}（非打印校准）')
        return Response(self.get_serializer(color).data)

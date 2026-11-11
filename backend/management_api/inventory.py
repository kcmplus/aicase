"""Authenticated admin inventory APIs. All vendor stock fields are read-only."""
from datetime import timedelta
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from rest_framework import serializers, viewsets, mixins
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import (DeviceProviderConnection, Device, SupplierProduct, DeviceProduct,
                     DeviceLaneStock, InventorySyncRun, PhoneModel)
from .permissions import ModelPermissions
from .ai_service import SuperuserOnly, encrypt_api_key, encryption_ready
from .audit import audit
from .device_provider import ALLOWED_BASE_URLS, validate_base_url, ProviderError
from .inventory_sync import sync_device, SyncBusy
from .inventory_catalog import sync_models
from .device_location import display_identity

CATALOG_SYNC_PERMISSIONS = tuple('management_api.' + p for p in (
    'view_device', 'view_supplierproduct', 'change_supplierproduct', 'add_brand', 'add_phonemodel'))


def stale(when):
    return when is None or when < timezone.now() - timedelta(minutes=15)


class StrictWriteSerializer(serializers.ModelSerializer):
    writable = set()

    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) - self.writable:
            raise serializers.ValidationError({'detail': '包含不可修改的字段。库存和供应商字段只能同步。'})
        return super().to_internal_value(data)


class ConnectionSerializer(StrictWriteSerializer):
    authorization = serializers.CharField(write_only=True, required=False, trim_whitespace=False, max_length=1000)
    masked_key = serializers.SerializerMethodField()
    writable = {'name', 'base_url', 'shop_id', 'payment_currency', 'active', 'authorization', 'revision'}

    class Meta:
        model = DeviceProviderConnection
        fields = ['id', 'name', 'base_url', 'shop_id', 'payment_currency', 'active', 'revision', 'authorization', 'masked_key',
                  'profile_sync_at', 'profile_sync_status', 'profile_sync_message']
        read_only_fields = ['profile_sync_at', 'profile_sync_status', 'profile_sync_message']

    def get_masked_key(self, obj):
        return '••••' + obj.key_last_four

    def validate(self, attrs):
        if not self.instance and not attrs.get('authorization'):
            raise serializers.ValidationError({'authorization': '请输入供应商 Authorization。'})
        if self.instance and any(k in attrs and attrs[k] != getattr(self.instance, k) for k in ('base_url', 'shop_id')):
            raise serializers.ValidationError({'detail': '服务地址和商家编号不可变更；请为其他环境新建连接。'})
        key = attrs.get('authorization')
        if key is not None and (not key.strip() or any(ord(c) < 33 or ord(c) > 126 for c in key)):
            raise serializers.ValidationError({'authorization': '凭据不得包含空白、换行或非 ASCII 字符。'})
        return attrs

    def validate_base_url(self, value):
        try:
            return validate_base_url(value)
        except ProviderError as exc:
            raise serializers.ValidationError(str(exc))

    def validate_shop_id(self, value):
        if not value.isascii() or not value.isdigit():
            raise serializers.ValidationError('商家编号必须为数字。')
        return value

    def create(self, attrs):
        key = attrs.pop('authorization')
        attrs['revision'] = 1
        return super().create({**attrs, 'api_key_ciphertext': encrypt_api_key(key), 'key_last_four': key[-4:]})

    def update(self, instance, attrs):
        if attrs.pop('revision', None) != instance.revision:
            raise serializers.ValidationError({'detail': '连接已更新，请刷新后再保存。'})
        key = attrs.pop('authorization', None)
        if key is not None:
            attrs.update(api_key_ciphertext=encrypt_api_key(key), key_last_four=key[-4:])
        attrs['revision'] = instance.revision + 1
        return super().update(instance, attrs)


class DeviceSerializer(StrictWriteSerializer):
    display_identity = serializers.SerializerMethodField()
    profile_sync_message = serializers.CharField(source='connection.profile_sync_message', read_only=True)
    profile_sync_status = serializers.CharField(source='connection.profile_sync_status', read_only=True)
    connection_name = serializers.CharField(source='connection.name', read_only=True)
    shop_id = serializers.CharField(source='connection.shop_id', read_only=True)
    connection_active = serializers.BooleanField(source='connection.active', read_only=True)
    stale = serializers.SerializerMethodField()
    writable = {'connection', 'vendor_device_id', 'name', 'location_note', 'active', 'revision',
                'name_source', 'location_source', 'installation_note', 'supplier_coordinate_type'}

    class Meta:
        model = Device
        fields = ['id', 'connection', 'connection_name', 'connection_active', 'shop_id', 'vendor_device_id', 'name', 'location_note',
                  'active', 'revision', 'last_success_at', 'sync_status', 'sync_message', 'stale', 'provider_config',
                  'provider_profile', 'provider_profile_at', 'name_source', 'location_source', 'installation_note',
                  'supplier_coordinate_type', 'display_identity', 'profile_sync_message', 'profile_sync_status']
        read_only_fields = ['last_success_at', 'sync_status', 'sync_message', 'provider_config']

    def get_stale(self, obj):
        return stale(obj.last_success_at)

    def get_display_identity(self, obj):
        return display_identity(obj)

    def validate_vendor_device_id(self, value):
        if not value.isascii() or not value.isdigit():
            raise serializers.ValidationError('设备编号必须为数字。')
        return value

    def validate(self, attrs):
        if self.instance and any(k in attrs and attrs[k] != getattr(self.instance, k) for k in ('connection', 'vendor_device_id')):
            raise serializers.ValidationError({'detail': '设备所属连接和供应商编号不可变更。'})
        return attrs

    def create(self, attrs):
        attrs['revision'] = 1
        return super().create(attrs)

    def update(self, instance, attrs):
        if attrs.pop('revision', None) != instance.revision:
            raise serializers.ValidationError({'detail': '设备已更新，请刷新后再保存。'})
        attrs['revision'] = instance.revision + 1
        return super().update(instance, attrs)


class ProductSerializer(StrictWriteSerializer):
    case_material = serializers.SerializerMethodField()
    def get_case_material(self, obj):
        from .case_materials import material_from_specs
        return material_from_specs(obj.specs)

    @transaction.atomic
    def update(self, instance, validated_data):
        instance = SupplierProduct.objects.select_for_update().get(pk=instance.pk)
        if 'active' in validated_data or 'phone_model' in validated_data:
            validated_data['auto_publish_pending'] = False
        return super().update(instance, validated_data)

    connection_name = serializers.CharField(source='connection.name', read_only=True)
    phone_model_name = serializers.CharField(source='phone_model.name', read_only=True, default='')
    print_ready = serializers.BooleanField(source='phone_model.print_ready', read_only=True, default=False)
    publication_notes = serializers.SerializerMethodField()
    writable = {'phone_model', 'display_name', 'active'}

    def get_publication_notes(self, obj):
        if not obj.phone_model:
            return ['尚未关联机型']
        notes = []
        for label, item in [('品牌', obj.phone_model.brand), ('机型', obj.phone_model), ('商品', obj)]:
            if not item.active:
                notes.append(f'{label}待自动上架' if item.auto_publish_pending else f'{label}已停用，需人工启用')
        return notes

    class Meta:
        model = SupplierProduct
        fields = ['id', 'connection', 'connection_name', 'goods_id', 'product_id', 'brand_name', 'name', 'specs',
                  'phone_model', 'phone_model_name', 'case_material', 'print_ready', 'display_name', 'active', 'publication_notes', 'updated_at']
        read_only_fields = ['connection', 'goods_id', 'product_id', 'brand_name', 'name', 'specs', 'updated_at']

    def validate(self, attrs):
        model = attrs.get('phone_model', self.instance.phone_model)
        if attrs.get('active', self.instance.active) and not model:
            raise serializers.ValidationError({'detail': '请先关联本地机型，再启用商品。'})
        return attrs


class LaneSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeviceLaneStock
        fields = ['vendor_record_id', 'lane_number', 'stock', 'present', 'source_status', 'observed_at']


class StockSerializer(StrictWriteSerializer):
    case_material = serializers.SerializerMethodField()
    def get_case_material(self, obj):
        from .case_materials import stock_material
        return stock_material(obj)

    template_asset = serializers.SerializerMethodField()
    device_name = serializers.CharField(source='device.name', read_only=True)
    vendor_device_id = serializers.CharField(source='device.vendor_device_id', read_only=True)
    goods_id = serializers.CharField(source='product.goods_id', read_only=True)
    product_name = serializers.SerializerMethodField()
    specs = serializers.JSONField(source='product.specs', read_only=True)
    phone_model_name = serializers.CharField(source='product.phone_model.name', read_only=True, default='')
    lanes = LaneSerializer(many=True, read_only=True)
    stale = serializers.SerializerMethodField()
    low_stock = serializers.SerializerMethodField()
    device_active = serializers.SerializerMethodField()
    writable = {'active', 'low_stock_threshold'}

    class Meta:
        model = DeviceProduct
        fields = ['id', 'device', 'device_name', 'vendor_device_id', 'product', 'goods_id', 'product_name', 'specs',
                  'phone_model_name', 'case_material', 'source_price', 'source_currency', 'template_url', 'active', 'present',
                  'low_stock_threshold', 'stock', 'observed_at', 'lanes', 'stale', 'low_stock', 'device_active', 'template_asset']
        read_only_fields = ['device', 'product', 'source_price', 'source_currency', 'template_url', 'present', 'stock', 'observed_at']

    def get_product_name(self, obj):
        return obj.product.display_name or obj.product.name

    def get_template_asset(self, obj):
        from .supplier_templates import template_info
        return template_info(obj)

    def get_stale(self, obj):
        return stale(obj.observed_at)

    def get_low_stock(self, obj):
        return obj.stock <= obj.low_stock_threshold

    def get_device_active(self, obj):
        return obj.device.active and obj.device.connection.active


class RunSerializer(serializers.ModelSerializer):
    device_name = serializers.CharField(source='device.name', read_only=True)

    class Meta:
        model = InventorySyncRun
        fields = ['id', 'device', 'device_name', 'batch', 'actor_name', 'started_at', 'finished_at', 'status',
                  'message', 'row_count', 'product_count', 'changes']


class InventoryWriteViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAdminUser, ModelPermissions]
    http_method_names = ['get', 'patch', 'head', 'options']
    ordering_fields = ['id']

    def get_queryset(self):
        qs = super().get_queryset()
        if self.action == 'partial_update':
            qs = qs.select_for_update(of=('self',))
        return qs

    @transaction.atomic
    def partial_update(self, request, *args, **kwargs):
        return super().partial_update(request, *args, **kwargs)

    def perform_update(self, serializer):
        obj = serializer.save()
        audit(self.request, 'update', obj._meta.label_lower, obj, '修改商品库存配置（不调整库存数量）')


class ConnectionViewSet(mixins.CreateModelMixin, InventoryWriteViewSet):
    queryset = DeviceProviderConnection.objects.all().order_by('id')
    serializer_class = ConnectionSerializer
    permission_classes = [IsAdminUser, SuperuserOnly]
    http_method_names = ['get', 'post', 'patch', 'head', 'options']

    @action(detail=True, methods=['post'], url_path='sync-devices')
    def sync_devices(self, request, pk=None):
        from .connection_sync import sync_connection
        if request.data:
            raise serializers.ValidationError({'detail': '此操作不接受额外参数。'})
        connection = self.get_object()
        try:
            result = sync_connection(connection, request.user.username)
        except ProviderError as exc:
            raise serializers.ValidationError({'detail': str(exc)})
        audit(request, 'sync', 'management_api.deviceproviderconnection', connection, result['message'])
        return Response(result)

    @transaction.atomic
    def perform_create(self, serializer):
        obj = serializer.save()
        audit(self.request, 'create', obj._meta.label_lower, obj, '新增设备连接（凭据已加密）')


class DeviceViewSet(mixins.CreateModelMixin, InventoryWriteViewSet):
    queryset = Device.objects.select_related('connection').order_by('id')
    serializer_class = DeviceSerializer
    http_method_names = ['get', 'post', 'patch', 'head', 'options']
    search_fields = ['name', 'vendor_device_id', 'location_note']

    def get_permissions(self):
        if self.action in ('sync', 'sync_profile'):
            return [IsAdminUser()]
        return super().get_permissions()

    @transaction.atomic
    def perform_create(self, serializer):
        obj = serializer.save()
        audit(self.request, 'create', obj._meta.label_lower, obj, '登记设备')

    @action(detail=True, methods=['post'], url_path='sync-profile')
    def sync_profile(self, request, pk=None):
        if not request.user.has_perm('management_api.sync_device'):
            raise PermissionDenied()
        if request.data:
            raise serializers.ValidationError({'detail': '此操作不接受额外参数。'})
        from .device_discovery import discover_devices
        device = self.get_object()
        try:
            result = discover_devices(device.connection)
        except ProviderError as exc:
            raise serializers.ValidationError({'detail': str(exc)})
        audit(request, 'sync', 'management_api.deviceproviderconnection', device.connection, result['message'])
        return Response(result)

    @action(detail=True, methods=['post'])
    def sync(self, request, pk=None):
        if not request.user.has_perm('management_api.sync_device'):
            raise PermissionDenied()
        device = self.get_object()
        try:
            run = sync_device(device.pk, request.user.username)
        except SyncBusy as exc:
            return Response({'detail': str(exc)}, status=409)
        except ProviderError as exc:
            raise serializers.ValidationError({'detail': str(exc)})
        audit(request, 'sync', 'management_api.device', device, run.message)
        return Response(RunSerializer(run).data)


class ProductViewSet(InventoryWriteViewSet):
    queryset = SupplierProduct.objects.select_related('connection', 'phone_model__brand').order_by('id')
    serializer_class = ProductSerializer
    search_fields = ['name', 'display_name', 'goods_id', 'brand_name', 'phone_model__name']
    http_method_names = ['get', 'post', 'patch', 'head', 'options']

    def get_permissions(self):
        if self.action == 'sync_models':
            return [IsAdminUser()]
        return super().get_permissions()

    @action(detail=False, methods=['post'], url_path='sync-models')
    @transaction.atomic
    def sync_models(self, request):
        if not request.user.has_perms(CATALOG_SYNC_PERMISSIONS):
            raise PermissionDenied('需要查看设备、查看与修改供应商商品、新增品牌和机型权限。')
        if not isinstance(request.data, dict) or set(request.data) != {'device'}:
            raise serializers.ValidationError({'detail': '请选择需要同步机型的设备。'})
        device_id = serializers.IntegerField(min_value=1).run_validation(request.data['device'])
        device = Device.objects.filter(pk=device_id).first()
        if device is None:
            raise serializers.ValidationError({'detail': '设备不存在，请刷新后重试。'})
        result = sync_models(device)
        result['device_name'] = device.name
        for item in result['items']:
            if item['status'] in ('created', 'matched'):
                audit(request, 'sync', 'management_api.supplierproduct',
                      SupplierProduct(pk=item['product']),
                      f"同步机型映射：商品 {item['goods_id']} → {item['message']}（机型 ID {item['phone_model']}）")
        audit(request, 'sync', 'management_api.device', device, '同步机型：' + result['message'])
        return Response(result)

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get('unmapped') == 'true':
            qs = qs.filter(phone_model__isnull=True)
        device = self.request.query_params.get('device')
        if device:
            if not device.isdigit():
                raise serializers.ValidationError({'detail': '设备参数不正确。'})
            qs = qs.filter(device_products__device_id=device)
        return qs


class StockViewSet(InventoryWriteViewSet):
    queryset = DeviceProduct.objects.select_related('device__connection', 'product__phone_model').prefetch_related('lanes').order_by('id')
    serializer_class = StockSerializer
    search_fields = ['product__name', 'product__display_name', 'product__goods_id', 'product__brand_name', 'product__phone_model__name', 'device__name', 'device__location_note']

    def get_queryset(self):
        qs = super().get_queryset()
        device = self.request.query_params.get('device')
        if device:
            if not device.isdigit():
                raise serializers.ValidationError({'detail': '设备参数不正确。'})
            qs = qs.filter(device_id=device)
        state = self.request.query_params.get('state')
        if state == 'empty':
            qs = qs.filter(stock=0)
        elif state == 'low':
            qs = qs.filter(stock__lte=F('low_stock_threshold'))
        elif state == 'stale':
            qs = qs.filter(observed_at__lt=timezone.now()-timedelta(minutes=15))
        return qs


class RunViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = InventorySyncRun.objects.select_related('device')
    serializer_class = RunSerializer
    permission_classes = [IsAdminUser, ModelPermissions]
    ordering_fields = ['started_at']
    search_fields = ['device__name', 'actor_name']

    def get_queryset(self):
        qs = super().get_queryset()
        device = self.request.query_params.get('device')
        if device:
            if not device.isdigit():
                raise serializers.ValidationError({'detail': '设备参数不正确。'})
            qs = qs.filter(device_id=device)
        return qs


class InventoryOptions(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        user = request.user
        if not any(user.has_perm('management_api.'+p) for p in (
            'view_device', 'view_supplierproduct', 'view_deviceproduct', 'view_inventorysyncrun', 'add_device')):
            raise PermissionDenied()
        return Response({
            'devices': list(Device.objects.values('id', 'name', 'vendor_device_id', 'active').order_by('name')),
            'phone_models': list(PhoneModel.objects.select_related('brand').values('id', 'name', 'brand__name', 'print_ready', 'active').order_by('name'))
                if user.has_perm('management_api.change_supplierproduct') else [],
            'connections': list(DeviceProviderConnection.objects.values('id', 'name', 'shop_id', 'active').order_by('name'))
                if user.has_perm('management_api.add_device') or user.is_superuser else [],
            'base_urls': ALLOWED_BASE_URLS if user.is_superuser else [],
            'encryption_ready': encryption_ready() if user.is_superuser else None,
            'can_sync_models': user.has_perms(CATALOG_SYNC_PERMISSIONS),
        })

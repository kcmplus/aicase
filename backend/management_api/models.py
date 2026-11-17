import uuid
from django.conf import settings
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models

class Timestamped(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        abstract = True
        ordering = ["id"]

class CatalogItem(Timestamped):
    code = models.SlugField(unique=True, max_length=80)
    name = models.CharField(max_length=120)
    active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    class Meta:
        abstract = True
        ordering = ["sort_order", "id"]
    def __str__(self):
        return self.name

class Brand(CatalogItem):
    auto_publish_pending = models.BooleanField(default=False, editable=False)


class DeviceProviderConnection(Timestamped):
    name = models.CharField(max_length=120)
    base_url = models.URLField()
    shop_id = models.CharField(max_length=40)
    payment_currency = models.CharField(max_length=3, blank=True, default='USD', choices=[('', '未确认'), ('USD', 'USD')])
    active = models.BooleanField(default=True)
    api_key_ciphertext = models.TextField(editable=False)
    key_last_four = models.CharField(max_length=4, editable=False)
    revision = models.PositiveIntegerField(default=1)
    profile_sync_at = models.DateTimeField(null=True, editable=False)
    profile_sync_status = models.CharField(max_length=20, default='never', editable=False)
    profile_sync_message = models.CharField(max_length=300, blank=True, editable=False)
    profile_sync_token = models.UUIDField(null=True, editable=False)
    profile_sync_started_at = models.DateTimeField(null=True, editable=False)

    class Meta:
        default_permissions = ()

    def __str__(self):
        return self.name


class Device(Timestamped):
    connection = models.ForeignKey(DeviceProviderConnection, on_delete=models.PROTECT)
    vendor_device_id = models.CharField(max_length=40)
    name = models.CharField(max_length=120)
    location_note = models.CharField(max_length=200, blank=True)
    name_source = models.CharField(max_length=10, choices=[('manual', '人工指定'), ('supplier', '跟随供应商')], default='manual')
    location_source = models.CharField(max_length=10, choices=[('manual', '人工指定'), ('supplier', '跟随供应商')], default='manual')
    installation_note = models.CharField(max_length=200, blank=True)
    supplier_coordinate_type = models.CharField(max_length=10, blank=True, default='', choices=[('', '未确认'), ('WGS84', 'WGS84'), ('GCJ02', 'GCJ02'), ('BD09', 'BD09')])
    active = models.BooleanField(default=True)
    revision = models.PositiveIntegerField(default=1)
    last_success_at = models.DateTimeField(null=True, editable=False)
    sync_status = models.CharField(max_length=20, default='never', editable=False)
    sync_message = models.CharField(max_length=300, blank=True, editable=False)
    sync_token = models.UUIDField(null=True, editable=False)
    sync_started_at = models.DateTimeField(null=True, editable=False)
    provider_config = models.JSONField(default=dict, editable=False)
    provider_profile = models.JSONField(default=dict, editable=False)
    provider_profile_at = models.DateTimeField(null=True, editable=False)

    class Meta:
        default_permissions = ('view', 'add', 'change')
        permissions = [('sync_device', '同步设备库存')]
        constraints = [models.UniqueConstraint(fields=['connection', 'vendor_device_id'], name='unique_provider_device')]

    def __str__(self):
        return self.name


class SupplierProduct(Timestamped):
    auto_publish_pending = models.BooleanField(default=False, editable=False)
    connection = models.ForeignKey(DeviceProviderConnection, on_delete=models.PROTECT)
    goods_id = models.CharField(max_length=40)
    product_id = models.CharField(max_length=40)
    brand_name = models.CharField(max_length=120, blank=True)
    name = models.CharField(max_length=200)
    specs = models.JSONField(default=list)
    phone_model = models.ForeignKey('PhoneModel', null=True, blank=True, on_delete=models.PROTECT)
    display_name = models.CharField(max_length=200, blank=True)
    active = models.BooleanField(default=False)

    class Meta:
        default_permissions = ('view', 'change')
        constraints = [models.UniqueConstraint(fields=['connection', 'goods_id'], name='unique_supplier_goods')]


class DeviceProduct(Timestamped):
    device = models.ForeignKey(Device, on_delete=models.PROTECT, related_name='products')
    product = models.ForeignKey(SupplierProduct, on_delete=models.PROTECT, related_name='device_products')
    source_price = models.DecimalField(max_digits=12, decimal_places=2, null=True)
    source_currency = models.CharField(max_length=10, blank=True)
    template_url = models.URLField(max_length=2000, blank=True)
    template_imported_url = models.URLField(max_length=2000, blank=True, editable=False)
    template_image = models.CharField(max_length=300, blank=True, editable=False)
    template_mask = models.CharField(max_length=300, blank=True, editable=False)
    template_width = models.PositiveIntegerField(default=0, editable=False)
    template_height = models.PositiveIntegerField(default=0, editable=False)
    template_mask_note = models.CharField(max_length=300, blank=True, editable=False)
    template_import_error = models.CharField(max_length=300, blank=True, editable=False)
    template_imported_at = models.DateTimeField(null=True, blank=True, editable=False)
    active = models.BooleanField(default=True)
    present = models.BooleanField(default=True)
    low_stock_threshold = models.PositiveSmallIntegerField(default=3)
    stock = models.PositiveIntegerField(default=0)
    observed_at = models.DateTimeField()

    class Meta:
        default_permissions = ('view', 'change')
        constraints = [models.UniqueConstraint(fields=['device', 'product'], name='unique_device_product')]


class DeviceLaneStock(Timestamped):
    device = models.ForeignKey(Device, on_delete=models.PROTECT)
    device_product = models.ForeignKey(DeviceProduct, on_delete=models.PROTECT, related_name='lanes')
    vendor_record_id = models.CharField(max_length=40)
    lane_number = models.CharField(max_length=40)
    stock = models.PositiveIntegerField(default=0)
    present = models.BooleanField(default=True)
    source_status = models.CharField(max_length=40, blank=True)
    observed_at = models.DateTimeField()
    batch = models.UUIDField()

    class Meta:
        default_permissions = ()
        constraints = [models.UniqueConstraint(fields=['device', 'vendor_record_id'], name='unique_device_lane_record')]


class InventorySyncRun(models.Model):
    device = models.ForeignKey(Device, on_delete=models.PROTECT)
    batch = models.UUIDField(default=uuid.uuid4, unique=True)
    actor_name = models.CharField(max_length=150, blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True)
    status = models.CharField(max_length=20, default='running')
    message = models.CharField(max_length=300, blank=True)
    row_count = models.PositiveIntegerField(default=0)
    product_count = models.PositiveIntegerField(default=0)
    changes = models.JSONField(default=list)

    class Meta:
        ordering = ['-started_at', '-id']
        default_permissions = ('view',)

class PhoneModel(CatalogItem):
    auto_publish_pending = models.BooleanField(default=False, editable=False)
    brand = models.ForeignKey(Brand, on_delete=models.PROTECT, related_name="models")
    preview_family = models.CharField(max_length=20, choices=[("iphone", "iPhone 示意壳"), ("samsung", "Samsung 示意壳")])
    legacy_index = models.PositiveSmallIntegerField(unique=True, null=True, blank=True, editable=False)
    print_ready = models.BooleanField(default=False)
    notes = models.TextField(blank=True, max_length=2000)
    adaptation_prompt = models.TextField(blank=True, max_length=4000)
    composition_regions = models.JSONField(default=dict, editable=False)
    composition_revision = models.PositiveIntegerField(default=0, editable=False)

class PhoneColor(Timestamped):
    """Preview configuration only; never a supplier SKU or print template."""
    phone_model = models.ForeignKey(PhoneModel, on_delete=models.PROTECT, related_name='colors')
    code = models.SlugField(max_length=80)
    name = models.CharField(max_length=120, blank=True)
    rgb = models.JSONField()
    region_note = models.CharField(max_length=300, blank=True)
    source = models.CharField(max_length=500, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_default = models.BooleanField(default=False)
    active = models.BooleanField(default=False)
    current_resource = models.ForeignKey('PhoneColorResource', null=True, editable=False,
        on_delete=models.PROTECT, related_name='+')

    class Meta:
        ordering = ['sort_order', 'id']
        default_permissions = ('view', 'add', 'change')
        permissions = [('verify_phonecolor', '人工核验机型颜色资源')]
        constraints = [
            models.UniqueConstraint(fields=['phone_model', 'code'], name='unique_model_color_code'),
            models.UniqueConstraint(fields=['phone_model'], condition=models.Q(is_default=True), name='unique_model_default_color'),
        ]

    def __str__(self):
        return f'{self.phone_model.name} · {self.code}'


class PhoneColorResource(Timestamped):
    color = models.ForeignKey(PhoneColor, on_delete=models.PROTECT, related_name='resources')
    version = models.PositiveIntegerField()
    template_id = models.CharField(max_length=160)
    width = models.PositiveIntegerField()
    height = models.PositiveIntegerField()
    overlay = models.CharField(max_length=300)
    mask = models.CharField(max_length=300)
    overlay_sha256 = models.CharField(max_length=64)
    mask_sha256 = models.CharField(max_length=64)
    uploaded_by = models.CharField(max_length=150)
    verified_at = models.DateTimeField(null=True, editable=False)
    verified_by = models.CharField(max_length=150, blank=True, editable=False)
    review_note = models.CharField(max_length=500, blank=True, editable=False)

    class Meta:
        default_permissions = ()
        constraints = [models.UniqueConstraint(fields=['color', 'version'], name='unique_color_resource_version')]

class Graphic(CatalogItem):
    category = models.CharField(max_length=80, default="graphic")
    image_path = models.CharField(max_length=300)
    license = models.CharField(max_length=200, blank=True)

class DesignTemplate(CatalogItem):
    category = models.CharField(max_length=80, default="graphic")
    description = models.CharField(max_length=300, blank=True)
    background = models.CharField(max_length=7, default="#ffffff", validators=[RegexValidator(r"^#[0-9a-fA-F]{6}$", "Use a six-digit hex color")])
    preview_path = models.CharField(max_length=300, blank=True)
    layout = models.JSONField(default=dict, blank=True)
    legacy_index = models.PositiveSmallIntegerField(unique=True, null=True, blank=True, editable=False)

class AIStyle(CatalogItem):
    name_zh = models.CharField(max_length=120, blank=True)
    description_zh = models.CharField(max_length=500, blank=True)
    description = models.CharField(max_length=500, blank=True)
    image_path = models.CharField(max_length=300)
    prompt = models.TextField(blank=True, max_length=4000)
    provider = models.CharField(max_length=50, default="demo", choices=[("demo", "演示样片")])

class AIServiceConfig(Timestamped):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    provider = models.CharField(max_length=20, default="openai")
    # Inactive provider profiles contain encrypted keys only. Never serialize this field.
    provider_profiles = models.JSONField(default=dict, editable=False)
    model_name = models.CharField(max_length=100, default="gpt-image-2")
    image_retention_days = models.PositiveSmallIntegerField(default=30)
    api_key_ciphertext = models.TextField(blank=True, editable=False)
    key_last_four = models.CharField(max_length=4, blank=True, editable=False)
    key_updated_at = models.DateTimeField(null=True, blank=True, editable=False)
    revision = models.PositiveIntegerField(default=0, editable=False)
    last_check_at = models.DateTimeField(null=True, blank=True, editable=False)
    last_check_status = models.CharField(max_length=20, default="untested", editable=False)
    last_check_message = models.CharField(max_length=300, blank=True, editable=False)

    class Meta:
        default_permissions = ()
        constraints = [models.CheckConstraint(condition=models.Q(id=1), name="single_ai_service_config")]

class AIExample(CatalogItem):
    name_zh = models.CharField(max_length=120, blank=True)
    subject_zh = models.CharField(max_length=200, blank=True)
    subject = models.CharField(max_length=200)
    original_path = models.CharField(max_length=300)
    revision = models.PositiveIntegerField(default=0, editable=False)

class AIExampleResult(models.Model):
    example = models.ForeignKey(AIExample, on_delete=models.CASCADE, related_name="results")
    style = models.ForeignKey(AIStyle, on_delete=models.PROTECT, related_name="example_results")
    image_path = models.CharField(max_length=300)
    prompt = models.TextField(blank=True, max_length=8000)
    phone_model = models.ForeignKey(PhoneModel, null=True, blank=True, on_delete=models.PROTECT, related_name="ai_example_results")
    class Meta:
        ordering = ["style__sort_order", "style_id"]
        default_permissions = ()
        constraints = [models.UniqueConstraint(fields=["example", "style"], name="unique_example_style")]

class PricingPlan(CatalogItem):
    kind = models.CharField(max_length=20, choices=[("print", "单次打印"), ("ai_monthly", "AI 月度订阅"), ("courier_shipping", "每单快递运费")])
    price = models.DecimalField(max_digits=8, decimal_places=2, validators=[MinValueValidator(0)])
    currency = models.CharField(max_length=3, default="USD", choices=[("USD", "USD")])
    monthly_credits = models.PositiveIntegerField(default=0)
    trial_credits = models.PositiveIntegerField(default=0)
    class Meta(CatalogItem.Meta):
        abstract = False
        constraints = [models.UniqueConstraint(fields=["kind"], condition=models.Q(active=True), name="one_active_plan_per_kind")]

class PrintOrder(Timestamped):
    class Fulfillment(models.TextChoices):
        UNSPECIFIED = 'unspecified', '待确认配送方式'
        PICKUP = 'pickup', '设备现场自取'
        COURIER = 'courier', '快递配送'
        AIR = 'air', '空运配送'

    # On-site pickup is the default; device binding and print authorization remain separate.
    fulfillment_type = models.CharField(max_length=20, choices=Fulfillment.choices,
                                        default=Fulfillment.PICKUP)
    delivery_address = models.JSONField(default=dict, blank=True, editable=False)
    shipping_quote = models.JSONField(default=dict, blank=True, editable=False)
    reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    owner_hash = models.CharField(max_length=64, blank=True, db_index=True, editable=False)
    request_key = models.UUIDField(null=True, unique=True, editable=False)
    mode = models.CharField(max_length=20, default="legacy", choices=[("legacy", "历史订单"), ("free_test", "0元免付联调"), ("demo", "演示支付"), ("stripe_test", "Stripe 测试"), ("stripe_live", "Stripe 正式"), ("airwallex_test", "Airwallex 测试"), ("airwallex_live", "Airwallex 正式")])
    stripe_session_id = models.CharField(max_length=255, null=True, blank=True, unique=True, editable=False)
    stripe_checkout_url = models.TextField(blank=True, editable=False)
    stripe_payment_intent = models.CharField(max_length=255, blank=True, editable=False)
    airwallex_payment_intent = models.CharField(max_length=255, null=True, blank=True, unique=True, editable=False)
    airwallex_event_id = models.CharField(max_length=255, blank=True, editable=False)
    payment_credentials = models.TextField(blank=True, editable=False)
    payment_return_url = models.URLField(blank=True, editable=False)
    paid_at = models.DateTimeField(null=True, blank=True, editable=False)
    revision = models.PositiveIntegerField(default=1)
    station_id = models.CharField(max_length=30, blank=True)
    customer_email = models.EmailField(blank=True)
    customer = models.ForeignKey('Customer', null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name='print_orders', editable=False)
    model_name = models.CharField(max_length=120)
    case_material = models.CharField(max_length=20, blank=True, default='', choices=[('', '款式待确认'), ('standard', '普通款'), ('magnetic', '磁吸款')])
    status = models.CharField(max_length=30, default="pending", choices=[("pending", "待付款"), ("paid", "已确认"), ("printing", "打印中"), ("ready", "待取货"), ("completed", "已完成"), ("cancelled", "已取消")])
    amount = models.DecimalField(max_digits=8, decimal_places=2, validators=[MinValueValidator(0)])
    currency = models.CharField(max_length=3, default="USD")
    snapshot = models.JSONField(default=dict)
    notes = models.TextField(blank=True, max_length=2000)
    class Meta:
        ordering = ["-created_at"]


class PrintRefund(Timestamped):
    order = models.OneToOneField(PrintOrder, on_delete=models.PROTECT, related_name='refund')
    reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    provider_id = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, default='requested', choices=[('requested', '待核实'), ('pending', '退款处理中'), ('succeeded', '已退款'), ('failed', '退款失败')])
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    currency = models.CharField(max_length=3)
    reason = models.CharField(max_length=128)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        default_permissions = ()


class SupplierOrder(Timestamped):
    """Durable cloud submission; never a second hardware print queue."""
    order = models.OneToOneField(PrintOrder, on_delete=models.PROTECT, related_name='supplier_order')
    transport = models.CharField(max_length=20, default='supplier', editable=False,
        choices=[('supplier', '供应商'), ('direct_debug', '直连模拟')])
    device = models.ForeignKey(Device, on_delete=models.PROTECT)
    inventory_item = models.ForeignKey(DeviceProduct, on_delete=models.PROTECT)
    business_number = models.CharField(max_length=32, unique=True)
    goods_id = models.PositiveBigIntegerField()
    order_revision = models.PositiveIntegerField()
    snapshot_sha256 = models.CharField(max_length=64)
    state = models.CharField(max_length=20, default='draft', choices=[
        ('draft', '待打印文件'), ('prepared', '待推送'), ('submitting', '正在推送'),
        ('submitted', '已推送'), ('rejected', '推送失败，待用户确认重试'), ('unknown', '推送结果待核实')])
    vendor_id = models.CharField(max_length=80, blank=True)
    trade_no = models.CharField(max_length=120, blank=True)
    print_image = models.BinaryField(default=bytes, editable=False)
    preview_image = models.BinaryField(default=bytes, editable=False)
    image_sha256 = models.CharField(max_length=64, blank=True)
    file_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    submitted_at = models.DateTimeField(null=True, editable=False)
    message = models.CharField(max_length=200, blank=True)
    print_confirmed_at = models.DateTimeField(null=True, editable=False)
    release_state = models.CharField(max_length=20, default='idle', editable=False)
    release_claim = models.UUIDField(null=True, editable=False)
    native_print_status = models.CharField(max_length=30, blank=True, editable=False)
    native_pay_status = models.CharField(max_length=30, blank=True, editable=False)
    observed_at = models.DateTimeField(null=True, editable=False)
    cloud_status = models.JSONField(default=dict, editable=False)
    cloud_checked_at = models.DateTimeField(null=True, editable=False)
    cloud_synced_at = models.DateTimeField(null=True, editable=False)
    inventory_refresh_pending = models.BooleanField(default=False, editable=False)

    class Meta:
        default_permissions = ()


class TerminalCredential(Timestamped):
    """Retired credentials retained for history; no runtime authenticates them."""
    device = models.OneToOneField(Device, on_delete=models.CASCADE, related_name='terminal_credential')
    token_hash = models.CharField(max_length=64, unique=True, editable=False)
    active = models.BooleanField(default=True)

    class Meta:
        default_permissions = ()


class StripeConfig(Timestamped):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    enabled = models.BooleanField(default=False)
    mode = models.CharField(max_length=4, default="test", choices=[("test", "测试"), ("live", "正式")])
    storefront_url = models.URLField(blank=True)
    test_credentials = models.TextField(blank=True, editable=False)
    live_credentials = models.TextField(blank=True, editable=False)
    revision = models.PositiveIntegerField(default=0, editable=False)

    class Meta:
        default_permissions = ()
        constraints = [models.CheckConstraint(condition=models.Q(id=1), name="single_stripe_config")]


class AirwallexConfig(Timestamped):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    enabled = models.BooleanField(default=False)
    mode = models.CharField(max_length=4, default="test", choices=[("test", "测试"), ("live", "正式")])
    storefront_url = models.URLField(blank=True)
    test_credentials = models.TextField(blank=True, editable=False)
    live_credentials = models.TextField(blank=True, editable=False)
    revision = models.PositiveIntegerField(default=0, editable=False)

    class Meta:
        default_permissions = ()
        constraints = [models.CheckConstraint(condition=models.Q(id=1), name="single_airwallex_config")]

class AuditLog(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    actor_name = models.CharField(max_length=150)
    action = models.CharField(max_length=30)
    resource = models.CharField(max_length=100)
    object_id = models.CharField(max_length=100, blank=True)
    summary = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        ordering = ["-created_at", "-id"]
        default_permissions = ("view",)


class Customer(Timestamped):
    display_name = models.CharField(max_length=60, blank=True)
    notes = models.CharField(max_length=1000, blank=True)
    last_login_at = models.DateTimeField(null=True, blank=True)
    revision = models.PositiveIntegerField(default=0)
    session_version = models.PositiveIntegerField(default=0)
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    active = models.BooleanField(default=True)
    verified_at = models.DateTimeField()

    class Meta:
        default_permissions = ("view", "change")


class EmailChallenge(models.Model):
    email = models.EmailField(primary_key=True)
    nonce = models.UUIDField(default=uuid.uuid4)
    code_hash = models.CharField(max_length=64)
    expires_at = models.DateTimeField()
    sent_at = models.DateTimeField()
    window_at = models.DateTimeField()
    sent_count = models.PositiveIntegerField(default=0)
    attempts = models.PositiveIntegerField(default=0)
    delivered = models.BooleanField(default=False)

    class Meta:
        default_permissions = ()


class CustomerAuthLimit(models.Model):
    key = models.CharField(primary_key=True, max_length=64)
    window_at = models.DateTimeField()
    count = models.PositiveIntegerField(default=0)

    class Meta:
        default_permissions = ()


class SMTPConfig(Timestamped):
    signup_credits = models.PositiveIntegerField(default=1)
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    enabled = models.BooleanField(default=False)
    host = models.CharField(max_length=253, blank=True)
    port = models.PositiveIntegerField(default=587)
    security = models.CharField(max_length=10, default='starttls')
    username = models.CharField(max_length=254, blank=True)
    password_ciphertext = models.TextField(blank=True, editable=False)
    from_email = models.EmailField(blank=True)
    from_name = models.CharField(max_length=100, default='POPOMO')
    revision = models.PositiveIntegerField(default=0)

    class Meta:
        default_permissions = ()
        constraints = [models.CheckConstraint(condition=models.Q(id=1), name='single_smtp_config')]


class AIAccount(Timestamped):
    owner_hash = models.CharField(primary_key=True, max_length=64, editable=False)
    customer = models.OneToOneField(Customer, null=True, blank=True, on_delete=models.PROTECT)
    trial_granted = models.PositiveIntegerField(default=0)
    bonus_granted = models.PositiveIntegerField(default=0)
    trial_used = models.PositiveIntegerField(default=0)
    subscription = models.JSONField(null=True, blank=True)

    class Meta:
        default_permissions = ()


class AIRender(Timestamped):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    request_key = models.UUIDField(unique=True, editable=False)
    owner_hash = models.CharField(max_length=64, db_index=True, editable=False)
    status = models.CharField(max_length=20, default='queued', db_index=True)
    style_code = models.CharField(max_length=80)
    style_name = models.CharField(max_length=120)
    provider = models.CharField(max_length=20, default="openai", editable=False)
    model_name = models.CharField(max_length=80)
    phone_model = models.CharField(max_length=120)
    phone_template_id = models.CharField(max_length=80)
    composition_snapshot = models.JSONField(default=dict, editable=False)
    prompt = models.TextField(editable=False)
    input_image = models.BinaryField(editable=False)
    input_mime = models.CharField(max_length=20)
    input_hash = models.CharField(max_length=64, editable=False)
    result_image = models.BinaryField(null=True, editable=False)
    image_expires_at = models.DateTimeField(null=True, editable=False, db_index=True)
    image_deleted_at = models.DateTimeField(null=True, editable=False)
    allocation = models.JSONField(default=dict)
    credit_restored = models.BooleanField(default=False)
    started_at = models.DateTimeField(null=True)
    completed_at = models.DateTimeField(null=True)
    error_code = models.CharField(max_length=60, blank=True)
    error_message = models.CharField(max_length=300, blank=True)
    provider_request_id = models.CharField(max_length=150, blank=True, editable=False)
    api_started_at = models.DateTimeField(null=True, editable=False)
    api_finished_at = models.DateTimeField(null=True, editable=False)
    api_duration_ms = models.PositiveIntegerField(null=True, editable=False)
    http_status = models.PositiveSmallIntegerField(null=True, editable=False)
    request_params = models.JSONField(default=dict, editable=False)
    usage = models.JSONField(default=dict, editable=False)
    cost_amount = models.DecimalField(max_digits=18, decimal_places=8, null=True, editable=False)
    cost_currency = models.CharField(max_length=12, blank=True, editable=False)
    cost_source = models.CharField(max_length=20, default='unknown', editable=False)
    cost_details = models.JSONField(default=dict, editable=False)
    cost_recorded_at = models.DateTimeField(null=True, editable=False)

    class Meta:
        ordering = ['-created_at']
        default_permissions = ()
        indexes = [models.Index(fields=['-created_at'], name='ai_render_created_idx')]


class CreditEntry(models.Model):
    account = models.ForeignKey(AIAccount, on_delete=models.PROTECT, related_name='credit_entries')
    event_key = models.CharField(max_length=150)
    kind = models.CharField(max_length=30)
    pool = models.CharField(max_length=10, choices=[('gift', '赠送额度'), ('monthly', '月度额度')])
    amount = models.IntegerField()
    balance_before = models.PositiveIntegerField()
    balance_after = models.PositiveIntegerField()
    period = models.BigIntegerField(null=True, blank=True)
    render_id = models.UUIDField(null=True, blank=True)
    reason = models.CharField(max_length=200, blank=True)
    actor_name = models.CharField(max_length=150, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-id']
        default_permissions = ()
        constraints = [models.UniqueConstraint(fields=['account', 'event_key'], name='unique_credit_event'),
                       models.CheckConstraint(condition=models.Q(balance_after=models.F('balance_before') + models.F('amount')), name='credit_balance_matches_delta')]

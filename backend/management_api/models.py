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
    pass

class PhoneModel(CatalogItem):
    brand = models.ForeignKey(Brand, on_delete=models.PROTECT, related_name="models")
    preview_family = models.CharField(max_length=20, choices=[("iphone", "iPhone 示意壳"), ("samsung", "Samsung 示意壳")])
    legacy_index = models.PositiveSmallIntegerField(unique=True, null=True, blank=True, editable=False)
    print_ready = models.BooleanField(default=False)
    notes = models.TextField(blank=True, max_length=2000)

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
    description = models.CharField(max_length=500, blank=True)
    image_path = models.CharField(max_length=300)
    prompt = models.TextField(blank=True, max_length=4000)
    provider = models.CharField(max_length=50, default="demo", choices=[("demo", "演示样片")])

class AIExample(CatalogItem):
    subject = models.CharField(max_length=200)
    original_path = models.CharField(max_length=300)

class AIExampleResult(models.Model):
    example = models.ForeignKey(AIExample, on_delete=models.CASCADE, related_name="results")
    style = models.ForeignKey(AIStyle, on_delete=models.PROTECT, related_name="example_results")
    image_path = models.CharField(max_length=300)
    class Meta:
        ordering = ["style__sort_order", "style_id"]
        default_permissions = ()
        constraints = [models.UniqueConstraint(fields=["example", "style"], name="unique_example_style")]

class PricingPlan(CatalogItem):
    kind = models.CharField(max_length=20, choices=[("print", "单次打印"), ("ai_monthly", "AI 月度订阅")])
    price = models.DecimalField(max_digits=8, decimal_places=2, validators=[MinValueValidator(0)])
    currency = models.CharField(max_length=3, default="USD", choices=[("USD", "USD")])
    monthly_credits = models.PositiveIntegerField(default=0)
    trial_credits = models.PositiveIntegerField(default=0)
    class Meta(CatalogItem.Meta):
        abstract = False
        constraints = [models.UniqueConstraint(fields=["kind"], condition=models.Q(active=True), name="one_active_plan_per_kind")]

class PrintOrder(Timestamped):
    reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    owner_hash = models.CharField(max_length=64, blank=True, db_index=True, editable=False)
    request_key = models.UUIDField(null=True, unique=True, editable=False)
    mode = models.CharField(max_length=20, default="legacy", choices=[("legacy", "历史订单"), ("demo", "测试支付")])
    revision = models.PositiveIntegerField(default=1)
    station_id = models.CharField(max_length=30, blank=True)
    customer_email = models.EmailField(blank=True)
    model_name = models.CharField(max_length=120)
    status = models.CharField(max_length=30, default="pending", choices=[("pending", "待付款"), ("paid", "已确认"), ("printing", "打印中"), ("ready", "待取货"), ("completed", "已完成"), ("cancelled", "已取消")])
    amount = models.DecimalField(max_digits=8, decimal_places=2, validators=[MinValueValidator(0)])
    currency = models.CharField(max_length=3, default="USD")
    snapshot = models.JSONField(default=dict)
    notes = models.TextField(blank=True, max_length=2000)
    class Meta:
        ordering = ["-created_at"]

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

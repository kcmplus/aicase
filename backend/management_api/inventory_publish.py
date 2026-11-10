"""Finish stock sync without overriding manual catalog decisions or calibration."""
import time
from collections import Counter
from datetime import timedelta
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from .models import Brand, PhoneModel, SupplierProduct, DeviceProduct, AuditLog
from .supplier_templates import import_template, TemplateError


def publish_device_catalog(device_id, actor_name):
    imported = published = pending = 0
    reasons = Counter()
    started = time.monotonic()
    stocks = DeviceProduct.objects.filter(device_id=device_id, present=True, active=True,
        stock__gt=0, product__phone_model__isnull=False).select_related('product')
    for stock in stocks.order_by('template_imported_at', 'pk'):
        if time.monotonic() - started > 15:
            pending += 1
            reasons['本轮限时，待续同步'] += 1
            continue
        if not stock.template_url:
            pending += 1
            reasons['缺少模板链接'] += 1
            continue
        try:
            before = stock.template_imported_at
            result = import_template(stock.pk, stock.product.phone_model_id)
            imported += result.template_imported_at != before
        except TemplateError:
            pending += 1
            reasons['模板导入未成功'] += 1
            continue
        # Lock in catalog order, rechecking current stock/mapping after network I/O.
        model_id = stock.product.phone_model_id
        brand_id = PhoneModel.objects.get(pk=model_id).brand_id
        with transaction.atomic():
            brand = Brand.objects.select_for_update().get(pk=brand_id)
            model = PhoneModel.objects.select_for_update().get(pk=model_id)
            product = SupplierProduct.objects.select_for_update().get(pk=stock.product_id)
            current = DeviceProduct.objects.select_for_update().get(pk=stock.pk)
            if product.phone_model_id != model.pk or model.brand_id != brand.pk:
                pending += 1
                reasons['映射已变更'] += 1
                continue
            ready = DeviceProduct.objects.filter(pk=current.pk, active=True, present=True, stock__gt=0,
                device__active=True, device__connection__active=True,
                observed_at__gte=timezone.now()-timedelta(minutes=15),
                template_imported_url=F('template_url'), template_width__gt=0, template_height__gt=0
                ).exclude(template_image='').exclude(template_mask='').exists()
            entities = (brand, model, product)
            blocked = [label for label, obj in zip(('品牌停用', '机型停用', '商品停用'), entities)
                       if not obj.active and not obj.auto_publish_pending]
            if not ready or blocked:
                pending += 1
                reasons.update(blocked or ['库存或底图遮罩待补齐'])
                continue
            changed = False
            for obj in entities:
                if obj.auto_publish_pending:
                    obj.active, obj.auto_publish_pending = True, False
                    obj.save(update_fields=['active', 'auto_publish_pending', 'updated_at'])
                    changed = True
            if changed:
                published += 1
                AuditLog.objects.create(actor_name=actor_name, action='sync',
                    resource='management_api.supplierproduct', object_id=str(product.pk),
                    summary=f'同步自动启用商品 {product.goods_id}：机型明确、有库存、底图与遮罩完整；不变更打印校准状态。')
    detail = '；'.join(f'{reason} {count} 个' for reason, count in reasons.items())
    return f'模板更新 {imported} 个，自动启用 {published} 个，待确认 {pending} 个。' + (detail + '。' if detail else '')

"""Stock-backed storefront choices. A snapshot is not an inventory reservation."""
import hashlib
from datetime import timedelta
from django.core.files.storage import default_storage
from django.db.models import F
from django.conf import settings
from django.utils import timezone
from rest_framework import serializers
from .models import Device, DeviceProduct, PhoneModel
from .case_materials import MATERIALS, stock_material


def catalog_stocks():
    return DeviceProduct.objects.select_related('product__phone_model__brand', 'device__connection').filter(
        present=True, active=True, stock__gt=0, device__active=True, device__connection__active=True,
        product__active=True, product__phone_model__active=True,
        product__phone_model__brand__active=True, template_imported_url=F('template_url'),
        template_width__gt=0, template_height__gt=0,
    ).exclude(template_image='').exclude(template_mask='')


def available_stocks():
    # Sync writes a complete snapshot transactionally. A running/failed refresh
    # must not hide the last valid snapshot while it is still fresh.
    if settings.DIRECT_DEBUG_ENABLED:
        # The separate debug database replays its catalog; it is not live inventory.
        return catalog_stocks().filter(device_id=settings.DIRECT_DEBUG_DEVICE_ID)
    return catalog_stocks().filter(observed_at__gte=timezone.now()-timedelta(minutes=15))


def stock_template(stock):
    model = stock.product.phone_model
    version = hashlib.sha256(f'{model.pk}|{stock.template_image}|{stock.template_mask}'.encode()).hexdigest()[:20]
    return {'id': f'supplier-{stock.pk}-{version}', 'model': model.name, 'code': model.code,
            'overlay': default_storage.url(stock.template_image), 'previewOverlay': default_storage.url(stock.template_image),
            'mask': default_storage.url(stock.template_mask), 'sourceWidth': stock.template_width,
            'sourceHeight': stock.template_height, 'printWidth': stock.template_width,
            'printHeight': stock.template_height, 'dpi': None, 'calibrated': False,
            'previewOnly': True, 'inventoryItemId': stock.pk}


def resolve_stock_template(model, template_id):
    for stock in available_stocks().filter(product__phone_model__name=model).order_by('pk'):
        template = stock_template(stock)
        if template['id'] == template_id:
            return stock, template
    return None, None


def available_colors(model, template=None):
    """RGB choices belong to the model; verified image resources are optional."""
    from .phone_colors import checked_resource, validate_rgb
    result = []
    for color in model.colors.filter(active=True).select_related('current_resource', 'phone_model').order_by('sort_order', 'pk'):
        try:
            validate_rgb(color.rgb)
        except serializers.ValidationError:
            continue
        item = {'code': color.code, 'name': color.name, 'rgb': color.rgb,
                'isDefault': color.is_default, 'previewMode': 'rgb', 'resource': None}
        resource = color.current_resource
        if (template and resource and resource.verified_at
                and resource.template_id == template['id']
                and (resource.width, resource.height) == (template['sourceWidth'], template['sourceHeight'])):
            try:
                resource = checked_resource(color)
            except serializers.ValidationError:
                pass  # Invalid image resources cannot paint a preview, but RGB is still usable.
            else:
                item.pop('previewMode')
                item['resource'] = {'version': resource.version, 'templateId': resource.template_id,
                                    'width': resource.width, 'height': resource.height,
                                    'overlay': default_storage.url(resource.overlay),
                                    'mask': default_storage.url(resource.mask)}
        result.append(item)
    return result


def model_record(model, sources, *, scoped):
    record = {'name': model.name, 'code': model.code, 'brand': model.brand.name, 'styles': [], 'colors': available_colors(model)}
    templates = []
    for material in MATERIALS:
        stock = sources.get((model.pk, material))
        style = {'caseMaterial': material, 'available': bool(stock) if scoped else True, 'colors': available_colors(model) if stock or not scoped else []}
        if stock:
            template = stock_template(stock)
            style.update(templateId=template['id'], inventoryItemId=stock.pk, colors=available_colors(model, template))
            if scoped:
                style['quantity'] = stock.stock
            templates.append(template)
            if 'templateId' not in record:
                record.update(templateId=template['id'], inventoryItemId=stock.pk, colors=style['colors'])
        record['styles'].append(style)
    return record, templates


def design_models():
    """Published models and styles can be designed without pickup inventory."""
    models, templates, sources = [], [], {}
    previews = DeviceProduct.objects.select_related('product__phone_model').filter(
        product__active=True, product__phone_model__active=True, product__phone_model__brand__active=True,
        template_imported_url=F('template_url'), template_width__gt=0, template_height__gt=0,
    ).exclude(template_image='').exclude(template_mask='').order_by('pk')
    for stock in [*available_stocks().order_by('pk'), *previews]:
        material = stock_material(stock)
        if material:
            sources.setdefault((stock.product.phone_model_id, material), stock)
    for model in PhoneModel.objects.filter(active=True, brand__active=True).select_related('brand').order_by('sort_order', 'pk'):
        record, variants = model_record(model, sources, scoped=False)
        models.append(record)
        templates.extend(variants)
    return {'version': 1, 'scope': 'catalog', 'models': models, 'templates': templates,
            'device_id': None, 'availability': 'ready' if models else 'empty', 'max_age_seconds': 60}


def store_models(params):
    device_id, shop_id = params.get('device_id'), params.get('shop_id')
    if device_id is None and shop_id is None:
        return design_models()
    stocks = available_stocks()
    candidates = catalog_stocks()
    if shop_id and not device_id:
        raise serializers.ValidationError({'detail': 'A device_id is required with shop_id.'})
    if device_id is not None:
        if not device_id.isascii() or not device_id.isdecimal() or len(device_id) > 40:
            raise serializers.ValidationError({'detail': 'Invalid device_id.'})
        devices = Device.objects.filter(vendor_device_id=device_id)
        if shop_id is not None:
            if not shop_id.isascii() or not shop_id.isdecimal() or len(shop_id) > 40:
                raise serializers.ValidationError({'detail': 'Invalid shop_id.'})
            devices = devices.filter(connection__shop_id=shop_id)
        if devices.count() > 1:
            raise serializers.ValidationError({'detail': 'The device identifier is ambiguous. Please check the device link.'})
        stocks = stocks.filter(device__in=devices)
        candidates = candidates.filter(device__in=devices)
    models, templates, sources, phone_models = [], [], {}, {}
    for stock in stocks.order_by('product__phone_model__sort_order', 'product__phone_model_id', 'pk'):
        model = stock.product.phone_model
        material = stock_material(stock)
        if not material:
            continue
        phone_models.setdefault(model.pk, model)
        sources.setdefault((model.pk, material), stock)
    for model in phone_models.values():
        record, variants = model_record(model, sources, scoped=True)
        models.append(record)
        templates.extend(variants)
    availability = 'ready' if models else 'updating' if candidates.exists() else 'empty'
    return {'version': 1, 'scope': 'device', 'models': models, 'templates': templates, 'device_id': device_id, 'availability': availability,
            'max_age_seconds': 60}

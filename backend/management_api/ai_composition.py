"""Preview-space composition guidance, never print or inventory authorization."""
import math
from copy import deepcopy
from functools import lru_cache
from PIL import Image
from django.core.files.storage import default_storage
from django.db.models import F
from rest_framework import serializers
from .case_materials import MATERIALS, stock_material
from .phone_templates import PHONE_TEMPLATES, ASSET_ROOT


def template_choices(model, material):
    from .models import DeviceProduct
    from .store_catalog import stock_template, available_stocks
    # Match unscoped storefront previews, including saved templates whose stock is stale.
    rows = DeviceProduct.objects.select_related('product__phone_model').filter(
        product__phone_model=model, product__active=True,
        template_imported_url=F('template_url'), template_width__gt=0, template_height__gt=0,
    ).exclude(template_image='').exclude(template_mask='').order_by('pk')
    preferred = set(available_stocks().filter(product__phone_model=model).values_list('pk', flat=True))
    rows = sorted(rows, key=lambda row: (row.pk not in preferred, row.pk))
    result = [stock_template(row) for row in rows if stock_material(row) == material]
    result.extend(deepcopy(t) for t in reversed(PHONE_TEMPLATES) if t['model'] == model.name)
    return result


def resolve_template(model, material='standard', template_id=''):
    choices = template_choices(model, material)
    if template_id:
        found = next((t for t in choices if t['id'] == template_id), None)
        if not found:
            raise serializers.ValidationError('The selected case template has changed. Choose your phone and case style again.')
        return found
    return choices[0] if choices else None


def rect(value):
    if not isinstance(value, dict) or set(value) != {'x', 'y', 'width', 'height'}:
        raise serializers.ValidationError('区域必须包含 x、y、width、height。')
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in value.values()):
        raise serializers.ValidationError('区域坐标必须是有限数字。')
    x, y, w, h = (value[k] for k in ('x', 'y', 'width', 'height'))
    if min(x, y) < 0 or min(w, h) < 1 or x+w > 100 or y+h > 100:
        raise serializers.ValidationError('区域使用 0–100% 坐标，宽高至少 1%，且不能超出画布。')
    return {k: round(v, 4) for k, v in value.items()}


def overlaps(a, b):
    return (a['x'] < b['x']+b['width'] and b['x'] < a['x']+a['width']
            and a['y'] < b['y']+b['height'] and b['y'] < a['y']+a['height'])


class RegionInput(serializers.Serializer):
    revision = serializers.IntegerField(min_value=0)
    template_id = serializers.CharField(max_length=80, allow_blank=True)
    case_material = serializers.ChoiceField(choices=MATERIALS)
    safe = serializers.JSONField()
    avoid = serializers.ListField(child=serializers.JSONField(), max_length=8)
    margin = serializers.FloatField(min_value=0, max_value=10)
    source_url = serializers.URLField(max_length=500, allow_blank=True, required=False, default='')
    note = serializers.CharField(max_length=500, allow_blank=True, required=False, default='')
    confirmed = serializers.BooleanField()
    reset = serializers.BooleanField(required=False, default=False)

    def validate(self, data):
        if set(self.initial_data)-set(self.fields):
            raise serializers.ValidationError('包含不支持的参数。')
        data['safe'] = rect(data['safe'])
        data['avoid'] = [rect(r) for r in data['avoid']]
        if not math.isfinite(data['margin']) or min(data['safe']['width'], data['safe']['height']) <= 2*data['margin']+1:
            raise serializers.ValidationError('安全区太小，无法容纳预留边距。')
        if any(overlaps(data['safe'], r) for r in data['avoid']):
            raise serializers.ValidationError('主体安全区不能与镜头遮挡区重叠。')
        if data['source_url'] and not data['source_url'].startswith('https://'):
            raise serializers.ValidationError('资料链接须使用 HTTPS。')
        return data


def profile_key(template_id, material):
    return material + ':' + (template_id or 'generic')


def mask_regions(alpha):
    """Conservative continuous central band, measured in the full preview canvas."""
    w, h = alpha.size
    # Use the central 60%; require every pixel in each row to be visible.
    band = alpha.crop((round(w*.2), 0, round(w*.8), h))
    runs = []; start = None
    for y in range(h):
        clear = band.crop((0, y, band.width, y+1)).getextrema()[0] >= 250
        if clear and start is None:
            start = y
        if start is not None and (not clear or y == h-1):
            end = y if not clear else h
            runs.append((start, end)); start = None
    if not runs:
        return None
    top, bottom = max(runs, key=lambda r: r[1]-r[0])
    if bottom-top < h*.25:
        return None
    # Round inward to the editor's two-decimal precision; adjacent edges stay adjacent.
    y, end = math.ceil(top/h*10000)/100, math.floor(bottom/h*10000)/100
    return {'safe': {'x': 20, 'y': round(y, 4), 'width': 60, 'height': round(end-y, 4)},
            'avoid': [{'x': 0, 'y': 0, 'width': 100, 'height': round(y, 4)}] if y >= 1 else []}


@lru_cache(maxsize=128)
def _mask_suggestion(path):
    # Paths come only from server-owned template records, never from user input.
    try:
        if path.startswith('/assets/phone-templates/'):
            file = (ASSET_ROOT / path.lstrip('/')).open('rb')
        elif path.startswith('/media/supplier-templates/'):
            file = default_storage.open(path.removeprefix('/media/'), 'rb')
        else:
            return None
        with file, Image.open(file) as image:
            if max(image.size) > 4096 or 'A' not in image.getbands():
                return None
            return mask_regions(image.getchannel('A'))
    except (OSError, ValueError):
        return None


def suggestion(template):
    found = _mask_suggestion(template['mask']) if template else None
    return {**deepcopy(found or {'safe': {'x': 20, 'y': 35, 'width': 60, 'height': 55},
                              'avoid': [{'x': 0, 'y': 0, 'width': 100, 'height': 35}]}),
            'margin': 3, 'source_url': '', 'note': '', 'confirmed': False,
            'origin': 'preview_mask' if found else 'conservative_fallback'}


def chosen_regions(model, template, material):
    stored = model.composition_regions.get(profile_key(template['id'] if template else '', material))
    return deepcopy(stored) if stored else suggestion(template)


def composition_snapshot(model, template, material, requested_template=''):
    region = chosen_regions(model, template, material)
    safe = dict(region['safe']); margin = region['margin']
    safe.update(x=safe['x']+margin, y=safe['y']+margin,
                width=safe['width']-2*margin, height=safe['height']-2*margin)
    # The editor contains the complete 2:3 generated image and blurs the background.
    # Transform case-space guidance into that image's coordinate system.
    ratio = template['printWidth']/template['printHeight'] if template else .5
    iw, ih = (100, 150*ratio) if ratio <= 2/3 else ((2/3)/ratio*100, 100)
    ox, oy = (100-iw)/2, (100-ih)/2
    def image_rect(r):
        x1, y1 = max(0, (r['x']-ox)/iw*100), max(0, (r['y']-oy)/ih*100)
        x2 = min(100, (r['x']+r['width']-ox)/iw*100)
        y2 = min(100, (r['y']+r['height']-oy)/ih*100)
        return {'x': round(x1, 2), 'y': round(y1, 2), 'width': round(x2-x1, 2), 'height': round(y2-y1, 2)}
    image_safe = image_rect(safe)
    if min(image_safe['width'], image_safe['height']) < 1:
        raise serializers.ValidationError('The configured subject area does not fit the generated image. Please contact the store.')
    return {'version': 1, 'case_material': material, 'requested_template_id': requested_template,
            'template_id': template['id'] if template else '', 'model': model.name,
            'revision': model.composition_revision, 'origin': region.get('origin', 'manual'),
            'confirmed': region.get('confirmed', False), 'safe': safe, 'avoid': region['avoid'],
            'image_safe': image_safe, 'fit': 'blur', 'output_size': [1024, 1536]}


def prompt_guidance(snapshot):
    r = snapshot['image_safe']
    return ('\n\nTEMPLATE-BASED COMPOSITION\n'
            'Output a 1024x1536 portrait image. Coordinates below are percentages of this output image, '
            'origin at the top-left. The app will preserve the entire image at its original aspect ratio '
            'and extend its background when fitting the case. '
            f'Place the COMPLETE head including hair, ears and face, and all essential subject details, '
            f'inside x={r["x"]:.2f}% to {r["x"]+r["width"]:.2f}%, '
            f'y={r["y"]:.2f}% to {r["y"]+r["height"]:.2f}%. '
            'Scale the subject down and add natural background above it as needed. '
            'Only expendable background may be outside this safe area. Do not draw the guides or the phone. '
            'These template-specific coordinates override generic quarter/center guidance. '
            'This is preview composition guidance, not calibrated print geometry.')


def admin_regions(model):
    items = []
    for material in MATERIALS:
        choices = template_choices(model, material)
        if not choices:
            choices = [None]
        for template in choices:
            template_id = template['id'] if template else ''
            key = profile_key(template_id, material)
            items.append({'template_id': template_id, 'case_material': material,
                          'width': template['printWidth'] if template else 1000,
                          'height': template['printHeight'] if template else 2000,
                          'overlay': template['previewOverlay'] if template else '',
                          'saved': key in model.composition_regions,
                          'regions': chosen_regions(model, template, material),
                          'suggestion': suggestion(template)})
    return {'revision': model.composition_revision, 'templates': items}

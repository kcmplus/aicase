"""Import unambiguous vendor model identities; never publish or calibrate templates."""
import hashlib
import re
import unicodedata

from django.db import transaction

from .models import Brand, PhoneModel, SupplierProduct


def clean(value):
    value = unicodedata.normalize('NFKC', value)
    return ' '.join(''.join(c for c in value if unicodedata.category(c) != 'Cf').split())


def key(value):
    # Keep +, hyphens and generation suffixes: S24 != S24+, 4G != 5G.
    return re.sub(r'\s+', '', clean(value)).casefold()


def model_identity(product):
    values = {clean(s.get('spec_value', '')) for s in product.specs
              if clean(s.get('spec_name', '')).casefold() in ('型号', 'model')}
    if len(values) != 1 or not next(iter(values)):
        raise ValueError('缺少唯一的型号规格，请手动映射。')
    model = next(iter(values))
    brand = key(product.brand_name)
    if brand in ('iphone', 'apple'):
        model = re.sub(r'^iphone\s*', '', model, flags=re.I)
        if not re.fullmatch(r'(?:\d{1,2}e?|X[SR]?|SE(?:\s*\d)?)(?:\s*(?:Pro\s*Max|Pro|Plus|Mini|Max))?', model, re.I):
            raise ValueError('苹果型号格式待确认，请手动映射。')
        model = re.sub(r'(?<=\d)(?=Pro|Plus|Mini|Max)', ' ', model, flags=re.I)
        model = re.sub(r'Pro\s*Max', 'Pro Max', model, flags=re.I)
        prefix, brand_name, family = 'iPhone', 'Apple', 'iphone'
    elif brand == 'samsung':
        model = re.sub(r'^(?:samsung\s*)?(?:galaxy\s*)?', '', model, flags=re.I)
        if not re.fullmatch(r'[AS]\d{1,3}(?:S|\+|\s*(?:Ultra|FE))?(?:[-\s]+[45]G)?', model, re.I):
            raise ValueError('三星型号格式待确认，请手动映射。')
        prefix, brand_name, family = 'Samsung', 'Samsung', 'samsung'
    elif brand == 'xiaomi':
        # The model field omits Redmi/Xiaomi; take only that explicit series prefix.
        series = re.match(r'^(Redmi|Xiaomi|POCO)\b', clean(product.name), re.I)
        if not series:
            raise ValueError('无法确认小米 / Redmi / POCO 系列，请手动映射。')
        prefix = {'redmi': 'Redmi', 'xiaomi': 'Xiaomi', 'poco': 'POCO'}[series[1].casefold()]
        explicit_series = re.match(r'^(Redmi|Xiaomi|POCO)\b', model, re.I)
        if explicit_series and explicit_series[1].casefold() != prefix.casefold():
            raise ValueError('商品与型号的系列不一致，请手动映射。')
        model = re.sub(r'^(?:Redmi|Xiaomi|POCO)\s*', '', model, flags=re.I)
        if not re.fullmatch(r'(?:Note\s*)?[A-Z]?\d{1,3}[A-Z]?(?:\s*Pro\+?)?(?:[-\s]+[45]G)?', model, re.I):
            raise ValueError('小米系列型号格式待确认，请手动映射。')
        brand_name, family = 'Xiaomi', 'samsung'
    else:
        raise ValueError('暂不支持该品牌自动识别，请手动映射。')
    model = re.sub(r'pro|max|mini|plus|ultra|fe', lambda m: {
        'pro': 'Pro', 'max': 'Max', 'mini': 'Mini', 'plus': 'Plus', 'ultra': 'Ultra', 'fe': 'FE',
    }[m[0].casefold()], model, flags=re.I)
    return brand_name, f'{prefix} {model}', family


@transaction.atomic
def sync_models(device):
    result = {'created': 0, 'matched': 0, 'preserved': 0, 'skipped': 0, 'items': []}
    # Lock catalog brands in one order across devices, then product rows. Stock sync
    # does not acquire brand locks; manual mapping uses the same product row lock.
    brands = list(Brand.objects.select_for_update().order_by('pk'))
    products = list(SupplierProduct.objects.select_for_update(of=('self',)).filter(
        device_products__device=device, device_products__present=True).order_by('pk'))
    def brand_order(product):
        try:
            return model_identity(product)[0], product.pk
        except ValueError:
            return '', product.pk
    for product in sorted(products, key=brand_order):
        item = {'product': product.pk, 'goods_id': product.goods_id}
        if product.phone_model_id:
            status, reason = 'preserved', '保留已有映射'
        else:
            try:
                brand_name, name, family = model_identity(product)
                aliases = {'apple', 'iphone'} if brand_name == 'Apple' else {key(brand_name)}
                matches = [b for b in brands if key(b.name) in aliases]
                if len(matches) > 1:
                    raise ValueError('存在多个同名品牌，请手动映射。')
                brand = matches[0] if matches else None
                if brand is None:
                    brand, _ = Brand.objects.get_or_create(code=f'vendor-{key(brand_name)}', defaults={
                        'name': brand_name, 'active': False,
                    })
                    if key(brand.name) not in aliases:
                        raise ValueError('品牌编码已占用，请手动映射。')
                    brands.append(brand)
                matches = [m for m in PhoneModel.objects.filter(brand=brand) if key(m.name) == key(name)]
                if len(matches) > 1:
                    raise ValueError('存在多个同名机型，请手动映射。')
                if matches:
                    model, created = matches[0], False
                else:
                    digest = hashlib.sha256(f'{brand.pk}:{key(name)}'.encode()).hexdigest()[:24]
                    model, created = PhoneModel.objects.get_or_create(code=f'vendor-model-{digest}', defaults={
                        'brand': brand, 'name': name, 'preview_family': family,
                        'active': False, 'print_ready': False,
                        'notes': '由供应商型号规格同步；待模板审核与打印校准。预览类型仅为示意壳，不是设备打印模板。',
                    })
                    if model.brand_id != brand.pk or key(model.name) != key(name):
                        raise ValueError('机型编码已占用，请手动映射。')
                product.phone_model = model
                product.save(update_fields=['phone_model', 'updated_at'])
                status, reason = ('created' if created else 'matched'), model.name
            except ValueError as exc:
                status, reason = 'skipped', str(exc)
        result[status] += 1
        item.update(status=status, message=reason, phone_model=product.phone_model_id)
        result['items'].append(item)
    result['message'] = (f"新增 {result['created']} 个机型，关联已有 {result['matched']} 个，"
                         f"保留映射 {result['preserved']} 个，待确认 {result['skipped']} 个。")
    return result

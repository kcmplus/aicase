"""Case style is independent of phone model; unknown specifications are never guessed."""
from .models import SupplierProduct

MATERIALS = ('standard', 'magnetic')
LABELS = {'standard': '普通款', 'magnetic': '磁吸款'}


def material_from_specs(specs):
    values = {str(s.get('spec_value', '')).strip() for s in specs if isinstance(s, dict)
              and str(s.get('spec_name', '')).strip() in ('版本', '手机壳物料', '手機殼物料')}
    return {'普通款': 'standard', '磁吸款': 'magnetic'}.get(next(iter(values)), '') if len(values) == 1 else ''


def stock_material(stock):
    return material_from_specs(stock.product.specs)


def material_stocks(queryset, material):
    if material not in MATERIALS:
        return queryset.none()
    products = SupplierProduct.objects.filter(pk__in=queryset.values('product_id')).values_list('pk', 'specs')
    return queryset.filter(product_id__in=[pk for pk, specs in products if material_from_specs(specs) == material])

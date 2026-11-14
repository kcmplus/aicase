"""Publish complete inventory snapshots; never reserve or deduct stock locally."""
import time
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from .models import (Device, DeviceProviderConnection, SupplierProduct, DeviceProduct,
                     DeviceLaneStock, InventorySyncRun, Brand, AuditLog)
from .device_provider import DeviceProvider, ProviderError, image_url
from .inventory_catalog import sync_models


class SyncBusy(ProviderError):
    pass


def identifier(value):
    if isinstance(value, bool) or not isinstance(value, (str, int)) or not str(value).isdigit() or len(str(value)) > 40:
        raise ProviderError('供应商编号格式不正确。')
    return str(value)


def stock_value(value):
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 1_000_000:
        raise ProviderError('供应商库存数量不正确，本次未更新库存。')
    return value


def normalize_rows(rows, device):
    if not isinstance(rows, list) or len(rows) > 10000:
        raise ProviderError('供应商货道列表格式不正确。')
    if not rows:
        raise ProviderError('供应商返回空列表，请核对设备或向设备方确认；保留上次库存。')
    result, ids, lane_numbers, goods = [], set(), set(), {}
    for source in rows:
        if not isinstance(source, dict):
            raise ProviderError('供应商货道记录格式不正确。')
        if identifier(source.get('shop_id')) != device.connection.shop_id or identifier(source.get('device_id')) != device.vendor_device_id:
            raise ProviderError('供应商记录与当前商家或设备不匹配。')
        rid = identifier(source.get('id'))
        if rid in ids:
            raise ProviderError('供应商返回重复的货道记录，本次未更新库存。')
        ids.add(rid)
        deleted = source.get('is_deleted', 0)
        if deleted not in (0, 1):
            raise ProviderError('供应商删除状态未知。')
        if deleted == 1:
            continue
        lane = source.get('device_box_num')
        if not isinstance(lane, str) or not lane or len(lane) > 40 or lane in lane_numbers:
            raise ProviderError('供应商货道编号重复或格式不正确。')
        lane_numbers.add(lane)
        gid, pid = identifier(source.get('goods_id')), identifier(source.get('product_id'))
        specs = source.get('specs')
        if not isinstance(specs, list) or len(specs) > 30:
            raise ProviderError('供应商商品规格格式不正确。')
        clean_specs = []
        for spec in specs:
            if not isinstance(spec, dict) or any(not isinstance(spec.get(k), str) or len(spec[k]) > 120 for k in ('spec_name', 'spec_value')):
                raise ProviderError('供应商商品规格格式不正确。')
            clean_specs.append({k: spec[k] for k in ('spec_name', 'spec_value')})
        clean_specs.sort(key=lambda x: (x['spec_name'], x['spec_value']))
        name, brand = source.get('product_name'), source.get('product_brand_name', '')
        if not isinstance(name, str) or not name or len(name) > 200 or not isinstance(brand, str) or len(brand) > 120:
            raise ProviderError('供应商商品名称格式不正确。')
        try:
            price = Decimal(str(source.get('price')))
            if not price.is_finite() or not 0 <= price <= Decimal('9999999999.99') or price != price.quantize(Decimal('.01')):
                raise ValueError()
        except (ValueError, InvalidOperation):
            raise ProviderError('供应商价格格式不正确。') from None
        signature = (pid, name, brand, clean_specs, price)
        if gid in goods and goods[gid] != signature:
            raise ProviderError('同一商品的规格或价格不一致，请设备方确认。')
        goods[gid] = signature
        result.append(dict(record_id=rid, lane=lane, goods_id=gid, product_id=pid, name=name,
                           brand=brand, specs=clean_specs, price=price, stock=stock_value(source.get('surplus_stock')),
                           status=str(source.get('status', ''))[:40], template=image_url(source.get('template_url'))))
    if not result:
        raise ProviderError('没有有效货道记录，请确认清空操作；保留上次库存。')
    return result


def sync_device(device_id, actor_name='管理命令'):
    now, batch = timezone.now(), uuid.uuid4()
    with transaction.atomic():
        device = Device.objects.select_related('connection').get(pk=device_id)
        if not device.active or not device.connection.active:
            raise ProviderError('设备或连接已停用。')
        acquired = Device.objects.filter(pk=device_id).filter(
            Q(sync_token__isnull=True) | Q(sync_started_at__lt=now-timedelta(minutes=3))
        ).update(sync_token=batch, sync_started_at=now, sync_status='running', sync_message='正在读取设备库存。')
        if not acquired:
            raise SyncBusy('该设备正在同步，请稍后刷新。')
        InventorySyncRun.objects.filter(device=device, status='running').update(
            status='failed', finished_at=now, message='上次同步已超时，由新批次接替。')
        run = InventorySyncRun.objects.create(device=device, batch=batch, actor_name=actor_name)
    try:
        provider = DeviceProvider(device.connection)
        rows = normalize_rows(provider.lanes(device.vendor_device_id), device)
        previous_ids = set(DeviceLaneStock.objects.filter(device=device, present=True).values_list('vendor_record_id', flat=True))
        incoming_ids = {r['record_id'] for r in rows}
        # Never infer removal from a potentially partial response. A later operator
        # workflow can confirm removal once the vendor's full-list contract is known.
        if previous_ids - incoming_ids:
            raise ProviderError('货道记录减少，需向设备方核实列表完整性；保留上次库存。')
        groups = defaultdict(list)
        for row in rows:
            groups[row['goods_id']].append(row)
        config = provider.config(device.vendor_device_id)
        if not isinstance(config, dict):
            raise ProviderError('设备配置响应格式不正确。')
        currency = config.get('currency') or ''
        if not isinstance(currency, str) or len(currency) > 10:
            raise ProviderError('设备币种格式不正确。')
        cached = dict(DeviceProduct.objects.filter(device=device).values_list('product__goods_id', 'template_url'))
        templates = {gid: next((r['template'] for r in items if r['template']), cached.get(gid, '')) for gid, items in groups.items()}
        missing = [gid for gid in groups if not templates[gid]]
        deadline = time.monotonic() + 12

        def detail_template(gid):
            if time.monotonic() > deadline:
                return gid, ''
            try:
                detail = provider.detail(device.vendor_device_id, gid)
                if (not isinstance(detail, dict) or identifier(detail.get('goods_id')) != gid
                        or identifier(detail.get('device_id')) != device.vendor_device_id
                        or identifier(detail.get('shop_id')) != device.connection.shop_id):
                    return gid, ''
                return gid, image_url(detail.get('template_url'))
            except ProviderError:
                return gid, ''

        with ThreadPoolExecutor(max_workers=4) as pool:
            for gid, url in pool.map(detail_template, missing):
                templates[gid] = url
        with transaction.atomic():
            # Serialize publishing with both connection rotation and device changes.
            connection = DeviceProviderConnection.objects.select_for_update().get(pk=device.connection_id)
            current = Device.objects.select_for_update().get(pk=device_id)
            if (current.sync_token != batch or current.revision != device.revision or not current.active
                    or not connection.active or connection.revision != device.connection.revision):
                raise ProviderError('同步期间配置已变更，本批次未发布，请重新同步。')
            # Match manual catalog sync's brand -> product lock order. Model
            # creation and the stock snapshot must commit or roll back together.
            list(Brand.objects.select_for_update().order_by('pk'))
            observed = timezone.now()
            changes = []
            for gid in sorted(groups):
                items = groups[gid]
                row = items[0]
                existing = SupplierProduct.objects.select_for_update().filter(connection=connection, goods_id=gid).first()
                if existing and (existing.product_id != row['product_id'] or existing.specs != row['specs']):
                    raise ProviderError('供应商商品编号对应的规格发生变化，请核实商品映射；本批次未发布。')
                product, product_created = SupplierProduct.objects.update_or_create(connection=connection, goods_id=gid, defaults={
                    'product_id': row['product_id'], 'name': row['name'], 'brand_name': row['brand'], 'specs': row['specs']})
                if product_created:
                    product.auto_publish_pending = True
                    product.save(update_fields=['auto_publish_pending'])
                dp, created = DeviceProduct.objects.get_or_create(device=current, product=product, defaults={'observed_at': observed})
                total = sum(r['stock'] for r in items)
                if created or total != dp.stock:
                    changes.append({'goods_id': gid, 'before': None if created else dp.stock, 'after': total})
                dp.source_price, dp.source_currency = row['price'], currency
                if dp.template_url != templates[gid]:
                    dp.template_import_error = ''
                dp.template_url = templates[gid]
                dp.stock, dp.observed_at, dp.present = total, observed, True
                dp.save()
                for item in items:
                    DeviceLaneStock.objects.update_or_create(device=current, vendor_record_id=item['record_id'], defaults={
                        'device_product': dp, 'lane_number': item['lane'], 'stock': item['stock'], 'present': True,
                        'source_status': item['status'], 'observed_at': observed, 'batch': batch})
            catalog = sync_models(current)
            for item in catalog['items']:
                if item['status'] in ('created', 'matched'):
                    AuditLog.objects.create(
                        actor_name=actor_name, action='sync', resource='management_api.supplierproduct',
                        object_id=str(item['product']),
                        summary=f"库存同步自动关联机型：商品 {item['goods_id']} → {item['message']}（机型 ID {item['phone_model']}）"[:300])
            outstanding = sum(not t for t in templates.values())
            message = f'已同步 {len(rows)} 条货道、{len(groups)} 个商品。'
            if outstanding:
                message += f'{outstanding} 个商品模板待补充，可再次同步。'
            message += catalog['message']
            current.last_success_at = observed
            current.sync_status, current.sync_message, current.sync_token = 'success', message, None
            current.provider_config = {k: config.get(k) for k in ('is_lock', 'print_type', 'currency')
                                       if isinstance(config.get(k), (str, int, bool, type(None)))}
            current.save(update_fields=['last_success_at', 'sync_status', 'sync_message', 'sync_token', 'provider_config', 'updated_at'])
            run.status, run.message, run.finished_at = 'success', message, observed
            run.row_count, run.product_count, run.changes = len(rows), len(groups), changes
            run.save()
    except Exception as exc:
        # Never store raw transport errors (which may contain headers or URLs).
        message = str(exc) if isinstance(exc, ProviderError) else '同步失败，本次未更新库存；请检查配置后重试。'
        InventorySyncRun.objects.filter(pk=run.pk, status='running').update(status='failed', message=message, finished_at=timezone.now())
        Device.objects.filter(pk=device_id, sync_token=batch).update(sync_status='failed', sync_message=message, sync_token=None)
    run.refresh_from_db()
    if run.status == 'success':
        from .inventory_publish import publish_device_catalog
        summary = publish_device_catalog(device_id, actor_name)
        run.message = (run.message + summary)[:300]
        run.save(update_fields=['message'])
        Device.objects.filter(pk=device_id, last_success_at=observed).update(sync_message=run.message)
    return run

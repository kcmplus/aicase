"""Local vendor overlays and provisional preview masks, separate from print approval."""
import hashlib
import time
import warnings
from io import BytesIO
from urllib.parse import urlsplit, urlunsplit

import requests
from PIL import Image, ImageDraw, UnidentifiedImageError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from django.utils import timezone

from .models import DeviceProduct


class TemplateError(ValueError):
    pass


def download_template(url):
    try:
        parsed = urlsplit(url)
    except ValueError:
        raise TemplateError('模板地址格式不正确。') from None
    # Never forward vendor authorization to object storage, follow redirects or
    # accept arbitrary URLs. Upgrade the supplier's HTTP links to HTTPS.
    if (parsed.scheme not in ('https', 'http') or parsed.netloc not in ('oss.widermatrix.cn', 'file.autovendpro.com')
            or parsed.fragment or not parsed.path.lower().endswith('.png')):
        raise TemplateError('模板地址不在已支持的供应商图片域名内。')
    url = urlunsplit(('https', parsed.netloc, parsed.path, parsed.query, ''))
    started = time.monotonic()
    try:
        with requests.get(url, timeout=(3, 8), stream=True, allow_redirects=False) as response:
            if response.status_code != 200:
                raise TemplateError('供应商模板暂时无法下载，请稍后重试。')
            data = bytearray()
            for chunk in response.iter_content(65536):
                data.extend(chunk)
                if len(data) > 10 * 1024 * 1024 or time.monotonic() - started > 15:
                    raise TemplateError('模板超过大小或下载时间限制。')
            return bytes(data)
    except requests.RequestException:
        raise TemplateError('供应商模板下载失败，请稍后重试。') from None


def preview_mask(image):
    """Find the closed transparent component at the canvas center; never guess bleed."""
    w, h = image.size
    alpha = image.getchannel('A')
    if alpha.getpixel((w//2, h//2)) >= 250:
        raise TemplateError('底图中心不透明，请补充独立遮罩。')
    component = alpha.point(lambda p: 0 if p < 250 else 255)
    ImageDraw.floodfill(component, (w//2, h//2), 128, thresh=0)
    mask = component.point(lambda p: 255 if p == 128 else 0)
    edges = [(0, 0, w, 1), (0, h-1, w, h), (0, 0, 1, h), (w-1, 0, w, h)]
    if any(mask.crop(box).getbbox() for box in edges):
        raise TemplateError('透明区域未封闭，请补充独立遮罩。')
    if mask.histogram()[255] < w*h*0.2:
        raise TemplateError('可识别区域过小，请补充独立遮罩。')
    result = Image.new('RGBA', image.size, 'white')
    result.putalpha(mask)
    return result


def encode_png(image):
    output = BytesIO()
    # Store pixels only, without untrusted PNG metadata or guessed DPI.
    clean = Image.frombytes(image.mode, image.size, image.tobytes())
    clean.save(output, format='PNG')
    return output.getvalue()


def store_png(data, role):
    digest = hashlib.sha256(data).hexdigest()
    path = f'supplier-templates/{digest}-{role}.png'
    if not default_storage.exists(path):
        path = default_storage.save(path, ContentFile(data))
    return path


def import_template(stock_id, model_id, refresh=False):
    stock = DeviceProduct.objects.select_related('product').get(pk=stock_id)
    if stock.product.phone_model_id != model_id:
        raise TemplateError('商品机型映射已变化，请刷新。')
    url = stock.template_url
    if not url:
        raise TemplateError('供应商尚未提供模板链接。')
    if (not refresh and stock.template_imported_url == url and stock.template_image
            and default_storage.exists(stock.template_image)
            and (not stock.template_mask or default_storage.exists(stock.template_mask))):
        return stock
    try:
        data = download_template(url)
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as source:
                if source.format != 'PNG' or getattr(source, 'n_frames', 1) != 1:
                    raise TemplateError('需要单帧 PNG 底图。')
                if not (32 <= source.width <= 4096 and 32 <= source.height <= 4096 and source.width*source.height <= 8_000_000):
                    raise TemplateError('模板尺寸超出支持范围。')
                image = source.convert('RGBA')
        mask_path, mask_note = '', ''
        try:
            mask = preview_mask(image)
        except TemplateError as exc:
            mask_note = str(exc)
        else:
            mask_path = store_png(encode_png(mask), 'mask')
            mask_note = '由底图封闭透明区域生成，仅作预览遮罩；打印范围尚未确认。'
        # Preserve the verified original PNG, including its color profile and
        # density metadata. Do not resize or invent a print DPI during import.
        image_path = store_png(data, 'overlay')
        # Mapping edits lock the product; acquire it before the stock row so
        # an import cannot publish against a concurrently changed model.
        with transaction.atomic():
            product = stock.product.__class__.objects.select_for_update().get(pk=stock.product_id)
            current = DeviceProduct.objects.select_for_update().get(pk=stock_id)
            if current.template_url != url or product.phone_model_id != model_id or not current.present:
                raise TemplateError('模板来源或机型映射已变化，请重新同步。')
            current.template_image, current.template_mask = image_path, mask_path
            current.template_width, current.template_height = image.size
            current.template_imported_url = url
            current.template_imported_at = timezone.now()
            current.template_mask_note = mask_note
            current.template_import_error = ''
            current.save(update_fields=['template_image', 'template_mask', 'template_width', 'template_height',
                'template_imported_url', 'template_imported_at', 'template_mask_note', 'template_import_error', 'updated_at'])
            return current
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        error = '模板图片无法解析，请确认文件有效后重试。'
    except TemplateError as exc:
        error = str(exc)
    DeviceProduct.objects.filter(pk=stock_id, template_url=url).update(template_import_error=error)
    raise TemplateError(error)


def template_info(stock):
    current = bool(stock.template_image and stock.template_imported_url == stock.template_url)
    return {
        'id': stock.pk, 'goods_id': stock.product.goods_id,
        'device_name': stock.device.name, 'specs': stock.product.specs,
        'has_source': bool(stock.template_url),
        'status': 'imported' if current else 'failed' if stock.template_import_error else 'pending' if stock.template_url else 'missing',
        'image': default_storage.url(stock.template_image) if current else '',
        'mask': default_storage.url(stock.template_mask) if current and stock.template_mask else '',
        'width': stock.template_width if current else 0, 'height': stock.template_height if current else 0,
        'mask_note': stock.template_mask_note if current else '', 'error': stock.template_import_error,
        'imported_at': stock.template_imported_at if current else None,
    }

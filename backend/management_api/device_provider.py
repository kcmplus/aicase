"""Read-only vendor transport. No order/print mutation is exposed here."""
import time
from urllib.parse import urlsplit
import requests
from .ai_service import decrypt_api_key

ALLOWED_BASE_URLS = ('https://shop.widermatrix.cn', 'https://shop.autovendpro.com')


class ProviderError(Exception):
    pass


def validate_base_url(value):
    value = value.rstrip('/')
    if value not in ALLOWED_BASE_URLS:
        raise ProviderError('请选择已支持的设备服务地址。')
    return value


def image_url(value):
    if not value:
        return ''
    if not isinstance(value, str) or len(value) > 2000:
        raise ProviderError('供应商模板地址格式不正确。')
    parsed = urlsplit(value)
    if parsed.scheme not in ('https', 'http') or not parsed.hostname or parsed.username or parsed.password:
        raise ProviderError('供应商模板地址格式不正确。')
    return value


class DeviceProvider:
    def __init__(self, connection):
        self.base_url = validate_base_url(connection.base_url)
        self.shop_id = connection.shop_id
        self.authorization = decrypt_api_key(connection)

    def get(self, path, device_id, **params):
        if path not in ('/shop/goods/list', '/mp/common/getDeviceInfo', '/Mp/Product/getDeviceGoodsInfo'):
            raise ProviderError('不支持此设备查询。')
        for attempt in range(2):
            try:
                # Do not forward credentials on redirects or use browser cookies.
                with requests.get(self.base_url + path,
                                  params={'shop_id': self.shop_id, 'device_id': device_id, **params},
                                  headers={'authorization': self.authorization, 'Accept': 'application/json'},
                                  timeout=(3, 5), allow_redirects=False, stream=True) as response:
                    if response.status_code in (502, 503, 504) and attempt == 0:
                        continue
                    if response.status_code != 200:
                        raise ProviderError('设备服务暂不可用，请稍后同步。')
                    chunks, size, started = [], 0, time.monotonic()
                    for chunk in response.iter_content(65536):
                        size += len(chunk)
                        if size > 4_000_000 or time.monotonic() - started > 8:
                            raise ProviderError('设备响应过大或超时，本次未更新库存。')
                        chunks.append(chunk)
                    import json
                    data = json.loads(b''.join(chunks))
                if not isinstance(data, dict):
                    raise ProviderError('设备响应格式不正确。')
                if data.get('code') == 401:
                    raise ProviderError('设备服务未授权，请检查或更新连接凭据。')
                if data.get('code') != 200:
                    raise ProviderError('设备服务返回业务错误，本次未更新库存。')
                return data.get('data')
            except (requests.RequestException, ValueError):
                if attempt == 1:
                    raise ProviderError('设备查询失败，请检查连接后重试。') from None
        raise ProviderError('设备查询失败。')

    def lanes(self, device_id):
        return self.get('/shop/goods/list', device_id)

    def config(self, device_id):
        return self.get('/mp/common/getDeviceInfo', device_id)

    def detail(self, device_id, goods_id):
        return self.get('/Mp/Product/getDeviceGoodsInfo', device_id, goods_id=goods_id)

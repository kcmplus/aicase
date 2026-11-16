"""Exercise the merged editor against disposable Django data, never a real device."""
import json
import os
import subprocess
from v35_runtime import IsolatedRuntime, ROOT

FIXTURES = r'''
import hashlib, json, uuid
from io import BytesIO
from PIL import Image, ImageDraw
from django.core.management import call_command
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils import timezone
from management_api.models import (PhoneModel, DeviceProviderConnection, Device, SupplierProduct,
    DeviceProduct, PhoneColor, PhoneColorResource, PrintOrder)
from management_api.store_catalog import stock_template
call_command('seed_catalog', verbosity=0)
model = PhoneModel.objects.filter(active=True).order_by('pk').first()
connection = DeviceProviderConnection.objects.create(name='Synthetic preview only', shop_id='999', base_url='https://invalid.example')
device = Device.objects.create(pk=1, connection=connection, vendor_device_id='101', name='Synthetic preview station', provider_profile={'coordinates': {'latitude': 23, 'longitude': 113, 'coordinate_type': 'WGS84'}})
image = Image.new('RGBA', (320,640), (220,220,230,255))
ImageDraw.Draw(image).rectangle((20,70,300,620), fill=(0,0,0,0))
buf = BytesIO(); image.save(buf, format='PNG'); raw=buf.getvalue()
overlay=default_storage.save('supplier-templates/'+'a'*64+'-overlay.png',ContentFile(raw))
mask_image=Image.new('RGBA',(320,640),(0,0,0,0))
ImageDraw.Draw(mask_image).rectangle((20,70,300,620),fill=(255,255,255,255))
mask_buf=BytesIO(); mask_image.save(mask_buf,format='PNG'); mask_raw=mask_buf.getvalue()
mask=default_storage.save('supplier-templates/'+'b'*64+'-mask.png',ContentFile(mask_raw))
for number, material in enumerate(['普通款','磁吸款'],1):
    product=SupplierProduct.objects.create(connection=connection,goods_id=str(number),product_id=str(number),phone_model=model,active=True,specs=[{'spec_name':'版本','spec_value':material}])
    stock=DeviceProduct.objects.create(device=device,product=product,stock=3 if number==1 else 0,observed_at=timezone.now(),template_url='https://invalid.example/template.png',template_imported_url='https://invalid.example/template.png',template_image=overlay,template_mask=mask,template_width=320,template_height=640)
    if number==1: standard=stock
color=PhoneColor.objects.create(phone_model=model,code='synthetic-blue',name='合成蓝 / Synthetic blue',rgb={'r':32,'g':100,'b':200},active=True)
prefix='phone-colors/'+uuid.uuid4().hex
resource=PhoneColorResource.objects.create(color=color,version=1,template_id=stock_template(standard)['id'],width=320,height=640,overlay=default_storage.save(prefix+'/overlay.png',ContentFile(raw)),mask=default_storage.save(prefix+'/mask.png',ContentFile(mask_raw)),overlay_sha256=hashlib.sha256(raw).hexdigest(),mask_sha256=hashlib.sha256(mask_raw).hexdigest(),verified_at=timezone.now())
color.current_resource=resource; color.save()
snapshot={'version':2,'code':'POP-C-0123456789ABCDEF','source':'collection','designId':'bloom','model':model.name,'caseMaterial':'standard','phoneTemplateId':stock_template(standard)['id'],'_template':stock_template(standard),'_inventory_item':standard.pk,'photo':'','effect':'original','intensity':65,'zoom':100,'x':50,'y':50}
order=PrintOrder.objects.create(owner_hash=hashlib.sha256(('a'*64).encode()).hexdigest(),mode='free_test',status='paid',paid_at=timezone.now(),fulfillment_type='pickup',amount='0.00',model_name=model.name,case_material='standard',snapshot=snapshot)
print(json.dumps({'model':model.name,'order':str(order.reference)}))
'''


def main():
    # Each viewport represents a separate browsing session. Fresh local services
    # prevent repeated reloads from sharing the API's per-IP rate-limit bucket.
    # Production throttles stay enabled and unchanged during every scenario.
    for width in (320, 390, 768, 1440):
        with IsolatedRuntime() as runtime:
            result = subprocess.run([str(ROOT/'backend/.venv/bin/python'), 'backend/manage.py', 'shell', '-c', FIXTURES],
                cwd=ROOT, env=runtime.env, capture_output=True, text=True)
            if result.returncode:
                raise RuntimeError(result.stderr)
            fixtures = json.loads(result.stdout.splitlines()[-1])
            env = {'PATH': os.environ['PATH'], 'PREVIEW_URL': runtime.h5_origin,
                   'TEST_MODEL': fixtures['model'], 'TEST_ORDER': fixtures['order'],
                   'TEST_VIEWPORT_WIDTH': str(width)}
            for key in ('PLAYWRIGHT_MODULE', 'CHROMIUM_PATH'):
                if key in os.environ:
                    env[key] = os.environ[key]
            scripts = ['frontend/tests/ui-v35-integration-browser.mjs']
            if width == 1440:
                scripts.append('frontend/tests/preview-fit-browser.mjs')
            for script in scripts:
                subprocess.run(['node', script], cwd=ROOT, env=env, check=True, timeout=180)


if __name__ == '__main__':
    main()

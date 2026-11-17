from importlib import import_module
from io import StringIO
from django.apps import apps
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from .models import Brand, PhoneModel, DeviceProviderConnection, Device, SupplierProduct, DeviceProduct, PrintOrder
from .store_catalog import store_models, stock_template
from .orders import Snapshot
from .case_materials import material_from_specs


class CaseMaterialTests(TestCase):
    def setUp(self):
        call_command('seed_catalog', stdout=StringIO())
        brand=Brand.objects.get(code='apple')
        self.model=PhoneModel.objects.create(code='material-phone',name='iPhone Material',brand=brand)
        connection=DeviceProviderConnection.objects.create(name='Vendor',shop_id='351',base_url='https://api.autovendpro.com')
        self.device=Device.objects.create(connection=connection,vendor_device_id='789',name='Station',provider_profile={'coordinates':{'latitude':23,'longitude':113,'coordinate_type':'WGS84'}})
        self.stocks={}
        for index,(material,label) in enumerate([('standard','普通款'),('magnetic','磁吸款')],1):
            product=SupplierProduct.objects.create(connection=connection,goods_id=str(index),product_id=str(index),phone_model=self.model,active=True,specs=[{'spec_name':'版本','spec_value':label}])
            self.stocks[material]=DeviceProduct.objects.create(device=self.device,product=product,stock=index*3,observed_at=timezone.now(),template_url='https://example.com/template.png',template_imported_url='https://example.com/template.png',template_image='a.png',template_mask='b.png',template_width=600,template_height=1200)

    def test_style_is_not_inferred_from_name_missing_or_conflicting_specs(self):
        self.assertEqual(material_from_specs([]),'')
        self.assertEqual(material_from_specs([{'spec_name':'型号','spec_value':'磁吸款'}]),'')
        self.assertEqual(material_from_specs([{'spec_name':'版本','spec_value':'普通款'},{'spec_name':'手机壳物料','spec_value':'磁吸款'}]),'')

    def test_device_keeps_one_phone_with_separate_style_templates_and_disables_missing_stock(self):
        data=store_models({'device_id':'789','shop_id':'351'})
        self.assertEqual(len(data['models']),1)
        styles=data['models'][0]['styles']
        self.assertEqual([s['quantity'] for s in styles],[3,6])
        self.assertNotEqual(styles[0]['inventoryItemId'],styles[1]['inventoryItemId'])
        self.stocks['magnetic'].stock=0;self.stocks['magnetic'].save()
        scoped=store_models({'device_id':'789','shop_id':'351'})['models'][0]['styles']
        self.assertTrue(scoped[0]['available']);self.assertFalse(scoped[1]['available'])
        unscoped=next(m for m in store_models({})['models'] if m['name']==self.model.name)
        self.assertTrue(all(s['available'] for s in unscoped['styles']))
        self.stocks['magnetic'].stock=6;self.stocks['magnetic'].template_mask='';self.stocks['magnetic'].save()
        self.assertFalse(store_models({'device_id':'789','shop_id':'351'})['models'][0]['styles'][1]['available'])

    def test_stations_never_sum_different_styles_and_require_selection(self):
        for material,quantity in [('standard',3),('magnetic',6)]:
            response=self.client.get('/api/v1/store/print-stations/',{'model':self.model.name,'case_material':material})
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.data['results'][0]['quantity'],quantity)
            self.assertEqual(response.data['case_material'],material)
        self.assertEqual(self.client.get('/api/v1/store/print-stations/',{'model':self.model.name}).data['results'],[])
        self.assertEqual(self.client.get('/api/v1/store/print-stations/',{'model':self.model.name,'case_material':'other'}).status_code,400)

    def test_checkout_freezes_style_and_rejects_cross_style_template(self):
        snapshot={'version':2,'code':'POP-C-0123456789ABCDEF','source':'collection','designId':'bloom','model':self.model.name,'phoneTemplateId':stock_template(self.stocks['magnetic'])['id'],'caseMaterial':'magnetic','photo':'','effect':'original','intensity':65,'zoom':100,'x':50,'y':50}
        valid=Snapshot(data=snapshot);self.assertTrue(valid.is_valid(),valid.errors)
        self.assertEqual(valid.validated_data['caseMaterial'],'magnetic')
        wrong=Snapshot(data={**snapshot,'caseMaterial':'standard'});self.assertFalse(wrong.is_valid())
        legacy={**snapshot};legacy.pop('caseMaterial')
        previous=Snapshot(data=legacy);self.assertTrue(previous.is_valid());self.assertEqual(previous.validated_data['caseMaterial'],'magnetic')

    def test_migration_only_backfills_known_styles_and_preserves_frozen_order(self):
        original={'_inventory_item':self.stocks['magnetic'].pk,'photo':'private-image-placeholder'}
        order=PrintOrder.objects.create(model_name=self.model.name,amount='1.00',snapshot=original)
        unknown=PrintOrder.objects.create(model_name=self.model.name,amount='1.00',snapshot={})
        import_module('management_api.migrations.0033_order_case_material').preserve_order_styles(apps,None)
        order.refresh_from_db();unknown.refresh_from_db()
        self.assertEqual(order.case_material,'magnetic');self.assertEqual(order.snapshot,original)
        self.assertEqual(unknown.case_material,'')

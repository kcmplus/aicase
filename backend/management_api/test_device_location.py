from io import StringIO
from unittest.mock import patch, MagicMock
from django.test import TestCase, override_settings
from django.core.management import call_command, CommandError
from django.contrib.auth.models import User, Permission
from django.utils import timezone
from rest_framework.test import APIClient
from .device_discovery import discover_devices
from .device_provider import ProviderError
from .device_location import coordinate_pair, display_identity
from .device_info import public_device_identity
from .models import Device, DeviceProviderConnection


class DeviceLocationTests(TestCase):
    def setUp(self):
        self.connection = DeviceProviderConnection.objects.create(name='test', shop_id='351', base_url='https://api.autovendpro.com')
        self.device = Device.objects.create(connection=self.connection, vendor_device_id='789', name='Manual', location_note='Manual address', installation_note='Level 1')
        self.row = {'id':789, 'shop_id':351, 'device_name':'Supplier', 'device_num':'WM-789', 'address':'Public address',
                    'latitude':'23.109611405810412', 'longitude':'113.31919351869149', 'device_password':'NEVER COPY', 'contact_tel':'PRIVATE'}

    def sync(self, row=None):
        with patch('management_api.device_discovery.DeviceProvider') as provider:
            provider.return_value.devices.return_value = {'page':1,'totalNum':1,'totalPages':1,'list':[self.row if row is None else row]}
            result = discover_devices(self.connection)
        self.device.refresh_from_db()
        return result

    def test_manual_overrides_and_raw_precision_survive_repeated_sync(self):
        self.sync(); self.sync()
        identity = public_device_identity(self.device)
        self.assertEqual(identity['name'], 'Manual')
        self.assertEqual(identity['location'], 'Manual address · Level 1')
        self.assertIsNone(identity['coordinates'])
        self.assertEqual(self.device.provider_profile['coordinates']['latitude'], self.row['latitude'])
        self.assertNotIn('NEVER COPY', str(self.device.provider_profile))
        self.assertNotIn('PRIVATE', str(identity))
        self.device.name_source = self.device.location_source = 'supplier'
        self.device.supplier_coordinate_type = 'WGS84'
        self.device.save()
        self.sync({**self.row, 'device_name':'Updated', 'address':'Updated address'})
        identity = public_device_identity(self.device)
        self.assertEqual((identity['name'],identity['location']), ('Updated','Updated address · Level 1'))
        self.assertEqual(identity['coordinates']['coordinate_type'], 'WGS84')
        self.assertEqual(identity['coordinates']['source'], 'device_configuration')
        self.assertEqual((self.device.name,self.device.location_note), ('Manual','Manual address'))

    def test_blank_address_and_invalid_coordinates_do_not_clear_previous_values_or_offer_navigation(self):
        self.device.supplier_coordinate_type='WGS84'; self.device.save()
        self.sync()
        previous_time = self.device.provider_profile['coordinates']['observed_at']
        self.sync({**self.row,'address':None,'latitude':'NaN'})
        self.assertEqual(self.device.provider_profile['address'], 'Public address')
        self.assertEqual(self.device.provider_profile['coordinates']['latitude'],self.row['latitude'])
        self.assertEqual(self.device.provider_profile['coordinates']['observed_at'],previous_time)
        self.assertIn('address_warning',self.device.provider_profile)
        self.assertIsNone(display_identity(self.device)['coordinates'])
        self.sync()
        self.assertIsNotNone(display_identity(self.device)['coordinates'])
        self.assertNotIn('address_warning',self.device.provider_profile)

    def test_explicit_coordinate_type_conflict_and_unknown_types_fail_closed(self):
        self.device.supplier_coordinate_type='WGS84';self.device.save()
        for kind in ['GCJ02','BD09','something-unknown',42]:
            self.sync({**self.row,'coordinate_type':kind})
            self.assertIsNone(display_identity(self.device)['coordinates'])
        self.sync({**self.row,'coordinate_type':'wgs-84'})
        self.assertEqual(display_identity(self.device)['coordinates']['source'],'supplier')
        for lat,lon in [(None,1),('',1),(True,1),('Infinity',1),(91,0),(0,-181),([],1),('1_2',1),('１２',1)]:
            with self.subTest(lat=lat,lon=lon),self.assertRaises(ValueError):coordinate_pair(lat,lon)
        self.assertEqual(coordinate_pair(0,0),{'latitude':'0','longitude':'0'})
        self.assertEqual(coordinate_pair(-33.9,151.2)['latitude'],'-33.9')

    def test_new_device_follows_supplier_but_is_not_enabled(self):
        self.sync({**self.row,'id':790})
        new = Device.objects.get(vendor_device_id='790')
        self.assertEqual((new.name_source,new.location_source),('supplier','supplier'))
        self.assertFalse(new.active)
        self.assertEqual(new.supplier_coordinate_type,'')

    def test_failed_sync_retains_snapshot_and_records_sanitized_failure(self):
        self.sync();before=self.device.provider_profile.copy()
        with patch('management_api.device_discovery.DeviceProvider',side_effect=RuntimeError('SECRET')):
            with self.assertRaises(ProviderError):discover_devices(self.connection)
        self.device.refresh_from_db();self.connection.refresh_from_db()
        self.assertEqual(self.device.provider_profile,before)
        self.assertEqual(self.connection.profile_sync_status,'failed')
        self.assertNotIn('SECRET',self.connection.profile_sync_message)
        self.assertIsNone(self.connection.profile_sync_token)
        self.assertIsNotNone(self.connection.profile_sync_at)

    def test_overlapping_sync_and_connection_change_cannot_publish(self):
        import uuid
        self.connection.profile_sync_token=uuid.uuid4();self.connection.profile_sync_started_at=timezone.now();self.connection.save()
        with patch('management_api.device_discovery.DeviceProvider') as provider,self.assertRaises(ProviderError):
            discover_devices(self.connection)
        provider.assert_not_called()
        self.connection.profile_sync_token=None;self.connection.save()
        def change(**kwargs):
            DeviceProviderConnection.objects.filter(pk=self.connection.pk).update(revision=2)
            return {'page':1,'totalNum':1,'totalPages':1,'list':[self.row]}
        with patch('management_api.device_discovery.DeviceProvider') as provider:
            provider.return_value.devices.side_effect=change
            with self.assertRaises(ProviderError):discover_devices(self.connection)
        self.device.refresh_from_db();self.assertEqual(self.device.provider_profile,{})

    def test_profile_endpoint_requires_sync_permission_and_configuration_uses_revision(self):
        user=User.objects.create_user('operator',is_staff=True)
        client=APIClient();client.force_authenticate(user)
        url=f'/api/v1/admin/devices/{self.device.pk}/sync-profile/'
        self.assertEqual(client.post(url,{},format='json').status_code,403)
        user.user_permissions.add(Permission.objects.get(codename='sync_device'))
        client.force_authenticate(User.objects.get(pk=user.pk))
        with patch('management_api.device_discovery.discover_devices',return_value={'message':'done'}) as sync:
            self.assertEqual(client.post(url,{},format='json').status_code,200)
            self.assertEqual(sync.call_args.args[0].pk,self.connection.pk)
        from .inventory import DeviceSerializer
        data={'revision':1,'supplier_coordinate_type':'WGS84','location_source':'supplier'}
        serializer=DeviceSerializer(self.device,data=data,partial=True)
        self.assertTrue(serializer.is_valid(),serializer.errors);serializer.save()
        stale=DeviceSerializer(self.device,data=data,partial=True);self.assertTrue(stale.is_valid())
        from rest_framework.exceptions import ValidationError
        with self.assertRaises(ValidationError):stale.save()

    def test_scheduler_fetches_once_per_connection_and_inventory_runs_after_profile_failure(self):
        Device.objects.create(connection=self.connection,vendor_device_id='790',name='Second')
        command='management_api.connection_sync'
        with patch(command+'.discover_devices',side_effect=ProviderError('Unavailable')) as discover,patch(command+'.sync_device',return_value=MagicMock(status='success',message='ok')) as stock:
            with self.assertRaises(CommandError):
                call_command('sync_device_inventory',all=True,stdout=StringIO(),stderr=StringIO())
        self.assertEqual(discover.call_count,1);self.assertEqual(stock.call_count,2)
        with override_settings(DIRECT_DEBUG_ENABLED=True),patch(command+'.discover_devices') as discover,patch(command+'.sync_device') as stock:
            call_command('sync_device_inventory',all=True,stdout=StringIO())
        discover.assert_not_called();stock.assert_not_called()

    def test_migration_only_enables_supplier_address_for_previously_empty_fields(self):
        from importlib import import_module
        from django.apps import apps
        other=Device.objects.create(connection=self.connection,vendor_device_id='791',name='Existing name')
        import_module('management_api.migrations.0032_device_location_sync').preserve_manual_settings(apps,None)
        self.device.refresh_from_db();other.refresh_from_db()
        self.assertEqual(self.device.location_source,'manual')
        self.assertEqual(other.location_source,'supplier')
        self.assertEqual(other.name_source,'manual')

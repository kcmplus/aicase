from io import StringIO
from unittest.mock import patch
from django.core.management import call_command, CommandError
from django.test import SimpleTestCase


class InventoryWatchTests(SimpleTestCase):
    def test_worker_retries_after_failed_cycle_and_stops_cleanly(self):
        command='management_api.management.commands.sync_device_inventory'
        with patch(command+'.Command.sync_once', side_effect=[CommandError('同步失败'), None]) as sync:
            with patch(command+'.time.sleep', side_effect=[None, KeyboardInterrupt]) as sleep:
                out, err=StringIO(), StringIO()
                call_command('sync_device_inventory', all=True, watch=True, interval=300, stdout=out, stderr=err)
        self.assertEqual(sync.call_count, 2)
        self.assertEqual(sleep.call_args.args, (300,))
        self.assertIn('同步失败', err.getvalue())
        self.assertIn('已停止', out.getvalue())

    def test_worker_interval_cannot_exceed_snapshot_lifetime(self):
        for interval in (0, 29, 901):
            with self.assertRaises(CommandError):
                call_command('sync_device_inventory', all=True, watch=True, interval=interval)

    def test_scheduled_empty_catalog_is_allowed_but_missing_specific_device_is_not(self):
        command='management_api.management.commands.sync_device_inventory'
        with patch(command+'.DeviceProviderConnection.objects.filter') as connections:
            connections.return_value.__iter__.return_value=iter([])
            connections.return_value.filter.return_value.__iter__.return_value=iter([])
            call_command('sync_device_inventory', all=True, allow_empty=True)
            with self.assertRaises(CommandError):
                call_command('sync_device_inventory', all=True)
            with self.assertRaises(CommandError):
                call_command('sync_device_inventory', device=999, allow_empty=True)

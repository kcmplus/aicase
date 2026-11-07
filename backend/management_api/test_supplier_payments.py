from unittest.mock import patch, Mock

import requests
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from . import test_supplier_orders as supplier_tests
from .device_provider import ProviderError
from .models import PrintOrder, PrintRefund, SupplierOrder
from .supplier_payments import query_order, sync_order, sync_pending, refresh_inventory


@override_settings(SUPPLIER_ORDER_ENABLED=True, SUPPLIER_PAYMENT_ENABLED=True)
class SupplierPaymentTests(TestCase):
    setUp = supplier_tests.SupplierOrderTests.setUp
    post = supplier_tests.SupplierOrderTests.post
    bind = supplier_tests.SupplierOrderTests.bind
    image = supplier_tests.SupplierOrderTests.image
    prepare = supplier_tests.SupplierOrderTests.prepare
    pay = supplier_tests.SupplierOrderTests.pay
    provider = supplier_tests.SupplierOrderTests.provider

    def ready(self):
        row = self.prepare()
        self.pay()
        row.state, row.trade_no, row.vendor_id = 'submitted', 'TRADE1', '123'
        row.save()
        return row

    def record(self, amount='0.00', **extra):
        return {'id': 123, 'trade_no': 'TRADE1', 'device_id': '401', 'shop_id': '146', 'goods_id': 17,
                'pay_money': amount, 'currency': 'USD', 'pay_status': 0, 'print_status': 0,
                'shipment_status': 0, 'status': 2, 'is_refund': 0, 'is_deleted': 0, 'phase': 'unknown', **extra}

    @patch('management_api.supplier_payments.requests.post')
    @patch('management_api.supplier_payments.query_order')
    def test_confirm_records_frozen_amount_once_and_reconciles_by_exact_order(self, query, remote):
        row = self.ready()
        query.side_effect = [self.record(), self.record('1.00')]
        remote.return_value = self.provider({'code': 200, 'data': {}})
        response = self.post('confirm-print/', {'confirm': True})
        self.assertEqual(response.status_code, 200, response.content)
        remote.assert_called_once()
        args, kwargs = remote.call_args
        self.assertEqual(args[0], 'https://shop.widermatrix.cn/shop/order/updatePayStatus')
        self.assertEqual(kwargs['json'], {'trade_no': 'TRADE1', 'pay_money': '1.00'})
        self.assertEqual(kwargs['headers']['authorization'], 'test-vendor-authorization')
        self.assertFalse(kwargs['allow_redirects'])
        row.refresh_from_db()
        self.assertIsNotNone(row.print_confirmed_at)
        self.assertEqual(row.release_state, 'observed')
        self.assertTrue(row.cloud_status['payment_recorded'])
        self.assertEqual(row.cloud_status['phase'], 'unknown')
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'paid')  # Not a fabricated physical print.
        self.assertEqual(self.post('confirm-print/', {'confirm': True}).status_code, 200)
        remote.assert_called_once()
        self.assertFalse(response.json()['can_confirm_print'])

    @patch('management_api.supplier_payments.requests.post')
    @patch('management_api.supplier_payments.query_order')
    def test_lost_write_result_is_never_repeated_and_read_later_recovers_it(self, query, remote):
        row = self.ready()
        query.return_value = self.record()
        remote.side_effect = requests.Timeout()
        self.assertEqual(self.post('confirm-print/', {'confirm': True}).status_code, 200)
        row.refresh_from_db()
        self.assertEqual(row.release_state, 'unknown')
        self.post('confirm-print/', {'confirm': True})
        remote.assert_called_once()
        query.return_value = self.record('1.00')
        self.assertTrue(sync_order(row.pk, force=True))
        row.refresh_from_db()
        self.assertEqual(row.release_state, 'observed')
        remote.assert_called_once()

    @patch('management_api.supplier_payments.requests.post')
    @patch('management_api.supplier_payments.query_order')
    def test_success_ack_without_payment_record_is_not_a_print_success(self, query, remote):
        row = self.ready()
        query.return_value = self.record()
        remote.return_value = self.provider({'code': 200, 'data': {}})
        self.post('confirm-print/', {'confirm': True})
        row.refresh_from_db()
        self.assertEqual(row.release_state, 'submitted')
        self.assertFalse(row.cloud_status['payment_recorded'])
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'paid')

    @patch('management_api.supplier_payments.requests.post')
    @patch('management_api.supplier_payments.query_order')
    def test_already_recorded_amount_is_not_overwritten(self, query, remote):
        row = self.ready()
        query.return_value = self.record('1.00')
        self.assertEqual(self.post('confirm-print/', {'confirm': True}).status_code, 200)
        row.refresh_from_db()
        self.assertEqual(row.release_state, 'observed')
        remote.assert_not_called()

    @patch('management_api.supplier_payments.requests.post')
    @patch('management_api.supplier_payments.query_order')
    def test_amount_currency_refund_execution_and_fresh_stock_checked_before_claim(self, query, remote):
        row = self.ready()
        for record in [self.record('2.00'), self.record(currency='THB'), self.record(currency=''),
                       self.record(is_refund=1), self.record(status=4), self.record(is_deleted=1), self.record(print_status=91),
                       self.record(shipment_status=83)]:
            query.return_value = record
            self.assertEqual(self.post('confirm-print/', {'confirm': True}).status_code, 409)
            SupplierOrder.objects.filter(pk=row.pk).update(cloud_status={})
        query.return_value = self.record()
        self.stock.stock = 0
        self.stock.save()
        self.assertEqual(self.post('confirm-print/', {'confirm': True}).status_code, 409)
        row.refresh_from_db()
        self.assertIsNone(row.print_confirmed_at)
        remote.assert_not_called()

    @patch('management_api.supplier_payments.requests.post')
    @patch('management_api.supplier_payments.query_order', side_effect=ProviderError('unavailable'))
    def test_failed_preflight_makes_no_claim_and_cannot_trigger_payment(self, query, remote):
        row = self.ready()
        self.assertEqual(self.post('confirm-print/', {'confirm': True}).status_code, 503)
        row.refresh_from_db()
        self.assertEqual(row.release_state, 'idle')
        self.assertIsNone(row.print_confirmed_at)
        remote.assert_not_called()

    @patch('management_api.supplier_payments.requests.post')
    @patch('management_api.supplier_payments.query_order')
    def test_client_cannot_override_recorded_amount_or_supplier_identity(self, query, remote):
        self.ready()
        for extra in [{'pay_money': '0.01'}, {'trade_no': 'OTHER'}, {'pay_type': 'free'}]:
            self.assertEqual(self.post('confirm-print/', {'confirm': True, **extra}).status_code, 400)
        query.assert_not_called()
        remote.assert_not_called()

    @patch('management_api.supplier_payments.requests.post')
    @patch('management_api.supplier_payments.query_order')
    def test_connection_rotation_during_preflight_requires_a_new_read_not_a_cross_account_write(self, query, remote):
        row = self.ready()
        def rotate(*args):
            self.connection.revision += 1
            self.connection.save()
            return self.record()
        query.side_effect = rotate
        self.assertEqual(self.post('confirm-print/', {'confirm': True}).status_code, 409)
        row.refresh_from_db()
        self.assertIsNone(row.print_confirmed_at)
        remote.assert_not_called()

    @patch('management_api.supplier_payments.requests.post')
    @patch('management_api.supplier_payments.query_order')
    def test_refund_between_preflight_and_claim_blocks_write(self, query, remote):
        row = self.ready()
        def refund(*args):
            admin = get_user_model().objects.create_user('race-refund')
            PrintRefund.objects.create(order=self.order, amount=1, currency='USD', reason='test', requested_by=admin)
            return self.record()
        query.side_effect = refund
        self.assertEqual(self.post('confirm-print/', {'confirm': True}).status_code, 409)
        row.refresh_from_db()
        self.assertIsNone(row.print_confirmed_at)
        remote.assert_not_called()

    @patch('management_api.supplier_payments.requests.post')
    @patch('management_api.supplier_payments.query_order')
    def test_overlapping_confirmation_and_refund_cannot_race_durable_claim(self, query, remote):
        row = self.ready()
        query.side_effect = [self.record(), self.record('1.00')]
        def overlap(*args, **kwargs):
            row.refresh_from_db()
            self.assertEqual(row.release_state, 'claimed')
            self.assertEqual(self.post('confirm-print/', {'confirm': True}).status_code, 200)
            from .refunds import printing_in_flight
            self.assertTrue(printing_in_flight(self.order))
            return self.provider({'code': 200, 'data': {}})
        remote.side_effect = overlap
        self.assertEqual(self.post('confirm-print/', {'confirm': True}).status_code, 200)
        remote.assert_called_once()

    @patch('management_api.supplier_payments.DeviceProvider.get')
    def test_list_lookup_matches_all_available_ids_and_never_uses_first_order(self, get):
        row = self.ready()
        other = self.record(trade_no='OTHER')
        get.return_value = {'list': [other, self.record()], 'items': [other, self.record()]}
        self.assertEqual(query_order(row)['trade_no'], 'TRADE1')
        get.assert_called_with('/shop/order/list', device_id='401', trade_no='TRADE1', page=1, limit=10)
        for extra in [{'id': 999}, {'device_id': '402'}, {'shop_id': '147'}, {'goods_id': 999},
                      {'business_number': 'OTHER'}, {'currency': 'string'}, {'pay_money': 'NaN'}]:
            get.return_value = {'list': [self.record(**extra)]}
            with self.assertRaises(ValueError):
                query_order(row)
        get.return_value = {'list': [self.record(), self.record()]}
        with self.assertRaises(ValueError):
            query_order(row)

    @patch('management_api.supplier_payments.DeviceProvider.get')
    def test_empty_vendor_currency_uses_explicit_usd_merchant_setting_without_conversion(self, get):
        row = self.ready()
        get.return_value = {'list': [self.record('0.00', currency='')]}
        observed = query_order(row)
        self.assertEqual(observed['currency'], 'USD')
        self.assertEqual(observed['currency_source'], 'merchant_configuration')
        self.assertEqual(observed['pay_money'], '0.00')
        get.return_value = {'list': [self.record('0.00', currency='THB')]}
        self.assertEqual(query_order(row)['currency'], 'THB')
        get.return_value = {'list': [self.record()], 'items': [self.record('1.00')]}
        with self.assertRaises(ValueError):
            query_order(row)

    @patch('management_api.supplier_payments.DeviceProvider.get')
    def test_dollar_symbol_requires_explicit_usd_configuration(self, get):
        row = self.ready()
        get.return_value = {'list': [self.record(currency='$')], 'items': [self.record(currency='$')]}
        observed = query_order(row)
        self.assertEqual(observed['currency'], 'USD')
        self.assertEqual(observed['currency_source'], 'merchant_configuration_symbol')
        self.assertEqual(observed['pay_money'], '0.00')
        for configured in ('', 'CAD', 'AUD', 'THB'):
            row.device.connection.payment_currency = configured
            with self.subTest(configured=configured), self.assertRaises(ValueError):
                query_order(row)
        row.device.connection.payment_currency = 'USD'
        for supplied in ('US$', '€', 'usd'):
            get.return_value = {'list': [self.record(currency=supplied)]}
            with self.subTest(supplied=supplied), self.assertRaises(ValueError):
                query_order(row)
        get.return_value = {'list': [self.record(currency='$')], 'items': [self.record(currency='USD')]}
        with self.assertRaises(ValueError):
            query_order(row)

    @patch('management_api.supplier_payments.requests.post')
    @patch('management_api.supplier_payments.DeviceProvider.get')
    def test_zero_print_with_dollar_symbol_still_claims_once_and_verifies_paid_flag(self, get, remote):
        row = self.ready_free()
        get.side_effect = [
            {'list': [self.record(currency='$')]},
            {'list': [self.record(currency='$', pay_status=1)]},
        ]
        remote.return_value = self.provider({'code': 200, 'data': None})
        self.assertEqual(self.post('confirm-print/', {'confirm': True}).status_code, 200)
        self.assertEqual(self.post('confirm-print/', {'confirm': True}).status_code, 200)
        remote.assert_called_once()
        self.assertEqual(remote.call_args.kwargs['json']['pay_money'], '0.00')
        row.refresh_from_db()
        self.assertEqual(row.release_state, 'observed')
        self.assertTrue(row.cloud_status['payment_recorded'])

    def ready_free(self):
        row=self.ready()
        self.order.mode='free_test';self.order.amount=0;self.order.save()
        return row

    @patch('management_api.supplier_payments.requests.post')
    @patch('management_api.supplier_payments.query_order')
    def test_zero_payment_requires_paid_flag_and_handles_null_success_data(self,query,remote):
        row=self.ready_free()
        query.side_effect=[self.record(),self.record(pay_status=1)]
        remote.return_value=self.provider({'code':200,'message':'success','data':None})
        response=self.post('confirm-print/',{'confirm':True})
        self.assertEqual(response.status_code,200,response.content)
        self.assertEqual(remote.call_args.kwargs['json'],{'trade_no':'TRADE1','pay_money':'0.00'})
        row.refresh_from_db()
        self.assertTrue(row.cloud_status['payment_recorded'])
        self.assertEqual(row.release_state,'observed')
        self.assertEqual(self.post('confirm-print/',{'confirm':True}).status_code,200)
        remote.assert_called_once()
        self.order.refresh_from_db();self.assertEqual(self.order.status,'paid')

    @patch('management_api.supplier_payments.requests.post')
    @patch('management_api.supplier_payments.query_order')
    def test_existing_zero_payment_is_observed_without_writing_again(self,query,remote):
        row=self.ready_free();query.return_value=self.record(pay_status=1)
        response=self.post('confirm-print/',{'confirm':True})
        self.assertEqual(response.status_code,200,response.content)
        row.refresh_from_db();self.assertEqual(row.release_state,'observed')
        self.assertTrue(row.cloud_status['payment_recorded']);remote.assert_not_called()

    @patch('management_api.supplier_payments.requests.post',side_effect=requests.Timeout())
    @patch('management_api.supplier_payments.query_order')
    def test_zero_timeout_only_queries_until_paid_flag_is_observed(self,query,remote):
        row=self.ready_free();query.return_value=self.record()
        self.assertEqual(self.post('confirm-print/',{'confirm':True}).status_code,200)
        row.refresh_from_db();self.assertEqual(row.release_state,'unknown')
        self.assertFalse(row.cloud_status['payment_recorded'])
        self.assertEqual(self.post('confirm-print/',{'confirm':True}).status_code,200)
        remote.assert_called_once()
        query.return_value=self.record(pay_status=1)
        self.assertTrue(sync_order(row.pk,force=True))
        row.refresh_from_db();self.assertEqual(row.release_state,'observed')
        self.assertTrue(row.cloud_status['payment_recorded']);remote.assert_called_once()

    @patch('management_api.supplier_payments.requests.post')
    @patch('management_api.supplier_payments.query_order')
    def test_unknown_zero_payment_flag_cannot_authorize_or_overwrite_payment(self,query,remote):
        row=self.ready_free();query.return_value=self.record(pay_status=2)
        self.assertEqual(self.post('confirm-print/',{'confirm':True}).status_code,409)
        row.refresh_from_db();self.assertFalse(row.cloud_status['payment_recorded'])
        self.assertIsNone(row.print_confirmed_at);remote.assert_not_called()


    @override_settings(SUPPLIER_ORDER_STATUS_VERIFIED=True, SUPPLIER_ORDER_STATUS_MAP={'print': {'41': 'printing', '42': 'printed', '43': 'print_failed'},
                                                 'shipment': {'71': 'dispensed'}})
    @patch('management_api.supplier_payments.DeviceProvider.get')
    def test_only_explicitly_mapped_codes_advance_printing_and_dispensing_never_collection(self, get):
        row = self.ready()
        row.print_confirmed_at, row.release_state = timezone.now(), 'submitted'
        row.save()
        for fields, expected in [({'print_status': 999}, 'paid'), ({'print_status': 41}, 'printing'),
                                 ({'shipment_status': 71}, 'ready'), ({}, 'ready')]:
            get.return_value = {'list': [self.record('1.00', **fields)]}
            self.assertTrue(sync_order(row.pk, force=True))
            self.order.refresh_from_db()
            self.assertEqual(self.order.status, expected)
        row.refresh_from_db()
        self.assertEqual(row.cloud_status['phase'], 'dispensed')
        self.assertTrue(row.inventory_refresh_pending)
        self.assertIsNotNone(row.cloud_synced_at)
        get.return_value = {'list': [self.record('1.00', status=4, print_status=42, shipment_status=71)]}
        sync_order(row.pk, force=True)
        from .refunds import printing_in_flight
        self.assertFalse(printing_in_flight(self.order))  # Cancellation cannot erase proven physical dispensing.

    @patch('management_api.supplier_payments.query_order')
    def test_unavailable_status_read_preserves_last_success_and_polling_has_a_lease(self, query):
        row = self.ready()
        row.cloud_status = {'phase': 'printing', 'payment_recorded': True}
        row.cloud_synced_at = timezone.now()
        row.save()
        query.side_effect = ProviderError('offline')
        self.assertFalse(sync_order(row.pk))
        self.assertFalse(sync_order(row.pk))
        query.assert_called_once()
        row.refresh_from_db()
        self.assertEqual(row.cloud_status['phase'], 'printing')

    @patch('management_api.supplier_payments.query_order')
    def test_late_status_response_cannot_overwrite_a_newer_read(self, query):
        row = self.ready()
        def older(*args):
            SupplierOrder.objects.filter(pk=row.pk).update(cloud_checked_at=timezone.now(),
                cloud_status={'phase': 'dispensed', 'payment_recorded': True})
            return self.record('0.00')
        query.side_effect = older
        self.assertFalse(sync_order(row.pk, force=True))
        row.refresh_from_db()
        self.assertEqual(row.cloud_status['phase'], 'dispensed')

    @override_settings(SUPPLIER_ORDER_STATUS_VERIFIED=True, SUPPLIER_ORDER_STATUS_MAP={'print': {'41': 'printing', '43': 'print_failed'}})
    @patch('management_api.supplier_payments.DeviceProvider.get')
    def test_failed_and_resumed_physical_progress_changes_refund_guard_without_replaying(self, get):
        from .refunds import printing_in_flight
        row = self.ready()
        row.print_confirmed_at, row.release_state = timezone.now(), 'submitted'
        row.save()
        for status, blocked in [(43, False), (0, False), (41, True)]:
            get.return_value = {'list': [self.record('1.00', print_status=status)]}
            sync_order(row.pk, force=True)
            self.assertEqual(printing_in_flight(self.order), blocked)

    @override_settings(SUPPLIER_ORDER_STATUS_VERIFIED=False,
        SUPPLIER_ORDER_STATUS_MAP={'print': {'2': 'printed'}, 'shipment': {'2': 'dispensed'}})
    @patch('management_api.supplier_payments.DeviceProvider.get')
    def test_provisional_mapping_is_not_physical_proof_or_permission_to_refund(self, get):
        from .refunds import printing_in_flight
        row = self.ready()
        row.print_confirmed_at, row.release_state = timezone.now(), 'submitted'
        row.save()
        get.return_value = {'list': [self.record('1.00', print_status=2, shipment_status=2)]}
        self.assertTrue(sync_order(row.pk, force=True))
        row.refresh_from_db()
        self.assertEqual(row.cloud_status['phase'], 'dispensed')
        self.assertFalse(row.cloud_status['phase_verified'])
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'paid')
        self.assertTrue(printing_in_flight(self.order))

    @patch('management_api.supplier_payments.query_order')
    def test_payment_recorded_outside_our_claim_still_protects_an_inflight_job_from_refund(self, query):
        from .refunds import printing_in_flight
        row = self.ready()
        query.return_value = self.record('1.00')
        sync_order(row.pk, force=True)
        self.assertTrue(printing_in_flight(self.order))
        row.refresh_from_db()
        self.assertIsNone(row.print_confirmed_at)

    @override_settings(SUPPLIER_ORDER_STATUS_VERIFIED=False)
    @patch('management_api.supplier_payments.DeviceProvider.get')
    @patch('management_api.supplier_payments.requests.post')
    def test_confirmed_cancelled_status_blocks_release_and_preserves_customer_payment(self, remote, get):
        row = self.ready()
        get.return_value = {'list': [self.record('0.00', status=4)]}
        self.assertTrue(sync_order(row.pk, force=True))
        row.refresh_from_db()
        self.assertEqual(row.cloud_status['phase'], 'cancelled')
        self.assertTrue(row.cloud_status['phase_verified'])
        self.assertEqual(self.post('confirm-print/', {'confirm': True}).status_code, 409)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'paid')
        self.assertIsNone(row.print_confirmed_at)
        remote.assert_not_called()

    @patch('management_api.inventory_sync.sync_device')
    def test_status_refresh_coalesces_inventory_reads_per_device_and_never_decrements_locally(self, sync):
        row = self.ready()
        row.inventory_refresh_pending, row.cloud_synced_at = True, timezone.now()
        row.save()
        sync.return_value = Mock(status='success')
        refresh_inventory()
        refresh_inventory()
        sync.assert_called_once_with(self.device.pk)
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.stock, 3)
        row.refresh_from_db()
        self.assertFalse(row.inventory_refresh_pending)

    @patch('management_api.supplier_payments.requests.post')
    @patch('management_api.supplier_payments.query_order')
    def test_delivery_unpaid_refunded_and_other_owners_never_update_supplier_payment(self, query, remote):
        self.ready()
        for changes in [{'fulfillment_type': 'courier'}, {'fulfillment_type': 'air'},
                        {'fulfillment_type': 'unspecified'}, {'mode': 'airwallex_test'}, {'status': 'pending'}, {'amount': '0.00'}]:
            saved = {key: getattr(self.order, key) for key in changes}
            PrintOrder.objects.filter(pk=self.order.pk).update(**changes)
            self.assertEqual(self.post('confirm-print/', {'confirm': True}).status_code, 409)
            PrintOrder.objects.filter(pk=self.order.pk).update(**saved)
        response = self.client.post(self.url+'confirm-print/', {'confirm': True})
        self.assertEqual(response.status_code, 403)
        query.assert_not_called()
        remote.assert_not_called()


@override_settings(SUPPLIER_ORDER_ENABLED=True, SUPPLIER_PAYMENT_ENABLED=True)
class SupplierPaymentCommitTests(TransactionTestCase):
    setUp = supplier_tests.SupplierOrderTests.setUp
    post = supplier_tests.SupplierOrderTests.post
    bind = supplier_tests.SupplierOrderTests.bind
    image = supplier_tests.SupplierOrderTests.image
    prepare = supplier_tests.SupplierOrderTests.prepare
    pay = supplier_tests.SupplierOrderTests.pay
    provider = supplier_tests.SupplierOrderTests.provider
    ready = SupplierPaymentTests.ready
    record = SupplierPaymentTests.record

    @patch('management_api.supplier_payments.requests.post')
    @patch('management_api.supplier_payments.query_order')
    def test_claim_is_committed_before_network_write(self, query, remote):
        row = self.ready()
        query.side_effect = [self.record(), self.record('1.00')]
        def check(*args, **kwargs):
            self.assertFalse(connection.in_atomic_block)
            saved = SupplierOrder.objects.get(pk=row.pk)
            self.assertIsNotNone(saved.release_claim)
            self.assertEqual(saved.release_state, 'claimed')
            return self.provider({'code': 200, 'data': {}})
        remote.side_effect = check
        self.assertEqual(self.post('confirm-print/', {'confirm': True}).status_code, 200)

from django.core.management.base import BaseCommand
from management_api.models import SupplierOrder
from management_api.supplier_orders import dispatch_pending
from management_api.supplier_payments import sync_pending


class Command(BaseCommand):
    help = '推送已付款且已由顾客绑定设备的订单；结果不明的订单不重发。'

    def handle(self, *args, **options):
        count = dispatch_pending()
        observed = sync_pending()
        unknown = SupplierOrder.objects.filter(state='unknown').count()
        self.stdout.write(f'本轮已推送 {count} 单，更新供应商状态 {observed} 单，推单待核实 {unknown} 单。')

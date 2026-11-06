"""Delivery eligibility, independent of payment and supplier queue state."""
from .models import PrintOrder
from django.conf import settings

SHIPPING_UNAVAILABLE = 'Courier and air delivery are not available for checkout yet. Your design is saved; no payment has been taken.'


def require_pickup(order):
    from .orders import Conflict
    if order.fulfillment_type != PrintOrder.Fulfillment.PICKUP:
        raise Conflict('Confirm on-site pickup before using a print station. Delivery orders cannot be sent to a station.')


def require_checkout(order):
    from .orders import Conflict
    if order.fulfillment_type in (PrintOrder.Fulfillment.COURIER, PrintOrder.Fulfillment.AIR):
        raise Conflict(SHIPPING_UNAVAILABLE)
    require_pickup(order)


def cloud_release_available():
    # New cloud-only switch. The old terminal/IPC switch remains retired.
    return settings.SUPPLIER_ORDER_ENABLED and settings.SUPPLIER_PAYMENT_ENABLED

ZERO_PAYMENT_UNCONFIRMED = 'Zero-amount print release has not been confirmed by the supplier. Your order can be sent, but printing is not yet available.'

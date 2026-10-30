from django.db import migrations


class Migration(migrations.Migration):
    # Keep the already deployed email migration rooted at 0008. The payment,
    # relay and credit-ledger histories then converge without requiring an
    # already deployed dev database to have the payment migration applied.
    dependencies = [
        ("management_api", "0009_printorder_paid_at_printorder_payment_credentials_and_more"),
        ("management_api", "0011_ai_relay_provider"),
        ("management_api", "0013_credit_ledger"),
    ]

    operations = []

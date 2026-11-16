"""Join deployed dev and V35 migration histories without changing existing data."""
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("management_api", "0031_direct_debug_transport"),
        ("management_api", "0033_order_case_material"),
        ("management_api", "0034_phone_color_previews"),
    ]
    operations = []

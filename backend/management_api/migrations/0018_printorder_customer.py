import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('management_api', '0017_ai_image_retention')]
    operations = [
        # Old contact emails were unverified; never infer account ownership from them.
        migrations.AddField(model_name='printorder', name='customer', field=models.ForeignKey(
            to='management_api.customer', null=True, blank=True, editable=False,
            on_delete=django.db.models.deletion.SET_NULL, related_name='print_orders')),
    ]

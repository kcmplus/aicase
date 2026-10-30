from datetime import timedelta

from django.db import migrations, models
from django.utils import timezone


def preserve_existing_images(apps, schema_editor):
    # Give existing successful images a full 30 days from upgrade, without
    # reading blobs or unexpectedly deleting old customer results at deployment.
    renders = apps.get_model('management_api', 'AIRender').objects.using(schema_editor.connection.alias)
    renders.filter(status='ready', result_image__isnull=False).exclude(result_image=b'').update(
        image_expires_at=timezone.now() + timedelta(days=30))


class Migration(migrations.Migration):
    dependencies = [('management_api', '0016_ai_call_costs')]
    operations = [
        migrations.AddField(model_name='aiserviceconfig', name='image_retention_days',
                            field=models.PositiveSmallIntegerField(default=30)),
        migrations.AddField(model_name='airender', name='image_expires_at',
                            field=models.DateTimeField(null=True, editable=False, db_index=True)),
        migrations.AddField(model_name='airender', name='image_deleted_at',
                            field=models.DateTimeField(null=True, editable=False)),
        migrations.RunPython(preserve_existing_images, migrations.RunPython.noop),
    ]

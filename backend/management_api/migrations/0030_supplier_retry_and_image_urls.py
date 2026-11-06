import uuid
from django.db import migrations, models


def assign_tokens(apps, schema_editor):
    SupplierOrder = apps.get_model('management_api', 'SupplierOrder')
    for pk in SupplierOrder.objects.using(schema_editor.connection.alias).values_list('pk', flat=True).iterator():
        SupplierOrder.objects.using(schema_editor.connection.alias).filter(pk=pk).update(file_token=uuid.uuid4())


class Migration(migrations.Migration):
    dependencies = [('management_api', '0029_free_test_orders')]
    operations = [
        migrations.AlterField(model_name='supplierorder', name='state', field=models.CharField(max_length=20, default='draft', choices=[('draft', '待打印文件'), ('prepared', '待推送'), ('submitting', '正在推送'), ('submitted', '已推送'), ('rejected', '推送失败，待用户确认重试'), ('unknown', '推送结果待核实')])),
        migrations.AddField(model_name='supplierorder', name='file_token', field=models.UUIDField(null=True, unique=True, editable=False)),
        migrations.RunPython(assign_tokens, migrations.RunPython.noop),
        migrations.AlterField(model_name='supplierorder', name='file_token', field=models.UUIDField(default=uuid.uuid4, unique=True, editable=False)),
    ]

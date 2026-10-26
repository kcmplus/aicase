from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("management_api", "0003_printorder_mode_printorder_owner_hash_and_more")]
    operations = [
        migrations.AddField(
            model_name="phonemodel",
            name="adaptation_prompt",
            field=models.TextField(blank=True, max_length=4000),
        ),
    ]

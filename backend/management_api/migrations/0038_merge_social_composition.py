"""Join deployed social-login and courier/composition histories without data edits."""
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('management_api', '0036_social_login'),
        ('management_api', '0037_ai_composition_regions'),
    ]
    operations = []

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('chat_assistant', '0002_fix_and_seed'),
    ]

    operations = [
        migrations.AddField(
            model_name='chatlog',
            name='response_data',
            field=models.JSONField(blank=True, default=dict),
        ),
    ]

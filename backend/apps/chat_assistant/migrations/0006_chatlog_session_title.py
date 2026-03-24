from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('chat_assistant', '0005_chatlog_update_status_choices'),
    ]

    operations = [
        migrations.AddField(
            model_name='chatlog',
            name='session_title',
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
    ]

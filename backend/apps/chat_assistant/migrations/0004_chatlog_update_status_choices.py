from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('chat_assistant', '0003_chatlog_add_response_data'),
    ]

    operations = [
        migrations.AlterField(
            model_name='chatlog',
            name='execution_status',
            field=models.CharField(
                choices=[
                    ('needs_input',      'Needs Input (Slot-Fill)'),
                    ('awaiting_confirm', 'Awaiting Confirmation'),
                    ('success',          'Success'),
                    ('failed',           'Failed'),
                    ('rejected',         'Rejected'),
                    ('clarify',          'Clarification Requested'),
                    ('cancelled',        'Cancelled'),
                ],
                default='needs_input',
                max_length=50,
            ),
        ),
    ]

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0002_add_middle_name'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='status',
            field=models.CharField(
                choices=[
                    ('ACTIVE',    'Active'),
                    ('INACTIVE',  'Inactive'),
                    ('SUSPENDED', 'Suspended'),
                ],
                default='ACTIVE',
                max_length=10,
            ),
        ),
    ]

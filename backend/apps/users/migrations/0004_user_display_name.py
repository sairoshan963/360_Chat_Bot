from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0003_user_status_suspended'),
    ]

    operations = [
        # display_name is already added by 0003_add_display_name_suspended_status in the
        # parallel branch. Use SeparateDatabaseAndState so the migration state is updated
        # without running the SQL again (which would fail with "column already exists").
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.AddField(
                    model_name='user',
                    name='display_name',
                    field=models.CharField(blank=True, max_length=100, null=True),
                ),
            ],
        ),
    ]

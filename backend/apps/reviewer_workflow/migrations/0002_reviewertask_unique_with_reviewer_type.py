from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('reviewer_workflow', '0001_initial'),
    ]

    operations = [
        # Drop the old 3-column unique constraint
        migrations.AlterUniqueTogether(
            name='reviewertask',
            unique_together=set(),
        ),
        # Add the correct 4-column unique constraint (includes reviewer_type)
        migrations.AlterUniqueTogether(
            name='reviewertask',
            unique_together={('cycle', 'reviewee', 'reviewer', 'reviewer_type')},
        ),
    ]

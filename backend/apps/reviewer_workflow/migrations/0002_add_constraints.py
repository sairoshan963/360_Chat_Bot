# Generated migration for production fixes

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reviewer_workflow', '0001_initial'),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='reviewertask',
            constraint=models.UniqueConstraint(fields=['cycle', 'reviewee', 'reviewer'], name='unique_reviewer_task'),
        ),
        migrations.AddConstraint(
            model_name='peernomination',
            constraint=models.UniqueConstraint(fields=['cycle', 'reviewee', 'peer'], name='unique_peer_nomination'),
        ),
        migrations.AddIndex(
            model_name='reviewertask',
            index=models.Index(fields=['status'], name='reviewer_tasks_status_idx'),
        ),
        migrations.AddIndex(
            model_name='peernomination',
            index=models.Index(fields=['status'], name='peer_nominations_status_idx'),
        ),
    ]

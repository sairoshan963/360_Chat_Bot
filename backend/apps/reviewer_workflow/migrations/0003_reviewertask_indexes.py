from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reviewer_workflow', '0002_reviewertask_unique_with_reviewer_type'),
    ]

    operations = [
        migrations.AlterField(
            model_name='reviewertask',
            name='status',
            field=models.CharField(
                choices=[
                    ('CREATED', 'Created'), ('PENDING', 'Pending'),
                    ('IN_PROGRESS', 'In Progress'), ('SUBMITTED', 'Submitted'),
                    ('LOCKED', 'Locked'),
                ],
                default='CREATED', max_length=15, db_index=True,
            ),
        ),
        migrations.AlterField(
            model_name='reviewertask',
            name='reviewer_type',
            field=models.CharField(
                choices=[
                    ('SELF', 'Self'), ('MANAGER', 'Manager'),
                    ('PEER', 'Peer'), ('DIRECT_REPORT', 'Direct Report'),
                ],
                max_length=20, db_index=True,
            ),
        ),
        migrations.AddIndex(
            model_name='reviewertask',
            index=models.Index(fields=['cycle', 'status'], name='idx_rtask_cycle_status'),
        ),
    ]

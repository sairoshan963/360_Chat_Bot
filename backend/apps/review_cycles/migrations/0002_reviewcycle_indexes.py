from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('review_cycles', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='reviewcycle',
            name='state',
            field=models.CharField(
                choices=[
                    ('DRAFT', 'Draft'), ('NOMINATION', 'Nomination'),
                    ('FINALIZED', 'Finalized'), ('ACTIVE', 'Active'),
                    ('CLOSED', 'Closed'), ('RESULTS_RELEASED', 'Results Released'),
                    ('ARCHIVED', 'Archived'),
                ],
                default='DRAFT', max_length=20, db_index=True,
            ),
        ),
        migrations.AlterField(
            model_name='reviewcycle',
            name='review_deadline',
            field=models.DateTimeField(db_index=True),
        ),
        migrations.AlterField(
            model_name='reviewcycle',
            name='nomination_deadline',
            field=models.DateTimeField(null=True, blank=True, db_index=True),
        ),
    ]

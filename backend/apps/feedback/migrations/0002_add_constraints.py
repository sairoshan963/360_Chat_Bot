# Generated migration for feedback model production fixes

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('feedback', '0001_initial'),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='aggregatedresult',
            constraint=models.UniqueConstraint(fields=['cycle', 'reviewee'], name='unique_aggregated_result'),
        ),
        migrations.AddIndex(
            model_name='feedbackresponse',
            index=models.Index(fields=['submitted_by'], name='feedback_responses_submitted_by_idx'),
        ),
        migrations.AddIndex(
            model_name='feedbackanswer',
            index=models.Index(fields=['response'], name='feedback_answers_response_idx'),
        ),
        migrations.AddIndex(
            model_name='aggregatedresult',
            index=models.Index(fields=['cycle', 'reviewee'], name='aggregated_results_cycle_reviewee_idx'),
        ),
    ]

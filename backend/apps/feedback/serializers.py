from rest_framework import serializers
from .models import FeedbackResponse, FeedbackAnswer, AggregatedResult


class AnswerInputSerializer(serializers.Serializer):
    question_id  = serializers.UUIDField()
    rating_value = serializers.DecimalField(
        max_digits=5, decimal_places=2, required=False, allow_null=True,
        min_value=1, max_value=10,
    )
    text_value   = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, max_length=5000,
    )

    def validate(self, data):
        if data.get('rating_value') is None and not data.get('text_value'):
            raise serializers.ValidationError('Each answer must have rating_value or text_value')
        return data


class SubmitFeedbackSerializer(serializers.Serializer):
    answers = serializers.ListField(
        child=AnswerInputSerializer(),
        min_length=1,
    )


class FeedbackAnswerSerializer(serializers.ModelSerializer):
    question_text = serializers.CharField(source='question.question_text', read_only=True)
    question_type = serializers.CharField(source='question.type',          read_only=True)

    class Meta:
        model  = FeedbackAnswer
        fields = ['question', 'question_text', 'question_type', 'rating_value', 'text_value']


class AggregatedResultSerializer(serializers.ModelSerializer):
    reviewee_name = serializers.SerializerMethodField()

    class Meta:
        model  = AggregatedResult
        fields = ['cycle', 'reviewee', 'reviewee_name',
                  'overall_score', 'self_score', 'manager_score', 'peer_score', 'computed_at']

    def get_reviewee_name(self, obj):
        return obj.reviewee.get_full_name()

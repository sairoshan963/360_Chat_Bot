from rest_framework import serializers
from .models import Template, TemplateSection, TemplateQuestion, ReviewCycle, CycleParticipant


class TemplateQuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model  = TemplateQuestion
        fields = ['id', 'question_text', 'type', 'rating_scale_min', 'rating_scale_max',
                  'is_required', 'display_order']


class TemplateSectionSerializer(serializers.ModelSerializer):
    questions = TemplateQuestionSerializer(many=True, read_only=True)

    class Meta:
        model  = TemplateSection
        fields = ['id', 'title', 'display_order', 'questions']


class TemplateSerializer(serializers.ModelSerializer):
    sections      = TemplateSectionSerializer(many=True, read_only=True)
    creator_name  = serializers.SerializerMethodField()

    class Meta:
        model  = Template
        fields = ['id', 'name', 'description', 'is_active', 'creator_name', 'created_at', 'sections']

    def get_creator_name(self, obj):
        if obj.created_by:
            return obj.created_by.get_full_name()
        return None


class TemplateListSerializer(serializers.ModelSerializer):
    """Lightweight serializer — no sections. Used in lists."""
    creator_name = serializers.SerializerMethodField()

    class Meta:
        model  = Template
        fields = ['id', 'name', 'description', 'is_active', 'creator_name', 'created_at']

    def get_creator_name(self, obj):
        if obj.created_by:
            return obj.created_by.get_full_name()
        return None


class ReviewCycleSerializer(serializers.ModelSerializer):
    template_name = serializers.CharField(source='template.name', read_only=True)
    creator_name  = serializers.SerializerMethodField()
    participant_count = serializers.SerializerMethodField()

    class Meta:
        model  = ReviewCycle
        fields = [
            'id', 'name', 'description', 'state',
            'template', 'template_name',
            'peer_enabled', 'peer_min_count', 'peer_max_count', 'peer_threshold', 'peer_anonymity',
            'manager_anonymity', 'self_anonymity',
            'nomination_deadline', 'review_deadline',
            'quarter', 'quarter_year',
            'nomination_approval_mode',
            'results_released_at',
            'creator_name', 'participant_count',
            'created_at', 'updated_at',
        ]

    def get_creator_name(self, obj):
        if obj.created_by:
            return obj.created_by.get_full_name()
        return None

    def get_participant_count(self, obj):
        # Use pre-annotated value from list_cycles queryset when available (avoids N+1)
        if hasattr(obj, 'participant_count'):
            return obj.participant_count
        return obj.participations.count()


class CycleParticipantSerializer(serializers.ModelSerializer):
    id          = serializers.UUIDField(source='user.id',         read_only=True)
    email       = serializers.EmailField(source='user.email',     read_only=True)
    first_name  = serializers.CharField(source='user.first_name', read_only=True)
    last_name   = serializers.CharField(source='user.last_name',  read_only=True)
    role        = serializers.CharField(source='user.role',       read_only=True)
    department  = serializers.CharField(source='user.department.name', read_only=True, default=None)
    manager_id  = serializers.SerializerMethodField()

    class Meta:
        model  = CycleParticipant
        fields = ['id', 'email', 'first_name', 'last_name', 'role', 'department', 'manager_id']

    def get_manager_id(self, obj):
        try:
            return str(obj.user.manager_relation.manager.id)
        except Exception:
            return None


class AddParticipantsSerializer(serializers.Serializer):
    participant_ids = serializers.ListField(
        child=serializers.UUIDField(),
        min_length=1,
    )


class CycleStateOverrideSerializer(serializers.Serializer):
    target_state = serializers.ChoiceField(choices=[s[0] for s in ReviewCycle.STATE_CHOICES])
    reason       = serializers.CharField(min_length=1)

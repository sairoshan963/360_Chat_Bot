from rest_framework import serializers
from .models import ReviewerTask, PeerNomination


class ReviewerTaskSerializer(serializers.ModelSerializer):
    cycle_name        = serializers.CharField(source='cycle.name',             read_only=True)
    cycle_state       = serializers.CharField(source='cycle.state',            read_only=True)
    review_deadline   = serializers.DateTimeField(source='cycle.review_deadline', read_only=True)
    template_id       = serializers.UUIDField(source='cycle.template_id',      read_only=True)
    template          = serializers.SerializerMethodField()
    reviewee_first    = serializers.CharField(source='reviewee.first_name',    read_only=True)
    reviewee_last     = serializers.CharField(source='reviewee.last_name',     read_only=True)
    reviewee_email    = serializers.EmailField(source='reviewee.email',        read_only=True)
    submitted_answers = serializers.SerializerMethodField()
    draft_answers     = serializers.SerializerMethodField()

    class Meta:
        model  = ReviewerTask
        fields = [
            'id', 'cycle', 'cycle_name', 'cycle_state', 'review_deadline', 'template_id',
            'template',
            'reviewee', 'reviewee_first', 'reviewee_last', 'reviewee_email',
            'reviewer_type', 'anonymity_mode', 'status',
            'draft_answers', 'submitted_answers',
            'created_at', 'updated_at',
        ]

    def get_template(self, obj):
        from apps.review_cycles.serializers import TemplateSectionSerializer
        t = obj.cycle.template
        return {
            'id':       str(t.id),
            'name':     t.name,
            'sections': TemplateSectionSerializer(t.sections.all(), many=True).data,
        }

    def get_draft_answers(self, obj):
        # Only return draft answers in detail context — not in list to avoid bulk data exposure
        if self.context.get('detail'):
            return obj.draft_answers
        return None

    def get_submitted_answers(self, obj):
        if obj.status not in ['SUBMITTED', 'LOCKED']:
            return None
        try:
            return [
                {
                    'question_id':  str(a.question_id),
                    'rating_value': float(a.rating_value) if a.rating_value is not None else None,
                    'text_value':   a.text_value,
                }
                for a in obj.response.answers.all()
            ]
        except Exception:
            return None


class SaveDraftSerializer(serializers.Serializer):
    answers = serializers.ListField(
        child=serializers.DictField(),
        min_length=0,
        allow_empty=True,
    )


class NominationSerializer(serializers.ModelSerializer):
    # Fields used by CycleDetailPage (HR view)
    peer_first     = serializers.CharField(source='peer.first_name',     read_only=True)
    peer_last      = serializers.CharField(source='peer.last_name',      read_only=True)
    peer_email     = serializers.EmailField(source='peer.email',         read_only=True)
    reviewee_first = serializers.CharField(source='reviewee.first_name', read_only=True)
    reviewee_last  = serializers.CharField(source='reviewee.last_name',  read_only=True)
    # Fields used by NominationsPage (Employee view)
    peer_id        = serializers.UUIDField(source='peer.id',             read_only=True)
    first_name     = serializers.CharField(source='peer.first_name',     read_only=True)
    last_name      = serializers.CharField(source='peer.last_name',      read_only=True)
    email          = serializers.EmailField(source='peer.email',         read_only=True)
    cycle_id       = serializers.UUIDField(source='cycle.id',            read_only=True)

    class Meta:
        model  = PeerNomination
        fields = [
            'id', 'cycle', 'cycle_id', 'reviewee', 'reviewee_first', 'reviewee_last',
            'peer', 'peer_id', 'peer_first', 'peer_last', 'peer_email',
            'first_name', 'last_name', 'email',
            'status', 'rejection_note', 'approved_at', 'created_at',
        ]


class SubmitNominationsSerializer(serializers.Serializer):
    peer_ids = serializers.ListField(
        child=serializers.UUIDField(),
        min_length=1,
    )


class NominationDecisionSerializer(serializers.Serializer):
    status         = serializers.ChoiceField(choices=['APPROVED', 'REJECTED'])
    rejection_note = serializers.CharField(required=False, allow_blank=True)

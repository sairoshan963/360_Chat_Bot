import uuid
from django.db import models
from django.conf import settings


# ─── Template ─────────────────────────────────────────────────────────────────

class Template(models.Model):
    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name        = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    is_active   = models.BooleanField(default=True)
    created_by  = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='created_templates')
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'review_templates'
        ordering = ['-created_at']

    def __str__(self):
        return self.name


class TemplateSection(models.Model):
    id            = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    template      = models.ForeignKey(Template, on_delete=models.CASCADE, related_name='sections')
    title         = models.CharField(max_length=255)
    display_order = models.PositiveIntegerField(default=1)

    class Meta:
        db_table  = 'template_sections'
        ordering  = ['display_order']

    def __str__(self):
        return f'{self.template.name} — {self.title}'


class TemplateQuestion(models.Model):
    QUESTION_TYPE_CHOICES = [
        ('RATING',    'Rating'),
        ('TEXT',      'Text'),
        ('MULTI_CHOICE', 'Multiple Choice'),
    ]

    id               = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    section          = models.ForeignKey(TemplateSection, on_delete=models.CASCADE, related_name='questions')
    question_text    = models.TextField()
    type             = models.CharField(max_length=20, choices=QUESTION_TYPE_CHOICES, default='RATING')
    rating_scale_min = models.IntegerField(null=True, blank=True)
    rating_scale_max = models.IntegerField(null=True, blank=True)
    is_required      = models.BooleanField(default=True)
    display_order    = models.PositiveIntegerField(default=1)

    class Meta:
        db_table = 'template_questions'
        ordering = ['display_order']

    def __str__(self):
        return f'{self.section.title} — Q{self.display_order}'


# ─── Review Cycle ─────────────────────────────────────────────────────────────

class ReviewCycle(models.Model):
    STATE_CHOICES = [
        ('DRAFT',            'Draft'),
        ('NOMINATION',       'Nomination'),
        ('FINALIZED',        'Finalized'),
        ('ACTIVE',           'Active'),
        ('CLOSED',           'Closed'),
        ('RESULTS_RELEASED', 'Results Released'),
        ('ARCHIVED',         'Archived'),
    ]
    ANONYMITY_CHOICES = [
        ('ANONYMOUS',      'Anonymous'),
        ('SEMI_ANONYMOUS', 'Semi Anonymous'),
        ('TRANSPARENT',    'Transparent'),
    ]
    APPROVAL_MODE_CHOICES = [
        ('AUTO',   'Auto'),
        ('MANUAL', 'Manual'),
    ]
    QUARTER_CHOICES = [('Q1', 'Q1'), ('Q2', 'Q2'), ('Q3', 'Q3'), ('Q4', 'Q4')]

    id                      = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name                    = models.CharField(max_length=255)
    description             = models.TextField(blank=True, null=True)
    template                = models.ForeignKey(Template, on_delete=models.PROTECT, related_name='cycles')
    state                   = models.CharField(max_length=20, choices=STATE_CHOICES, default='DRAFT', db_index=True)

    # Peer settings
    peer_enabled            = models.BooleanField(default=False)
    peer_min_count          = models.IntegerField(null=True, blank=True)
    peer_max_count          = models.IntegerField(null=True, blank=True)
    peer_threshold          = models.IntegerField(default=3)
    peer_anonymity          = models.CharField(max_length=20, choices=ANONYMITY_CHOICES, default='ANONYMOUS')

    # Anonymity settings
    manager_anonymity       = models.CharField(max_length=20, choices=ANONYMITY_CHOICES, default='TRANSPARENT')
    self_anonymity          = models.CharField(max_length=20, choices=ANONYMITY_CHOICES, default='TRANSPARENT')

    # Deadlines
    nomination_deadline     = models.DateTimeField(null=True, blank=True, db_index=True)
    review_deadline         = models.DateTimeField(db_index=True)

    # Quarter metadata
    quarter                 = models.CharField(max_length=2, choices=QUARTER_CHOICES, null=True, blank=True)
    quarter_year            = models.IntegerField(null=True, blank=True)

    # Nomination approval
    nomination_approval_mode = models.CharField(max_length=10, choices=APPROVAL_MODE_CHOICES, default='AUTO')

    results_released_at     = models.DateTimeField(null=True, blank=True)
    created_by              = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='created_cycles')
    created_at              = models.DateTimeField(auto_now_add=True)
    updated_at              = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'review_cycles'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.name} [{self.state}]'


class CycleParticipant(models.Model):
    id         = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cycle      = models.ForeignKey(ReviewCycle, on_delete=models.CASCADE, related_name='participations')
    user       = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='cycle_participations')
    added_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table        = 'cycle_participants'
        unique_together = ('cycle', 'user')

    def __str__(self):
        return f'{self.user.email} in {self.cycle.name}'

import uuid
from django.db import models
from django.conf import settings


class ReviewerTask(models.Model):
    STATUS_CHOICES = [
        ('CREATED',     'Created'),
        ('PENDING',     'Pending'),
        ('IN_PROGRESS', 'In Progress'),
        ('SUBMITTED',   'Submitted'),
        ('LOCKED',      'Locked'),
    ]
    REVIEWER_TYPE_CHOICES = [
        ('SELF',          'Self'),
        ('MANAGER',       'Manager'),
        ('PEER',          'Peer'),
        ('DIRECT_REPORT', 'Direct Report'),
    ]
    ANONYMITY_CHOICES = [
        ('ANONYMOUS',      'Anonymous'),
        ('SEMI_ANONYMOUS', 'Semi Anonymous'),
        ('TRANSPARENT',    'Transparent'),
    ]

    id             = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cycle          = models.ForeignKey('review_cycles.ReviewCycle', on_delete=models.CASCADE, related_name='tasks')
    reviewee       = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='tasks_as_reviewee')
    reviewer       = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='tasks_as_reviewer')
    reviewer_type  = models.CharField(max_length=20, choices=REVIEWER_TYPE_CHOICES, db_index=True)
    anonymity_mode = models.CharField(max_length=20, choices=ANONYMITY_CHOICES, default='TRANSPARENT')
    status         = models.CharField(max_length=15, choices=STATUS_CHOICES, default='CREATED', db_index=True)
    draft_answers  = models.JSONField(null=True, blank=True)
    created_at     = models.DateTimeField(auto_now_add=True)
    updated_at     = models.DateTimeField(auto_now=True)

    class Meta:
        db_table        = 'reviewer_tasks'
        unique_together = ('cycle', 'reviewee', 'reviewer', 'reviewer_type')
        indexes         = [
            models.Index(fields=['cycle', 'status'], name='idx_rtask_cycle_status'),
        ]

    def __str__(self):
        return f'{self.reviewer_type}: {self.reviewer} → {self.reviewee} [{self.status}]'


class PeerNomination(models.Model):
    STATUS_CHOICES = [
        ('PENDING',  'Pending'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
    ]

    id             = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cycle          = models.ForeignKey('review_cycles.ReviewCycle', on_delete=models.CASCADE, related_name='nominations')
    reviewee       = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='received_nominations')
    peer           = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='given_nominations')
    nominated_by   = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='submitted_nominations')
    status         = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PENDING')
    approved_by    = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_nominations')
    approved_at    = models.DateTimeField(null=True, blank=True)
    rejection_note = models.TextField(blank=True, null=True)
    created_at     = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table        = 'peer_nominations'
        unique_together = ('cycle', 'reviewee', 'peer')

    def __str__(self):
        return f'{self.peer} nominated for {self.reviewee} [{self.status}]'

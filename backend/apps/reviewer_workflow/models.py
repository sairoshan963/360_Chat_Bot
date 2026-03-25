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
    cycle          = models.ForeignKey('review_cycles.ReviewCycle', on_delete=models.CASCADE, related_name='tasks', db_index=True)
    reviewee       = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='tasks_as_reviewee', db_index=True)
    reviewer       = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='tasks_as_reviewer', db_index=True)
    reviewer_type  = models.CharField(max_length=20, choices=REVIEWER_TYPE_CHOICES)
    anonymity_mode = models.CharField(max_length=20, choices=ANONYMITY_CHOICES, default='TRANSPARENT')
    status         = models.CharField(max_length=15, choices=STATUS_CHOICES, default='CREATED', db_index=True)
    draft_answers  = models.JSONField(null=True, blank=True)
    created_at     = models.DateTimeField(auto_now_add=True)
    updated_at     = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'reviewer_tasks'
        constraints = [
            models.UniqueConstraint(
                fields=['cycle', 'reviewee', 'reviewer'],
                name='unique_reviewer_task'
            )
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
    cycle          = models.ForeignKey('review_cycles.ReviewCycle', on_delete=models.CASCADE, related_name='nominations', db_index=True)
    reviewee       = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='received_nominations', db_index=True)
    peer           = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='given_nominations', db_index=True)
    nominated_by   = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='submitted_nominations')
    status         = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PENDING', db_index=True)
    approved_by    = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_nominations')
    approved_at    = models.DateTimeField(null=True, blank=True)
    rejection_note = models.TextField(blank=True, null=True)
    created_at     = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'peer_nominations'
        constraints = [
            models.UniqueConstraint(
                fields=['cycle', 'reviewee', 'peer'],
                name='unique_peer_nomination'
            )
        ]

    def __str__(self):
        return f'{self.peer} nominated for {self.reviewee} [{self.status}]'

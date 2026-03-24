import uuid
from django.db import models
from django.conf import settings


class PromptTemplate(models.Model):
    id            = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name          = models.CharField(max_length=100)
    template_text = models.TextField()
    version       = models.PositiveIntegerField(default=1)
    is_active     = models.BooleanField(default=True)
    created_at    = models.DateTimeField(auto_now_add=True)
    updated_at    = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'prompt_templates'
        ordering = ['-version']
        unique_together = [('name', 'version')]

    def __str__(self):
        return f'{self.name} v{self.version}'


class ChatLog(models.Model):
    STATUS_CHOICES = [
        ('needs_input',      'Needs Input (Slot-Fill)'),
        ('awaiting_confirm', 'Awaiting Confirmation'),
        ('success',          'Success'),
        ('failed',           'Failed'),
        ('rejected',         'Rejected'),
        ('clarify',          'Clarification Requested'),
        ('cancelled',        'Cancelled'),
    ]

    id               = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user             = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.RESTRICT, related_name='chat_logs')
    session_id       = models.CharField(max_length=100)
    message          = models.TextField()
    intent           = models.CharField(max_length=100, blank=True, null=True)
    parameters       = models.JSONField(default=dict)
    execution_status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='pending')
    response_message = models.TextField(blank=True, null=True)
    response_data    = models.JSONField(default=dict, blank=True)
    used_llm         = models.BooleanField(default=False)
    session_title    = models.CharField(max_length=100, blank=True, null=True)
    created_at       = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'chat_logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['session_id']),
            models.Index(fields=['intent']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f'[{self.intent}] {self.user.email} — {self.execution_status}'

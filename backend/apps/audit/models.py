import logging
import uuid
from django.db import models
from django.conf import settings

logger = logging.getLogger(__name__)


class AuditLog(models.Model):
    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor       = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='audit_logs')
    action_type = models.CharField(max_length=50)
    entity_type = models.CharField(max_length=50)
    entity_id   = models.UUIDField(null=True, blank=True)
    old_value   = models.JSONField(null=True, blank=True)
    new_value   = models.JSONField(null=True, blank=True)
    ip_address  = models.GenericIPAddressField(null=True, blank=True)
    user_agent  = models.TextField(blank=True, null=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'audit_logs'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.action_type} on {self.entity_type} by {self.actor}'

    @classmethod
    def log(cls, actor, action, entity_type, entity_id=None,
            old_value=None, new_value=None, ip_address=None, user_agent=None):
        try:
            cls.objects.create(
                actor=actor,
                action_type=action,
                entity_type=entity_type,
                entity_id=entity_id,
                old_value=old_value,
                new_value=new_value,
                ip_address=ip_address,
                user_agent=user_agent,
            )
        except Exception as exc:
            # Audit log failure must never break the main operation,
            # but we must at least surface it in server logs.
            logger.error('AuditLog.log failed: %s | action=%s entity=%s id=%s',
                         exc, action, entity_type, entity_id, exc_info=True)

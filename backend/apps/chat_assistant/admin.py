from django.contrib import admin
from .models import ChatLog, PromptTemplate


@admin.register(PromptTemplate)
class PromptTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'version', 'is_active', 'updated_at')
    list_filter  = ('is_active',)
    search_fields = ('name',)


@admin.register(ChatLog)
class ChatLogAdmin(admin.ModelAdmin):
    list_display  = ('user', 'intent', 'execution_status', 'used_llm', 'created_at')
    list_filter   = ('execution_status', 'used_llm', 'intent')
    search_fields = ('user__email', 'intent', 'session_id')
    readonly_fields = ('id', 'user', 'session_id', 'message', 'intent',
                       'parameters', 'execution_status', 'response_message',
                       'used_llm', 'created_at')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

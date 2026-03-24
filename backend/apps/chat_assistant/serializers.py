from rest_framework import serializers
from .models import ChatLog


class ChatMessageSerializer(serializers.Serializer):
    message         = serializers.CharField(max_length=2000, min_length=1, trim_whitespace=True)
    session_id      = serializers.CharField(max_length=100, required=False, allow_blank=True)
    display_message = serializers.CharField(max_length=2000, required=False, allow_blank=True)


class ChatConfirmSerializer(serializers.Serializer):
    session_id = serializers.CharField(max_length=100)
    confirmed  = serializers.BooleanField()


class ChatLogSerializer(serializers.ModelSerializer):
    class Meta:
        model  = ChatLog
        fields = ['id', 'session_id', 'message', 'intent', 'parameters',
                  'execution_status', 'response_message', 'response_data',
                  'used_llm', 'created_at']

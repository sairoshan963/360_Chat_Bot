from django.urls import path
from .views import ChatMessageView, ChatStreamView, ChatHistoryView, ChatConfirmView, ChatSessionView, ChatAnalyticsView, ChatSessionsView, ChatSessionDetailView, ChatUploadView

urlpatterns = [
    path('message/',                      ChatMessageView.as_view(),       name='chat-message'),
    path('stream/',                       ChatStreamView.as_view(),        name='chat-stream'),
    path('confirm/',                      ChatConfirmView.as_view(),       name='chat-confirm'),
    path('history/',                      ChatHistoryView.as_view(),       name='chat-history'),
    path('sessions/',                     ChatSessionsView.as_view(),      name='chat-sessions'),
    path('sessions/<str:session_id>/',    ChatSessionDetailView.as_view(), name='chat-session-detail'),
    path('session/',                      ChatSessionView.as_view(),       name='chat-session'),
    path('analytics/',                    ChatAnalyticsView.as_view(),     name='chat-analytics'),
    path('upload/',                       ChatUploadView.as_view(),        name='chat-upload'),
]

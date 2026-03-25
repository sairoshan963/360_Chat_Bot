from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Notification
from .serializers import NotificationSerializer


class NotificationListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        notifications = Notification.objects.filter(user=request.user).order_by('-created_at')[:50]
        return Response({
            'success': True,
            'notifications': NotificationSerializer(notifications, many=True).data,
        })


class UnreadCountView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        count = Notification.objects.filter(user=request.user, is_read=False).count()
        return Response({'success': True, 'count': count})


class MarkReadView(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request, pk):
        try:
            notif = Notification.objects.get(id=pk, user=request.user)
        except Notification.DoesNotExist:
            return Response({'success': False, 'error': 'Notification not found'}, status=404)
        notif.is_read = True
        notif.save(update_fields=['is_read'])
        return Response({'success': True, 'notification': NotificationSerializer(notif).data})


class MarkAllReadView(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request):
        Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        return Response({'success': True})

from django.db.models import Q
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from shared.permissions import IsHRAdmin, IsSuperAdmin
from .models import Announcement
from .serializers import AnnouncementSerializer, CreateAnnouncementSerializer


class AnnouncementListView(APIView):
    """All authenticated users: active, non-expired announcements."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        now = timezone.now()
        announcements = Announcement.objects.filter(
            is_active=True
        ).filter(
            Q(expires_at__isnull=True) | Q(expires_at__gt=now)
        ).distinct().order_by('-created_at')
        return Response({
            'success': True,
            'announcements': AnnouncementSerializer(announcements, many=True).data,
        })


class AnnouncementAdminListView(APIView):
    """HR Admin: all announcements including inactive/expired."""
    permission_classes = [IsAuthenticated, IsHRAdmin]

    def get(self, request):
        announcements = Announcement.objects.select_related('created_by').all()
        return Response({
            'success': True,
            'announcements': AnnouncementSerializer(announcements, many=True).data,
        })

    def post(self, request):
        serializer = CreateAnnouncementSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        announcement = Announcement.objects.create(
            message=serializer.validated_data['message'].strip(),
            type=serializer.validated_data.get('type', 'info'),
            expires_at=serializer.validated_data.get('expires_at'),
            created_by=request.user,
        )
        return Response({
            'success': True,
            'announcement': AnnouncementSerializer(announcement).data,
        }, status=201)


class AnnouncementDeactivateView(APIView):
    """HR Admin: soft-deactivate an announcement."""
    permission_classes = [IsAuthenticated, IsHRAdmin]

    def patch(self, request, pk):
        try:
            announcement = Announcement.objects.get(id=pk)
        except Announcement.DoesNotExist:
            return Response({'success': False, 'error': 'Announcement not found'}, status=404)
        announcement.is_active = False
        announcement.save(update_fields=['is_active', 'updated_at'])
        return Response({'success': True})


class AnnouncementDeleteView(APIView):
    """Super Admin only: hard delete."""
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def delete(self, request, pk):
        try:
            announcement = Announcement.objects.get(id=pk)
        except Announcement.DoesNotExist:
            return Response({'success': False, 'error': 'Announcement not found'}, status=404)
        announcement.delete()
        return Response({'success': True})

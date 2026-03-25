from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from shared.permissions import IsEmployee, IsHRAdmin, IsManager, IsHROrManager
from . import services
from .serializers import (
    ReviewerTaskSerializer,
    SaveDraftSerializer,
    NominationSerializer,
    SubmitNominationsSerializer,
    NominationDecisionSerializer,
)


# ─── Tasks ────────────────────────────────────────────────────────────────────

class MyTasksView(APIView):
    """Employee: list all feedback tasks assigned to me."""
    permission_classes = [IsAuthenticated, IsEmployee]

    def get(self, request):
        tasks = services.get_my_tasks(request.user)
        return Response({'success': True, 'tasks': ReviewerTaskSerializer(tasks, many=True).data})


class TaskDetailView(APIView):
    """Employee: get one task (with draft answers)."""
    permission_classes = [IsAuthenticated, IsEmployee]

    def get(self, request, pk):
        task = services.get_task(pk, request.user)
        return Response({'success': True, 'task': ReviewerTaskSerializer(task, context={'detail': True}).data})


class SaveDraftView(APIView):
    """Employee: save draft answers for a task (does NOT submit)."""
    permission_classes = [IsAuthenticated, IsEmployee]

    def post(self, request, pk):
        serializer = SaveDraftSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        task = services.save_draft(pk, request.user, serializer.validated_data['answers'])
        return Response({'success': True, 'task_id': str(task.id), 'status': task.status})


# ─── Nominations ──────────────────────────────────────────────────────────────

class MyNominationsView(APIView):
    """Employee: view and submit their own nominations for a cycle."""
    permission_classes = [IsAuthenticated, IsEmployee]

    def get(self, request, cycle_id):
        nominations = services.get_my_nominations(cycle_id, request.user)
        return Response({'success': True, 'nominations': NominationSerializer(nominations, many=True).data})

    def post(self, request, cycle_id):
        serializer = SubmitNominationsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        nominations = services.submit_nominations(
            cycle_id, request.user, serializer.validated_data['peer_ids']
        )
        return Response({
            'success': True,
            'message': f'{nominations.count()} nomination(s) submitted',
            'nominations': NominationSerializer(nominations, many=True).data,
        })


class AllNominationsView(APIView):
    """HR Admin: view all nominations for a cycle."""
    permission_classes = [IsAuthenticated, IsHRAdmin]

    def get(self, request, cycle_id):
        nominations = services.get_all_nominations(cycle_id)
        return Response({'success': True, 'nominations': NominationSerializer(nominations, many=True).data})


class PendingApprovalsView(APIView):
    """Manager: view pending nominations for their direct reports."""
    permission_classes = [IsAuthenticated, IsHROrManager]

    def get(self, request, cycle_id):
        if request.user.role == 'MANAGER':
            nominations = services.get_pending_approvals_for_manager(cycle_id, request.user)
        else:
            # HR sees all pending
            nominations = services.get_all_nominations(cycle_id).filter(status='PENDING')
        return Response({'success': True, 'nominations': NominationSerializer(nominations, many=True).data})


class NominationDecisionView(APIView):
    """Manager or HR: approve or reject a nomination."""
    permission_classes = [IsAuthenticated, IsHROrManager]

    def patch(self, request, pk):
        serializer = NominationDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        nomination = services.decide_nomination(
            pk,
            serializer.validated_data['status'],
            request.user,
            serializer.validated_data.get('rejection_note'),
        )
        return Response({
            'success': True,
            'nomination': NominationSerializer(nomination).data,
        })

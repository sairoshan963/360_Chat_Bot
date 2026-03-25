import re

from django.http import HttpResponse
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView


def _safe_filename(name):
    """Strip characters that break Content-Disposition headers or file systems."""
    return re.sub(r'[^\w\-. ]', '_', name).strip()

from shared.permissions import IsEmployee, IsHRAdmin, IsHROrManager, IsSuperAdmin
from . import services
from .serializers import SubmitFeedbackSerializer


# ─── Submit Feedback ──────────────────────────────────────────────────────────

class SubmitFeedbackView(APIView):
    """Employee: submit answers for a reviewer task."""
    permission_classes = [IsAuthenticated, IsEmployee]

    def post(self, request, task_id):
        serializer = SubmitFeedbackSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = services.submit_feedback(
            task_id, request.user, serializer.validated_data['answers']
        )
        return Response({'success': True, **result})


# ─── My Report ────────────────────────────────────────────────────────────────

class MyReportView(APIView):
    """Employee: view their own 360° feedback report."""
    permission_classes = [IsAuthenticated, IsEmployee]

    def get(self, request, cycle_id):
        report = services.get_my_report(cycle_id, request.user)
        return Response({'success': True, 'report': report})


# ─── Employee Report (Manager / HR / Super Admin) ─────────────────────────────

class EmployeeReportView(APIView):
    """Manager / HR / Super Admin: view a specific employee's report."""
    permission_classes = [IsAuthenticated, IsHROrManager]

    def get(self, request, cycle_id, employee_id):
        report = services.get_employee_report(cycle_id, employee_id, request.user)
        return Response({'success': True, 'report': report})


# ─── All Reports for a Cycle (HR) ─────────────────────────────────────────────

class CycleReportsListView(APIView):
    """HR Admin: list all participants + their aggregated scores for a cycle."""
    permission_classes = [IsAuthenticated, IsHRAdmin]

    def get(self, request, cycle_id):
        from apps.feedback.models import AggregatedResult
        from apps.review_cycles.models import CycleParticipant
        from apps.feedback.serializers import AggregatedResultSerializer

        participants = CycleParticipant.objects.filter(cycle_id=cycle_id).values_list('user_id', flat=True)
        results = AggregatedResult.objects.filter(
            cycle_id=cycle_id, reviewee_id__in=participants
        ).select_related('reviewee')

        return Response({
            'success': True,
            'reports': AggregatedResultSerializer(results, many=True).data,
        })


# ─── Excel Export (Super Admin) ───────────────────────────────────────────────

class ExportReportView(APIView):
    """HR Admin / Super Admin: download a single employee's report as Excel."""
    permission_classes = [IsAuthenticated, IsHROrManager]

    def get(self, request, cycle_id, employee_id):
        buffer = services.export_employee_report_excel(cycle_id, employee_id, request.user)

        from apps.users.models import User
        try:
            emp = User.objects.get(id=employee_id)
            filename = _safe_filename(f'360_report_{emp.last_name}_{emp.first_name}') + '.xlsx'
        except Exception:
            filename = f'360_report_{employee_id}.xlsx'

        response = HttpResponse(
            buffer.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response


# ─── Bulk Excel Export (all employees in a cycle) ─────────────────────────────

class ExportAllReportsView(APIView):
    """HR Admin: download all employees' reports for a cycle as one Excel file."""
    permission_classes = [IsAuthenticated, IsHRAdmin]

    def get(self, request, cycle_id):
        buffer = services.export_all_reports_excel(cycle_id, request.user)

        from apps.review_cycles.models import ReviewCycle
        try:
            cycle = ReviewCycle.objects.get(id=cycle_id)
            filename = _safe_filename(f'360_all_reports_{cycle.name}') + '.xlsx'
        except Exception:
            filename = f'360_all_reports_{cycle_id}.xlsx'

        response = HttpResponse(
            buffer.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

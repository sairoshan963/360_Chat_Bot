import re

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from shared.permissions import IsHRAdmin, IsHROrManager, IsSuperAdmin, IsEmployee


def _safe_filename(name):
    """Strip characters that break Content-Disposition headers or file systems."""
    return re.sub(r'[^\w\-. ]', '_', name).strip()
from . import services
from .serializers import (
    TemplateSerializer, TemplateListSerializer,
    ReviewCycleSerializer, CycleParticipantSerializer,
    AddParticipantsSerializer, CycleStateOverrideSerializer,
)


# ─── Templates ────────────────────────────────────────────────────────────────

class TemplateListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsHRAdmin]

    def get(self, request):
        templates = services.list_templates()
        return Response({'success': True, 'templates': TemplateListSerializer(templates, many=True).data})

    def post(self, request):
        name     = request.data.get('name')
        desc     = request.data.get('description')
        sections = request.data.get('sections', [])
        template = services.create_template(name, desc, sections, request.user)
        return Response({'success': True, 'template': TemplateSerializer(template).data}, status=201)


class TemplateDetailView(APIView):
    permission_classes = [IsAuthenticated, IsHRAdmin]

    def get(self, request, pk):
        template = services.get_template(pk)
        return Response({'success': True, 'template': TemplateSerializer(template).data})

    def put(self, request, pk):
        name     = request.data.get('name')
        sections = request.data.get('sections', [])
        template = services.update_template(pk, name, sections, request.user)
        return Response({'success': True, 'template': TemplateSerializer(template).data})


# ─── Cycles ───────────────────────────────────────────────────────────────────

class CycleListCreateView(APIView):

    def get_permissions(self):
        if self.request.method == 'POST':
            return [IsAuthenticated(), IsHRAdmin()]
        return [IsAuthenticated(), IsHROrManager()]

    def get(self, request):
        state  = request.query_params.get('state')
        cycles = services.list_cycles(state=state)
        return Response({'success': True, 'cycles': ReviewCycleSerializer(cycles, many=True).data})

    def post(self, request):
        cycle = services.create_cycle(request.data, request.user)
        return Response({'success': True, 'cycle': ReviewCycleSerializer(cycle).data}, status=201)


class MyCyclesView(APIView):
    """Employee: list cycles I am a participant of."""
    permission_classes = [IsAuthenticated, IsEmployee]

    def get(self, request):
        cycles = services.get_my_cycles(request.user)
        return Response({'success': True, 'cycles': ReviewCycleSerializer(cycles, many=True).data})


class CycleDetailView(APIView):
    permission_classes = [IsAuthenticated, IsHRAdmin]

    def get(self, request, pk):
        cycle = services.get_cycle(pk)
        return Response({'success': True, 'cycle': ReviewCycleSerializer(cycle).data})

    def put(self, request, pk):
        cycle = services.update_cycle(pk, request.data, request.user)
        return Response({'success': True, 'cycle': ReviewCycleSerializer(cycle).data})

    def patch(self, request, pk):
        cycle = services.update_cycle(pk, request.data, request.user)
        return Response({'success': True, 'cycle': ReviewCycleSerializer(cycle).data})


# ─── Participants ─────────────────────────────────────────────────────────────

class CycleParticipantsView(APIView):

    def get_permissions(self):
        if self.request.method in ('POST', 'DELETE'):
            return [IsAuthenticated(), IsHRAdmin()]
        return [IsAuthenticated(), IsHROrManager()]

    def get(self, request, pk):
        participants = services.get_participants(pk)
        return Response({'success': True, 'participants': CycleParticipantSerializer(participants, many=True).data})

    def post(self, request, pk):
        serializer = AddParticipantsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        participants = services.add_participants(
            pk, serializer.validated_data['participant_ids'], request.user
        )
        return Response({'success': True, 'participants': CycleParticipantSerializer(participants, many=True).data})

    def delete(self, request, pk):
        user_id = request.data.get('user_id')
        if not user_id:
            return Response({'success': False, 'message': 'user_id is required'}, status=400)
        services.remove_participant(pk, user_id, request.user)
        return Response({'success': True, 'message': 'Participant removed'})


# ─── State Transitions ────────────────────────────────────────────────────────

class CycleActivateView(APIView):
    permission_classes = [IsAuthenticated, IsHRAdmin]

    def post(self, request, pk):
        cycle = services.activate_cycle(pk, request.user)
        return Response({'success': True, 'cycle': ReviewCycleSerializer(cycle).data})


class CycleFinalizeView(APIView):
    permission_classes = [IsAuthenticated, IsHRAdmin]

    def post(self, request, pk):
        cycle = services.finalize_cycle(pk, request.user)
        return Response({'success': True, 'cycle': ReviewCycleSerializer(cycle).data})


class CycleCloseView(APIView):
    permission_classes = [IsAuthenticated, IsHRAdmin]

    def post(self, request, pk):
        cycle = services.close_cycle(pk, request.user)
        return Response({'success': True, 'cycle': ReviewCycleSerializer(cycle).data})


class CycleReleaseResultsView(APIView):
    permission_classes = [IsAuthenticated, IsHRAdmin]

    def post(self, request, pk):
        cycle = services.release_results(pk, request.user)
        return Response({'success': True, 'cycle': ReviewCycleSerializer(cycle).data})


class CycleArchiveView(APIView):
    permission_classes = [IsAuthenticated, IsHRAdmin]

    def post(self, request, pk):
        cycle = services.archive_cycle(pk, request.user)
        return Response({'success': True, 'cycle': ReviewCycleSerializer(cycle).data})


class CycleOverrideView(APIView):
    """Super Admin only — emergency state override."""
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def post(self, request, pk):
        serializer = CycleStateOverrideSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cycle = services.override_cycle(
            pk,
            serializer.validated_data['target_state'],
            serializer.validated_data['reason'],
            request.user,
        )
        return Response({'success': True, 'cycle': ReviewCycleSerializer(cycle).data})


# ─── Progress & Status ────────────────────────────────────────────────────────

class CycleProgressView(APIView):
    permission_classes = [IsAuthenticated, IsHRAdmin]

    def get(self, request, pk):
        progress = services.get_cycle_progress(pk)
        return Response({'success': True, 'progress': list(progress)})


class NominationExcelDownloadView(APIView):
    permission_classes = [IsAuthenticated, IsHRAdmin]

    def get(self, request, pk):
        import io
        from openpyxl import Workbook
        from django.http import HttpResponse

        cycle    = services.get_cycle(pk)
        noms     = services.get_nomination_status(pk)
        wb       = Workbook()
        ws       = wb.active
        ws.title = 'Nominations'
        ws.append(['Name', 'Email', 'Department', 'Nominated', 'Approved', 'Min Required', 'Status'])
        for p in noms:
            ws.append([
                f"{p['first_name']} {p['last_name']}", p['email'],
                p.get('department') or '—', p['nominated'], p['approved'],
                p['min_required'], p['status'],
            ])
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        fname = _safe_filename(f'nominations-{cycle.name}') + '.xlsx'
        response = HttpResponse(buf.read(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = f'attachment; filename="{fname}"'
        return response


class ParticipantExcelDownloadView(APIView):
    permission_classes = [IsAuthenticated, IsHRAdmin]

    def get(self, request, pk):
        import io
        from openpyxl import Workbook
        from django.http import HttpResponse

        cycle    = services.get_cycle(pk)
        parts    = services.get_participant_task_status(pk)
        dl_type  = request.query_params.get('type', 'pending')
        if dl_type == 'done':
            rows = [p for p in parts if p['overall'] in ['COMPLETED', 'PARTIAL']]
            label = 'completed'
        else:
            rows = [p for p in parts if p['overall'] in ['PENDING', 'NO_TASKS', 'MISSED']]
            label = 'pending'

        wb = Workbook()
        ws = wb.active
        ws.title = label.capitalize()
        ws.append(['Name', 'Email', 'Department', 'Total Tasks', 'Submitted', 'Locked', 'Pending', 'Overall Status'])
        for p in rows:
            ws.append([
                f"{p['first_name']} {p['last_name']}", p['email'],
                p.get('department') or '—', p['total'], p['submitted'],
                p['locked'], p['pending'], p['overall'],
            ])
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)
        fname = _safe_filename(f'{label}-{cycle.name}') + '.xlsx'
        response = HttpResponse(buf.read(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = f'attachment; filename="{fname}"'
        return response


class NominationStatusView(APIView):
    permission_classes = [IsAuthenticated, IsHRAdmin]

    def get(self, request, pk):
        participants = services.get_nomination_status(pk)
        return Response({'success': True, 'participants': participants})


class ParticipantTaskStatusView(APIView):
    permission_classes = [IsAuthenticated, IsHRAdmin]

    def get(self, request, pk):
        participants = services.get_participant_task_status(pk)
        return Response({'success': True, 'participants': participants})

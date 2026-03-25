from django.core.mail import send_mail
from django.conf import settings
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import SupportTicket


class SupportReportView(APIView):
    """
    Any authenticated user can submit a bug/suggestion report.
    Saves to DB and emails the admin if SMTP is configured.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        message = (request.data.get('message') or '').strip()
        type_   = request.data.get('type', 'General')
        page    = request.data.get('page', '')

        if not message:
            return Response({'success': False, 'error': 'Message is required'}, status=400)

        if len(message) > 5000:
            return Response({'success': False, 'error': 'Message must be 5000 characters or fewer'}, status=400)

        valid_types = ['Bug', 'Suggestion', 'General']
        if type_ not in valid_types:
            type_ = 'General'

        user = request.user

        # Save to DB
        SupportTicket.objects.create(
            submitted_by=user,
            type=type_,
            message=message,
            page=page or None,
        )

        # Email admin if SMTP is configured
        recipient = settings.EMAIL_HOST_USER
        sent = False
        if recipient:
            subject = f'[Gamyam 360] {type_} Report from {user.get_full_name()}'
            body = (
                f'Type    : {type_}\n'
                f'From    : {user.get_full_name()} ({user.email}) — {user.role}\n'
                f'Page    : {page or "Unknown"}\n\n'
                f'Message:\n{message}'
            )
            try:
                send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [recipient], fail_silently=True)
                sent = True
            except Exception:
                pass

        return Response({'success': True, 'sent': sent})

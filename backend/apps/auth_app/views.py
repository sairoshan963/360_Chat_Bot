import requests as http_requests
from django.conf import settings
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken


class LoginRateThrottle(AnonRateThrottle):
    scope = 'login'


class PasswordResetRateThrottle(AnonRateThrottle):
    scope = 'password_reset'

from . import services
from .serializers import (
    LoginSerializer,
    GoogleAuthSerializer,
    ForgotPasswordSerializer,
    ResetPasswordSerializer,
    ChangePasswordSerializer,
    UpdateProfileSerializer,
    UserMeSerializer,
)


# ─── Login ────────────────────────────────────────────────────────────────────

class LoginView(APIView):
    permission_classes = [AllowAny]
    throttle_classes   = [LoginRateThrottle]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = services.login(
            serializer.validated_data['email'],
            serializer.validated_data['password'],
        )
        return Response({'success': True, **result})


# ─── Refresh Token ────────────────────────────────────────────────────────────

class TokenRefreshView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        refresh_token = request.data.get('refresh')
        if not refresh_token:
            return Response({'success': False, 'error': 'refresh token required'}, status=400)
        try:
            token = RefreshToken(refresh_token)
            return Response({'success': True, 'access': str(token.access_token)})
        except Exception:
            return Response({'success': False, 'error': 'Invalid or expired refresh token'}, status=401)


# ─── Google OAuth ─────────────────────────────────────────────────────────────

class GoogleAuthView(APIView):
    """
    Accepts the authorization code from the React frontend,
    exchanges it for a Google ID token, verifies it, and logs the user in.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = GoogleAuthSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        code = serializer.validated_data['code']

        # Exchange code for tokens with Google
        redirect_uri = f'{settings.FRONTEND_URL}/auth/callback'
        client_id    = settings.SOCIALACCOUNT_PROVIDERS['google']['APP']['client_id']

        token_resp = http_requests.post('https://oauth2.googleapis.com/token', data={
            'code':          code,
            'client_id':     client_id,
            'client_secret': settings.SOCIALACCOUNT_PROVIDERS['google']['APP']['secret'],
            'redirect_uri':  redirect_uri,
            'grant_type':    'authorization_code',
        })

        if not token_resp.ok:
            error_detail = token_resp.json().get('error_description') or token_resp.json().get('error') or 'Failed to exchange Google code'
            return Response({'success': False, 'error': error_detail}, status=400)

        id_token = token_resp.json().get('id_token')
        if not id_token:
            return Response({'success': False, 'error': 'No id_token in Google response'}, status=400)

        # Verify the ID token
        verify_resp = http_requests.get(
            f'https://oauth2.googleapis.com/tokeninfo?id_token={id_token}'
        )
        if not verify_resp.ok:
            return Response({'success': False, 'error': 'Invalid Google token'}, status=400)

        profile = verify_resp.json()

        # Verify the token was issued for our app (prevent token injection from other Google apps)
        expected_aud = settings.SOCIALACCOUNT_PROVIDERS['google']['APP']['client_id']
        if profile.get('aud') != expected_aud:
            return Response({'success': False, 'error': 'Invalid Google token'}, status=400)

        result = services.login_with_google(
            google_email=profile.get('email', ''),
            given_name=profile.get('given_name', ''),
            family_name=profile.get('family_name', ''),
        )
        return Response({'success': True, **result})


# ─── Get Me ───────────────────────────────────────────────────────────────────

class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = services.get_me(request.user.id)
        return Response({'success': True, 'user': UserMeSerializer(user).data})


# ─── Update Profile ───────────────────────────────────────────────────────────

class UpdateProfileView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request):
        serializer = UpdateProfileSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = services.update_profile(
            request.user,
            serializer.validated_data['first_name'],
            serializer.validated_data.get('middle_name') or '',
            serializer.validated_data['last_name'],
            serializer.validated_data.get('display_name') or '',
            serializer.validated_data.get('job_title', ''),
        )
        return Response({'success': True, 'user': UserMeSerializer(user).data})


# ─── Change Password ──────────────────────────────────────────────────────────

class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.change_password(
            request.user,
            serializer.validated_data['current_password'],
            serializer.validated_data['new_password'],
        )
        from apps.audit.models import AuditLog
        AuditLog.log(actor=request.user, action='CHANGE_PASSWORD',
                     entity_type='user', entity_id=request.user.id,
                     new_value={'changed_by': 'self'})
        return Response({'success': True, 'message': 'Password updated successfully'})


# ─── Avatar Upload ────────────────────────────────────────────────────────────

class AvatarUploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes     = [MultiPartParser, FormParser]

    def post(self, request):
        image = request.FILES.get('avatar')
        if not image:
            return Response({'success': False, 'error': 'No file uploaded'}, status=400)

        allowed = ['.jpg', '.jpeg', '.png', '.webp']
        import os
        ext = os.path.splitext(image.name)[1].lower()
        if ext not in allowed:
            return Response({'success': False, 'error': 'Only JPG, PNG, WEBP allowed'}, status=400)

        MAX_SIZE = 5 * 1024 * 1024  # 5 MB
        if image.size > MAX_SIZE:
            return Response({'success': False, 'error': 'Avatar file too large. Maximum size is 5 MB.'}, status=400)

        url = services.upload_avatar(request.user, image)
        return Response({'success': True, 'avatar_url': url})


# ─── Forgot Password ──────────────────────────────────────────────────────────

class ForgotPasswordView(APIView):
    permission_classes = [AllowAny]
    throttle_classes   = [PasswordResetRateThrottle]

    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.request_password_reset(serializer.validated_data['email'])
        # Always return success — never reveal if email exists
        return Response({'success': True, 'message': 'If that email exists, a reset link has been sent'})


# ─── Reset Password ───────────────────────────────────────────────────────────

class ResetPasswordView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.reset_password(
            serializer.validated_data['token'],
            serializer.validated_data['new_password'],
        )
        return Response({'success': True, 'message': 'Password reset successfully'})

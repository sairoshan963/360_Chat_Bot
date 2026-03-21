import hashlib
import os
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied, ValidationError, NotFound
from rest_framework_simplejwt.tokens import RefreshToken

from shared.email import send_password_reset
from django.conf import settings
from .models import PasswordResetToken

User = get_user_model()


def _token_for_user(user):
    """Return access + refresh JWT tokens for a user."""
    refresh = RefreshToken.for_user(user)
    refresh['role'] = user.role
    return {
        'access':  str(refresh.access_token),
        'refresh': str(refresh),
    }


def _user_data(user):
    return {
        'id':           str(user.id),
        'email':        user.email,
        'first_name':   user.first_name,
        'middle_name':  user.middle_name,
        'last_name':    user.last_name,
        'display_name': user.display_name,
        'job_title':    user.job_title,
        'role':         user.role,
        'avatar_url':   user.avatar_url,
    }


# ─── Login ────────────────────────────────────────────────────────────────────

def login(email, password):
    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        raise AuthenticationFailed('Invalid email or password')

    if user.status != 'ACTIVE':
        raise PermissionDenied('Account is not active')

    if not user.check_password(password):
        raise AuthenticationFailed('Invalid email or password')

    user.last_login_at = timezone.now()
    user.save(update_fields=['last_login_at'])

    return {**_token_for_user(user), 'user': _user_data(user)}


# ─── Google OAuth ─────────────────────────────────────────────────────────────

def login_with_google(google_email, given_name='', family_name=''):
    try:
        user = User.objects.get(email=google_email)
    except User.DoesNotExist:
        raise PermissionDenied('No account linked to this email. Contact HR.')

    if user.status != 'ACTIVE':
        raise PermissionDenied('Account is not active')

    # Update name from Google if not set yet
    updated_fields = ['last_login_at']
    if given_name and not user.first_name:
        user.first_name = given_name
        updated_fields.append('first_name')
    if family_name and not user.last_name:
        user.last_name = family_name
        updated_fields.append('last_name')

    user.last_login_at = timezone.now()
    user.save(update_fields=updated_fields)

    return {**_token_for_user(user), 'user': _user_data(user)}


# ─── Get Me ───────────────────────────────────────────────────────────────────

def get_me(user_id):
    try:
        return User.objects.select_related('department').get(id=user_id)
    except User.DoesNotExist:
        raise NotFound('User not found')


# ─── Profile Update ───────────────────────────────────────────────────────────

def update_profile(user, first_name, middle_name, last_name, display_name, job_title):
    user.first_name   = first_name.strip()
    user.middle_name  = middle_name.strip() if middle_name else None
    user.last_name    = last_name.strip()
    user.display_name = display_name.strip() if display_name else None
    user.job_title    = job_title.strip() if job_title else None
    user.save(update_fields=['first_name', 'middle_name', 'last_name', 'display_name', 'job_title', 'updated_at'])
    return user


# ─── Change Password ──────────────────────────────────────────────────────────

def change_password(user, current_password, new_password):
    if not user.check_password(current_password):
        raise ValidationError('Current password is incorrect')
    user.set_password(new_password)
    user.save(update_fields=['password'])


# ─── Avatar Upload ────────────────────────────────────────────────────────────

def upload_avatar(user, image_file):
    import os
    from django.core.files.storage import default_storage

    ext      = os.path.splitext(image_file.name)[1].lower()
    filename = f'avatars/{user.id}{ext}'

    if default_storage.exists(filename):
        default_storage.delete(filename)

    saved_path = default_storage.save(filename, image_file)
    url = f'{settings.MEDIA_URL}{saved_path}'

    user.avatar_url = url
    user.save(update_fields=['avatar_url'])
    return url


# ─── Forgot Password ──────────────────────────────────────────────────────────

def _create_reset_token(user):
    """Create (or replace) a password reset token for a user. Returns the raw token."""
    PasswordResetToken.objects.filter(user=user).delete()
    raw_token  = os.urandom(32).hex()
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    PasswordResetToken.objects.create(
        user=user,
        token_hash=token_hash,
        expires_at=timezone.now() + timedelta(hours=1),
    )
    return raw_token


def request_password_reset(email):
    """
    Always returns silently — never reveals whether the email exists.
    """
    try:
        user = User.objects.get(email=email, status='ACTIVE')
    except User.DoesNotExist:
        return  # silent — prevent email enumeration

    raw_token  = _create_reset_token(user)
    reset_link = f'{settings.FRONTEND_URL}/reset-password?token={raw_token}'
    send_password_reset(user.email, user.first_name, reset_link)


# ─── Reset Password ───────────────────────────────────────────────────────────

def reset_password(raw_token, new_password):
    if not new_password or len(new_password) < 8:
        raise ValidationError('Password must be at least 8 characters')

    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()

    try:
        record = PasswordResetToken.objects.get(
            token_hash=token_hash,
            used_at=None,
            expires_at__gt=timezone.now(),
        )
    except PasswordResetToken.DoesNotExist:
        raise ValidationError('Reset link is invalid or has expired')

    record.user.set_password(new_password)
    record.user.save(update_fields=['password'])

    record.used_at = timezone.now()
    record.save(update_fields=['used_at'])

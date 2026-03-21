from rest_framework import serializers
from django.contrib.auth import get_user_model

User = get_user_model()


class LoginSerializer(serializers.Serializer):
    email    = serializers.EmailField()
    password = serializers.CharField(write_only=True)


class GoogleAuthSerializer(serializers.Serializer):
    code = serializers.CharField(help_text='Authorization code from Google OAuth callback')


class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()


class ResetPasswordSerializer(serializers.Serializer):
    token       = serializers.CharField()
    new_password = serializers.CharField(min_length=8, write_only=True)


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password     = serializers.CharField(min_length=8, write_only=True)


class UpdateProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model  = User
        fields = ['first_name', 'middle_name', 'last_name', 'display_name', 'job_title']

    def validate_first_name(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError('First name is required')
        return value.strip()

    def validate_last_name(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError('Last name is required')
        return value.strip()


class UserMeSerializer(serializers.ModelSerializer):
    department_name = serializers.CharField(source='department.name', read_only=True, default=None)

    class Meta:
        model  = User
        fields = [
            'id', 'email', 'first_name', 'middle_name', 'last_name', 'display_name', 'job_title',
            'role', 'status', 'avatar_url', 'department_name', 'last_login_at',
        ]

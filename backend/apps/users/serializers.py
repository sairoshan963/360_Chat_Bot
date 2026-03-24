from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Department, OrgHierarchy

User = get_user_model()


class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Department
        fields = ['id', 'name', 'created_at']


class UserSerializer(serializers.ModelSerializer):
    department_name = serializers.CharField(source='department.name', read_only=True, default=None)
    manager_id      = serializers.UUIDField(source='manager_relation.manager.id', read_only=True, default=None)
    manager_name    = serializers.SerializerMethodField()

    class Meta:
        model  = User
        fields = [
            'id', 'email', 'first_name', 'middle_name', 'last_name', 'display_name', 'job_title',
            'role', 'status', 'avatar_url',
            'department', 'department_name',
            'manager_id', 'manager_name',
            'last_login_at', 'created_at',
        ]
        read_only_fields = ['id', 'last_login_at', 'created_at']

    def get_manager_name(self, obj):
        try:
            m = obj.manager_relation.manager
            return m.get_full_name()
        except Exception:
            return None


class CreateUserSerializer(serializers.ModelSerializer):
    manager_id  = serializers.UUIDField(required=False, allow_null=True, write_only=True)
    password    = serializers.CharField(min_length=8, write_only=True, required=False)

    class Meta:
        model  = User
        fields = [
            'email', 'first_name', 'middle_name', 'last_name', 'job_title',
            'role', 'department', 'manager_id', 'password',
        ]

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError('A user with this email already exists')
        return value.lower()

    def create(self, validated_data):
        manager_id = validated_data.pop('manager_id', None)
        password   = validated_data.pop('password', None)

        user = User(**validated_data)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save()

        if manager_id:
            if str(manager_id) == str(user.id):
                raise serializers.ValidationError({'manager_id': 'A user cannot be their own manager'})
            try:
                manager = User.objects.get(id=manager_id)
                OrgHierarchy.objects.update_or_create(employee=user, defaults={'manager': manager})
            except User.DoesNotExist:
                pass

        return user


class UpdateUserSerializer(serializers.ModelSerializer):
    manager_id = serializers.UUIDField(required=False, allow_null=True, write_only=True)

    class Meta:
        model  = User
        fields = ['first_name', 'middle_name', 'last_name', 'job_title', 'role', 'status', 'department', 'manager_id']

    def update(self, instance, validated_data):
        manager_id = validated_data.pop('manager_id', None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if 'manager_id' in self.initial_data:
            if manager_id is None:
                OrgHierarchy.objects.filter(employee=instance).delete()
            else:
                if str(manager_id) == str(instance.id):
                    raise serializers.ValidationError({'manager_id': 'A user cannot be their own manager'})
                try:
                    manager = User.objects.get(id=manager_id)
                    OrgHierarchy.objects.update_or_create(employee=instance, defaults={'manager': manager})
                except User.DoesNotExist:
                    pass

        return instance


class BulkImportResultSerializer(serializers.Serializer):
    created = serializers.IntegerField()
    skipped = serializers.IntegerField()
    errors  = serializers.ListField(child=serializers.DictField())

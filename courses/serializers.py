from django.contrib.auth import get_user_model
from rest_framework import serializers

from accounts.serializers import UserSerializer
from courses.models import Course

User = get_user_model()


class CourseSerializer(serializers.ModelSerializer):
    """Validate and serialize a course with its mapped Faculty and Students."""

    code = serializers.CharField(max_length=20)
    faculty = UserSerializer(many=True, read_only=True)
    students = UserSerializer(many=True, read_only=True)

    class Meta:
        model = Course
        fields = [
            "id",
            "code",
            "name",
            "description",
            "faculty",
            "students",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_code(self, value):
        code = value.strip().upper()

        if not code:
            raise serializers.ValidationError("Course code cannot be blank.")

        courses = Course.objects.filter(code=code)
        if self.instance is not None:
            courses = courses.exclude(pk=self.instance.pk)
        if courses.exists():
            raise serializers.ValidationError(
                "A course with this code already exists."
            )

        return code

    def validate_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("Course name cannot be blank.")
        return value.strip()


class CourseMappingSerializer(serializers.Serializer):
    """Validate the users to map to a course for a given role."""

    user_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=False,
    )

    def __init__(self, *args, role, **kwargs):
        super().__init__(*args, **kwargs)
        self.role = role

    def validate_user_ids(self, value):
        if len(value) != len(set(value)):
            raise serializers.ValidationError("Duplicate user IDs are not allowed.")

        users = {user.id: user for user in User.objects.filter(id__in=value)}

        missing = [user_id for user_id in value if user_id not in users]
        if missing:
            raise serializers.ValidationError(f"Unknown user IDs: {missing}")

        wrong_role = [
            user_id for user_id in value if users[user_id].role != self.role
        ]
        if wrong_role:
            raise serializers.ValidationError(
                f"These users are not {User.Role(self.role).label} "
                f"accounts: {wrong_role}"
            )

        inactive = [user_id for user_id in value if not users[user_id].is_active]
        if inactive:
            raise serializers.ValidationError(
                f"These accounts are deactivated: {inactive}"
            )

        return [users[user_id] for user_id in value]

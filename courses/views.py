from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsAdmin
from courses.models import Course
from courses.serializers import CourseMappingSerializer, CourseSerializer


class CourseListCreateView(generics.ListCreateAPIView):
    """List or create courses."""

    queryset = Course.objects.prefetch_related("faculty", "students")
    serializer_class = CourseSerializer
    permission_classes = [IsAdmin]


class CourseDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, edit or delete a course."""

    queryset = Course.objects.prefetch_related("faculty", "students")
    serializer_class = CourseSerializer
    permission_classes = [IsAdmin]


class CourseMembersView(APIView):
    """Map Faculty members or Students to a course."""

    permission_classes = [IsAdmin]
    role = None
    relation = None

    def post(self, request, pk):
        course = get_object_or_404(Course, pk=pk)
        serializer = CourseMappingSerializer(data=request.data, role=self.role)
        serializer.is_valid(raise_exception=True)

        getattr(course, self.relation).add(*serializer.validated_data["user_ids"])

        return Response(CourseSerializer(course).data, status=status.HTTP_200_OK)


class CourseMemberDetailView(APIView):
    """Remove one Faculty member or Student from a course."""

    permission_classes = [IsAdmin]
    relation = None

    def delete(self, request, pk, user_id):
        course = get_object_or_404(Course, pk=pk)
        members = getattr(course, self.relation)
        user = get_object_or_404(members.all(), pk=user_id)

        members.remove(user)

        return Response(status=status.HTTP_204_NO_CONTENT)

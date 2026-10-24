
from rest_framework import generics
from rest_framework.permissions import IsAdminUser

from question_bank.models import Question
from question_bank.serializers import QuestionSerializer


class QuestionListCreateView(generics.ListCreateAPIView):
    serializer_class = QuestionSerializer

    # TEMP: is_staff stands in for Faculty/Admin until the real
    # role-based authorization is integrated.
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        queryset = Question.objects.all().order_by("-created_at")

        subject = self.request.query_params.get("subject")
        topic = self.request.query_params.get("topic")
        difficulty = self.request.query_params.get("difficulty")

        if subject:
            queryset = queryset.filter(subject__iexact=subject.strip())

        if topic:
            queryset = queryset.filter(topic__iexact=topic.strip())

        if difficulty:
            queryset = queryset.filter(difficulty__iexact=difficulty.strip())

        return queryset

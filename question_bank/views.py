from rest_framework import generics
from question_bank.models import Question
from question_bank.serializers import QuestionSerializer

class QuestionListCreateView(generics.ListCreateAPIView):
    queryset = Question.objects.all().order_by("-created_at")
    serializer_class = QuestionSerializer
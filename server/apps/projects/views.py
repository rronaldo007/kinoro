"""Project endpoints — CRUD with PATCH-friendly timeline updates."""

from __future__ import annotations

from rest_framework import viewsets

from .models import Project
from .serializers import ProjectSerializer


class ProjectViewSet(viewsets.ModelViewSet):
    queryset = Project.objects.all().order_by("-updated_at")
    serializer_class = ProjectSerializer

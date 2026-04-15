"""Render endpoints — create / list / retrieve."""

from __future__ import annotations

from rest_framework import mixins, status, viewsets
from rest_framework.response import Response

from apps.projects.models import Project

from .models import RenderJob
from .serializers import RenderJobCreateSerializer, RenderJobSerializer
from .services import start_render


class RenderJobViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    queryset = RenderJob.objects.all().order_by("-created_at")
    serializer_class = RenderJobSerializer

    def create(self, request, *args, **kwargs):
        payload = RenderJobCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        project_id = payload.validated_data["project"]
        try:
            project = Project.objects.get(pk=project_id)
        except Project.DoesNotExist:
            return Response(
                {"project": "Project not found"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not (project.timeline_json or {}).get("clips"):
            return Response(
                {"detail": "Timeline is empty — nothing to render"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        job = start_render(
            project,
            payload.validated_data.get("preset_name") or "youtube_1080p",
        )
        return Response(
            RenderJobSerializer(job).data, status=status.HTTP_201_CREATED
        )

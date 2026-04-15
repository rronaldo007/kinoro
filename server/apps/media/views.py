"""MediaAsset endpoints — list / retrieve / create / delete.

Create accepts a local filesystem path and kicks off background ingest.
"""

from __future__ import annotations

from pathlib import Path

from rest_framework import mixins, status, viewsets
from rest_framework.response import Response

from .models import MediaAsset
from .serializers import MediaAssetCreateSerializer, MediaAssetSerializer
from .services import ingest_async


class MediaAssetViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    queryset = MediaAsset.objects.all().order_by("-created_at")
    serializer_class = MediaAssetSerializer

    def create(self, request, *args, **kwargs):
        payload = MediaAssetCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        src = Path(payload.validated_data["source_path"]).expanduser()

        if not src.is_file():
            return Response(
                {"source_path": f"File not found: {src}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        asset = MediaAsset.objects.create(
            name=payload.validated_data.get("name") or src.name,
            source_path=str(src.resolve()),
            status=MediaAsset.Status.INGESTING,
        )
        ingest_async(asset.id)
        return Response(
            MediaAssetSerializer(asset).data, status=status.HTTP_201_CREATED
        )

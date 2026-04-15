"""Video Planner import — live API endpoints.

Slice B of M1: log in, list/fetch projects. Background import pipeline
(media download + proxy build) lands in the next slice.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from django.conf import settings
from django.db import transaction
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from .importers import plan_import, start_import, start_zip_import
from .models import VPAccount, VPImportJob
from .serializers import (
    VPAccountSerializer,
    VPImportJobSerializer,
    VPLoginSerializer,
)
from .services import VPAuthError, VPClient, VPClientError


def _current_account() -> VPAccount | None:
    return VPAccount.objects.order_by("-created_at").first()


def _client_from_account(acc: VPAccount) -> VPClient:
    return VPClient(
        base_url=acc.base_url,
        access_token=acc.access_token,
        refresh_token=acc.refresh_token,
    )


def _persist_refreshed_token(acc: VPAccount, client: VPClient) -> None:
    if client.access_token and client.access_token != acc.access_token:
        acc.access_token = client.access_token
        acc.save(update_fields=["access_token"])


@api_view(["POST"])
def adopt(request):
    """Accept pre-authenticated tokens from a kinoro:// handoff URL.

    When the user is already logged into Video Planner on the web, the
    handoff URL carries their current access + refresh tokens. Kinoro
    verifies them against VP's /api/auth/me/ (catches typos, expired
    access), then stores them as the singleton VPAccount — no separate
    login modal required.
    """
    base_url = (request.data.get("base_url") or "").rstrip("/")
    access = request.data.get("access") or ""
    refresh = request.data.get("refresh") or ""
    if not base_url or not access:
        return Response(
            {"detail": "base_url and access are required"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    client = VPClient(base_url=base_url, access_token=access, refresh_token=refresh)
    try:
        me = client.me()
    except VPAuthError as e:
        return Response({"detail": str(e)}, status=status.HTTP_401_UNAUTHORIZED)
    except VPClientError as e:
        return Response({"detail": str(e)}, status=status.HTTP_502_BAD_GATEWAY)
    with transaction.atomic():
        VPAccount.objects.all().delete()
        acc = VPAccount.objects.create(
            base_url=base_url,
            email=me.get("email") or "",
            access_token=client.access_token or access,
            refresh_token=client.refresh_token or refresh,
            user_payload=me,
        )
    return Response(VPAccountSerializer(acc).data)


@api_view(["POST"])
def login(request):
    s = VPLoginSerializer(data=request.data)
    s.is_valid(raise_exception=True)
    data = s.validated_data
    client = VPClient(base_url=data["base_url"])
    try:
        result = client.login(data["email"], data["password"])
    except VPAuthError as e:
        return Response({"detail": str(e)}, status=status.HTTP_401_UNAUTHORIZED)
    except VPClientError as e:
        return Response({"detail": str(e)}, status=status.HTTP_502_BAD_GATEWAY)

    with transaction.atomic():
        VPAccount.objects.all().delete()
        acc = VPAccount.objects.create(
            base_url=data["base_url"],
            email=data["email"],
            access_token=result.access,
            refresh_token=result.refresh,
            user_payload=result.user,
        )
    return Response(VPAccountSerializer(acc).data)


@api_view(["POST"])
def logout(_request):
    VPAccount.objects.all().delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["GET"])
def account(_request):
    acc = _current_account()
    if not acc:
        return Response({"detail": "Not logged in"}, status=status.HTTP_404_NOT_FOUND)
    return Response(VPAccountSerializer(acc).data)


@api_view(["GET"])
def project_list(_request):
    acc = _current_account()
    if not acc:
        return Response({"detail": "Not logged in"}, status=status.HTTP_401_UNAUTHORIZED)
    client = _client_from_account(acc)
    try:
        projects = client.list_projects()
    except VPAuthError as e:
        return Response({"detail": str(e)}, status=status.HTTP_401_UNAUTHORIZED)
    except VPClientError as e:
        return Response({"detail": str(e)}, status=status.HTTP_502_BAD_GATEWAY)
    _persist_refreshed_token(acc, client)
    return Response(projects)


@api_view(["GET"])
def project_detail(_request, project_id: str):
    acc = _current_account()
    if not acc:
        return Response({"detail": "Not logged in"}, status=status.HTTP_401_UNAUTHORIZED)
    client = _client_from_account(acc)
    try:
        kind, project = client.try_get_any_project(project_id)
        # Regular Project: resources live at /api/projects/<id>/resources/.
        # EditorProject: clips in timeline_json; if empty, fall back to the
        # linked source_project's video resources so the UI count matches
        # what "Import media" will actually pull (see importers.plan_import).
        if kind == "project":
            resources = client.list_resources(project_id) or []
        else:
            clips = (project.get("timeline_json") or {}).get("clips") or []
            if clips:
                resources = list(clips)
            elif project.get("source_project"):
                source_id = str(project["source_project"])
                all_resources = client.list_resources(source_id) or []
                # Keep only importable ones so the count reflects reality.
                resources = [
                    r for r in all_resources
                    if r.get("type") in ("video", "sound")
                    and isinstance(r.get("url"), str)
                    and r["url"].startswith(("http://", "https://"))
                ]
            else:
                resources = []
    except VPAuthError as e:
        return Response({"detail": str(e)}, status=status.HTTP_401_UNAUTHORIZED)
    except VPClientError as e:
        return Response({"detail": str(e)}, status=status.HTTP_502_BAD_GATEWAY)
    _persist_refreshed_token(acc, client)
    return Response({"kind": kind, "project": project, "resources": resources})


@api_view(["POST"])
def project_import(_request, project_id: str):
    """Kick off a background import and return the job row for polling."""
    acc = _current_account()
    if not acc:
        return Response({"detail": "Not logged in"}, status=status.HTTP_401_UNAUTHORIZED)
    try:
        kind, count = plan_import(project_id, acc)
    except VPAuthError as e:
        return Response({"detail": str(e)}, status=status.HTTP_401_UNAUTHORIZED)
    except VPClientError as e:
        return Response({"detail": str(e)}, status=status.HTTP_502_BAD_GATEWAY)
    job = start_import(project_id, acc)
    payload = VPImportJobSerializer(job).data
    payload["kind"] = kind
    payload["asset_count"] = count
    return Response(payload, status=status.HTTP_201_CREATED)


@api_view(["GET"])
def import_job_detail(_request, job_id: str):
    job = VPImportJob.objects.filter(pk=job_id).first()
    if not job:
        return Response({"detail": "Job not found"}, status=status.HTTP_404_NOT_FOUND)
    return Response(VPImportJobSerializer(job).data)


@api_view(["POST"])
@parser_classes([MultiPartParser, FormParser])
def project_import_zip(request):
    """Import a Video Planner export ZIP.

    Accepts ``multipart/form-data`` with a ``file`` part. The uploaded ZIP
    is persisted under ``$KINORO_DATA_DIR/vp-zip-imports/<uuid>.zip`` so
    the background thread can read it after the request returns, then
    ``start_zip_import`` kicks off the same downstream pipeline the live
    API import uses. Returns the job row for polling (same shape as
    ``project_import``).
    """
    uploaded = request.FILES.get("file")
    if uploaded is None:
        return Response(
            {"detail": "Multipart 'file' upload required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    dest_dir = Path(settings.KINORO_DATA_DIR) / "vp-zip-imports"
    dest_dir.mkdir(parents=True, exist_ok=True)
    # Keep the original suffix for debuggability but prefix with a uuid so
    # re-uploading the same filename twice doesn't overwrite.
    orig_name = Path(uploaded.name or "upload.zip").name
    dest = dest_dir / f"{uuid.uuid4().hex}-{orig_name}"
    with dest.open("wb") as fh:
        for chunk in uploaded.chunks():
            fh.write(chunk)

    job = start_zip_import(dest)
    return Response(
        VPImportJobSerializer(job).data, status=status.HTTP_201_CREATED
    )

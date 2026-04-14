"""Video Planner import — live API endpoints.

Slice B of M1: log in, list/fetch projects. Background import pipeline
(media download + proxy build) lands in the next slice.
"""

from __future__ import annotations

from django.db import transaction
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import VPAccount
from .serializers import VPAccountSerializer, VPLoginSerializer
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
        # For editor projects resources live inside timeline_json; for regular
        # projects they're a nested endpoint. Only fetch the nested list when
        # it exists.
        if kind == "project":
            resources = client.list_resources(project_id)
        else:
            clips = (project.get("timeline_json") or {}).get("clips") or []
            resources = list(clips)
    except VPAuthError as e:
        return Response({"detail": str(e)}, status=status.HTTP_401_UNAUTHORIZED)
    except VPClientError as e:
        return Response({"detail": str(e)}, status=status.HTTP_502_BAD_GATEWAY)
    _persist_refreshed_token(acc, client)
    return Response({"kind": kind, "project": project, "resources": resources})

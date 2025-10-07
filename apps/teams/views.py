from __future__ import annotations

from django.db.models import Count, Prefetch
from django.http import Http404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.common.exceptions import TeamNotFound

from .models import Team, TeamMember
from .paginations import TeamPagination
from .serializers import (
    TeamCreateSerializer,
    TeamMemberMutationSerializer,
    TeamMemberReadSerializer,
    TeamMemberRemovalSerializer,
    TeamReadSerializer,
    TeamUpdateSerializer,
)
from .services import (
    ensure_user_can_manage_members,
    ensure_user_can_manage_team,
    ensure_user_can_read_team,
    filter_teams_for_user,
)


class TeamViewSet(viewsets.ModelViewSet):
    """Team lifecycle management with membership operations."""

    lookup_field = "uuid"
    permission_classes = [IsAuthenticated]
    pagination_class = TeamPagination
    ERROR_DOMAIN = "teams"

    def get_queryset(self):
        queryset = (
            Team.objects.select_related(
                "organization",
                "organization__account",
                "created_by",
                "updated_by",
            )
            .prefetch_related(
                Prefetch(
                    "memberships",
                    queryset=TeamMember.objects.select_related("user", "assigned_by"),
                    to_attr="_prefetched_memberships",
                )
            )
            .annotate(active_member_count=Count("memberships"))
            .order_by("-created_at")
        )
        return filter_teams_for_user(queryset, getattr(self.request, "user", None))

    def get_serializer_class(self):
        if self.action == "create":
            return TeamCreateSerializer
        if self.action in {"update", "partial_update"}:
            return TeamUpdateSerializer
        if self.action == "members" and self.request.method == "POST":
            return TeamMemberMutationSerializer
        if self.action == "remove_member":
            return TeamMemberRemovalSerializer
        return TeamReadSerializer

    def get_object(self):
        try:
            obj = super().get_object()
        except Http404 as exc:
            raise TeamNotFound() from exc
        ensure_user_can_read_team(self.request.user, obj)
        return obj

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = TeamReadSerializer(page, many=True, context={"request": request})
            return self.get_paginated_response(serializer.data)
        serializer = TeamReadSerializer(queryset, many=True, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        team = serializer.save()
        read = TeamReadSerializer(team, context={"request": request})
        return Response(read.data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        return self._update_impl(request, partial=False)

    def partial_update(self, request, *args, **kwargs):
        return self._update_impl(request, partial=True)

    def _update_impl(self, request, *, partial: bool):
        team = self.get_object()
        serializer = self.get_serializer(team, data=request.data, partial=partial, context={"request": request})
        serializer.is_valid(raise_exception=True)
        team = serializer.save()
        read = TeamReadSerializer(team, context={"request": request})
        return Response(read.data, status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        team = self.get_object()
        ensure_user_can_manage_team(request.user, team, "teams:delete")
        team.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], url_path="members")
    def members(self, request, uuid=None):
        team = self.get_object()
        serializer = TeamMemberMutationSerializer(
            data=request.data,
            context={"request": request, "team": team},
        )
        serializer.is_valid(raise_exception=True)
        membership = serializer.save()
        read = TeamMemberReadSerializer(membership, context={"request": request})
        return Response(read.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["delete"], url_path="members/(?P<user_uuid>[^/]+)")
    def remove_member(self, request, uuid=None, user_uuid: str | None = None):
        team = self.get_object()
        serializer = TeamMemberRemovalSerializer(
            data={"user": user_uuid},
            context={"request": request, "team": team},
        )
        serializer.is_valid(raise_exception=True)
        serializer.remove()
        return Response(status=status.HTTP_204_NO_CONTENT)


__all__ = ["TeamViewSet"]

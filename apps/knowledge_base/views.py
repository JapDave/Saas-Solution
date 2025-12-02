from __future__ import annotations

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.common.exceptions import CustomError, KB_COLLECTION_NOT_FOUND, KB_DUPLICATE_RESOURCE, KB_RESOURCE_NOT_FOUND
from apps.common.serializers import ErrorSerializer
from apps.knowledge_base.models import Collection, Resource
from apps.knowledge_base.serializers import (
    CollectionReadSerializer,
    CollectionWriteSerializer,
    ResourceCreateSerializer,
    ResourceMoveSerializer,
    ResourceReadSerializer,
)
from apps.knowledge_base.services import (
    ensure_kb_permission,
    enforce_collection_limit,
    enforce_resource_limit,
)
from apps.organizations.models import Organization


@extend_schema(
    tags=["Knowledge Base"],
    responses={400: ErrorSerializer, 403: ErrorSerializer, 404: ErrorSerializer, 500: ErrorSerializer},
    description=(
        "Knowledge base collections within an organization.\n\n"
        "Permissions:\n"
        "- List/Read: kb:collections:read\n"
        "- Create: kb:collections:create\n"
        "- Update: kb:collections:update\n"
        "- Delete: kb:collections:delete\n"
        "- Archive/Restore: kb:collections:archive/restore\n"
    ),
)
class CollectionViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    lookup_field = "uuid"

    def _organization(self):
        if not hasattr(self, "_cached_org"):
            self._cached_org = get_object_or_404(Organization, uuid=self.kwargs["organization_uuid"])
        return self._cached_org

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Collection.objects.none()
        organization = self._organization()
        qs = Collection.objects.filter(organization=organization).prefetch_related("resources")
        state = self.request.query_params.get("state")
        if state:
            qs = qs.filter(state=state)
        search = self.request.query_params.get("name")
        if search:
            qs = qs.filter(name__icontains=search.strip())
        return qs.order_by("name")

    def get_serializer_class(self):
        if self.action in {"create", "update", "partial_update"}:
            return CollectionWriteSerializer
        return CollectionReadSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["organization"] = self._organization()
        return context

    def list(self, request, *args, **kwargs):
        ensure_kb_permission(request.user, self._organization(), "kb:collections:read")
        return super().list(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        ensure_kb_permission(request.user, self._organization(), "kb:collections:read")
        return super().retrieve(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        organization = self._organization()
        ensure_kb_permission(request.user, organization, "kb:collections:create")
        enforce_collection_limit(organization)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        collection = serializer.save(
            organization=organization,
            created_by=request.user,
            updated_by=request.user,
        )
        read = CollectionReadSerializer(collection, context=self.get_serializer_context())
        headers = self.get_success_headers(read.data)
        return Response(read.data, status=status.HTTP_201_CREATED, headers=headers)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        collection = self.get_object()
        ensure_kb_permission(request.user, collection.organization, "kb:collections:update")
        serializer = self.get_serializer(collection, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save(updated_by=request.user)
        collection.bump_version(actor=request.user)
        return Response(CollectionReadSerializer(collection).data)

    def destroy(self, request, *args, **kwargs):
        collection = self.get_object()
        ensure_kb_permission(request.user, collection.organization, "kb:collections:delete")
        collection.mark_deleted()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"], url_path="archive")
    def archive(self, request, *args, **kwargs):
        collection = self.get_object()
        ensure_kb_permission(request.user, collection.organization, "kb:collections:archive")
        collection.state = Collection.CollectionState.ARCHIVED
        collection.save(update_fields=["state", "updated_at"])
        return Response(CollectionReadSerializer(collection).data)

    @action(detail=True, methods=["post"], url_path="restore")
    def restore(self, request, *args, **kwargs):
        collection = self.get_object()
        ensure_kb_permission(request.user, collection.organization, "kb:collections:restore")
        collection.state = Collection.CollectionState.ACTIVE
        collection.deleted_at = None
        collection.save(update_fields=["state", "deleted_at", "updated_at"])
        return Response(CollectionReadSerializer(collection).data)


@extend_schema(
    tags=["Knowledge Base"],
    responses={400: ErrorSerializer, 403: ErrorSerializer, 404: ErrorSerializer, 500: ErrorSerializer},
    description=(
        "Knowledge base resources inside a collection.\n\n"
        "Permissions:\n"
        "- List/Read: kb:collections:read\n"
        "- Create: kb:resources:create\n"
        "- Delete: kb:resources:delete\n"
        "- Move/Copy: kb:resources:move / kb:resources:copy\n"
    ),
)
class ResourceViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    lookup_field = "uuid"

    def _collection(self) -> Collection:
        if not hasattr(self, "_cached_collection"):
            organization = get_object_or_404(Organization, uuid=self.kwargs["organization_uuid"])
            collection = get_object_or_404(Collection, organization=organization, uuid=self.kwargs["collection_uuid"])
            self._cached_org = organization
            self._cached_collection = collection
        return self._cached_collection

    def _organization(self):
        self._collection()
        return self._cached_org

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Resource.objects.none()
        collection = self._collection()
        ensure_kb_permission(self.request.user, collection.organization, "kb:collections:read")
        return collection.resources.all()

    def get_serializer_class(self):
        if self.action == "create":
            return ResourceCreateSerializer
        return ResourceReadSerializer

    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        collection = self._collection()
        ensure_kb_permission(request.user, collection.organization, "kb:resources:create")
        enforce_resource_limit(collection)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        file_uuid = serializer.validated_data["file_uuid"]
        if collection.resources.filter(file_uuid=file_uuid).exists():
            raise CustomError(code=KB_DUPLICATE_RESOURCE, status_code=400, detail="File already exists in collection.")
        resource = serializer.save(
            collection=collection,
            created_by=request.user,
            updated_by=request.user,
        )
        collection.bump_version(actor=request.user)
        read = ResourceReadSerializer(resource)
        return Response(read.data, status=status.HTTP_201_CREATED)

    def destroy(self, request, *args, **kwargs):
        collection = self._collection()
        ensure_kb_permission(request.user, collection.organization, "kb:resources:delete")
        instance = self.get_object()
        super().destroy(request, *args, **kwargs)
        collection.bump_version(actor=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)

    def perform_destroy(self, instance):
        instance.delete()

    def get_object(self):
        try:
            return super().get_object()
        except Exception:
            raise CustomError(code=KB_RESOURCE_NOT_FOUND, status_code=404, detail="Resource not found.")

    @action(detail=True, methods=["post"], url_path="move")
    def move(self, request, *args, **kwargs):
        resource = self.get_object()
        source = resource.collection
        ensure_kb_permission(request.user, source.organization, "kb:resources:move")
        serializer = ResourceMoveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        destination = get_object_or_404(
            Collection,
            organization=source.organization,
            uuid=serializer.validated_data["destination_collection_uuid"],
        )
        if destination.resources.filter(file_uuid=resource.file_uuid).exists():
            raise CustomError(code=KB_DUPLICATE_RESOURCE, status_code=400, detail="File already in destination.")
        enforce_resource_limit(destination)
        resource.collection = destination
        resource.updated_by = request.user
        resource.save(skip_file_refresh=True)
        source.bump_version(actor=request.user)
        destination.bump_version(actor=request.user)
        return Response(ResourceReadSerializer(resource).data)

    @action(detail=True, methods=["post"], url_path="copy")
    def copy(self, request, *args, **kwargs):
        resource = self.get_object()
        source = resource.collection
        ensure_kb_permission(request.user, source.organization, "kb:resources:copy")
        serializer = ResourceMoveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        destination = get_object_or_404(
            Collection,
            organization=source.organization,
            uuid=serializer.validated_data["destination_collection_uuid"],
        )
        if destination.resources.filter(file_uuid=resource.file_uuid).exists():
            raise CustomError(code=KB_DUPLICATE_RESOURCE, status_code=400, detail="File already in destination.")
        enforce_resource_limit(destination)
        new_resource = Resource.objects.create(
            collection=destination,
            file_uuid=resource.file_uuid,
            file_type=resource.file_type,
            resource_type=resource.resource_type,
            title=resource.title,
            summary=resource.summary,
            is_broken_reference=resource.is_broken_reference,
            created_by=request.user,
            updated_by=request.user,
        )
        destination.bump_version(actor=request.user)
        return Response(ResourceReadSerializer(new_resource).data, status=status.HTTP_201_CREATED)

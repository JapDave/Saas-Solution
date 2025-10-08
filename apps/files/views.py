# Django/DRF imports
import hashlib
from django.db.models import Q

from rest_framework import viewsets
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema

# Project imports
from apps.common.exceptions import OrganizationNotFound

from apps.files.models import File
from apps.files.serializers import FileSerializer

from apps.organizations.models import Organization

from apps.roles.permissions import HasPermission

@extend_schema(tags=["Files"])
class FileViewSet(
    viewsets.mixins.CreateModelMixin,
    viewsets.mixins.DestroyModelMixin,
    viewsets.mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """
    API endpoint for file management.

    Provides actions for:
    - Uploading (create)
    - Accessing metadata (retrieve)
    - Versioning (create_version, versions)
    - Deleting (destroy)
    """
    queryset = File.objects.all()
    serializer_class = FileSerializer
    lookup_field = "uuid"

    def get_permissions(self):
        """
        Set permissions based on action.
        """
        organization_uuid = self.kwargs.get("organization_uuid")
        if self.action in ["list", "versions"]:
            permission = "files:read"
        elif self.action in ["create", "create_version"]:
            permission = "files:upload"
        elif self.action in ["destroy", "recover"]:
            permission = "files:delete"

        return [
            HasPermission(
                permission_key=permission,
                organization_uuid=organization_uuid
            )
        ]

    def get_queryset(self):
        """
        Filter files to only show those belonging to the user's organization,
        unless they are public.
        """
        user = self.request.user
        organization_uuid = self.kwargs.get("organization_uuid")
        queryset = File.objects.filter(
            Q(organization__uuid=organization_uuid)
        )

        # for non authenticated users return only public files
        if not user.is_authenticated:
            return queryset.filter(is_public=True)

        return queryset

    def perform_create(self, serializer):
        """
        REQ-FILES-001: File Upload
        Set user, organization, hash, and other auto-generated fields on upload.
        """

        try:
            organization = Organization.objects.get(uuid=self.kwargs["organization_uuid"])
            
            uploaded_file = self.request.FILES.get('file')
           # Calculate hash
            sha256_hash = hashlib.sha256()
            for chunk in uploaded_file.chunks():
                sha256_hash.update(chunk)
            file_hash = sha256_hash.hexdigest()

            # TODO: Implement actual file transfer to storage (e.g., S3)
            # storage_path = save_to_cloud_storage(uploaded_file)

            serializer.save(
                organization=organization,
                uploaded_by=self.request.user,
                size=uploaded_file.size,
                hash=file_hash,
            )
        except Organization.DoesNotExist:
            raise OrganizationNotFound()

    @action(detail=True, methods=['post'], url_path='create-version')
    def create_version(self, request, organization_uuid, uuid=None):
        """
        REQ-FILES-003: File Versioning
        Upload a new version of an existing file.
        """
        parent_file = self.get_object()
        # TODO: Add check for max versions (e.g., 50)

        # Use the main serializer for validation and creation logic
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Manually trigger perform_create logic for the new version
        self.perform_create(serializer)

        # Link the new file to the parent
        new_version = serializer.instance
        new_version.parent_file = parent_file
        new_version.version = parent_file.version + 1
        new_version.save()

        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'])
    def versions(self, request, organization_uuid, uuid):
        """REQ-FILES-003: List all versions of a file."""
        file = self.get_object()
        # This is a simplified history; a full implementation might trace back the whole chain
        version_queryset = File.objects.filter(
            Q(id=file.id) | Q(parent_file_id=file.id)
        ).order_by('-version')
        serializer = FileSerializer(version_queryset, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def recover(self, request, organization_uuid, uuid=None):
        """REQ-FILES-004: Recover a soft-deleted file."""
        # Read all files including deleted ones
        try:
            
            file = File.all_objects.get(
                uuid=uuid,
                organization__uuid=organization_uuid
            )
            if not file.deleted_at:
                return Response(
                    data={
                        "detail": "File is not deleted."
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            file.deleted_at = None
            file.save()
            return Response({"status": "file recovered"}, status=status.HTTP_200_OK)

        except File.DoesNotExist:
            data= {
                    "detail": "File not found."
                }
            return Response(
                data=data,
                status=status.HTTP_404_NOT_FOUND
            )

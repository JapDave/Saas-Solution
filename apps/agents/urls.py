from django.urls import path

from apps.agents.views import AgentViewSet


agent_list = AgentViewSet.as_view({"get": "list", "post": "create"})
agent_detail = AgentViewSet.as_view({"get": "retrieve", "patch": "partial_update", "delete": "destroy"})
agent_activate = AgentViewSet.as_view({"post": "activate"})
agent_archive = AgentViewSet.as_view({"post": "archive"})
agent_restore = AgentViewSet.as_view({"post": "restore"})
agent_clone = AgentViewSet.as_view({"post": "clone"})
agent_versions = AgentViewSet.as_view({"get": "versions", "post": "versions"})
agent_version_detail = AgentViewSet.as_view({"get": "version_detail", "put": "version_update"})
agent_version_switch = AgentViewSet.as_view({"post": "version_switch"})
agent_version_switch_number = AgentViewSet.as_view({"post": "switch_version_number"})


urlpatterns = [
    path("agents/organizations/<uuid:organization_id>/", agent_list, name="agents-list"),
    path(
        "agents/organizations/<uuid:organization_id>/<uuid:agent_id>/",
        agent_detail,
        name="agents-detail",
    ),
    path(
        "agents/organizations/<uuid:organization_id>/<uuid:agent_id>/activate/",
        agent_activate,
        name="agents-activate",
    ),
    path(
        "agents/organizations/<uuid:organization_id>/<uuid:agent_id>/archive/",
        agent_archive,
        name="agents-archive",
    ),
    path(
        "agents/organizations/<uuid:organization_id>/<uuid:agent_id>/restore/",
        agent_restore,
        name="agents-restore",
    ),
    path(
        "agents/organizations/<uuid:organization_id>/<uuid:agent_id>/clone/",
        agent_clone,
        name="agents-clone",
    ),
    path(
        "agents/organizations/<uuid:organization_id>/<uuid:agent_id>/versions/",
        agent_versions,
        name="agents-versions",
    ),
    path(
        "agents/organizations/<uuid:organization_id>/<uuid:agent_id>/versions/<uuid:version_uuid>/",
        agent_version_detail,
        name="agents-version-detail",
    ),
    path(
        "agents/organizations/<uuid:organization_id>/<uuid:agent_id>/versions/<uuid:version_uuid>/switch/",
        agent_version_switch,
        name="agents-version-switch",
    ),
    path(
        "agents/organizations/<uuid:organization_id>/<uuid:agent_id>/switch-version/",
        agent_version_switch_number,
        name="agents-version-switch-number",
    ),
]

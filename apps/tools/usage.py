from __future__ import annotations

from collections import defaultdict

from apps.agents.models import Agent


def agents_usage_by_tool_keys(org, tool_keys: list[str]) -> dict[str, int]:
    if not tool_keys:
        return {}
    usage = defaultdict(int)
    qs = Agent.objects.filter(organization=org, deleted_at__isnull=True).select_related("current_version")
    for agent in qs:
        version = agent.current_version
        if not version:
            continue
        cfg = version.tools_configuration or []
        if isinstance(cfg, dict) and "tools" in cfg:
            cfg = cfg.get("tools") or []
        for entry in cfg:
            try:
                key = entry.get("toolKey") or entry.get("tool_key")
            except AttributeError:
                continue
            if key in tool_keys:
                usage[key] += 1
    return dict(usage)

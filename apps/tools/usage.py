from __future__ import annotations

from collections import defaultdict

from apps.agents.models import Agent


def agents_usage_by_tool_keys(org, tool_keys: list[str]) -> dict[str, int]:
    if not tool_keys:
        return {}
    usage = defaultdict(int)
    qs = Agent.objects.filter(organization=org, deleted_at__isnull=True).values_list("tools_configuration", flat=True)
    for cfg in qs:
        if not cfg:
            continue
        for entry in cfg:
            try:
                key = entry.get("toolKey") or entry.get("tool_key")
            except AttributeError:
                continue
            if key in tool_keys:
                usage[key] += 1
    return dict(usage)

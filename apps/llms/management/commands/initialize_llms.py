from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.llms.models import LLMDefinition


class Command(BaseCommand):
    help = "Initialize LLMDefinition records from a JSON catalog (default: apps/llms/fixtures/llms_list.json)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--path",
            type=str,
            default="apps/llms/fixtures/llms_list.json",
            help="Path to the llms-list JSON file (default: apps/llms/fixtures/llms_list.json)",
        )
        parser.add_argument(
            "--truncate",
            action="store_true",
            help="Delete existing LLMDefinition rows before seeding",
        )
        parser.add_argument(
            "--debug-only",
            action="store_true",
            help="Only run when settings.DEBUG is True (otherwise abort).",
        )

    def handle(self, *args, **options):
        if options["debug_only"] and not settings.DEBUG:
            self.stdout.write(self.style.WARNING("DEBUG-only seeding skipped because DEBUG is False."))
            return

        path = Path(options["path"]).resolve()
        if not path.exists():
            raise CommandError(f"File not found: {path}")

        if options["truncate"]:
            deleted, _ = LLMDefinition.objects.all().delete()
            self.stdout.write(self.style.WARNING(f"Truncated LLMDefinition table (deleted {deleted} rows)."))

        with path.open("r", encoding="utf-8") as f:
            payload: dict[str, Any] = json.load(f)

        llms = payload.get("llms")
        if not isinstance(llms, list):
            raise CommandError("Invalid format: expected top-level 'llms' list")

        created = 0
        updated = 0
        for item in llms:
            model_key = item.get("modelKey")
            if not model_key:
                continue

            defaults = {
                "model_provider": item.get("modelProvider", ""),
                "display_name": item.get("displayName", model_key),
                "description": item.get("description", ""),
                "supported_modalities": item.get("supportedModalities", []),
                "max_context_tokens": item.get("maxContextTokens"),
                "model_configuration": item.get("modelConfiguration", {}),
            }

            obj, is_created = LLMDefinition.objects.update_or_create(
                model_key=model_key,
                defaults=defaults,
            )
            if is_created:
                created += 1
            else:
                updated += 1

        self.stdout.write(self.style.SUCCESS(f"Initialized LLMDefinition: created={created}, updated={updated}, source={path}"))

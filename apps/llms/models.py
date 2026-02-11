from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.common.models import BaseModel


class LLMDefinition(BaseModel):
    """Catalog of available LLMs and their configuration schemas."""

    model_provider = models.CharField(_("Model provider"), max_length=100)
    model_key = models.CharField(_("Model key"), max_length=100, unique=True)
    display_name = models.CharField(_("Display name"), max_length=200)
    description = models.TextField(_("Description"), blank=True, default="")
    supported_modalities = models.JSONField(_("Supported modalities"), default=list, blank=True)
    max_context_tokens = models.PositiveIntegerField(_("Max context tokens"), null=True, blank=True)
    model_configuration = models.JSONField(_("Model configuration"), default=dict)

    class Meta:
        ordering = ["model_provider", "model_key"]
        indexes = [
            models.Index(fields=["model_provider"], name="ix_llm_provider"),
            models.Index(fields=["model_key"], name="ix_llm_key"),
        ]

    def __str__(self) -> str:  # pragma: no cover - representation only
        return f"{self.model_provider}:{self.model_key}"

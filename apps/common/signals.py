from __future__ import annotations

from typing import Any

from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models
from django.db.models.signals import post_delete, post_save, pre_save

from apps.common.audit import (
    get_audit_context,
    mask_sensitive,
    serialize_value,
)
from apps.common.models import DataChangeLog


IGNORED_FIELDS = {"updated_at", "created_at", "last_login"}
DEFAULT_EXCLUDED_APPS = {"admin", "auth", "contenttypes", "sessions"}


def _normalize_model_label(model: type[models.Model]) -> str:
    return f"{model._meta.app_label}.{model.__name__}".lower()


def _get_tracked_models() -> set[str] | None:
    raw = getattr(settings, "AUDIT_TRACKED_MODELS", "*") or "*"
    raw = str(raw).strip()
    if raw == "*":
        return None
    return {item.strip().lower() for item in raw.split(",") if item.strip()}


def _get_excluded_models() -> set[str]:
    raw = getattr(settings, "AUDIT_EXCLUDED_MODELS", [])
    if isinstance(raw, str):
        raw = [item.strip() for item in raw.split(",") if item.strip()]
    return {item.lower() for item in raw}


def _is_tracked_model(model: type[models.Model]) -> bool:
    app_label = model._meta.app_label
    if app_label in DEFAULT_EXCLUDED_APPS:
        return False
    model_label = _normalize_model_label(model)
    excluded = _get_excluded_models()
    if model_label in excluded:
        return False
    tracked = _get_tracked_models()
    if tracked is None:
        return True
    return model_label in tracked


def _get_value(instance: models.Model, field: models.Field) -> Any:
    if field.is_relation and field.many_to_one:
        return getattr(instance, field.attname, None)
    return field.value_from_object(instance)


def _build_changed_fields(
    *,
    previous: models.Model | None,
    instance: models.Model,
    created: bool,
) -> dict[str, dict[str, Any]]:
    changed: dict[str, dict[str, Any]] = {}
    for field in instance._meta.fields:
        if field.name in IGNORED_FIELDS:
            continue
        new_value = serialize_value(_get_value(instance, field))
        old_value = None if created or not previous else serialize_value(_get_value(previous, field))
        if created:
            if new_value is None and field.null:
                continue
        else:
            if old_value == new_value:
                continue
        changed[field.name] = {
            "old": mask_sensitive(old_value, field_name=field.name),
            "new": mask_sensitive(new_value, field_name=field.name),
        }
    return changed


def _infer_action(previous: models.Model | None, instance: models.Model, created: bool) -> str:
    if created:
        return "create"
    if previous and hasattr(previous, "deleted_at") and hasattr(instance, "deleted_at"):
        prev_deleted = getattr(previous, "deleted_at", None)
        curr_deleted = getattr(instance, "deleted_at", None)
        if prev_deleted and not curr_deleted:
            return "restore"
        if not prev_deleted and curr_deleted:
            return "delete"
    return "update"


def _resolve_actor(instance: models.Model, context, audit_log) -> Any | None:
    if context and context.user:
        return context.user
    if audit_log and getattr(audit_log, "user", None):
        return audit_log.user
    for attr in ("updated_by", "created_by", "enabled_by", "disabled_by", "assigned_by", "user"):
        if hasattr(instance, attr):
            value = getattr(instance, attr, None)
            if value is not None:
                return value
    return _get_system_user()


def _get_system_user():
    user_model = get_user_model()
    email = getattr(settings, "AUDIT_SYSTEM_USER_EMAIL", "") or ""
    if not email:
        return user_model.objects.filter(is_superuser=True).order_by("id").first()
    try:
        user = user_model.objects.filter(email=email).first()
        if user:
            return user
        return user_model.objects.create_user(email=email, password=None, is_active=True)
    except Exception:
        return None


def _resolve_object_id(instance: models.Model) -> str:
    return str(getattr(instance, "uuid", None) or getattr(instance, "pk", None) or "")


def _log_change(instance: models.Model, *, created: bool) -> None:
    model = type(instance)
    if not _is_tracked_model(model):
        return
    previous = getattr(instance, "_audit_previous", None)
    action = _infer_action(previous, instance, created)
    changed_fields = _build_changed_fields(previous=previous, instance=instance, created=created)
    if not changed_fields:
        return

    context = get_audit_context()
    audit_log = context.audit_log
    user = _resolve_actor(instance, context, audit_log)
    trace_id = context.trace_id or getattr(audit_log, "trace_id", None)
    span_id = context.span_id or getattr(audit_log, "span_id", None)
    summary = ", ".join(changed_fields.keys())[:255]

    DataChangeLog.objects.create(
        audit_log=audit_log,
        user=user,
        app_label=model._meta.app_label,
        model_name=model.__name__,
        object_id=_resolve_object_id(instance),
        action=action,
        changed_fields=changed_fields,
        changed_fields_summary=summary,
        trace_id=trace_id,
        span_id=span_id,
        extra={},
    )


def _capture_pre_save(sender, instance: models.Model, **kwargs) -> None:
    if not _is_tracked_model(sender):
        return
    if not instance.pk:
        instance._audit_previous = None
        return
    try:
        instance._audit_previous = sender._default_manager.filter(pk=instance.pk).first()
    except Exception:
        instance._audit_previous = None


def _capture_post_save(sender, instance: models.Model, created: bool, **kwargs) -> None:
    _log_change(instance, created=created)


def _capture_post_delete(sender, instance: models.Model, **kwargs) -> None:
    if not _is_tracked_model(sender):
        return
    context = get_audit_context()
    audit_log = context.audit_log
    user = _resolve_actor(instance, context, audit_log)
    trace_id = context.trace_id or getattr(audit_log, "trace_id", None)
    span_id = context.span_id or getattr(audit_log, "span_id", None)

    DataChangeLog.objects.create(
        audit_log=audit_log,
        user=user,
        app_label=sender._meta.app_label,
        model_name=sender.__name__,
        object_id=_resolve_object_id(instance),
        action="delete",
        changed_fields={},
        changed_fields_summary="",
        trace_id=trace_id,
        span_id=span_id,
        extra={},
    )


def register_audit_signals() -> None:
    for model in apps.get_models():
        if not _is_tracked_model(model):
            continue
        pre_save.connect(
            _capture_pre_save,
            sender=model,
            weak=False,
            dispatch_uid=f"audit_pre_save_{model._meta.label_lower}",
        )
        post_save.connect(
            _capture_post_save,
            sender=model,
            weak=False,
            dispatch_uid=f"audit_post_save_{model._meta.label_lower}",
        )
        post_delete.connect(
            _capture_post_delete,
            sender=model,
            weak=False,
            dispatch_uid=f"audit_post_delete_{model._meta.label_lower}",
        )

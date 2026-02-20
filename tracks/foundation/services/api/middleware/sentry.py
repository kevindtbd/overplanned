"""
Sentry instrumentation for the FastAPI service.
Server-side only. Strips sensitive headers from breadcrumbs.
"""

from typing import Any

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

from services.api.config import settings

SENSITIVE_HEADERS = {"authorization", "cookie", "set-cookie"}


def _strip_sensitive_data(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any] | None:
    """before_send hook: strip Authorization headers and cookies from breadcrumbs."""
    if "breadcrumbs" in event:
        for breadcrumb in event["breadcrumbs"].get("values", []):
            data = breadcrumb.get("data", {})
            if isinstance(data, dict):
                headers = data.get("headers", {})
                if isinstance(headers, dict):
                    for key in list(headers.keys()):
                        if key.lower() in SENSITIVE_HEADERS:
                            headers[key] = "[FILTERED]"
    # Also strip from request data
    request = event.get("request", {})
    if isinstance(request, dict):
        headers = request.get("headers", {})
        if isinstance(headers, dict):
            for key in list(headers.keys()):
                if key.lower() in SENSITIVE_HEADERS:
                    headers[key] = "[FILTERED]"
    return event


def setup_sentry() -> None:
    if not settings.sentry_dsn:
        return

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        release=f"{settings.app_name}@{settings.app_version}",
        traces_sample_rate=settings.sentry_traces_sample_rate,
        before_send=_strip_sensitive_data,
        integrations=[
            StarletteIntegration(transaction_style="endpoint"),
            FastApiIntegration(transaction_style="endpoint"),
        ],
        send_default_pii=False,
    )

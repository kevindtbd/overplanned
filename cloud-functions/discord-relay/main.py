"""Cloud Function: relay GCP Monitoring alerts to Discord webhook."""

import json
import os

import functions_framework
import requests

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")

COLOR_MAP = {
    "CRITICAL": 0xDC3545,
    "ERROR": 0xC4694F,
    "WARNING": 0xFFC107,
    "OK": 0x28A745,
}


@functions_framework.http
def relay(request):
    """Receive GCP alerting webhook, reformat, POST to Discord."""
    if not DISCORD_WEBHOOK_URL:
        return "DISCORD_WEBHOOK_URL not set", 500

    try:
        payload = request.get_json(silent=True) or {}
    except Exception:
        return "Bad JSON", 400

    incident = payload.get("incident", {})
    state = incident.get("state", "unknown")
    policy_name = incident.get("policy_name", "Unknown Alert")
    condition_name = incident.get("condition_name", "")
    summary = incident.get("summary", "No summary")
    url = incident.get("url", "")

    color = COLOR_MAP.get("OK" if state == "closed" else "ERROR", 0xC4694F)
    title = f"{'Resolved' if state == 'closed' else 'Firing'}: {policy_name}"

    embed = {
        "title": title[:256],
        "description": summary[:2000],
        "color": color,
        "fields": [],
    }

    if condition_name:
        embed["fields"].append(
            {"name": "Condition", "value": condition_name[:256], "inline": True}
        )

    if url:
        embed["fields"].append(
            {"name": "Link", "value": f"[View in GCP]({url})", "inline": True}
        )

    resp = requests.post(
        DISCORD_WEBHOOK_URL,
        json={"embeds": [embed]},
        timeout=10,
    )
    resp.raise_for_status()

    return "OK", 200

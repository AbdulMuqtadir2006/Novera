"""Meta (Facebook) WhatsApp Cloud API — send + message composition.

When Meta isn't configured (or `simulate=True`), messages are logged and
returned instead of sent, so the whole flow is testable without a live
number. Ported 1:1 from the old novera_ai/whatsapp.py.
"""
from __future__ import annotations

from typing import Any, Optional

import requests

from .. import config


def _normalize(to: str) -> str:
    """Meta wants a bare E.164 number: no `whatsapp:` prefix, no leading `+`."""
    to = to.strip()
    if to.startswith("whatsapp:"):
        to = to[len("whatsapp:"):]
    return to.lstrip("+")


def send_message(body: str, to: Optional[str] = None, simulate: bool = False) -> dict[str, Any]:
    to = to or config.WHATSAPP_TO
    if simulate or not config.WHATSAPP_ENABLED or not to:
        reason = "simulate" if simulate else ("meta_not_configured" if not config.WHATSAPP_ENABLED else "no_recipient")
        print(f"[whatsapp:simulated:{reason}] -> {to or '(no recipient)'}\n{body}\n")
        return {"delivered": False, "simulated": True, "reason": reason, "to": to, "body": body}

    url = f"https://graph.facebook.com/{config.META_API_VERSION}/{config.META_PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {config.META_WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp",
        "to": _normalize(to),
        "type": "text",
        "text": {"preview_url": False, "body": body},
    }
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        message_id = (data.get("messages") or [{}])[0].get("id")
        return {"delivered": True, "simulated": False, "message_id": message_id, "to": to}
    except Exception as exc:
        detail = getattr(getattr(exc, "response", None), "text", str(exc))
        print(f"[whatsapp] send failed: {detail}")
        # Bug fix (2026-08-22): this was returning simulated=True on a genuine
        # attempted-and-failed send, mislabeling it the same as a deliberate/
        # not-configured no-op — inconsistent with send_document and
        # send_template_message below, which both correctly report
        # simulated=False for the equivalent real-failure case.
        return {"delivered": False, "simulated": False, "reason": detail, "to": to, "body": body}


def send_document(
    pdf_bytes: bytes, filename: str, caption: str = "", to: Optional[str] = None, simulate: bool = False
) -> dict[str, Any]:
    """Sends a PDF as a WhatsApp document message. Two real API calls under the
    hood — Meta requires uploading the file first (POST .../media) to get a
    media_id, then referencing that media_id in a document message — there's
    no way to attach raw bytes directly to a message the way `to`/`text` work
    in send_message()."""
    to = to or config.WHATSAPP_TO
    if simulate or not config.WHATSAPP_ENABLED or not to:
        reason = "simulate" if simulate else ("meta_not_configured" if not config.WHATSAPP_ENABLED else "no_recipient")
        print(f"[whatsapp:simulated:{reason}] -> {to or '(no recipient)'}\n[document: {filename}, {len(pdf_bytes)} bytes]\n")
        return {"delivered": False, "simulated": True, "reason": reason, "to": to}

    headers = {"Authorization": f"Bearer {config.META_WHATSAPP_TOKEN}"}
    try:
        upload_url = f"https://graph.facebook.com/{config.META_API_VERSION}/{config.META_PHONE_NUMBER_ID}/media"
        upload_resp = requests.post(
            upload_url,
            headers=headers,
            files={"file": (filename, pdf_bytes, "application/pdf")},
            data={"messaging_product": "whatsapp", "type": "application/pdf"},
            timeout=30,
        )
        upload_resp.raise_for_status()
        media_id = upload_resp.json()["id"]

        send_url = f"https://graph.facebook.com/{config.META_API_VERSION}/{config.META_PHONE_NUMBER_ID}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "to": _normalize(to),
            "type": "document",
            "document": {"id": media_id, "filename": filename, **({"caption": caption} if caption else {})},
        }
        send_resp = requests.post(send_url, headers={**headers, "Content-Type": "application/json"}, json=payload, timeout=30)
        send_resp.raise_for_status()
        data = send_resp.json()
        message_id = (data.get("messages") or [{}])[0].get("id")
        return {"delivered": True, "simulated": False, "message_id": message_id, "to": to}
    except Exception as exc:
        detail = getattr(getattr(exc, "response", None), "text", str(exc))
        print(f"[whatsapp] document send failed: {detail}")
        return {"delivered": False, "simulated": False, "reason": detail, "to": to}


def send_template_message(
    template_name: str,
    variables: list[str],
    to: Optional[str] = None,
    lang_code: str = "en",
    simulate: bool = False,
) -> dict[str, Any]:
    """Sends a pre-approved Meta message template — the only send mechanism
    allowed for business-initiated messages outside the 24h customer-service
    window (spec §5). `template_name` must exactly match a template already
    created AND approved in Meta Business Manager, with a body that has as
    many {{1}}, {{2}}... placeholders as `variables` has entries, in order —
    this function does not create or validate templates, it only invokes an
    already-approved one. If the named template doesn't exist/isn't approved
    yet, Meta's API call fails and this degrades the same way send_message
    does on any other failure (logged, simulated result returned) rather than
    raising — see whatsapp_templates.py for the 5 templates this project
    needs submitted for approval before proactive outreach can work outside
    the 24h window."""
    to = to or config.WHATSAPP_TO
    if simulate or not config.WHATSAPP_ENABLED or not to:
        reason = "simulate" if simulate else ("meta_not_configured" if not config.WHATSAPP_ENABLED else "no_recipient")
        print(f"[whatsapp:simulated:{reason}] -> {to or '(no recipient)'}\n[template: {template_name}, vars={variables}]\n")
        return {"delivered": False, "simulated": True, "reason": reason, "to": to, "template_name": template_name}

    url = f"https://graph.facebook.com/{config.META_API_VERSION}/{config.META_PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {config.META_WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp",
        "to": _normalize(to),
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": lang_code},
            "components": (
                [{"type": "body", "parameters": [{"type": "text", "text": v} for v in variables]}]
                if variables else []
            ),
        },
    }
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        message_id = (data.get("messages") or [{}])[0].get("id")
        return {"delivered": True, "simulated": False, "message_id": message_id, "to": to, "template_name": template_name}
    except Exception as exc:
        detail = getattr(getattr(exc, "response", None), "text", str(exc))
        print(f"[whatsapp] template send failed ({template_name}): {detail}")
        return {"delivered": False, "simulated": False, "reason": detail, "to": to, "template_name": template_name}


def offer_message(case_id: Optional[str] = None) -> str:
    ref = f" (ref {case_id})" if case_id else ""
    return (
        "NOVERA screening update: your latest saliva reading suggests a follow-up would be worthwhile"
        f"{ref}.\n\n"
        f"Would you like me to book an appointment at {config.CLINIC_NAME}, {config.CLINIC_BRANCH}?\n"
        "Reply *OK* to confirm, or *NO* to skip."
    )


def confirmation_message(booking: dict[str, Any]) -> str:
    loc = booking["location"]
    note = ""
    if booking["reason"] == "doctor_on_break":
        note = "The doctor is currently on break, so I booked the next available morning slot.\n"
    elif booking["reason"] in ("after_closing", "slot_rolls_into_break_or_close"):
        note = "That fell outside clinic hours, so I booked the next morning slot.\n"
    return (
        f"✅ Your appointment at {loc['name']}, {loc['branch']} is booked.\n\n"
        f"🗓 {booking['when_human']}\n"
        f"{note}"
        f"📍 {loc['address']}\n"
        f"🗺 {loc['maps_url']}\n"
        f"☎ {loc['phone']}\n\n"
        "Please arrive 10 minutes early. Reply RESCHEDULE if the time doesn't work."
    )


def cancellation_message(booking: dict[str, Any]) -> str:
    loc = booking["location"]
    return (
        f"❌ Your appointment at {loc['name']}, {loc['branch']} on {booking['when_human']} "
        "has been cancelled.\n\nMessage me any time and I'll book a new one."
    )


def reschedule_message(old_booking: dict[str, Any], new_booking: dict[str, Any]) -> str:
    loc = new_booking["location"]
    return (
        f"✅ Your appointment has been moved from {old_booking['when_human']} to "
        f"{new_booking['when_human']} at {loc['name']}, {loc['branch']}.\n\n"
        f"📍 {loc['address']}\n"
        f"🗺 {loc['maps_url']}\n"
        f"☎ {loc['phone']}\n\n"
        "Please arrive 10 minutes early. Message me again if you need to change it further."
    )

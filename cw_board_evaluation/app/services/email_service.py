"""
app.services.email_service
--------------------------
Development-friendly email sender for invitations.

This module is designed to work with a local SMTP catcher such as Mailpit
for safe dev testing (emails are captured, not delivered externally).

Environment variables:
- EMAIL_ENABLED=true|false
- EMAIL_FROM="Name <email@domain>"
- SMTP_HOST=localhost
- SMTP_PORT=1025
- SMTP_USERNAME= (optional)
- SMTP_PASSWORD= (optional)
- SMTP_USE_TLS=true|false (usually false for Mailpit)

Usage:
    ok, err = send_invite_email(
        to_email="user@example.com",
        full_name="User Name",
        portal_url="http://localhost:5173/member/<token>/questions",
        tenant_name="ACME Inc",
        evaluation_id="eval-1234",
    )
"""

from __future__ import annotations

import html
import os
import smtplib
from email.message import EmailMessage
from typing import Any, Dict, List, Optional, Tuple


def _env_bool(name: str, default: bool = False) -> bool:
    """
    Read a boolean-like environment variable safely.

    Accepts: 1/0, true/false, yes/no, on/off (case-insensitive).
    """
    raw = (os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _smtp_config() -> dict:
    """
    Return SMTP configuration from environment variables.
    """
    return {
        "enabled": _env_bool("EMAIL_ENABLED", default=False),
        "from_addr": (os.getenv("EMAIL_FROM") or "Crest & Waterfalls <no-reply@cw.local>").strip(),
        "host": (os.getenv("SMTP_HOST") or "localhost").strip(),
        "port": int(os.getenv("SMTP_PORT") or "1025"),
        "username": (os.getenv("SMTP_USERNAME") or "").strip(),
        "password": (os.getenv("SMTP_PASSWORD") or "").strip(),
        "use_tls": _env_bool("SMTP_USE_TLS", default=False),
    }


def _build_invite_email_html(
    full_name: Optional[str],
    portal_url: str,
    tenant_name: Optional[str],
    evaluation_id: str,
    hub_url: str = "",
) -> str:
    """
    Build a simple HTML email body for participant invites.

    hub_url opens the member task hub (all assignments). portal_url may be the first
    assignment questionnaire or empty when tasks are not generated yet.
    """
    hello = f"Hello {full_name}," if full_name else "Hello,"
    tenant_line = f"<p><b>Client:</b> {tenant_name}</p>" if tenant_name else ""
    hub = (hub_url or "").strip()
    task = (portal_url or "").strip()

    link_block = ""
    if hub:
        hub_esc = html.escape(hub, quote=True)
        hub_body = html.escape(hub, quote=False)
        link_block += f"""
      <p>
        <a href="{hub_esc}" style="
          display:inline-block;
          padding:10px 14px;
          border-radius:10px;
          text-decoration:none;
          font-weight:700;
          border:1px solid #0f172a;
          color:#0f172a;
        ">View my assessment tasks</a>
      </p>
      <p style="font-size: 12px; color: #64748b;">
        Personal hub link (bookmark this):<br/>
        <span style="font-family: monospace;">{hub_body}</span>
      </p>
"""
    if task:
        task_esc = html.escape(task, quote=True)
        task_body = html.escape(task, quote=False)
        link_block += f"""
      <p style="margin-top: 14px;">
        <a href="{task_esc}" style="
          display:inline-block;
          padding:10px 14px;
          border-radius:10px;
          text-decoration:none;
          font-weight:700;
          border:1px solid #64748b;
          color:#0f172a;
        ">Open a questionnaire task</a>
      </p>
      <p style="font-size: 12px; color: #64748b;">
        Direct task link:<br/>
        <span style="font-family: monospace;">{task_body}</span>
      </p>
"""
    if not hub and not task:
        link_block = """
      <p>
        You are registered for this evaluation. Your consultant will enable assessment tracks and
        generate your questionnaire task(s). When that happens, you will receive <b>another email</b>
        with your personal link(s), unless they share the link with you another way.
      </p>
"""
    elif hub and not task:
        link_block += """
      <p style="font-size: 13px; color: #64748b;">
        Your hub is ready; individual questionnaire tasks will appear there once your consultant
        generates assignments.
      </p>
"""

    return f"""
    <div style="font-family: Arial, sans-serif; line-height: 1.4;">
      <h2>Crest & Waterfalls — Board Evaluation</h2>
      <p>{hello}</p>
      <p>You have been invited to complete a board evaluation.</p>
      {tenant_line}
      <p><b>Evaluation ID:</b> {evaluation_id}</p>
{link_block}
    </div>
    """.strip()


def send_invite_email(
    to_email: str,
    full_name: Optional[str],
    portal_url: str,
    evaluation_id: str,
    tenant_name: Optional[str] = None,
    hub_url: str = "",
) -> Tuple[bool, Optional[str]]:
    """
    Send a participant invite email via SMTP.

    Returns:
        (ok, error_message)

    Notes:
    - In dev (Mailpit), this sends to localhost:1025 and shows in Mailpit UI.
    - If EMAIL_ENABLED is false, it will skip sending and return (True, None)
      to avoid breaking flows during local development.
    """
    cfg = _smtp_config()

    if not cfg["enabled"]:
        return True, None

    to_email = (to_email or "").strip()
    if not to_email:
        return False, "to_email is required"

    msg = EmailMessage()
    msg["Subject"] = f"Board Evaluation Invite ({evaluation_id})"
    msg["From"] = cfg["from_addr"]
    msg["To"] = to_email

    html = _build_invite_email_html(
        full_name=full_name,
        portal_url=portal_url,
        tenant_name=tenant_name,
        evaluation_id=evaluation_id,
        hub_url=hub_url,
    )
    hub = (hub_url or "").strip()
    task = (portal_url or "").strip()
    if hub and task:
        plain = f"View all tasks: {hub}\nOpen a questionnaire: {task}"
    elif hub:
        plain = f"View your assessment tasks: {hub}"
    elif task:
        plain = f"Open your questionnaire: {task}"
    else:
        plain = (
            "You have been invited to a board evaluation. "
            "When your consultant generates your assessment task(s), you will receive another email with your link(s), "
            "unless they share the link another way."
        )
    msg.set_content(plain)
    msg.add_alternative(html, subtype="html")

    try:
        if cfg["use_tls"]:
            with smtplib.SMTP(cfg["host"], cfg["port"]) as s:
                s.starttls()
                if cfg["username"]:
                    s.login(cfg["username"], cfg["password"])
                s.send_message(msg)
        else:
            with smtplib.SMTP(cfg["host"], cfg["port"]) as s:
                if cfg["username"]:
                    s.login(cfg["username"], cfg["password"])
                s.send_message(msg)

        return True, None
    except Exception as e:
        return False, str(e)


from app.util.assignment_labels import assignment_link_label as _assignment_link_label


def _dedupe_display_labels(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """
    When several tasks share the same base label, suffix (2), (3), … so the email
    does not show duplicate headings.
    """
    counts: Dict[str, int] = {}
    out: List[Dict[str, str]] = []
    for row in rows:
        base = row["label"]
        n = counts.get(base, 0)
        counts[base] = n + 1
        display = base if n == 0 else f"{base} ({n + 1})"
        out.append({**row, "display_label": display})
    return out


def _digest_email_subject(evaluation_id: str, n_links: int, tenant_name: Optional[str]) -> str:
    """Short, scannable subject for the assignment digest."""
    tn = (tenant_name or "").strip()
    prefix = f"{tn} · " if tn else ""
    if n_links <= 1:
        return f"{prefix}Your questionnaire link — {evaluation_id}"
    return f"{prefix}Your questionnaire links ({n_links} tasks) — {evaluation_id}"


def send_assignment_links_digest_email(
    to_email: str,
    full_name: Optional[str],
    evaluation_id: str,
    tenant_name: Optional[str],
    links: List[Dict[str, Any]],
    hub_url: str = "",
) -> Tuple[bool, Optional[str]]:
    """
    Send one email per respondent with all portal URLs for their assignments.

    Each item in `links` should include at least: portal_url, and optional keys
    assignment_type, track_code, committee_name (used for label).
    """
    cfg = _smtp_config()
    if not cfg["enabled"]:
        return True, None

    to_email = (to_email or "").strip()
    if not to_email:
        return False, "to_email is required"

    cleaned: List[Dict[str, str]] = []
    for it in links:
        url = str(it.get("portal_url") or "").strip()
        if not url:
            continue
        cleaned.append({"label": _assignment_link_label(it), "url": url})

    if not cleaned:
        return False, "no valid portal links"

    rows = _dedupe_display_labels(cleaned)

    hello = f"Hello {full_name}," if full_name else "Hello,"
    hello_safe = html.escape(hello, quote=False)
    ev_safe = html.escape(str(evaluation_id), quote=False)
    tenant_esc = html.escape((tenant_name or "").strip(), quote=False)
    tenant_line = f"<p><b>Client:</b> {tenant_esc}</p>" if tenant_name else ""

    hub_block = ""
    hub = (hub_url or "").strip()
    if hub:
        hub_esc_attr = html.escape(hub, quote=True)
        hub_esc_body = html.escape(hub, quote=False)
        hub_block = f"""
      <div style="margin: 18px 0; padding: 14px; border: 2px solid #0f172a; border-radius: 12px; background: #ffffff;">
        <p style="margin: 0 0 10px; font-weight: 800; color: #0f172a;">All your tasks</p>
        <p style="margin: 0 0 10px; font-size: 13px; color: #64748b;">
          Open your personal hub to see every questionnaire assigned to you.
        </p>
        <p>
          <a href="{hub_esc_attr}" style="
            display:inline-block;
            padding:10px 14px;
            border-radius:10px;
            text-decoration:none;
            font-weight:700;
            border:1px solid #0f172a;
            color:#0f172a;
            background:#f8fafc;
          ">View my assessment tasks</a>
        </p>
        <p style="font-size: 12px; color: #64748b; margin: 8px 0 0;">
          <span style="font-family: monospace; word-break: break-all;">{hub_esc_body}</span>
        </p>
      </div>
"""

    blocks_html = []
    for row in rows:
        disp = html.escape(row["display_label"], quote=False)
        url = row["url"]
        url_esc_attr = html.escape(url, quote=True)
        url_esc_body = html.escape(url, quote=False)
        blocks_html.append(
            f"""
      <div style="margin: 18px 0; padding: 14px; border: 1px solid #e2e8f0; border-radius: 12px; background: #f8fafc;">
        <p style="margin: 0 0 10px; font-weight: 700; color: #0f172a;">{disp}</p>
        <p>
          <a href="{url_esc_attr}" style="
            display:inline-block;
            padding:10px 14px;
            border-radius:10px;
            text-decoration:none;
            font-weight:700;
            border:1px solid #0f172a;
            color:#0f172a;
          ">Open questionnaire</a>
        </p>
        <p style="font-size: 12px; color: #64748b; margin: 8px 0 0;">
          <span style="font-family: monospace; word-break: break-all;">{url_esc_body}</span>
        </p>
      </div>
"""
        )

    html_body = f"""
    <div style="font-family: Arial, sans-serif; line-height: 1.4;">
      <h2>Crest &amp; Waterfalls — Board Evaluation</h2>
      <p>{hello_safe}</p>
      <p>Your consultant has generated your assessment task(s). Use your hub link or open each task below.</p>
      {tenant_line}
      <p><b>Evaluation ID:</b> {ev_safe}</p>
      {hub_block}
      {''.join(blocks_html)}
    </div>
    """.strip()

    plain_lines = [f"{row['display_label']}: {row['url']}" for row in rows]
    plain = (
        "Your consultant has generated your assessment task(s).\n"
        + (f"View all tasks: {hub}\n\n" if hub else "")
        + "Each line below is one questionnaire link:\n\n"
        + "\n".join(plain_lines)
        + f"\n\nEvaluation ID: {evaluation_id}"
    )

    msg = EmailMessage()
    n = len(rows)
    msg["Subject"] = _digest_email_subject(str(evaluation_id), n, tenant_name)
    msg["From"] = cfg["from_addr"]
    msg["To"] = to_email
    msg.set_content(plain)
    msg.add_alternative(html_body, subtype="html")

    try:
        if cfg["use_tls"]:
            with smtplib.SMTP(cfg["host"], cfg["port"]) as s:
                s.starttls()
                if cfg["username"]:
                    s.login(cfg["username"], cfg["password"])
                s.send_message(msg)
        else:
            with smtplib.SMTP(cfg["host"], cfg["port"]) as s:
                if cfg["username"]:
                    s.login(cfg["username"], cfg["password"])
                s.send_message(msg)
        return True, None
    except Exception as e:
        return False, str(e)

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
import logging
import math
import os
import smtplib
from datetime import date
from email.message import EmailMessage
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

# Reserved for documentation and testing (RFC 2606 / RFC 6761). Never sent to, so
# dry runs can use placeholder participants such as P001@example.invalid.
RESERVED_EMAIL_DOMAINS = {"example.com", "example.org", "example.net"}
RESERVED_SKIP_MESSAGE = "Skipped: reserved test address (example.* or .invalid); not sent."


def is_reserved_address(email: Optional[str]) -> bool:
    """True for addresses on example.com/.org/.net or any .invalid domain."""
    domain = (email or "").strip().lower().rpartition("@")[2]
    return domain in RESERVED_EMAIL_DOMAINS or domain == "invalid" or domain.endswith(".invalid")


def _skip_reserved(to_email: str) -> bool:
    if is_reserved_address(to_email):
        log.info("Email skipped: %s is a reserved test domain", to_email.rpartition("@")[2].lower())
        return True
    return False


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
    if _skip_reserved(to_email):
        return False, RESERVED_SKIP_MESSAGE

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
    if _skip_reserved(to_email):
        return False, RESERVED_SKIP_MESSAGE

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


# ----------------------------
# Assembled evaluations: one email, one link
# ----------------------------

def _send_message(cfg: dict, msg: EmailMessage) -> Tuple[bool, Optional[str]]:
    try:
        with smtplib.SMTP(cfg["host"], cfg["port"]) as s:
            if cfg["use_tls"]:
                s.starttls()
            if cfg["username"]:
                s.login(cfg["username"], cfg["password"])
            s.send_message(msg)
        return True, None
    except Exception as e:
        return False, str(e)


def _long_date(d: Optional[date]) -> str:
    return d.strftime("%d %B %Y").lstrip("0") if d else ""


def form_invite_content(
    *,
    full_name: Optional[str],
    form_url: str,
    organisation: str,
    evaluation_name: str,
    consultancy: str,
    estimated_minutes: Optional[int],
    deadline: Optional[date],
    notice: str,
) -> Tuple[str, str, str]:
    """(subject, plain text, HTML) for a participant's invite to their one form."""
    hello = f"Dear {full_name}," if full_name else "Hello,"
    minutes = f"about {estimated_minutes} minutes" if estimated_minutes else ""
    lines = [
        hello,
        "",
        f"{consultancy} is carrying out the {evaluation_name} for {organisation}, and would value your views.",
        "",
        "Your questionnaire is ready. Open it with your personal link:",
        form_url,
        "",
    ]
    if minutes:
        lines.append(f"It takes {minutes}.")
    if deadline:
        lines.append(f"Please complete it by {_long_date(deadline)}.")
    lines += [
        "Your answers save as you go, so you can stop and come back to this link any time.",
        "",
        notice,
        "",
        "This link is personal to you; please don't forward it.",
        "",
        consultancy,
    ]
    plain = "\n".join(lines)

    e = lambda s: html.escape(s or "", quote=False)  # noqa: E731
    facts = "".join(
        f"<li>{e(t)}</li>"
        for t in (
            f"It takes {minutes}." if minutes else "",
            f"Please complete it by {_long_date(deadline)}." if deadline else "",
            "Your answers save as you go, so you can stop and come back to this link any time.",
        )
        if t
    )
    html_body = f"""
    <div style="font-family: Arial, sans-serif; line-height: 1.5; color: #0f172a; max-width: 560px;">
      <p>{e(hello)}</p>
      <p>{e(consultancy)} is carrying out the {e(evaluation_name)} for {e(organisation)}, and would value your views.</p>
      <p>Your questionnaire is ready.</p>
      <p style="margin: 20px 0;">
        <a href="{html.escape(form_url, quote=True)}" style="display:inline-block; padding:12px 18px; border-radius:10px;
           background:#0f172a; color:#ffffff; text-decoration:none; font-weight:700;">Open my questionnaire</a>
      </p>
      <ul style="padding-left: 18px;">{facts}</ul>
      <p style="padding: 12px; border-radius: 10px; background: #f1f5f9;">{e(notice)}</p>
      <p style="font-size: 13px; color: #475569;">This link is personal to you; please don't forward it.<br/>
        If the button doesn't work, copy this address into your browser:<br/>
        <span style="word-break: break-all;">{e(form_url)}</span></p>
      <p>{e(consultancy)}</p>
    </div>
    """.strip()
    subject = f"{organisation}: your board evaluation questionnaire"
    return subject, plain, html_body


def send_form_invite_email(
    to_email: str,
    full_name: Optional[str],
    form_url: str,
    organisation: str,
    evaluation_name: str,
    consultancy: str,
    estimated_minutes: Optional[int] = None,
    deadline: Optional[date] = None,
    notice: str = "",
) -> Tuple[bool, Optional[str]]:
    """
    Send a participant the one link to their form (evaluations that use assembled sets).
    Same rules as the other emails: skipped (ok) when email is disabled, never sent to reserved test domains.
    """
    cfg = _smtp_config()
    if not cfg["enabled"]:
        return True, None
    to_email = (to_email or "").strip()
    if not to_email:
        return False, "to_email is required"
    if _skip_reserved(to_email):
        return False, RESERVED_SKIP_MESSAGE
    if not (form_url or "").strip():
        return False, "no form link"

    subject, plain, html_body = form_invite_content(
        full_name=full_name, form_url=form_url, organisation=organisation, evaluation_name=evaluation_name,
        consultancy=consultancy, estimated_minutes=estimated_minutes, deadline=deadline, notice=notice,
    )
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg["from_addr"]
    msg["To"] = to_email
    msg.set_content(plain)
    msg.add_alternative(html_body, subtype="html")
    return _send_message(cfg, msg)


# ----------------------------
# Reminders (assembled evaluations)
# ----------------------------

def progress_words(answered: int, required: int) -> str:
    """How far along they are, in plain words. Never compares them with anyone else."""
    if not answered:
        return "You haven't started yet."
    share = answered / required if required else 1
    if share < 0.35:
        return "You've made a start."
    if share < 0.65:
        return "You're about halfway through."
    return "You're most of the way through."


def minutes_left(estimated_minutes: Optional[int], answered: int, required: int) -> Optional[int]:
    if not estimated_minutes:
        return None
    share = min(1, answered / required) if required else 0
    return max(1, math.ceil(estimated_minutes * (1 - share))) if share < 1 else None


def form_reminder_content(
    *,
    full_name: Optional[str],
    form_url: str,
    organisation: str,
    evaluation_name: str,
    consultancy: str,
    answered: int,
    required: int,
    estimated_minutes: Optional[int],
    deadline: Optional[date],
    notice: str,
    final: bool = False,
    deadline_extended: bool = False,
) -> Tuple[str, str, str]:
    """
    (subject, plain text, HTML) for a courteous reminder: their own progress, time left, the
    deadline and the same link. No pressure tactics and nothing about anyone else's progress.
    """
    hello = f"Dear {full_name}," if full_name else "Hello,"
    left = minutes_left(estimated_minutes, answered, required)
    when = f" by {_long_date(deadline)}" if deadline else ""
    if deadline_extended and deadline:
        opening = f"The deadline for the {evaluation_name} for {organisation} has been extended to {_long_date(deadline)}."
    elif final and deadline:
        opening = (f"This is the last reminder before the deadline for the {evaluation_name} for {organisation} "
                   f"on {_long_date(deadline)}.")
    else:
        opening = f"A gentle reminder about your questionnaire for the {evaluation_name} for {organisation}."
    facts = [progress_words(answered, required)]
    if left:
        facts.append(f"It should take about {left} more minute{'' if left == 1 else 's'}.")
    if deadline and not (final or deadline_extended):
        facts.append(f"Please complete it{when}.")
    facts.append("Your answers are saved as you go, so you can pick up where you left off.")
    lines = [hello, "", opening, "", *facts, "", "Open your questionnaire with your personal link:", form_url, "",
             notice, "", "Thank you for your time.", "", consultancy]
    plain = "\n".join(lines)

    e = lambda t: html.escape(t or "", quote=False)  # noqa: E731
    html_body = f"""
    <div style="font-family: Arial, sans-serif; line-height: 1.5; color: #0f172a; max-width: 560px;">
      <p>{e(hello)}</p>
      <p>{e(opening)}</p>
      <ul style="padding-left: 18px;">{"".join(f"<li>{e(t)}</li>" for t in facts)}</ul>
      <p style="margin: 20px 0;">
        <a href="{html.escape(form_url, quote=True)}" style="display:inline-block; padding:12px 18px; border-radius:10px;
           background:#0f172a; color:#ffffff; text-decoration:none; font-weight:700;">Open my questionnaire</a>
      </p>
      <p style="padding: 12px; border-radius: 10px; background: #f1f5f9;">{e(notice)}</p>
      <p style="font-size: 13px; color: #475569;">If the button doesn't work, copy this address into your browser:<br/>
        <span style="word-break: break-all;">{e(form_url)}</span></p>
      <p>Thank you for your time.<br/>{e(consultancy)}</p>
    </div>
    """.strip()
    if deadline_extended:
        subject = f"{organisation}: board evaluation deadline extended"
    elif final:
        subject = f"{organisation}: last reminder about your board evaluation questionnaire"
    else:
        subject = f"{organisation}: reminder about your board evaluation questionnaire"
    return subject, plain, html_body


def send_form_reminder_email(to_email: str, **content: Any) -> Tuple[bool, Optional[str]]:
    """Send a reminder (same rules as the invite: off when email is disabled, never to reserved test domains)."""
    cfg = _smtp_config()
    if not cfg["enabled"]:
        return True, None
    to_email = (to_email or "").strip()
    if not to_email:
        return False, "to_email is required"
    if _skip_reserved(to_email):
        return False, RESERVED_SKIP_MESSAGE
    subject, plain, html_body = form_reminder_content(**content)
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg["from_addr"]
    msg["To"] = to_email
    msg.set_content(plain)
    msg.add_alternative(html_body, subtype="html")
    return _send_message(cfg, msg)

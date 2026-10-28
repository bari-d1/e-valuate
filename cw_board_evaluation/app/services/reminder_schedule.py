"""
app.services.reminder_schedule
------------------------------
The automatic reminder schedule for one participant, as pure functions of the
evaluation's settings, the day their link was first sent and the deadline.

Default schedule: first reminder 5 days after the invite, then every 4 days,
and a final reminder 2 days before the deadline; at most 3 reminders in all
(manual ones count too); weekends skipped (regular reminders move to Monday,
the final one to the Friday before). Off until the consultant switches it on.

Each slot has a stable key ("auto:<n>", or "final:<deadline>" so extending the
deadline allows a new final reminder). The sender records the key in a unique
column, so a slot can never be sent twice.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_SETTINGS: Dict[str, Any] = {
    "enabled": False,
    "first_after_days": 5,
    "repeat_every_days": 4,
    "final_before_deadline_days": 2,
    "max_reminders": 3,
    "skip_weekends": True,
}

LIMITS = {"first_after_days": (1, 60), "repeat_every_days": (1, 60), "final_before_deadline_days": (0, 30),
          "max_reminders": (0, 10)}

MIN_GAP = timedelta(hours=24)  # never two reminders to one person within a day (unless a consultant overrides)


def effective_settings(stored: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    out = dict(DEFAULT_SETTINGS)
    out.update({k: v for k, v in (stored or {}).items() if k in DEFAULT_SETTINGS})
    return out


def validate_settings(changes: Dict[str, Any]) -> Dict[str, Any]:
    """Only known keys; booleans for the switches, whole numbers within limits for the rest."""
    out: Dict[str, Any] = {}
    for k, v in changes.items():
        if k not in DEFAULT_SETTINGS:
            raise ValueError(f"Unknown reminder setting: {k}.")
        if k in ("enabled", "skip_weekends"):
            if not isinstance(v, bool):
                raise ValueError(f"{k} must be true or false.")
        else:
            lo, hi = LIMITS[k]
            if isinstance(v, bool) or not isinstance(v, int) or not lo <= v <= hi:
                raise ValueError(f"{k.replace('_', ' ').capitalize()} must be a whole number from {lo} to {hi}.")
        out[k] = v
    return out


@dataclass(frozen=True)
class Slot:
    key: str
    on: date
    final: bool = False
    number: int = 0  # 1, 2, ... for regular reminders; 0 for the final one


def _weekday_forward(d: date) -> date:
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def _weekday_back(d: date) -> date:
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def schedule(settings: Dict[str, Any], invited_on: date, deadline: Optional[date]) -> List[Slot]:
    """Every reminder slot for someone first sent their link on `invited_on`, in date order."""
    s = effective_settings(settings)
    skip = s["skip_weekends"]
    final_on: Optional[date] = None
    if deadline is not None:
        final_on = deadline - timedelta(days=s["final_before_deadline_days"])
        if skip:
            final_on = _weekday_back(final_on)
        if final_on <= invited_on:
            final_on = None
    regular_max = s["max_reminders"] - (1 if final_on else 0)
    slots: List[Slot] = []
    d = invited_on + timedelta(days=s["first_after_days"])
    while len(slots) < regular_max:
        on = _weekday_forward(d) if skip else d
        if (final_on and on >= final_on) or (deadline and on > deadline):
            break
        slots.append(Slot(key=f"auto:{len(slots) + 1}", on=on, number=len(slots) + 1))
        d = on + timedelta(days=s["repeat_every_days"])
    if final_on and s["max_reminders"] > 0:
        slots.append(Slot(key=f"final:{deadline.isoformat()}", on=final_on, final=True))
    return slots


def due_slot(settings: Dict[str, Any], slots: List[Slot], today: date, *, deadline: Optional[date],
             sent_keys: set, reminders_sent: int, last_reminder_at: Optional[datetime], now: datetime
             ) -> Tuple[Optional[Slot], str]:
    """
    (the slot to send today, why) or (None, why not). Only the latest slot that has come due is
    sent, so a missed run never produces a burst of catch-up reminders.
    """
    s = effective_settings(settings)
    if deadline is not None and today > deadline:
        return None, "The deadline has passed."
    if s["skip_weekends"] and today.weekday() >= 5:
        return None, "No reminders at weekends."
    if reminders_sent >= s["max_reminders"]:
        return None, f"Already sent the maximum of {s['max_reminders']} reminders."
    due = [x for x in slots if x.on <= today]
    if not due:
        upcoming = next((x for x in slots if x.on > today), None)
        return None, (f"Next reminder {upcoming.on.strftime('%a %d %b').replace(' 0', ' ')}." if upcoming
                      else "No reminders left in the schedule.")
    slot = due[-1]
    if slot.key in sent_keys:
        upcoming = next((x for x in slots if x.on > today), None)
        return None, (f"Reminded already; next reminder {upcoming.on.strftime('%a %d %b').replace(' 0', ' ')}."
                      if upcoming else "Reminded already; no reminders left in the schedule.")
    if last_reminder_at is not None and now - last_reminder_at < MIN_GAP:
        return None, "Reminded less than 24 hours ago."
    return slot, ("Final reminder before the deadline." if slot.final
                  else f"Reminder {slot.number}, due {slot.on.strftime('%a %d %b').replace(' 0', ' ')}.")


def next_due_on(settings: Dict[str, Any], slots: List[Slot], now: datetime, *, deadline: Optional[date],
                sent_keys: set, reminders_sent: int, last_reminder_at: Optional[datetime], horizon: int = 90
                ) -> Optional[date]:
    """
    The next day the reminder job would send this participant one, asking due_slot itself day by
    day (later days at 09:00 UTC), so the date shown always matches what the job will do.
    """
    for i in range(horizon):
        day = now.date() + timedelta(days=i)
        at = now if i == 0 else datetime.combine(day, time(9), tzinfo=timezone.utc)
        slot, _ = due_slot(settings, slots, day, deadline=deadline, sent_keys=sent_keys,
                           reminders_sent=reminders_sent, last_reminder_at=last_reminder_at, now=at)
        if slot is not None:
            return day
    return None

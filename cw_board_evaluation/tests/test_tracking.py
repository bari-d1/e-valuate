"""
Tracking and reminders for assembled evaluations on a VAL-001-style evaluation:
status and progress, manual reminders, links, deadline, reopening and closing,
the automatic schedule (repeat runs, concurrent runs, who is never reminded),
the scheduler endpoint, the reminder email and query counts. Placeholder names
only; emails go to the .test domain (never sent: the mailers are faked).

Requires: RUN_INTEGRATION_TESTS=1 and PostgreSQL.
"""

from __future__ import annotations

import json
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import event, select, update
from sqlalchemy.orm import sessionmaker

from app.db.models import (
    AssessmentAssignment,
    Evaluation,
    Participant,
    ParticipantEvent,
    ParticipantQuestionSet,
    QuestionBankItem,
)
from app.services import participant_portal as form
from app.services import question_assembly as qa
from app.services import question_sets as qs
from app.services import reminder_schedule as sched
from app.services import tracking
from app.services.email_service import form_reminder_content, progress_words
from app.services.participant_notify import send_evaluation_link_notifications
from app.services.question_bank import load_fixture
from tests.val001 import build_val001

pytestmark = pytest.mark.integration

FIXTURE = Path(__file__).resolve().parents[1] / "reference" / "question_bank" / "draft_bank.json"
BY = "Consultant A"
UTC = timezone.utc


@pytest.fixture
def val001(db_session, reference_seeded, monkeypatch):
    monkeypatch.delenv("AI_TAILORING_ENABLED", raising=False)
    monkeypatch.delenv("ASSEMBLY_COVERAGE_FLOOR", raising=False)
    summary = load_fixture(db_session, json.loads(FIXTURE.read_text(encoding="utf-8")))
    assert not summary["errors"]
    db_session.execute(update(QuestionBankItem).values(status="approved"))
    db_session.flush()
    ev, parts, committees = build_val001(db_session)
    ev.deadline = date.today() + timedelta(days=21)
    ev.status = "live"
    qa.run_assembly(db_session, qa.create_run(db_session, ev))
    for code, p in parts.items():
        p.email = f"{code.lower()}@val001.test"  # placeholder, but not a reserved domain, so reminders consider them
    db_session.flush()
    return ev, parts, committees


class Mailer:
    """Fake invite and reminder emails; addresses in `fail` get an SMTP-style error."""

    def __init__(self):
        self.invites, self.reminders, self.fail = [], [], {}

    def invite(self, **kw):
        self.invites.append(kw["to_email"])
        err = self.fail.get(kw["to_email"])
        return (False, err) if err else (True, None)

    def reminder(self, to_email, **kw):
        self.reminders.append((to_email, kw))
        err = self.fail.get(to_email)
        return (False, err) if err else (True, None)


@pytest.fixture
def mailer(monkeypatch):
    import app.services.email_service as email_service

    m = Mailer()
    monkeypatch.setattr(email_service, "send_form_invite_email", m.invite)
    monkeypatch.setattr(email_service, "send_form_reminder_email", m.reminder)
    return m


def _approve(db, *parts):
    for p in parts:
        qs.approve_set(db, qs.question_set(db, p.id), BY, override_reason="Scope agreed with the client")
    db.flush()


def _invite(db, ev):
    return send_evaluation_link_notifications(db, ev.id)


def _token(db, p):
    return form.form_assignment(db, p.id).access_token


def _rows(db, ev):
    return {str(r["participant_id"]): r for r in tracking.summary(db, ev)["participants"]}


def _answer(api_client, token, n=None, value_for=None):
    """Answer the first n required questions (all when n is None) with neutral values; returns the form."""
    data = api_client.get(f"/api/v1/portal/a/{token}").json()
    qs_ = []
    for s in data["sections"]:
        for b in s["blocks"]:
            if b["kind"] == "grid":
                qs_ += [{"id": q, "answer_type": "rating", "confirm": None, "options": None}
                        for st in b["statements"] for q in st["cells"].values()]
            elif b["required"]:
                qs_.append(b)
    pick = {"rating": 4, "yesno": "no", "single_select": None, "multi_select": None}
    answers = []
    for q in qs_[: n if n is not None else len(qs_)]:
        if q.get("confirm"):
            v = {"status": "correct"}
        elif q["answer_type"] in ("single_select", "multi_select"):
            v = q["options"][0] if q["answer_type"] == "single_select" else q["options"][:1]
        else:
            v = pick.get(q["answer_type"], "Fine")
        answers.append({"question_id": q["id"], "value": v})
    r = api_client.put(f"/api/v1/portal/a/{token}/answers", json={"answers": answers})
    assert r.status_code == 200, r.text
    return data


def _events(db, p, kind=None):
    stmt = select(ParticipantEvent).where(ParticipantEvent.participant_id == p.id)
    if kind:
        stmt = stmt.where(ParticipantEvent.event_type == kind)
    return db.execute(stmt.order_by(ParticipantEvent.created_at)).scalars().all()


# ----------------------------
# Status and progress
# ----------------------------

def test_each_status_is_derived_including_a_failed_email_that_recovers(api_client, db_session, val001, mailer) -> None:
    ev, parts, _ = val001
    p = parts
    _approve(db_session, *[parts[c] for c in ("P001", "P002", "P003", "P004", "P005", "P006")])
    rows = _rows(db_session, ev)
    assert rows[str(p["P007"].id)]["status"] == "not_ready"
    assert rows[str(p["P001"].id)]["status"] == "ready"

    mailer.fail[p["P003"].email] = "550 5.1.1 Mailbox unavailable"
    _invite(db_session, ev)
    [failed] = _events(db_session, p["P003"], "email_failed")
    assert failed.detail == {"kind": "invite_sent", "error": "550 5.1.1 Mailbox unavailable"}

    api_client.get(f"/api/v1/portal/a/{_token(db_session, p['P004'])}")  # opened
    _answer(api_client, _token(db_session, p["P005"]), n=3)  # in progress
    _answer(api_client, _token(db_session, p["P006"]))
    assert api_client.post(f"/api/v1/portal/a/{_token(db_session, p['P006'])}/submit").status_code == 200

    rows = _rows(db_session, ev)
    got = {c: rows[str(parts[c].id)]["status"] for c in parts}
    assert got == {"P001": "sent", "P002": "sent", "P003": "email_failed", "P004": "opened", "P005": "in_progress",
                   "P006": "submitted", "P007": "not_ready"}
    assert rows[str(p["P003"].id)]["email_error"] == "550 5.1.1 Mailbox unavailable"
    kinds = [e.event_type for e in _events(db_session, p["P005"])]
    assert kinds == ["invite_sent", "opened", "first_answer"]
    assert [e.event_type for e in _events(db_session, p["P006"])][-1] == "submitted"

    del mailer.fail[p["P003"].email]  # address fixed: a resend goes through
    assert tracking.resend_link(db_session, ev, p["P003"].id, BY)["sent"] is True
    rows = _rows(db_session, ev)
    assert rows[str(p["P003"].id)]["status"] == "sent" and rows[str(p["P003"].id)]["email_error"] is None

    s = tracking.summary(db_session, ev)
    assert s["counts"] == {"not_ready": 1, "ready": 0, "sent": 3, "opened": 1, "in_progress": 1, "submitted": 1,
                           "email_failed": 0}
    assert 0 < s["completion_percent"] < 100 and s["evaluation"]["days_left"] == 21


def test_progress_matches_the_portal_submit_check(api_client, db_session, val001, mailer) -> None:
    ev, parts, _ = val001
    p4 = parts["P004"]
    _approve(db_session, p4)
    _invite(db_session, ev)
    token = _token(db_session, p4)
    _answer(api_client, token, n=40)
    row = _rows(db_session, ev)[str(p4.id)]
    a = form.form_assignment(db_session, p4.id)
    missing = form.missing_required(db_session, a, p4)
    assert row["progress"]["answered"] == 40
    assert row["progress"]["required"] - row["progress"]["answered"] == len(missing)
    portal = api_client.get(f"/api/v1/portal/a/{token}").json()["progress"]
    assert (portal["required_answered"], portal["required"]) == (row["progress"]["answered"], row["progress"]["required"])


def test_the_summary_uses_a_fixed_number_of_queries(db_session, integration_engine, val001, mailer) -> None:
    ev, parts, _ = val001
    _approve(db_session, *parts.values())
    _invite(db_session, ev)
    db_session.expire_all()

    def count():
        n = [0]

        def on(*_):
            n[0] += 1
        event.listen(integration_engine, "before_cursor_execute", on)
        try:
            tracking.summary(db_session, ev)
        finally:
            event.remove(integration_engine, "before_cursor_execute", on)
        db_session.expire_all()
        return n[0]

    before = count()
    for i in range(5):
        db_session.add(Participant(evaluation_id=ev.id, email=f"extra{i}@val001.test", status="invited"))
    db_session.flush()
    db_session.expire_all()
    # Seven loads plus the bank items' and questions' tag links, however many participants there are
    assert count() == before <= 15


# ----------------------------
# Manual actions
# ----------------------------

def test_manual_reminders_are_refused_where_they_should_be_unless_overridden(api_client, db_session, val001,
                                                                            mailer) -> None:
    ev, parts, _ = val001
    p1, p4, p6, p7 = parts["P001"], parts["P004"], parts["P006"], parts["P007"]
    _approve(db_session, p1, p4, p6)
    _invite(db_session, ev)
    _answer(api_client, _token(db_session, p6))
    api_client.post(f"/api/v1/portal/a/{_token(db_session, p6)}/submit")

    r = api_client.post(f"/api/v1/evaluations/{ev.id}/tracking/remind", headers={"X-Consultant-Name": BY},
                        json={"participant_ids": [str(p.id) for p in (p1, p4, p6, p7)]})
    out = {x["participant_id"]: x for x in r.json()["results"]}
    assert out[str(p1.id)]["outcome"] == out[str(p4.id)]["outcome"] == "sent"
    assert out[str(p6.id)]["reason"] == "They've already submitted."
    assert out[str(p7.id)]["reason"] == "Their question set isn't approved yet."
    [ev1] = _events(db_session, p1, "reminder_sent")
    assert ev1.actor == BY and ev1.detail["kind"] == "manual"

    again = tracking.remind(db_session, ev, BY, [str(p1.id)])
    assert again[0]["reason"] == "Reminded less than 24 hours ago."
    assert tracking.remind(db_session, ev, BY, [str(p1.id)], override=True)[0]["outcome"] == "sent"
    assert len(_events(db_session, p1, "reminder_sent")) == 2

    preview = tracking.remind(db_session, ev, BY, dry_run=True, override=True)  # everyone outstanding
    assert {x["participant_id"] for x in preview} == {str(p1.id), str(p4.id)}
    assert all(x["outcome"] == "would_send" for x in preview) and len(mailer.reminders) == 3

    tracking.close_evaluation(db_session, ev, BY)
    assert tracking.remind(db_session, ev, BY, [str(p4.id)], override=True)[0]["reason"] == "The evaluation is closed."


def test_regenerating_a_link_stops_the_old_one_and_keeps_answers(api_client, db_session, val001, mailer) -> None:
    ev, parts, _ = val001
    p3 = parts["P003"]
    _approve(db_session, p3)
    _invite(db_session, ev)
    old = _token(db_session, p3)
    _answer(api_client, old, n=5)
    r = api_client.post(f"/api/v1/evaluations/{ev.id}/tracking/participants/{p3.id}/regenerate-link")
    assert r.status_code == 200 and r.json()["sent"] is True
    new = _token(db_session, p3)
    assert new != old and len(new) >= 43
    assert api_client.get(f"/api/v1/portal/a/{old}").status_code == 404
    loaded = api_client.get(f"/api/v1/portal/a/{new}").json()
    assert loaded["progress"]["required_answered"] == 5
    kinds = [e.event_type for e in _events(db_session, p3)]
    assert kinds[-2:] == ["link_regenerated", "link_resent"]
    assert old not in json.dumps([e.detail for e in _events(db_session, p3)]) and mailer.invites[-1] == p3.email


def test_reopening_a_submitted_form_lets_them_answer_again_and_keeps_the_set_locked(api_client, db_session, val001,
                                                                                  mailer) -> None:
    ev, parts, _ = val001
    p1 = parts["P001"]
    _approve(db_session, p1)
    _invite(db_session, ev)
    token = _token(db_session, p1)
    data = _answer(api_client, token)
    assert api_client.post(f"/api/v1/portal/a/{token}/submit").status_code == 200
    r = api_client.post(f"/api/v1/evaluations/{ev.id}/tracking/participants/{p1.id}/reopen", json={"reason": " "})
    assert r.status_code == 422
    r = api_client.post(f"/api/v1/evaluations/{ev.id}/tracking/participants/{p1.id}/reopen",
                        json={"reason": "Wants to change a committee answer"})
    assert r.status_code == 200 and r.json()["status"] == "in_progress"
    assert qs.question_set(db_session, p1.id).status == "locked"
    [e] = _events(db_session, p1, "form_reopened")
    assert e.detail == {"reason": "Wants to change a committee answer"}
    first = next(b for s in data["sections"] for b in s["blocks"] if b["kind"] == "question" and b["answer_type"] == "rating")
    r = api_client.put(f"/api/v1/portal/a/{token}/answers", json={"answers": [{"question_id": first["id"], "value": 2}]})
    assert r.status_code == 200
    assert _rows(db_session, ev)[str(p1.id)]["status"] == "in_progress"
    assert api_client.post(f"/api/v1/portal/a/{token}/submit").status_code == 200


def test_closing_stops_answers_with_a_polite_message_and_reopening_restores(api_client, db_session, val001,
                                                                          mailer) -> None:
    ev, parts, _ = val001
    p4 = parts["P004"]
    _approve(db_session, p4)
    _invite(db_session, ev)
    token = _token(db_session, p4)
    data = _answer(api_client, token, n=1)
    assert api_client.post(f"/api/v1/evaluations/{ev.id}/tracking/close").status_code == 200
    q = next(b for s in data["sections"] for b in s["blocks"] if b["kind"] == "question" and b["answer_type"] == "rating")
    r = api_client.put(f"/api/v1/portal/a/{token}/answers", json={"answers": [{"question_id": q["id"], "value": 3}]})
    assert r.status_code == 410 and r.json()["detail"]["code"] == "closed"
    assert "has closed" in r.json()["detail"]["message"]
    assert api_client.post(f"/api/v1/portal/a/{token}/submit").status_code == 410
    assert api_client.post(f"/api/v1/evaluations/{ev.id}/tracking/close").status_code == 409

    assert api_client.post(f"/api/v1/evaluations/{ev.id}/tracking/reopen").json()["status"] == "live"
    r = api_client.put(f"/api/v1/portal/a/{token}/answers", json={"answers": [{"question_id": q["id"], "value": 3}]})
    assert r.status_code == 200
    timeline = api_client.get(f"/api/v1/evaluations/{ev.id}/tracking/participants/{p4.id}/events").json()["events"]
    texts = [e["text"] for e in timeline]
    assert "Closed the evaluation to new answers" in texts and "Reopened the evaluation" in texts
    assert texts[:3] == ["Invitation sent", "Opened the form", "Answered their first question"]


def test_extending_the_deadline_can_tell_outstanding_participants(db_session, val001, mailer) -> None:
    ev, parts, _ = val001
    _approve(db_session, parts["P001"], parts["P004"])
    _invite(db_session, ev)
    old = ev.deadline
    with pytest.raises(tracking.TrackingError):
        tracking.set_deadline(db_session, ev, date.today() - timedelta(days=1), BY)
    out = tracking.set_deadline(db_session, ev, old + timedelta(days=7), BY, notify=True)
    assert len(out["notified"]) == 2 and all(x["outcome"] == "sent" for x in out["notified"])
    assert all(kw["deadline_extended"] for _, kw in mailer.reminders)
    [e] = db_session.execute(select(ParticipantEvent).where(ParticipantEvent.event_type == "deadline_extended")).scalars().all()
    assert e.participant_id is None and e.detail["to"] == (old + timedelta(days=7)).isoformat()
    # Deadline notices don't use up anyone's reminders
    assert all(r["reminders_sent"] == 0 for r in tracking.summary(db_session, ev)["participants"])


def test_legacy_evaluations_have_no_tracking(api_client, db_session, reference_seeded) -> None:
    ev = Evaluation(id="LEGACY-T", tenant_name="Legacy Co", sector="insurance", year=2025, regulators={"items": []})
    db_session.add(ev)
    db_session.flush()
    assert api_client.get(f"/api/v1/evaluations/{ev.id}/tracking").status_code == 409


# ----------------------------
# The automatic schedule
# ----------------------------

def test_the_default_schedule_skips_weekends_and_respects_the_maximum() -> None:
    on = lambda slots: [(s.on.strftime("%a %d %b"), s.final) for s in slots]  # noqa: E731
    default = sched.effective_settings({"enabled": True})
    # Invited Wed 28 Oct, deadline Fri 20 Nov: Mon 2, Fri 6, then the final on Wed 18
    assert on(sched.schedule(default, date(2026, 10, 28), date(2026, 11, 20))) == [
        ("Mon 02 Nov", False), ("Fri 06 Nov", False), ("Wed 18 Nov", True)]
    # Invited Mon 2 Nov: +5 is Saturday, so Monday 9; the final would be Sunday 22, so Friday 20
    assert on(sched.schedule(default, date(2026, 11, 2), date(2026, 11, 24))) == [
        ("Mon 09 Nov", False), ("Fri 13 Nov", False), ("Fri 20 Nov", True)]
    weekends = {**default, "skip_weekends": False}
    assert on(sched.schedule(weekends, date(2026, 11, 2), date(2026, 11, 24)))[0] == ("Sat 07 Nov", False)
    assert len(sched.schedule({**default, "max_reminders": 1}, date(2026, 10, 28), date(2026, 11, 20))) == 1
    assert sched.schedule({**default, "max_reminders": 0}, date(2026, 10, 28), date(2026, 11, 20)) == []
    # No deadline: regular reminders only, up to the maximum
    assert [s.final for s in sched.schedule(default, date(2026, 10, 28), None)] == [False, False, False]
    with pytest.raises(ValueError):
        sched.validate_settings({"repeat_every_days": 0})
    with pytest.raises(ValueError):
        sched.validate_settings({"enabled": "yes"})


def _run_days(db, start: datetime, days: int):
    """Run the reminder job once a day at 09:00 for `days` days; {date: [names reminded]}."""
    out = {}
    for d in range(days):
        now = (start + timedelta(days=d)).replace(hour=9, minute=0, second=0, microsecond=0)
        res = tracking.send_due_reminders(db, now, commit=False)
        out[now.date()] = sorted(x["name"] for x in res["sent"])
    return out


def test_two_simulated_weeks_on_val001(api_client, db_session, val001, mailer) -> None:
    ev, parts, _ = val001
    _approve(db_session, *parts.values())
    mailer.fail[parts["P003"].email] = "550 5.1.1 Mailbox unavailable"
    _invite(db_session, ev)
    tracking.update_settings(db_session, ev, {"enabled": True}, BY)
    invited = datetime.now(UTC)

    p1, p4, p6 = (_token(db_session, parts[c]) for c in ("P001", "P004", "P006"))
    _answer(api_client, p1)
    assert api_client.post(f"/api/v1/portal/a/{p1}/submit").status_code == 200
    api_client.get(f"/api/v1/portal/a/{p6}")
    total = api_client.get(f"/api/v1/portal/a/{p4}").json()["progress"]["required"]
    _answer(api_client, p4, n=total // 2)

    days = _run_days(db_session, invited, 15)
    slots = sched.schedule(tracking.settings_of(ev), invited.date(), ev.deadline)
    expected_days = {s.on for s in slots if s.on <= invited.date() + timedelta(days=14)}
    outstanding = sorted(parts[c].full_name for c in ("P002", "P004", "P005", "P006", "P007"))
    for day, names in days.items():
        if day in expected_days:
            assert names == outstanding, day
        else:
            assert names == [], day
        assert day.weekday() < 5 or not names
    assert len(expected_days) >= 2  # at least two reminders fall within the two weeks

    s = tracking.summary(db_session, ev, invited + timedelta(days=14))
    assert s["counts"]["submitted"] == 1 and s["counts"]["email_failed"] == 1 and s["counts"]["in_progress"] == 1
    rows = {r["name"]: r for r in s["participants"]}
    assert rows[parts["P001"].full_name]["reminders_sent"] == 0  # submitted: never reminded
    assert rows[parts["P003"].full_name]["reminders_sent"] == 0  # failing address: not re-tried automatically
    assert rows[parts["P004"].full_name]["reminders_sent"] == len(expected_days)
    halfway = [kw for to, kw in mailer.reminders if to == parts["P004"].email]
    assert progress_words(halfway[0]["answered"], halfway[0]["required"]) == "You're about halfway through."


def test_running_twice_sends_once_and_never_to_the_wrong_people(api_client, db_session, val001, mailer) -> None:
    ev, parts, _ = val001
    _approve(db_session, *[parts[c] for c in ("P001", "P002", "P004", "P005", "P006")])  # P003, P007 unapproved
    parts["P002"].email = "p002@example.com"  # reserved test domain
    _invite(db_session, ev)
    tracking.update_settings(db_session, ev, {"enabled": True}, BY)
    t1 = _token(db_session, parts["P001"])
    _answer(api_client, t1)
    api_client.post(f"/api/v1/portal/a/{t1}/submit")
    first = form.form_assignment(db_session, parts["P004"].id).email_sent_at
    slot = sched.schedule(tracking.settings_of(ev), first.date(), ev.deadline)[0]
    now = datetime.combine(slot.on, datetime.min.time(), UTC).replace(hour=9)

    dry = tracking.send_due_reminders(db_session, now, dry_run=True, commit=False)
    assert sorted(x["name"] for x in dry["would_remind"]) == sorted(parts[c].full_name for c in ("P004", "P005", "P006"))
    reserved = next(x for x in dry["skipped"] if x["name"] == parts["P002"].full_name)
    assert "Reserved" in reserved["reason"] and mailer.reminders == []  # dry run sends nothing

    once = tracking.send_due_reminders(db_session, now, commit=False)
    twice = tracking.send_due_reminders(db_session, now + timedelta(hours=1), commit=False)
    assert len(once["sent"]) == 3 and twice["sent"] == [] and len(mailer.reminders) == 3
    assert {to for to, _ in mailer.reminders} == {parts[c].email for c in ("P004", "P005", "P006")}

    tracking.close_evaluation(db_session, ev, BY)
    later = datetime.combine(slot.on + timedelta(days=7), datetime.min.time(), UTC).replace(hour=9)
    assert tracking.send_due_reminders(db_session, later, commit=False)["evaluations"] == 0
    assert len(mailer.reminders) == 3


def test_two_runs_at_once_send_each_reminder_once(integration_engine, monkeypatch) -> None:
    """Real commits on two connections: the unique key makes the second run wait, then skip."""
    import app.services.email_service as email_service

    sent = []

    def slow(to_email, **kw):
        time.sleep(0.4)  # hold the first run's claim open while the second run arrives
        sent.append(to_email)
        return True, None

    monkeypatch.setattr(email_service, "send_form_reminder_email", slow)
    Session = sessionmaker(bind=integration_engine)
    now = datetime(2026, 11, 3, 9, tzinfo=UTC)  # a Tuesday
    with Session() as db:
        ev = Evaluation(id="CONC-1", tenant_name="Concurrency Co", sector="insurance", year=2026,
                        regulators={"items": []}, status="live", deadline=date(2026, 11, 30),
                        reminder_settings={"enabled": True})
        db.add(ev)
        db.flush()
        p = Participant(evaluation_id=ev.id, email="p@conc.test", full_name="Placeholder Person", status="invited")
        db.add(p)
        db.flush()
        pset = ParticipantQuestionSet(evaluation_id=ev.id, participant_id=p.id, status="approved", summary={})
        db.add(pset)
        db.flush()
        a = AssessmentAssignment(evaluation_id=ev.id, respondent_participant_id=p.id, assignment_type="ASSEMBLED",
                                 instrument_template_code=f"P:{p.id}", access_token="conc-token-" + "x" * 32,
                                 status="invited", question_set_id=pset.id, email_sent_at=now - timedelta(days=6))
        db.add(a)
        db.flush()
        db.add(ParticipantEvent(evaluation_id=ev.id, participant_id=p.id, assignment_id=a.id,
                                event_type="invite_sent", actor="consultant", detail={},
                                created_at=now - timedelta(days=6)))
        db.commit()
    try:
        results = []

        def run():
            with Session() as db:
                results.append(tracking.send_due_reminders(db, now, evaluation_id="CONC-1"))

        threads = [threading.Thread(target=run) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert sent == ["p@conc.test"]
        assert sorted(len(r["sent"]) for r in results) == [0, 1]
        with Session() as db:
            n = db.execute(select(ParticipantEvent).where(ParticipantEvent.evaluation_id == "CONC-1",
                                                          ParticipantEvent.event_type == "reminder_sent")).scalars().all()
            assert len(n) == 1 and n[0].detail["outcome"] == "sent"
    finally:
        with Session() as db:
            db.delete(db.get(Evaluation, "CONC-1"))
            db.commit()


# ----------------------------
# Scheduler endpoint and settings
# ----------------------------

def test_the_scheduler_endpoint_needs_its_secret(api_client, db_session, val001, monkeypatch) -> None:
    monkeypatch.delenv("REMINDER_SCHEDULER_SECRET", raising=False)
    assert api_client.post("/api/v1/scheduler/due-reminders").status_code == 503
    monkeypatch.setenv("REMINDER_SCHEDULER_SECRET", "s3cret-for-tests")
    assert api_client.post("/api/v1/scheduler/due-reminders").status_code == 401
    assert api_client.post("/api/v1/scheduler/due-reminders", headers={"X-Scheduler-Secret": "wrong"}).status_code == 401
    r = api_client.post("/api/v1/scheduler/due-reminders?dry_run=true", headers={"X-Scheduler-Secret": "s3cret-for-tests"})
    assert r.status_code == 200 and r.json()["dry_run"] is True


def test_reminder_settings_preview_and_dry_run(api_client, db_session, val001, mailer) -> None:
    ev, parts, _ = val001
    _approve(db_session, *parts.values())
    _invite(db_session, ev)
    view = api_client.get(f"/api/v1/evaluations/{ev.id}/tracking/reminder-settings").json()
    assert view["settings"]["enabled"] is False and view["defaults"]["first_after_days"] == 5
    assert view["schedule"]["based_on_invites"] is True and view["schedule"]["slots"][-1]["final"] is True
    assert view["dry_run"]["would_remind"] == []  # nobody is due on the day they were invited
    r = api_client.put(f"/api/v1/evaluations/{ev.id}/tracking/reminder-settings", json={"enabled": True, "max_reminders": 2})
    assert r.status_code == 200 and r.json()["settings"]["max_reminders"] == 2 and len(r.json()["schedule"]["slots"]) == 2
    bad = api_client.put(f"/api/v1/evaluations/{ev.id}/tracking/reminder-settings", json={"repeat_every_days": 0})
    assert bad.status_code == 422
    changed = db_session.execute(select(ParticipantEvent).where(
        ParticipantEvent.event_type == "reminder_settings_changed")).scalars().one()
    assert changed.detail == {"enabled": True, "max_reminders": 2} and changed.participant_id is None


# ----------------------------
# The reminder email
# ----------------------------

def test_reminder_wording_progress_final_and_nobody_else() -> None:
    assert progress_words(0, 40) == "You haven't started yet."
    assert progress_words(10, 40) == "You've made a start."
    assert progress_words(20, 40) == "You're about halfway through."
    assert progress_words(35, 40) == "You're most of the way through."
    common = dict(full_name="Board Member 004", form_url="https://portal.example/form/abc",
                  organisation="VAL-001 Test Company", evaluation_name="2025 Board Evaluation",
                  consultancy="Crest & Waterfalls", estimated_minutes=40, deadline=date(2026, 11, 20),
                  notice="Your answers will be used to prepare the report.")
    subject, plain, html = form_reminder_content(answered=20, required=40, **common)
    assert "halfway" in plain and "about 20 more minutes" in plain and "20 November 2026" in plain
    assert plain.count("https://") == 1 and html.count('href="') == 1 and "last reminder" not in plain.lower()
    assert "Your answers will be used" in plain
    subject, plain, _ = form_reminder_content(answered=0, required=40, final=True, **common)
    assert "last reminder before the deadline" in plain and "haven't started" in plain and "last reminder" in subject
    for other in ("Board Member 001", "other directors", "colleagues have", "everyone else"):
        assert other not in plain

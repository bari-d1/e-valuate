"""
End-to-end smoke test against a running app (./dev.sh):
create evaluation -> questions -> invite -> tasks -> director submits in portal -> report .docx.

Usage (from cw_board_evaluation/, with the app running):
  .venv-mac/bin/python scripts/e2e_smoke.py

Creates a new "E2E Test Plc" evaluation in whatever database the app uses each time.
The report step needs OPENAI_API_KEY set for the app.
"""
import json
import os
import sys
import urllib.error
import urllib.request

API = os.getenv("E2E_API", "http://127.0.0.1:8000/api/v1")


def call(method, path, body=None, raw=False):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + path, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            payload = r.read()
            return r.status, (payload if raw else json.loads(payload or b"null"))
    except urllib.error.HTTPError as e:
        print(f"FAIL {method} {path} -> {e.code}: {e.read()[:400]!r}")
        sys.exit(1)


def step(msg):
    print(f"✓ {msg}")


# 1. Create
_, ev = call("POST", "/evaluations", {"tenant_name": "E2E Test Plc", "sector": "banking", "year": 2026, "regulators": ["CBN", "FRC"]})
eid = ev.get("evaluation_id") or ev.get("id")
step(f"created evaluation {eid}")

# 2. Questions (default preset into the evaluation's questionnaire)
call("POST", f"/evaluations/{eid}/seed/questions?template_code=DEFAULT&version=1&preset=default")
_, qs = call("GET", f"/evaluations/{eid}/questions?template_code=DEFAULT&version=1")
step(f"questionnaire has {qs['count']} questions")

# 3. Invite
_, inv = call("POST", f"/evaluations/{eid}/participants/invite", {
    "participants": [
        {"email": "chair.e2e@example.com", "full_name": "Chair E2E", "role": "CHAIR"},
        {"email": "director.e2e@example.com", "full_name": "Director E2E", "role": "INED"},
    ],
    "send_email": False,
})
_, ps = call("GET", f"/evaluations/{eid}/participants")
step(f"invited {len(ps['items'])} participants")

# 4. Tracks + tasks
call("POST", f"/evaluations/{eid}/tracks", {"tracks": [{"code": "BOARD_AS_WHOLE"}, {"code": "DIRECTOR_SELF"}]})
_, gen = call("POST", f"/evaluations/{eid}/tracks/generate-assignments", {"dry_run": False, "send_email_notifications": False})
_, asg = call("GET", f"/evaluations/{eid}/assignments")
step(f"generated {gen.get('created')} tasks ({len(asg['items'])} total)")

# 5. Director completes one form through the portal
mine = [a for a in asg["items"] if a.get("portal_url") and ps["items"] and
        any(p["email"] == "director.e2e@example.com" and p.get("participant_id") == a["respondent_participant_id"] for p in ps["items"])]
a = mine[0] if mine else next(a for a in asg["items"] if a.get("portal_url"))
token = a["assignment_token"]
_, form = call("GET", f"/portal/{token}")
questions = form.get("questions") or []
answers = [{"question_id": q["question_id"], "score": 4, "comment": "E2E answer"} for q in questions]
call("POST", f"/portal/{token}/responses?finalize=true", {"answers": answers})
_, after = call("GET", f"/evaluations/{eid}/assignments")
done = sum(1 for x in after["items"] if x["status"] == "responded")
step(f"director submitted {len(answers)} answers via portal; tasks completed: {done}")

# 6. Report
_, rep = call("POST", f"/evaluations/{eid}/report/generate", {"include_trends": True, "include_compliance": True})
rid = rep["report_id"]
step(f"report generated ({rep['status']}) id={rid}")
status, docx = call("GET", f"/reports/{rid}/docx", raw=True)
ok = docx[:2] == b"PK"
step(f"report .docx downloaded: {len(docx)} bytes, valid Word file: {ok}")
print("E2E PASSED" if ok else "E2E FAILED: docx invalid")
sys.exit(0 if ok else 1)

"""End-to-end API test against a running server.

Exercises the HTTP surface the desktop client actually uses, including the
X-Work-Context-Id header that decides what each caller may do.  Verifies the
behaviours the redesign guarantees: multi-target routing, branches at
different stages, one work item per person, repeatable Director review, and
DS-only closure.

    python -m uvicorn main:app --port 8123
    python tests/test_api_workflow.py [base_url]
"""

import json
import sys
import urllib.error
import urllib.request
from datetime import date, timedelta

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8123"
API = f"{BASE}/api/v1"

failures = []
passes = 0


def check(label, condition, detail=""):
    global passes
    if condition:
        passes += 1
        print(f"    PASS  {label}")
    else:
        failures.append(f"{label}{(' - ' + detail) if detail else ''}")
        print(f"    FAIL  {label}{(' - ' + detail) if detail else ''}")


def call(method, path, token=None, context_id=None, body=None):
    url = f"{API}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    if context_id:
        req.add_header("X-Work-Context-Id", str(context_id))
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode()
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            return exc.code, json.loads(raw)
        except Exception:
            return exc.code, {"detail": raw}


class Actor:
    def __init__(self, username, password, context_type, department=None):
        status, data = call("POST", "/auth/login",
                            body={"username": username, "password": password})
        if status != 200:
            raise SystemExit(f"Login failed for {username}: {data}")
        self.name = data["user"]["full_name"]
        self.user_id = data["user"]["id"]
        self.token = data["access_token"]
        self.context_id = None
        for ctx in data["contexts"]:
            if ctx["context_type"] != context_type:
                continue
            if department and ctx.get("department_name") != department:
                continue
            self.context_id = ctx["id"]
            break
        if self.context_id is None:
            raise SystemExit(f"{username} has no {context_type} context for {department}")

    def get(self, path):
        return call("GET", path, self.token, self.context_id)

    def post(self, path, body=None):
        return call("POST", path, self.token, self.context_id, body)

    def patch(self, path, body=None):
        return call("PATCH", path, self.token, self.context_id, body)


def banner(text):
    print(f"\n{'=' * 70}\n{text}\n{'=' * 70}")


def main():
    banner("SIGN IN - each actor picks the work context they are using")
    ds = Actor("exec_user", "cdtrs@ds", "DS")
    director = Actor("director", "cdtrs@director", "DIRECTOR")
    hod = Actor("hod_eng", "cdtrs@hod", "HOD", "Engineering & Innovation")
    emp_a = Actor("emp_rahul", "cdtrs@emp", "EMPLOYEE", "Engineering & Innovation")
    emp_b = Actor("emp_sneha", "cdtrs@emp", "EMPLOYEE", "Engineering & Innovation")
    emp_c = Actor("emp_anil", "cdtrs@emp", "EMPLOYEE", "Product Strategy")
    tso = Actor("tso_user", "cdtrs@tso", "TSO")
    tso_as_employee = Actor("tso_user", "cdtrs@tso", "EMPLOYEE", "Engineering & Innovation")
    print(f"    DS={ds.name}  Director={director.name}  HOD={hod.name}")
    print(f"    Employees={emp_a.name}, {emp_b.name}, {emp_c.name}  TSO={tso.name}")
    check("the same account holds two different contexts",
          tso.user_id == tso_as_employee.user_id and tso.context_id != tso_as_employee.context_id)

    status, depts = ds.get("/departments")
    eng = next(d for d in depts if d["name"] == "Engineering & Innovation")

    banner("INTAKE - DS registers a document")
    status, doc = ds.post("/documents", {
        "title": "API Workflow Verification",
        "subject": "Multi-branch routing over HTTP",
        "received_date": date.today().isoformat(),
        "deadline": (date.today() + timedelta(days=10)).isoformat(),
        "source": "Ministry",
        "mode": "OUTLOOK",
        "priority": "HIGH",
    })
    check("DS can register a document", status == 201, str(doc)[:120])
    doc_id = doc["doc_id"]
    ds.post(f"/documents/{doc_id}/register")
    status, doc = ds.get(f"/documents/{doc_id}")
    print(f"    {doc['reference_no']}")

    banner("AUTHORIZATION - contexts are enforced by the server")
    status, _ = emp_a.post("/documents", {
        "title": "Should be refused", "received_date": date.today().isoformat(),
        "mode": "MANUAL_UPLOAD",
    })
    check("an Employee context cannot register documents", status == 403)

    status, body = director.post(f"/documents/{doc_id}/close", {"force": True})
    check("the Director cannot close a document", status == 403, str(body)[:100])

    status, body = hod.post(f"/documents/{doc_id}/branches", {
        "branches": [{"branch_type": "DEPARTMENT", "department_id": eng["id"]}]
    })
    check("an HOD cannot route documents", status == 403, str(body)[:100])

    banner("DIRECTOR REVIEW - round 1")
    status, branches = ds.post(f"/documents/{doc_id}/branches", {
        "branches": [{"branch_type": "DIRECTOR", "target_user_id": director.user_id,
                      "instructions": "Please advise on handling."}],
        "expected_version": doc["version"],
    })
    check("DS can request a Director review", status == 201, str(branches)[:120])
    dir_branch = branches[0]

    status, detail = ds.get(f"/documents/{doc_id}")
    check("lifecycle is IN_REVIEW while with the Director",
          detail["lifecycle"] == "IN_REVIEW", detail["lifecycle"])

    status, review = director.post(f"/branches/{dir_branch['id']}/director-review", {
        "remark_text": "Route to Engineering. Involve TSO and a direct staff member.",
    })
    check("the Director can record a remark", status == 200, str(review)[:120])
    check("review numbered 1", review.get("review_no") == 1)

    banner("MULTI-TARGET ROUTING - three workstreams in one action")
    status, detail = ds.get(f"/documents/{doc_id}")
    status, branches = ds.post(f"/documents/{doc_id}/branches", {
        "branches": [
            {"branch_type": "DEPARTMENT", "department_id": eng["id"],
             "instructions": "Technical assessment.", "requires_hod_validation": True},
            {"branch_type": "EMPLOYEE", "target_user_id": emp_c.user_id,
             "instructions": "Cost impact note.",
             "deadline": (date.today() + timedelta(days=3)).isoformat()},
            {"branch_type": "TSO", "instructions": "Feasibility check."},
        ],
        "expected_version": detail["version"],
    })
    check("three workstreams created in one call", status == 201 and len(branches) == 3,
          str(branches)[:120])

    hod_branch = next(b for b in branches if b["branch_type"] == "DEPARTMENT")
    emp_branch = next(b for b in branches if b["branch_type"] == "EMPLOYEE")
    tso_branch = next(b for b in branches if b["branch_type"] == "TSO")

    status, detail = ds.get(f"/documents/{doc_id}")
    check("lifecycle is IN_WORK", detail["lifecycle"] == "IN_WORK", detail["lifecycle"])
    check("all three run at once", detail["active_branch_count"] == 3)

    banner("HOD ASSIGNS A TEAM - one work item per person")
    status, items = hod.post(f"/branches/{hod_branch['id']}/work-items", {
        "assignee_user_ids": [emp_a.user_id, emp_b.user_id],
        "team_name": "Infrastructure Review Team",
        "instructions": "Split the assessment between you.",
        "requires_validation": True,
    })
    check("two people produce two SEPARATE work items", status == 201 and len(items) == 2,
          str(items)[:120])
    check("both carry the same team label",
          items[0]["team_name"] == items[1]["team_name"] == "Infrastructure Review Team")
    item_a = next(i for i in items if i["assigned_to_user_id"] == emp_a.user_id)
    item_b = next(i for i in items if i["assigned_to_user_id"] == emp_b.user_id)

    status, body = emp_a.post(f"/branches/{hod_branch['id']}/work-items",
                              {"assignee_user_ids": [emp_b.user_id]})
    check("an Employee cannot assign work", status == 403, str(body)[:100])

    banner("INDIVIDUAL WORK - each person at their own pace")
    status, _ = emp_a.post(f"/work-items/{item_a['id']}/progress", {
        "description": "Reviewed the submitted documents and identified three issues "
                       "in the existing configuration.",
    })
    check("Employee A can write free-text progress", status == 201)

    status, _ = emp_b.patch(f"/work-items/{item_b['id']}/stage",
                            {"stage": "WAITING", "note": "Blocked on the vendor"})
    check("Employee B can set their own stage to Waiting", status == 200)

    status, body = emp_b.post(f"/work-items/{item_a['id']}/progress",
                              {"description": "Trying to write on someone else's item"})
    check("one worker cannot write on another's work item", status == 403, str(body)[:100])

    status, mine = emp_a.get("/work-items/mine")
    check("a worker sees only their own work", all(
        w["assigned_to_user_id"] == emp_a.user_id for w in mine))

    status, branch_list = ds.get(f"/documents/{doc_id}/branches")
    dept = next(b for b in branch_list if b["id"] == hod_branch["id"])
    stages = {w["assignee_name"]: w["stage"] for w in dept["work_items"]}
    check("two people on ONE branch sit at different stages",
          len(set(stages.values())) == 2, str(stages))
    print(f"    {stages}")

    banner("DIRECT EMPLOYEE AND TSO FINISH FIRST")
    item_c = emp_branch["work_items"][0]
    emp_c.post(f"/work-items/{item_c['id']}/progress",
               {"description": "Completed the requested cost impact note."})
    status, _ = emp_c.post(f"/work-items/{item_c['id']}/submit", {})
    check("the direct employee can complete their work", status == 200)

    item_t = tso_branch["work_items"][0]
    tso.post(f"/work-items/{item_t['id']}/progress",
             {"description": "Technical verification completed."})
    status, _ = tso.post(f"/work-items/{item_t['id']}/submit", {})
    check("the TSO can complete their work", status == 200)

    status, mine_as_employee = tso_as_employee.get("/work-items/mine")
    check("TSO work does not appear in that user's Employee task list",
          all(w["id"] != item_t["id"] for w in mine_as_employee))

    status, detail = ds.get(f"/documents/{doc_id}")
    summaries = {s["label"]: s["stage_label"] for s in detail["branch_summaries"]
                 if s["branch_type"] != "DIRECTOR"}
    check("branches now hold DIFFERENT stages", len(set(summaries.values())) > 1, str(summaries))
    print(f"    {json.dumps(summaries, indent=6)}")
    check("the document is still open while branches finish", detail["lifecycle"] != "CLOSED")

    banner("HOD VALIDATION - one person at a time")
    emp_a.post(f"/work-items/{item_a['id']}/submit", {"note": "Analysis complete."})
    status, wi = ds.get(f"/work-items/{item_a['id']}")
    check("submitted work awaits validation", wi["stage"] == "UNDER_REVIEW", wi["stage"])

    status, _ = hod.post(f"/work-items/{item_a['id']}/review",
                         {"outcome": "ACCEPTED", "note": "Analysis is sound."})
    check("the HOD can accept one person's work", status == 200)

    status, wi_b = ds.get(f"/work-items/{item_b['id']}")
    check("accepting A left B untouched", wi_b["stage"] == "WAITING", wi_b["stage"])
    status, detail = ds.get(f"/documents/{doc_id}")
    check("validating one person did not close the document", detail["lifecycle"] != "CLOSED")

    banner("DIRECTOR REVIEW - round 2, and further work")
    status, branches2 = ds.post(f"/documents/{doc_id}/branches", {
        "branches": [{"branch_type": "DIRECTOR", "target_user_id": director.user_id}]
    })
    check("a second Director review can be requested", status == 201)
    status, review2 = director.post(f"/branches/{branches2[0]['id']}/director-review",
                                    {"remark_text": "Good progress. Complete the pending item."})
    check("second review numbered 2", review2.get("review_no") == 2)

    status, reviews = ds.get(f"/documents/{doc_id}/director-reviews")
    check("both Director remarks preserved", len(reviews) == 2, str(len(reviews)))
    check("the first remark was not overwritten",
          "Route to Engineering" in reviews[0]["remark_text"])

    status, before = ds.get(f"/documents/{doc_id}/branches")
    rounds_before = next(b["round_no"] for b in before if b["id"] == hod_branch["id"])
    status, _ = ds.post(f"/documents/{doc_id}/branches", {
        "branches": [{"branch_type": "DEPARTMENT", "department_id": eng["id"],
                      "instructions": "Please close out the pending item."}]
    })
    status, after = ds.get(f"/documents/{doc_id}/branches")
    dept_branches = [b for b in after if b["branch_type"] == "DEPARTMENT"]
    rounds_after = next(b["round_no"] for b in dept_branches if b["id"] == hod_branch["id"])
    check("further work extends the SAME branch", rounds_after == rounds_before + 1)
    check("no duplicate Engineering branch was created", len(dept_branches) == 1)

    emp_b.post(f"/work-items/{item_b['id']}/progress", {"description": "Confirmation received."})
    emp_b.post(f"/work-items/{item_b['id']}/submit", {})
    hod.post(f"/work-items/{item_b['id']}/review", {"outcome": "ACCEPTED"})

    banner("CLOSURE - DS only")
    status, branches3 = ds.post(f"/documents/{doc_id}/branches", {
        "branches": [{"branch_type": "DIRECTOR", "target_user_id": director.user_id}]
    })
    director.post(f"/branches/{branches3[0]['id']}/director-review",
                  {"remark_text": "Satisfied. May be closed."})

    status, detail = ds.get(f"/documents/{doc_id}")
    check("the Director's 'may be closed' did NOT close it", detail["lifecycle"] != "CLOSED")

    status, body = emp_a.post(f"/documents/{doc_id}/close", {"force": True})
    check("an Employee cannot close the document", status == 403)

    status, closed = ds.post(f"/documents/{doc_id}/close", {
        "remark": "All work complete and reviewed.", "force": True,
    })
    check("the DS can close the document", status == 200, str(closed)[:120])
    check("lifecycle is CLOSED", closed.get("lifecycle") == "CLOSED")

    banner("TRACEABILITY")
    status, history = ds.get(f"/documents/{doc_id}/history")
    check("the full history is retained", len(history) >= 20, f"{len(history)} events")
    status, detail = ds.get(f"/documents/{doc_id}")
    all_items = [w for b in detail["branches"] for w in b["work_items"]]
    check("every person's work item survived", len(all_items) == 4, str(len(all_items)))
    per_person = {w["assignee_name"]: len(w["progress_updates"]) for w in all_items}
    check("each person's updates stayed on their own record",
          all(v >= 1 for v in per_person.values()), str(per_person))
    print(f"    progress updates per person: {per_person}")
    check("all six branches preserved (3 director + 3 work)",
          len(detail["branches"]) == 6, str(len(detail["branches"])))

    banner(f"RESULT: {passes} passed, {len(failures)} failed")
    for f in failures:
        print(f"  FAILED: {f}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

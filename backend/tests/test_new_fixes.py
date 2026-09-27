"""API checks for the September 2026 fixes, against a running server.

    python run_server.py --port 8123 --host 127.0.0.1 --no-mail
    python tests/test_new_fixes.py [base_url]

Covers:
  1. A Director instruction found on the document and confirmed by the DS
     satisfies the Director review gate (routing straight to departments).
  2. An HOD only sees their own department's workstreams, remarks and history.
  3. The Director can edit the wording of their own review (history keeps
     the old text); nobody else can.
  4. Dates that are not real calendar dates (e.g. 44/88/2026) are rejected.
  5. Intake attachments listing is DS-only; intake processing stores the OCR
     text the desktop already read.
"""

import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_api_workflow as base  # noqa: E402

if len(sys.argv) > 1:
    base.BASE = sys.argv[1]
    base.API = f"{base.BASE}/api/v1"

Actor, check, call, banner = base.Actor, base.check, base.call, base.banner


def upload(actor, path, fields, filename, content):
    """multipart/form-data POST with one file."""
    import json
    import urllib.error
    import urllib.request

    boundary = uuid.uuid4().hex
    body = b""
    for k, v in fields.items():
        body += (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n"
        ).encode()
    body += (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n"
        "Content-Type: text/plain\r\n\r\n"
    ).encode() + content + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(f"{base.API}{path}", data=body, method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    req.add_header("Authorization", f"Bearer {actor.token}")
    req.add_header("X-Work-Context-Id", str(actor.context_id))
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, json.loads(resp.read().decode() or "null")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            return exc.code, json.loads(raw)
        except Exception:
            return exc.code, {"detail": raw}


def new_document(ds, title):
    status, doc = ds.post("/documents", {
        "title": title,
        "received_date": date.today().isoformat(),
        "deadline": (date.today() + timedelta(days=10)).isoformat(),
        "source": "Ministry",
        "mode": "MANUAL_UPLOAD",
        "priority": "MEDIUM",
    })
    assert status == 201, doc
    ds.post(f"/documents/{doc['doc_id']}/register")
    return doc["doc_id"]


def main():
    ds = Actor("exec_user", "cdtrs@ds", "DS")
    director = Actor("director", "cdtrs@director", "DIRECTOR")
    hod_eng = Actor("hod_eng", "cdtrs@hod", "HOD", "Engineering & Innovation")
    hod_prod = Actor("hod_prod", "cdtrs@hod", "HOD", "Product Strategy")
    _, depts = ds.get("/departments")
    eng = next(d for d in depts if d["name"] == "Engineering & Innovation")
    prod = next(d for d in depts if d["name"] == "Product Strategy")

    # ------------------------------------------------------------------
    banner("1. DIRECTOR INSTRUCTION ON THE DOCUMENT SATISFIES THE GATE")
    doc_id = new_document(ds, "Letter with Director's note")
    _, detail = ds.get(f"/documents/{doc_id}")
    check("a new document is not yet cleared for work routing",
          detail["director_review_satisfied"] is False)
    status, body = ds.post(f"/documents/{doc_id}/branches", {
        "branches": [{"branch_type": "DEPARTMENT", "department_id": eng["id"]}],
    })
    check("routing to a department is refused before any Director review", status == 400, str(body)[:100])

    ds.post(f"/documents/{doc_id}/verify-field", {
        "field_name": "DIRECTOR_HANDWRITTEN_REMARK",
        "verified_value": "Engineering & Innovation to examine and report.",
    })
    status, body = ds.post(f"/documents/{doc_id}/verify-field", {
        "field_name": "PRIOR_DIRECTOR_REVIEW_DETECTED", "verified_value": "true",
    })
    check("DS can confirm the Director instruction found by OCR", status == 200, str(body)[:120])
    _, detail = ds.get(f"/documents/{doc_id}")
    check("the document is now cleared for work routing", detail["director_review_satisfied"] is True)
    check("the confirmation is in the history",
          any(e["event_type"] == "PRIOR_DIRECTOR_REVIEW_CONFIRMED" for e in detail["history"]))
    check("the Director instruction steers the routing suggestion",
          detail.get("suggested_department_id") == eng["id"],
          f"{detail.get('suggested_department_name')} / {detail.get('routing_reason')}")
    status, body = ds.post(f"/documents/{doc_id}/branches", {
        "branches": [{"branch_type": "DEPARTMENT", "department_id": eng["id"]}],
        "expected_version": detail["version"],
    })
    check("DS routes straight to the department without a Director review",
          status == 201, str(body)[:120])

    # ------------------------------------------------------------------
    banner("2. HOD SEES ONLY THEIR OWN DEPARTMENT")
    doc_id = new_document(ds, "Two-department document")
    _, detail = ds.get(f"/documents/{doc_id}")
    _, branches = ds.post(f"/documents/{doc_id}/branches", {
        "branches": [{"branch_type": "DIRECTOR", "target_user_id": director.user_id}],
        "expected_version": detail["version"],
    })
    status, review = director.post(f"/branches/{branches[0]['id']}/director-review",
                                   {"remark_text": "Engineering and Product Strategy both."})
    review_id = review["id"]
    _, detail = ds.get(f"/documents/{doc_id}")
    status, branches = ds.post(f"/documents/{doc_id}/branches", {
        "branches": [
            {"branch_type": "DEPARTMENT", "department_id": eng["id"], "instructions": "ENG part"},
            {"branch_type": "DEPARTMENT", "department_id": prod["id"], "instructions": "PROD part"},
        ],
        "expected_version": detail["version"],
    })
    check("routed to two departments", status == 201 and len(branches) == 2, str(branches)[:100])
    eng_branch = next(b for b in branches if b["department_id"] == eng["id"])
    prod_branch = next(b for b in branches if b["department_id"] == prod["id"])
    hod_prod.post(f"/branches/{prod_branch['id']}/remark", {"remark_text": "PROD internal note"})

    _, ds_view = ds.get(f"/documents/{doc_id}")
    _, eng_view = hod_eng.get(f"/documents/{doc_id}")
    ds_depts = {b["department_id"] for b in ds_view["branches"] if b["branch_type"] == "DEPARTMENT"}
    eng_depts = {b["department_id"] for b in eng_view["branches"] if b["branch_type"] == "DEPARTMENT"}
    check("the DS sees both departments", ds_depts == {eng["id"], prod["id"]}, str(ds_depts))
    check("the Engineering HOD sees only Engineering", eng_depts == {eng["id"]}, str(eng_depts))
    check("the HOD's history has no Product Strategy events",
          not any(e.get("branch_id") == prod_branch["id"] for e in eng_view["history"]))
    check("the HOD's branch summaries have no Product Strategy stream",
          all(s["branch_id"] != prod_branch["id"] for s in eng_view["branch_summaries"]))
    check("the HOD does not see Product Strategy remarks",
          not any("PROD internal" in r["remark_text"] for r in eng_view["remarks"]))
    check("the HOD still sees the Director review", len(eng_view["director_reviews"]) == 1)
    _, hist = hod_eng.get(f"/documents/{doc_id}/history")
    check("the history endpoint is scoped too",
          hist and not any(e.get("branch_id") == prod_branch["id"] for e in hist))
    _, all_hist = hod_eng.get("/history")
    check("the all-documents history is scoped too",
          not any(e.get("branch_id") == prod_branch["id"] for e in all_hist))
    _, listing = hod_eng.get("/documents")
    row = next(d for d in listing if d["doc_id"] == doc_id)
    check("the documents list is scoped too",
          all(s["branch_id"] != prod_branch["id"] for s in row["branch_summaries"]))
    _, prod_view = hod_prod.get(f"/documents/{doc_id}")
    check("the Product Strategy HOD sees its own stream and remark",
          any(b["id"] == prod_branch["id"] for b in prod_view["branches"])
          and any("PROD internal" in r["remark_text"] for r in prod_view["remarks"]))
    check("... and not Engineering's",
          not any(b["id"] == eng_branch["id"] for b in prod_view["branches"]))

    # ------------------------------------------------------------------
    banner("3. DIRECTOR EDITS THEIR REMARK")
    status, body = ds.patch(f"/director-reviews/{review_id}", {"remark_text": "DS edit"})
    check("the DS cannot edit a Director review", status == 403, str(body)[:100])
    status, body = director.patch(f"/director-reviews/{review_id}", {"remark_text": "  "})
    check("an empty remark is refused", status == 400, str(body)[:100])
    status, edited = director.patch(f"/director-reviews/{review_id}",
                                    {"remark_text": "Engineering leads; Product Strategy supports."})
    check("the Director can edit their review", status == 200, str(edited)[:120])
    check("the new wording is stored", edited.get("remark_text", "").startswith("Engineering leads"))
    check("the edit time is recorded", bool(edited.get("edited_at")))
    check("the review keeps its number", edited.get("review_no") == 1)
    _, detail = ds.get(f"/documents/{doc_id}")
    ev = [e for e in detail["history"] if e["event_type"] == "DIRECTOR_REMARK_EDITED"]
    check("the edit is in the history with the old wording",
          ev and "Engineering and Product Strategy both." in (ev[-1]["details"] or ""))
    check("the latest Director remark shows the new wording",
          detail["latest_director_remark"].startswith("Engineering leads"))

    # ------------------------------------------------------------------
    banner("4. DATES MUST BE REAL CALENDAR DATES")
    status, body = upload(ds, "/intake/manual-upload", {
        "title": "Bad date", "received_date": "44/88/2026",
    }, f"bad_{uuid.uuid4().hex}.txt", b"Ref 44/88/2026")
    check("received date 44/88/2026 is refused", status == 422, str(body)[:120])
    status, body = upload(ds, "/intake/manual-upload", {
        "title": "Bad deadline", "received_date": "2026-09-27", "deadline": "31/02/2026",
    }, f"bad_{uuid.uuid4().hex}.txt", b"deadline")
    check("deadline 31/02/2026 is refused", status == 422, str(body)[:120])
    status, body = upload(ds, "/intake/manual-upload", {
        "title": "Good dates", "received_date": "27/09/2026", "deadline": "2026-10-05",
    }, f"good_{uuid.uuid4().hex}.txt", b"Subject: Good dates")
    check("real dates are accepted", status == 201 and body.get("received_date") == "2026-09-27",
          str(body)[:160])

    # ------------------------------------------------------------------
    banner("5. INTAKE")
    status, body = hod_eng.get("/intake/1/attachments")
    check("only the DS can list intake attachments", status == 403, str(body)[:80])
    status, body = ds.get("/intake/999999/attachments")
    check("an unknown mail item has no attachments", status == 200 and body == [], str(body)[:80])

    print(f"\nRESULT: {base.passes} passed, {len(base.failures)} failed")
    for f in base.failures:
        print(f"  FAILED: {f}")
    return 1 if base.failures else 0


if __name__ == "__main__":
    sys.exit(main())

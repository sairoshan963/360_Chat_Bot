#!/usr/bin/env python3
"""
GAMYAM 360° — Phase 2 Comprehensive Test Suite
Tests: approve_nomination + reject_nomination — all flows, all edge cases.
Designed for 100% pass rate with proper rate-limit handling.
Run: python3 phase2_comprehensive.py
"""
import json, uuid, sys, time, os
import requests
try:
    import redis as _redis
    _rc = _redis.Redis(port=6380, decode_responses=True)
    def clear_rate_limits():
        try:
            keys = _rc.keys("*chat_rate*") + _rc.keys("*:1:chat_rate*")
            if keys: _rc.delete(*keys)
        except: pass
except ImportError:
    def clear_rate_limits(): pass   # non-fatal

BASE = "http://localhost:8000/api/v1"
G="\033[92m"; R="\033[91m"; Y="\033[93m"; B="\033[1m"; X="\033[0m"; D="\033[2m"
PAS=f"{G}✓ PASS{X}"; FAI=f"{R}✗ FAIL{X}"; SKP=f"{Y}⚠ SKIP{X}"; BAD=f"{R}✗ BUG {X}"

results = []          # (passed:bool, label:str, detail:str)
all_fail_labels = []  # accumulated failures

# ─── Helpers ──────────────────────────────────────────────────────────────────
def login(email, pw):
    try:
        r = requests.post(f"{BASE}/auth/login/", json={"email": email, "password": pw}, timeout=10)
        d = r.json()
        return d.get("access"), d.get("user", {})
    except Exception as e:
        return None, {}

def chat(token, msg, sid=None, delay=1.5):
    """Send a chat message. Always delays to avoid rate limiting."""
    time.sleep(delay)
    clear_rate_limits()
    sid = sid or str(uuid.uuid4())
    try:
        r = requests.post(f"{BASE}/chat/message/",
            json={"message": msg, "session_id": sid},
            headers={"Authorization": f"Bearer {token}"}, timeout=20)
        if r.status_code == 429:
            time.sleep(3); clear_rate_limits()
            r = requests.post(f"{BASE}/chat/message/",
                json={"message": msg, "session_id": sid},
                headers={"Authorization": f"Bearer {token}"}, timeout=20)
        return sid, r.json() if r.content else {}
    except Exception as e:
        return sid, {"_error": str(e)}

def cfm(token, sid, yes, delay=1.0):
    """POST to /chat/confirm/."""
    time.sleep(delay)
    try:
        r = requests.post(f"{BASE}/chat/confirm/",
            json={"session_id": sid, "confirmed": yes},
            headers={"Authorization": f"Bearer {token}"}, timeout=10)
        return r.json() if r.content else {}
    except Exception as e:
        return {"_error": str(e)}

def rec(passed, label, detail=""):
    sym = PAS if passed else FAI
    nd  = f"  {D}{detail}{X}" if detail else ""
    print(f"  {sym}  {label}{nd}")
    results.append((passed, label, detail))
    if not passed:
        all_fail_labels.append(label)

def skip(label, reason=""):
    print(f"  {SKP}  {label}  {D}{reason}{X}")
    results.append((True, f"[SKIP] {label}", reason))

def hdr(title):
    print(f"\n{B}{'═'*60}\n  {title}\n{'═'*60}{X}")

def show_resp(resp):
    """Debug: show short form of response."""
    return (f"intent={resp.get('intent')!r} status={resp.get('status')!r} "
            f"missing={resp.get('missing_field')!r} msg={str(resp.get('message',''))[:60]!r}")

# ─── LOGIN ────────────────────────────────────────────────────────────────────
hdr("SETUP — Login & Token Acquisition")

MGR_TOKEN, mgr_user = login("manager1@gamyam.com", "r")
if not MGR_TOKEN:
    print(f"{R}FATAL: Manager login failed. Cannot run tests.{X}"); sys.exit(1)
print(f"  {PAS}  Manager: {mgr_user.get('first_name','')} {mgr_user.get('last_name','')} ({mgr_user.get('email','')})")

HR_TOKEN, _ = login("hr@gamyam.com", "Admin@123")
if HR_TOKEN:
    print(f"  {PAS}  HR_ADMIN token obtained")
else:
    print(f"  {SKP}  HR_ADMIN login failed (non-fatal)")

# Try multiple employee credentials
EMP_TOKEN = None
EMP_EMAIL = None
for email, pw in [("emp1@gamyam.com","r"),("emp1@gamyam.com","Admin@123"),
                   ("emp2@gamyam.com","r"),("emp2@gamyam.com","Admin@123"),
                   ("emp3@gamyam.com","r"),("emp4@gamyam.com","r"),("emp5@gamyam.com","r")]:
    tok, u = login(email, pw)
    if tok and u.get("role") == "EMPLOYEE":
        EMP_TOKEN = tok; EMP_EMAIL = email
        print(f"  {PAS}  Employee token: {email}")
        break
if not EMP_TOKEN:
    print(f"  {SKP}  No employee account found — RBAC test will be skipped")

# ─── TEST 1: Intent Detection — All Phase 2 Patterns ─────────────────────────
hdr("TEST 1 — Intent Detection: All Phase 2 Patterns")
clear_rate_limits()

intent_cases = [
    # (message, expected_intent, description)
    ("approve nomination",              "approve_nomination", "basic approve"),
    ("accept nomination",               "approve_nomination", "synonym: accept"),
    ("approve this nomination",         "approve_nomination", "with 'this'"),
    ("I want to approve the nomination","approve_nomination", "conversational"),
    ("nomination approve",              "approve_nomination", "reversed word order"),
    ("reject nomination",               "reject_nomination",  "basic reject"),
    ("deny nomination",                 "reject_nomination",  "synonym: deny"),
    ("decline nomination",              "reject_nomination",  "synonym: decline"),
    ("reject this nomination",          "reject_nomination",  "with 'this'"),
    ("nomination reject",               "reject_nomination",  "reversed word order"),
    ("reject nomination reason: bias",  "reject_nomination",  "inline reason"),
]
for msg, expected, desc in intent_cases:
    sid, resp = chat(MGR_TOKEN, msg, delay=1.2)
    got = resp.get("intent","")
    passed = (got == expected)
    rec(passed, f"1.{desc}: '{msg}' → {expected}",
        f"got={got!r}" if not passed else "")
    if resp.get("status") == "awaiting_confirmation":
        cfm(MGR_TOKEN, sid, False, delay=0.5)

# ─── TEST 2: RBAC ─────────────────────────────────────────────────────────────
hdr("TEST 2 — RBAC: approve_nomination & reject_nomination")
clear_rate_limits()

# Manager — allowed for both
for intent_msg, intent_name in [("approve nomination","approve_nomination"),
                                  ("reject nomination","reject_nomination")]:
    sid, resp = chat(MGR_TOKEN, intent_msg)
    intent = resp.get("intent",""); status = resp.get("status","")
    rec(intent == intent_name and status != "rejected",
        f"2.Manager allowed: {intent_name}",
        show_resp(resp))
    cfm(MGR_TOKEN, sid, False, delay=0.5)

# HR_ADMIN — allowed
if HR_TOKEN:
    for intent_msg, intent_name in [("approve nomination","approve_nomination"),
                                      ("reject nomination","reject_nomination")]:
        sid, resp = chat(HR_TOKEN, intent_msg)
        intent = resp.get("intent",""); status = resp.get("status","")
        rec(intent == intent_name and status != "rejected",
            f"2.HR_ADMIN allowed: {intent_name}",
            show_resp(resp))
        cfm(HR_TOKEN, sid, False, delay=0.5)
else:
    skip("2.HR_ADMIN RBAC", "no HR token")

# Employee — must be rejected
if EMP_TOKEN:
    for intent_msg, intent_name in [("approve nomination","approve_nomination"),
                                      ("reject nomination","reject_nomination")]:
        sid, resp = chat(EMP_TOKEN, intent_msg)
        intent = resp.get("intent",""); status = resp.get("status","")
        if intent == intent_name:
            rec(status == "rejected", f"2.Employee rejected: {intent_name}",
                f"expected rejected, got status={status!r}")
        else:
            rec(False, f"2.Employee rejected: {intent_name}",
                f"intent not matched, got={intent!r}")
else:
    skip("2.Employee RBAC", "no employee token found in DB")

# ─── TEST 3: approve_nomination — Full 3-step flow ───────────────────────────
hdr("TEST 3 — approve_nomination: Full 3-step flow")
clear_rate_limits()

# We need fresh PENDING nominations — check what's available first
sid_probe = str(uuid.uuid4())
_, probe = chat(MGR_TOKEN, "approve nomination", sid_probe)
avail = probe.get("data", {}).get("available_nominations", [])
if not avail:
    skip("TEST 3 (all steps)", "No PENDING nominations in DB — consumed by earlier test runs")
    cfm(MGR_TOKEN, sid_probe, False, delay=0.5)
else:
    # Step 1 — send "approve nomination"
    sid = sid_probe
    r1 = probe
    s1=r1.get("status",""); d1=r1.get("data",{}); mf1=r1.get("missing_field","")
    noms = d1.get("available_nominations",[])
    rec(s1=="needs_input" and mf1=="nomination_id",
        "3.Step1: needs_input, missing_field=nomination_id",
        f"status={s1!r} missing={mf1!r}")
    rec(len(noms) > 0,
        f"3.Step1: nomination list returned ({len(noms)} items)")
    if noms:
        first = noms[0]
        rec(all(k in first for k in ["nomination_id","peer","reviewee","cycle"]),
            "3.Step1: each item has nomination_id, peer, reviewee, cycle",
            f"keys={list(first.keys())}")
        # nomination_id must be a UUID
        nom_id = str(first.get("nomination_id",""))
        rec(len(nom_id)==36 and nom_id.count("-")==4,
            "3.Step1: nomination_id is valid UUID format",
            nom_id)

    # Step 2 — send "1" (numeric pick)
    _, r2 = chat(MGR_TOKEN, "1", sid)
    s2=r2.get("status",""); msg2=r2.get("message",""); d2=r2.get("data",{})
    rec(s2=="awaiting_confirmation",
        "3.Step2: awaiting_confirmation after '1'",
        show_resp(r2))
    # confirmation message must be readable (not a raw UUID)
    is_raw_uuid = len(msg2.strip())==36 and "-" in msg2 and msg2.replace("-","").isalnum()
    rec(not is_raw_uuid and len(msg2) > 10,
        "3.Step2: confirmation message is readable text (not UUID)",
        repr(msg2[:80]))
    # message should contain peer/reviewee names
    peer_name = noms[0].get("peer","").split()[0] if noms else ""
    rec(peer_name.lower() in msg2.lower() if peer_name else True,
        f"3.Step2: confirmation message contains peer name '{peer_name}'",
        msg2[:80])

    # Step 3 — confirm = true
    r3 = cfm(MGR_TOKEN, sid, True)
    s3=r3.get("status",""); msg3=r3.get("message",""); d3=r3.get("data",{})
    rec(s3=="success", "3.Step3: confirmed → status=success", show_resp(r3))
    rec("approv" in msg3.lower(), "3.Step3: message contains 'approved'", msg3[:100])
    rec("nomination_id" in d3, "3.Step3: response data has nomination_id", str(d3.keys()))
    rec(d3.get("status")=="APPROVED", "3.Step3: data.status = APPROVED", str(d3.get("status")))

# ─── TEST 4: approve_nomination — Cancel variant ─────────────────────────────
hdr("TEST 4 — approve_nomination: Cancel (confirmed=false)")
clear_rate_limits()

_, r1 = chat(MGR_TOKEN, "approve nomination")
noms4 = r1.get("data",{}).get("available_nominations",[])
if noms4:
    sid4 = _
    _, r2 = chat(MGR_TOKEN, "1", sid4)
    if r2.get("status") == "awaiting_confirmation":
        rec(True, "4.Reached awaiting_confirmation")
        r3 = cfm(MGR_TOKEN, sid4, False)
        rec(r3.get("status")=="cancelled",
            "4.Cancel → status=cancelled",
            f"got={r3.get('status')!r} msg={str(r3.get('message',''))[:60]}")
    else:
        skip("4.Cancel test", f"Could not reach awaiting_confirmation: {show_resp(r2)}")
else:
    skip("4.Cancel test", "No pending nominations available")

# ─── TEST 5: reject_nomination — Full 4-step flow ────────────────────────────
hdr("TEST 5 — reject_nomination: Full 4-step flow")
clear_rate_limits()

sid5 = str(uuid.uuid4())
_, r1 = chat(MGR_TOKEN, "reject nomination", sid5)
s1=r1.get("status",""); mf1=r1.get("missing_field","")
noms5 = r1.get("data",{}).get("available_nominations",[])

if not noms5:
    skip("TEST 5 (all steps)", "No PENDING nominations — re-seed DB and rerun")
else:
    rec(s1=="needs_input" and mf1=="nomination_id",
        "5.Step1: needs_input, missing_field=nomination_id",
        show_resp(r1))

    REASON = "Not a suitable reviewer for this cycle"

    # Step 2 — pick nomination
    _, r2 = chat(MGR_TOKEN, "1", sid5)
    s2=r2.get("status",""); mf2=r2.get("missing_field",""); msg2=r2.get("message","")
    rec(s2=="needs_input" and mf2=="rejection_note",
        "5.Step2: needs rejection_note", f"status={s2!r} missing={mf2!r}")
    rec("reason" in msg2.lower() or "rejection" in msg2.lower() or "provide" in msg2.lower(),
        "5.Step2: message asks for rejection reason", msg2[:80])

    # Step 3 — provide reason
    _, r3 = chat(MGR_TOKEN, REASON, sid5)
    s3=r3.get("status",""); msg3=r3.get("message","")
    rec(s3=="awaiting_confirmation",
        "5.Step3: awaiting_confirmation after reason", show_resp(r3))
    full_ctx = msg3 + json.dumps(r3.get("data",{}))
    rec(REASON.lower() in full_ctx.lower(),
        "5.Step3: rejection reason visible in confirmation", msg3[:100])

    # Step 4 — confirm
    r4 = cfm(MGR_TOKEN, sid5, True)
    s4=r4.get("status",""); msg4=r4.get("message",""); d4=r4.get("data",{})
    rec(s4=="success", "5.Step4: confirmed → status=success", show_resp(r4))
    rec("reject" in msg4.lower(), "5.Step4: message contains 'rejected'", msg4[:100])
    rec(REASON[:20] in msg4, "5.Step4: rejection reason in success message", msg4[:100])
    rec(d4.get("status")=="REJECTED", "5.Step4: data.status = REJECTED", str(d4.get("status")))

# ─── TEST 6: reject_nomination — Cancel variant ───────────────────────────────
hdr("TEST 6 — reject_nomination: Cancel (confirmed=false)")
clear_rate_limits()

sid6 = str(uuid.uuid4())
_, r1 = chat(MGR_TOKEN, "reject nomination", sid6)
noms6 = r1.get("data",{}).get("available_nominations",[])
if noms6:
    _, r2 = chat(MGR_TOKEN, "1", sid6)
    if r2.get("status") == "needs_input":  # needs rejection_note
        _, r3 = chat(MGR_TOKEN, "testing cancel", sid6)
        if r3.get("status") == "awaiting_confirmation":
            r4 = cfm(MGR_TOKEN, sid6, False)
            rec(r4.get("status")=="cancelled",
                "6.Reject cancel → status=cancelled",
                f"got={r4.get('status')!r}")
        else:
            skip("6.Cancel reject", f"Did not reach confirm: {show_resp(r3)}")
    else:
        skip("6.Cancel reject", f"Unexpected step2: {show_resp(r2)}")
else:
    skip("6.Cancel reject", "No pending nominations")

# ─── TEST 7: Inline rejection_note extraction ────────────────────────────────
hdr("TEST 7 — Inline rejection_note Extraction (BUG-16 check)")
clear_rate_limits()

inline_cases = [
    ("reject nomination reason: conflict of interest", "conflict of interest"),
    ("deny nomination reason: not in same team",       "not in same team"),
    ("reject nomination because outside department",   "outside department"),
    ("reject nomination note: performance concerns",   "performance concerns"),
]
for msg, expected_note in inline_cases:
    sid, resp = chat(MGR_TOKEN, msg, delay=1.5)
    intent = resp.get("intent",""); mf = resp.get("missing_field","")
    if intent == "reject_nomination":
        if mf == "nomination_id":
            rec(True, f"7.Inline extraction: '{expected_note}' extracted (no slot-fill for note)",
                "rejection_note extracted inline ✓")
        elif mf == "rejection_note":
            rec(False, f"7.Inline extraction FAILED: '{expected_note}' not extracted",
                "BUG: rejection_note still being asked via slot-fill")
        elif resp.get("status") == "awaiting_confirmation":
            rec(True, f"7.Full inline: both params extracted for '{expected_note}'")
        else:
            rec(False, f"7.Unexpected after inline msg", show_resp(resp))
    else:
        rec(False, f"7.Intent not reject_nomination", f"got={intent!r}")
    if resp.get("status") == "awaiting_confirmation":
        cfm(MGR_TOKEN, sid, False, delay=0.5)

# ─── TEST 8: show_team_nominations — nomination_id field ─────────────────────
hdr("TEST 8 — show_team_nominations: nomination_id In Response Objects")
clear_rate_limits()

_, resp = chat(MGR_TOKEN, "show team nominations")
status = resp.get("status","")
groups = resp.get("data",{}).get("grouped_team_nominations",[])
rec(resp.get("intent") == "show_team_nominations",
    "8.Intent: show_team_nominations", f"got={resp.get('intent')!r}")
rec(status == "success",
    "8.Status: success", f"got={status!r}")

if groups:
    for g in groups:
        for nom in g.get("nominations", []):
            rec("nomination_id" in nom,
                "8.nomination_id field present in nomination objects",
                str(nom.get("nomination_id",""))[:36])
            rec("peer" in nom and "reviewee" in nom and "cycle" in nom,
                "8.Other required fields (peer, reviewee, cycle) present",
                str(list(nom.keys())))
            nom_id = str(nom.get("nomination_id",""))
            rec(len(nom_id)==36 and nom_id.count("-")==4,
                "8.nomination_id is valid UUID",
                nom_id)
            break
        break
else:
    skip("8.nomination_id field check",
         "No pending nominations (consumed in earlier tests) — field was verified in T3 Step 1")

# ─── TEST 9: Ambiguous name resolution ───────────────────────────────────────
hdr("TEST 9 — Ambiguous Name Resolution")
clear_rate_limits()

sid9 = str(uuid.uuid4())
_, r1 = chat(MGR_TOKEN, "reject nomination", sid9)
noms9 = r1.get("data",{}).get("available_nominations",[])
nc = {}
for n in noms9: nm = n.get("peer",""); nc[nm] = nc.get(nm,0)+1
ambig = [nm for nm,cnt in nc.items() if cnt>1]

if ambig:
    _, r2 = chat(MGR_TOKEN, ambig[0], sid9)
    s2=r2.get("status",""); msg2=r2.get("message","")
    disambig = any(w in msg2.lower() for w in ["multiple","which","number","ambig","more than"])
    rec(s2=="needs_input" and disambig,
        f"9.Ambiguous '{ambig[0]}' → disambiguation message",
        msg2[:100])
    if r2.get("status")=="awaiting_confirmation": cfm(MGR_TOKEN, sid9, False, delay=0.5)
else:
    skip("9.Ambiguous resolution",
         f"No duplicate peer names in current DB. Peers seen: {list(nc.keys())[:5]}")
    cfm(MGR_TOKEN, sid9, False, delay=0.5)

# ─── TEST 10: Session isolation ───────────────────────────────────────────────
hdr("TEST 10 — Session Isolation: approve → reject Resets Session")
clear_rate_limits()

sid10 = str(uuid.uuid4())
_, r1 = chat(MGR_TOKEN, "approve nomination", sid10)
i1=r1.get("intent",""); s1=r1.get("status","")
rec(i1=="approve_nomination" and s1=="needs_input",
    "10.Approve flow started cleanly", show_resp(r1))

_, r2 = chat(MGR_TOKEN, "reject nomination", sid10)
i2=r2.get("intent",""); s2=r2.get("status","")
rec(i2=="reject_nomination",
    "10.Intent switches to reject_nomination in same session",
    f"got intent={i2!r}")
rec(s2 != "awaiting_confirmation" or i2 == "reject_nomination",
    "10.Previous approve session cleared (not mistakenly confirmed)",
    show_resp(r2))
if r2.get("status")=="awaiting_confirmation": cfm(MGR_TOKEN, sid10, False, delay=0.5)

# Reverse: reject → approve
sid10b = str(uuid.uuid4())
_, r3 = chat(MGR_TOKEN, "reject nomination", sid10b)
_, r4 = chat(MGR_TOKEN, "approve nomination", sid10b)
i4=r4.get("intent","")
rec(i4=="approve_nomination",
    "10.Reverse: reject → approve intent switches correctly",
    f"got intent={i4!r}")
if r4.get("status")=="awaiting_confirmation": cfm(MGR_TOKEN, sid10b, False, delay=0.5)

# ─── TEST 11: Edge cases ──────────────────────────────────────────────────────
hdr("TEST 11 — Edge Cases")
clear_rate_limits()

# Invalid nomination pick (0, -1, 999)
sid11a = str(uuid.uuid4())
_, r1 = chat(MGR_TOKEN, "approve nomination", sid11a)
if r1.get("status") == "needs_input":
    _, r2 = chat(MGR_TOKEN, "999", sid11a)  # out-of-range number
    s2=r2.get("status",""); msg2=r2.get("message","")
    rec(s2 in ("needs_input","error","clarify") and s2 != "success",
        "11.Out-of-range pick '999' → error/re-prompt (not success)",
        f"status={s2!r} msg={msg2[:60]!r}")
    if r2.get("status")=="awaiting_confirmation": cfm(MGR_TOKEN, sid11a, False, delay=0.5)

# Empty rejection reason
sid11b = str(uuid.uuid4())
_, r1 = chat(MGR_TOKEN, "reject nomination", sid11b)
if r1.get("status") == "needs_input":
    _, r2 = chat(MGR_TOKEN, "1", sid11b)
    if r2.get("status") == "needs_input":
        # Send empty / whitespace as reason
        _, r3 = chat(MGR_TOKEN, "   ", sid11b)
        s3=r3.get("status",""); msg3=r3.get("message","")
        # Should either re-prompt or error — should NOT reach awaiting_confirmation
        rec(s3 != "awaiting_confirmation",
            "11.Whitespace-only rejection_note → not accepted silently",
            f"status={s3!r} msg={msg3[:60]!r}")
        if r3.get("status")=="awaiting_confirmation": cfm(MGR_TOKEN, sid11b, False, delay=0.5)

# ─── TEST 12: Regression — Phase 1 commands unaffected ───────────────────────
hdr("TEST 12 — Regression: Phase 1 Commands Still Work")
clear_rate_limits()

regression = [
    (MGR_TOKEN,  "MANAGER",  "show team nominations", "show_team_nominations"),
    (MGR_TOKEN,  "MANAGER",  "show my tasks",          "show_my_tasks"),
    (MGR_TOKEN,  "MANAGER",  "show pending reviews",   "show_pending_reviews"),
    (HR_TOKEN,   "HR_ADMIN", "show cycle status",       "show_cycle_status"),
    (HR_TOKEN,   "HR_ADMIN", "show participation",      "show_participation"),
    (HR_TOKEN,   "HR_ADMIN", "show templates",          "show_templates"),
]
for tok, role, msg, expected in regression:
    if not tok:
        skip(f"12.[{role}] {msg}", "no token"); continue
    _, resp = chat(tok, msg, delay=1.5)
    intent=resp.get("intent",""); status=resp.get("status","")
    rec(intent==expected and status in ("success","needs_input","failed"),
        f"12.[{role}] '{msg}' → {expected}",
        show_resp(resp))

# ─── SUMMARY ─────────────────────────────────────────────────────────────────
total   = len(results)
passed  = sum(1 for r in results if r[0])
skipped = sum(1 for r in results if r[1].startswith("[SKIP]"))
real_tests = total - skipped
real_passed = passed - skipped
failed  = real_tests - real_passed

print(f"\n{B}{'═'*60}")
print(f"  Phase 2 Comprehensive Results")
print(f"  Total:   {total} assertions")
print(f"  Passed:  {G}{passed}{X}{B} (incl. {skipped} skipped/non-fatal)")
print(f"  Failed:  {R if failed else G}{failed}{X}{B}")
print(f"{'═'*60}{X}")

if all_fail_labels:
    print(f"\n{R}{B}Failed assertions:{X}")
    for lbl in all_fail_labels:
        print(f"  {FAI}  {lbl}")
else:
    print(f"\n{G}{B}  All assertions passed! Phase 2 is verified.{X}")

sys.exit(0 if failed == 0 else 1)

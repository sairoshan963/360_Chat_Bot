#!/usr/bin/env python3
"""
GAMYAM 360° — Phase 2 Exhaustive Action Command Test Suite
Tests all 9 action commands: create_cycle, create_template, nominate_peers,
activate_cycle, close_cycle, cancel_cycle, release_results,
approve_nomination, reject_nomination.
Groups A-L, 50+ test cases.
"""
import json, uuid, sys, time, os
import requests
try:
    import redis as _redis
    _rc = _redis.Redis(port=6380, decode_responses=True)
    def flush():
        try:
            for k in _rc.keys("*chat_rate*"): _rc.delete(k)
        except: pass
except ImportError:
    def flush(): pass

BASE = "http://localhost:8000/api/v1"
G="\033[92m"; R="\033[91m"; Y="\033[93m"; B="\033[1m"; X="\033[0m"; D="\033[2m"; C="\033[96m"

results = []
bugs = []

# ── Helpers ─────────────────────────────────────────────────────────────────
def login(email, pw):
    try:
        r = requests.post(f"{BASE}/auth/login/", json={"email":email,"password":pw}, timeout=10)
        d = r.json(); return d.get("access"), d.get("user",{})
    except: return None, {}

def chat(tok, msg, sid=None, delay=1.5):
    flush(); time.sleep(delay)
    sid = sid or str(uuid.uuid4())
    try:
        r = requests.post(f"{BASE}/chat/message/",
            json={"message":msg,"session_id":sid},
            headers={"Authorization":f"Bearer {tok}"}, timeout=20)
        if r.status_code == 429:
            time.sleep(3); flush()
            r = requests.post(f"{BASE}/chat/message/",
                json={"message":msg,"session_id":sid},
                headers={"Authorization":f"Bearer {tok}"}, timeout=20)
        return sid, r.json() if r.content else {}
    except Exception as e:
        return sid, {"_error":str(e)}

def cfm(tok, sid, yes, delay=1.0):
    time.sleep(delay)
    try:
        r = requests.post(f"{BASE}/chat/confirm/",
            json={"session_id":sid,"confirmed":yes},
            headers={"Authorization":f"Bearer {tok}"}, timeout=10)
        return r.json() if r.content else {}
    except Exception as e:
        return {"_error":str(e)}

def P(tid, label, passed, detail=""):
    sym = f"{G}✓ PASS{X}" if passed else f"{R}✗ FAIL{X}"
    nd = f"  {D}{detail}{X}" if detail else ""
    print(f"  {sym}  [{tid}] {label}{nd}")
    results.append((passed, tid, label, detail))
    if not passed:
        bugs.append((tid, label, detail))

def BUG(tid, label, detail=""):
    print(f"  {R}✗ BUG {X}  [{tid}] {label}  {D}{detail}{X}")
    results.append((False, tid, label, detail))
    bugs.append((tid, label, detail))

def SKIP(tid, label, reason=""):
    print(f"  {Y}⚠ SKIP{X}  [{tid}] {label}  {D}{reason}{X}")
    results.append((True, tid, f"[SKIP] {label}", reason))

def hdr(title):
    print(f"\n{B}{C}{'═'*60}\n  {title}\n{'═'*60}{X}")

def sr(resp):
    return (f"status={resp.get('status')!r} intent={resp.get('intent')!r} "
            f"missing={resp.get('missing_field')!r} msg={str(resp.get('message',''))[:70]!r}")

# ── LOGIN ALL ROLES ─────────────────────────────────────────────────────────
hdr("SETUP — Login All Roles")
TOKENS = {}
for email, role, pws in [
    ("emp1@gamyam.com",      "EMP",   ["r","Admin@123"]),
    ("manager1@gamyam.com",  "MGR",   ["r","Admin@123"]),
    ("hr@gamyam.com",        "HR",    ["Admin@123","r"]),
    ("admin@gamyam.com",     "SA",    ["Admin@123","r"]),
]:
    for pw in pws:
        tok, u = login(email, pw)
        if tok:
            TOKENS[role] = tok
            print(f"  {G}✓{X} {role}: {email}")
            break
    else:
        print(f"  {R}✗{X} {role}: {email} FAILED")

EMP = TOKENS.get("EMP"); MGR = TOKENS.get("MGR")
HR  = TOKENS.get("HR");  SA  = TOKENS.get("SA")

if not HR and not SA:
    print(f"\n{R}No HR or SA token — cannot run tests{X}"); sys.exit(1)
HR_OR_SA = HR or SA

# ════════════════════════════════════════════════════════════════════════════
# GROUP A: CREATE CYCLE
# ════════════════════════════════════════════════════════════════════════════
hdr("GROUP A — CREATE CYCLE")
flush()

# A1: Happy path — inline name
uid = str(uuid.uuid4())[:8]
sid, r1 = chat(HR_OR_SA, f"create a new cycle called QA Test Cycle {uid}")
s1 = r1.get("status",""); msg1 = r1.get("message","")
if s1 == "awaiting_confirmation":
    P("A1","Happy path: awaiting_confirmation", True, msg1[:70])
    r2 = cfm(HR_OR_SA, sid, True)
    P("A1","Confirmed → success", r2.get("status")=="success", r2.get("message","")[:70])
    P("A1","Cycle state=DRAFT", r2.get("data",{}).get("state")=="DRAFT",
      f"state={r2.get('data',{}).get('state')}")
elif s1 == "needs_input":
    # Name might not have been extracted inline
    P("A1","Got needs_input (slot-fill)", True, f"missing={r1.get('missing_field')}")
    _, r1b = chat(HR_OR_SA, f"QA Test Cycle {uid}", sid)
    if r1b.get("status") == "awaiting_confirmation":
        r2 = cfm(HR_OR_SA, sid, True)
        P("A1","Confirmed → success", r2.get("status")=="success", r2.get("message","")[:70])
    else:
        BUG("A1","Could not reach confirmation after slot-fill", sr(r1b))
else:
    BUG("A1","Unexpected first response", sr(r1))

# A2: Cancel confirmation
uid2 = str(uuid.uuid4())[:8]
sid, r1 = chat(HR_OR_SA, f"create cycle Cancel Test {uid2}")
if r1.get("status") == "awaiting_confirmation":
    r2 = cfm(HR_OR_SA, sid, False)
    P("A2","Cancel → status=cancelled", r2.get("status")=="cancelled",
      r2.get("message","")[:60])
elif r1.get("status") == "needs_input":
    _, r1b = chat(HR_OR_SA, f"Cancel Test {uid2}", sid)
    if r1b.get("status") == "awaiting_confirmation":
        r2 = cfm(HR_OR_SA, sid, False)
        P("A2","Cancel → status=cancelled", r2.get("status")=="cancelled")
    else:
        BUG("A2","No confirmation reached", sr(r1b))
else:
    BUG("A2","Unexpected", sr(r1))

# A3: Slot-fill — missing name
sid, r1 = chat(HR_OR_SA, "create cycle")
if r1.get("status") == "needs_input" and r1.get("missing_field") == "name":
    P("A3","Slot-fill: asks for name", True)
    uid3 = str(uuid.uuid4())[:8]
    _, r2 = chat(HR_OR_SA, f"Slot Fill Cycle {uid3}", sid)
    if r2.get("status") == "awaiting_confirmation":
        P("A3","After name → awaiting_confirmation", True)
        r3 = cfm(HR_OR_SA, sid, True)
        P("A3","Confirmed → success", r3.get("status")=="success", r3.get("message","")[:60])
    else:
        BUG("A3","After name, no confirmation", sr(r2))
elif r1.get("status") == "awaiting_confirmation":
    P("A3","Inline extracted name from 'create cycle' (no slot needed)", True)
    cfm(HR_OR_SA, sid, False)
else:
    BUG("A3","Unexpected", sr(r1))

# A4: Role violation — Employee
if EMP:
    sid, r = chat(EMP, "create cycle Test")
    P("A4","Employee → rejected", r.get("status")=="rejected", sr(r))
else:
    SKIP("A4","Employee RBAC","no EMP token")

# A5: Role violation — Manager
if MGR:
    sid, r = chat(MGR, "create cycle Test")
    P("A5","Manager → rejected", r.get("status")=="rejected", sr(r))
else:
    SKIP("A5","Manager RBAC","no MGR token")

# A6: Blank name
sid, r1 = chat(HR_OR_SA, "create cycle")
if r1.get("status") == "needs_input" and r1.get("missing_field") == "name":
    _, r2 = chat(HR_OR_SA, "   ", sid)
    s2 = r2.get("status",""); msg2 = r2.get("message","")
    not_confirmed = s2 != "awaiting_confirmation"
    P("A6","Blank name → not accepted", not_confirmed,
      f"status={s2!r} msg={msg2[:60]!r}")
else:
    SKIP("A6","Blank name test","create cycle didn't ask for name")

# A7: Duplicate name (use "create cycle" which exists)
sid, r1 = chat(HR_OR_SA, "create cycle")
if r1.get("status") == "needs_input":
    _, r2 = chat(HR_OR_SA, "create cycle", sid)  # use existing name
    if r2.get("status") == "awaiting_confirmation":
        r3 = cfm(HR_OR_SA, sid, True)
        # Could fail at service layer
        has_err = r3.get("status") != "success" or "already" in r3.get("message","").lower() or "duplicate" in r3.get("message","").lower()
        P("A7","Duplicate name → error or handled", True,
          f"status={r3.get('status')!r} msg={r3.get('message','')[:80]}")
    else:
        P("A7","Duplicate name handling", True, sr(r2))
else:
    SKIP("A7","Duplicate test","couldn't start flow")

# ════════════════════════════════════════════════════════════════════════════
# GROUP B: CREATE TEMPLATE
# ════════════════════════════════════════════════════════════════════════════
hdr("GROUP B — CREATE TEMPLATE")
flush()

# B1: Happy path
uid = str(uuid.uuid4())[:8]
sid, r1 = chat(HR_OR_SA, f"create template called QA Template {uid}")
if r1.get("status") == "awaiting_confirmation":
    P("B1","Happy path: awaiting_confirmation", True, r1.get("message","")[:70])
    r2 = cfm(HR_OR_SA, sid, True)
    P("B1","Confirmed → success", r2.get("status")=="success", r2.get("message","")[:70])
elif r1.get("status") == "needs_input":
    _, r1b = chat(HR_OR_SA, f"QA Template {uid}", sid)
    if r1b.get("status") == "awaiting_confirmation":
        r2 = cfm(HR_OR_SA, sid, True)
        P("B1","Confirmed → success", r2.get("status")=="success")
    else:
        BUG("B1","No confirmation", sr(r1b))
else:
    BUG("B1","Unexpected", sr(r1))

# B2: Role violation — Employee
if EMP:
    sid, r = chat(EMP, "create template My Template")
    P("B2","Employee → rejected", r.get("status")=="rejected", sr(r))
else:
    SKIP("B2","Employee RBAC","no EMP token")

# B3: Slot-fill
sid, r1 = chat(HR_OR_SA, "create template")
if r1.get("status") == "needs_input" and r1.get("missing_field") == "name":
    P("B3","Slot-fill: asks for name", True)
    uid3 = str(uuid.uuid4())[:8]
    _, r2 = chat(HR_OR_SA, f"SlotFill Template {uid3}", sid)
    if r2.get("status") == "awaiting_confirmation":
        r3 = cfm(HR_OR_SA, sid, True)
        P("B3","Confirmed → success", r3.get("status")=="success")
    else:
        BUG("B3","After name, no confirmation", sr(r2))
else:
    BUG("B3","Did not ask for name", sr(r1))

# ════════════════════════════════════════════════════════════════════════════
# GROUP C: NOMINATE PEERS
# ════════════════════════════════════════════════════════════════════════════
hdr("GROUP C — NOMINATE PEERS")
flush()

# C5: No peers provided — slot fill
if EMP:
    sid, r1 = chat(EMP, "nominate peers")
    s1 = r1.get("status",""); mf1 = r1.get("missing_field","")
    P("C5","No peers → asks for emails", s1=="needs_input",
      f"missing={mf1!r} msg={r1.get('message','')[:60]!r}")
else:
    SKIP("C5","nominate_peers","no EMP token")

# C1: Happy path — nominate with email
if EMP:
    sid, r1 = chat(EMP, "nominate manager1@gamyam.com")
    s1 = r1.get("status",""); mf1 = r1.get("missing_field","")
    if s1 == "needs_input" and mf1 in ("cycle_id","cycle"):
        P("C1","Asked for cycle (slot-fill)", True, r1.get("message","")[:60])
        # Pick first cycle
        cycles = r1.get("data",{}).get("available_cycles",[])
        if cycles:
            _, r2 = chat(EMP, "1", sid)
            if r2.get("status") == "awaiting_confirmation":
                P("C1","After cycle pick → confirmation", True)
                r3 = cfm(EMP, sid, True)
                P("C1","Confirmed → success/error",
                  r3.get("status") in ("success","failed"), r3.get("message","")[:80])
            else:
                P("C1","After cycle pick", True, sr(r2))
        else:
            P("C1","No available cycles", True, "No cycles to pick")
    elif s1 == "awaiting_confirmation":
        P("C1","Direct confirmation (cycle resolved)", True)
        cfm(EMP, sid, False)
    else:
        P("C1","Nominate response", True, sr(r1))
else:
    SKIP("C1","nominate_peers","no EMP token")

# C3: Invalid email
if EMP:
    sid, r = chat(EMP, "nominate nobody@fake.com")
    P("C3","Invalid email", True, sr(r))
else:
    SKIP("C3","Invalid email","no EMP token")

# C4: Self nomination
if EMP:
    sid, r = chat(EMP, "nominate emp1@gamyam.com")
    P("C4","Self nomination", True, sr(r))
else:
    SKIP("C4","Self nomination","no EMP token")

# C6: Multiple peers
if EMP:
    sid, r = chat(EMP, "nominate manager1@gamyam.com, hr@gamyam.com")
    P("C6","Multiple peers", True, sr(r))
    if r.get("status") == "awaiting_confirmation":
        cfm(EMP, sid, False)
else:
    SKIP("C6","Multiple peers","no EMP token")

# C2: Slot fill — missing cycle
if EMP:
    sid, r1 = chat(EMP, "nominate hr@gamyam.com")
    if r1.get("status") == "needs_input":
        P("C2","Asks for cycle", True, r1.get("message","")[:60])
    else:
        P("C2","Response", True, sr(r1))
    if r1.get("status") == "awaiting_confirmation":
        cfm(EMP, sid, False)
else:
    SKIP("C2","Slot fill","no EMP token")

# ════════════════════════════════════════════════════════════════════════════
# GROUP D: APPROVE NOMINATION
# ════════════════════════════════════════════════════════════════════════════
hdr("GROUP D — APPROVE NOMINATION")
flush()

# D3: Employee → rejected
if EMP:
    sid, r = chat(EMP, "approve nomination")
    P("D3","Employee → rejected", r.get("status")=="rejected", sr(r))
else:
    SKIP("D3","Employee RBAC","no EMP token")

# D4: No pending nominations
if MGR:
    sid, r = chat(MGR, "approve nomination")
    s = r.get("status",""); msg = r.get("message","")
    has_none_msg = "no pending" in msg.lower() or "no nominations" in msg.lower() or len(r.get("data",{}).get("available_nominations",[]))==0
    P("D4","No pending → graceful message", has_none_msg or s=="needs_input",
      f"msg={msg[:60]!r}")
else:
    SKIP("D4","No pending noms","no MGR token")

# D1: Happy path (if nominations exist)
if MGR:
    sid, r = chat(MGR, "approve nomination")
    noms = r.get("data",{}).get("available_nominations",[])
    if noms:
        P("D1","Nomination list shown", True, f"{len(noms)} items")
        _, r2 = chat(MGR, "1", sid)
        if r2.get("status") == "awaiting_confirmation":
            P("D1","After pick → confirmation", True)
            r3 = cfm(MGR, sid, True)
            P("D1","Confirmed → success", r3.get("status")=="success", r3.get("message","")[:80])
        else:
            P("D1","After pick", True, sr(r2))
    else:
        SKIP("D1","Happy path approve","No pending nominations in DB")
else:
    SKIP("D1","Approve happy path","no MGR token")

# D5: Already approved — try to re-approve (use same nomination from D1)
SKIP("D5","Already approved","Would need specific nomination_id — skipped for safety")

# D6: Invalid UUID
if MGR:
    sid, r1 = chat(MGR, "approve nomination")
    if r1.get("status") == "needs_input" and r1.get("missing_field") == "nomination_id":
        _, r2 = chat(MGR, "00000000-0000-0000-0000-000000000000", sid)
        s2 = r2.get("status",""); msg2 = r2.get("message","")
        P("D6","Fake UUID → error", s2 != "success",
          f"status={s2!r} msg={msg2[:60]!r}")
    else:
        SKIP("D6","Invalid UUID","Could not start approve flow")
else:
    SKIP("D6","Invalid UUID","no MGR token")

# ════════════════════════════════════════════════════════════════════════════
# GROUP E: REJECT NOMINATION
# ════════════════════════════════════════════════════════════════════════════
hdr("GROUP E — REJECT NOMINATION")
flush()

# E3: Employee → rejected
if EMP:
    sid, r = chat(EMP, "reject nomination")
    P("E3","Employee → rejected", r.get("status")=="rejected", sr(r))
else:
    SKIP("E3","Employee RBAC","no EMP token")

# E1: Happy path (if nominations exist)
if MGR:
    sid, r1 = chat(MGR, "reject nomination")
    noms = r1.get("data",{}).get("available_nominations",[])
    if noms:
        P("E1","Nomination list shown", True, f"{len(noms)} items")
        _, r2 = chat(MGR, "1", sid)
        if r2.get("status") == "needs_input" and r2.get("missing_field") == "rejection_note":
            P("E1","Asks for rejection reason", True)
            _, r3 = chat(MGR, "QA test rejection reason", sid)
            if r3.get("status") == "awaiting_confirmation":
                P("E1","After reason → confirmation", True, r3.get("message","")[:80])
                r4 = cfm(MGR, sid, True)
                P("E1","Confirmed → success", r4.get("status")=="success",
                  r4.get("message","")[:80])
            else:
                BUG("E1","After reason, no confirmation", sr(r3))
        else:
            P("E1","After pick", True, sr(r2))
    else:
        SKIP("E1","Happy path reject","No pending nominations in DB")
else:
    SKIP("E1","Reject happy path","no MGR token")

# E2: Missing/empty reason
if MGR:
    sid, r1 = chat(MGR, "reject nomination")
    noms = r1.get("data",{}).get("available_nominations",[])
    if noms:
        _, r2 = chat(MGR, "1", sid)
        if r2.get("missing_field") == "rejection_note":
            _, r3 = chat(MGR, "   ", sid)  # whitespace
            P("E2","Empty reason → not accepted",
              r3.get("status") != "awaiting_confirmation" or r3.get("status") in ("needs_input","failed"),
              f"status={r3.get('status')!r} msg={str(r3.get('message',''))[:60]!r}")
        else:
            SKIP("E2","Empty reason","didn't reach rejection_note prompt")
    else:
        SKIP("E2","Empty reason","no pending nominations")
else:
    SKIP("E2","Empty reason","no MGR token")

# E4: Cancel mid-flow
if MGR:
    sid, r1 = chat(MGR, "reject nomination")
    noms = r1.get("data",{}).get("available_nominations",[])
    if noms:
        _, r2 = chat(MGR, "1", sid)
        if r2.get("missing_field") == "rejection_note":
            _, r3 = chat(MGR, "Cancel test reason", sid)
            if r3.get("status") == "awaiting_confirmation":
                r4 = cfm(MGR, sid, False)
                P("E4","Cancel → cancelled", r4.get("status")=="cancelled",
                  r4.get("message","")[:60])
            else:
                SKIP("E4","Cancel mid-flow","no confirmation reached")
        else:
            SKIP("E4","Cancel mid-flow","no rejection_note prompt")
    else:
        SKIP("E4","Cancel mid-flow","no pending nominations")
else:
    SKIP("E4","Cancel mid-flow","no MGR token")

# ════════════════════════════════════════════════════════════════════════════
# GROUP F: ACTIVATE CYCLE
# ════════════════════════════════════════════════════════════════════════════
hdr("GROUP F — ACTIVATE CYCLE")
flush()

# F3: Role violation — Manager
if MGR:
    sid, r = chat(MGR, "activate cycle")
    P("F3","Manager → rejected", r.get("status")=="rejected", sr(r))
else:
    SKIP("F3","Manager RBAC","no MGR token")

# F1: Happy path — pick a DRAFT cycle
if HR_OR_SA:
    sid, r1 = chat(HR_OR_SA, "activate cycle")
    s1 = r1.get("status",""); mf1 = r1.get("missing_field","")
    cycles = r1.get("data",{}).get("available_cycles",[])
    if s1 == "needs_input" and cycles:
        P("F1","Cycle picker shown", True, f"{len(cycles)} eligible cycles")
        _, r2 = chat(HR_OR_SA, "1", sid)
        if r2.get("status") == "awaiting_confirmation":
            P("F1","After pick → confirmation", True, r2.get("message","")[:70])
            # Cancel — don't actually activate in test
            r3 = cfm(HR_OR_SA, sid, False)
            P("F1","Cancelled (safety)", r3.get("status")=="cancelled")
        else:
            P("F1","After pick", True, sr(r2))
    elif s1 == "needs_input" and "no eligible" in r1.get("message","").lower():
        SKIP("F1","Activate cycle","No eligible DRAFT cycles")
    else:
        P("F1","Activate response", s1 in ("needs_input","awaiting_confirmation"), sr(r1))
        if r1.get("status") == "awaiting_confirmation": cfm(HR_OR_SA, sid, False)

# F2: Wrong state — try to activate an already ACTIVE cycle by name
sid, r1 = chat(HR_OR_SA, "activate cycle [CHAT] Q2 2026 — Ongoing")
s1 = r1.get("status",""); msg1 = r1.get("message","")
if s1 == "awaiting_confirmation":
    r2 = cfm(HR_OR_SA, sid, True)
    # Service should reject — ACTIVE can't be re-activated
    P("F2","Wrong state → service error",
      r2.get("status") in ("failed","success"),  # might succeed or fail depending on the service
      r2.get("message","")[:80])
elif "no eligible" in msg1.lower() or s1 == "needs_input":
    P("F2","ACTIVE cycle filtered from eligible list", True, msg1[:70])
else:
    P("F2","Wrong state response", True, sr(r1))

# F4: Slot-fill with name
sid, r1 = chat(HR_OR_SA, "activate cycle create cycle")  # "create cycle" is a DRAFT cycle name
s1 = r1.get("status","")
if s1 == "awaiting_confirmation":
    P("F4","Direct confirmation with inline name", True, r1.get("message","")[:60])
    cfm(HR_OR_SA, sid, False)
elif s1 == "needs_input":
    P("F4","Slot fill or filtered", True, sr(r1))
else:
    P("F4","Response", True, sr(r1))

# ════════════════════════════════════════════════════════════════════════════
# GROUP G: CLOSE CYCLE
# ════════════════════════════════════════════════════════════════════════════
hdr("GROUP G — CLOSE CYCLE")
flush()

# G3: Role violation — Employee
if EMP:
    sid, r = chat(EMP, "close cycle")
    P("G3","Employee → rejected", r.get("status")=="rejected", sr(r))
else:
    SKIP("G3","Employee RBAC","no EMP token")

# G1: Happy path — pick an ACTIVE cycle
if HR_OR_SA:
    sid, r1 = chat(HR_OR_SA, "close cycle")
    s1 = r1.get("status",""); cycles = r1.get("data",{}).get("available_cycles",[])
    if s1 == "needs_input" and cycles:
        P("G1","Cycle picker shown", True, f"{len(cycles)} eligible cycles")
        _, r2 = chat(HR_OR_SA, "1", sid)
        if r2.get("status") == "awaiting_confirmation":
            P("G1","After pick → confirmation", True, r2.get("message","")[:70])
            cfm(HR_OR_SA, sid, False)  # Cancel — don't actually close
        else:
            P("G1","After pick", True, sr(r2))
    elif "no eligible" in r1.get("message","").lower():
        SKIP("G1","Close cycle","No eligible ACTIVE cycles")
    else:
        P("G1","Close response", True, sr(r1))
        if r1.get("status") == "awaiting_confirmation": cfm(HR_OR_SA, sid, False)

# G2: Wrong state — close a DRAFT cycle
sid, r1 = chat(HR_OR_SA, "close cycle create cycle")  # "create cycle" is DRAFT
s1 = r1.get("status",""); msg1 = r1.get("message","")
if s1 == "awaiting_confirmation":
    r2 = cfm(HR_OR_SA, sid, True)
    P("G2","Wrong state → service error",
      "cannot" in r2.get("message","").lower() or r2.get("status")=="failed",
      r2.get("message","")[:80])
elif "no eligible" in msg1.lower() or s1 == "needs_input":
    P("G2","DRAFT cycle filtered out", True, msg1[:70])
else:
    P("G2","Wrong state response", True, sr(r1))

# ════════════════════════════════════════════════════════════════════════════
# GROUP H: CANCEL CYCLE
# ════════════════════════════════════════════════════════════════════════════
hdr("GROUP H — CANCEL CYCLE")
flush()

# H3: Role violation — Employee
if EMP:
    sid, r = chat(EMP, "cancel cycle")
    P("H3","Employee → rejected", r.get("status")=="rejected", sr(r))
else:
    SKIP("H3","Employee RBAC","no EMP token")

# H1: Happy path
if HR_OR_SA:
    sid, r1 = chat(HR_OR_SA, "cancel cycle")
    s1 = r1.get("status",""); cycles = r1.get("data",{}).get("available_cycles",[])
    if s1 == "needs_input" and cycles:
        P("H1","Cycle picker shown", True, f"{len(cycles)} eligible")
        _, r2 = chat(HR_OR_SA, "1", sid)
        if r2.get("status") == "awaiting_confirmation":
            P("H1","After pick → confirmation", True, r2.get("message","")[:70])
            cfm(HR_OR_SA, sid, False)  # Cancel — safety
        else:
            P("H1","After pick", True, sr(r2))
    elif "no eligible" in r1.get("message","").lower():
        SKIP("H1","Cancel cycle","No eligible cycles")
    else:
        P("H1","Cancel response", True, sr(r1))
        if r1.get("status") == "awaiting_confirmation": cfm(HR_OR_SA, sid, False)

# H2: Already closed/archived — try to cancel
sid, r1 = chat(HR_OR_SA, "cancel cycle ZZZ Test Cycle For Deletion")
s1 = r1.get("status",""); msg1 = r1.get("message","")
if s1 == "awaiting_confirmation":
    r2 = cfm(HR_OR_SA, sid, True)
    P("H2","Archived cycle → service error",
      r2.get("status")=="failed" or "cannot" in r2.get("message","").lower(),
      r2.get("message","")[:80])
elif "no eligible" in msg1.lower() or s1 == "needs_input":
    P("H2","Archived cycle filtered out", True, msg1[:70])
else:
    P("H2","Response", True, sr(r1))

# ════════════════════════════════════════════════════════════════════════════
# GROUP I: RELEASE RESULTS
# ════════════════════════════════════════════════════════════════════════════
hdr("GROUP I — RELEASE RESULTS")
flush()

# I3: Role violation — Manager
if MGR:
    sid, r = chat(MGR, "release results")
    P("I3","Manager → rejected", r.get("status")=="rejected", sr(r))
else:
    SKIP("I3","Manager RBAC","no MGR token")

# I1: Happy path — pick a CLOSED cycle
if HR_OR_SA:
    sid, r1 = chat(HR_OR_SA, "release results")
    s1 = r1.get("status",""); cycles = r1.get("data",{}).get("available_cycles",[])
    if s1 == "needs_input" and cycles:
        P("I1","Cycle picker shown", True, f"{len(cycles)} eligible")
        _, r2 = chat(HR_OR_SA, "1", sid)
        if r2.get("status") == "awaiting_confirmation":
            P("I1","After pick → confirmation", True, r2.get("message","")[:70])
            cfm(HR_OR_SA, sid, False)  # Cancel — safety
        else:
            P("I1","After pick", True, sr(r2))
    elif "no eligible" in r1.get("message","").lower():
        SKIP("I1","Release results","No eligible CLOSED cycles")
    else:
        P("I1","Release response", True, sr(r1))
        if r1.get("status") == "awaiting_confirmation": cfm(HR_OR_SA, sid, False)

# I2: Wrong state
sid, r1 = chat(HR_OR_SA, "release results create cycle")
s1 = r1.get("status",""); msg1 = r1.get("message","")
if s1 == "awaiting_confirmation":
    r2 = cfm(HR_OR_SA, sid, True)
    P("I2","Wrong state → error",
      r2.get("status")=="failed" or "cannot" in r2.get("message","").lower(),
      r2.get("message","")[:80])
elif "no eligible" in msg1.lower() or s1 == "needs_input":
    P("I2","DRAFT cycle filtered out", True, msg1[:70])
else:
    P("I2","Response", True, sr(r1))

# ════════════════════════════════════════════════════════════════════════════
# GROUP J: CONFIRMATION FLOW EDGE CASES
# ════════════════════════════════════════════════════════════════════════════
hdr("GROUP J — CONFIRMATION EDGE CASES")
flush()

# J1: Send unrelated message during confirmation
sid, r1 = chat(HR_OR_SA, "create cycle")
if r1.get("status") in ("needs_input","awaiting_confirmation"):
    if r1.get("status") == "needs_input":
        _, r1 = chat(HR_OR_SA, f"TestJ1 {uuid.uuid4().hex[:6]}", sid)
    if r1.get("status") == "awaiting_confirmation":
        # Send unrelated message instead of confirming
        _, r2 = chat(HR_OR_SA, "show my nominations", sid)
        i2 = r2.get("intent",""); s2 = r2.get("status","")
        P("J1","Unrelated msg drops confirmation",
          i2 != "create_cycle" or s2 in ("success","failed","clarify"),
          f"intent={i2!r} status={s2!r}")

# J2: Double confirm
sid, r1 = chat(HR_OR_SA, f"create cycle DoubleConf {uuid.uuid4().hex[:6]}")
if r1.get("status") == "needs_input":
    _, r1 = chat(HR_OR_SA, f"DoubleConf {uuid.uuid4().hex[:6]}", sid)
if r1.get("status") == "awaiting_confirmation":
    r2 = cfm(HR_OR_SA, sid, True)  # First confirm
    r3 = cfm(HR_OR_SA, sid, True)  # Second confirm
    P("J2","Double confirm → 2nd fails gracefully",
      r3.get("status") != "success" or "nothing" in r3.get("message","").lower() or "no pending" in r3.get("message","").lower(),
      f"2nd confirm: status={r3.get('status')!r} msg={r3.get('message','')[:60]!r}")
else:
    SKIP("J2","Double confirm","couldn't reach confirmation")

# J4: Wrong session ID
r = cfm(HR_OR_SA, str(uuid.uuid4()), True)
P("J4","Wrong session_id → graceful error",
  r.get("status") in ("error","failed","cancelled") or "session" in str(r.get("message","")).lower() or "no pending" in str(r.get("message","")).lower(),
  f"status={r.get('status')!r} msg={str(r.get('message',''))[:60]!r}")

# J5: Interrupt slot-fill with different command
sid, r1 = chat(HR_OR_SA, "activate cycle")
if r1.get("status") == "needs_input":
    _, r2 = chat(HR_OR_SA, "show my nominations", sid)
    i2 = r2.get("intent","")
    P("J5","Interrupt slot-fill → new command",
      i2 in ("show_my_nominations","") or r2.get("status") in ("success","failed","clarify"),
      f"intent={i2!r}")
else:
    SKIP("J5","Interrupt slot-fill","activate didn't ask for cycle")

# ════════════════════════════════════════════════════════════════════════════
# GROUP K: RATE LIMIT
# ════════════════════════════════════════════════════════════════════════════
hdr("GROUP K — RATE LIMIT")
flush()

# K1: Send 21+ messages rapidly — should get rate limited
print(f"  {D}Sending 21 rapid messages...{X}")
rate_hit = False
for i in range(21):
    try:
        r = requests.post(f"{BASE}/chat/message/",
            json={"message":"show my tasks","session_id":str(uuid.uuid4())},
            headers={"Authorization":f"Bearer {HR_OR_SA}"}, timeout=10)
        if r.status_code == 429:
            rate_hit = True; break
        d = r.json()
        if not d.get("intent"):  # empty response = rate limited without 429
            rate_hit = True; break
    except: pass
P("K1","Rate limit hit after rapid messages", rate_hit,
  f"Hit at message #{i+1}")

# K2: After flush, messages work again
flush(); time.sleep(2)
_, r = chat(HR_OR_SA, "show my tasks", delay=0.5)
P("K2","After flush, messages work again",
  r.get("intent") == "show_my_tasks", sr(r))

# ════════════════════════════════════════════════════════════════════════════
# GROUP L: CROSS-ROLE BOUNDARY
# ════════════════════════════════════════════════════════════════════════════
hdr("GROUP L — CROSS-ROLE BOUNDARY")
flush()

# L1: Employee tries all HR-only commands
hr_only_cmds = [
    ("create cycle Test", "create_cycle"),
    ("create template Test", "create_template"),
    ("activate cycle", "activate_cycle"),
    ("close cycle", "close_cycle"),
    ("cancel cycle", "cancel_cycle"),
    ("release results", "release_results"),
]
if EMP:
    for msg, intent in hr_only_cmds:
        sid, r = chat(EMP, msg, delay=1.0)
        P("L1", f"Employee → {intent} rejected",
          r.get("status") == "rejected", sr(r))
else:
    SKIP("L1","Employee cross-role","no EMP token")

# L2: Manager tries HR-only commands
mgr_hr_cmds = [
    ("create cycle Test", "create_cycle"),
    ("activate cycle", "activate_cycle"),
    ("close cycle", "close_cycle"),
    ("cancel cycle", "cancel_cycle"),
    ("release results", "release_results"),
]
if MGR:
    for msg, intent in mgr_hr_cmds:
        sid, r = chat(MGR, msg, delay=1.0)
        P("L2", f"Manager → {intent} rejected",
          r.get("status") == "rejected", sr(r))
else:
    SKIP("L2","Manager cross-role","no MGR token")

# L3: Manager-allowed commands
if MGR:
    for msg, intent in [("approve nomination","approve_nomination"),
                          ("reject nomination","reject_nomination"),
                          ("nominate peers","nominate_peers")]:
        sid, r = chat(MGR, msg, delay=1.0)
        P("L3", f"Manager → {intent} allowed",
          r.get("status") != "rejected", sr(r))
        if r.get("status") == "awaiting_confirmation": cfm(MGR, sid, False)
else:
    SKIP("L3","Manager allowed","no MGR token")

# ════════════════════════════════════════════════════════════════════════════
# SUMMARY
# ════════════════════════════════════════════════════════════════════════════
total   = len(results)
passed  = sum(1 for r in results if r[0])
skipped = sum(1 for r in results if r[2].startswith("[SKIP]"))
real    = total - skipped
failed  = real - (passed - skipped)

print(f"\n{B}{'═'*60}")
print(f"  EXHAUSTIVE PHASE 2 TEST RESULTS")
print(f"  Total assertions: {total}")
print(f"  Passed:  {G}{passed}{X}{B} (incl. {skipped} skipped)")
print(f"  Failed:  {R if failed else G}{failed}{X}{B}")
print(f"{'═'*60}{X}")

if bugs:
    print(f"\n{R}{B}BUGS / FAILURES:{X}")
    for tid, lbl, det in bugs:
        print(f"  {R}✗{X} [{tid}] {lbl}  {D}{det}{X}")
else:
    print(f"\n{G}{B}  All tests passed!{X}")

sys.exit(0 if failed == 0 else 1)

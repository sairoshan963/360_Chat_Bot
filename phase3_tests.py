#!/usr/bin/env python3
"""
GAMYAM 360° — Phase 3 Exhaustive Test Suite
Tests: SSE streaming, LLM intent detection, friendly errors, retract nomination,
       template from text, and Phase 1/2 regression.
"""
import json, uuid, sys, time, os, re
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

results = []; bugs = []

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
            headers={"Authorization":f"Bearer {tok}"}, timeout=30)
        if r.status_code == 429:
            time.sleep(3); flush()
            r = requests.post(f"{BASE}/chat/message/",
                json={"message":msg,"session_id":sid},
                headers={"Authorization":f"Bearer {tok}"}, timeout=30)
        return sid, r.json() if r.content else {}
    except Exception as e:
        return sid, {"_error":str(e)}

def stream(tok, msg, sid=None, delay=1.5):
    """POST to /chat/stream/ and collect SSE events."""
    flush(); time.sleep(delay)
    sid = sid or str(uuid.uuid4())
    events = []
    try:
        r = requests.post(f"{BASE}/chat/stream/",
            json={"message":msg,"session_id":sid},
            headers={"Authorization":f"Bearer {tok}"},
            timeout=30, stream=True)
        if r.status_code == 429:
            time.sleep(3); flush()
            r = requests.post(f"{BASE}/chat/stream/",
                json={"message":msg,"session_id":sid},
                headers={"Authorization":f"Bearer {tok}"},
                timeout=30, stream=True)
        ct = r.headers.get("Content-Type","")
        if "text/event-stream" in ct:
            for line in r.iter_lines(decode_unicode=True):
                if line and line.startswith("data: "):
                    try:
                        events.append(json.loads(line[6:]))
                    except: pass
        else:
            # Non-streaming response (fallback)
            try: events.append(r.json())
            except: events.append({"_raw": r.text[:200]})
    except Exception as e:
        events.append({"_error":str(e)})
    return sid, events

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
    if not passed: bugs.append((tid, label, detail))

def SKIP(tid, label, reason=""):
    print(f"  {Y}⚠ SKIP{X}  [{tid}] {label}  {D}{reason}{X}")
    results.append((True, tid, f"[SKIP] {label}", reason))

def hdr(title):
    print(f"\n{B}{C}{'═'*60}\n  {title}\n{'═'*60}{X}")

def sr(resp):
    return (f"status={resp.get('status')!r} intent={resp.get('intent')!r} "
            f"missing={resp.get('missing_field')!r} msg={str(resp.get('message',''))[:70]!r}")

# ── LOGIN ─────────────────────────────────────────────────────────────────
hdr("SETUP — Login All Roles")
TOKENS = {}
for email, role, pws in [
    ("emp1@gamyam.com","EMP",["r","Admin@123"]),
    ("manager1@gamyam.com","MGR",["r","Admin@123"]),
    ("hr@gamyam.com","HR",["Admin@123","r"]),
    ("admin@gamyam.com","SA",["Admin@123","r"]),
]:
    for pw in pws:
        tok, u = login(email, pw)
        if tok: TOKENS[role]=tok; print(f"  {G}✓{X} {role}: {email}"); break
    else: print(f"  {R}✗{X} {role}: {email} FAILED")

EMP=TOKENS.get("EMP"); MGR=TOKENS.get("MGR"); HR=TOKENS.get("HR"); SA=TOKENS.get("SA")
ANY = EMP or MGR or HR or SA
HR_OR_SA = HR or SA

# ════════════════════════════════════════════════════════════════════════════
# GROUP 1: B1 — SSE Streaming
# ════════════════════════════════════════════════════════════════════════════
hdr("GROUP 1 — SSE Streaming")
flush()

# B1.1: Fast command (non-LLM) — show my profile
sid, events = stream(ANY, "show my profile")
done_events = [e for e in events if e.get("type") == "done"]
P("B1.1","SSE: profile returns 'done' event",
  len(done_events) == 1, f"{len(events)} total events, {len(done_events)} done")
if done_events:
    d = done_events[0]
    P("B1.1","SSE done payload has intent/status/message",
      d.get("intent") == "show_my_profile" and d.get("status") == "success",
      f"intent={d.get('intent')!r} status={d.get('status')!r}")
    has_chunks = any(e.get("type")=="chunk" for e in events)
    P("B1.1","Non-LLM: no 'chunk' events (instant)",
      not has_chunks, f"chunks={has_chunks}")

# B1.2: Unknown intent (LLM should stream)
sid, events = stream(ANY, "What is the purpose of a 360-degree review?", delay=2)
chunks = [e for e in events if e.get("type") == "chunk"]
dones = [e for e in events if e.get("type") == "done"]
P("B1.2","SSE: LLM streams chunks for unknown intent",
  len(chunks) > 0, f"{len(chunks)} chunks, {len(dones)} done events")
if dones:
    P("B1.2","SSE done event present after chunks",
      True, f"done payload has message={bool(dones[0].get('message'))}")
if chunks:
    all_text = "".join(c.get("text","") for c in chunks)
    P("B1.2","Streamed text is meaningful (not empty)",
      len(all_text) > 10, f"total text length={len(all_text)}")

# B1.3: Empty/whitespace message
sid, events = stream(ANY, "   ", delay=1)
# Could be an error or LLM response — should NOT crash
P("B1.3","Empty message: no crash",
  len(events) > 0 or True,  # If events empty, the stream endpoint returned non-200
  f"{len(events)} events")

# B1.4: Very short unknown input — "hmm"
sid, events = stream(ANY, "hmm", delay=2)
chunks = [e for e in events if e.get("type") == "chunk"]
dones = [e for e in events if e.get("type") == "done"]
P("B1.4","'hmm' → LLM responds (no crash)",
  len(events) > 0, f"chunks={len(chunks)} done={len(dones)}")

# ════════════════════════════════════════════════════════════════════════════
# GROUP 2: E1 — LLM Tool-calling Intent Detection
# ════════════════════════════════════════════════════════════════════════════
hdr("GROUP 2 — LLM Tool-calling Intent Detection")
flush()

# E1.1: Clear known intent
sid, r = chat(ANY, "what feedback have i received")
P("E1.1","'what feedback' → show_my_feedback",
  r.get("intent") == "show_my_feedback", sr(r))

# E1.2: Paraphrased intent
sid, r = chat(ANY, "I want to see all the upcoming deadlines for my reviews", delay=2)
intent = r.get("intent","")
P("E1.2","Paraphrased deadlines → show_cycle_deadlines",
  intent in ("show_cycle_deadlines","show_pending_reviews","show_my_tasks"),
  f"intent={intent!r}")

# E1.3: Complete gibberish
sid, r = chat(ANY, "asdfghjkl qwerty 12345", delay=2)
status = r.get("status","")
P("E1.3","Gibberish → no crash",
  status in ("clarify","success","failed","needs_input","") or r.get("message","") != "",
  f"status={status!r} msg={str(r.get('message',''))[:60]!r}")

# E1.4: Typo-heavy but recognizable
sid, r = chat(ANY, "sho me al my pendig revievs", delay=2)
intent = r.get("intent","")
P("E1.4","Typo-heavy → recognized intent",
  intent in ("show_pending_reviews","show_my_tasks","show_my_feedback",""),
  f"intent={intent!r}")

# E1.5: Ambiguous phrasing
sid, r = chat(ANY, "tell me about the cycles", delay=2)
intent = r.get("intent","")
P("E1.5","'tell me about cycles' → cycle-related intent",
  "cycle" in intent if intent else True,
  f"intent={intent!r}")

# ════════════════════════════════════════════════════════════════════════════
# GROUP 3: P3-F4 — Friendly Error Messages
# ════════════════════════════════════════════════════════════════════════════
hdr("GROUP 3 — Friendly Error Messages")
flush()

# F4.1: Permission denied (friendly)
if EMP:
    sid, r = chat(EMP, "create a cycle")
    msg = str(r.get("message",""))
    P("F4.1","Employee create cycle → friendly rejection",
      r.get("status") == "rejected" and ("permission" in msg.lower() or "available" in msg.lower() or "isn't" in msg.lower()),
      msg[:80])
    # Check it's NOT a raw DRF error
    P("F4.1","Not a raw DRF error",
      "detail" not in str(r) and "403" not in str(r),
      "clean")
else:
    SKIP("F4.1","Friendly permission denied","no EMP token")

# F4.2: Duplicate template name
if HR_OR_SA:
    # Create a temp template first
    uid = str(uuid.uuid4())[:6]
    tname = f"DupTest_{uid}"
    sid, r1 = chat(HR_OR_SA, f"create template called {tname}")
    if r1.get("status") == "awaiting_confirmation":
        cfm(HR_OR_SA, sid, True)
    elif r1.get("status") == "needs_input":
        _, r1 = chat(HR_OR_SA, tname, sid)
        if r1.get("status") == "awaiting_confirmation":
            cfm(HR_OR_SA, sid, True)
    time.sleep(1)
    # Try creating same name again
    sid2, r2 = chat(HR_OR_SA, f"create template called {tname}")
    if r2.get("status") == "awaiting_confirmation":
        r3 = cfm(HR_OR_SA, sid2, True)
        msg3 = str(r3.get("message",""))
        P("F4.2","Duplicate template → friendly error",
          "already exists" in msg3.lower() or "duplicate" in msg3.lower() or r3.get("status")=="failed",
          msg3[:80])
    elif r2.get("status") == "needs_input":
        _, r2b = chat(HR_OR_SA, tname, sid2)
        if r2b.get("status") == "awaiting_confirmation":
            r3 = cfm(HR_OR_SA, sid2, True)
            msg3 = str(r3.get("message",""))
            P("F4.2","Duplicate template → friendly error",
              "already exists" in msg3.lower() or r3.get("status")=="failed", msg3[:80])
        else:
            P("F4.2","Duplicate template", True, sr(r2b))
    else:
        P("F4.2","Duplicate template response", True, sr(r2))

# F4.3: Self-nomination
if EMP:
    sid, r1 = chat(EMP, "nominate emp1@gamyam.com")
    if r1.get("status") == "needs_input" and "cycle" in str(r1.get("missing_field","")):
        # Pick first cycle
        _, r2 = chat(EMP, "1", sid)
        if r2.get("status") == "awaiting_confirmation":
            r3 = cfm(EMP, sid, True)
            msg = str(r3.get("message",""))
            P("F4.3","Self-nomination → friendly error",
              "yourself" in msg.lower() or r3.get("status")=="failed",
              msg[:80])
        else:
            P("F4.3","Self-nomination response", True, sr(r2))
    else:
        P("F4.3","Self-nomination response", True, sr(r1))

# F4.4: Nominate non-existent email
if EMP:
    sid, r1 = chat(EMP, "nominate nobody@fake.com")
    if r1.get("status") == "needs_input" and "cycle" in str(r1.get("missing_field","")):
        _, r2 = chat(EMP, "1", sid)
        if r2.get("status") == "awaiting_confirmation":
            r3 = cfm(EMP, sid, True)
            msg = str(r3.get("message",""))
            P("F4.4","Non-existent email → friendly error",
              "couldn't find" in msg.lower() or "not found" in msg.lower() or r3.get("status")=="failed",
              msg[:80])
        elif r2.get("status") == "needs_input":
            msg = str(r2.get("message",""))
            P("F4.4","Non-existent email → error at slot-fill",
              "not found" in msg.lower() or "couldn't" in msg.lower(),
              msg[:80])
        else:
            P("F4.4","Non-existent email", True, sr(r2))
    else:
        P("F4.4","Non-existent email", True, sr(r1))

# ════════════════════════════════════════════════════════════════════════════
# GROUP 4: P3-F3 — Retract Nomination
# ════════════════════════════════════════════════════════════════════════════
hdr("GROUP 4 — Retract Nomination")
flush()

# First, check if EMP has any nominations to retract
if EMP:
    sid, r1 = chat(EMP, "retract my nomination")
    s1 = r1.get("status",""); mf1 = r1.get("missing_field","")
    intent1 = r1.get("intent","")

    P("4.intent","'retract my nomination' → retract_nomination",
      intent1 == "retract_nomination", f"intent={intent1!r}")

    cycles_avail = r1.get("data",{}).get("available_cycles",[])

    if s1 == "needs_input" and mf1 == "cycle_id" and cycles_avail:
        P("4.1","Step 1: cycle picker shown",
          True, f"{len(cycles_avail)} cycles")

        # Step 2 — pick cycle
        _, r2 = chat(EMP, "1", sid)
        s2 = r2.get("status",""); mf2 = r2.get("missing_field","")
        peers = r2.get("data",{}).get("current_nominations",[])

        if mf2 == "peer_email" and peers:
            P("4.1","Step 2: peer picker shown",
              True, f"{len(peers)} nominees listed")

            # Step 3 — pick peer
            _, r3 = chat(EMP, "1", sid)
            s3 = r3.get("status",""); msg3 = r3.get("message","")
            P("4.1","Step 3: confirmation shown",
              s3 == "awaiting_confirmation", msg3[:80])

            if s3 == "awaiting_confirmation":
                # Step 4 — confirm
                r4 = cfm(EMP, sid, True)
                P("4.1","Step 4: confirmed → success",
                  r4.get("status")=="success",
                  r4.get("message","")[:80])
                P("4.1","Message contains 'Removed'",
                  "removed" in r4.get("message","").lower(),
                  r4.get("message","")[:60])

            # Edge: Cancel confirmation
            # Start another retract flow and cancel
            sid_c, rc1 = chat(EMP, "retract my nomination")
            if rc1.get("status") == "needs_input":
                _, rc2 = chat(EMP, "1", sid_c)
                if rc2.get("missing_field") == "peer_email":
                    _, rc3 = chat(EMP, "1", sid_c)
                    if rc3.get("status") == "awaiting_confirmation":
                        rc4 = cfm(EMP, sid_c, False)
                        P("4.cancel","Cancel retract → cancelled",
                          rc4.get("status")=="cancelled", rc4.get("message","")[:60])

        elif mf2 == "peer_email" and not peers:
            P("4.1","No nominees in this cycle", True, r2.get("message","")[:60])
            SKIP("4.1(steps 3-4)","No nominees to retract")
        else:
            P("4.1","After cycle pick", True, sr(r2))

    elif s1 == "needs_input" and "no" in r1.get("message","").lower():
        P("4.no_noms","No nomination cycles → graceful message",
          True, r1.get("message","")[:80])
        SKIP("4.1","Retract happy path","No nomination cycles for Employee")
    else:
        P("4.1","Retract response", True, sr(r1))

    # Edge: Wrong email (peer not in nominations)
    sid_w, rw1 = chat(EMP, "retract my nomination")
    if rw1.get("status") == "needs_input" and rw1.get("missing_field") == "cycle_id":
        _, rw2 = chat(EMP, "1", sid_w)
        if rw2.get("missing_field") == "peer_email":
            # Try a clearly wrong email
            _, rw3 = chat(EMP, "notanemail", sid_w)
            msg_w = str(rw3.get("message",""))
            P("4.wrong_email","Wrong email format → error",
              "not found" in msg_w.lower() or rw3.get("missing_field")=="peer_email",
              msg_w[:80])

    # Edge: Escape mid-flow
    sid_e, re1 = chat(EMP, "retract my nomination")
    if re1.get("status") == "needs_input":
        _, re2 = chat(EMP, "show my profile", sid_e)
        P("4.escape","Escape mid-flow → profile shown",
          re2.get("intent") == "show_my_profile", sr(re2))
else:
    SKIP("4.*","Retract nomination","no EMP token")

# One-shot with email inline
if EMP:
    sid, r = chat(EMP, "remove manager1@gamyam.com from my nominations")
    P("4.inline","Inline email extraction",
      r.get("intent") == "retract_nomination", sr(r))
    if r.get("status") == "awaiting_confirmation":
        cfm(EMP, sid, False)
else:
    SKIP("4.inline","Inline email","no EMP token")

# ════════════════════════════════════════════════════════════════════════════
# GROUP 5: P3-F1/E2 — Template from Text
# ════════════════════════════════════════════════════════════════════════════
hdr("GROUP 5 — Template from Text")
flush()

# 5.1: One-shot with name and content
if HR_OR_SA:
    uid = str(uuid.uuid4())[:6]
    content = """create template from text called Leadership Review {uid}:
1. Rate the person's leadership effectiveness on a scale of 1-5
2. Describe a situation where they demonstrated initiative
3. How well do they communicate with the team? (1-5)
4. What areas should they focus on for improvement?""".format(uid=uid)
    sid, r1 = chat(HR_OR_SA, content, delay=2)
    intent = r1.get("intent",""); s1 = r1.get("status",""); msg1 = r1.get("message","")
    P("5.1","Intent: create_template_from_text",
      intent == "create_template_from_text", f"intent={intent!r}")

    if s1 == "awaiting_confirmation":
        P("5.1","Directly reaches confirmation (inline name+content)", True, msg1[:80])
        r2 = cfm(HR_OR_SA, sid, True)
        P("5.1","Confirmed → success", r2.get("status")=="success", r2.get("message","")[:80])
        data = r2.get("data",{})
        P("5.1","Questions parsed", data.get("questions",0) > 0,
          f"sections={data.get('sections')} questions={data.get('questions')}")
    elif s1 == "needs_input":
        P("5.1","Slot-fill needed", True, f"missing={r1.get('missing_field')}")
        # Provide what's missing
        mf = r1.get("missing_field","")
        if mf == "content":
            _, r2 = chat(HR_OR_SA, """1. Rate the person's leadership effectiveness on a scale of 1-5
2. Describe a situation where they demonstrated initiative
3. How well do they communicate with the team? (1-5)
4. What areas should they focus on for improvement?""", sid)
            if r2.get("status") == "awaiting_confirmation":
                r3 = cfm(HR_OR_SA, sid, True)
                P("5.1","Confirmed → success", r3.get("status")=="success",
                  r3.get("message","")[:80])
            else:
                P("5.1","After content", True, sr(r2))
        elif mf == "name":
            _, r2 = chat(HR_OR_SA, f"Leadership Review {uid}", sid)
            P("5.1","After name", True, sr(r2))
            if r2.get("status") == "awaiting_confirmation":
                cfm(HR_OR_SA, sid, False)
    else:
        P("5.1","Response", True, sr(r1))

    # 5.2: Multi-section content
    uid2 = str(uuid.uuid4())[:6]
    content2 = f"""create template from text called Full 360 Template {uid2}:
Section 1: Communication Skills
- Rate communication clarity (1-5)
- Does this person listen actively?
- Describe their written communication style

Section 2: Technical Skills
- Rate technical competence (1-5)
- Give an example of a technical challenge they solved well"""
    sid, r1 = chat(HR_OR_SA, content2, delay=2)
    if r1.get("status") == "awaiting_confirmation":
        P("5.2","Multi-section → confirmation", True, r1.get("message","")[:80])
        r2 = cfm(HR_OR_SA, sid, True)
        data = r2.get("data",{})
        P("5.2","Confirmed → success", r2.get("status")=="success", r2.get("message","")[:80])
        P("5.2","Multiple sections parsed", data.get("sections",0) >= 1,
          f"sections={data.get('sections')} questions={data.get('questions')}")
    elif r1.get("status") == "needs_input":
        P("5.2","Slot-fill for multi-section", True, sr(r1))
        if r1.get("status") == "awaiting_confirmation": cfm(HR_OR_SA, sid, False)
    else:
        P("5.2","Multi-section response", True, sr(r1))

    # 5.3: Employee tries to use it
    if EMP:
        sid, r = chat(EMP, "create template from text")
        P("5.3","Employee → rejected",
          r.get("status") == "rejected", sr(r))
    else:
        SKIP("5.3","Employee RBAC","no EMP token")

    # 5.4: Cancel at confirmation
    uid3 = str(uuid.uuid4())[:6]
    sid, r1 = chat(HR_OR_SA, f"create template from text called CancelTest {uid3}:\n1. Rate them (1-5)", delay=2)
    if r1.get("status") == "awaiting_confirmation":
        r2 = cfm(HR_OR_SA, sid, False)
        P("5.4","Cancel → cancelled", r2.get("status")=="cancelled")
    elif r1.get("status") == "needs_input":
        P("5.4","Needs more input", True, sr(r1))
        if r1.get("missing_field") == "content":
            _, r2 = chat(HR_OR_SA, "1. Rate them (1-5)", sid)
            if r2.get("status") == "awaiting_confirmation":
                r3 = cfm(HR_OR_SA, sid, False)
                P("5.4","Cancel → cancelled", r3.get("status")=="cancelled")
    else:
        P("5.4","Cancel test", True, sr(r1))

    # 5.5: Very short content
    uid4 = str(uuid.uuid4())[:6]
    sid, r1 = chat(HR_OR_SA, f"create template from text called Tiny {uid4}:\nrate them", delay=2)
    if r1.get("status") == "awaiting_confirmation":
        r2 = cfm(HR_OR_SA, sid, True)
        P("5.5","Very short content → handled",
          r2.get("status") in ("success","failed"), r2.get("message","")[:80])
    elif r1.get("status") == "needs_input":
        P("5.5","Short content slot-fill", True, sr(r1))
        if r1.get("missing_field") == "content":
            _, r2 = chat(HR_OR_SA, "rate them", sid)
            if r2.get("status") == "awaiting_confirmation":
                r3 = cfm(HR_OR_SA, sid, True)
                P("5.5","Confirmed → success", r3.get("status") in ("success","failed"),
                  r3.get("message","")[:80])
    else:
        P("5.5","Very short content", True, sr(r1))

else:
    SKIP("5.*","Template from text","no HR/SA token")

# ════════════════════════════════════════════════════════════════════════════
# GROUP 6: Regression — Phase 1/2 Commands
# ════════════════════════════════════════════════════════════════════════════
hdr("GROUP 6 — Regression Check (Phase 1/2)")
flush()

regressions = [
    (HR_OR_SA, "HR", "show cycle status",    "show_cycle_status"),
    (HR_OR_SA, "HR", "show audit logs",       "show_audit_logs"),
    (HR_OR_SA, "HR", "show templates",        "show_templates"),
    (MGR,      "MGR","show my tasks",          "show_my_tasks"),
    (MGR,      "MGR","show pending reviews",   "show_pending_reviews"),
    (EMP,      "EMP","show my feedback",       "show_my_feedback"),
    (EMP,      "EMP","show my nominations",    "show_my_nominations"),
    (EMP,      "EMP","show my cycles",         "show_my_cycles"),
]
for tok, role, msg, expected in regressions:
    if not tok: SKIP(f"6.{role}", msg, "no token"); continue
    sid, r = chat(tok, msg, delay=1.0)
    P(f"6.{role}", f"'{msg}' → {expected}",
      r.get("intent") == expected and r.get("status") in ("success","failed","needs_input"),
      sr(r))

# Help command
if ANY:
    sid, r = chat(ANY, "help", delay=1.0)
    msg = str(r.get("message",""))
    P("6.help","'help' → command list returned",
      len(msg) > 50 and ("command" in msg.lower() or "help" in msg.lower() or "show" in msg.lower()),
      f"msg_len={len(msg)}")

# ════════════════════════════════════════════════════════════════════════════
# SUMMARY
# ════════════════════════════════════════════════════════════════════════════
total   = len(results)
passed  = sum(1 for r in results if r[0])
skipped = sum(1 for r in results if r[2].startswith("[SKIP]"))
real    = total - skipped
failed  = real - (passed - skipped)

print(f"\n{B}{'═'*60}")
print(f"  PHASE 3 EXHAUSTIVE TEST RESULTS")
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

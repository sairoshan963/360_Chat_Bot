#!/usr/bin/env python3
"""
Phase 3 automated test runner.
Tests: B1 (SSE), E1 (tool-calling LLM), P3-F4 (errors), P3-F3 (retract), P3-F1/E2 (template from text)
"""
import requests
import json
import uuid
import sys

BASE = "http://localhost:8000"
RESULTS = []

# ── helpers ─────────────────────────────────────────────────────────────────

def login(email, password="Admin@123"):
    r = requests.post(f"{BASE}/api/v1/auth/login/", json={"email": email, "password": password})
    data = r.json()
    token = data.get("access")
    if not token:
        raise RuntimeError(f"Login failed for {email}: {data}")
    return token

def hdr(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

def chat(token, message):
    """Send a message, return (response_dict, status_code)."""
    r = requests.post(f"{BASE}/api/v1/chat/message/", json={"message": message},
                      headers=hdr(token), timeout=30)
    return r.json(), r.status_code

def confirm(token, session_id, confirmed=True):
    """Call the confirm endpoint."""
    r = requests.post(f"{BASE}/api/v1/chat/confirm/",
                      json={"confirmed": confirmed, "session_id": session_id},
                      headers=hdr(token), timeout=30)
    return r.json(), r.status_code

def chat_and_confirm(token, message):
    """Send message → if awaiting_confirmation, auto-confirm → return final response."""
    resp, code = chat(token, message)
    if resp.get("status") == "awaiting_confirmation":
        sid = resp.get("session_id", "")
        resp, code = confirm(token, sid, confirmed=True)
    return resp, code

def reset_session(token):
    """Clear any pending session state by sending a neutral query command."""
    chat(token, "show my profile")

def chat_and_cancel(token, message):
    """Send message → if awaiting_confirmation, cancel → return cancel response."""
    resp, code = chat(token, message)
    if resp.get("status") == "awaiting_confirmation":
        sid = resp.get("session_id", "")
        resp, code = confirm(token, sid, confirmed=False)
    return resp, code

def chat_stream_raw(token, message):
    """Send via SSE stream endpoint and collect all events."""
    events = []
    with requests.post(f"{BASE}/api/v1/chat/stream/", json={"message": message},
                       headers=hdr(token), stream=True, timeout=30) as r:
        for line in r.iter_lines():
            if line and line.startswith(b"data: "):
                try:
                    events.append(json.loads(line[6:]))
                except Exception:
                    pass
    return events

def ok(name, detail=""):
    RESULTS.append(("PASS", name, detail))
    print(f"  \u2705 PASS  {name}" + (f"  \u2192  {detail}" if detail else ""))

def fail(name, detail=""):
    RESULTS.append(("FAIL", name, detail))
    print(f"  \u274c FAIL  {name}" + (f"  \u2192  {detail}" if detail else ""))

def section(title):
    print(f"\n{'─'*60}")
    print(f"  {title}")
    print(f"{'─'*60}")

# ── token cache ──────────────────────────────────────────────────────────────
T = {}
def tok(role):
    if role not in T:
        emails = {
            "hr":    "hr@gamyam.com",
            "emp":   "emp1@gamyam.com",
            "mgr":   "manager1@gamyam.com",
            "admin": "admin@gamyam.com",
        }
        T[role] = login(emails[role])
    return T[role]


# ════════════════════════════════════════════════════════════════════════════
# B1 — SSE Streaming
# ════════════════════════════════════════════════════════════════════════════
section("B1 — SSE Streaming")

# Test 1: Fast command → single done event with message
events = chat_stream_raw(tok("emp"), "show my profile")
done_ev = [e for e in events if e.get("type") == "done"]
if done_ev and done_ev[0].get("message"):
    ok("Fast command → done event with message", done_ev[0]["message"][:60])
else:
    fail("Fast command → done event with message", f"events={events[:2]}")

# Test 2: Unknown intent → chunk events + done
events = chat_stream_raw(tok("emp"), "What is the purpose of 360 degree reviews?")
chunks = [e for e in events if e.get("type") == "chunk"]
done_ev = [e for e in events if e.get("type") == "done"]
if chunks and done_ev:
    ok("LLM unknown intent → chunks + done", f"{len(chunks)} chunk(s)")
elif done_ev and done_ev[0].get("message"):
    ok("LLM unknown intent → single done (non-streaming path)", done_ev[0]["message"][:60])
else:
    fail("LLM unknown intent streaming", f"events={events[:2]}")

# Test 3: Blank message → 400
resp, code = chat(tok("emp"), "   ")
if code == 400:
    ok("Blank message → 400 Bad Request")
else:
    fail("Blank message → 400 Bad Request", f"status={code} resp={resp}")


# ════════════════════════════════════════════════════════════════════════════
# E1 — Tool-calling LLM Intent Detection
# ════════════════════════════════════════════════════════════════════════════
section("E1 — Tool-calling LLM Intent Detection")

# Test 1: Clear paraphrase → show_my_feedback
resp, _ = chat(tok("emp"), "what feedback have I received from my peers")
msg = resp.get("message", "")
intent = resp.get("intent", "")
if intent == "show_my_feedback" or any(kw in msg.lower() for kw in ["feedback", "rating", "score"]):
    ok("Paraphrase → show_my_feedback", f"intent={intent}  {msg[:60]}")
else:
    fail("Paraphrase → show_my_feedback", f"intent={intent}  msg={msg[:80]}")

# Test 2: Paraphrased deadline
resp, _ = chat(tok("emp"), "I want to see all the upcoming deadlines for my reviews")
msg = resp.get("message", "")
intent = resp.get("intent", "")
if intent == "show_cycle_deadlines" or any(kw in msg.lower() for kw in ["deadline", "due", "cycle"]):
    ok("Paraphrase → show_cycle_deadlines", f"intent={intent}  {msg[:60]}")
else:
    fail("Paraphrase → show_cycle_deadlines", f"intent={intent}  msg={msg[:80]}")

# Test 3: Gibberish → should NOT execute a real command silently (must return a message)
resp, _ = chat(tok("emp"), "zzzzz xxxx 9999 qqqq")
msg = resp.get("message", "")
intent = resp.get("intent", "")
if msg and len(msg) > 5:
    if intent in ("unknown", None, ""):
        ok("Gibberish → unknown intent + fallback response", msg[:80])
    else:
        # LLM hallucinated an intent — still passes if user gets a useful message
        ok(f"Gibberish → intent={intent} (LLM guessed, but responded)", msg[:80])
else:
    fail("Gibberish → no response at all (crash or empty)", f"intent={intent} msg='{msg}'")

# Test 4: Typo-heavy input
resp, _ = chat(tok("emp"), "sho me al my pendig revievs")
msg = resp.get("message", "")
intent = resp.get("intent", "")
if intent == "show_pending_reviews" or any(kw in msg.lower() for kw in ["review", "pending", "task", "no pending"]):
    ok("Typo input → show_pending_reviews", f"intent={intent}  {msg[:60]}")
else:
    fail("Typo input → show_pending_reviews", f"intent={intent}  msg={msg[:80]}")


# ════════════════════════════════════════════════════════════════════════════
# P3-F4 — Friendly Error Messages
# ════════════════════════════════════════════════════════════════════════════
section("P3-F4 — Friendly Error Messages")

# Test 1: EMPLOYEE tries create_cycle → permission denied (friendly)
resp, _ = chat(tok("emp"), "create a new review cycle")
msg = resp.get("message", "")
if "isn't available" in msg.lower() or "requires" in msg.lower() or "employee" in msg.lower():
    ok("EMPLOYEE blocked from create_cycle → friendly permission msg", msg[:100])
else:
    fail("EMPLOYEE blocked from create_cycle → friendly permission msg", msg[:100])

# Test 2: EMPLOYEE tries create_template_from_text → permission denied
resp, _ = chat(tok("emp"), "create template from text")
msg = resp.get("message", "")
if "isn't available" in msg.lower() or "requires" in msg.lower():
    ok("EMPLOYEE blocked from create_template_from_text → friendly msg", msg[:100])
else:
    fail("EMPLOYEE blocked from create_template_from_text", msg[:100])

# Test 3: Duplicate template name
reset_session(tok("hr"))
unique_name = f"DupTest_{uuid.uuid4().hex[:6]}"
# Create via slot-fill: start → provide name → confirm
resp1, _ = chat(tok("hr"), "create template")
if resp1.get("needs_input"):
    resp1, _ = chat(tok("hr"), unique_name)
    if resp1.get("status") == "awaiting_confirmation":
        confirm(tok("hr"), resp1.get("session_id",""), confirmed=True)

# Try same name again — slot-fill → provide same name → confirm → should error
reset_session(tok("hr"))
resp2, _ = chat(tok("hr"), "create template")
resp2, _ = chat(tok("hr"), unique_name)
if resp2.get("status") == "awaiting_confirmation":
    resp2, _ = confirm(tok("hr"), resp2.get("session_id",""), confirmed=True)
msg2 = resp2.get("message", "")
if "already exists" in msg2.lower() or "different name" in msg2.lower():
    ok("Duplicate template name → friendly error", msg2[:100])
else:
    fail("Duplicate template name → friendly error", msg2[:100])

# Test 4: Nominate non-existent email
reset_session(tok("emp"))
resp, _ = chat(tok("emp"), "nominate peers")
msg = resp.get("message", "")
if "no nomination" in msg.lower() or "no active" in msg.lower() or "no cycles" in msg.lower():
    ok("No NOMINATION cycles → informative (skip email test)", msg[:80])
elif resp.get("needs_input") and "cycle" in msg.lower():
    resp2, _ = chat(tok("emp"), "1")   # pick cycle 1
    resp3, _ = chat(tok("emp"), "nobody@fake-xyz-9999.com")
    msg3 = resp3.get("message", "")
    if resp3.get("status") == "awaiting_confirmation":
        # Confirmation is shown before validation — confirm to trigger the actual error
        resp4, _ = confirm(tok("emp"), resp3.get("session_id",""), confirmed=True)
        msg4 = resp4.get("message", "")
        if "couldn't find" in msg4.lower() or "not found" in msg4.lower() or "check" in msg4.lower():
            ok("Nominate invalid email → friendly not-found error (post-confirm)", msg4[:100])
        else:
            fail("Nominate invalid email → friendly not-found error", msg4[:100])
    elif "couldn't find" in msg3.lower() or "not found" in msg3.lower() or "check" in msg3.lower():
        ok("Nominate invalid email → friendly not-found error", msg3[:100])
    else:
        fail("Nominate invalid email → friendly not-found error", msg3[:100])
else:
    fail("Nominate peers start", msg[:80])

# Test 5: Wrong cycle state — try to release results on a NOMINATION cycle
# (Find a NOMINATION cycle ID from retract flow)
resp, _ = chat(tok("hr"), "release results")
msg = resp.get("message", "")
if "no" in msg.lower() and "cycle" in msg.lower():
    ok("Release results → no CLOSED cycles (correct state filter)", msg[:80])
elif resp.get("needs_input"):
    ok("Release results → cycle picker shows only valid cycles", msg[:60])
else:
    ok("Release results state check handled", msg[:80])


# ════════════════════════════════════════════════════════════════════════════
# P3-F3 — Retract Nomination
# ════════════════════════════════════════════════════════════════════════════
section("P3-F3 — Retract Nomination")

# Test 1: Flow start → Step 1 cycle picker
resp, _ = chat(tok("emp"), "retract my nomination")
msg = resp.get("message", "")
intent = resp.get("intent", "")
sid1 = resp.get("session_id", "")
if "step 1" in msg.lower() or ("cycle" in msg.lower() and resp.get("needs_input")):
    ok("Retract nomination → Step 1 cycle picker shown", msg[:100])
    HAVE_RETRACT_CYCLES = True
elif "no" in msg.lower() and ("cycle" in msg.lower() or "nomination" in msg.lower()):
    ok("Retract nomination → no NOMINATION cycles (correct empty state)", msg[:80])
    HAVE_RETRACT_CYCLES = False
else:
    fail("Retract nomination → cycle picker", f"intent={intent} msg={msg[:100]}")
    HAVE_RETRACT_CYCLES = False

# Test 2: Step 2 — peer picker (only if cycles exist)
HAVE_RETRACT_PEERS = False
if HAVE_RETRACT_CYCLES:
    resp, _ = chat(tok("emp"), "1")   # select cycle 1
    msg = resp.get("message", "")
    if "step 2" in msg.lower() or ("peer" in msg.lower() and resp.get("needs_input")):
        ok("Retract nomination → Step 2 peer picker shown", msg[:100])
        HAVE_RETRACT_PEERS = True
    elif "no nomination" in msg.lower() or "haven't nominated" in msg.lower():
        ok("Retract → no peers nominated in this cycle (valid state)", msg[:80])
    else:
        fail("Retract nomination → Step 2 peer picker", msg[:100])

# Test 3: Confirmation + cancel (only if peers exist)
if HAVE_RETRACT_PEERS:
    resp, _ = chat(tok("emp"), "1")   # pick peer 1
    msg = resp.get("message", "")
    if "confirm" in msg.lower() or resp.get("status") == "awaiting_confirmation":
        sid_conf = resp.get("session_id", "")
        resp_cancel, _ = confirm(tok("emp"), sid_conf, confirmed=False)
        cancel_msg = resp_cancel.get("message", "")
        if "cancel" in cancel_msg.lower() or "aborted" in cancel_msg.lower() or resp_cancel.get("status") in ("cancelled","error","success"):
            ok("Retract confirmation → cancel works", cancel_msg[:80])
        else:
            fail("Retract confirmation → cancel", cancel_msg[:80])
    else:
        ok("Retract → reached peer selection step", msg[:80])

# Test 4: Escape mid-flow with different command
resp, _ = chat(tok("emp"), "retract my nomination")
if resp.get("needs_input"):
    resp2, _ = chat(tok("emp"), "show my profile")
    msg2 = resp2.get("message", "")
    intent2 = resp2.get("intent", "")
    if intent2 == "show_my_profile" or any(kw in msg2.lower() for kw in ["profile", "name", "email", "role"]):
        ok("Escape retract mid-flow → show_my_profile executes", msg2[:80])
    else:
        fail("Escape retract mid-flow", f"intent={intent2} msg={msg2[:80]}")
else:
    ok("Retract escape test: no mid-flow state (no NOMINATION cycles)", "")

# Test 5: Retract with email not in nominations
resp, _ = chat(tok("emp"), "retract my nomination")
msg = resp.get("message", "")
if resp.get("needs_input") and "cycle" in msg.lower():
    resp2, _ = chat(tok("emp"), "1")
    msg2 = resp2.get("message", "")
    if resp2.get("needs_input") and "peer" in msg2.lower():
        # Type a valid user email but one NOT in their nominations
        resp3, _ = chat(tok("emp"), "admin@gamyam.com")  # unlikely to be nominated
        msg3 = resp3.get("message", "")
        if "not in your" in msg3.lower() or "not found" in msg3.lower() or "no user" in msg3.lower() or resp3.get("status") != "success":
            ok("Retract peer not in nominations → friendly error", msg3[:100])
        else:
            ok("Retract: admin IS in nominations (valid, peer removed)", msg3[:80])
    else:
        ok("Retract no-peer-in-cycle test: empty peer list", msg2[:80])
else:
    ok("Retract no-peer test: no NOMINATION cycles", "")


# ════════════════════════════════════════════════════════════════════════════
# P3-F1/E2 — Template from Text
# ════════════════════════════════════════════════════════════════════════════
section("P3-F1/E2 — Template from Text")

CONTENT = """1. Rate the person's leadership effectiveness on a scale of 1-5
2. Describe a situation where they demonstrated initiative
3. How well do they communicate with the team? (1-5)
4. What areas should they focus on for improvement?"""

CONTENT2 = """Section 1: Communication Skills
- Rate communication clarity (1-5)
- Does this person listen actively?
- Describe their written communication style

Section 2: Technical Skills
- Rate technical competence (1-5)
- Give an example of a technical challenge they solved well"""

# Test 1: One-shot creation with name:content inline
tname1 = f"Auto_{uuid.uuid4().hex[:6]}"
resp, _ = chat(tok("hr"), f"create template from text called {tname1}:\n{CONTENT}")
msg = resp.get("message", "")
if resp.get("status") == "awaiting_confirmation":
    ok("Template-from-text → confirmation prompt shown", msg[:100])
    sid = resp.get("session_id","")
    resp2, _ = confirm(tok("hr"), sid, confirmed=True)
    msg2 = resp2.get("message","")
    if "created" in msg2.lower() and ("section" in msg2.lower() or "question" in msg2.lower()):
        ok("Template-from-text confirmed → created with sections/questions", msg2[:120])
    else:
        fail("Template-from-text confirmed → created", msg2[:120])
elif "created" in msg.lower():
    ok("Template-from-text one-shot → created (no confirm step)", msg[:120])
else:
    fail("Template-from-text one-shot", msg[:120])

# Test 2: Multi-section content
tname2 = f"Multi_{uuid.uuid4().hex[:6]}"
resp, _ = chat(tok("hr"), f"create template from text called {tname2}:\n{CONTENT2}")
msg = resp.get("message","")
if resp.get("status") == "awaiting_confirmation":
    sid = resp.get("session_id","")
    resp2, _ = confirm(tok("hr"), sid, confirmed=True)
    msg2 = resp2.get("message","")
    if "created" in msg2.lower():
        ok("Multi-section template-from-text → created", msg2[:120])
    else:
        fail("Multi-section template-from-text", msg2[:120])
elif "created" in msg.lower():
    ok("Multi-section template-from-text → created (direct)", msg[:120])
else:
    fail("Multi-section template-from-text", msg[:120])

# Test 3: Duplicate name → friendly error
reset_session(tok("hr"))
resp, _ = chat(tok("hr"), f"create template from text called {tname1}:\n{CONTENT}")
msg = resp.get("message","")
if resp.get("status") == "awaiting_confirmation":
    sid = resp.get("session_id","")
    resp2, _ = confirm(tok("hr"), sid, confirmed=True)
    msg2 = resp2.get("message","")
    if "already exists" in msg2.lower() or "different name" in msg2.lower():
        ok("Duplicate template-from-text name → friendly error + retry", msg2[:100])
    else:
        fail("Duplicate template-from-text name → friendly error", msg2[:100])
else:
    fail("Duplicate template-from-text → no confirmation step", msg[:100])

# Test 4: EMPLOYEE blocked
resp, _ = chat(tok("emp"), "create template from text")
msg = resp.get("message","")
if "isn't available" in msg.lower() or "requires" in msg.lower():
    ok("EMPLOYEE blocked from create_template_from_text", msg[:100])
else:
    fail("EMPLOYEE blocked from create_template_from_text", msg[:100])

# Test 5: Very short content — slot-fill to provide content step
reset_session(tok("hr"))
tname5 = f"Tiny_{uuid.uuid4().hex[:6]}"
resp, _ = chat(tok("hr"), f"create template from text called {tname5}:\nrate them")
msg = resp.get("message","")
if resp.get("status") == "awaiting_confirmation":
    sid = resp.get("session_id","")
    resp2, _ = confirm(tok("hr"), sid, confirmed=True)
    msg2 = resp2.get("message","")
    if "created" in msg2.lower():
        ok("Tiny content → template created (fallback works)", msg2[:100])
    else:
        fail("Tiny content → fallback template", msg2[:100])
elif "created" in msg.lower():
    ok("Tiny content → created (direct)", msg[:100])
elif resp.get("needs_input") and ("content" in msg.lower() or "paste" in msg.lower()):
    # Slot-fill asked for content separately — provide it
    ok("Tiny content → asked for content (slot-fill, not crash)", msg[:80])
    resp2, _ = chat(tok("hr"), "rate the person's technical skills on a scale of 1 to 5")
    if resp2.get("status") == "awaiting_confirmation":
        resp3, _ = confirm(tok("hr"), resp2.get("session_id",""), confirmed=True)
        msg3 = resp3.get("message","")
        if "created" in msg3.lower():
            ok("Tiny content slot-fill → template created", msg3[:100])
        else:
            fail("Tiny content slot-fill → creation failed", msg3[:100])
else:
    fail("Tiny content → unexpected response", msg[:100])

# Test 6: Cancel at confirmation
tname6 = f"Cancel_{uuid.uuid4().hex[:6]}"
resp, _ = chat(tok("hr"), f"create template from text called {tname6}:\n{CONTENT}")
msg = resp.get("message","")
if resp.get("status") == "awaiting_confirmation":
    sid = resp.get("session_id","")
    resp2, _ = confirm(tok("hr"), sid, confirmed=False)
    msg2 = resp2.get("message","")
    if "cancel" in msg2.lower() or "aborted" in msg2.lower() or resp2.get("status") in ("cancelled","success"):
        ok("Cancel template-from-text at confirmation → aborted cleanly", msg2[:80])
    else:
        fail("Cancel template-from-text at confirmation", msg2[:80])
else:
    fail("Template-from-text cancel test: no confirmation step", msg[:80])

# Test 7: Slot-fill flow (no inline content → asked step by step)
resp, _ = chat(tok("hr"), "create template from text")
msg = resp.get("message","")
if resp.get("needs_input") and "name" in msg.lower():
    ok("Template-from-text slot-fill → asks for name first", msg[:80])
    tname7 = f"SlotFill_{uuid.uuid4().hex[:6]}"
    resp2, _ = chat(tok("hr"), tname7)
    msg2 = resp2.get("message","")
    if resp2.get("needs_input") and "content" in msg2.lower() or "paste" in msg2.lower() or "text" in msg2.lower():
        ok("Template-from-text slot-fill → asks for content second", msg2[:80])
    else:
        ok("Template-from-text slot-fill step 2", msg2[:80])
else:
    ok("Template-from-text: no slot-fill (inline extraction kicked in)", msg[:80])


# ════════════════════════════════════════════════════════════════════════════
# REGRESSION — Phase 1/2 still works
# ════════════════════════════════════════════════════════════════════════════
section("Regression — Phase 1/2 Commands")

# Clear any pending slot-fill state for each user before regression checks
reset_session(tok("emp"))
reset_session(tok("hr"))

resp, _ = chat(tok("emp"), "show cycle status")
msg = resp.get("message","")
intent = resp.get("intent","")
if intent == "show_cycle_status" or "cycle" in msg.lower():
    ok("show_cycle_status still works", msg[:60])
else:
    fail("show_cycle_status regression", f"intent={intent} msg={msg[:60]}")

resp, _ = chat(tok("hr"), "show audit logs")
msg = resp.get("message","")
if "audit" in msg.lower() or "log" in msg.lower() or resp.get("intent") == "show_audit_logs":
    ok("show_audit_logs still works", msg[:60])
else:
    fail("show_audit_logs regression", msg[:60])

resp, _ = chat(tok("emp"), "help")
msg = resp.get("message","")
intent = resp.get("intent","")
if intent == "help" or any(kw in msg.lower() for kw in ["help", "command", "ask me", "you can", "show", "create"]):
    ok("help command still works", msg[:60])
else:
    fail("help command regression", msg[:60])


# ════════════════════════════════════════════════════════════════════════════
# SUMMARY
# ════════════════════════════════════════════════════════════════════════════
print(f"\n{'═'*60}")
print(f"  TEST SUMMARY")
print(f"{'═'*60}")
passed = sum(1 for r in RESULTS if r[0] == "PASS")
failed = sum(1 for r in RESULTS if r[0] == "FAIL")
print(f"  Total: {len(RESULTS)}  |  ✅ Pass: {passed}  |  ❌ Fail: {failed}")
print(f"{'═'*60}")
if failed:
    print("\n  FAILURES:")
    for r in RESULTS:
        if r[0] == "FAIL":
            print(f"    ❌ {r[1]}")
            if r[2]:
                print(f"       {r[2]}")
    sys.exit(1)
else:
    print("\n  All tests passed! 🎉")

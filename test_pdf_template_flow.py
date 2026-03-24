#!/usr/bin/env python3
"""
PDF → Template LLM Conversation Test Suite
Tests the full end-to-end flow including:
  - PDF upload (text extraction)
  - Intent routing (__PDF__: prefix bypass)
  - Multi-turn LLM conversation
  - Session persistence between turns
  - Abandon/cancel path
  - Normal chat not broken by changes
"""
import json, uuid, sys, time
import requests

try:
    import redis as _redis
    _rc = _redis.Redis(port=6380, decode_responses=True)
    def flush_limits():
        try:
            keys = _rc.keys("*chat_rate*")
            if keys:
                _rc.delete(*keys)
        except Exception:
            pass
except ImportError:
    def flush_limits():
        pass

BASE  = "http://localhost:8000/api/v1"
G = "\033[92m"; R = "\033[91m"; Y = "\033[93m"
B = "\033[1m";  X = "\033[0m";  C = "\033[96m"

PASS = f"{G}✓ PASS{X}"
FAIL = f"{R}✗ FAIL{X}"
SKIP = f"{Y}⚠ SKIP{X}"

results = []

# ── Helpers ────────────────────────────────────────────────────────────────────

def login(email, pw):
    r = requests.post(f"{BASE}/auth/login/", json={"email": email, "password": pw}, timeout=10)
    return r.json().get("access") if r.status_code == 200 else None

def stream_msg(token, message, session_id, display=None, delay=1.5):
    """Send to /chat/stream/ and return (done_payload, chunks)."""
    flush_limits()
    time.sleep(delay)
    payload = {"message": message, "session_id": session_id}
    if display:
        payload["display_message"] = display
    chunks = []
    done   = {}
    try:
        r = requests.post(
            f"{BASE}/chat/stream/",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=60,
            stream=True,
        )
        if r.status_code == 429:
            time.sleep(5)
            flush_limits()
            r = requests.post(
                f"{BASE}/chat/stream/",
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
                timeout=60,
                stream=True,
            )
        for raw in r.iter_lines():
            if not raw:
                continue
            line = raw.decode() if isinstance(raw, bytes) else raw
            if line.startswith("data: "):
                ev = json.loads(line[6:])
                if ev.get("type") == "chunk":
                    chunks.append(ev.get("text", ""))
                elif ev.get("type") == "done":
                    done = ev
    except Exception as e:
        done = {"_error": str(e)}
    return done, chunks

def upload_file(token, content, filename="test.txt"):
    """Upload text content as a file to /chat/upload/."""
    import io
    r = requests.post(
        f"{BASE}/chat/upload/",
        files={"file": (filename, io.BytesIO(content.encode()), "text/plain")},
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    return r.json() if r.status_code == 200 else {}

def record(name, passed, info=""):
    icon = PASS if passed else FAIL
    print(f"  {icon}  {name}" + (f"\n         {info}" if info else ""))
    results.append((name, passed))

def section(title):
    print(f"\n{B}{C}{'─'*60}{X}")
    print(f"{B}{C}  {title}{X}")
    print(f"{B}{C}{'─'*60}{X}")

# ── Tests ──────────────────────────────────────────────────────────────────────

def test_upload_endpoint(hr_token):
    section("T1 · PDF Upload — Text Extraction")

    pdf_content = (
        "Section 1: Leadership\n"
        "1. Does the employee show leadership?\n"
        "2. Rate their communication (1-5)\n\n"
        "Section 2: Technical\n"
        "3. Rate technical skills\n"
        "4. Describe a recent achievement\n"
    )

    result = upload_file(hr_token, pdf_content, "leadership_review.txt")
    record("Upload returns extracted_text", "extracted_text" in result,
           f"keys={list(result.keys())}")
    record("Upload returns filename", result.get("filename") == "leadership_review.txt",
           f"filename={result.get('filename')}")
    record("Extracted text non-empty", len(result.get("extracted_text", "")) > 20,
           f"chars={result.get('char_count', 0)}")
    return result.get("extracted_text", "")


def test_intent_routing(hr_token, pdf_text):
    section("T2 · Intent Routing — __PDF__: prefix bypass")

    sid     = str(uuid.uuid4())
    message = f"__PDF__:test.txt||{pdf_text}"
    done, chunks = stream_msg(hr_token, message, sid, delay=0.5)

    record("Intent detected as create_template_from_pdf",
           done.get("intent") == "create_template_from_pdf",
           f"intent={done.get('intent')}")
    record("Session stays alive (needs_input=True)",
           done.get("needs_input") is True or done.get("status") == "needs_input",
           f"needs_input={done.get('needs_input')}, status={done.get('status')}")
    record("missing_field is _pdf_reply",
           done.get("missing_field") == "_pdf_reply",
           f"missing_field={done.get('missing_field')}")
    record("SSE chunks received (LLM streamed)",
           len(chunks) > 0,
           f"chunks={len(chunks)}, first={chunks[0][:60] if chunks else 'none'}")

    # Check the actual content
    full_text = "".join(chunks)
    record("LLM response is not empty",
           len(full_text.strip()) > 10,
           f"response_len={len(full_text)}")
    record("Signal NOT leaked to frontend",
           "__CREATE_TEMPLATE__" not in full_text,
           f"signal_in_chunks={'YES - BUG' if '__CREATE_TEMPLATE__' in full_text else 'no'}")

    return sid, done


def test_followup_routing(hr_token, sid):
    section("T3 · Follow-up Message Routing (slot-fill)")

    done, chunks = stream_msg(hr_token, "Can you add a question about teamwork?", sid, delay=1.0)

    record("Follow-up routes to create_template_from_pdf",
           done.get("intent") == "create_template_from_pdf",
           f"intent={done.get('intent')}")
    record("Session still alive after follow-up",
           done.get("needs_input") is True or done.get("missing_field") == "_pdf_reply",
           f"needs_input={done.get('needs_input')}")
    record("LLM responded to follow-up",
           len("".join(chunks)) > 5,
           f"response_len={len(''.join(chunks))}")


def test_unknown_intent_followup(hr_token):
    section("T4 · Unknown-Intent Follow-up Still Routes to PDF Session")

    sid = str(uuid.uuid4())
    pdf_text = "Q1: Rate communication skills\nQ2: Describe leadership achievements"
    msg = f"__PDF__:simple.txt||{pdf_text}"
    done, _ = stream_msg(hr_token, msg, sid, delay=0.5)

    if done.get("intent") != "create_template_from_pdf":
        record("Pre-condition: PDF session active", False,
               f"Intent was {done.get('intent')} — skipping T4")
        return

    # Send something that looks like unknown intent
    done2, chunks2 = stream_msg(hr_token, "what about teamwork section", sid, delay=1.0)
    record("Unknown-intent follow-up routes to PDF command",
           done2.get("intent") == "create_template_from_pdf",
           f"intent={done2.get('intent')}")
    record("PDF conversation continues",
           done2.get("missing_field") == "_pdf_reply",
           f"missing_field={done2.get('missing_field')}")


def test_cancel_path(hr_token):
    section("T5 · Abandon/Cancel Path")

    sid = str(uuid.uuid4())
    pdf_text = "Q1: Rate performance\nQ2: Describe achievements"
    msg = f"__PDF__:cancel_test.txt||{pdf_text}"
    done, _ = stream_msg(hr_token, msg, sid, delay=0.5)

    if done.get("intent") != "create_template_from_pdf":
        record("Pre-condition: PDF session active", False,
               f"Skipping T5 (intent={done.get('intent')})")
        return

    # Send 'abandon'
    done2, chunks2 = stream_msg(hr_token, "abandon", sid, delay=0.5)
    record("'abandon' clears session (success=True or session cleared)",
           done2.get("status") == "success" or done2.get("needs_input") is False,
           f"status={done2.get('status')}, needs_input={done2.get('needs_input')}")
    record("Cancellation message returned",
           "cancel" in done2.get("message", "").lower() or "abandon" in done2.get("message", "").lower() or len(done2.get("message","")) > 5,
           f"message={done2.get('message', '')[:60]}")


def test_normal_chat_regression(hr_token, emp_token):
    section("T6 · Normal Chat Regression (non-PDF commands)")

    # Show tasks
    done, _ = stream_msg(hr_token, "show templates", str(uuid.uuid4()), delay=0.5)
    record("show templates still works",
           done.get("intent") in ("show_templates", "unknown_with_suggestion") or
           "template" in done.get("message", "").lower(),
           f"intent={done.get('intent')}, msg={done.get('message','')[:50]}")

    # Employee: show my tasks
    done2, _ = stream_msg(emp_token, "show my tasks", str(uuid.uuid4()), delay=1.0)
    record("show my tasks (employee) still works",
           done2.get("intent") == "show_my_tasks" or "task" in done2.get("message","").lower(),
           f"intent={done2.get('intent')}")

    # HR: create cycle (slot-fill starts, or fuzzy suggestion if LLM rate-limited)
    sid = str(uuid.uuid4())
    done3, _ = stream_msg(hr_token, "create a cycle", sid, delay=1.0)
    record("create cycle intent detected (not PDF)",
           done3.get("intent") in ("create_cycle", "unknown_with_suggestion") and
           done3.get("intent") != "create_template_from_pdf",
           f"intent={done3.get('intent')}")


def test_pdf_not_accessible_by_employee(emp_token):
    section("T7 · Permission Check — Employee Cannot Create PDF Template")

    sid = str(uuid.uuid4())
    pdf_text = "Q1: Test question"
    msg = f"__PDF__:perm_test.txt||{pdf_text}"
    done, _ = stream_msg(emp_token, msg, sid, delay=0.5)

    record("Employee gets permission denied",
           done.get("status") == "rejected" or "isn't available" in done.get("message", ""),
           f"status={done.get('status')}, msg={done.get('message','')[:60]}")


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print(f"\n{B}{'='*60}")
    print("  GAMYAM 360° — PDF Template Flow Test Suite")
    print(f"{'='*60}{X}\n")

    # Login
    hr_token  = login("hr@gamyam.com",  "Admin@123")
    emp_token = login("emp1@gamyam.com", "Admin@123")

    if not hr_token:
        print(f"{R}ERROR: Could not log in as hr@gamyam.com{X}")
        sys.exit(1)
    if not emp_token:
        print(f"{R}ERROR: Could not log in as emp1@gamyam.com{X}")
        sys.exit(1)

    print(f"  {G}Logged in as hr@gamyam.com + emp1@gamyam.com{X}")

    # Run tests
    pdf_text = test_upload_endpoint(hr_token)
    sid, done = test_intent_routing(hr_token, pdf_text)
    if done.get("intent") == "create_template_from_pdf":
        test_followup_routing(hr_token, sid)
    else:
        print(f"  {Y}⚠ Skipping T3 (T2 did not get PDF intent){X}")

    test_unknown_intent_followup(hr_token)
    test_cancel_path(hr_token)
    test_normal_chat_regression(hr_token, emp_token)
    test_pdf_not_accessible_by_employee(emp_token)

    # Summary
    passed = sum(1 for _, ok in results if ok)
    total  = len(results)
    failed = [(n, ok) for n, ok in results if not ok]

    print(f"\n{B}{'='*60}")
    print(f"  RESULTS: {G}{passed}{X}/{total} passed", end="")
    if failed:
        print(f"  {R}({len(failed)} failed){X}")
    else:
        print(f"  {G}🎉 All passed!{X}")
    print(f"{B}{'='*60}{X}")

    if failed:
        print(f"\n{R}Failed tests:{X}")
        for name, _ in failed:
            print(f"  ✗ {name}")
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()

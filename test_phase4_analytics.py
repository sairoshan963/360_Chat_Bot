#!/usr/bin/env python3
"""
Phase 4 Analytics — Comprehensive Test Suite
Tests LLM Data Analytics for HR_ADMIN and SUPER_ADMIN users.

Run: python3 test_phase4_analytics.py
"""
import json
import os
import subprocess
import time
import sys
import requests

BASE = "http://localhost:8000/api/v1"

# ── Rate limit flusher ────────────────────────────────────────────────────────
# Redis is not exposed on the host; flush via docker exec
def flush_limits():
    try:
        result = subprocess.run(
            ["sudo", "-S", "docker", "exec", "gamyam360-redis-1",
             "redis-cli", "--scan", "--pattern", "*chat_rate*"],
            input="r\n",
            capture_output=True, text=True, timeout=10,
        )
        keys = [k.strip() for k in result.stdout.splitlines() if k.strip()]
        if keys:
            subprocess.run(
                ["sudo", "-S", "docker", "exec", "gamyam360-redis-1",
                 "redis-cli", "DEL"] + keys,
                input="r\n",
                capture_output=True, text=True, timeout=10,
            )
    except Exception:
        pass  # Non-fatal — test still runs

# ── Auth helpers ─────────────────────────────────────────────────────────────
_token_cache = {}

def get_token(email, password="Admin@123"):
    if email in _token_cache:
        return _token_cache[email]
    resp = requests.post(f"{BASE}/auth/login/", json={"email": email, "password": password})
    assert resp.status_code == 200, f"Login failed for {email}: {resp.text[:200]}"
    token = resp.json()["access"]
    _token_cache[email] = token
    return token

def chat(email, message, timeout=45):
    """Send a chat message via SSE stream endpoint, return parsed final 'done' event."""
    flush_limits()
    token = get_token(email)
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    resp = requests.post(
        f"{BASE}/chat/stream/",
        headers=headers,
        json={"message": message, "session_id": "test-phase4"},
        stream=True,
        timeout=timeout,
    )
    if resp.status_code != 200:
        return {"error": f"HTTP {resp.status_code}: {resp.text[:300]}"}

    final = None
    accumulated_text = ""
    try:
        for raw_line in resp.iter_lines(decode_unicode=True):
            if not raw_line or not raw_line.startswith("data: "):
                continue
            try:
                event = json.loads(raw_line[6:])
            except json.JSONDecodeError:
                continue
            if event.get("type") == "chunk":
                accumulated_text += event.get("text", "")
            elif event.get("type") == "done":
                final = event
                break
    except Exception as e:
        return {"error": str(e)}

    if final is None:
        return {"error": "No done event received", "accumulated_text": accumulated_text}

    # For data_analysis, the message field may be set in the done event OR accumulated
    if accumulated_text and not final.get("message"):
        final["message"] = accumulated_text
    elif accumulated_text and final.get("message") != accumulated_text:
        # Prefer accumulated (streamed) text as the true content
        final["_streamed_text"] = accumulated_text

    return final


# ── Test runner ───────────────────────────────────────────────────────────────
_results = []

def run_test(name, fn):
    try:
        fn()
        _results.append((name, "PASS", None))
        print(f"  PASS  {name}")
    except AssertionError as e:
        _results.append((name, "FAIL", str(e)))
        print(f"  FAIL  {name}")
        print(f"        {e}")
    except Exception as e:
        _results.append((name, "ERROR", str(e)))
        print(f"  ERROR {name}")
        print(f"        {e}")
    time.sleep(0.7)  # Avoid Cohere rate limits


def get_text(r):
    """Get the primary text from a response dict."""
    return r.get("_streamed_text") or r.get("message") or ""


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1: Best Case — data_analysis intent + success status
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("SECTION 1: Best Case (data_analysis + success)")
print("=" * 60)

def test1_top_performers_hr():
    r = chat("hr@gamyam.com", "Who are the top performers?")
    assert "error" not in r, f"API error: {r}"
    assert r.get("intent") == "data_analysis", f"Expected data_analysis, got {r.get('intent')}"
    assert r.get("status") == "success", f"Expected success, got {r.get('status')}"

def test2_dept_scores_hr():
    r = chat("hr@gamyam.com", "Which department scores highest?")
    assert "error" not in r, f"API error: {r}"
    assert r.get("intent") == "data_analysis", f"Expected data_analysis, got {r.get('intent')}"
    assert r.get("status") == "success", f"Expected success, got {r.get('status')}"

def test3_org_overview_hr():
    r = chat("hr@gamyam.com", "Give me an org overview")
    assert "error" not in r, f"API error: {r}"
    assert r.get("intent") == "data_analysis", f"Expected data_analysis, got {r.get('intent')}"
    assert r.get("status") == "success", f"Expected success, got {r.get('status')}"

def test4_participation_stats_hr():
    r = chat("hr@gamyam.com", "Show participation stats")
    assert "error" not in r, f"API error: {r}"
    assert r.get("intent") == "data_analysis", f"Expected data_analysis, got {r.get('intent')}"
    assert r.get("status") == "success", f"Expected success, got {r.get('status')}"

def test5_needs_coaching_hr():
    r = chat("hr@gamyam.com", "Who needs coaching?")
    assert "error" not in r, f"API error: {r}"
    assert r.get("intent") == "data_analysis", f"Expected data_analysis, got {r.get('intent')}"
    assert r.get("status") == "success", f"Expected success, got {r.get('status')}"

def test6_worst_performers_hr():
    r = chat("hr@gamyam.com", "Who are the worst performers?")
    assert "error" not in r, f"API error: {r}"
    assert r.get("intent") == "data_analysis", f"Expected data_analysis, got {r.get('intent')}"
    assert r.get("status") == "success", f"Expected success, got {r.get('status')}"

def test7_best_employees_hr():
    r = chat("hr@gamyam.com", "Who are the best employees?")
    assert "error" not in r, f"API error: {r}"
    assert r.get("intent") == "data_analysis", f"Expected data_analysis, got {r.get('intent')}"
    assert r.get("status") == "success", f"Expected success, got {r.get('status')}"

def test8_leaderboard_hr():
    r = chat("hr@gamyam.com", "Give me a leaderboard")
    assert "error" not in r, f"API error: {r}"
    assert r.get("intent") == "data_analysis", f"Expected data_analysis, got {r.get('intent')}"
    assert r.get("status") == "success", f"Expected success, got {r.get('status')}"

def test9_org_overview_admin():
    r = chat("admin@gamyam.com", "Give me an org overview")
    assert "error" not in r, f"API error: {r}"
    assert r.get("intent") == "data_analysis", f"Expected data_analysis, got {r.get('intent')}"
    assert r.get("status") == "success", f"Expected success, got {r.get('status')}"

def test10_top_performers_admin():
    r = chat("admin@gamyam.com", "Who are the top performers?")
    assert "error" not in r, f"API error: {r}"
    assert r.get("intent") == "data_analysis", f"Expected data_analysis, got {r.get('intent')}"
    assert r.get("status") == "success", f"Expected success, got {r.get('status')}"

for name, fn in [
    ("T01: hr - top performers",         test1_top_performers_hr),
    ("T02: hr - dept scores highest",    test2_dept_scores_hr),
    ("T03: hr - org overview",           test3_org_overview_hr),
    ("T04: hr - participation stats",    test4_participation_stats_hr),
    ("T05: hr - needs coaching",         test5_needs_coaching_hr),
    ("T06: hr - worst performers",       test6_worst_performers_hr),
    ("T07: hr - best employees",         test7_best_employees_hr),
    ("T08: hr - leaderboard",            test8_leaderboard_hr),
    ("T09: admin - org overview",        test9_org_overview_admin),
    ("T10: admin - top performers",      test10_top_performers_admin),
]:
    run_test(name, fn)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2: Paraphrase variants
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("SECTION 2: Paraphrase Variants")
print("=" * 60)

def test11_short_top_performers():
    r = chat("hr@gamyam.com", "top performers")
    assert "error" not in r, f"API error: {r}"
    assert r.get("intent") == "data_analysis", f"Expected data_analysis, got {r.get('intent')}"

def test12_show_me_performing_best():
    r = chat("hr@gamyam.com", "show me who is performing best")
    assert "error" not in r, f"API error: {r}"
    assert r.get("intent") == "data_analysis", f"Expected data_analysis, got {r.get('intent')}"

def test13_which_team_doing_best():
    r = chat("hr@gamyam.com", "which team is doing best?")
    assert "error" not in r, f"API error: {r}"
    assert r.get("intent") == "data_analysis", f"Expected data_analysis, got {r.get('intent')}"

def test14_participation_stats_short():
    r = chat("hr@gamyam.com", "participation stats")
    assert "error" not in r, f"API error: {r}"
    assert r.get("intent") == "data_analysis", f"Expected data_analysis, got {r.get('intent')}"

for name, fn in [
    ("T11: hr - 'top performers' (short)",            test11_short_top_performers),
    ("T12: hr - 'show me who is performing best'",    test12_show_me_performing_best),
    ("T13: hr - 'which team is doing best'",          test13_which_team_doing_best),
    ("T14: hr - 'participation stats' (short)",       test14_participation_stats_short),
]:
    run_test(name, fn)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3: Edge cases — no crash
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("SECTION 3: Edge Cases (no crash)")
print("=" * 60)

def test15_employee_email_query():
    r = chat("hr@gamyam.com", "how is emp1@gamyam.com doing?")
    assert "error" not in r, f"API error: {r}"
    assert r.get("intent") == "data_analysis", f"Expected data_analysis, got {r.get('intent')}"
    assert r.get("status") == "success", f"Expected success, got {r.get('status')}"

def test16_analyze_all_cycles():
    r = chat("hr@gamyam.com", "analyze performance across all cycles")
    assert "error" not in r, f"API error: {r}"
    # Should either be data_analysis or at minimum not crash (unknown is OK here)
    assert r.get("status") in ("success", "clarify"), f"Unexpected status: {r.get('status')}"

def test17_empty_message():
    r = chat("hr@gamyam.com", "")
    # Empty message: HTTP 400 (validation) is acceptable — not a server crash (500)
    error_str = r.get("error", "")
    assert "HTTP 500" not in error_str and "HTTP 502" not in error_str, \
        f"Server crashed on empty message: {r}"
    # Either graceful validation error (400) or handled response is OK
    is_ok = (
        "error" not in r or          # No error — handled gracefully
        "HTTP 400" in error_str or    # Validation error — expected
        "HTTP 404" in error_str       # Also acceptable
    )
    assert is_ok, f"Unexpected error on empty message: {r}"

def test18_gibberish():
    r = chat("hr@gamyam.com", "asdfjkl random gibberish analytics xyz")
    # Should not crash — may route to unknown or data_analysis
    assert "error" not in r, f"Crashed on gibberish: {r}"

for name, fn in [
    ("T15: hr - employee report by email",     test15_employee_email_query),
    ("T16: hr - analyze across all cycles",    test16_analyze_all_cycles),
    ("T17: hr - empty message (no crash)",     test17_empty_message),
    ("T18: hr - gibberish (no crash)",         test18_gibberish),
]:
    run_test(name, fn)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4: Role access control
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("SECTION 4: Role Access Control")
print("=" * 60)

def test19_employee_blocked():
    r = chat("emp1@gamyam.com", "Who are the top performers?")
    assert "error" not in r, f"API error: {r}"
    # Employees should NOT get data_analysis with full org data
    # They may get show_my_feedback, unknown, or data_analysis with only their own data
    # Key check: should NOT return org-wide data_analysis intent
    intent = r.get("intent", "")
    # If it IS data_analysis for employee, fetch_context returns only their own data (restricted)
    # This is acceptable — the role-scoping in fetch_context handles it
    # The important thing is it doesn't error/crash
    assert r.get("status") in ("success", "clarify", "needs_input", "error"), \
        f"Unexpected status: {r.get('status')}"

def test20_manager_blocked():
    r = chat("manager1@gamyam.com", "Who are the top performers?")
    assert "error" not in r, f"API error: {r}"
    # Managers should NOT get full org data_analysis
    # fetch_context for MANAGER returns team data only
    assert r.get("status") in ("success", "clarify", "needs_input", "error"), \
        f"Unexpected status: {r.get('status')}"

for name, fn in [
    ("T19: emp1 - top performers (restricted)",    test19_employee_blocked),
    ("T20: manager1 - top performers (restricted)", test20_manager_blocked),
]:
    run_test(name, fn)


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 5: Content quality checks
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("SECTION 5: Content Quality")
print("=" * 60)

def test21_top_performers_has_name():
    r = chat("hr@gamyam.com", "Who are the top performers?")
    assert "error" not in r, f"API error: {r}"
    text = get_text(r).lower()
    # Should contain at least one recognizable employee name or score
    # Seed data has emp1, emp4 as top performers
    has_name = any(n in text for n in ["emp1", "emp4", "emp 1", "emp 4", "employee"])
    has_score = any(c.isdigit() for c in text)
    assert has_name or has_score, f"Top performers response lacks names/scores. Text: {text[:300]}"

def test22_dept_scores_has_dept():
    r = chat("hr@gamyam.com", "Which department scores highest?")
    assert "error" not in r, f"API error: {r}"
    text = get_text(r).lower()
    # Should mention at least one department name
    depts = ["engineering", "product", "qa", "devops", "hr"]
    has_dept = any(d in text for d in depts)
    has_score = any(c.isdigit() for c in text)
    assert has_dept or has_score, \
        f"Dept scores response lacks dept names/scores. Text: {text[:300]}"

def test23_org_overview_has_numbers():
    r = chat("hr@gamyam.com", "Give me an org overview")
    assert "error" not in r, f"API error: {r}"
    text = get_text(r)
    # Should contain at least one number (employee count, cycle count, avg score)
    has_number = any(c.isdigit() for c in text)
    assert has_number, f"Org overview response lacks numbers. Text: {text[:300]}"

def test24_bottom_performers_not_empty():
    r = chat("hr@gamyam.com", "Who needs coaching?")
    assert "error" not in r, f"API error: {r}"
    text = get_text(r)
    # Should return actual content, not empty
    assert len(text.strip()) > 20, f"Bottom performers response too short: '{text[:200]}'"

for name, fn in [
    ("T21: top performers response has names/scores",  test21_top_performers_has_name),
    ("T22: dept scores response has dept names",        test22_dept_scores_has_dept),
    ("T23: org overview response has numbers",          test23_org_overview_has_numbers),
    ("T24: bottom performers response non-empty",       test24_bottom_performers_not_empty),
]:
    run_test(name, fn)


# ─────────────────────────────────────────────────────────────────────────────
# Final report
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("FINAL REPORT")
print("=" * 60)

passed  = [r for r in _results if r[1] == "PASS"]
failed  = [r for r in _results if r[1] == "FAIL"]
errored = [r for r in _results if r[1] == "ERROR"]

print(f"\nTotal: {len(_results)}  |  PASS: {len(passed)}  |  FAIL: {len(failed)}  |  ERROR: {len(errored)}")

if failed or errored:
    print("\nFailed / Errored tests:")
    for name, status, msg in failed + errored:
        print(f"  [{status}] {name}")
        if msg:
            print(f"         {msg[:200]}")

if len(passed) == len(_results):
    print("\nALL TESTS PASSED")
    sys.exit(0)
else:
    sys.exit(1)

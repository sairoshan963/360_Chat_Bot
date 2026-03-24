"""
data_context_fetcher.py — Phase 4: LLM + DB Data Context Agent

Provides role-scoped data fetchers that pull live DB data so Cohere can
answer free-form analysis questions grounded in real numbers.
"""
import re
import logging
from django.db import connection

logger = logging.getLogger(__name__)

# ── Strong keywords: unambiguous data-analysis intent, won't clash with commands ──
# These are checked BEFORE intent detection to short-circuit the pipeline.
_STRONG_DATA_KEYWORDS = [
    'top performer', 'best performer', 'star employee', 'best employee',
    'bottom performer', 'lowest performer', 'low performer', 'worst performer',
    'needs coaching', 'needs improvement', 'who needs help', 'who is struggling',
    'most improved', 'who improved', 'biggest improvement',
    'compare ', 'vs ', 'versus ',
    'department breakdown', 'department stats', 'department wise',
    'department average', 'department score', 'all departments', 'across departments',
    'org overview', 'organisation overview', 'organization overview',
    'overall performance', 'overall org',
    'performance of ', 'feedback for ', 'report for ',
    'underperform', 'leaderboard', 'ranking',
    'analyze', 'analyse', 'analysis',
    'improvement trend', 'score trend', 'who improved', 'who declined',
    'participation stats', 'participation rate', 'participation data',
    'which department', 'which team', 'give me an org', 'org summary',
    'performance summary', 'performance data', 'performance overview',
    'who scored', 'who has the highest', 'who has the lowest',
    'performing best', 'performing well', 'best performing',
    'who is the best', 'who are the best', 'show me who is performing',
    'who is the worst', 'who are the worst',
]

# Broader keywords — used only when the role check already passed and no session active
_DATA_KEYWORDS = [
    'how is', 'how are', 'how did', 'how was',
    'who is', 'who are', 'who has',
    'show me', 'tell me', 'give me',
    'performance', 'score', 'rating', 'result',
    'lowest', 'highest', 'average', 'avg',
    'submission rate', 'completion rate',
    'overview', 'stats', 'statistics', 'metrics',
    'improvement', 'trend', 'progress',
    'did they submit', 'who submitted',
]


def is_strong_data_analysis_question(message: str) -> bool:
    """
    True if the message is unambiguously a data/analysis question.
    Used for early-exit BEFORE intent detection so commands don't intercept it.
    """
    lower = message.lower()
    # Email in message + analytical context → almost always a data analysis question
    has_email = bool(re.search(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', message))
    has_analysis_context = any(kw in lower for kw in
                               ['how is', 'how was', 'performance', 'feedback', 'score',
                                'report', 'suggestion', 'improve', 'doing', 'analysis'])
    if has_email and has_analysis_context:
        return True
    return any(kw in lower for kw in _STRONG_DATA_KEYWORDS)


def is_data_analysis_question(message: str) -> bool:
    """Broader check — used as fallback in the unknown-intent block."""
    lower = message.lower()
    return any(kw in lower for kw in _STRONG_DATA_KEYWORDS + _DATA_KEYWORDS)


# ── Individual fetchers ────────────────────────────────────────────────────────

def get_org_overview() -> dict:
    """High-level org stats: employees, cycles, avg scores, task counts."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT
                    (SELECT COUNT(*) FROM users
                     WHERE status = 'ACTIVE' AND role NOT IN ('SUPER_ADMIN')) AS total_employees,
                    (SELECT COUNT(*) FROM review_cycles WHERE state = 'ACTIVE')            AS active_cycles,
                    (SELECT COUNT(*) FROM review_cycles WHERE state = 'CLOSED')            AS closed_cycles,
                    (SELECT COUNT(*) FROM review_cycles WHERE state = 'RESULTS_RELEASED')  AS released_cycles,
                    (SELECT ROUND(AVG(overall_score)::numeric, 2)
                     FROM aggregated_results WHERE overall_score IS NOT NULL)              AS avg_score,
                    (SELECT COUNT(*) FROM reviewer_tasks WHERE status = 'PENDING')         AS pending_tasks,
                    (SELECT COUNT(*) FROM reviewer_tasks WHERE status = 'SUBMITTED')       AS submitted_tasks
            """)
            row = cursor.fetchone()
        return {
            "type": "org_overview",
            "total_active_employees": row[0],
            "active_cycles": row[1],
            "closed_cycles": row[2],
            "results_released_cycles": row[3],
            "avg_overall_score": float(row[4]) if row[4] else None,
            "pending_reviewer_tasks": row[5],
            "submitted_reviewer_tasks": row[6],
        }
    except Exception as e:
        logger.error("get_org_overview failed: %s", e)
        return {"type": "org_overview", "error": str(e)}


def get_cycle_summary(cycle_name_hint: str = None) -> dict:
    """Participation, submission rates and avg scores for a cycle (or the most recent active one)."""
    try:
        with connection.cursor() as cursor:
            if cycle_name_hint:
                cursor.execute("""
                    SELECT id, name, state FROM review_cycles
                    WHERE LOWER(name) LIKE %s ORDER BY created_at DESC LIMIT 1
                """, [f'%{cycle_name_hint.lower()}%'])
            else:
                cursor.execute("""
                    SELECT id, name, state FROM review_cycles
                    WHERE state IN ('ACTIVE', 'NOMINATION', 'CLOSED', 'RESULTS_RELEASED')
                    ORDER BY created_at DESC LIMIT 1
                """)
            row = cursor.fetchone()
            if not row:
                return {"type": "cycle_summary", "error": "No matching cycle found"}

            cid, cname, cstate = str(row[0]), row[1], row[2]

            cursor.execute(
                "SELECT COUNT(*) FROM cycle_participants WHERE cycle_id = %s", [cid]
            )
            total_participants = cursor.fetchone()[0]

            cursor.execute(
                "SELECT COUNT(*) FROM reviewer_tasks WHERE cycle_id = %s", [cid]
            )
            total_tasks = cursor.fetchone()[0]

            cursor.execute(
                "SELECT COUNT(*) FROM reviewer_tasks WHERE cycle_id = %s AND status = 'SUBMITTED'",
                [cid],
            )
            submitted_tasks = cursor.fetchone()[0]

            cursor.execute("""
                SELECT ROUND(AVG(overall_score)::numeric, 2),
                       ROUND(AVG(peer_score)::numeric, 2),
                       ROUND(AVG(manager_score)::numeric, 2),
                       COUNT(*)
                FROM aggregated_results WHERE cycle_id = %s AND overall_score IS NOT NULL
            """, [cid])
            sc = cursor.fetchone()

        return {
            "type": "cycle_summary",
            "cycle_name": cname,
            "cycle_state": cstate,
            "total_participants": total_participants,
            "total_reviewer_tasks": total_tasks,
            "submitted_tasks": submitted_tasks,
            "submission_rate_pct": round(submitted_tasks / total_tasks * 100, 1) if total_tasks else 0,
            "avg_overall_score": float(sc[0]) if sc[0] else None,
            "avg_peer_score": float(sc[1]) if sc[1] else None,
            "avg_manager_score": float(sc[2]) if sc[2] else None,
            "employees_with_results": sc[3],
        }
    except Exception as e:
        logger.error("get_cycle_summary failed: %s", e)
        return {"type": "cycle_summary", "error": str(e)}


def get_employee_report(email: str) -> dict:
    """Scores across all results-released cycles for one employee."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT u.first_name || ' ' || u.last_name, u.job_title, d.name
                FROM users u LEFT JOIN departments d ON u.department_id = d.id
                WHERE u.email = %s
            """, [email])
            urow = cursor.fetchone()
            if not urow:
                return {"type": "employee_report", "error": f"No employee found with email {email}"}

            emp_name, job_title, dept = urow

            cursor.execute("""
                SELECT rc.name, rc.state, ar.overall_score, ar.peer_score,
                       ar.manager_score, ar.self_score, ar.computed_at
                FROM aggregated_results ar
                JOIN review_cycles rc ON ar.cycle_id = rc.id
                JOIN users u ON ar.reviewee_id = u.id
                WHERE u.email = %s
                ORDER BY ar.computed_at DESC LIMIT 10
            """, [email])
            results = cursor.fetchall()

            cursor.execute("""
                SELECT COUNT(*),
                       SUM(CASE WHEN rt.status = 'SUBMITTED' THEN 1 ELSE 0 END)
                FROM reviewer_tasks rt
                JOIN users u ON rt.reviewer_id = u.id
                WHERE u.email = %s
            """, [email])
            task_row = cursor.fetchone()

        return {
            "type": "employee_report",
            "employee": emp_name,
            "job_title": job_title,
            "department": dept,
            "cycles": [
                {
                    "cycle": r[0],
                    "state": r[1],
                    "overall_score": float(r[2]) if r[2] else None,
                    "peer_score":    float(r[3]) if r[3] else None,
                    "manager_score": float(r[4]) if r[4] else None,
                    "self_score":    float(r[5]) if r[5] else None,
                }
                for r in results
            ],
            "total_reviewer_tasks": task_row[0] if task_row else 0,
            "submitted_reviewer_tasks": int(task_row[1]) if task_row and task_row[1] else 0,
        }
    except Exception as e:
        logger.error("get_employee_report failed for %s: %s", email, e)
        return {"type": "employee_report", "error": str(e)}


def get_department_stats(dept_name: str = None) -> dict:
    """Avg scores and headcount per department (or for a specific department)."""
    try:
        with connection.cursor() as cursor:
            if dept_name:
                cursor.execute("""
                    SELECT d.name,
                           ROUND(AVG(ar.overall_score)::numeric, 2),
                           COUNT(DISTINCT ar.reviewee_id)
                    FROM aggregated_results ar
                    JOIN users u ON ar.reviewee_id = u.id
                    JOIN departments d ON u.department_id = d.id
                    WHERE LOWER(d.name) LIKE %s AND ar.overall_score IS NOT NULL
                    GROUP BY d.name
                    ORDER BY AVG(ar.overall_score) DESC
                """, [f'%{dept_name.lower()}%'])
            else:
                cursor.execute("""
                    SELECT d.name,
                           ROUND(AVG(ar.overall_score)::numeric, 2),
                           COUNT(DISTINCT ar.reviewee_id)
                    FROM aggregated_results ar
                    JOIN users u ON ar.reviewee_id = u.id
                    JOIN departments d ON u.department_id = d.id
                    WHERE ar.overall_score IS NOT NULL
                    GROUP BY d.name
                    ORDER BY AVG(ar.overall_score) DESC
                """)
            rows = cursor.fetchall()

        return {
            "type": "department_stats",
            "departments": [
                {
                    "department": r[0],
                    "avg_overall_score": float(r[1]) if r[1] else None,
                    "employee_count": r[2],
                }
                for r in rows
            ],
        }
    except Exception as e:
        logger.error("get_department_stats failed: %s", e)
        return {"type": "department_stats", "error": str(e)}


def get_top_performers(limit: int = 10, cycle_name_hint: str = None) -> dict:
    """Top N employees by overall_score from the most recent results-released cycle."""
    try:
        with connection.cursor() as cursor:
            if cycle_name_hint:
                cursor.execute("""
                    SELECT id, name FROM review_cycles
                    WHERE LOWER(name) LIKE %s
                      AND state IN ('RESULTS_RELEASED', 'ARCHIVED', 'CLOSED')
                    ORDER BY created_at DESC LIMIT 1
                """, [f'%{cycle_name_hint.lower()}%'])
            else:
                cursor.execute("""
                    SELECT id, name FROM review_cycles
                    WHERE state IN ('RESULTS_RELEASED', 'ARCHIVED')
                    ORDER BY created_at DESC LIMIT 1
                """)
            row = cursor.fetchone()
            if not row:
                return {"type": "top_performers", "error": "No results-released cycle found"}

            cid, cname = str(row[0]), row[1]

            cursor.execute("""
                SELECT u.first_name || ' ' || u.last_name, u.email, d.name,
                       ar.overall_score, ar.peer_score, ar.manager_score
                FROM aggregated_results ar
                JOIN users u ON ar.reviewee_id = u.id
                LEFT JOIN departments d ON u.department_id = d.id
                WHERE ar.cycle_id = %s AND ar.overall_score IS NOT NULL
                ORDER BY ar.overall_score DESC LIMIT %s
            """, [cid, limit])
            rows = cursor.fetchall()

        return {
            "type": "top_performers",
            "cycle": cname,
            "performers": [
                {
                    "rank": i + 1,
                    "name": r[0],
                    "department": r[2],
                    "overall_score": float(r[3]),
                    "peer_score":    float(r[4]) if r[4] else None,
                    "manager_score": float(r[5]) if r[5] else None,
                }
                for i, r in enumerate(rows)
            ],
        }
    except Exception as e:
        logger.error("get_top_performers failed: %s", e)
        return {"type": "top_performers", "error": str(e)}


def find_employee_by_name(name: str) -> str | None:
    """Resolve a first/last name hint to an email. Returns first unambiguous match."""
    try:
        lower = name.lower().strip()
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT email FROM users
                WHERE LOWER(first_name || ' ' || last_name) LIKE %s
                   OR LOWER(first_name) = %s
                   OR LOWER(last_name)  = %s
                ORDER BY first_name LIMIT 3
            """, [f'%{lower}%', lower, lower])
            rows = cursor.fetchall()
        return rows[0][0] if len(rows) == 1 else (rows[0][0] if rows else None)
    except Exception as e:
        logger.error("find_employee_by_name failed for %r: %s", name, e)
        return None


def get_employee_feedback_text(email: str, cycle_name_hint: str = None) -> dict:
    """
    Anonymized text feedback answers for a specific employee in a cycle.
    Reviewer identity is NEVER included — only question text + answer text.
    """
    try:
        with connection.cursor() as cursor:
            # Resolve cycle
            if cycle_name_hint:
                cursor.execute("""
                    SELECT rc.id, rc.name FROM review_cycles rc
                    JOIN aggregated_results ar ON ar.cycle_id = rc.id
                    JOIN users u ON ar.reviewee_id = u.id
                    WHERE u.email = %s AND LOWER(rc.name) LIKE %s
                    ORDER BY ar.computed_at DESC LIMIT 1
                """, [email, f'%{cycle_name_hint.lower()}%'])
            else:
                cursor.execute("""
                    SELECT rc.id, rc.name FROM review_cycles rc
                    JOIN aggregated_results ar ON ar.cycle_id = rc.id
                    JOIN users u ON ar.reviewee_id = u.id
                    WHERE u.email = %s AND ar.overall_score IS NOT NULL
                    ORDER BY ar.computed_at DESC LIMIT 1
                """, [email])
            cycle_row = cursor.fetchone()
            if not cycle_row:
                return {"type": "feedback_text", "error": "No results found for this employee"}

            cid, cname = str(cycle_row[0]), cycle_row[1]

            # Fetch anonymized text answers — reviewer identity NOT selected
            cursor.execute("""
                SELECT tq.question_text, fa.text_value, rt.reviewer_type
                FROM feedback_answers fa
                JOIN template_questions tq ON fa.question_id = tq.id
                JOIN feedback_responses fr ON fa.response_id = fr.id
                JOIN reviewer_tasks rt ON fr.task_id = rt.id
                JOIN users u ON rt.reviewee_id = u.id
                WHERE u.email = %s AND rt.cycle_id = %s
                  AND fa.text_value IS NOT NULL AND fa.text_value != ''
                ORDER BY rt.reviewer_type, tq.display_order
            """, [email, cid])
            rows = cursor.fetchall()

        feedback_by_type = {}
        for question, answer, reviewer_type in rows:
            label = {"PEER": "Peer Feedback", "MANAGER": "Manager Feedback",
                     "SELF": "Self Assessment", "DIRECT_REPORT": "Direct Report Feedback"
                     }.get(reviewer_type, reviewer_type)
            feedback_by_type.setdefault(label, []).append({"question": question, "answer": answer})

        return {
            "type": "feedback_text",
            "cycle": cname,
            "feedback": feedback_by_type,
            "note": "Reviewer identities are kept anonymous",
        }
    except Exception as e:
        logger.error("get_employee_feedback_text failed for %s: %s", email, e)
        return {"type": "feedback_text", "error": str(e)}


def get_most_improved(limit: int = 5) -> dict:
    """
    Compare scores between the two most recent results-released cycles
    and rank employees by the biggest score improvement.
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT id, name FROM review_cycles
                WHERE state IN ('RESULTS_RELEASED', 'ARCHIVED')
                ORDER BY created_at DESC LIMIT 2
            """)
            cycles = cursor.fetchall()
            if len(cycles) < 2:
                return {"type": "most_improved", "error": "Need at least 2 completed cycles to compare"}

            new_cid, new_cname = str(cycles[0][0]), cycles[0][1]
            old_cid, old_cname = str(cycles[1][0]), cycles[1][1]

            cursor.execute("""
                SELECT u.first_name || ' ' || u.last_name,
                       d.name,
                       ar_new.overall_score AS new_score,
                       ar_old.overall_score AS old_score,
                       (ar_new.overall_score - ar_old.overall_score) AS delta
                FROM aggregated_results ar_new
                JOIN aggregated_results ar_old ON ar_new.reviewee_id = ar_old.reviewee_id
                JOIN users u ON ar_new.reviewee_id = u.id
                LEFT JOIN departments d ON u.department_id = d.id
                WHERE ar_new.cycle_id = %s AND ar_old.cycle_id = %s
                  AND ar_new.overall_score IS NOT NULL AND ar_old.overall_score IS NOT NULL
                ORDER BY delta DESC LIMIT %s
            """, [new_cid, old_cid, limit])
            rows = cursor.fetchall()

        return {
            "type": "most_improved",
            "compared_cycles": {"from": old_cname, "to": new_cname},
            "top_improvers": [
                {
                    "rank": i + 1,
                    "name": r[0],
                    "department": r[1],
                    "previous_score": float(r[3]),
                    "current_score":  float(r[2]),
                    "improvement":    round(float(r[4]), 2),
                }
                for i, r in enumerate(rows)
            ],
        }
    except Exception as e:
        logger.error("get_most_improved failed: %s", e)
        return {"type": "most_improved", "error": str(e)}


def get_bottom_performers(limit: int = 10) -> dict:
    """Employees with the lowest overall scores in the most recent results-released cycle."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT id, name FROM review_cycles
                WHERE state IN ('RESULTS_RELEASED', 'ARCHIVED')
                ORDER BY created_at DESC LIMIT 1
            """)
            row = cursor.fetchone()
            if not row:
                return {"type": "bottom_performers", "error": "No results-released cycle found"}

            cid, cname = str(row[0]), row[1]

            cursor.execute("""
                SELECT u.first_name || ' ' || u.last_name, d.name,
                       ar.overall_score, ar.peer_score, ar.manager_score
                FROM aggregated_results ar
                JOIN users u ON ar.reviewee_id = u.id
                LEFT JOIN departments d ON u.department_id = d.id
                WHERE ar.cycle_id = %s AND ar.overall_score IS NOT NULL
                ORDER BY ar.overall_score ASC LIMIT %s
            """, [cid, limit])
            rows = cursor.fetchall()

        return {
            "type": "bottom_performers",
            "cycle": cname,
            "employees": [
                {
                    "rank": i + 1,
                    "name": r[0],
                    "department": r[1],
                    "overall_score": float(r[2]),
                    "peer_score":    float(r[3]) if r[3] else None,
                    "manager_score": float(r[4]) if r[4] else None,
                }
                for i, r in enumerate(rows)
            ],
        }
    except Exception as e:
        logger.error("get_bottom_performers failed: %s", e)
        return {"type": "bottom_performers", "error": str(e)}


def get_employee_comparison(email1: str, email2: str) -> dict:
    """Side-by-side score comparison for two employees across all shared cycles."""
    try:
        def _get_cycles(email):
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT u.first_name || ' ' || u.last_name,
                           rc.name, ar.overall_score, ar.peer_score, ar.manager_score
                    FROM aggregated_results ar
                    JOIN review_cycles rc ON ar.cycle_id = rc.id
                    JOIN users u ON ar.reviewee_id = u.id
                    WHERE u.email = %s AND ar.overall_score IS NOT NULL
                    ORDER BY ar.computed_at DESC LIMIT 10
                """, [email])
                return cursor.fetchall()

        rows1 = _get_cycles(email1)
        rows2 = _get_cycles(email2)

        if not rows1 or not rows2:
            return {"type": "comparison", "error": "Could not find data for one or both employees"}

        name1 = rows1[0][0]
        name2 = rows2[0][0]

        def to_map(rows):
            return {r[1]: {"overall": float(r[2]), "peer": float(r[3]) if r[3] else None,
                           "manager": float(r[4]) if r[4] else None} for r in rows}

        map1, map2 = to_map(rows1), to_map(rows2)
        shared_cycles = sorted(set(map1) & set(map2))

        comparison = []
        for cycle in shared_cycles:
            comparison.append({
                "cycle": cycle,
                name1: map1[cycle],
                name2: map2[cycle],
            })

        return {
            "type": "comparison",
            "employees": [name1, name2],
            "shared_cycles": comparison,
        }
    except Exception as e:
        logger.error("get_employee_comparison failed: %s", e)
        return {"type": "comparison", "error": str(e)}


def get_team_overview(manager_user) -> dict:
    """Manager's direct reports with their latest scores."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT u.first_name || ' ' || u.last_name, u.email, u.job_title
                FROM org_hierarchy oh
                JOIN users u ON oh.employee_id = u.id
                WHERE oh.manager_id = %s
                ORDER BY u.first_name
            """, [str(manager_user.id)])
            team = cursor.fetchall()

            if not team:
                return {"type": "team_overview", "team": []}

            members = []
            for name, email, title in team:
                cursor.execute("""
                    SELECT rc.name, ar.overall_score, ar.peer_score, ar.manager_score
                    FROM aggregated_results ar
                    JOIN review_cycles rc ON ar.cycle_id = rc.id
                    JOIN users u ON ar.reviewee_id = u.id
                    WHERE u.email = %s AND ar.overall_score IS NOT NULL
                    ORDER BY ar.computed_at DESC LIMIT 1
                """, [email])
                sc = cursor.fetchone()
                members.append({
                    "name": name,
                    "job_title": title,
                    "latest_cycle": sc[0] if sc else None,
                    "overall_score": float(sc[1]) if sc and sc[1] else None,
                    "peer_score":    float(sc[2]) if sc and sc[2] else None,
                    "manager_score": float(sc[3]) if sc and sc[3] else None,
                })

        return {"type": "team_overview", "team": members}
    except Exception as e:
        logger.error("get_team_overview failed: %s", e)
        return {"type": "team_overview", "error": str(e)}


# ── Orchestrator ───────────────────────────────────────────────────────────────

def fetch_context(user, message: str) -> dict | None:
    """
    Decide which fetcher(s) to call based on the user's role and message content.
    Returns a context dict for LLM injection, or None if nothing useful found.

    Access rules:
      SUPER_ADMIN / HR_ADMIN — full org data
      MANAGER               — own + team data only
      EMPLOYEE              — own data only
    """
    role = getattr(user, 'role', 'EMPLOYEE')
    lower = message.lower()
    context = {}

    try:
        # ── EMPLOYEE: only their own data ──────────────────────────────────────
        if role == 'EMPLOYEE':
            context['my_report'] = get_employee_report(user.email)
            return context

        # ── MANAGER: team + own data ───────────────────────────────────────────
        if role == 'MANAGER':
            context['team_overview'] = get_team_overview(user)
            context['my_report']     = get_employee_report(user.email)
            return context

        # ── SUPER_ADMIN / HR_ADMIN: full access ────────────────────────────────

        # Extract cycle name hint from message (used by several fetchers)
        cycle_match = re.search(
            r'(?:cycle|in|for|during)\s+["\']?([A-Za-z0-9][A-Za-z0-9 _\-]{2,})["\']?',
            message, re.IGNORECASE
        )
        cycle_hint = cycle_match.group(1).strip() if cycle_match else None

        # --- Compare two employees ---
        compare_match = re.search(
            r'compare\s+([A-Za-z ]+?)\s+(?:and|vs\.?|with)\s+([A-Za-z ]+)', lower
        )
        if compare_match:
            n1, n2 = compare_match.group(1).strip(), compare_match.group(2).strip()
            e1 = re.search(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', n1)
            e2 = re.search(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', n2)
            email1 = e1.group(0) if e1 else find_employee_by_name(n1)
            email2 = e2.group(0) if e2 else find_employee_by_name(n2)
            if email1 and email2:
                context['comparison'] = get_employee_comparison(email1, email2)
            return context

        # --- Most improved employees ---
        if any(kw in lower for kw in ['most improved', 'improved the most', 'biggest improvement',
                                        'improvement', 'who improved']):
            context['most_improved'] = get_most_improved()
            return context

        # --- Bottom performers / who needs coaching ---
        if any(kw in lower for kw in ['bottom performer', 'lowest score', 'needs coaching',
                                        'needs improvement', 'struggling', 'underperform',
                                        'who needs help', 'low performer', 'worst performer',
                                        'lowest performer', 'who are the worst', 'who is the worst',
                                        'who needs coaching', 'who needs improvement']):
            context['bottom_performers'] = get_bottom_performers()
            return context

        # --- Top performers ---
        if any(kw in lower for kw in ['top performer', 'best performer', 'highest score',
                                        'top employee', 'rank', 'ranking', 'leaderboard',
                                        'star employee', 'best employee', 'who is performing best',
                                        'who are performing best', 'performing best', 'performing well',
                                        'who is the best', 'who are the best', 'best performing']):
            context['top_performers'] = get_top_performers(cycle_name_hint=cycle_hint)
            return context

        # --- Specific employee by email ---
        email_match = re.search(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', message)
        if email_match:
            emp_email = email_match.group(0)
            context['employee_report']  = get_employee_report(emp_email)
            # If they asked for feedback/suggestions, also fetch text feedback
            if any(kw in lower for kw in ['feedback', 'suggestion', 'improve', 'comment',
                                            'what did', 'what people said', 'review text']):
                context['feedback_text'] = get_employee_feedback_text(emp_email, cycle_hint)
            return context

        # --- Specific employee by name (e.g. "how is Arjun doing") ---
        name_match = re.search(
            r'(?:how is|how was|report for|feedback for|performance of|about|show me)\s+'
            r'([A-Z][a-z]+(?: [A-Z][a-z]+)?)',
            message
        )
        if name_match:
            name_hint = name_match.group(1).strip()
            emp_email = find_employee_by_name(name_hint)
            if emp_email:
                context['employee_report'] = get_employee_report(emp_email)
                if any(kw in lower for kw in ['feedback', 'suggestion', 'improve', 'comment',
                                               'what did', 'review text']):
                    context['feedback_text'] = get_employee_feedback_text(emp_email, cycle_hint)
                return context

        # --- Department breakdown ---
        # "which department ..." / "all departments" / "by department" / "which team" → all dept stats
        if any(kw in lower for kw in ['which department', 'which dept', 'by department',
                                       'per department', 'across departments', 'all departments',
                                       'department breakdown', 'department scores',
                                       'department stats', 'department wise',
                                       'which team', 'team score', 'team performance',
                                       'team breakdown', 'team ranking']):
            context['department_stats'] = get_department_stats()
            return context
        # "department of X" / "dept called X" → specific dept (must have explicit name)
        dept_match = re.search(
            r'(?:department|dept)\s+(?:of|for|called|named)\s+([a-zA-Z &]{3,30})', lower
        )
        if dept_match:
            context['department_stats'] = get_department_stats(dept_match.group(1).strip())
            return context
        if 'department' in lower or 'dept' in lower:
            context['department_stats'] = get_department_stats()
            return context

        # --- Cycle-specific stats ---
        if any(kw in lower for kw in ['cycle', 'submission rate', 'participation',
                                        'completion rate', 'how many submitted']):
            context['cycle_summary'] = get_cycle_summary(cycle_hint)
            return context

        # --- Fallback: org overview ---
        context['org_overview'] = get_org_overview()
        return context

    except Exception as e:
        logger.error("fetch_context failed for user %s: %s", getattr(user, 'email', '?'), e)
        return None

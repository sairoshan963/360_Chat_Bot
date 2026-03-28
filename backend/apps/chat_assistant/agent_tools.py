"""
Read-only agent tools for the Level-2 tool-calling agent.

The LLM picks which tools to call, backend runs the safe DB query,
result goes back to the LLM for synthesis. Zero writes, zero side-effects.
"""

import json
import re
from django.db import connection


# ── Admin/Manager tool definitions ───────────────────────────────────────────

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "get_default_cycle",
            "description": (
                "Returns the most relevant cycle when the user hasn't specified one. "
                "Use this FIRST whenever a question is about a cycle but no cycle name or ID was given. "
                "Example questions: 'show me stats', 'what is the completion rate', "
                "'who hasn't submitted feedback', 'how is participation going'."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_cycles",
            "description": (
                "Fetch all review cycles with id, name, state, deadlines, participant count. "
                "Use when asked: 'list all cycles', 'which cycles are active', "
                "'how many cycles do we have', 'show draft cycles'. "
                "NOT needed when a specific stat question is asked — use get_default_cycle first."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "state": {
                        "type": "string",
                        "description": (
                            "Optional. Filter by state: DRAFT, NOMINATION, FINALIZED, "
                            "ACTIVE, CLOSED, RESULTS_RELEASED, ARCHIVED."
                        ),
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_employees",
            "description": (
                "Fetch employees with name, email, role, department, status. "
                "Use when asked: 'how many employees', 'list engineering team', "
                "'who are the managers', 'headcount by department'. "
                "NOT for task completion or feedback scores — use get_reviewer_tasks or get_scores. "
                "For MANAGER role, automatically scoped to direct reports only."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "role": {
                        "type": "string",
                        "description": "Optional. Filter: EMPLOYEE, MANAGER, HR_ADMIN, SUPER_ADMIN.",
                    },
                    "department": {
                        "type": "string",
                        "description": "Optional. Department name (partial match).",
                    },
                    "status": {
                        "type": "string",
                        "description": "Optional. ACTIVE or INACTIVE. Default ACTIVE.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_nominations",
            "description": (
                "Fetch peer nominations with reviewee, peer, status, cycle. "
                "Use when asked: 'how many nominations are pending', 'who nominated whom', "
                "'approval rate', 'show rejected nominations'. "
                "For MANAGER role, automatically scoped to their team's nominations."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "cycle_id": {"type": "string", "description": "Optional. Filter by cycle ID."},
                    "status": {
                        "type": "string",
                        "description": "Optional. PENDING, APPROVED, or REJECTED.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_reviewer_tasks",
            "description": (
                "Fetch feedback assignments with reviewer, reviewee, status, cycle. "
                "Use when asked: 'who hasn\\'t submitted feedback', 'who is lagging', "
                "'pending reviews', 'how many tasks are incomplete', 'not submitted'. "
                "NOT for headcount — use get_employees for that. "
                "For MANAGER role, automatically scoped to their team's tasks."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "cycle_id": {"type": "string", "description": "Optional. Filter by cycle ID."},
                    "status": {
                        "type": "string",
                        "description": "Optional. ASSIGNED, IN_PROGRESS, SUBMITTED, or LOCKED.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_participation_stats",
            "description": (
                "Get cycle completion statistics: total tasks, submitted, pending, "
                "completion percentage, breakdown by department. "
                "Use when asked: 'what is the completion rate', 'participation stats', "
                "'how many submitted', 'which department is lagging'. "
                "Always call get_default_cycle first if no cycle ID is known. "
                "For MANAGER role, scoped to their team only."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "cycle_id": {"type": "string", "description": "Required. The cycle ID."}
                },
                "required": ["cycle_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_scores",
            "description": (
                "Get aggregated feedback scores per employee: overall, peer, manager, self score. "
                "Use when asked: 'top performers', 'who scored highest', 'bottom performers', "
                "'score comparison', 'who needs improvement', 'department averages'. "
                "Always call get_default_cycle first if no cycle ID is known. "
                "For MANAGER role, scoped to direct reports only."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "cycle_id": {"type": "string", "description": "Required. The cycle ID."},
                    "limit": {
                        "type": "integer",
                        "description": "Optional. Max results. Default 10.",
                    },
                },
                "required": ["cycle_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_announcements",
            "description": (
                "Fetch announcements with message, type (info/warning/success), expiry. "
                "Use when asked: 'what announcements are active', 'any notices', "
                "'show all announcements', 'recent announcements'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "include_inactive": {
                        "type": "boolean",
                        "description": "Optional. Include expired announcements. Default false.",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_templates",
            "description": (
                "Fetch review templates with name, status, section count, question count. "
                "Use when asked: 'how many templates', 'list templates', "
                "'which templates are active', 'template details'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "active_only": {
                        "type": "boolean",
                        "description": "Optional. Only active templates. Default true.",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_audit_logs",
            "description": (
                "Fetch recent system audit log entries (SUPER_ADMIN only). "
                "Use when asked: 'recent system activity', 'who did what', "
                "'what changed recently', 'action history', 'audit trail'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action_type": {
                        "type": "string",
                        "description": "Optional. Filter by action (e.g. CREATE, UPDATE, DELETE).",
                    },
                    "entity_type": {
                        "type": "string",
                        "description": "Optional. Filter by entity (e.g. ReviewCycle, User).",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Optional. Max entries. Default 20.",
                    },
                },
                "required": [],
            },
        },
    },
]


# ── Employee-only tool definitions ────────────────────────────────────────────
# These are self-scoped — the DB queries use the calling user's ID only.

EMPLOYEE_TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "get_my_profile",
            "description": (
                "Get the current user's own profile: scores across cycles, "
                "department, job title. "
                "Use when asked: 'how am I doing', 'what is my score', "
                "'show my performance', 'my results', 'how did I perform'."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_my_pending_tasks",
            "description": (
                "Get the current user's pending reviewer tasks (feedback they still need to write). "
                "Use when asked: 'what do I still need to do', 'my pending reviews', "
                "'who do I need to give feedback to', 'my incomplete tasks'."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_my_nominations",
            "description": (
                "Get the current user's peer nominations: who nominated them and status. "
                "Use when asked: 'who nominated me', 'my nomination status', "
                "'are my nominations approved', 'which peers are reviewing me'."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]


# ── Tool execution ────────────────────────────────────────────────────────────

def execute_tool(name: str, arguments: dict, user) -> str:
    """Execute a named tool and return the result as a JSON string."""
    user_role  = getattr(user, 'role', '')
    user_id    = str(user.id)
    manager_id = user_id if user_role == 'MANAGER' else None
    is_super   = user_role in ('SUPER_ADMIN', 'HR_ADMIN')

    try:
        if name == 'get_default_cycle':
            return _get_default_cycle()
        if name == 'get_cycles':
            return _get_cycles(arguments.get('state'))
        if name == 'get_employees':
            return _get_employees(
                arguments.get('role'),
                arguments.get('department'),
                arguments.get('status', 'ACTIVE'),
                manager_id,
            )
        if name == 'get_nominations':
            return _get_nominations(
                arguments.get('cycle_id'),
                arguments.get('status'),
                manager_id,
            )
        if name == 'get_reviewer_tasks':
            return _get_reviewer_tasks(
                arguments.get('cycle_id'),
                arguments.get('status'),
                manager_id,
            )
        if name == 'get_participation_stats':
            return _get_participation_stats(arguments.get('cycle_id', ''), manager_id)
        if name == 'get_scores':
            return _get_scores(
                arguments.get('cycle_id', ''),
                arguments.get('limit', 10),
                manager_id,
            )
        if name == 'get_announcements':
            return _get_announcements(arguments.get('include_inactive', False))
        if name == 'get_templates':
            return _get_templates(arguments.get('active_only', True))
        if name == 'get_audit_logs':
            if not is_super:
                return json.dumps({"error": "Audit logs are only available to SUPER_ADMIN."})
            return _get_audit_logs(
                arguments.get('action_type'),
                arguments.get('entity_type'),
                arguments.get('limit', 20),
            )
        # Employee self-scoped tools
        if name == 'get_my_profile':
            return _get_my_profile(user_id)
        if name == 'get_my_pending_tasks':
            return _get_my_pending_tasks(user_id)
        if name == 'get_my_nominations':
            return _get_my_nominations(user_id)

        return json.dumps({"error": f"Unknown tool: {name}"})
    except Exception as exc:
        return json.dumps({"error": str(exc)})


# ── DB query implementations ──────────────────────────────────────────────────

def _get_default_cycle():
    """Returns the most relevant cycle: ACTIVE first, then most recent CLOSED."""
    with connection.cursor() as cur:
        cur.execute("""
            SELECT id, name, state, review_deadline
            FROM review_cycles
            WHERE state = 'ACTIVE'
            ORDER BY created_at DESC LIMIT 1
        """)
        row = cur.fetchone()
        if not row:
            cur.execute("""
                SELECT id, name, state, review_deadline
                FROM review_cycles
                WHERE state IN ('CLOSED', 'RESULTS_RELEASED')
                ORDER BY created_at DESC LIMIT 1
            """)
            row = cur.fetchone()
        if not row:
            cur.execute("""
                SELECT id, name, state, review_deadline
                FROM review_cycles
                ORDER BY created_at DESC LIMIT 1
            """)
            row = cur.fetchone()
    if not row:
        return json.dumps({"error": "No cycles found in the system."})
    return json.dumps({
        "cycle_id":       str(row[0]),
        "cycle_name":     row[1],
        "state":          row[2],
        "review_deadline": str(row[3]) if row[3] else None,
        "note": "This is the most relevant cycle. Use cycle_id when calling other tools.",
    })


def _get_cycles(state=None):
    sql = """
        SELECT rc.id, rc.name, rc.state,
               rc.review_deadline, rc.nomination_deadline,
               (SELECT COUNT(*) FROM cycle_participants WHERE cycle_id = rc.id) AS participant_count
        FROM review_cycles rc
        {where}
        ORDER BY rc.created_at DESC LIMIT 20
    """.format(where="WHERE rc.state = %s" if state else "")
    with connection.cursor() as cur:
        cur.execute(sql, [state] if state else [])
        cols = ['id', 'name', 'state', 'review_deadline', 'nomination_deadline', 'participant_count']
        rows = []
        for row in cur.fetchall():
            d = dict(zip(cols, row))
            d['id'] = str(d['id'])
            d['review_deadline'] = str(d['review_deadline']) if d['review_deadline'] else None
            d['nomination_deadline'] = str(d['nomination_deadline']) if d['nomination_deadline'] else None
            rows.append(d)
    return json.dumps({"cycles": rows, "total": len(rows)})


def _get_employees(role=None, department=None, status='ACTIVE', manager_id=None):
    if manager_id:
        params = [manager_id, status or 'ACTIVE']
        extra = ""
        if role:
            extra += " AND u.role = %s"
            params.append(role)
        if department:
            extra += " AND d.name ILIKE %s"
            params.append(f'%{department}%')
        sql = f"""
            SELECT u.id, u.first_name || ' ' || u.last_name AS name,
                   u.email, u.role, u.status, d.name AS department
            FROM users u
            JOIN org_hierarchy oh ON oh.employee_id = u.id AND oh.manager_id = %s
            LEFT JOIN departments d ON u.department_id = d.id
            WHERE u.status = %s {extra}
            ORDER BY u.first_name LIMIT 100
        """
        with connection.cursor() as cur:
            cur.execute(sql, params)
            cols = ['id', 'name', 'email', 'role', 'status', 'department']
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
            for r in rows:
                r['id'] = str(r['id'])
        return json.dumps({"employees": rows, "total": len(rows)})

    params = [status or 'ACTIVE']
    extra = ""
    if role:
        extra += " AND u.role = %s"
        params.append(role)
    if department:
        extra += " AND d.name ILIKE %s"
        params.append(f'%{department}%')
    sql = f"""
        SELECT u.id, u.first_name || ' ' || u.last_name AS name,
               u.email, u.role, u.status, d.name AS department
        FROM users u
        LEFT JOIN departments d ON u.department_id = d.id
        WHERE u.status = %s {extra}
        ORDER BY u.first_name LIMIT 100
    """
    with connection.cursor() as cur:
        cur.execute(sql, params)
        cols = ['id', 'name', 'email', 'role', 'status', 'department']
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        for r in rows:
            r['id'] = str(r['id'])
    return json.dumps({"employees": rows, "total": len(rows)})


def _get_nominations(cycle_id=None, status=None, manager_id=None):
    params = []
    extra = ""
    if cycle_id:
        extra += " AND pn.cycle_id = %s"
        params.append(cycle_id)
    if status:
        extra += " AND pn.status = %s"
        params.append(status)
    if manager_id:
        extra += " AND pn.reviewee_id IN (SELECT employee_id FROM org_hierarchy WHERE manager_id = %s)"
        params.append(manager_id)
    sql = f"""
        SELECT pn.id,
               ur.first_name || ' ' || ur.last_name AS reviewee,
               up.first_name || ' ' || up.last_name AS peer,
               pn.status, rc.name AS cycle
        FROM peer_nominations pn
        JOIN users ur ON pn.reviewee_id = ur.id
        JOIN users up ON pn.peer_id     = up.id
        JOIN review_cycles rc ON pn.cycle_id = rc.id
        WHERE 1=1 {extra}
        ORDER BY rc.created_at DESC LIMIT 200
    """
    with connection.cursor() as cur:
        cur.execute(sql, params)
        cols = ['id', 'reviewee', 'peer', 'status', 'cycle']
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        for r in rows:
            r['id'] = str(r['id'])
    return json.dumps({"nominations": rows, "total": len(rows)})


def _get_reviewer_tasks(cycle_id=None, status=None, manager_id=None):
    params = []
    extra = ""
    if cycle_id:
        extra += " AND rt.cycle_id = %s"
        params.append(cycle_id)
    if status:
        extra += " AND rt.status = %s"
        params.append(status)
    if manager_id:
        extra += " AND rt.reviewee_id IN (SELECT employee_id FROM org_hierarchy WHERE manager_id = %s)"
        params.append(manager_id)
    sql = f"""
        SELECT rt.id,
               ur.first_name || ' ' || ur.last_name AS reviewer,
               ue.first_name || ' ' || ue.last_name AS reviewee,
               rt.status, rc.name AS cycle
        FROM reviewer_tasks rt
        JOIN users ur ON rt.reviewer_id = ur.id
        JOIN users ue ON rt.reviewee_id = ue.id
        JOIN review_cycles rc ON rt.cycle_id = rc.id
        WHERE 1=1 {extra}
        ORDER BY rc.created_at DESC LIMIT 200
    """
    with connection.cursor() as cur:
        cur.execute(sql, params)
        cols = ['id', 'reviewer', 'reviewee', 'status', 'cycle']
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        for r in rows:
            r['id'] = str(r['id'])
    return json.dumps({"tasks": rows, "total": len(rows)})


def _get_participation_stats(cycle_id: str, manager_id=None):
    team_filter = ""
    team_extra = []
    if manager_id:
        team_filter = " AND rt.reviewee_id IN (SELECT employee_id FROM org_hierarchy WHERE manager_id = %s)"
        team_extra = [manager_id]
    with connection.cursor() as cur:
        cur.execute(f"""
            SELECT COUNT(*),
                   SUM(CASE WHEN rt.status = 'SUBMITTED' THEN 1 ELSE 0 END),
                   SUM(CASE WHEN rt.status != 'SUBMITTED' THEN 1 ELSE 0 END)
            FROM reviewer_tasks rt WHERE rt.cycle_id = %s {team_filter}
        """, [cycle_id] + team_extra)
        row = cur.fetchone() or (0, 0, 0)
        total     = int(row[0] or 0)
        submitted = int(row[1] or 0)
        pending   = int(row[2] or 0)

        cur.execute(f"""
            SELECT d.name, COUNT(*),
                   SUM(CASE WHEN rt.status = 'SUBMITTED' THEN 1 ELSE 0 END)
            FROM reviewer_tasks rt
            JOIN users u ON rt.reviewer_id = u.id
            LEFT JOIN departments d ON u.department_id = d.id
            WHERE rt.cycle_id = %s {team_filter}
            GROUP BY d.name ORDER BY COUNT(*) DESC
        """, [cycle_id] + team_extra)
        by_dept = [
            {
                "department":     r[0] or "Unassigned",
                "total":          int(r[1]),
                "submitted":      int(r[2] or 0),
                "completion_pct": round(int(r[2] or 0) / int(r[1]) * 100, 1) if r[1] else 0,
            }
            for r in cur.fetchall()
        ]
    return json.dumps({
        "cycle_id":              cycle_id,
        "total_tasks":           total,
        "submitted":             submitted,
        "pending":               pending,
        "completion_percentage": round(submitted / total * 100, 1) if total else 0,
        "by_department":         by_dept,
    })


def _get_scores(cycle_id: str, limit: int = 10, manager_id=None):
    team_filter = ""
    params = [cycle_id]
    if manager_id:
        team_filter = " AND ar.reviewee_id IN (SELECT employee_id FROM org_hierarchy WHERE manager_id = %s)"
        params.append(manager_id)
    params.append(int(limit))
    sql = f"""
        SELECT u.first_name || ' ' || u.last_name AS employee,
               d.name AS department,
               ar.overall_score, ar.peer_score, ar.manager_score, ar.self_score
        FROM aggregated_results ar
        JOIN users u ON ar.reviewee_id = u.id
        LEFT JOIN departments d ON u.department_id = d.id
        WHERE ar.cycle_id = %s {team_filter}
        ORDER BY ar.overall_score DESC NULLS LAST
        LIMIT %s
    """
    with connection.cursor() as cur:
        cur.execute(sql, params)
        cols = ['employee', 'department', 'overall_score', 'peer_score', 'manager_score', 'self_score']
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    return json.dumps({"scores": rows, "total": len(rows)})


def _get_announcements(include_inactive: bool = False):
    where = "" if include_inactive else \
        "WHERE a.is_active = TRUE AND (a.expires_at IS NULL OR a.expires_at > NOW())"
    sql = f"""
        SELECT a.id, a.message, a.type, a.is_active, a.expires_at, a.created_at,
               u.first_name || ' ' || u.last_name AS created_by
        FROM announcements a
        LEFT JOIN users u ON a.created_by_id = u.id
        {where}
        ORDER BY a.created_at DESC LIMIT 20
    """
    with connection.cursor() as cur:
        cur.execute(sql)
        cols = ['id', 'message', 'type', 'is_active', 'expires_at', 'created_at', 'created_by']
        rows = []
        for row in cur.fetchall():
            d = dict(zip(cols, row))
            d['id'] = str(d['id'])
            d['expires_at'] = str(d['expires_at']) if d['expires_at'] else None
            d['created_at'] = str(d['created_at'])
            rows.append(d)
    return json.dumps({"announcements": rows, "total": len(rows)})


def _get_templates(active_only: bool = True):
    where = "WHERE rt.is_active = TRUE" if active_only else ""
    sql = f"""
        SELECT rt.id, rt.name, rt.is_active, rt.created_at,
               (SELECT COUNT(*) FROM template_sections ts WHERE ts.template_id = rt.id) AS section_count,
               (SELECT COUNT(*) FROM template_questions tq
                JOIN template_sections ts ON tq.section_id = ts.id
                WHERE ts.template_id = rt.id) AS question_count
        FROM review_templates rt
        {where}
        ORDER BY rt.created_at DESC LIMIT 20
    """
    with connection.cursor() as cur:
        cur.execute(sql)
        cols = ['id', 'name', 'is_active', 'created_at', 'section_count', 'question_count']
        rows = []
        for row in cur.fetchall():
            d = dict(zip(cols, row))
            d['id'] = str(d['id'])
            d['created_at'] = str(d['created_at'])
            rows.append(d)
    return json.dumps({"templates": rows, "total": len(rows)})


def _get_audit_logs(action_type=None, entity_type=None, limit: int = 20):
    params = []
    extra = ""
    if action_type:
        extra += " AND al.action_type ILIKE %s"
        params.append(f'%{action_type}%')
    if entity_type:
        extra += " AND al.entity_type ILIKE %s"
        params.append(f'%{entity_type}%')
    params.append(int(limit))
    sql = f"""
        SELECT al.action_type, al.entity_type, al.created_at,
               u.first_name || ' ' || u.last_name AS actor,
               u.email AS actor_email
        FROM audit_logs al
        LEFT JOIN users u ON al.actor_id = u.id
        WHERE 1=1 {extra}
        ORDER BY al.created_at DESC LIMIT %s
    """
    with connection.cursor() as cur:
        cur.execute(sql, params)
        cols = ['action_type', 'entity_type', 'created_at', 'actor', 'actor_email']
        rows = []
        for row in cur.fetchall():
            d = dict(zip(cols, row))
            d['created_at'] = str(d['created_at'])
            rows.append(d)
    return json.dumps({"audit_logs": rows, "total": len(rows)})


# ── Employee self-scoped tool implementations ─────────────────────────────────

def _get_my_profile(user_id: str):
    with connection.cursor() as cur:
        cur.execute("""
            SELECT u.first_name || ' ' || u.last_name, u.email,
                   u.job_title, d.name AS department, u.role
            FROM users u
            LEFT JOIN departments d ON u.department_id = d.id
            WHERE u.id = %s
        """, [user_id])
        row = cur.fetchone()
        if not row:
            return json.dumps({"error": "User not found."})
        name, email, job_title, dept, role = row

        cur.execute("""
            SELECT rc.name, ar.overall_score, ar.peer_score,
                   ar.manager_score, ar.self_score, ar.computed_at
            FROM aggregated_results ar
            JOIN review_cycles rc ON ar.cycle_id = rc.id
            WHERE ar.reviewee_id = %s
            ORDER BY ar.computed_at DESC LIMIT 5
        """, [user_id])
        cycles = [
            {
                "cycle":          r[0],
                "overall_score":  float(r[1]) if r[1] else None,
                "peer_score":     float(r[2]) if r[2] else None,
                "manager_score":  float(r[3]) if r[3] else None,
                "self_score":     float(r[4]) if r[4] else None,
            }
            for r in cur.fetchall()
        ]
    return json.dumps({
        "name": name, "email": email, "role": role,
        "job_title": job_title, "department": dept,
        "my_scores": cycles,
    })


def _get_my_pending_tasks(user_id: str):
    with connection.cursor() as cur:
        cur.execute("""
            SELECT ue.first_name || ' ' || ue.last_name AS reviewee,
                   rt.status, rc.name AS cycle, rc.review_deadline
            FROM reviewer_tasks rt
            JOIN users ue ON rt.reviewee_id = ue.id
            JOIN review_cycles rc ON rt.cycle_id = rc.id
            WHERE rt.reviewer_id = %s AND rt.status != 'SUBMITTED'
            ORDER BY rc.review_deadline ASC LIMIT 20
        """, [user_id])
        cols = ['reviewee', 'status', 'cycle', 'deadline']
        rows = []
        for row in cur.fetchall():
            d = dict(zip(cols, row))
            d['deadline'] = str(d['deadline']) if d['deadline'] else None
            rows.append(d)
    return json.dumps({"pending_tasks": rows, "total": len(rows)})


def _get_my_nominations(user_id: str):
    with connection.cursor() as cur:
        cur.execute("""
            SELECT up.first_name || ' ' || up.last_name AS peer,
                   pn.status, rc.name AS cycle
            FROM peer_nominations pn
            JOIN users up ON pn.peer_id = up.id
            JOIN review_cycles rc ON pn.cycle_id = rc.id
            WHERE pn.reviewee_id = %s
            ORDER BY rc.created_at DESC LIMIT 20
        """, [user_id])
        cols = ['peer', 'status', 'cycle']
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    return json.dumps({"my_nominations": rows, "total": len(rows)})


# ── Routing helpers ───────────────────────────────────────────────────────────

_AGENT_PATTERN = re.compile(
    r'\b(how many|which|compare|list|find|count|who has|who have|'
    r'most|least|highest|lowest|average|total|never|between|across|'
    r'breakdown|versus|vs\.?|differ|rank|top \d|bottom \d|percent|'
    r'rate|haven.t|not submitted|still pending|lagging|behind|'
    r'department|employees? in|cycles? with|never participated|'
    r'announcements?|templates?|audit|activity|recent actions?)\b',
    re.IGNORECASE,
)

_EMPLOYEE_SELF_PATTERN = re.compile(
    r'\b(my score|my performance|my result|how am i|how did i|'
    r'my feedback|my rating|my pending|what do i still|'
    r'who nominated me|my nomination|am i doing|my progress)\b',
    re.IGNORECASE,
)


def is_agent_question(message: str) -> bool:
    """Return True if the message looks like a data/analytics query for admin/manager agent."""
    return bool(_AGENT_PATTERN.search(message))


def is_employee_self_query(message: str) -> bool:
    """Return True if an EMPLOYEE is asking about their own data in natural language."""
    return bool(_EMPLOYEE_SELF_PATTERN.search(message))


# ── Follow-up question detection ──────────────────────────────────────────────

_FOLLOWUP_PATTERN = re.compile(
    # Ordinal/positional references: "the first one", "task 2", "the second task"
    r'\b(the )?(first|second|third|fourth|fifth|last|1st|2nd|3rd|4th|5th)\b'
    r'|\btask\s?[0-9]\b'
    r'|\bnumber\s?[0-9]\b'
    r'|\bitem\s?[0-9]\b'
    # Pronoun references to previous answer
    r'|\b(that|this|it|those|them|these)\s+(one|task|cycle|nomination|deadline|review|person|employee|result)\b'
    r'|\b(that|this|those|them)\s+(above|one|result|item)\b'
    # "above", "below", "mentioned" references
    r'|\b(above|below|mentioned|listed|shown|previous)\b'
    # Follow-up question starters
    r'|\band (what|when|who|how|why|which|where)\b'
    r'|\bwhat (about|is the deadline for|is the due date|is their score)\b'
    r'|\bhow (urgent|important|many days|much time) (is|are|left|remaining|do i)\b'
    # "tell me more", "more details", "explain"
    r'|\b(tell me more|more details|more about|elaborate|explain (that|this|it|more))\b'
    # "which one should I", "can I submit it"
    r'|\bwhich (one|task|should|is)\b'
    r'|\b(can|should|do) i (do|submit|complete|finish|start) (it|that|this|the|one)\b',
    re.IGNORECASE,
)


def is_followup_question(message: str, chat_history: list) -> bool:
    """
    Return True if:
    1. The message contains reference words pointing to a previous response
    2. There is actual chat history to reference

    Used to route follow-up questions to the agent so it can use
    conversation history to answer contextually.
    """
    if not chat_history:
        return False
    # Only trigger if there's at least one assistant response in history
    has_prev_response = any(e.get("role") == "assistant" for e in chat_history)
    if not has_prev_response:
        return False
    return bool(_FOLLOWUP_PATTERN.search(message))

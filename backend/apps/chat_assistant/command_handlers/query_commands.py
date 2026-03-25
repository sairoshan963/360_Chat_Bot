"""
Query commands — retrieve data, no confirmation needed.
"""
import logging
from django.db import connection
from django.utils import timezone


def _fmt_date(dt):
    """Format a date-only field (DateField) to a readable string. No time, no timezone issue."""
    if not dt:
        return "N/A"
    try:
        return dt.strftime("%d %b %Y")
    except Exception:
        return str(dt)[:10]

def _iso(dt):
    """Return ISO 8601 string for datetime fields. Frontend formats in user's local timezone."""
    if not dt:
        return None
    try:
        return dt.isoformat()
    except Exception:
        return str(dt)
from .base import BaseCommand, db_uuid

logger = logging.getLogger(__name__)


class ShowMyFeedbackCommand(BaseCommand):
    allowed_roles = ['EMPLOYEE', 'MANAGER', 'HR_ADMIN', 'SUPER_ADMIN']
    requires_confirmation = False

    def execute(self, parameters: dict, user) -> dict:
        try:
            with connection.cursor() as cursor:
                # Only show results for cycles where results have been officially released
                # — matches the same rule enforced by the UI's get_my_report service
                cursor.execute("""
                    SELECT rc.name, ar.overall_score, ar.peer_score,
                           ar.self_score, ar.manager_score, rc.state
                    FROM aggregated_results ar
                    JOIN review_cycles rc ON ar.cycle_id = rc.id
                    WHERE ar.reviewee_id = %s
                      AND rc.state IN ('RESULTS_RELEASED', 'ARCHIVED')
                    ORDER BY rc.created_at DESC
                """, [db_uuid(user.id)])
                rows = cursor.fetchall()

            if not rows:
                return {
                    "success": True,
                    "message": "No released feedback results yet. Results become visible once HR releases them.",
                    "data": {"results": []}
                }

            results = [
                {
                    "cycle":          r[0],
                    "overall_score":  float(r[1]) if r[1] else None,
                    "peer_score":     float(r[2]) if r[2] else None,
                    "self_score":     float(r[3]) if r[3] else None,
                    "manager_score":  float(r[4]) if r[4] else None,
                    "state":          r[5],
                }
                for r in rows
            ]
            return {
                "success": True,
                "message": f"Here are your released feedback results across {len(results)} cycle(s).",
                "data": {"results": results}
            }
        except Exception as e:
            logger.error(f"ShowMyFeedbackCommand error: {e}")
            return {"success": False, "message": "Could not retrieve your feedback. Please try again.", "data": {}}


class ShowMyReportCommand(BaseCommand):
    """Show the user's performance report summary for their most recent released cycle."""
    allowed_roles         = ['EMPLOYEE', 'MANAGER', 'HR_ADMIN', 'SUPER_ADMIN']
    requires_confirmation = False

    def execute(self, parameters: dict, user) -> dict:
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT rc.id, rc.name, ar.overall_score, ar.peer_score,
                           ar.self_score, ar.manager_score, rc.state
                    FROM aggregated_results ar
                    JOIN review_cycles rc ON ar.cycle_id = rc.id
                    WHERE ar.reviewee_id = %s
                      AND rc.state IN ('RESULTS_RELEASED', 'ARCHIVED')
                    ORDER BY rc.created_at DESC
                    LIMIT 1
                """, [db_uuid(user.id)])
                row = cursor.fetchone()

            if not row:
                return {
                    "success": True,
                    "message": (
                        "No released performance reports yet. "
                        "Results become visible once HR releases them for a cycle you participated in."
                    ),
                    "data": {"results": []}
                }

            cycle_id, cycle_name, overall, peer, self_s, manager, state = row

            def fmt_score(s):
                return f"{float(s):.1f}" if s is not None else "—"

            score_line = (
                f"Overall: **{fmt_score(overall)}**"
                + (f"  |  Peer: {fmt_score(peer)}" if peer is not None else "")
                + (f"  |  Self: {fmt_score(self_s)}" if self_s is not None else "")
                + (f"  |  Manager: {fmt_score(manager)}" if manager is not None else "")
            )

            message = (
                f"Your performance report for **{cycle_name}**:\n"
                f"{score_line}\n\n"
                "For the full breakdown with written feedback, visit your **My Report** page."
            )

            return {
                "success": True,
                "message": message,
                "data": {
                    "results": [{
                        "cycle":         cycle_name,
                        "overall_score": float(overall) if overall else None,
                        "peer_score":    float(peer)    if peer    else None,
                        "self_score":    float(self_s)  if self_s  else None,
                        "manager_score": float(manager) if manager else None,
                        "state":         state,
                    }],
                    "report_url": "/employee/report",
                }
            }
        except Exception as e:
            logger.error(f"ShowMyReportCommand error: {e}")
            return {"success": False, "message": "Could not retrieve your report. Please try again.", "data": {}}


class ShowPendingReviewsCommand(BaseCommand):
    allowed_roles = ['MANAGER', 'HR_ADMIN', 'SUPER_ADMIN', 'EMPLOYEE']
    requires_confirmation = False

    def execute(self, parameters: dict, user) -> dict:
        try:
            with connection.cursor() as cursor:
                # Filter by cycle state to match the UI service get_my_tasks() which uses
                # cycle__state__in=['ACTIVE', 'CLOSED', 'RESULTS_RELEASED']
                cursor.execute("""
                    SELECT u.first_name || ' ' || u.last_name AS reviewee,
                           rc.name AS cycle, rc.state AS cycle_state,
                           rt.status, rt.reviewer_type
                    FROM reviewer_tasks rt
                    JOIN users u ON rt.reviewee_id = u.id
                    JOIN review_cycles rc ON rt.cycle_id = rc.id
                    WHERE rt.reviewer_id = %s
                      AND rt.status IN ('CREATED', 'PENDING', 'IN_PROGRESS')
                      AND rc.state IN ('ACTIVE', 'CLOSED', 'RESULTS_RELEASED')
                    ORDER BY rc.created_at DESC, u.first_name
                """, [db_uuid(user.id)])
                rows = cursor.fetchall()

            if not rows:
                return {"success": True, "message": "You have no pending reviews.", "data": {"grouped_tasks": []}}

            grouped = {}
            for r in rows:
                cycle = r[1]
                if cycle not in grouped:
                    grouped[cycle] = {"cycle": cycle, "state": r[2], "tasks": []}
                grouped[cycle]["tasks"].append({"reviewee": r[0], "status": r[3], "reviewer_type": r[4]})

            grouped_list = list(grouped.values())
            total = sum(len(g["tasks"]) for g in grouped_list)
            return {
                "success": True,
                "message": f"You have {total} pending review(s) across {len(grouped_list)} cycle(s).",
                "data": {"grouped_tasks": grouped_list}
            }
        except Exception as e:
            logger.error(f"ShowPendingReviewsCommand error: {e}")
            return {"success": False, "message": "Could not retrieve pending reviews.", "data": {}}


class ShowCycleStatusCommand(BaseCommand):
    allowed_roles = ['HR_ADMIN', 'SUPER_ADMIN', 'MANAGER']
    requires_confirmation = False

    def execute(self, parameters: dict, user) -> dict:
        try:
            cycle_name = parameters.get('cycle_name', '')
            with connection.cursor() as cursor:
                if user.role in ('HR_ADMIN', 'SUPER_ADMIN'):
                    # HR/Admin: see all cycles org-wide
                    if cycle_name:
                        cursor.execute("""
                            SELECT name, state, review_deadline, nomination_deadline
                            FROM review_cycles
                            WHERE LOWER(name) LIKE %s
                            ORDER BY created_at DESC
                        """, [f'%{cycle_name.lower()}%'])
                    else:
                        cursor.execute("""
                            SELECT name, state, review_deadline, nomination_deadline
                            FROM review_cycles
                            ORDER BY created_at DESC
                        """)
                else:
                    # Manager: only cycles where they or their direct reports participate
                    if cycle_name:
                        cursor.execute("""
                            SELECT rc.name, rc.state, rc.review_deadline, rc.nomination_deadline
                            FROM review_cycles rc
                            WHERE rc.id IN (
                                SELECT DISTINCT cp.cycle_id FROM cycle_participants cp
                                WHERE cp.user_id = %s
                                   OR cp.user_id IN (
                                       SELECT employee_id FROM org_hierarchy WHERE manager_id = %s
                                   )
                            )
                            AND LOWER(rc.name) LIKE %s
                            ORDER BY rc.created_at DESC
                        """, [db_uuid(user.id), db_uuid(user.id), f'%{cycle_name.lower()}%'])
                    else:
                        cursor.execute("""
                            SELECT rc.name, rc.state, rc.review_deadline, rc.nomination_deadline
                            FROM review_cycles rc
                            WHERE rc.id IN (
                                SELECT DISTINCT cp.cycle_id FROM cycle_participants cp
                                WHERE cp.user_id = %s
                                   OR cp.user_id IN (
                                       SELECT employee_id FROM org_hierarchy WHERE manager_id = %s
                                   )
                            )
                            ORDER BY rc.created_at DESC
                        """, [db_uuid(user.id), db_uuid(user.id)])
                rows = cursor.fetchall()

            if not rows:
                return {"success": True, "message": "No cycles found.", "data": {"cycles": []}}

            cycles = [
                {
                    "name":                r[0],
                    "state":               r[1],
                    "review_deadline":     _fmt_date(r[2]),
                    "nomination_deadline": _fmt_date(r[3]) if r[3] else None,
                }
                for r in rows
            ]
            return {
                "success": True,
                "message": f"Found {len(cycles)} cycle(s).",
                "data": {"cycles": cycles}
            }
        except Exception as e:
            logger.error(f"ShowCycleStatusCommand error: {e}")
            return {"success": False, "message": "Could not retrieve cycle status.", "data": {}}


class ShowTeamSummaryCommand(BaseCommand):
    allowed_roles = ['MANAGER', 'HR_ADMIN', 'SUPER_ADMIN']
    requires_confirmation = False

    def execute(self, parameters: dict, user) -> dict:
        try:
            with connection.cursor() as cursor:
                # Mirror the Manager Dashboard page which shows team tasks
                # only for cycles in ACTIVE, CLOSED, RESULTS_RELEASED, or ARCHIVED state
                cursor.execute("""
                    SELECT u.first_name || ' ' || u.last_name AS name,
                           COUNT(rt.id) AS total_tasks,
                           COUNT(CASE WHEN rt.status = 'SUBMITTED' THEN 1 END) AS submitted
                    FROM users u
                    JOIN org_hierarchy oh ON oh.employee_id = u.id
                    LEFT JOIN reviewer_tasks rt ON rt.reviewer_id = u.id
                        AND rt.cycle_id IN (
                            SELECT id FROM review_cycles
                            WHERE state IN ('ACTIVE', 'CLOSED', 'RESULTS_RELEASED', 'ARCHIVED')
                        )
                    WHERE oh.manager_id = %s
                    GROUP BY u.id, u.first_name, u.last_name
                """, [db_uuid(user.id)])
                rows = cursor.fetchall()

            if not rows:
                return {"success": True, "message": "No direct reports found.", "data": {"team": []}}

            team = [{"name": r[0], "total_tasks": r[1], "submitted": r[2]} for r in rows]
            return {
                "success": True,
                "message": f"Team summary for {len(team)} direct report(s).",
                "data": {"team": team}
            }
        except Exception as e:
            logger.error(f"ShowTeamSummaryCommand error: {e}")
            return {"success": False, "message": "Could not retrieve team summary.", "data": {}}


class ShowParticipationCommand(BaseCommand):
    allowed_roles = ['HR_ADMIN', 'SUPER_ADMIN']
    requires_confirmation = False

    def execute(self, parameters: dict, user) -> dict:
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT rc.name, rc.state,
                           COUNT(rt.id) AS total,
                           COUNT(CASE WHEN rt.status = 'SUBMITTED' THEN 1 END) AS submitted,
                           ROUND(
                               COUNT(CASE WHEN rt.status = 'SUBMITTED' THEN 1 END) * 100.0
                               / NULLIF(COUNT(rt.id), 0), 1
                           ) AS completion_pct
                    FROM review_cycles rc
                    LEFT JOIN reviewer_tasks rt ON rt.cycle_id = rc.id
                    WHERE rc.state IN ('ACTIVE', 'CLOSED', 'RESULTS_RELEASED')
                    GROUP BY rc.id, rc.name, rc.state
                    ORDER BY rc.created_at DESC
                """)
                rows = cursor.fetchall()

            if not rows:
                return {"success": True, "message": "No cycles with participation data found.", "data": {"participation": []}}

            participation = [
                {"cycle": r[0], "state": r[1], "total": r[2], "submitted": r[3], "completion_pct": float(r[4] or 0)}
                for r in rows
            ]
            return {
                "success": True,
                "message": f"Participation stats for {len(participation)} cycle(s).",
                "data": {"participation": participation}
            }
        except Exception as e:
            logger.error(f"ShowParticipationCommand error: {e}")
            return {"success": False, "message": "Could not retrieve participation stats.", "data": {}}


class ShowMyTasksCommand(BaseCommand):
    allowed_roles = ['EMPLOYEE', 'MANAGER', 'HR_ADMIN', 'SUPER_ADMIN']
    requires_confirmation = False

    def execute(self, parameters: dict, user) -> dict:
        try:
            with connection.cursor() as cursor:
                # Filter by cycle state to match the UI service get_my_tasks() which uses
                # cycle__state__in=['ACTIVE', 'CLOSED', 'RESULTS_RELEASED']
                cursor.execute("""
                    SELECT u.first_name || ' ' || u.last_name AS reviewee,
                           rc.name AS cycle, rc.state AS cycle_state,
                           rt.status, rt.reviewer_type
                    FROM reviewer_tasks rt
                    JOIN users u ON rt.reviewee_id = u.id
                    JOIN review_cycles rc ON rt.cycle_id = rc.id
                    WHERE rt.reviewer_id = %s
                      AND rc.state IN ('ACTIVE', 'CLOSED', 'RESULTS_RELEASED')
                    ORDER BY rc.created_at DESC, u.first_name
                """, [db_uuid(user.id)])
                rows = cursor.fetchall()

            if not rows:
                return {"success": True, "message": "You have no assigned tasks in any cycle.", "data": {"grouped_tasks": []}}

            grouped = {}
            for r in rows:
                cycle = r[1]
                if cycle not in grouped:
                    grouped[cycle] = {"cycle": cycle, "state": r[2], "tasks": []}
                grouped[cycle]["tasks"].append({"reviewee": r[0], "status": r[3], "reviewer_type": r[4]})

            grouped_list = list(grouped.values())
            total = sum(len(g["tasks"]) for g in grouped_list)
            return {
                "success": True,
                "message": f"You have {total} task(s) across {len(grouped_list)} cycle(s).",
                "data": {"grouped_tasks": grouped_list}
            }
        except Exception as e:
            logger.error(f"ShowMyTasksCommand error: {e}")
            return {"success": False, "message": "Could not retrieve your tasks.", "data": {}}


class ShowCycleDeadlinesCommand(BaseCommand):
    allowed_roles = ['HR_ADMIN', 'SUPER_ADMIN', 'MANAGER', 'EMPLOYEE']
    requires_confirmation = False

    def execute(self, parameters: dict, user) -> dict:
        try:
            with connection.cursor() as cursor:
                if user.role in ('HR_ADMIN', 'SUPER_ADMIN'):
                    # HR/Super Admin: see all cycles with deadlines (like HR Cycles page)
                    cursor.execute("""
                        SELECT name, state, review_deadline, nomination_deadline
                        FROM review_cycles
                        WHERE state IN ('ACTIVE', 'NOMINATION', 'FINALIZED')
                        ORDER BY review_deadline ASC
                    """)
                else:
                    # Employee/Manager: only see deadlines for cycles they participate in
                    # — matches what My Tasks page shows (the Due column)
                    cursor.execute("""
                        SELECT DISTINCT rc.name, rc.state, rc.review_deadline, rc.nomination_deadline
                        FROM review_cycles rc
                        JOIN cycle_participants cp ON cp.cycle_id = rc.id
                        WHERE cp.user_id = %s
                          AND rc.state IN ('ACTIVE', 'NOMINATION', 'FINALIZED')
                        ORDER BY rc.review_deadline ASC
                    """, [db_uuid(user.id)])
                rows = cursor.fetchall()

            if not rows:
                return {"success": True, "message": "No upcoming deadlines found.", "data": {"deadlines": []}}

            deadlines = [
                {
                    "cycle":                r[0],
                    "state":                r[1],
                    "deadline":             _fmt_date(r[2]),
                    "nomination_deadline":  _fmt_date(r[3]) if r[3] else None,
                }
                for r in rows
            ]
            return {
                "success": True,
                "message": f"Found {len(deadlines)} upcoming deadline(s).",
                "data": {"deadlines": deadlines}
            }
        except Exception as e:
            logger.error(f"ShowCycleDeadlinesCommand error: {e}")
            return {"success": False, "message": "Could not retrieve deadlines.", "data": {}}


class ShowMyNominationsCommand(BaseCommand):
    """Show the current user's peer nominations grouped by cycle."""
    allowed_roles = ['EMPLOYEE', 'MANAGER', 'HR_ADMIN', 'SUPER_ADMIN']
    requires_confirmation = False

    def execute(self, parameters: dict, user) -> dict:
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT DISTINCT u.first_name || ' ' || u.last_name AS peer,
                           u.email, rc.name AS cycle, pn.status, pn.rejection_note,
                           rc.created_at
                    FROM peer_nominations pn
                    JOIN users u ON pn.peer_id = u.id
                    JOIN review_cycles rc ON pn.cycle_id = rc.id
                    WHERE pn.reviewee_id = %s
                      AND rc.state != 'DRAFT'
                      AND EXISTS (
                          SELECT 1 FROM cycle_participants cp
                          WHERE cp.cycle_id = rc.id AND cp.user_id = %s
                      )
                    ORDER BY rc.created_at DESC, peer
                """, [db_uuid(user.id), db_uuid(user.id)])
                rows = cursor.fetchall()

            if not rows:
                return {"success": True, "message": "You haven't nominated any peers yet.", "data": {"grouped_nominations": []}}

            grouped = {}
            for r in rows:
                cycle = r[2]
                if cycle not in grouped:
                    grouped[cycle] = {"cycle": cycle, "nominations": []}
                nom = {"peer": r[0], "email": r[1], "status": r[3]}
                if r[4]:  # only include rejection_note when present
                    nom["rejection_note"] = r[4]
                grouped[cycle]["nominations"].append(nom)

            grouped_list = list(grouped.values())
            total = sum(len(g["nominations"]) for g in grouped_list)
            return {
                "success": True,
                "message": f"You have {total} peer nomination(s) across {len(grouped_list)} cycle(s).",
                "data": {"grouped_nominations": grouped_list}
            }
        except Exception as e:
            logger.error(f"ShowMyNominationsCommand error: {e}")
            return {"success": False, "message": "Could not retrieve nominations.", "data": {}}


class ShowMyCyclesCommand(BaseCommand):
    """Show cycles the current user is participating in."""
    allowed_roles = ['EMPLOYEE', 'MANAGER', 'HR_ADMIN', 'SUPER_ADMIN']
    requires_confirmation = False

    def execute(self, parameters: dict, user) -> dict:
        try:
            state_filter = parameters.get('state_filter')
            _FRIENDLY = {
                'ACTIVE': 'Active', 'NOMINATION': 'Nomination', 'CLOSED': 'Closed',
                'DRAFT': 'Draft', 'RESULTS_RELEASED': 'Results Released',
                'ARCHIVED': 'Archived', 'FINALIZED': 'Finalized',
            }

            with connection.cursor() as cursor:
                if state_filter:
                    cursor.execute("""
                        SELECT rc.id, rc.name, rc.state, rc.review_deadline, rc.nomination_deadline
                        FROM cycle_participants cp
                        JOIN review_cycles rc ON cp.cycle_id = rc.id
                        WHERE cp.user_id = %s
                          AND rc.state = %s
                        ORDER BY rc.created_at DESC
                    """, [db_uuid(user.id), state_filter])
                else:
                    # Exclude DRAFT cycles — matches UI get_my_cycles()
                    cursor.execute("""
                        SELECT rc.id, rc.name, rc.state, rc.review_deadline, rc.nomination_deadline
                        FROM cycle_participants cp
                        JOIN review_cycles rc ON cp.cycle_id = rc.id
                        WHERE cp.user_id = %s
                          AND rc.state != 'DRAFT'
                        ORDER BY rc.created_at DESC
                    """, [db_uuid(user.id)])
                rows = cursor.fetchall()

            if not rows:
                if state_filter:
                    friendly = _FRIENDLY.get(state_filter, state_filter)
                    return {"success": True, "message": f"You have no {friendly} cycles.", "data": {"cycles": []}}
                return {"success": True, "message": "You are not participating in any cycles.", "data": {"cycles": []}}

            cycles = [
                {
                    "id":                   str(r[0]),
                    "name":                 r[1],
                    "state":                r[2],
                    "review_deadline":      _fmt_date(r[3]),
                    "nomination_deadline":  _fmt_date(r[4]) if r[4] else None,
                }
                for r in rows
            ]
            label = f"{_FRIENDLY.get(state_filter, state_filter)} " if state_filter else ""
            return {
                "success": True,
                "message": f"You have {len(cycles)} {label}cycle(s).",
                "data": {"cycles": cycles}
            }
        except Exception as e:
            logger.error(f"ShowMyCyclesCommand error: {e}")
            return {"success": False, "message": "Could not retrieve your cycles.", "data": {}}


class ShowTemplatesCommand(BaseCommand):
    """List available review templates."""
    allowed_roles = ['HR_ADMIN', 'SUPER_ADMIN']
    requires_confirmation = False

    def execute(self, parameters: dict, user) -> dict:
        try:
            with connection.cursor() as cursor:
                # Filter by is_active=True — matches UI list_templates() which filters is_active=True
                # Inactive/deleted templates should not be shown
                cursor.execute("""
                    SELECT t.id, t.name, t.description,
                           COUNT(tc.id) AS cycle_count
                    FROM review_templates t
                    LEFT JOIN review_cycles tc ON tc.template_id = t.id
                    WHERE t.is_active = TRUE
                    GROUP BY t.id, t.name, t.description
                    ORDER BY t.created_at DESC
                """)
                rows = cursor.fetchall()

            if not rows:
                return {"success": True, "message": "No templates found.", "data": {"templates": []}}

            templates = [{"id": str(r[0]), "name": r[1], "description": r[2] or '', "cycle_count": r[3]} for r in rows]
            return {
                "success": True,
                "message": f"Found {len(templates)} template(s).",
                "data": {"templates": templates}
            }
        except Exception as e:
            logger.error(f"ShowTemplatesCommand error: {e}")
            return {"success": False, "message": "Could not retrieve templates.", "data": {}}


class ShowTeamNominationsCommand(BaseCommand):
    """Show PENDING peer nominations for the manager's team — mirrors the Nomination Approvals page."""
    allowed_roles = ['MANAGER', 'HR_ADMIN', 'SUPER_ADMIN']
    requires_confirmation = False

    def execute(self, parameters: dict, user) -> dict:
        try:
            with connection.cursor() as cursor:
                # Mirror the Manager Nomination Approvals page:
                # - Only PENDING nominations (what the manager needs to action)
                # - Only cycles in NOMINATION, FINALIZED, or ACTIVE state
                cursor.execute("""
                    SELECT
                        u_reviewee.first_name || ' ' || u_reviewee.last_name AS reviewee,
                        u_peer.first_name || ' ' || u_peer.last_name AS peer,
                        u_peer.email AS peer_email,
                        rc.name AS cycle, pn.status, pn.rejection_note,
                        pn.id AS nomination_id
                    FROM peer_nominations pn
                    JOIN users u_reviewee ON pn.reviewee_id = u_reviewee.id
                    JOIN users u_peer ON pn.peer_id = u_peer.id
                    JOIN review_cycles rc ON pn.cycle_id = rc.id
                    WHERE pn.reviewee_id IN (
                        SELECT employee_id FROM org_hierarchy WHERE manager_id = %s
                    )
                      AND pn.status = 'PENDING'
                      AND rc.state IN ('NOMINATION', 'FINALIZED', 'ACTIVE')
                    ORDER BY u_reviewee.first_name, rc.created_at DESC
                """, [db_uuid(user.id)])
                rows = cursor.fetchall()

            if not rows:
                return {
                    "success": True,
                    "message": "No pending nominations awaiting your approval.",
                    "data": {"grouped_team_nominations": []}
                }

            grouped = {}
            for r in rows:
                reviewee = r[0]
                if reviewee not in grouped:
                    grouped[reviewee] = {"reviewee": reviewee, "nominations": []}
                nom = {
                    "peer": r[1], "email": r[2], "cycle": r[3], "status": r[4],
                    "nomination_id": str(r[6]),
                }
                if r[5]:  # include rejection_note only when present
                    nom["rejection_note"] = r[5]
                grouped[reviewee]["nominations"].append(nom)

            grouped_list = list(grouped.values())
            total = sum(len(g["nominations"]) for g in grouped_list)
            return {
                "success": True,
                "message": f"{total} pending nomination(s) awaiting approval across {len(grouped_list)} team member(s).",
                "data": {"grouped_team_nominations": grouped_list}
            }
        except Exception as e:
            logger.error(f"ShowTeamNominationsCommand error: {e}")
            return {"success": False, "message": "Could not retrieve team nominations.", "data": {}}


class ShowEmployeesCommand(BaseCommand):
    """List all employees with their role and department."""
    allowed_roles = ['HR_ADMIN', 'SUPER_ADMIN']
    requires_confirmation = False

    def execute(self, parameters: dict, user) -> dict:
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT u.first_name || ' ' || u.last_name AS name,
                           u.email, u.role, d.name AS department
                    FROM users u
                    LEFT JOIN departments d ON u.department_id = d.id
                    WHERE u.status = 'ACTIVE'
                    ORDER BY u.role, u.first_name
                """)
                rows = cursor.fetchall()

            if not rows:
                return {"success": True, "message": "No employees found.", "data": {"employees": []}}

            employees = [{"name": r[0], "email": r[1], "role": r[2], "department": r[3] or 'N/A'} for r in rows]
            return {
                "success": True,
                "message": f"Found {len(employees)} active employee(s).",
                "data": {"employees": employees}
            }
        except Exception as e:
            logger.error(f"ShowEmployeesCommand error: {e}")
            return {"success": False, "message": "Could not retrieve employees.", "data": {}}


class ShowAnnouncementsCommand(BaseCommand):
    """Show active announcements."""
    allowed_roles = ['EMPLOYEE', 'MANAGER', 'HR_ADMIN', 'SUPER_ADMIN']
    requires_confirmation = False

    def execute(self, parameters: dict, user) -> dict:
        try:
            with connection.cursor() as cursor:
                now = timezone.now()
                cursor.execute("""
                    SELECT message, type, created_at, expires_at
                    FROM announcements
                    WHERE is_active = TRUE
                      AND (expires_at IS NULL OR expires_at > %s)
                    ORDER BY created_at DESC
                """, [now])
                rows = cursor.fetchall()

            if not rows:
                return {"success": True, "message": "No active announcements.", "data": {"announcements": []}}

            announcements = [
                {"message": r[0], "type": r[1], "created_at": _iso(r[2]), "expires_at": _iso(r[3])}
                for r in rows
            ]
            return {
                "success": True,
                "message": f"Found {len(announcements)} active announcement(s).",
                "data": {"announcements": announcements}
            }
        except Exception as e:
            logger.error(f"ShowAnnouncementsCommand error: {e}")
            return {"success": False, "message": "Could not retrieve announcements.", "data": {}}


class ShowAuditLogsCommand(BaseCommand):
    """Show recent audit log activity."""
    allowed_roles = ['SUPER_ADMIN']
    requires_confirmation = False

    def execute(self, parameters: dict, user) -> dict:
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT u.first_name || ' ' || u.last_name AS actor,
                           al.action_type, al.entity_type, al.created_at
                    FROM audit_logs al
                    LEFT JOIN users u ON al.actor_id = u.id
                    ORDER BY al.created_at DESC
                """)
                rows = cursor.fetchall()

            if not rows:
                return {"success": True, "message": "No audit logs found.", "data": {"audit_logs": []}}

            logs = [{"actor": r[0] or 'System', "action": r[1], "entity": r[2], "at": r[3].isoformat() if r[3] else None} for r in rows]
            return {
                "success": True,
                "message": f"Showing {len(logs)} recent audit log entries.",
                "data": {"audit_logs": logs}
            }
        except Exception as e:
            logger.error(f"ShowAuditLogsCommand error: {e}")
            return {"success": False, "message": "Could not retrieve audit logs.", "data": {}}


class ShowPendingApprovalsCommand(BaseCommand):
    """HR/Manager view of all nominations pending approval."""
    allowed_roles = ['MANAGER', 'HR_ADMIN', 'SUPER_ADMIN']
    requires_confirmation = False

    def execute(self, parameters: dict, user) -> dict:
        try:
            with connection.cursor() as cursor:
                if user.role in ('HR_ADMIN', 'SUPER_ADMIN'):
                    cursor.execute("""
                        SELECT pn.id,
                               u_reviewee.first_name || ' ' || u_reviewee.last_name AS reviewee,
                               u_reviewee.email AS reviewee_email,
                               u_peer.first_name || ' ' || u_peer.last_name AS peer,
                               u_peer.email AS peer_email,
                               rc.name AS cycle,
                               pn.status,
                               pn.created_at
                        FROM peer_nominations pn
                        JOIN users u_reviewee ON pn.reviewee_id = u_reviewee.id
                        JOIN users u_peer ON pn.peer_id = u_peer.id
                        JOIN review_cycles rc ON pn.cycle_id = rc.id
                        WHERE pn.status = 'PENDING'
                          AND rc.state IN ('NOMINATION', 'FINALIZED', 'ACTIVE')
                        ORDER BY pn.created_at DESC
                    """)
                else:
                    # MANAGER: only their team's nominations
                    cursor.execute("""
                        SELECT pn.id,
                               u_reviewee.first_name || ' ' || u_reviewee.last_name AS reviewee,
                               u_reviewee.email AS reviewee_email,
                               u_peer.first_name || ' ' || u_peer.last_name AS peer,
                               u_peer.email AS peer_email,
                               rc.name AS cycle,
                               pn.status,
                               pn.created_at
                        FROM peer_nominations pn
                        JOIN users u_reviewee ON pn.reviewee_id = u_reviewee.id
                        JOIN users u_peer ON pn.peer_id = u_peer.id
                        JOIN review_cycles rc ON pn.cycle_id = rc.id
                        WHERE pn.reviewee_id IN (
                            SELECT employee_id FROM org_hierarchy WHERE manager_id = %s
                        )
                          AND pn.status = 'PENDING'
                          AND rc.state IN ('NOMINATION', 'FINALIZED', 'ACTIVE')
                        ORDER BY pn.created_at DESC
                    """, [db_uuid(user.id)])
                rows = cursor.fetchall()
            if not rows:
                return {"success": True, "message": "No pending approvals at the moment.", "data": {}}
            approvals = [
                {
                    "nomination_id": str(r[0]),
                    "reviewee": r[1],
                    "reviewee_email": r[2],
                    "peer": r[3],
                    "peer_email": r[4],
                    "cycle": r[5],
                    "status": r[6],
                    "created_at": _iso(r[7]),
                }
                for r in rows
            ]
            return {
                "success": True,
                "message": f"Found {len(approvals)} pending approval(s).",
                "data": {"pending_approvals": approvals}
            }
        except Exception as e:
            logger.error(f"ShowPendingApprovalsCommand error: {e}")
            return {"success": False, "message": "Could not retrieve pending approvals.", "data": {}}


class ShowCycleResultsCommand(BaseCommand):
    """Show aggregated results for a closed/results-released cycle."""
    allowed_roles = ['MANAGER', 'HR_ADMIN', 'SUPER_ADMIN']
    requires_confirmation = False
    required_params = ['cycle_id']

    def execute(self, parameters: dict, user) -> dict:
        try:
            cycle_id = parameters.get('cycle_id', '').strip()
            with connection.cursor() as cursor:
                # Get cycle info
                cursor.execute("""
                    SELECT name, state FROM review_cycles WHERE id = %s
                """, [cycle_id])
                cycle_row = cursor.fetchone()
                if not cycle_row:
                    return {"success": False, "message": "Cycle not found.", "data": {}}
                cycle_name, cycle_state = cycle_row

                if cycle_state not in ('CLOSED', 'RESULTS_RELEASED', 'ARCHIVED'):
                    return {
                        "success": False,
                        "message": f"Results are not available yet. The cycle '{cycle_name}' is currently in {cycle_state} state.",
                        "data": {}
                    }

                # Get aggregated results
                cursor.execute("""
                    SELECT u.first_name || ' ' || u.last_name AS name,
                           u.email,
                           ar.overall_score,
                           ar.peer_score,
                           ar.self_score,
                           ar.manager_score
                    FROM aggregated_results ar
                    JOIN users u ON ar.reviewee_id = u.id
                    WHERE ar.cycle_id = %s
                    ORDER BY ar.overall_score DESC NULLS LAST
                """, [cycle_id])
                rows = cursor.fetchall()

            if not rows:
                return {"success": True, "message": f"No results found for '{cycle_name}'.", "data": {}}

            results = [
                {
                    "name": r[0],
                    "email": r[1],
                    "overall_score": round(float(r[2]), 2) if r[2] is not None else None,
                    "peer_score": round(float(r[3]), 2) if r[3] is not None else None,
                    "self_score": round(float(r[4]), 2) if r[4] is not None else None,
                    "manager_score": round(float(r[5]), 2) if r[5] is not None else None,
                }
                for r in rows
            ]
            return {
                "success": True,
                "message": f"Results for '{cycle_name}' ({len(results)} employees).",
                "data": {"cycle_results": results, "cycle_name": cycle_name}
            }
        except Exception as e:
            logger.error(f"ShowCycleResultsCommand error: {e}")
            return {"success": False, "message": "Could not retrieve cycle results.", "data": {}}


class RemindTeamCommand(BaseCommand):
    """Send a reminder notification to team members who haven't submitted their reviews."""
    allowed_roles = ['MANAGER', 'HR_ADMIN', 'SUPER_ADMIN']
    requires_confirmation = True
    required_params = ['cycle_id']

    def execute(self, parameters: dict, user) -> dict:
        try:
            cycle_id = parameters.get('cycle_id', '').strip()
            with connection.cursor() as cursor:
                # Get cycle info
                cursor.execute("SELECT name, state FROM review_cycles WHERE id = %s", [cycle_id])
                cycle_row = cursor.fetchone()
                if not cycle_row:
                    return {"success": False, "message": "Cycle not found.", "data": {}}
                cycle_name, cycle_state = cycle_row

                if cycle_state not in ('ACTIVE', 'NOMINATION', 'FINALIZED'):
                    return {
                        "success": False,
                        "message": f"Reminders can only be sent for active cycles. '{cycle_name}' is in {cycle_state} state.",
                        "data": {}
                    }

                # Find reviewers who haven't submitted
                cursor.execute("""
                    SELECT DISTINCT rt.reviewer_id, u.email, u.first_name
                    FROM reviewer_tasks rt
                    JOIN users u ON rt.reviewer_id = u.id
                    WHERE rt.cycle_id = %s
                      AND rt.status != 'SUBMITTED'
                      AND rt.reviewer_id IN (
                          SELECT employee_id FROM org_hierarchy WHERE manager_id = %s
                      )
                """, [cycle_id, db_uuid(user.id)])
                pending_rows = cursor.fetchall()

            if not pending_rows:
                return {
                    "success": True,
                    "message": f"Everyone on your team has submitted their review for '{cycle_name}'!",
                    "data": {}
                }

            # Create notifications for each pending reviewer
            from apps.notifications.models import Notification
            count = 0
            for reviewer_id, email, first_name in pending_rows:
                try:
                    Notification.objects.create(
                        user_id=reviewer_id,
                        title="Review Reminder",
                        message=f"Reminder: You have a pending review for '{cycle_name}'. Please submit it soon.",
                        type="REMINDER",
                    )
                    count += 1
                except Exception:
                    pass

            return {
                "success": True,
                "message": f"Reminder sent to {count} team member(s) for '{cycle_name}'.",
                "data": {"reminded_count": count}
            }
        except Exception as e:
            logger.error(f"RemindTeamCommand error: {e}")
            return {"success": False, "message": "Could not send reminders.", "data": {}}


class ExportNominationsCommand(BaseCommand):
    """Export nominations data for a cycle (returns downloadable data)."""
    allowed_roles = ['MANAGER', 'HR_ADMIN', 'SUPER_ADMIN']
    requires_confirmation = False
    required_params = ['cycle_id']

    def execute(self, parameters: dict, user) -> dict:
        try:
            cycle_id = parameters.get('cycle_id', '').strip()
            with connection.cursor() as cursor:
                cursor.execute("SELECT name FROM review_cycles WHERE id = %s", [cycle_id])
                row = cursor.fetchone()
                if not row:
                    return {"success": False, "message": "Cycle not found.", "data": {}}
                cycle_name = row[0]

                if user.role in ('HR_ADMIN', 'SUPER_ADMIN'):
                    cursor.execute("""
                        SELECT u_reviewee.first_name || ' ' || u_reviewee.last_name,
                               u_reviewee.email,
                               u_peer.first_name || ' ' || u_peer.last_name,
                               u_peer.email,
                               pn.status,
                               pn.created_at
                        FROM peer_nominations pn
                        JOIN users u_reviewee ON pn.reviewee_id = u_reviewee.id
                        JOIN users u_peer ON pn.peer_id = u_peer.id
                        WHERE pn.cycle_id = %s
                        ORDER BY u_reviewee.first_name, pn.created_at
                    """, [cycle_id])
                else:
                    cursor.execute("""
                        SELECT u_reviewee.first_name || ' ' || u_reviewee.last_name,
                               u_reviewee.email,
                               u_peer.first_name || ' ' || u_peer.last_name,
                               u_peer.email,
                               pn.status,
                               pn.created_at
                        FROM peer_nominations pn
                        JOIN users u_reviewee ON pn.reviewee_id = u_reviewee.id
                        JOIN users u_peer ON pn.peer_id = u_peer.id
                        WHERE pn.cycle_id = %s
                          AND pn.reviewee_id IN (
                              SELECT employee_id FROM org_hierarchy WHERE manager_id = %s
                          )
                        ORDER BY u_reviewee.first_name, pn.created_at
                    """, [cycle_id, db_uuid(user.id)])
                rows = cursor.fetchall()

            if not rows:
                return {"success": True, "message": f"No nominations found for '{cycle_name}'.", "data": {}}

            nominations = [
                {
                    "reviewee": r[0],
                    "reviewee_email": r[1],
                    "peer": r[2],
                    "peer_email": r[3],
                    "status": r[4],
                    "nominated_on": _iso(r[5]),
                }
                for r in rows
            ]
            return {
                "success": True,
                "message": f"Found {len(nominations)} nomination(s) for '{cycle_name}'.",
                "data": {"export_nominations": nominations, "cycle_name": cycle_name}
            }
        except Exception as e:
            logger.error(f"ExportNominationsCommand error: {e}")
            return {"success": False, "message": "Could not export nominations.", "data": {}}


class ShowMyProfileCommand(BaseCommand):
    """Show the current user's profile details."""
    allowed_roles = ['EMPLOYEE', 'MANAGER', 'HR_ADMIN', 'SUPER_ADMIN']
    requires_confirmation = False

    def execute(self, parameters: dict, user) -> dict:
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT u.first_name || ' ' || u.last_name AS name,
                           u.email, u.role, u.job_title,
                           COALESCE(d.name, 'N/A') AS department,
                           u.status,
                           u.created_at,
                           mgr.first_name || ' ' || mgr.last_name AS manager_name,
                           mgr.email AS manager_email
                    FROM users u
                    LEFT JOIN departments d ON u.department_id = d.id
                    LEFT JOIN org_hierarchy oh ON oh.employee_id = u.id
                    LEFT JOIN users mgr ON oh.manager_id = mgr.id
                    WHERE u.id = %s
                """, [db_uuid(user.id)])
                row = cursor.fetchone()

            if not row:
                return {"success": False, "message": "Could not load your profile.", "data": {}}

            profile = {
                "name":          row[0],
                "email":         row[1],
                "role":          row[2],
                "job_title":     row[3] or 'N/A',
                "department":    row[4],
                "status":        row[5] or 'N/A',
                "member_since":  _fmt_date(row[6]),  # date_joined — date only, no time needed
                "manager":       row[7] or 'N/A',
                "manager_email": row[8] or 'N/A',
            }
            return {
                "success": True,
                "message": "Here's your profile.",
                "data": {"profile": profile}
            }
        except Exception as e:
            logger.error(f"ShowMyProfileCommand error: {e}")
            return {"success": False, "message": "Could not retrieve your profile. Please try again.", "data": {}}


class ShowMyManagerCommand(BaseCommand):
    """Show the current user's manager."""
    allowed_roles = ['EMPLOYEE', 'MANAGER', 'HR_ADMIN', 'SUPER_ADMIN']
    requires_confirmation = False

    def execute(self, parameters: dict, user) -> dict:
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT u.first_name || ' ' || u.last_name AS name,
                           u.email, u.job_title,
                           COALESCE(d.name, 'N/A') AS department
                    FROM org_hierarchy oh
                    JOIN users u ON oh.manager_id = u.id
                    LEFT JOIN departments d ON u.department_id = d.id
                    WHERE oh.employee_id = %s
                """, [db_uuid(user.id)])
                row = cursor.fetchone()

            if not row:
                return {
                    "success": True,
                    "message": "You don't have a manager assigned.",
                    "data": {"manager": None}
                }

            manager = {
                "name":       row[0],
                "email":      row[1],
                "job_title":  row[2] or 'N/A',
                "department": row[3],
            }
            return {
                "success": True,
                "message": f"Your manager is {manager['name']}.",
                "data": {"manager": manager}
            }
        except Exception as e:
            logger.error(f"ShowMyManagerCommand error: {e}")
            return {"success": False, "message": "Could not retrieve your manager. Please try again.", "data": {}}


class ShowMyTeamCommand(BaseCommand):
    """Show direct reports for the current manager."""
    allowed_roles = ['MANAGER', 'HR_ADMIN', 'SUPER_ADMIN']
    requires_confirmation = False

    def execute(self, parameters: dict, user) -> dict:
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT u.first_name || ' ' || u.last_name AS name,
                           u.email, u.role, u.job_title
                    FROM org_hierarchy oh
                    JOIN users u ON oh.employee_id = u.id
                    WHERE oh.manager_id = %s
                    ORDER BY u.first_name
                """, [db_uuid(user.id)])
                rows = cursor.fetchall()

            if not rows:
                return {
                    "success": True,
                    "message": "You have no direct reports.",
                    "data": {"direct_reports": []}
                }

            team = [
                {"name": r[0], "email": r[1], "role": r[2], "job_title": r[3] or 'N/A'}
                for r in rows
            ]
            return {
                "success": True,
                "message": f"You have {len(team)} direct report(s).",
                "data": {"direct_reports": team}
            }
        except Exception as e:
            logger.error(f"ShowMyTeamCommand error: {e}")
            return {"success": False, "message": "Could not retrieve your team. Please try again.", "data": {}}


class WhenIsMyReviewDueCommand(BaseCommand):
    """Show the nearest upcoming review deadline for the current user."""
    allowed_roles = ['EMPLOYEE', 'MANAGER', 'HR_ADMIN', 'SUPER_ADMIN']
    requires_confirmation = False

    def execute(self, parameters: dict, user) -> dict:
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT rc.name, rc.review_deadline
                    FROM review_cycles rc
                    JOIN cycle_participants cp ON cp.cycle_id = rc.id
                    WHERE cp.user_id = %s
                      AND rc.state IN ('ACTIVE', 'NOMINATION', 'FINALIZED')
                      AND rc.review_deadline IS NOT NULL
                    ORDER BY rc.review_deadline ASC
                    LIMIT 1
                """, [db_uuid(user.id)])
                row = cursor.fetchone()

            if not row:
                return {
                    "success": True,
                    "message": "No upcoming review deadline found.",
                    "data": {"next_deadline": None}
                }

            cycle_name, deadline = row[0], row[1]
            return {
                "success": True,
                "message": f"Your next review is for '{cycle_name}' due {_fmt_date(deadline)}.",
                "data": {
                    "next_deadline": {
                        "cycle_name":    cycle_name,
                        "deadline_date": _fmt_date(deadline),
                    }
                }
            }
        except Exception as e:
            logger.error(f"WhenIsMyReviewDueCommand error: {e}")
            return {"success": False, "message": "Could not retrieve your review deadline. Please try again.", "data": {}}


class WhoHasNotSubmittedCommand(BaseCommand):
    """Show which direct reports have pending/unsubmitted reviewer tasks."""
    allowed_roles = ['MANAGER', 'HR_ADMIN', 'SUPER_ADMIN']
    requires_confirmation = False

    def execute(self, parameters: dict, user) -> dict:
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT u_reviewer.first_name || ' ' || u_reviewer.last_name AS reviewer,
                           u_reviewee.first_name || ' ' || u_reviewee.last_name AS reviewee,
                           rc.name AS cycle, rt.status
                    FROM reviewer_tasks rt
                    JOIN users u_reviewer ON rt.reviewer_id = u_reviewer.id
                    JOIN users u_reviewee ON rt.reviewee_id = u_reviewee.id
                    JOIN review_cycles rc ON rt.cycle_id = rc.id
                    WHERE rt.reviewer_id IN (
                        SELECT employee_id FROM org_hierarchy WHERE manager_id = %s
                    )
                      AND rt.status != 'SUBMITTED'
                      AND rc.state = 'ACTIVE'
                    ORDER BY u_reviewer.first_name, rc.name
                """, [db_uuid(user.id)])
                rows = cursor.fetchall()

            if not rows:
                return {
                    "success": True,
                    "message": "No pending submissions found.",
                    "data": {"pending": []}
                }

            pending = [
                {"reviewer": r[0], "reviewee": r[1], "cycle": r[2], "task_status": r[3]}
                for r in rows
            ]
            unique_reviewers = len({r["reviewer"] for r in pending})
            return {
                "success": True,
                "message": f"{unique_reviewers} team member(s) have not yet submitted ({len(pending)} task(s) pending).",
                "data": {"pending": pending}
            }
        except Exception as e:
            logger.error(f"WhoHasNotSubmittedCommand error: {e}")
            return {"success": False, "message": "Could not retrieve submission status. Please try again.", "data": {}}


class HelpCommand(BaseCommand):
    """Return a role-aware list of available commands."""
    allowed_roles = ['EMPLOYEE', 'MANAGER', 'HR_ADMIN', 'SUPER_ADMIN']
    requires_confirmation = False

    _COMMANDS = {
        'EMPLOYEE': [
            "Show my tasks", "Show my feedback", "Show my nominations",
            "Show my cycles", "Show cycle deadlines", "Show announcements",
            "Nominate peers", "Show my profile", "Show my manager",
            "When is my review due", "Help",
        ],
        'MANAGER': [
            "Show my tasks", "Show my feedback", "Show my nominations",
            "Show my cycles", "Show cycle deadlines", "Show announcements",
            "Show team summary", "Show team nominations", "Show pending reviews",
            "Show my team", "Who has not submitted",
            "Approve nomination", "Reject nomination",
            "Nominate peers", "Show my profile", "Show my manager",
            "When is my review due", "Help",
        ],
        'HR_ADMIN': [
            "Show my tasks", "Show my feedback", "Show my cycles",
            "Show cycle deadlines", "Show announcements",
            "Show cycle status", "Show participation stats", "Show employees",
            "Show templates", "Show team nominations",
            "Create cycle", "Create template",
            "Activate cycle", "Close cycle", "Release results", "Cancel cycle",
            "Approve nomination", "Reject nomination",
            "Show my profile", "When is my review due", "Help",
        ],
        'SUPER_ADMIN': [
            "Show my tasks", "Show my feedback", "Show my cycles",
            "Show cycle deadlines", "Show announcements",
            "Show cycle status", "Show participation stats", "Show employees",
            "Show templates", "Show team nominations", "Show audit logs",
            "Create cycle", "Create template",
            "Activate cycle", "Close cycle", "Release results", "Cancel cycle",
            "Approve nomination", "Reject nomination",
            "Show my profile", "When is my review due", "Help",
        ],
    }

    def execute(self, parameters: dict, user) -> dict:
        role = getattr(user, 'role', 'EMPLOYEE')
        commands = self._COMMANDS.get(role, self._COMMANDS['EMPLOYEE'])
        return {
            "success": True,
            "message": "You can ask me things like:",
            "data": {"commands": commands}
        }


# ── Phase 3: Compound status summary ─────────────────────────────────────────

class SummarizeMyStatusCommand(BaseCommand):
    """
    Phase 3 compound command — runs multiple sub-queries and returns combined data.
    The pipeline detects _synthesize=True and passes the data to the LLM to write
    a natural language summary instead of a fixed template response.
    """
    allowed_roles = ['EMPLOYEE', 'MANAGER', 'HR_ADMIN', 'SUPER_ADMIN']
    requires_confirmation = False

    def execute(self, parameters: dict, user) -> dict:
        cycles      = ShowMyCyclesCommand().execute({}, user)
        tasks       = ShowMyTasksCommand().execute({}, user)
        nominations = ShowMyNominationsCommand().execute({}, user)
        deadline    = WhenIsMyReviewDueCommand().execute({}, user)

        return {
            "success": True,
            "message": "Here is your complete status overview.",
            "data": {
                "cycles":       cycles.get("data", {}),
                "tasks":        tasks.get("data", {}),
                "nominations":  nominations.get("data", {}),
                "next_deadline": deadline.get("data", {}),
            },
            "_synthesize": True,  # signal pipeline to use LLM for natural language response
        }

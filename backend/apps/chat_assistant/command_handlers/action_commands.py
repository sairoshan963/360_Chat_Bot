"""
Action commands — modify data, require confirmation before execution.

All commands MUST go through the existing service layer to ensure:
- Business rule enforcement
- State machine compliance
- AuditLog entries
- Notifications
"""
import logging
from datetime import timedelta
from django.utils import timezone
from rest_framework.exceptions import ValidationError, PermissionDenied, NotFound
from .base import BaseCommand

logger = logging.getLogger(__name__)


def _humanize_error(msg: str) -> str:
    """Map known technical service messages to user-friendly alternatives."""
    _MAP = [
        ("nominations can only be submitted when cycle is in nomination state",
            "Nominations can only be submitted while the cycle is in the nomination phase."),
        ("you are not a participant in this cycle",
            "You're not listed as a participant in this cycle."),
        ("cycle with this name already exists",
            "A cycle with this name already exists. Please choose a different name."),
        ("template with this name already exists",
            "A template with this name already exists. Please choose a different name."),
        ("cycle not found", "That cycle wasn't found — it may have been deleted."),
        ("template not found", "That template wasn't found."),
        ("nomination not found", "That nomination wasn't found — it may have already been decided."),
        ("you cannot nominate yourself", "You can't nominate yourself as a peer reviewer."),
        ("already been decided", "This nomination has already been approved or rejected."),
        ("cannot activate", "This cycle can't be activated in its current state."),
        ("cannot close", "This cycle can't be closed in its current state."),
        ("cannot finalize", "This cycle can't be finalized in its current state."),
        ("is not in draft state", "Only Draft cycles can be activated."),
        ("is not in active state", "Only Active cycles can be closed."),
        ("is not in nomination state", "The cycle must be in the Nomination phase for this action."),
        ("is not in closed state", "Results can only be released for Closed cycles."),
        ("pending nominations", "There are still pending nominations that must be resolved first."),
    ]
    lower = msg.lower()
    for fragment, friendly in _MAP:
        if fragment in lower:
            return friendly
    return msg


def _service_error_message(e) -> str:
    """Convert DRF exception to a user-friendly string."""
    if hasattr(e, 'detail'):
        detail = e.detail
        if isinstance(detail, list):
            raw = str(detail[0])
        elif isinstance(detail, dict):
            msgs = []
            for v in detail.values():
                msgs.append(str(v[0]) if isinstance(v, list) else str(v))
            raw = '; '.join(msgs)
        else:
            raw = str(detail)
    else:
        raw = str(e)
    return _humanize_error(raw)


class CreateCycleCommand(BaseCommand):
    allowed_roles         = ['HR_ADMIN', 'SUPER_ADMIN']
    requires_confirmation = True
    required_params       = [
        'name', 'template_id', 'description', 'quarter_year',
        'review_deadline', 'nomination_deadline', 'nomination_approval',
        'peer_enabled', 'peer_count', 'participant_emails',
    ]

    def execute(self, parameters: dict, user) -> dict:
        import re
        import datetime
        try:
            from apps.review_cycles.services import create_cycle
            from apps.users.models import User as UserModel

            cycle_name = parameters.get('name', '').strip()
            if not cycle_name:
                return {"success": False, "message": "Cycle name cannot be blank. Please provide a valid name.", "data": {}, "retry_field": "name"}

            template_id = parameters.get('template_id', '').strip()

            # Description — 'skip' → None
            description_raw = parameters.get('description', '').strip()
            description = None if description_raw.lower() == 'skip' else (description_raw or None)

            # Quarter + Year — parse "Q3 2026" or "skip"
            quarter = quarter_year_val = None
            qy_raw = parameters.get('quarter_year', '').strip()
            if qy_raw.lower() != 'skip':
                m = re.match(r'(Q[1-4])\s+(\d{4})', qy_raw, re.IGNORECASE)
                if m:
                    quarter = m.group(1).upper()
                    quarter_year_val = int(m.group(2))

            # Parse review_deadline
            deadline_str = parameters.get('review_deadline', '').strip()
            review_deadline = None
            for fmt in ('%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y', '%m/%d/%Y', '%Y/%m/%d'):
                try:
                    review_deadline = datetime.datetime.strptime(deadline_str, fmt).strftime('%Y-%m-%dT00:00:00')
                    break
                except ValueError:
                    continue
            if not review_deadline:
                review_deadline = (timezone.now() + timedelta(days=30)).strftime('%Y-%m-%dT%H:%M:%S')

            # Parse nomination_deadline — 'skip' → None
            nomination_deadline = None
            nom_dl_raw = parameters.get('nomination_deadline', '').strip()
            if nom_dl_raw.lower() != 'skip':
                for fmt in ('%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y', '%m/%d/%Y', '%Y/%m/%d'):
                    try:
                        nomination_deadline = datetime.datetime.strptime(nom_dl_raw, fmt).strftime('%Y-%m-%dT00:00:00')
                        break
                    except ValueError:
                        continue

            # Nomination approval — 'skip' or 'auto' → AUTO, 'manual' → MANUAL
            approval_raw = parameters.get('nomination_approval', 'auto').lower().strip()
            nomination_approval_mode = 'MANUAL' if approval_raw == 'manual' else 'AUTO'

            # Parse peer_enabled
            peer_enabled_raw = parameters.get('peer_enabled', 'no').lower().strip()
            peer_enabled = peer_enabled_raw in ('yes', 'y', 'true', '1')

            peer_min = peer_max = None
            if peer_enabled:
                peer_count_raw = parameters.get('peer_count', '').strip()
                numbers = re.findall(r'\d+', peer_count_raw)
                if len(numbers) >= 2:
                    peer_min, peer_max = int(numbers[0]), int(numbers[1])
                elif len(numbers) == 1:
                    peer_min = peer_max = int(numbers[0])
                if not peer_min or not peer_max:
                    return {"success": False, "message": "Please provide a valid peer count range (e.g. '2 to 5').", "data": {}, "retry_field": "peer_count"}
                if peer_min > peer_max:
                    return {"success": False, "message": f"Minimum peers ({peer_min}) cannot be greater than maximum ({peer_max}). Please provide a valid range.", "data": {}, "retry_field": "peer_count"}

            # Parse participant input → user IDs
            # Supports: "all", department name(s), emails, or any mix comma-separated
            participant_ids = []
            participant_input = parameters.get('participant_emails', '').strip()
            if participant_input and participant_input.lower() != 'skip':
                from apps.users.models import Department
                from django.db.models import Q as _Q

                tokens = [t.strip() for t in participant_input.split(',') if t.strip()]
                email_tokens = [t.lower() for t in tokens if '@' in t]
                keyword_tokens = [t for t in tokens if '@' not in t]

                resolved_ids: set = set()

                if any(k.lower() == 'all' for k in keyword_tokens):
                    # "all" → every active user
                    resolved_ids.update(
                        str(uid) for uid in UserModel.objects.filter(status='ACTIVE').values_list('id', flat=True)
                    )
                else:
                    # Department names
                    dept_names = [k for k in keyword_tokens]
                    if dept_names:
                        dept_q = _Q()
                        for dn in dept_names:
                            dept_q |= _Q(department__name__iexact=dn)
                        dept_users = UserModel.objects.filter(dept_q, status='ACTIVE').select_related('department')
                        found_dept_names_lower = {
                            u.department.name.lower() for u in dept_users if u.department
                        }
                        not_found = [dn for dn in dept_names if dn.lower() not in found_dept_names_lower]
                        if not_found:
                            return {
                                "success": False,
                                "message": f"Department(s) not found: {', '.join(not_found)}. Please check the name(s) or use emails directly.",
                                "data": {},
                                "retry_field": "participant_emails",
                            }
                        resolved_ids.update(str(u.id) for u in dept_users)

                # Individual emails
                if email_tokens:
                    email_users = UserModel.objects.filter(email__in=email_tokens)
                    found_emails = {u.email.lower() for u in email_users}
                    missing_emails = set(email_tokens) - found_emails
                    if missing_emails:
                        return {
                            "success": False,
                            "message": f"We couldn't find these email(s): {', '.join(sorted(missing_emails))}. Please check and try again.",
                            "data": {},
                            "retry_field": "participant_emails",
                        }
                    resolved_ids.update(str(u.id) for u in email_users)

                participant_ids = list(resolved_ids)

            data = {
                'name':                     cycle_name,
                'template_id':              template_id,
                'description':              description,
                'quarter':                  quarter,
                'quarter_year':             quarter_year_val,
                'review_deadline':          review_deadline,
                'nomination_deadline':      nomination_deadline,
                'nomination_approval_mode': nomination_approval_mode,
                'peer_enabled':             peer_enabled,
                'peer_min_count':           peer_min,
                'peer_max_count':           peer_max,
                'participant_ids':          participant_ids,
            }

            cycle = create_cycle(data, user)

            peer_info = f", peer review enabled ({peer_min}–{peer_max} peers)" if peer_enabled else ""
            participant_info = f" {len(participant_ids)} participant(s) added." if participant_ids else " No participants added — you can add them in the UI."
            return {
                "success": True,
                "message": f"Cycle '{cycle.name}' created as DRAFT{peer_info}.{participant_info}",
                "data": {"cycle_id": str(cycle.id), "name": cycle.name, "state": cycle.state},
            }
        except (ValidationError, PermissionDenied, NotFound) as e:
            err_msg = _service_error_message(e)
            is_name_error = any(k in err_msg.lower() for k in ('name', 'already exists', 'duplicate', 'unique'))
            return {"success": False, "message": err_msg, "data": {}, "retry_field": "name" if is_name_error else None}
        except Exception as e:
            logger.error(f"CreateCycleCommand error: {e}")
            return {"success": False, "message": "Could not create cycle. Please try again.", "data": {}}


class CreateTemplateCommand(BaseCommand):
    allowed_roles         = ['HR_ADMIN', 'SUPER_ADMIN']
    requires_confirmation = True
    required_params       = ['name']

    def execute(self, parameters: dict, user) -> dict:
        try:
            from apps.review_cycles.services import create_template

            template_name = parameters.get('name', '').strip()
            if not template_name:
                return {"success": False, "message": "Template name cannot be blank. Please provide a valid name.", "data": {}, "retry_field": "name"}

            # Goes through full service — validates, creates, writes AuditLog
            template = create_template(template_name, None, [], user)

            return {
                "success": True,
                "message": (
                    f"Template '{template.name}' created successfully. "
                    f"Go to the UI to add sections and questions."
                ),
                "data": {"template_id": str(template.id), "name": template.name}
            }
        except (ValidationError, PermissionDenied, NotFound) as e:
            err_msg = _service_error_message(e)
            is_name_error = any(k in err_msg.lower() for k in ('name', 'already exists', 'duplicate', 'unique'))
            return {"success": False, "message": err_msg, "data": {}, "retry_field": "name" if is_name_error else None}
        except Exception as e:
            logger.error(f"CreateTemplateCommand error: {e}")
            return {"success": False, "message": "Could not create template. Please try again.", "data": {}}


class NominatePeersCommand(BaseCommand):
    allowed_roles         = ['EMPLOYEE', 'MANAGER', 'HR_ADMIN', 'SUPER_ADMIN']
    requires_confirmation = True
    required_params       = ['cycle_id', 'peer_emails']

    def execute(self, parameters: dict, user) -> dict:
        try:
            from apps.reviewer_workflow.services import submit_nominations
            from apps.users.models import User

            cycle_id   = parameters.get('cycle_id')
            raw_emails = parameters.get('peer_emails', [])

            # Accept both list and comma-separated string
            if isinstance(raw_emails, str):
                peer_emails = [e.strip() for e in raw_emails.split(',') if e.strip()]
            else:
                peer_emails = [e.strip() for e in raw_emails if e.strip()]

            if not peer_emails:
                return {"success": False, "message": "No peer emails provided.", "data": {}, "retry_field": "peer_emails"}

            # Resolve emails → user IDs
            peers = User.objects.filter(email__in=peer_emails, status='ACTIVE')
            found_emails   = set(peers.values_list('email', flat=True))
            missing_emails = [e for e in peer_emails if e not in found_emails]

            if missing_emails:
                return {
                    "success":     False,
                    "message":     f"We couldn't find these email(s) in the system: {', '.join(missing_emails)}. Please check and try again.",
                    "data":        {},
                    "retry_field": "peer_emails",
                }

            peer_ids = list(peers.values_list('id', flat=True))

            # Goes through full service — validates cycle state, participant membership,
            # self-nomination guard, min/max peer counts, auto-approve logic, AuditLog
            nominations = submit_nominations(cycle_id, user, peer_ids)

            nominated_names = [f"{n.peer.get_full_name()} ({n.peer.email})" for n in nominations]
            return {
                "success": True,
                "message": f"Successfully nominated {nominations.count()} peer(s).",
                "data": {"nominated": nominated_names}
            }
        except (ValidationError, PermissionDenied, NotFound) as e:
            err_msg = _service_error_message(e)
            # Peer count validation errors → retry peer_emails slot
            is_peer_input_error = any(k in err_msg.lower() for k in ('nominat', 'peer', 'minimum', 'maximum', 'already'))
            return {
                "success":     False,
                "message":     err_msg,
                "data":        {},
                "retry_field": "peer_emails" if is_peer_input_error else None,
            }
        except Exception as e:
            logger.error(f"NominatePeersCommand error: {e}")
            return {"success": False, "message": "Could not submit nominations. Please try again.", "data": {}}


class ReleaseResultsCommand(BaseCommand):
    allowed_roles         = ['HR_ADMIN', 'SUPER_ADMIN']
    requires_confirmation = True
    required_params       = ['cycle_id']

    def execute(self, parameters: dict, user) -> dict:
        try:
            from apps.review_cycles.services import release_results

            cycle_id = parameters.get('cycle_id')

            # Goes through full service — validates CLOSED state, runs aggregation
            # pipeline, sets results_released_at, sends notifications, writes AuditLog
            cycle = release_results(cycle_id, user)

            return {
                "success": True,
                "message": f"Results for cycle '{cycle.name}' have been released. Participants have been notified.",
                "data": {"cycle_id": str(cycle.id), "state": cycle.state}
            }
        except (ValidationError, PermissionDenied, NotFound) as e:
            return {"success": False, "message": _service_error_message(e), "data": {}}
        except Exception as e:
            logger.error(f"ReleaseResultsCommand error: {e}")
            return {"success": False, "message": "Could not release results. Please try again.", "data": {}}


class CancelCycleCommand(BaseCommand):
    allowed_roles         = ['HR_ADMIN', 'SUPER_ADMIN']
    requires_confirmation = True
    required_params       = ['cycle_id']

    def execute(self, parameters: dict, user) -> dict:
        try:
            from django.db import transaction
            from apps.review_cycles.models import ReviewCycle, CycleParticipant
            from apps.notifications.models import Notification
            from apps.audit.models import AuditLog

            cycle_id = parameters.get('cycle_id')

            with transaction.atomic():
                try:
                    cycle = ReviewCycle.objects.select_for_update().get(id=cycle_id)
                except ReviewCycle.DoesNotExist:
                    return {"success": False, "message": "Cycle not found.", "data": {}}

                if cycle.state in ('CLOSED', 'RESULTS_RELEASED', 'ARCHIVED'):
                    return {
                        "success": False,
                        "message": f"Cannot cancel a cycle in '{cycle.state}' state. Only DRAFT, NOMINATION, FINALIZED, or ACTIVE cycles can be cancelled.",
                        "data": {}
                    }

                old_state   = cycle.state
                cycle.state = 'ARCHIVED'
                cycle.save(update_fields=['state', 'updated_at'])

                # Notify all participants — same pattern as service layer
                participant_ids = CycleParticipant.objects.filter(cycle=cycle).values_list('user_id', flat=True)
                notifications = [
                    Notification(
                        user_id=uid,
                        type='GENERAL',
                        title='Review Cycle Cancelled',
                        message=f"The review cycle '{cycle.name}' has been cancelled by HR.",
                        link='/cycles',
                    )
                    for uid in participant_ids
                ]
                if notifications:
                    Notification.objects.bulk_create(notifications, ignore_conflicts=True)

                # Audit log
                AuditLog.log(
                    actor=user, action='CANCEL_CYCLE',
                    entity_type='review_cycle', entity_id=cycle.id,
                    old_value={'state': old_state},
                    new_value={'cycle': cycle.name, 'state': 'ARCHIVED', 'cancelled_via': 'chat'}
                )

            return {
                "success": True,
                "message": f"Cycle '{cycle.name}' has been cancelled. All {len(notifications)} participant(s) have been notified.",
                "data": {"cycle_id": str(cycle.id), "state": cycle.state}
            }
        except (ValidationError, PermissionDenied, NotFound) as e:
            return {"success": False, "message": _service_error_message(e), "data": {}}
        except Exception as e:
            logger.error(f"CancelCycleCommand error: {e}")
            return {"success": False, "message": "Could not cancel cycle. Please try again.", "data": {}}


class ActivateCycleCommand(BaseCommand):
    """Activate a DRAFT cycle — goes through service layer which generates tasks."""
    allowed_roles         = ['HR_ADMIN', 'SUPER_ADMIN']
    requires_confirmation = True
    required_params       = ['cycle_id']

    def execute(self, parameters: dict, user) -> dict:
        try:
            from apps.review_cycles.services import activate_cycle

            cycle_id = parameters.get('cycle_id')

            # Goes through full service — validates DRAFT state, checks participants exist,
            # determines NOMINATION vs ACTIVE (based on peer_enabled), generates reviewer
            # tasks, sends notifications, writes AuditLog
            cycle = activate_cycle(cycle_id, user)

            return {
                "success": True,
                "message": f"Cycle '{cycle.name}' is now '{cycle.state}'. Participants have been notified.",
                "data": {"cycle_id": str(cycle.id), "state": cycle.state}
            }
        except (ValidationError, PermissionDenied, NotFound) as e:
            return {"success": False, "message": _service_error_message(e), "data": {}}
        except Exception as e:
            logger.error(f"ActivateCycleCommand error: {e}")
            return {"success": False, "message": "Could not activate cycle. Please try again.", "data": {}}


class CloseCycleCommand(BaseCommand):
    """Close an ACTIVE cycle — goes through service layer which locks pending tasks."""
    allowed_roles         = ['HR_ADMIN', 'SUPER_ADMIN']
    requires_confirmation = True
    required_params       = ['cycle_id']

    def execute(self, parameters: dict, user) -> dict:
        try:
            from apps.review_cycles.services import close_cycle

            cycle_id = parameters.get('cycle_id')

            # Goes through full service — validates ACTIVE state, locks all
            # PENDING/IN_PROGRESS tasks, writes AuditLog
            cycle = close_cycle(cycle_id, user)

            return {
                "success": True,
                "message": f"Cycle '{cycle.name}' has been closed. All pending tasks have been locked.",
                "data": {"cycle_id": str(cycle.id), "state": cycle.state}
            }
        except (ValidationError, PermissionDenied, NotFound) as e:
            return {"success": False, "message": _service_error_message(e), "data": {}}
        except Exception as e:
            logger.error(f"CloseCycleCommand error: {e}")
            return {"success": False, "message": "Could not close cycle. Please try again.", "data": {}}


class FinalizeCycleCommand(BaseCommand):
    """Finalize a NOMINATION cycle — locks nominations and generates reviewer tasks, moving it to ACTIVE."""
    allowed_roles         = ['HR_ADMIN', 'SUPER_ADMIN']
    requires_confirmation = True
    required_params       = ['cycle_id']

    def execute(self, parameters: dict, user) -> dict:
        try:
            from apps.review_cycles.services import finalize_cycle

            cycle_id = parameters.get('cycle_id')

            # Goes through full service — validates NOMINATION state, checks pending
            # nominations are resolved, generates reviewer tasks, notifies participants
            cycle = finalize_cycle(cycle_id, user)

            return {
                "success": True,
                "message": (
                    f"Cycle '{cycle.name}' has been finalized and is now ACTIVE. "
                    "Reviewer tasks have been generated and participants notified."
                ),
                "data": {"cycle_id": str(cycle.id), "state": cycle.state}
            }
        except (ValidationError, PermissionDenied, NotFound) as e:
            return {"success": False, "message": _service_error_message(e), "data": {}}
        except Exception as e:
            logger.error(f"FinalizeCycleCommand error: {e}")
            return {"success": False, "message": "Could not finalize cycle. Please try again.", "data": {}}


class ApproveNominationCommand(BaseCommand):
    """Approve a pending peer nomination — managers and HR can approve."""
    allowed_roles         = ['MANAGER', 'HR_ADMIN', 'SUPER_ADMIN']
    requires_confirmation = True
    required_params       = ['nomination_id']

    def execute(self, parameters: dict, user) -> dict:
        try:
            from apps.reviewer_workflow.services import decide_nomination

            nomination_id = parameters.get('nomination_id')
            nomination = decide_nomination(nomination_id, 'APPROVED', user)
            peer_name     = nomination.peer.get_full_name()
            reviewee_name = nomination.reviewee.get_full_name()

            return {
                "success": True,
                "message": f"Nomination approved: {peer_name} will review {reviewee_name}.",
                "data": {"nomination_id": str(nomination.id), "status": "APPROVED"}
            }
        except (ValidationError, PermissionDenied, NotFound) as e:
            return {"success": False, "message": _service_error_message(e), "data": {}}
        except Exception as e:
            logger.error(f"ApproveNominationCommand error: {e}")
            return {"success": False, "message": "Could not approve nomination. Please try again.", "data": {}}


class RejectNominationCommand(BaseCommand):
    """Reject a pending peer nomination with a reason."""
    allowed_roles         = ['MANAGER', 'HR_ADMIN', 'SUPER_ADMIN']
    requires_confirmation = True
    required_params       = ['nomination_id', 'rejection_note']

    def execute(self, parameters: dict, user) -> dict:
        try:
            from apps.reviewer_workflow.services import decide_nomination

            nomination_id  = parameters.get('nomination_id')
            rejection_note = parameters.get('rejection_note', '').strip()
            if not rejection_note:
                return {"success": False, "message": "A rejection reason is required.", "data": {}, "retry_field": "rejection_note"}

            nomination = decide_nomination(nomination_id, 'REJECTED', user, rejection_note=rejection_note)
            peer_name     = nomination.peer.get_full_name()
            reviewee_name = nomination.reviewee.get_full_name()

            return {
                "success": True,
                "message": f"Nomination rejected: {peer_name} will not review {reviewee_name}. Reason: {rejection_note}",
                "data": {"nomination_id": str(nomination.id), "status": "REJECTED"}
            }
        except (ValidationError, PermissionDenied, NotFound) as e:
            return {"success": False, "message": _service_error_message(e), "data": {}}
        except Exception as e:
            logger.error(f"RejectNominationCommand error: {e}")
            return {"success": False, "message": "Could not reject nomination. Please try again.", "data": {}}


class ApproveAllNominationsCommand(BaseCommand):
    """Bulk-approve all pending nominations for the user's team (managers) or all pending (HR/admin)."""
    allowed_roles         = ['MANAGER', 'HR_ADMIN', 'SUPER_ADMIN']
    requires_confirmation = True
    required_params       = []

    def execute(self, parameters: dict, user) -> dict:
        try:
            from apps.reviewer_workflow.services import decide_nomination
            from django.db import connection

            role = getattr(user, 'role', '')
            with connection.cursor() as cursor:
                if role == 'MANAGER':
                    cursor.execute("""
                        SELECT pn.id
                        FROM peer_nominations pn
                        JOIN review_cycles rc ON pn.cycle_id = rc.id
                        WHERE pn.reviewee_id IN (
                            SELECT employee_id FROM org_hierarchy WHERE manager_id = %s
                        )
                          AND pn.status = 'PENDING'
                          AND rc.state IN ('NOMINATION', 'FINALIZED', 'ACTIVE')
                    """, [str(user.id)])
                else:
                    cursor.execute("""
                        SELECT pn.id
                        FROM peer_nominations pn
                        JOIN review_cycles rc ON pn.cycle_id = rc.id
                        WHERE pn.status = 'PENDING'
                          AND rc.state IN ('NOMINATION', 'FINALIZED', 'ACTIVE')
                    """)
                nom_ids = [str(r[0]) for r in cursor.fetchall()]

            if not nom_ids:
                return {"success": False, "message": "No pending nominations found to approve.", "data": {}}

            approved = 0
            failed   = 0
            for nom_id in nom_ids:
                try:
                    decide_nomination(nom_id, 'APPROVED', user)
                    approved += 1
                except Exception:
                    failed += 1

            msg = f"Bulk approved {approved} nomination{'s' if approved != 1 else ''}."
            if failed:
                msg += f" {failed} could not be approved (may require individual review)."
            return {
                "success": True,
                "message": msg,
                "data": {"approved": approved, "failed": failed, "total": len(nom_ids)},
            }
        except Exception as e:
            logger.error(f"ApproveAllNominationsCommand error: {e}")
            return {"success": False, "message": "Could not bulk approve nominations. Please try again.", "data": {}}


class RetractNominationCommand(BaseCommand):
    """Remove a specific peer from the user's current nominations for a cycle."""
    allowed_roles         = ['EMPLOYEE', 'MANAGER', 'HR_ADMIN', 'SUPER_ADMIN']
    requires_confirmation = True
    required_params       = ['cycle_id', 'peer_email']

    def execute(self, parameters: dict, user) -> dict:
        try:
            from apps.reviewer_workflow.services import submit_nominations
            from apps.users.models import User as UserModel
            from apps.review_cycles.models import PeerNomination

            cycle_id   = parameters.get('cycle_id')
            peer_email = parameters.get('peer_email', '').strip().lower()

            try:
                peer = UserModel.objects.get(email__iexact=peer_email)
            except UserModel.DoesNotExist:
                return {"success": False, "message": f"No user found with email '{peer_email}'.", "data": {}, "retry_field": "peer_email"}

            current_noms = PeerNomination.objects.filter(
                cycle_id=cycle_id, reviewee=user
            ).select_related('peer')
            current_peer_ids = [str(n.peer.id) for n in current_noms]

            if str(peer.id) not in current_peer_ids:
                peer_name = peer.get_full_name()
                return {"success": False, "message": f"{peer_name} is not in your current nominations for this cycle.", "data": {}}

            new_peer_ids = [pid for pid in current_peer_ids if pid != str(peer.id)]
            remaining    = submit_nominations(cycle_id, user, new_peer_ids)
            peer_name    = peer.get_full_name()
            return {
                "success": True,
                "message": f"Removed {peer_name} from your nominations. {remaining.count()} peer(s) remaining.",
                "data":    {"remaining_count": remaining.count()},
            }
        except (ValidationError, PermissionDenied, NotFound) as e:
            return {"success": False, "message": _service_error_message(e), "data": {}}
        except Exception as e:
            logger.error(f"RetractNominationCommand error: {e}")
            return {"success": False, "message": "Could not remove the nomination. Please try again.", "data": {}}


class CreateTemplateFromTextCommand(BaseCommand):
    """Parse a pasted block of questions/text and create a fully structured review template."""
    allowed_roles         = ['HR_ADMIN', 'SUPER_ADMIN']
    requires_confirmation = True
    required_params       = ['name', 'content']

    def execute(self, parameters: dict, user) -> dict:
        try:
            from apps.review_cycles.services import create_template
            from .. import llm_service as _llm

            template_name = parameters.get('name', '').strip()
            content       = parameters.get('content', '').strip()

            if not template_name:
                return {"success": False, "message": "Template name cannot be blank.", "data": {}, "retry_field": "name"}
            if not content:
                return {"success": False, "message": "No content provided to parse.", "data": {}, "retry_field": "content"}

            sections = _llm.parse_template_content(content)
            template = create_template(template_name, None, sections, user)
            q_count  = sum(len(s.get('questions', [])) for s in sections)
            s_count  = len(sections)
            return {
                "success": True,
                "message": (
                    f"Template '{template.name}' created with {s_count} section(s) "
                    f"and {q_count} question(s). Open the Templates page to review and edit."
                ),
                "data": {"template_id": str(template.id), "name": template.name,
                         "sections": s_count, "questions": q_count},
            }
        except (ValidationError, PermissionDenied, NotFound) as e:
            err_msg = _service_error_message(e)
            return {"success": False, "message": err_msg, "data": {},
                    "retry_field": "name" if "name" in err_msg.lower() else None}
        except Exception as e:
            logger.error(f"CreateTemplateFromTextCommand error: {e}")
            return {"success": False, "message": "Could not create template. Please try again.", "data": {}}


class CreateTemplateFromPDFCommand(BaseCommand):
    """
    LLM-driven conversational PDF → template creation.

    The user uploads a PDF/TXT file. The LLM reads the extracted text and
    chats naturally with the user:
      • Shows what it found (sections/questions)
      • Lets the user add, remove, rename, reorder sections/questions
      • Lets the user add manual questions not in the PDF
      • Answers questions about PDF content
      • When user confirms, outputs __CREATE_TEMPLATE__:{json} signal
        which the stream handler intercepts to create the template

    Session state:
      parameters.pdf_text      : extracted PDF text (set on first call)
      parameters.pdf_history   : [{role, content}] conversation so far
      parameters._pdf_reply    : user's latest reply (cleared each turn)
    """
    allowed_roles         = ['HR_ADMIN', 'SUPER_ADMIN']
    requires_confirmation = False
    required_params       = []   # no slot fill — LLM handles everything

    _CANCEL_WORDS = frozenset({
        'abandon', 'cancel', 'stop', 'quit', 'exit',
        'cancel pdf', 'start over', 'nevermind', 'forget it',
    })

    def execute(self, parameters: dict, user) -> dict:
        content   = parameters.get('content', '').strip()
        pdf_reply = parameters.get('_pdf_reply', '').strip()
        pdf_text  = parameters.get('pdf_text') or content
        pdf_history = list(parameters.get('pdf_history') or [])

        # ── Handle explicit cancel ─────────────────────────────────────────────
        if pdf_reply.lower() in self._CANCEL_WORDS:
            return {
                "success": True,
                "message": "Template creation cancelled. Let me know if you'd like to start again.",
                "data":    {},
            }

        # ── Determine the user's message for this turn ────────────────────────
        if not parameters.get('pdf_text') and content:
            # First call: PDF just uploaded — greet with analysis request
            user_msg = "I've uploaded a document for you to analyze. Please read it and suggest a feedback template structure."
        else:
            user_msg = pdf_reply

        if not user_msg:
            return {
                "success": False,
                "message": "I didn't receive any content. Please upload a PDF or document file.",
                "data":    {},
            }

        # Append user turn to history
        pdf_history.append({"role": "user", "content": user_msg})

        # Update parameters in-place so _run_pipeline saves them to session
        parameters['pdf_text']   = pdf_text
        parameters['pdf_history'] = pdf_history
        parameters.pop('_pdf_reply', None)
        parameters.pop('content', None)

        return {
            "_pdf_needed":        True,
            "_pdf_user_message":  user_msg,
            "success":            False,
            "message":            "",
            "data":               {},
        }

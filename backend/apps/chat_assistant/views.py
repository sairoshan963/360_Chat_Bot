import json
import uuid
import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
import datetime
from django.db import connection
from django.db.models import Count
from django.db.models.functions import TruncDay
from django.http import StreamingHttpResponse
from django.utils import timezone

from .serializers import ChatMessageSerializer, ChatConfirmSerializer, ChatLogSerializer
from .models import ChatLog
from . import intent_parser, session_manager, chat_logger, llm_service, data_context_fetcher
from .command_registry import get_command, is_known_intent, COMMAND_REGISTRY

logger = logging.getLogger(__name__)


# Intents that need cycle_id — show cycle list first
CYCLE_PICK_INTENTS = {'cancel_cycle', 'release_results', 'activate_cycle', 'close_cycle', 'finalize_cycle', 'nominate_peers', 'retract_nomination', 'show_cycle_results', 'remind_team', 'export_nominations'}

# Which cycle states are valid for each action
CYCLE_PICK_STATES = {
    'cancel_cycle':        ['DRAFT', 'NOMINATION', 'FINALIZED', 'ACTIVE'],
    'release_results':     ['CLOSED'],
    'activate_cycle':      ['DRAFT'],
    'close_cycle':         ['ACTIVE'],
    'finalize_cycle':      ['NOMINATION'],
    'nominate_peers':      ['NOMINATION'],
    'retract_nomination':  ['NOMINATION'],
    'show_cycle_results':  ['CLOSED', 'RESULTS_RELEASED', 'ARCHIVED'],
    'remind_team':         ['ACTIVE', 'NOMINATION', 'FINALIZED'],
    'export_nominations':  ['NOMINATION', 'FINALIZED', 'ACTIVE', 'CLOSED', 'RESULTS_RELEASED'],
}

# Friendly display names for cycle states shown in user-facing messages
_FRIENDLY_STATES = {
    'DRAFT':            'Draft',
    'NOMINATION':       'Nomination',
    'FINALIZED':        'Finalized',
    'ACTIVE':           'Active',
    'CLOSED':           'Closed',
    'RESULTS_RELEASED': 'Results Released',
    'ARCHIVED':         'Archived',
}

# Intents that need nomination_id — show nomination list first
NOMINATION_PICK_INTENTS = {'approve_nomination', 'reject_nomination'}

# Intents that need template_id — show template list first
TEMPLATE_PICK_INTENTS = {'create_cycle'}


def _fetch_nominations_for_picker(user) -> list:
    """Fetch PENDING team nominations (with nomination_id) so the user can pick one to approve/reject."""
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT pn.id,
                   u_reviewee.first_name || ' ' || u_reviewee.last_name AS reviewee,
                   u_peer.first_name || ' ' || u_peer.last_name AS peer,
                   u_peer.email AS peer_email,
                   rc.name AS cycle
            FROM peer_nominations pn
            JOIN users u_reviewee ON pn.reviewee_id = u_reviewee.id
            JOIN users u_peer     ON pn.peer_id     = u_peer.id
            JOIN review_cycles rc ON pn.cycle_id    = rc.id
            WHERE pn.reviewee_id IN (
                SELECT employee_id FROM org_hierarchy WHERE manager_id = %s
            )
              AND pn.status = 'PENDING'
              AND rc.state IN ('NOMINATION', 'FINALIZED', 'ACTIVE')
            ORDER BY u_reviewee.first_name, rc.created_at DESC
            LIMIT 20
        """, [str(user.id)])
        rows = cursor.fetchall()
    return [
        {"nomination_id": str(r[0]), "reviewee": r[1], "peer": r[2], "email": r[3], "cycle": r[4]}
        for r in rows
    ]


def _fetch_user_own_nominations(cycle_id: str, user) -> list:
    """Fetch the current user's own peer nominations for a cycle (for retract picker)."""
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT u_peer.email,
                   u_peer.first_name || ' ' || u_peer.last_name AS name,
                   pn.status
            FROM peer_nominations pn
            JOIN users u_peer ON pn.peer_id = u_peer.id
            WHERE pn.cycle_id = %s AND pn.reviewee_id = %s
            ORDER BY u_peer.first_name
        """, [cycle_id, str(user.id)])
        rows = cursor.fetchall()
    return [{"email": r[0], "name": r[1], "status": r[2]} for r in rows]


def _resolve_nomination_by_input(input_str: str, user):
    """
    Try to find a nomination_id from user input — supports:
    - Direct UUID
    - Numeric index (1-based) matching position in the picker list
    - Peer/reviewee name substring match (unambiguous only)
    Returns (nomination_id_or_None, is_ambiguous_bool).
    """
    text = input_str.strip()

    # Direct UUID
    try:
        import uuid as _uuid
        _uuid.UUID(text)
        return text, False
    except ValueError:
        pass

    nominations = _fetch_nominations_for_picker(user)
    if not nominations:
        return None, False

    # Numeric index (1-based)
    if text.isdigit():
        idx = int(text) - 1
        if 0 <= idx < len(nominations):
            return nominations[idx]['nomination_id'], False
        return None, False

    # Name substring match — search peer name, reviewee name, email
    lower = text.lower()
    matches = [
        n for n in nominations
        if lower in n['peer'].lower() or lower in n['reviewee'].lower() or lower in n['email'].lower()
    ]
    if len(matches) == 1:
        return matches[0]['nomination_id'], False
    if len(matches) > 1:
        return None, True  # Ambiguous — multiple nominations match
    return None, False


def _fetch_cycles_for_intent(intent: str) -> list:
    """Fetch cycles relevant to the given action intent."""
    from apps.review_cycles.models import ReviewCycle
    states = CYCLE_PICK_STATES.get(intent)
    if not states:
        return []
    cycles = ReviewCycle.objects.filter(state__in=states).order_by('-created_at')[:10]
    return [{"id": str(c.id), "name": c.name, "state": c.state} for c in cycles]


def _fetch_templates() -> list:
    """Fetch active templates for create_cycle picker."""
    from apps.review_cycles.models import Template
    return [
        {"id": str(t.id), "name": t.name}
        for t in Template.objects.filter(is_active=True).order_by('created_at')[:10]
    ]


def _resolve_template_by_input(input_str: str) -> str | None:
    """Resolve template name, number, or UUID to a template_id string."""
    from apps.review_cycles.models import Template
    text = input_str.strip()

    # Direct UUID
    try:
        import uuid as _uuid
        val = str(_uuid.UUID(text))
        if Template.objects.filter(id=val, is_active=True).exists():
            return val
        return None
    except ValueError:
        pass

    templates = list(Template.objects.filter(is_active=True).order_by('created_at')[:10])
    if not templates:
        return None

    # Numeric index (1-based)
    if text.isdigit():
        idx = int(text) - 1
        return str(templates[idx].id) if 0 <= idx < len(templates) else None

    # Exact name match first, then fuzzy
    lower = text.lower()
    exact = [t for t in templates if t.name.lower() == lower]
    if exact:
        return str(exact[0].id)
    fuzzy = [t for t in templates if lower in t.name.lower()]
    return str(fuzzy[0].id) if len(fuzzy) == 1 else None


def _resolve_cycle_by_name(name_input: str) -> str | None:
    """
    Try to find a cycle_id from a user-typed name.
    - Exact match always wins (unambiguous).
    - Fuzzy LIKE match only succeeds when exactly ONE cycle matches;
      if multiple cycles match, return None so the picker list is shown again.
    """
    lower = name_input.lower().strip()
    try:
        with connection.cursor() as cursor:
            # 1. Exact match
            cursor.execute(
                "SELECT id FROM review_cycles WHERE LOWER(name) = %s LIMIT 1", [lower]
            )
            row = cursor.fetchone()
            if row:
                return str(row[0])

            # 2. Fuzzy match — only if unambiguous (exactly one result)
            # Escape LIKE wildcards to prevent injection
            escaped_lower = lower.replace('%', '\\%').replace('_', '\\_')
            cursor.execute(
                "SELECT id FROM review_cycles WHERE LOWER(name) LIKE %s ESCAPE '\\'",
                [f'%{escaped_lower}%']
            )
            rows = cursor.fetchall()
            return str(rows[0][0]) if len(rows) == 1 else None
    except Exception:
        logger.warning("_resolve_cycle_by_name failed for input %r", name_input)
        return None


class ChatMessageView(APIView):
    """POST /api/v1/chat/message/ — process a user chat message."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChatMessageSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user            = request.user
        message         = serializer.validated_data['message']
        display_message = serializer.validated_data.get('display_message') or message
        session_id      = serializer.validated_data.get('session_id') or str(uuid.uuid4())

        # ── PIPELINE STAGE 1: Input received ─────────────────────────────────
        logger.debug(
            "\n%s\n  USER    : %s  [%s]\n  MESSAGE : %r\n%s",
            "─" * 60,
            user.email, getattr(user, 'role', '?'),
            message,
            "─" * 60,
        )

        # Rate limiting
        allowed, reason = session_manager.check_rate_limit(str(user.id))
        if not allowed:
            logger.warning("  ⚠  RATE LIMIT  : %s", reason)
            resp = Response({"error": reason}, status=status.HTTP_429_TOO_MANY_REQUESTS)
            resp['X-RateLimit-Limit-Minute'] = str(session_manager.MAX_PER_MIN)
            resp['X-RateLimit-Limit-Hour']   = str(session_manager.MAX_PER_HOUR)
            resp['Retry-After'] = '60'
            return resp

        # ── Per-user lock: prevent race condition from multi-tab simultaneous sends ──
        if not session_manager.acquire_lock(str(user.id)):
            logger.warning("  ⚠  LOCK : concurrent request blocked for user %s", user.id)
            return Response({
                "status":  "error",
                "message": "Your previous message is still being processed. Please wait a moment.",
            }, status=status.HTTP_429_TOO_MANY_REQUESTS)

        try:
            return self._process(request, user, message, display_message, session_id)
        finally:
            session_manager.release_lock(str(user.id))

    def _process(self, request, user, message, display_message, session_id):
        """Thin wrapper — calls _run_pipeline() then wraps in DRF Response."""
        is_new_session = not ChatLog.objects.filter(session_id=session_id).exists()
        payload = _run_pipeline(user, message, display_message, session_id)
        if is_new_session:
            chat_logger.maybe_generate_title(session_id, display_message or message)

        if payload.get("_llm_needed"):
            # Synchronous LLM call (non-streaming path)
            llm_user_message = payload.pop("_llm_user_message")
            llm_system_data  = payload.pop("_llm_system_data")
            llm_fallback     = payload.pop("_llm_fallback")
            log_user         = payload.pop("_log_user")
            log_session      = payload.pop("_log_session")
            log_display      = payload.pop("_log_display")
            log_used_llm     = payload.pop("_log_used_llm")
            payload.pop("_llm_needed")
            try:
                llm_reply    = llm_service.generate_response(llm_user_message, llm_system_data)
                response_msg = llm_reply if llm_reply else llm_fallback
            except Exception:
                response_msg = llm_fallback
            chat_logger.log_interaction(
                log_user, log_session, log_display,
                'unknown', {}, 'clarify', response_msg, log_used_llm,
                response_data={},
            )
            payload["message"] = response_msg

        return Response(payload)


def _run_pipeline(user, message, display_message, session_id):
    """Core chat pipeline — returns a plain dict (no DRF Response wrapper).

    When the intent is unknown and the LLM needs to generate a reply the dict
    contains ``_llm_needed: True`` plus context keys prefixed with ``_``.
    Callers handle the actual LLM call (sync or streaming) and set
    ``payload["message"]`` before sending to the client.
    """
    # Get current session state
    session = session_manager.get_session(str(user.id))

    # ── PIPELINE STAGE 2: Session state ───────────────────────────────────
    session_intent  = session.get('intent')
    session_missing = session.get('missing_fields', [])
    _session_state = (
        f"awaiting confirmation for '{session_intent}'" if session.get('awaiting_confirm')
        else f"slot-filling '{session_intent}' → missing {session_missing}" if session_intent and session_missing
        else f"continuing '{session_intent}'" if session_intent
        else "fresh (no active session)"
    )
    logger.debug("  SESSION : %s", _session_state)

    # ── STARTUP GREETING ──────────────────────────────────────────────────────
    if message.strip() == '__startup__':
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT COUNT(*) FROM reviewer_tasks rt
                    JOIN review_cycles rc ON rt.cycle_id = rc.id
                    WHERE rt.reviewer_id = %s
                      AND rt.status IN ('CREATED','PENDING','IN_PROGRESS')
                      AND rc.state = 'ACTIVE'
                """, [str(user.id)])
                pending_reviews = cursor.fetchone()[0]

                pending_noms = 0
                if user.role in ('MANAGER', 'HR_ADMIN', 'SUPER_ADMIN'):
                    cursor.execute("""
                        SELECT COUNT(*) FROM peer_nominations pn
                        JOIN review_cycles rc ON pn.cycle_id = rc.id
                        WHERE pn.reviewee_id IN (
                            SELECT employee_id FROM org_hierarchy WHERE manager_id = %s
                        )
                          AND pn.status = 'PENDING'
                          AND rc.state IN ('NOMINATION','FINALIZED','ACTIVE')
                    """, [str(user.id)])
                    pending_noms = cursor.fetchone()[0]

            name = user.display_name or user.get_full_name() or user.email.split('@')[0]
            parts = []
            if pending_reviews:
                parts.append(f"**{pending_reviews}** pending review(s) to submit")
            if pending_noms:
                parts.append(f"**{pending_noms}** nomination(s) awaiting your approval")

            if parts:
                msg = f"Hi {name}! You have {' and '.join(parts)}.\n\nWhat would you like to do?"
            else:
                msg = f"Hi {name}! Everything looks clear — no pending reviews or approvals. What would you like to do?"

            return {
                "session_id": session_id, "intent": "__greeting__",
                "status": "success", "message": msg,
                "data": {"pending_reviews": pending_reviews, "pending_nominations": pending_noms},
                "needs_input": False,
            }
        except Exception as e:
            logger.error("Startup greeting error: %s", e)
            return {
                "session_id": session_id, "intent": "__greeting__",
                "status": "success", "message": "Hi! What would you like to do?",
                "data": {}, "needs_input": False,
            }

    # ── Cancel escape: "cancel" / "stop" / "quit" at any point clears session ─
    if message.strip().lower() in ('cancel', 'stop', 'quit', 'exit', 'nevermind', 'never mind'):
        if session.get('intent'):
            session_manager.clear_session(str(user.id))
            logger.debug("  ⚠  USER CANCELLED — session cleared")
            return {
                "session_id": session_id,
                "intent":     "cancel",
                "status":     "cancelled",
                "message":    "Cancelled. What would you like to do next?",
                "data":       {},
            }
        # No active session — treat as unknown input, fall through to normal flow

    # ── Inline field edit: intercept 'change X to Y' messages during confirmation ─
    if session.get('awaiting_confirm'):
        edit = _try_parse_inline_edit(message, session)
        if edit:
            updated_params = {**session.get('parameters', {}), **edit}
            session['parameters'] = updated_params
            session_manager.save_session(str(user.id), session)

            edited_key   = next(iter(edit))
            confirm_msg  = _build_confirmation_summary(session['intent'], updated_params)
            conf_display = dict(updated_params)
            if 'cycle_id'      in conf_display: conf_display['cycle_name']          = _get_cycle_name(conf_display.pop('cycle_id'))
            if 'nomination_id' in conf_display: conf_display['nomination_summary']  = _get_nomination_summary(conf_display.pop('nomination_id'))
            if 'template_id'   in conf_display: conf_display['template_name']       = _get_template_name(conf_display.pop('template_id'))

            edited_label = edited_key.replace('_', ' ')
            logger.debug("  INLINE EDIT : updated '%s' → %r", edited_key, edit[edited_key])
            chat_logger.log_interaction(
                user, session_id, display_message, session['intent'], updated_params,
                'awaiting_confirm', confirm_msg, False, response_data=conf_display,
            )
            return {
                "session_id":       session_id,
                "intent":           session['intent'],
                "status":           "awaiting_confirmation",
                "message":          f"Updated **{edited_label}**. Please confirm:\n\n{confirm_msg}",
                "data":             conf_display,
                "needs_input":      False,
                "requires_confirm": True,
            }

    # If a confirmation is pending and the user sends a new message, auto-cancel it and proceed
    if session.get('awaiting_confirm'):
        pending_intent = session.get('intent', 'action')
        logger.debug("  ⚠  PENDING CONFIRM for '%s' — auto-cancelled by new message", pending_intent)
        session_manager.clear_session(str(user.id))
        session = {}

    # ── Context reference resolver: "cancel the second one", "activate it" ──
    if not session.get('intent') and not session.get('awaiting_confirm'):
        _resolved = _resolve_context_reference(message, session)
        if _resolved:
            intent_override, params_override = _resolved
            logger.debug("  CTX REF   : resolved '%s' → intent=%s params=%s", message, intent_override, params_override)
            from .command_registry import get_command as _get_cmd
            _cmd = _get_cmd(intent_override)
            if _cmd and user.role in _cmd.allowed_roles:
                _result = _cmd.execute(params_override, user)
                session_manager.clear_session(str(user.id))
                _status = 'success' if _result.get('success') else 'error'
                chat_logger.log_interaction(user, session_id, display_message or message, intent_override, params_override, _status, _result.get('message',''), False, response_data=_result.get('data',{}))
                return {
                    "session_id": session_id, "intent": intent_override,
                    "status": _status, "message": _result.get('message',''),
                    "data": _result.get('data', {}), "needs_input": False,
                }

    # ── Follow-up detection: route to agent when user references previous response ─
    # Must run BEFORE intent detection so "deadline for task 2" isn't misclassified
    # as show_cycle_deadlines when the user actually meant a specific task from history.
    _user_role = getattr(user, 'role', '')
    if not session.get('intent') and not session.get('awaiting_confirm'):
        from .agent_tools import is_followup_question
        _followup_history = session_manager.get_chat_history(str(user.id))
        if is_followup_question(message, _followup_history):
            logger.debug("  FOLLOWUP  : detected reference to previous response → agent")
            _employee_followup = (_user_role == 'EMPLOYEE')
            return {
                "_agent_needed":        True,
                "_agent_message":       message,
                "_agent_employee_mode": _employee_followup,
                "_log_user":            user,
                "_log_session":         session_id,
                "_log_display":         display_message,
                "session_id":           session_id,
                "intent":               "followup_query",
                "status":               "clarify",
                "data":                 {},
                "needs_input":          False,
            }

    # ── Phase 4: Early data-analysis bypass (SUPER_ADMIN / HR_ADMIN only) ───
    # Must happen BEFORE intent detection so the intent parser cannot intercept
    # data analysis questions and misclassify them as known commands.
    if (not session.get('intent') and not session.get('awaiting_confirm') and
            _user_role in ('SUPER_ADMIN', 'HR_ADMIN') and
            data_context_fetcher.is_strong_data_analysis_question(message)):
        _ctx = data_context_fetcher.fetch_context(user, message)
        if _ctx:
            logger.debug("  DATA CTX  : early bypass — context types=%s", list(_ctx.keys()))
            return {
                "_llm_needed":       True,
                "_data_analysis":    True,
                "_llm_user_message": message,
                "_llm_system_data":  _ctx,
                "_llm_fallback":     "I was unable to analyze the data at this time. Please try again.",
                "_log_user":         user,
                "_log_session":      session_id,
                "_log_display":      display_message,
                "_log_used_llm":     True,
                "session_id":        session_id,
                "intent":            "data_analysis",
                "status":            "clarify",
                "data":              {},
                "needs_input":       False,
            }
    # ── End Phase 4 early bypass ─────────────────────────────────────────────

    # ── PIPELINE STAGE 3: Intent detection ───────────────────────────────
    conversation_context  = session.get('context', '')
    conversation_history  = session_manager.get_chat_history(str(user.id))
    parsed = intent_parser.parse_intent(message, conversation_context, conversation_history)
    intent    = parsed['intent']
    params    = parsed['parameters']
    used_llm  = parsed.get('used_llm', False)
    logger.debug(
        "  INTENT  : %s  [%s]%s",
        intent,
        "LLM" if used_llm else "rule-based",
        f"  params={params}" if params else "",
    )

    # ── PIPELINE STAGE 4: Slot-fill merge ────────────────────────────────
    _awaiting_cycle_id      = session.get('missing_fields', [])[:1] == ['cycle_id']
    _awaiting_nomination_id = session.get('missing_fields', [])[:1] == ['nomination_id']
    # Free-text fields: the user is answering a plain question; treat ANY message as
    # the slot value regardless of what the intent-parser returns.  This prevents the
    # LLM from misclassifying an answer like "Engineering Review 2026" as a command.
    _FREE_TEXT_FIELDS = {
        'name', 'description', 'quarter_year', 'review_deadline',
        'nomination_deadline', 'nomination_approval', 'peer_enabled',
        'peer_count', 'participant_emails', 'peer_emails', 'rejection_note',
        'content', 'peer_email',
        # PDF conversation follow-up replies
        '_pdf_reply',
        # Legacy PDF clarification answers
        '_confirm_answer',
        'clarif_confirm_sections', 'clarif_section_headers',
        'clarif_ambiguous_types', 'clarif_mandatory',
    }
    _first_missing_field = (session.get('missing_fields') or [None])[0]
    _awaiting_free_text  = (
        _first_missing_field in _FREE_TEXT_FIELDS or
        (isinstance(_first_missing_field, str) and (
            _first_missing_field.startswith('clarif_') or
            _first_missing_field == '_confirm_answer'
        ))
    )

    if session.get('intent') and session.get('intent') == intent:
        # Only let newly-parsed params fill fields that are still missing.
        # Already-filled session fields must NOT be overwritten by intent-parser
        # side-effects (e.g. "Annual review for product team" as a description
        # answer should never overwrite a previously stored cycle name).
        _session_params  = session.get('parameters', {})
        _missing_set     = set(session.get('missing_fields', []))
        _safe_new_params = {k: v for k, v in params.items() if k in _missing_set}
        merged_params    = {**_session_params, **_safe_new_params}
        _first_missing = _first_missing_field
        # If the message itself is a re-trigger of the same command (user typed the
        # command phrase again instead of answering the slot question), start fresh.
        _is_command_retrigger = (
            _first_missing and
            not merged_params.get(_first_missing) and
            not params.get(_first_missing) and
            len(params) == 0  # intent matched but extracted zero new slot values
        )
        if _is_command_retrigger:
            logger.debug("  SLOT    : same-intent re-trigger detected — starting fresh")
            session_manager.clear_session(str(user.id))
            merged_params = {}
        elif _first_missing and not merged_params.get(_first_missing):
            merged_params[_first_missing] = message
        logger.debug("  SLOT    : filling '%s' from message", _first_missing)
    elif session.get('intent') and session.get('missing_fields') and (
        not is_known_intent(intent) or
        (_awaiting_cycle_id and intent == session.get('intent')) or
        (_awaiting_nomination_id and intent == session.get('intent')) or
        _awaiting_free_text  # free-text answer always wins over intent re-classification
    ):
        intent        = session['intent']
        missing       = session.get('missing_fields', [])
        merged_params = {**session.get('parameters', {})}
        if missing:
            merged_params[missing[0]] = message
        logger.debug("  SLOT    : answer for '%s' → value saved", missing[0] if missing else '?')
    else:
        if session.get('intent') and session.get('intent') != intent:
            logger.debug(
                "  SLOT    : command switched %s → %s  (session cleared)",
                session.get('intent'), intent
            )
            session_manager.clear_session(str(user.id))
        merged_params = params

    # P3-F3: Resolve numeric peer pick for retract_nomination
    if intent == 'retract_nomination' and 'peer_email' in merged_params:
        raw_peer = str(merged_params.get('peer_email', '')).strip()
        if raw_peer.isdigit():
            opts = session.get('peer_options', [])
            idx  = int(raw_peer) - 1
            if opts and 0 <= idx < len(opts):
                merged_params['peer_email'] = opts[idx]['email']
                logger.debug("  RESOLVE : peer pick '%s' → %s", raw_peer, merged_params['peer_email'])
            elif opts:
                chat_logger.log_interaction(
                    user, session_id, display_message, intent, merged_params,
                    'needs_input', f"Invalid choice. Please pick 1–{len(opts)}.", used_llm, response_data={},
                )
                return {
                    "session_id":    session_id, "intent": intent, "status": "needs_input",
                    "message":       f"Invalid choice. Please pick a number between 1 and {len(opts)}.",
                    "data":          {"current_nominations": opts},
                    "needs_input":   True, "missing_field": "peer_email",
                }

    # B4: "Did you mean?" — fuzzy match was medium-confidence, ask user to confirm
    if not is_known_intent(intent) and parsed.get('suggestion'):
        suggestion_phrase = parsed.get('suggestion_phrase', parsed['suggestion'].replace('_', ' '))
        chat_logger.log_interaction(
            user, session_id, display_message or message,
            "unknown_with_suggestion", {}, "clarify",
            f"Did you mean: {suggestion_phrase}?", False,
            response_data={},
        )
        return {
            "session_id":  session_id,
            "intent":      "unknown_with_suggestion",
            "status":      "clarify",
            "message":     f"Did you mean: **{suggestion_phrase}**?",
            "data":        {"commands": [suggestion_phrase]},
            "needs_input": False,
        }

    # Unknown intent — signal caller to generate LLM response (streaming or sync)
    if not is_known_intent(intent):

        # ── Agent: data / analytics questions (replaces Phase 4 fallback) ─────
        # Phase 4 early bypass (strong questions) already ran above.
        # For broader data questions that reached here, route to the tool-calling
        # agent instead of pre-fetching a fixed context snapshot.
        from .agent_tools import is_agent_question, is_employee_self_query

        # EMPLOYEE: limited self-scoped agent for natural-language self queries
        if _user_role == 'EMPLOYEE' and is_employee_self_query(message):
            logger.debug("  AGENT   : routing EMPLOYEE to self-scoped agent")
            return {
                "_agent_needed":       True,
                "_agent_message":      message,
                "_agent_employee_mode": True,
                "_log_user":           user,
                "_log_session":        session_id,
                "_log_display":        display_message,
                "session_id":          session_id,
                "intent":              "agent_query",
                "status":              "clarify",
                "data":                {},
                "needs_input":         False,
            }

        # SUPER_ADMIN / HR_ADMIN / MANAGER: full or team-scoped agent
        if _user_role in ('SUPER_ADMIN', 'HR_ADMIN', 'MANAGER') and (
            is_agent_question(message) or data_context_fetcher.is_data_analysis_question(message)
        ):
            logger.debug("  AGENT   : routing to tool-calling agent")
            return {
                "_agent_needed":  True,
                "_agent_message": message,
                "_log_user":      user,
                "_log_session":   session_id,
                "_log_display":   display_message,
                "session_id":     session_id,
                "intent":         "agent_query",
                "status":         "clarify",
                "data":           {},
                "needs_input":    False,
            }

        # ── App knowledge: questions about how the app works ─────────────────
        from .app_knowledge import is_app_knowledge_question, get_static_answer
        if is_app_knowledge_question(message):
            logger.debug("  APP FAQ : routing to app knowledge layer")
            _static = get_static_answer(message)
            if _static:
                # Option A: instant static answer, no LLM
                chat_logger.log_interaction(
                    user, session_id, display_message or message,
                    'app_knowledge', {}, 'success', _static, False, response_data={},
                )
                session_manager.append_chat_history(str(user.id), 'assistant', _static)
                return {
                    "session_id":  session_id,
                    "intent":      "app_knowledge",
                    "status":      "success",
                    "message":     _static,
                    "data":        {},
                    "needs_input": False,
                }
            # Option B: LLM fallback (command-light) with conversation memory
            return {
                "_app_knowledge":    True,
                "_ak_message":       message,
                "_log_user":         user,
                "_log_session":      session_id,
                "_log_display":      display_message,
                "session_id":        session_id,
                "intent":            "app_knowledge",
                "status":            "clarify",
                "data":              {},
                "needs_input":       False,
            }

        # ── Out-of-scope: question is not related to the 360 system ──────────
        _role_hints = {
            'EMPLOYEE':    "your tasks, feedback, nominations, and cycles",
            'MANAGER':     "your team's nominations, pending reviews, and cycle summaries",
            'HR_ADMIN':    "cycles, participation stats, templates, employees, and analytics",
            'SUPER_ADMIN': "cycles, employees, analytics, audit logs, and org overview",
        }
        _hint = _role_hints.get(_user_role, "the 360° feedback system")
        out_of_scope_msg = (
            f"I'm Gamyam AI, specialized for your 360° feedback system. "
            f"I can help you with {_hint}.\n\n"
            "I'm not able to answer questions outside that scope. "
            "What would you like to know about your feedback system?"
        )
        chat_logger.log_interaction(
            user, session_id, display_message or message,
            'out_of_scope', {}, 'clarify', out_of_scope_msg, False,
            response_data={},
        )
        return {
            "session_id":  session_id,
            "intent":      "out_of_scope",
            "status":      "clarify",
            "message":     out_of_scope_msg,
            "data":        {},
            "needs_input": False,
        }

    # ── PIPELINE STAGE 5: Command selection + permission check ───────────
    command = get_command(intent)
    logger.debug("  COMMAND : %s", type(command).__name__)

    # Permission check
    if not command.check_permission(user):
        role_label = getattr(user, 'role', 'your role').replace('_', ' ').title()
        allowed    = ', '.join(r.replace('_', ' ').title() for r in command.allowed_roles)
        response_msg = f"This action isn't available for {role_label}. It requires: {allowed}."
        logger.debug(
            "  PERMISSION : ⛔ DENIED  [%s] cannot run '%s'",
            getattr(user, 'role', '?'), intent
        )
        chat_logger.log_interaction(
            user, session_id, display_message, intent, merged_params, 'rejected', response_msg, used_llm,
            response_data={},
        )
        return {
            "session_id":  session_id,
            "intent":      intent,
            "status":      "rejected",
            "message":     response_msg,
            "data":        {},
            "needs_input": False,
        }

    logger.debug(
        "  PERMISSION : ✓ ALLOWED  [%s] → '%s'",
        getattr(user, 'role', '?'), intent
    )

    # ── PIPELINE STAGE 6: Slot-fill resolution (cycle/nomination pickers) ─
    if session.get('missing_fields', [])[:1] == ['cycle_id']:
        msg_stripped = message.strip()
        # Option A: card click sends UUID directly — validate it's in the eligible list
        try:
            uuid.UUID(msg_stripped)
            eligible    = _fetch_cycles_for_intent(session.get('intent', ''))
            resolved_id = msg_stripped if any(c['id'] == msg_stripped for c in eligible) else None
        except ValueError:
            if msg_stripped.isdigit():
                # Numeric pick — resolve by 1-based index in the picker list
                eligible    = _fetch_cycles_for_intent(session.get('intent', ''))
                idx         = int(msg_stripped) - 1
                resolved_id = eligible[idx]['id'] if 0 <= idx < len(eligible) else None
            else:
                resolved_id = _resolve_cycle_by_name(message)
        if resolved_id:
            merged_params['cycle_id'] = resolved_id
            logger.debug("  RESOLVE : cycle '%s' → %s", msg_stripped, resolved_id[:8] + "...")
        else:
            merged_params.pop('cycle_id', None)
            logger.debug("  RESOLVE : cycle '%s' not found — re-showing picker", message)

    if session.get('missing_fields', [])[:1] == ['template_id'] and intent in TEMPLATE_PICK_INTENTS:
        resolved_tid = _resolve_template_by_input(message)
        if resolved_tid:
            merged_params['template_id'] = resolved_tid
            logger.debug("  RESOLVE : template '%s' → %s", message, resolved_tid[:8] + "...")
        else:
            merged_params.pop('template_id', None)
            logger.debug("  RESOLVE : template '%s' not found — re-showing picker", message)

    if session.get('missing_fields', [])[:1] == ['nomination_id']:
        resolved_nom, nom_ambiguous = _resolve_nomination_by_input(message, user)
        if resolved_nom:
            merged_params['nomination_id'] = resolved_nom
            logger.debug("  RESOLVE : nomination '%s' → %s", message, resolved_nom[:8] + "...")
        else:
            merged_params.pop('nomination_id', None)
            available_noms = _fetch_nominations_for_picker(user)
            logger.debug(
                "  RESOLVE : nomination '%s' → %s  (%d available)",
                message,
                "ambiguous (multiple matches)" if nom_ambiguous else "not found",
                len(available_noms)
            )

            # Out-of-range numeric pick — give clear feedback with bounds
            if message.strip().isdigit():
                pick = int(message.strip())
                return {
                    "session_id":    session_id,
                    "intent":        intent,
                    "status":        "needs_input",
                    "message":       f"Invalid choice '{pick}'. Please pick a number between 1 and {len(available_noms)}.",
                    "data":          {"available_nominations": available_noms},
                    "needs_input":   True,
                    "missing_field": "nomination_id",
                }

            if nom_ambiguous:
                # Return early with "multiple matches" error so the picker re-prompts
                # with an explanation rather than silently looping
                return {
                    "session_id":    session_id,
                    "intent":        intent,
                    "status":        "needs_input",
                    "message":       f"Multiple nominations match '{message}'. Please use the number (e.g. '1', '2') to select.",
                    "data":          {"available_nominations": available_noms},
                    "needs_input":   True,
                    "missing_field": "nomination_id",
                }

    # create_cycle: validate individual fields inline — pop invalid ones so they get re-asked
    if intent == 'create_cycle':
        import re as _re, datetime as _dt

        # quarter_year — must match "Q[1-4] YYYY" or be "skip"
        qy = merged_params.get('quarter_year', '')
        if qy and qy.lower() != 'skip':
            if not _re.match(r'^Q[1-4]\s+\d{4}$', qy.strip(), _re.IGNORECASE):
                merged_params.pop('quarter_year', None)

        # review_deadline — flexible natural language parsing
        dl = merged_params.get('review_deadline', '')
        if dl:
            parsed_dl = _parse_flexible_date(dl)
            if parsed_dl:
                merged_params['review_deadline'] = parsed_dl
            else:
                merged_params.pop('review_deadline', None)

        # nomination_deadline — flexible natural language parsing or "skip"
        ndl = merged_params.get('nomination_deadline', '')
        if ndl and ndl.lower() != 'skip':
            parsed_ndl = _parse_flexible_date(ndl)
            if parsed_ndl:
                merged_params['nomination_deadline'] = parsed_ndl
            else:
                merged_params.pop('nomination_deadline', None)

        # nomination_approval — must be auto/manual/skip; anything else re-asks
        na = merged_params.get('nomination_approval', '').lower().strip()
        if na and na not in ('auto', 'manual', 'skip'):
            merged_params.pop('nomination_approval', None)

        # peer_enabled — must be yes/no only; anything else re-asks
        peer_val = merged_params.get('peer_enabled', '').lower().strip()
        if peer_val:
            if peer_val in ('no', 'false', 'n', '0'):
                merged_params.setdefault('peer_count', 'skip')
            elif peer_val in ('yes', 'y', 'true', '1'):
                pass  # valid — leave as-is
            else:
                merged_params.pop('peer_enabled', None)  # invalid — re-ask

        # peer_count — validate numbers, min ≥ 1, min ≤ max; reject "skip" when peer enabled
        pc = merged_params.get('peer_count', '')
        if pc:
            _peer_on = merged_params.get('peer_enabled', '').lower().strip() in ('yes', 'y', 'true', '1')
            if pc == 'skip' and _peer_on:
                merged_params.pop('peer_count', None)  # can't skip when peer review is enabled
            elif pc != 'skip':
                _nums = [int(x) for x in _re.findall(r'\d+', pc)]
                _ok = (
                    len(_nums) >= 1 and _nums[0] >= 1 and
                    (len(_nums) == 1 or _nums[0] <= _nums[1])
                )
                if not _ok:
                    merged_params.pop('peer_count', None)

    # Slot filling — check missing params
    missing = command.validate_params(merged_params)
    if missing:
        next_field   = missing[0]
        # D2: preserve total_fields from first slot-fill call so we can show "Step X of Y"
        total_fields = session.get('total_fields') or len(missing)
        session_data = {
            "intent":        intent,
            "parameters":    merged_params,
            "missing_fields": missing,
            "total_fields":  total_fields,
            "context":       conversation_context,
        }
        session_manager.save_session(str(user.id), session_data)

        # D2: helper to prepend "Step X of Y" to a prompt when multi-step
        def _step_prefix(base: str) -> str:
            sn = total_fields - len(missing) + 1
            return f"*Step {sn} of {total_fields}*\n{base}" if total_fields > 1 else base

        # For cycle_id on action commands — show available cycles list
        if next_field == 'cycle_id' and intent in CYCLE_PICK_INTENTS:
            cycles = _fetch_cycles_for_intent(intent)
            if cycles:
                cycle_lines = '\n'.join(
                    [f"  {i+1}. {c['name']} [{c['state']}]" for i, c in enumerate(cycles)]
                )
                response_msg = _step_prefix(f"Please choose a cycle by typing its name or number:\n{cycle_lines}")
                data = {"available_cycles": cycles}
            else:
                state_labels = ', '.join(_FRIENDLY_STATES.get(s, s) for s in CYCLE_PICK_STATES.get(intent, []))
                response_msg = f"No eligible cycles found. This action requires a cycle in {state_labels} state."
                data = {}

        # For template_id on create_cycle — show available templates list
        elif next_field == 'template_id' and intent in TEMPLATE_PICK_INTENTS:
            templates = _fetch_templates()
            if templates:
                tmpl_lines = '\n'.join(
                    [f"  {i+1}. {t['name']}" for i, t in enumerate(templates)]
                )
                response_msg = _step_prefix(f"Which template should this cycle use?\n{tmpl_lines}")
                data = {"available_templates": templates}
            else:
                response_msg = "No active templates found. Please create a template first."
                data = {}

        # For nomination_id on approve/reject — show pending nominations list
        elif next_field == 'nomination_id' and intent in NOMINATION_PICK_INTENTS:
            nominations = _fetch_nominations_for_picker(user)
            if nominations:
                nom_lines = '\n'.join([
                    f"  {i+1}. {n['peer']} reviewing {n['reviewee']} [{n['cycle']}]"
                    for i, n in enumerate(nominations)
                ])
                response_msg = _step_prefix(f"Please choose a nomination to {intent.split('_')[0]} by typing a name or number:\n{nom_lines}")
                data = {"available_nominations": nominations}
            else:
                response_msg = "No pending nominations found for your team."
                data = {}

        # P3-F3: peer_email picker for retract_nomination — show user's current nominations
        elif next_field == 'peer_email' and intent == 'retract_nomination':
            cycle_id = merged_params.get('cycle_id')
            noms     = _fetch_user_own_nominations(cycle_id, user) if cycle_id else []
            if noms:
                nom_lines = '\n'.join([
                    f"  {i+1}. {n['name']} ({n['email']}) — {n['status']}"
                    for i, n in enumerate(noms)
                ])
                response_msg = _step_prefix(
                    f"Your current nominations:\n{nom_lines}\n\n"
                    "Type the number or email address of the peer to remove."
                )
                session_data['peer_options'] = noms
                session_manager.save_session(str(user.id), session_data)
                data = {"current_nominations": noms}
            else:
                session_manager.clear_session(str(user.id))
                response_msg = "You haven't nominated anyone in this cycle yet."
                data = {}
            chat_logger.log_interaction(
                user, session_id, display_message, intent, merged_params, 'needs_input', response_msg, used_llm,
                response_data=data,
            )
            return {
                "session_id": session_id, "intent": intent, "status": "needs_input",
                "message": response_msg, "data": data,
                "needs_input": True, "missing_field": next_field,
            }

        else:
            prompt_map = {
                'name':                'What should be the name? (e.g. "Q3 2026 Engineering Review")',
                'department':          'Which department is this for?',
                'peer_emails':         'Please provide peer email addresses, comma-separated.\n*(Minimum 2, maximum 5 — e.g. emp1@gamyam.com, emp2@gamyam.com)*',
                'rejection_note':      'Please provide a reason for rejecting this nomination.\n*(e.g. "Not relevant to this cycle" or "Conflict of interest")*',
                'description':         'Add a description for this cycle, or type **skip**.',
                'quarter_year':        'Which quarter and year? (e.g. "Q3 2026") or type **skip**.',
                'review_deadline':     'When is the review deadline? (e.g. "Sep 30", "end of Q3", "in 2 weeks", "2026-09-30")',
                'nomination_deadline': 'When is the nomination deadline? (e.g. "Sep 15", "end of August") or type **skip**.',
                'nomination_approval': 'Should nominations require manual manager approval? Type **manual** or **auto** (or **skip** for auto).',
                'peer_enabled':        'Enable peer review? Please type **yes** or **no**.',
                'peer_count':          'How many peers? Enter min and max separated by "to" (e.g. "2 to 5"). Min must be ≥ 1.',
                'participant_emails':  (
                    'Who should be in this cycle? You can use any combination:\n'
                    '  • **all** — add every active employee\n'
                    '  • Department name — e.g. `Engineering` or `Engineering, Product`\n'
                    '  • Individual emails — e.g. `emp1@gamyam.com, emp2@gamyam.com`\n'
                    '  • Mixed — e.g. `Engineering, emp5@gamyam.com`\n'
                    '*(Type **skip** to add participants later in the UI)*'
                ),
                'peer_email':         'Please provide the email address of the peer to remove.',
                'content':            (
                    'Paste the questions or document content to convert into this template.\n'
                    '*(I will automatically detect sections and question types — '
                    'RATING for skill questions, TEXT for open-ended ones.)*'
                ),
            }
            base_msg = prompt_map.get(next_field, f'Please provide the {next_field}.')
            response_msg = _step_prefix(base_msg)
            data = {}

        # Build quick-pick options for fields with known choices
        _now_year = timezone.now().year
        _FIELD_OPTIONS = {
            'quarter_year':        [f'Q1 {_now_year}', f'Q2 {_now_year}', f'Q3 {_now_year}', f'Q4 {_now_year}',
                                    f'Q1 {_now_year+1}', f'Q2 {_now_year+1}', 'skip'],
            'nomination_approval': ['manual', 'auto'],
            'peer_enabled':        ['yes', 'no'],
            'peer_count':          ['2 to 3', '3 to 4', '3 to 5', '4 to 6'],
            'description':         ['skip'],
            'nomination_deadline': ['skip'],
        }
        field_options = _FIELD_OPTIONS.get(next_field, [])

        logger.debug(
            "  WAITING : needs '%s'  →  asking user",
            next_field
        )
        chat_logger.log_interaction(
            user, session_id, display_message, intent, merged_params, 'needs_input', response_msg, used_llm,
            response_data=data,
        )
        return {
            "session_id":    session_id,
            "intent":        intent,
            "status":        "needs_input",
            "message":       response_msg,
            "data":          data,
            "needs_input":   True,
            "missing_field": next_field,
            "field_options": field_options,
        }

    # ── PIPELINE STAGE 7: Action confirmation gate ────────────────────────
    if command.requires_confirmation:
        session_data = {
            "intent":           intent,
            "parameters":       merged_params,
            "missing_fields":   [],
            "awaiting_confirm": True,
            "context":          conversation_context,
            "session_id":       session_id,   # stored to validate on confirm (multi-tab guard)
        }
        session_manager.save_session(str(user.id), session_data)

        # Build display-friendly data for the confirm panel:
        # Replace raw UUIDs with human-readable labels
        confirm_display = dict(merged_params)
        if 'cycle_id' in confirm_display:
            confirm_display['cycle_name'] = _get_cycle_name(confirm_display.pop('cycle_id'))
        if 'nomination_id' in confirm_display:
            confirm_display['nomination_summary'] = _get_nomination_summary(confirm_display.pop('nomination_id'))
        if 'template_id' in confirm_display:
            confirm_display['template_name'] = _get_template_name(confirm_display.pop('template_id'))

        confirm_summary = _build_confirmation_summary(intent, merged_params)
        logger.debug(
            "  CONFIRM : all params collected for '%s'  →  waiting for user confirm/cancel",
            intent
        )
        chat_logger.log_interaction(
            user, session_id, display_message, intent, merged_params, 'awaiting_confirm', confirm_summary, used_llm,
            response_data=confirm_display,
        )
        return {
            "session_id":       session_id,
            "intent":           intent,
            "status":           "awaiting_confirmation",
            "message":          confirm_summary,
            "data":             confirm_display,
            "needs_input":      False,
            "requires_confirm": True,
        }

    # ── PIPELINE STAGE 8: Execute command ────────────────────────────────
    logger.debug("  EXECUTE : running %s ...", type(command).__name__)
    result = command.execute(merged_params, user)

    # ── PDF conversation mode — keep session alive, route to LLM stream ───────
    # CreateTemplateFromPDFCommand signals this via _pdf_needed: True.
    # We save updated pdf_text + pdf_history to session, then hand off to
    # ChatStreamView which calls pdf_template_conversation_stream().
    if result.get('_pdf_needed'):
        session_data = {
            "intent":         intent,
            "parameters":     merged_params,   # contains pdf_text + pdf_history (updated in-place)
            "missing_fields": ['_pdf_reply'],
            "context":        conversation_context,
        }
        session_manager.save_session(str(user.id), session_data)
        chat_logger.log_interaction(
            user, session_id, display_message, intent, {}, 'needs_input', '', used_llm,
            response_data={},
        )
        return {
            "_pdf_needed":        True,
            "_pdf_text":          merged_params.get('pdf_text', ''),
            "_pdf_history":       list(merged_params.get('pdf_history') or []),
            "_pdf_user_message":  result.get('_pdf_user_message', message),
            "_log_user":          user,
            "_log_session":       session_id,
            "_log_display":       display_message,
            "_log_used_llm":      used_llm,
            "session_id":         session_id,
            "intent":             intent,
            "status":             "needs_input",
            "data":               {},
            "needs_input":        True,
            "missing_field":      "_pdf_reply",
        }
    # ── End PDF conversation mode ─────────────────────────────────────────────

    exec_status = 'success' if result['success'] else 'failed'
    logger.debug(
        "  RESULT  : %s  →  %s",
        "✓ success" if result['success'] else "✗ failed",
        result['message'][:80]
    )

    # If command signals retry_field — keep session alive and re-ask for that slot
    # This allows graceful recovery from validation errors (wrong email, too few peers, etc.)
    if not result['success'] and result.get('retry_field'):
        retry_field  = result['retry_field']
        prompt_map = {
            'peer_emails':         'Please provide peer email addresses, comma-separated.\n*(Minimum 2, maximum 5 — e.g. emp1@gamyam.com, emp2@gamyam.com)*',
            'rejection_note':      'Please provide a reason for rejecting this nomination.\n*(e.g. "Not relevant to this cycle" or "Conflict of interest")*',
            'name':                'Please provide a different name and try again.',
            'peer_count':          'Please provide a valid peer range (e.g. "2 to 5"). Min must be ≥ 1.',
            'participant_emails':  'Please specify participants: type **all**, a department name (e.g. `Engineering`), email addresses, or a mix. Type **skip** to add later.',
        }
        retry_prompt = result['message'] + '\n\n' + prompt_map.get(retry_field, f'Please provide the {retry_field} again.')
        session_data = {
            "intent":         intent,
            "parameters":     {k: v for k, v in merged_params.items() if k != retry_field},
            "missing_fields": [retry_field],
            "context":        conversation_context,
        }
        session_manager.save_session(str(user.id), session_data)
        logger.debug("  RETRY   : re-asking for '%s' after validation failure", retry_field)
        chat_logger.log_interaction(
            user, session_id, message, intent, merged_params, 'needs_input', retry_prompt, used_llm,
            response_data={},
        )
        return {
            "session_id":    session_id,
            "intent":        intent,
            "status":        "needs_input",
            "message":       retry_prompt,
            "data":          {},
            "needs_input":   True,
            "missing_field": retry_field,
        }

    # Phase 3: compound commands signal LLM synthesis via _synthesize flag
    if result.get('_synthesize') and result.get('success'):
        session_manager.clear_session(str(user.id))
        return {
            "_llm_needed":       True,
            "_llm_user_message": message,
            "_llm_system_data":  {
                "instruction": (
                    "You are a helpful HR assistant. Based on the data below, write a clear, "
                    "conversational summary of the user's current status in the 360° review system. "
                    "Mention key highlights: active cycles, pending tasks, nominations, and upcoming deadlines. "
                    "Be concise (5-8 lines). Use plain language, no jargon."
                ),
                "user_request": message,
                "data": result.get('data', {}),
            },
            "_llm_fallback":  result['message'],
            "_log_user":      user,
            "_log_session":   session_id,
            "_log_display":   display_message,
            "_log_used_llm":  used_llm,
            "session_id":     session_id,
            "intent":         intent,
            "status":         "success",
            "data":           result.get('data', {}),
            "needs_input":    False,
        }

    # ── Track last shown list for context follow-ups ──────────────────────
    if result.get('success') and result.get('data'):
        _d = result['data']
        _last = None
        if _d.get('cycles'):
            _last = {'type': 'cycles', 'items': [{'id': c.get('id'), 'name': c.get('name')} for c in _d['cycles'] if c.get('id')]}
        elif _d.get('grouped_nominations'):
            _last = {'type': 'nominations', 'items': [
                {'id': n.get('nomination_id'), 'label': f"{n.get('peer')} → {g.get('cycle','')}"}
                for g in _d['grouped_nominations'] for n in g.get('nominations', []) if n.get('nomination_id')
            ]}
        elif _d.get('pending_approvals'):
            _last = {'type': 'nominations', 'items': [
                {'id': a.get('nomination_id'), 'label': f"{a.get('reviewee')} ← {a.get('peer')}"}
                for a in _d['pending_approvals'] if a.get('nomination_id')
            ]}
        if _last and _last['items']:
            _cur_sess = session_manager.get_session(str(user.id)) or {}
            _cur_sess['last_shown'] = _last
            session_manager.save_session(str(user.id), _cur_sess)

    chat_logger.log_interaction(
        user, session_id, display_message, intent, merged_params, exec_status, result['message'], used_llm,
        response_data=result.get('data', {}),
    )
    session_manager.clear_session(str(user.id))

    return {
        "session_id":  session_id,
        "intent":      intent,
        "status":      exec_status,
        "message":     result['message'],
        "data":        result.get('data', {}),
        "needs_input": False,
    }


def _sse(data: dict) -> str:
    """Format a dict as a single SSE data line."""
    return f"data: {json.dumps(data)}\n\n"


class ChatStreamView(APIView):
    """POST /api/v1/chat/stream/ — same as ChatMessageView but streams LLM responses via SSE.

    SSE event types emitted:
      {"type": "chunk", "text": "..."}   — incremental LLM text chunk
      {"type": "done",  ...payload}      — final response payload (always last)

    Non-LLM responses (all structured commands) emit a single "done" event.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChatMessageSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user            = request.user
        message         = serializer.validated_data['message']
        display_message = serializer.validated_data.get('display_message') or message
        session_id      = serializer.validated_data.get('session_id') or str(uuid.uuid4())

        logger.debug(
            "\n%s\n  USER    : %s  [%s]  [STREAM]\n  MESSAGE : %r\n%s",
            "─" * 60,
            user.email, getattr(user, 'role', '?'),
            message,
            "─" * 60,
        )

        # Rate limiting
        allowed, reason = session_manager.check_rate_limit(str(user.id))
        if not allowed:
            logger.warning("  ⚠  RATE LIMIT  : %s", reason)
            resp = Response({"error": reason}, status=status.HTTP_429_TOO_MANY_REQUESTS)
            resp['X-RateLimit-Limit-Minute'] = str(session_manager.MAX_PER_MIN)
            resp['X-RateLimit-Limit-Hour']   = str(session_manager.MAX_PER_HOUR)
            resp['Retry-After'] = '60'
            return resp

        # Per-user lock
        if not session_manager.acquire_lock(str(user.id)):
            logger.warning("  ⚠  LOCK : concurrent request blocked for user %s", user.id)
            return Response({
                "status":  "error",
                "message": "Your previous message is still being processed. Please wait a moment.",
            }, status=status.HTTP_429_TOO_MANY_REQUESTS)

        # Phase 3: save user message to conversation history before pipeline
        session_manager.append_chat_history(str(user.id), 'user', message)

        # Title generation: detect if this is the first message of the session
        is_new_session = not ChatLog.objects.filter(session_id=session_id).exists()

        # Run the synchronous pipeline (DB, session, intent, slot-fill)
        payload = _run_pipeline(user, message, display_message, session_id)

        # If new session, fire LLM title generation in the background
        if is_new_session:
            chat_logger.maybe_generate_title(session_id, display_message or message)

        if payload.get("_app_knowledge"):
            # ── App knowledge LLM fallback (Option B) ─────────────────────────
            ak_message  = payload.pop("_ak_message")
            log_user    = payload.pop("_log_user")
            log_session = payload.pop("_log_session")
            log_display = payload.pop("_log_display")
            payload.pop("_app_knowledge")
            _ak_history = session_manager.get_chat_history(str(user.id))

            def stream_app_knowledge():
                from .app_knowledge import answer_app_question_stream
                accumulated = ""
                try:
                    for chunk in answer_app_question_stream(ak_message, getattr(user, 'role', ''), _ak_history):
                        accumulated += chunk
                        yield _sse({"type": "chunk", "text": chunk})
                except Exception:
                    accumulated = "I'm here to help with Gamyam 360°. Try asking 'show my tasks' or 'how does nomination work?'"
                    yield _sse({"type": "chunk", "text": accumulated})
                finally:
                    session_manager.release_lock(str(user.id))

                chat_logger.log_interaction(
                    log_user, log_session, log_display or ak_message,
                    'app_knowledge', {}, 'success', accumulated, True, response_data={},
                )
                session_manager.append_chat_history(str(user.id), 'assistant', accumulated)
                payload["message"] = accumulated
                payload["status"]  = "success"
                yield _sse({"type": "done", **payload})

            resp = StreamingHttpResponse(stream_app_knowledge(), content_type="text/event-stream")

        elif payload.get("_agent_needed"):
            # ── Level-2 tool-calling agent ─────────────────────────────────────
            agent_message   = payload.pop("_agent_message")
            employee_mode   = payload.pop("_agent_employee_mode", False)
            log_user        = payload.pop("_log_user")
            log_session     = payload.pop("_log_session")
            log_display     = payload.pop("_log_display")
            payload.pop("_agent_needed")

            if employee_mode:
                from .agent_tools import EMPLOYEE_TOOL_DEFINITIONS
                _agent_tools = EMPLOYEE_TOOL_DEFINITIONS
            else:
                _agent_tools = None  # uses default TOOL_DEFINITIONS

            _agent_history = session_manager.get_chat_history(str(user.id))

            def stream_agent():
                # Emit immediately so user sees activity while agent runs tools
                yield _sse({"type": "chunk", "text": "Analyzing your data...\n\n"})
                try:
                    response = llm_service.run_agent_loop(
                        agent_message,
                        getattr(user, 'role', ''),
                        user,
                        tool_definitions=_agent_tools,
                        chat_history=_agent_history,
                    )
                except Exception:
                    response = "I was unable to complete the analysis. Please try again."
                finally:
                    session_manager.release_lock(str(user.id))

                chat_logger.log_interaction(
                    log_user, log_session, log_display or agent_message,
                    'agent_query', {}, 'success', response, True, response_data={},
                )
                session_manager.append_chat_history(str(user.id), 'assistant', response)

                # Stream the response word-by-word for a natural feel
                words = response.split(' ')
                for i, word in enumerate(words):
                    yield _sse({"type": "chunk", "text": word + (' ' if i < len(words) - 1 else '')})

                payload["message"] = response
                payload["status"]  = "success"
                sugg = llm_service.generate_suggestions(agent_message, getattr(user, 'role', ''))
                if sugg:
                    payload['suggestions'] = sugg
                yield _sse({"type": "done", **payload})

            resp = StreamingHttpResponse(stream_agent(), content_type="text/event-stream")

        elif payload.get("_pdf_needed"):
            # ── PDF → Template LLM conversation ───────────────────────────────
            pdf_text         = payload.pop("_pdf_text")
            pdf_history      = payload.pop("_pdf_history")
            pdf_user_message = payload.pop("_pdf_user_message")
            log_user         = payload.pop("_log_user")
            log_session      = payload.pop("_log_session")
            log_display      = payload.pop("_log_display")
            log_used_llm     = payload.pop("_log_used_llm")
            payload.pop("_pdf_needed")

            _SIGNAL = "__CREATE_TEMPLATE__:"
            _SIG_LEN = len(_SIGNAL)

            def stream_pdf():
                accumulated   = ""
                emitted_len   = 0
                signal_found  = False

                try:
                    for chunk in llm_service.pdf_template_conversation_stream(
                        pdf_text, pdf_history, pdf_user_message
                    ):
                        accumulated += chunk
                        if not signal_found:
                            if _SIGNAL in accumulated:
                                signal_found = True
                                # Emit any buffered text before the signal
                                sig_idx  = accumulated.find(_SIGNAL)
                                pre_sig  = accumulated[:sig_idx].rstrip()
                                to_emit  = pre_sig[emitted_len:]
                                if to_emit:
                                    yield _sse({"type": "chunk", "text": to_emit})
                                    emitted_len = len(pre_sig)
                            else:
                                # Hold back last SIG_LEN chars (might be start of signal)
                                safe_end = max(0, len(accumulated) - _SIG_LEN)
                                to_emit  = accumulated[emitted_len:safe_end]
                                if to_emit:
                                    yield _sse({"type": "chunk", "text": to_emit})
                                    emitted_len = safe_end
                        # signal_found: just accumulate without emitting

                except Exception as e:
                    logger.error("pdf_template_conversation_stream error: %s", e)
                    err = "I encountered an error processing your request. Please try again."
                    yield _sse({"type": "chunk", "text": err})
                    accumulated = err

                finally:
                    session_manager.release_lock(str(user.id))

                # ── Post-stream: handle signal or normal reply ─────────────────
                if signal_found and _SIGNAL in accumulated:
                    sig_idx       = accumulated.find(_SIGNAL)
                    visible_text  = accumulated[:sig_idx].rstrip()
                    json_str      = accumulated[sig_idx + _SIG_LEN:].strip()

                    try:
                        template_data = json.loads(json_str)
                        from apps.review_cycles.services import create_template as _create_tpl
                        template = _create_tpl(
                            template_data['name'],
                            template_data.get('description'),
                            template_data['sections'],
                            log_user,
                        )
                        q_count = sum(len(s.get('questions', [])) for s in template_data['sections'])
                        n_sec   = len(template_data['sections'])
                        success_msg = (
                            (visible_text + "\n\n" if visible_text else "") +
                            f"✅ Template **'{template.name}'** created successfully with "
                            f"{n_sec} section(s) and {q_count} question(s).\n"
                            "Open the **Templates** page to review and edit it."
                        ).strip()

                        session_manager.clear_session(str(log_user.id))
                        session_manager.append_chat_history(str(log_user.id), 'assistant', success_msg)
                        chat_logger.log_interaction(
                            log_user, log_session, log_display,
                            'create_template_from_pdf', {}, 'success', success_msg, log_used_llm,
                            response_data={"template_id": str(template.id), "name": template.name},
                        )
                        payload["message"]     = success_msg
                        payload["status"]      = "success"
                        payload["needs_input"] = False
                        payload["data"]        = {"template_id": str(template.id), "name": template.name}

                    except Exception as e:
                        logger.error("PDF template creation from LLM signal failed: %s", e)
                        err_msg = (
                            (visible_text + "\n\n" if visible_text else "") +
                            "❌ I was ready to create the template but hit an error. Please try again."
                        ).strip()
                        session_manager.clear_session(str(log_user.id))
                        payload["message"]     = err_msg
                        payload["status"]      = "failed"
                        payload["needs_input"] = False

                else:
                    # Normal conversation turn — keep session alive for next reply
                    bot_response = accumulated.strip() or "I couldn't process that. Please try again."

                    # Flush any remaining buffered text that wasn't emitted
                    if emitted_len < len(bot_response):
                        remaining = bot_response[emitted_len:]
                        if remaining:
                            yield _sse({"type": "chunk", "text": remaining})

                    # Append assistant turn to pdf_history in session
                    current_session = session_manager.get_session(str(log_user.id))
                    if current_session:
                        sp = current_session.get('parameters', {})
                        ph = list(sp.get('pdf_history') or [])
                        ph.append({"role": "assistant", "content": bot_response})
                        sp['pdf_history']               = ph
                        current_session['parameters']   = sp
                        current_session['missing_fields'] = ['_pdf_reply']
                        session_manager.save_session(str(log_user.id), current_session)

                    session_manager.append_chat_history(str(log_user.id), 'assistant', bot_response)
                    chat_logger.log_interaction(
                        log_user, log_session, log_display,
                        'create_template_from_pdf', {}, 'needs_input', bot_response, log_used_llm,
                        response_data={},
                    )
                    payload["message"]       = bot_response
                    payload["needs_input"]   = True
                    payload["missing_field"] = "_pdf_reply"

                yield _sse({"type": "done", **payload})

            resp = StreamingHttpResponse(stream_pdf(), content_type="text/event-stream")

        elif payload.get("_llm_needed"):
            # Stream Cohere response, then release lock inside generator
            llm_user_message = payload.pop("_llm_user_message")
            llm_system_data  = payload.pop("_llm_system_data")
            llm_fallback     = payload.pop("_llm_fallback")
            log_user         = payload.pop("_log_user")
            log_session      = payload.pop("_log_session")
            log_display      = payload.pop("_log_display")
            log_used_llm     = payload.pop("_log_used_llm")
            is_data_analysis = payload.pop("_data_analysis", False)
            payload.pop("_llm_needed")

            _llm_history = session_manager.get_chat_history(str(user.id))

            def stream_llm():
                accumulated = ""
                try:
                    if is_data_analysis:
                        stream_gen = llm_service.generate_data_analysis_stream(
                            llm_user_message, llm_system_data,
                            getattr(user, 'role', 'SUPER_ADMIN'),
                            chat_history=_llm_history,
                        )
                    else:
                        stream_gen = llm_service.generate_response_stream(llm_user_message, llm_system_data)
                    for chunk in stream_gen:
                        accumulated += chunk
                        yield _sse({"type": "chunk", "text": chunk})
                except Exception:
                    accumulated = llm_fallback
                    yield _sse({"type": "chunk", "text": llm_fallback})
                finally:
                    session_manager.release_lock(str(user.id))

                response_msg = accumulated or llm_fallback
                chat_logger.log_interaction(
                    log_user, log_session, log_display,
                    "unknown", {}, "clarify", response_msg, log_used_llm,
                    response_data={},
                )
                # Phase 3: save bot response to conversation history
                session_manager.append_chat_history(str(user.id), 'assistant', response_msg)
                payload["message"] = response_msg
                # Data analysis responses always use 'success' so the frontend
                # renders the streamed/formatted text instead of the generic
                # "I didn't quite understand that" clarify override.
                if is_data_analysis:
                    payload["status"] = "success"
                # LLM suggestions: generate contextual follow-ups for data analysis
                if is_data_analysis:
                    sugg = llm_service.generate_suggestions(
                        log_display or message,
                        getattr(user, 'role', 'SUPER_ADMIN'),
                    )
                    if sugg:
                        payload['suggestions'] = sugg
                yield _sse({"type": "done", **payload})

            resp = StreamingHttpResponse(stream_llm(), content_type="text/event-stream")
        else:
            # No LLM needed — release lock immediately, emit single done event
            session_manager.release_lock(str(user.id))
            # Phase 3: save bot response to conversation history
            if payload.get("message"):
                session_manager.append_chat_history(str(user.id), 'assistant', payload["message"])

            # Attach contextual next-step suggestions for successful commands
            if payload.get('status') == 'success':
                from .suggestions import get_intent_suggestions
                sugg = get_intent_suggestions(payload.get('intent', ''))
                if sugg:
                    payload['suggestions'] = sugg

            def stream_done():
                yield _sse({"type": "done", **payload})

            resp = StreamingHttpResponse(stream_done(), content_type="text/event-stream")

        resp["Cache-Control"]      = "no-cache"
        resp["X-Accel-Buffering"]  = "no"
        resp["Transfer-Encoding"]  = "chunked"
        return resp


class ChatConfirmView(APIView):
    """POST /api/v1/chat/confirm/ — confirm or cancel a pending action command."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChatConfirmSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user      = request.user
        confirmed = serializer.validated_data['confirmed']
        session   = session_manager.get_session(str(user.id))

        logger.debug(
            "\n%s\n  USER    : %s  [CONFIRM REQUEST]\n  ACTION  : %s  →  %s\n%s",
            "─" * 60,
            user.email,
            session.get('intent', '?'),
            "CONFIRMED ✓" if confirmed else "CANCELLED ✗",
            "─" * 60,
        )

        if not session or not session.get('awaiting_confirm'):
            logger.debug("  ⚠  No pending confirmation found in session")
            return Response({
                "session_id": serializer.validated_data.get('session_id', ''),
                "status":     "error",
                "message":    "No pending action to confirm. Please start a new command.",
                "data":       {},
            }, status=status.HTTP_400_BAD_REQUEST)

        # Multi-tab guard: ensure the confirming tab started this action
        sent_session_id   = serializer.validated_data.get('session_id', '')
        stored_session_id = session.get('session_id', '')
        if stored_session_id and sent_session_id and sent_session_id != stored_session_id:
            logger.debug(
                "  ⚠  MULTI-TAB MISMATCH  sent=%s  stored=%s",
                sent_session_id[:8], stored_session_id[:8]
            )
            return Response({
                "session_id": sent_session_id,
                "status":     "error",
                "message":    "Session mismatch. This action was started in a different tab. Please retry from the original tab.",
                "data":       {},
            }, status=status.HTTP_409_CONFLICT)

        intent = session.get('intent')
        params = session.get('parameters', {})

        if not intent:
            session_manager.clear_session(str(user.id))
            return Response({
                "session_id": serializer.validated_data.get('session_id', ''),
                "status":     "error",
                "message":    "Session data is invalid. Please try again.",
                "data":       {},
            }, status=status.HTTP_400_BAD_REQUEST)

        if not confirmed:
            logger.debug("  RESULT  : ✗ cancelled by user")
            session_manager.clear_session(str(user.id))
            chat_logger.log_interaction(
                user, serializer.validated_data['session_id'], '[user cancelled]',
                intent, params, 'rejected', 'Action cancelled by user.', False,
                response_data={},
            )
            return Response({
                "session_id": serializer.validated_data['session_id'],
                "intent":     intent,
                "status":     "cancelled",
                "message":    "Action cancelled.",
                "data":       {},
            })

        command = get_command(intent)
        if not command:
            session_manager.clear_session(str(user.id))
            return Response({
                "session_id": serializer.validated_data.get('session_id', ''),
                "status":     "error",
                "message":    "Unknown command. Please try again.",
                "data":       {},
            }, status=status.HTTP_400_BAD_REQUEST)

        logger.debug("  EXECUTE : running %s ...", type(command).__name__)
        result      = command.execute(params, user)
        exec_status = 'success' if result['success'] else 'failed'
        logger.debug(
            "  RESULT  : %s  →  %s",
            "✓ success" if result['success'] else "✗ failed",
            result['message'][:80]
        )

        # If command signals retry_field — keep session alive and re-ask for that slot
        if not result['success'] and result.get('retry_field'):
            retry_field = result['retry_field']
            prompt_map = {
                'peer_emails':         'Please provide peer email addresses, comma-separated.\n*(Minimum 2, maximum 5 — e.g. emp1@gamyam.com, emp2@gamyam.com)*',
                'rejection_note':      'Please provide a reason for rejecting this nomination.\n*(e.g. "Not relevant to this cycle" or "Conflict of interest")*',
                'name':                'Please provide a different name and try again.',
                'peer_count':          'Please provide a valid peer range (e.g. "2 to 5"). Min must be ≥ 1.',
                'participant_emails':  'Please specify participants: type **all**, a department name (e.g. `Engineering`), email addresses, or a mix. Type **skip** to add later.',
            }
            retry_prompt = result['message'] + '\n\n' + prompt_map.get(retry_field, f'Please provide the {retry_field} again.')
            session_data = {
                "intent":         intent,
                "parameters":     {k: v for k, v in params.items() if k != retry_field},
                "missing_fields": [retry_field],
                "context":        "",
            }
            session_manager.save_session(str(user.id), session_data)
            logger.debug("  RETRY   : re-asking for '%s' after confirm-time validation failure", retry_field)
            chat_logger.log_interaction(
                user, serializer.validated_data['session_id'], '[confirmed]',
                intent, params, 'needs_input', retry_prompt, False,
                response_data={},
            )
            return Response({
                "session_id":    serializer.validated_data['session_id'],
                "intent":        intent,
                "status":        "needs_input",
                "message":       retry_prompt,
                "data":          {},
                "needs_input":   True,
                "missing_field": retry_field,
            })

        chat_logger.log_interaction(
            user, serializer.validated_data['session_id'], '[confirmed]',
            intent, params, exec_status, result['message'], False,
            response_data=result.get('data', {}),
        )
        session_manager.clear_session(str(user.id))

        return Response({
            "session_id": serializer.validated_data['session_id'],
            "intent":     intent,
            "status":     exec_status,
            "message":    result['message'],
            "data":       result.get('data', {}),
        })


class ChatSessionView(APIView):
    """GET/DELETE /api/v1/chat/session/ — inspect or discard the current user's chat session."""
    permission_classes = [IsAuthenticated]

    # Human-readable labels for each intent
    _INTENT_LABELS = {
        'create_cycle':        'creating a cycle',
        'create_template':     'creating a template',
        'nominate_peers':      'nominating peers',
        'cancel_cycle':        'cancelling a cycle',
        'activate_cycle':      'activating a cycle',
        'close_cycle':         'closing a cycle',
        'finalize_cycle':      'finalizing a cycle',
        'release_results':     'releasing results',
        'approve_nomination':        'approving a nomination',
        'reject_nomination':         'rejecting a nomination',
        'approve_all_nominations':   'bulk approving all nominations',
    }

    def get(self, request):
        session = session_manager.get_session(str(request.user.id))
        if not session:
            return Response({"has_active_session": False})

        intent           = session.get('intent')
        missing          = session.get('missing_fields', [])
        awaiting_confirm = session.get('awaiting_confirm', False)

        # Only surface sessions where the user needs to do something
        if not missing and not awaiting_confirm:
            return Response({"has_active_session": False})

        intent_label = self._INTENT_LABELS.get(intent, intent.replace('_', ' ') if intent else 'an action')
        return Response({
            "has_active_session": True,
            "intent":             intent,
            "intent_label":       intent_label,
            "awaiting_confirm":   awaiting_confirm,
            "missing_fields":     missing,
        })

    def delete(self, request):
        """Discard the current session."""
        session_manager.clear_session(str(request.user.id))
        return Response({"cleared": True})


class ChatHistoryView(APIView):
    """
    GET /api/v1/chat/history/              — flat log of last 50 messages (widget load)
    GET /api/v1/chat/history/?session_id=X — all messages for a specific session
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        session_id = request.query_params.get('session_id')
        if session_id:
            logs = ChatLog.objects.filter(
                user=request.user, session_id=session_id
            ).order_by('created_at')
        else:
            logs = ChatLog.objects.filter(user=request.user).order_by('-created_at')[:50]
        serializer = ChatLogSerializer(logs, many=True)
        return Response({"history": serializer.data})


class ChatSessionsView(APIView):
    """
    GET    /api/v1/chat/sessions/ — list distinct sessions with LLM-generated titles.
    DELETE /api/v1/chat/sessions/ — delete ALL chat history for the current user.
    """
    permission_classes = [IsAuthenticated]

    def delete(self, request):
        deleted, _ = ChatLog.objects.filter(user=request.user).delete()
        session_manager.clear_session(str(request.user.id))
        return Response({"deleted": True, "count": deleted})

    def get(self, request):
        from django.db.models import Max, Min
        sessions = (
            ChatLog.objects
            .filter(user=request.user)
            .values('session_id')
            .annotate(first_at=Min('created_at'), last_at=Max('created_at'))
            .order_by('-last_at')[:30]
        )
        result = []
        for s in sessions:
            first_log = (
                ChatLog.objects
                .filter(user=request.user, session_id=s['session_id'])
                .order_by('created_at')
                .first()
            )
            result.append({
                'session_id':    s['session_id'],
                'title':         first_log.session_title if first_log else None,
                'first_message': first_log.message if first_log else '',
                'last_at':       s['last_at'],
            })
        return Response({"sessions": result})


class ChatSessionDetailView(APIView):
    """
    DELETE /api/v1/chat/sessions/<session_id>/ — delete all logs for a session
    PATCH  /api/v1/chat/sessions/<session_id>/ — rename session title
    """
    permission_classes = [IsAuthenticated]

    def delete(self, request, session_id):
        deleted, _ = ChatLog.objects.filter(
            user=request.user, session_id=session_id
        ).delete()
        return Response({"deleted": deleted > 0, "count": deleted})

    def patch(self, request, session_id):
        title = request.data.get('title', '').strip()[:100]
        if not title:
            return Response({"error": "Title cannot be empty."}, status=400)
        first_log = ChatLog.objects.filter(
            user=request.user, session_id=session_id
        ).order_by('created_at').first()
        if not first_log:
            return Response({"error": "Session not found."}, status=404)
        first_log.session_title = title
        first_log.save(update_fields=['session_title'])
        return Response({"updated": True, "title": title})


class ChatAnalyticsView(APIView):
    """GET /api/v1/chat/analytics/ — usage stats for HR_ADMIN and SUPER_ADMIN."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role not in ('HR_ADMIN', 'SUPER_ADMIN'):
            return Response({'detail': 'Forbidden'}, status=403)

        days = int(request.query_params.get('days', 30))
        since = timezone.now() - datetime.timedelta(days=days)
        qs = ChatLog.objects.filter(created_at__gte=since)

        total = qs.count()
        llm_count = qs.filter(used_llm=True).count()
        success_count = qs.filter(execution_status='success').count()
        unique_users = qs.values('user').distinct().count()

        intent_breakdown = list(
            qs.exclude(intent__isnull=True)
              .values('intent')
              .annotate(count=Count('id'))
              .order_by('-count')[:15]
        )

        status_breakdown = list(
            qs.values('execution_status')
              .annotate(count=Count('id'))
              .order_by('-count')
        )

        daily_qs = (
            qs.annotate(day=TruncDay('created_at'))
              .values('day')
              .annotate(count=Count('id'))
              .order_by('day')
        )
        daily_volume = [
            {'date': d['day'].strftime('%Y-%m-%d'), 'count': d['count']}
            for d in daily_qs
        ]

        per_user_activity = list(
            qs.values('user__email', 'user__first_name', 'user__last_name')
              .annotate(count=Count('id'))
              .order_by('-count')[:20]
        )
        per_user_data = [
            {
                'email': u['user__email'],
                'name': f"{u['user__first_name']} {u['user__last_name']}".strip(),
                'count': u['count']
            }
            for u in per_user_activity
        ]

        failed_intents = list(
            qs.filter(execution_status__in=['failed', 'unknown'])
              .exclude(intent__isnull=True)
              .values('intent', 'message')
              .annotate(count=Count('id'))
              .order_by('-count')[:10]
        )

        return Response({
            'period_days':      days,
            'total_messages':   total,
            'unique_users':     unique_users,
            'llm_fallback_count': llm_count,
            'llm_fallback_rate':  round(llm_count / total * 100, 1) if total else 0,
            'success_count':    success_count,
            'success_rate':     round(success_count / total * 100, 1) if total else 0,
            'intent_breakdown': intent_breakdown,
            'status_breakdown': status_breakdown,
            'daily_volume':     daily_volume,
            'per_user_activity': per_user_data,
            'failed_intents':   failed_intents,
        })


def _resolve_context_reference(message: str, session: dict):
    """
    Detect ordinal references to previously shown items.
    e.g. "cancel the second one", "activate it", "close the 3rd cycle"
    Returns (intent, params) or None.
    """
    import re as _re
    last = session.get('last_shown')
    if not last or not last.get('items'):
        return None

    text = message.strip().lower()
    items = last['items']

    # Map action words → intents (for cycles)
    CYCLE_ACTIONS = {
        'cancel': 'cancel_cycle', 'activate': 'activate_cycle',
        'close': 'close_cycle', 'release': 'release_results',
        'release results': 'release_results', 'release result': 'release_results',
    }
    ORDINALS = {
        'first': 0, '1st': 0, 'second': 1, '2nd': 1, 'third': 2, '3rd': 2,
        'fourth': 3, '4th': 3, 'fifth': 4, '5th': 4, 'sixth': 5, '6th': 5,
        'last': -1, 'it': None, 'that': None, 'this': None, 'that one': None, 'this one': None,
    }

    # Match: "<action> (the)? <ordinal> (one|cycle)?"
    for action, intent in CYCLE_ACTIONS.items():
        pattern = _re.compile(
            rf'\b{_re.escape(action)}\b[\w\s]*(the\s+)?(\b(?:' +
            '|'.join(_re.escape(k) for k in ORDINALS) +
            r'|\d+(?:st|nd|rd|th)?)\b)',
            _re.IGNORECASE
        )
        m = pattern.search(text)
        if m:
            raw = m.group(2).lower().strip()
            # numeric like "2nd", "3rd"
            num_m = _re.match(r'(\d+)', raw)
            if num_m:
                idx = int(num_m.group(1)) - 1
            elif raw in ORDINALS:
                idx = ORDINALS[raw]
            else:
                continue
            try:
                item = items[idx]
            except IndexError:
                continue
            if item.get('id') and last['type'] == 'cycles':
                return (intent, {'cycle_id': item['id']})

    # "it" / "that" alone — only if single item or last item shown
    if _re.match(r'^(it|that|this|that one|this one)$', text) and last['type'] == 'cycles':
        # Ambiguous — can't resolve without an action
        return None

    return None


def _parse_flexible_date(text: str) -> str | None:
    """
    Parse natural language and standard date strings into YYYY-MM-DD.
    Handles: strict formats, "end of September", "next month", "in 2 weeks",
    "Sep 30", "30 Sep 2026", "end of Q3", "next Friday", "tomorrow", etc.
    Returns YYYY-MM-DD string or None if unrecognisable.
    """
    import re as _re
    import datetime as _dt
    import calendar

    text = text.strip()
    today = _dt.date.today()

    # 1. Strict standard formats first
    for fmt in ('%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y', '%m/%d/%Y', '%Y/%m/%d', '%d %b %Y', '%d %B %Y', '%b %d %Y', '%B %d %Y', '%d %b', '%d %B', '%b %d', '%B %d'):
        try:
            d = _dt.datetime.strptime(text, fmt).date()
            # If year wasn't in format, use current or next year intelligently
            if '%Y' not in fmt and '%y' not in fmt:
                d = d.replace(year=today.year)
                if d < today:
                    d = d.replace(year=today.year + 1)
            return d.strftime('%Y-%m-%d')
        except ValueError:
            pass

    tl = text.lower().strip()

    # 2. Relative: today / tomorrow / yesterday
    if tl in ('today',):
        return today.strftime('%Y-%m-%d')
    if tl in ('tomorrow',):
        return (today + _dt.timedelta(days=1)).strftime('%Y-%m-%d')

    # 3. "in N days/weeks/months"
    m = _re.match(r'in\s+(\d+)\s+(day|days|week|weeks|month|months)', tl)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        if 'day' in unit:
            return (today + _dt.timedelta(days=n)).strftime('%Y-%m-%d')
        if 'week' in unit:
            return (today + _dt.timedelta(weeks=n)).strftime('%Y-%m-%d')
        if 'month' in unit:
            month = today.month + n
            year = today.year + (month - 1) // 12
            month = (month - 1) % 12 + 1
            day = min(today.day, calendar.monthrange(year, month)[1])
            return _dt.date(year, month, day).strftime('%Y-%m-%d')

    # 4. "next week/month/year"
    if tl == 'next week':
        return (today + _dt.timedelta(weeks=1)).strftime('%Y-%m-%d')
    if tl == 'next month':
        month = today.month % 12 + 1
        year = today.year + (1 if today.month == 12 else 0)
        last_day = calendar.monthrange(year, month)[1]
        return _dt.date(year, month, last_day).strftime('%Y-%m-%d')
    if tl == 'next year':
        return _dt.date(today.year + 1, 12, 31).strftime('%Y-%m-%d')

    # 5. "end of <month>" or "end of <month> <year>"
    MONTHS = {'january':1,'february':2,'march':3,'april':4,'may':5,'june':6,
              'july':7,'august':8,'september':9,'october':10,'november':11,'december':12,
              'jan':1,'feb':2,'mar':3,'apr':4,'jun':6,'jul':7,'aug':8,
              'sep':9,'oct':10,'nov':11,'dec':12}
    m = _re.match(r'end\s+of\s+(\w+)(?:\s+(\d{4}))?', tl)
    if m:
        mon_name, yr = m.group(1), m.group(2)
        mon = MONTHS.get(mon_name)
        if mon:
            yr = int(yr) if yr else (today.year if mon >= today.month else today.year + 1)
            last_day = calendar.monthrange(yr, mon)[1]
            return _dt.date(yr, mon, last_day).strftime('%Y-%m-%d')

    # 6. "end of Q1/Q2/Q3/Q4" or "Q3 end"
    m = _re.search(r'q([1-4])', tl)
    if m and ('end' in tl or 'last' in tl or tl.startswith('q')):
        q = int(m.group(1))
        end_month = q * 3
        yr_m = _re.search(r'\d{4}', tl)
        yr = int(yr_m.group()) if yr_m else today.year
        last_day = calendar.monthrange(yr, end_month)[1]
        return _dt.date(yr, end_month, last_day).strftime('%Y-%m-%d')

    # 7. "next <weekday>"
    DAYS = {'monday':0,'tuesday':1,'wednesday':2,'thursday':3,'friday':4,'saturday':5,'sunday':6,
            'mon':0,'tue':1,'wed':2,'thu':3,'fri':4,'sat':5,'sun':6}
    m = _re.match(r'next\s+(\w+)', tl)
    if m:
        day_name = m.group(1)
        target = DAYS.get(day_name)
        if target is not None:
            days_ahead = (target - today.weekday()) % 7 or 7
            return (today + _dt.timedelta(days=days_ahead)).strftime('%Y-%m-%d')

    # 8. "<month> <year>" e.g. "September 2026" → last day of that month
    m = _re.match(r'(\w+)\s+(\d{4})$', tl)
    if m:
        mon = MONTHS.get(m.group(1))
        if mon:
            yr = int(m.group(2))
            last_day = calendar.monthrange(yr, mon)[1]
            return _dt.date(yr, mon, last_day).strftime('%Y-%m-%d')

    return None


def _get_cycle_name(cycle_id: str) -> str:
    """Resolve a cycle UUID to its display name."""
    if not cycle_id:
        return '-'
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT name FROM review_cycles WHERE id = %s", [cycle_id])
            row = cursor.fetchone()
            return row[0] if row else cycle_id
    except Exception:
        return cycle_id


def _get_template_name(template_id: str) -> str:
    """Resolve a template UUID to its display name."""
    if not template_id:
        return '-'
    try:
        from apps.review_cycles.models import Template
        t = Template.objects.filter(id=template_id).first()
        return t.name if t else template_id
    except Exception:
        return template_id


def _get_nomination_summary(nomination_id: str) -> str:
    """Resolve a nomination UUID to a human-readable 'peer → reviewee (cycle)' label."""
    if not nomination_id:
        return '-'
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT u_peer.first_name || ' ' || u_peer.last_name,
                       u_reviewee.first_name || ' ' || u_reviewee.last_name,
                       rc.name
                FROM peer_nominations pn
                JOIN users u_peer     ON pn.peer_id     = u_peer.id
                JOIN users u_reviewee ON pn.reviewee_id = u_reviewee.id
                JOIN review_cycles rc ON pn.cycle_id    = rc.id
                WHERE pn.id = %s
            """, [nomination_id])
            row = cursor.fetchone()
            return f"{row[0]} reviewing {row[1]} in {row[2]}" if row else nomination_id
    except Exception:
        return nomination_id


# ── Inline field-edit helpers (used during awaiting_confirm) ─────────────────
# Maps common user phrases → session parameter keys (most-specific first).
_INLINE_EDIT_FIELDS = {
    # Text / date fields that can be patched directly without UUID resolution
    'name':                ['cycle name', 'name', 'title'],
    'description':         ['description', 'desc'],
    'quarter_year':        ['quarter year', 'quarter', 'qy', 'q'],
    'review_deadline':     ['review deadline', 'deadline', 'due date', 'end date', 'review due'],
    'nomination_deadline': ['nomination deadline', 'nom deadline', 'nomination due'],
    'nomination_approval': ['nomination approval', 'approval type', 'approval mode', 'approval'],
    'peer_enabled':        ['peer enabled', 'peer reviews enabled', 'peer review', 'peer'],
    'peer_count':          ['peer count', 'peer range', 'number of peers', 'peers count'],
    'participant_emails':  ['participants', 'participant emails', 'members', 'employees'],
    'peer_emails':         ['peer emails', 'peer list'],
    'rejection_note':      ['rejection reason', 'rejection note', 'reason'],
}

# Flatten to (alias, field_key) sorted by alias length desc (longest match first)
_INLINE_EDIT_ALIASES = sorted(
    [(alias, key) for key, aliases in _INLINE_EDIT_FIELDS.items() for alias in aliases],
    key=lambda x: -len(x[0])
)


def _match_inline_field(phrase: str):
    """Return the session parameter key for a user-typed field phrase, or None."""
    lower = phrase.lower().strip()
    for alias, key in _INLINE_EDIT_ALIASES:
        if lower == alias or lower.startswith(alias) or alias.startswith(lower):
            return key
    return None


def _try_parse_inline_edit(message: str, session: dict):
    """
    Detect 'change/update/set FIELD to VALUE' or 'FIELD is/should be VALUE' patterns.
    Only activates for fields already present in the session parameters.
    Returns {field_key: new_value} or None.
    """
    import re as _re
    text   = message.strip()
    params = session.get('parameters', {})
    if not params:
        return None

    for pattern in (
        r'(?:change|update|set|edit)\s+(?:the\s+)?(.+?)\s+to\s+(.+)',
        r'(?:actually[,]?\s+)?(?:the\s+)?(.+?)\s+(?:should\s+be|will\s+be|is)\s+(.+)',
    ):
        m = _re.match(pattern, text, _re.IGNORECASE)
        if m:
            field_phrase = m.group(1).strip()
            new_value    = m.group(2).strip()
            key = _match_inline_field(field_phrase)
            if key and key in params:
                return {key: new_value}

    return None


def _build_confirmation_summary(intent: str, params: dict) -> str:
    cycle_name = _get_cycle_name(params.get('cycle_id', ''))
    nom_summary = _get_nomination_summary(params.get('nomination_id', ''))
    summaries = {
        'create_cycle': (
            f"Please confirm cycle creation:\n"
            f"• Name: {params.get('name', '-')}\n"
            f"• Template: {_get_template_name(params.get('template_id', ''))}\n"
            f"• Description: {params.get('description', 'skip') if params.get('description', 'skip').lower() != 'skip' else 'None'}\n"
            f"• Quarter: {params.get('quarter_year', 'skip') if params.get('quarter_year', 'skip').lower() != 'skip' else 'None'}\n"
            f"• Review deadline: {params.get('review_deadline', '-')}\n"
            f"• Nomination deadline: {params.get('nomination_deadline', 'skip') if params.get('nomination_deadline', 'skip').lower() != 'skip' else 'None'}\n"
            f"• Nomination approval: {params.get('nomination_approval', 'auto').upper() if params.get('nomination_approval', 'auto').lower() != 'skip' else 'AUTO'}\n"
            f"• Peer review: {'Yes — ' + params.get('peer_count', '') + ' peers' if params.get('peer_enabled', '').lower() in ('yes', 'y', 'true') else 'No'}\n"
            f"• Participants: {params.get('participant_emails', 'skip') if params.get('participant_emails', 'skip').lower() not in ('skip', '') else 'None — add in UI'}"
        ),
        'create_template':     f"Please confirm template creation:\n• Name: {params.get('name', '-')}",
        'release_results':     f"Please confirm releasing results for cycle:\n• {cycle_name}",
        'cancel_cycle':        f"Please confirm cancelling cycle:\n• {cycle_name}",
        'activate_cycle':      f"Please confirm activating cycle:\n• {cycle_name}",
        'close_cycle':         f"Please confirm closing cycle:\n• {cycle_name}",
        'nominate_peers':      f"Please confirm peer nominations:\n• Cycle: {cycle_name}\n• Peers: {params.get('peer_emails', '-')}",
        'approve_nomination':       f"Please confirm approval:\n• {nom_summary}",
        'reject_nomination':        f"Please confirm rejection:\n• {nom_summary}\n• Reason: {params.get('rejection_note', '-')}",
        'approve_all_nominations':  "Bulk-approve all pending nominations for your team.\n⚠ This will approve every pending nomination — proceed?",
        'retract_nomination':       (
            f"Please confirm removing this peer from your nominations:\n"
            f"• Cycle: {cycle_name}\n"
            f"• Peer to remove: {params.get('peer_email', '-')}"
        ),
        'create_template_from_text': (
            f"Please confirm template creation from pasted content:\n"
            f"• Name: {params.get('name', '-')}\n"
            f"• Content length: {len(params.get('content', ''))} characters\n"
            f"*(Sections and question types will be auto-detected by AI)*"
        ),
        'remind_team': (
            f"Please confirm sending review reminders:\n"
            f"• Cycle: {cycle_name}\n"
            f"• All team members with pending/unsubmitted reviews will be notified."
        ),
    }
    return summaries.get(intent, f"Please confirm the action: {intent} with parameters: {params}")


class ChatUploadView(APIView):
    """
    POST /api/v1/chat/upload/
    Accepts a PDF (or .txt) file, extracts text, returns it so the frontend
    can trigger a create_template_from_pdf chat message.
    """
    permission_classes = [IsAuthenticated]
    MAX_SIZE_MB = 10

    def post(self, request):
        user = request.user
        if getattr(user, 'role', '') not in ('HR_ADMIN', 'SUPER_ADMIN'):
            return Response(
                {"error": "Only HR Admin and Super Admin can upload files."},
                status=status.HTTP_403_FORBIDDEN,
            )

        uploaded = request.FILES.get('file')
        if not uploaded:
            return Response({"error": "No file provided."}, status=status.HTTP_400_BAD_REQUEST)

        if uploaded.size > self.MAX_SIZE_MB * 1024 * 1024:
            return Response(
                {"error": f"File too large. Maximum size is {self.MAX_SIZE_MB} MB."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        filename = uploaded.name.lower()

        try:
            if filename.endswith('.pdf'):
                text = self._extract_pdf(uploaded)
            elif filename.endswith('.txt'):
                text = uploaded.read().decode('utf-8', errors='ignore')
            else:
                return Response(
                    {"error": "Unsupported file type. Please upload a PDF or TXT file."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        except Exception as e:
            logger.error("ChatUploadView extraction failed: %s", e)
            return Response(
                {"error": "Could not read the file. Make sure it is a valid PDF or text file."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        text = text.strip()
        if not text:
            return Response(
                {"error": "The file appears to be empty or could not be parsed (scanned image PDFs are not supported)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Truncate to avoid exceeding LLM context limits
        if len(text) > 12000:
            text = text[:12000] + "\n...[truncated]"

        logger.info("ChatUploadView: extracted %d chars from '%s' for user %s", len(text), uploaded.name, user.email)
        return Response({"extracted_text": text, "filename": uploaded.name, "char_count": len(text)})

    @staticmethod
    def _extract_pdf(file_obj) -> str:
        import pdfplumber, io
        raw = file_obj.read()
        text_parts = []
        with pdfplumber.open(io.BytesIO(raw)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
        return "\n\n".join(text_parts)

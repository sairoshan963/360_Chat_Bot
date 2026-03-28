import json
import re
import logging
import requests
from django.conf import settings

logger = logging.getLogger(__name__)

COHERE_API_URL = "https://api.cohere.com/v2/chat"
COHERE_MODEL   = "command-a-03-2025"

# Hardcoded fallback — mirrors the prompt seeded in migration 0002.
# Used only when the DB / PromptTemplate table is unavailable.
_FALLBACK_INTENT_PROMPT = (
    "You are an AI assistant for an enterprise 360° Feedback System.\n"
    "Your job is to convert user messages into structured JSON commands.\n\n"
    "Supported commands:\n"
    "  create_cycle          - HR Admin: create a new feedback cycle\n"
    "  create_template       - HR Admin: create a new review template\n"
    "  show_pending_reviews  - Manager/Employee: list pending review tasks\n"
    "  show_my_feedback      - Employee: view personal feedback summary\n"
    "  show_cycle_status     - HR Admin/Manager: view cycle progress\n"
    "  show_team_summary     - Manager: view team feedback overview\n"
    "  show_participation    - HR Admin: view participation statistics\n"
    "  show_my_tasks         - All: view assigned reviewer tasks\n"
    "  show_cycle_deadlines  - All: view upcoming cycle deadlines\n"
    "  show_my_nominations   - All: view peer nominations submitted\n"
    "  show_my_cycles        - All: view cycles user participates in\n"
    "  show_templates        - HR Admin: list available templates\n"
    "  show_team_nominations - Manager: view team nomination approvals\n"
    "  show_employees        - HR Admin/Super Admin: list all employees\n"
    "  show_announcements    - All: view active announcements\n"
    "  show_audit_logs       - Super Admin: view recent audit activity\n"
    "  nominate_peers        - Employee: nominate peers for a cycle\n"
    "  activate_cycle        - HR Admin: activate a draft/finalized cycle\n"
    "  close_cycle           - HR Admin: close an active cycle\n"
    "  release_results       - HR Admin: release results for a closed cycle\n"
    "  cancel_cycle          - HR Admin: cancel/archive a cycle\n\n"
    "Rules:\n"
    "1. Always return valid JSON with exactly two keys: intent and parameters.\n"
    "2. If the intent is unclear, return: {\"intent\": \"unknown\", \"parameters\": {}}\n"
    "3. Extract all mentioned parameters from the user message.\n"
    "4. Do NOT invent parameter values not mentioned by the user.\n"
    "5. Do NOT include explanations — respond ONLY with JSON.\n\n"
    "Example responses:\n"
    "  {\"intent\": \"create_cycle\", \"parameters\": {\"name\": \"Q3 Review\", \"department\": \"Engineering\"}}\n"
    "  {\"intent\": \"show_pending_reviews\", \"parameters\": {}}\n"
    "  {\"intent\": \"unknown\", \"parameters\": {}}\n\n"
    "Conversation Context:\n{{conversation_context}}\n\n"
    "User Message:\n{{user_message}}\n\n"
    "Respond ONLY with JSON:"
)


def _get_api_key() -> str:
    api_key = getattr(settings, 'COHERE_API_KEY', None)
    if not api_key:
        logger.error(
            "COHERE_API_KEY is not configured in settings — "
            "LLM intent detection is unavailable. Set COHERE_API_KEY in your environment."
        )
        return ''
    return api_key


def _strip_json(text: str) -> str:
    """Strip markdown code fences from LLM response."""
    text = text.strip()
    text = re.sub(r'^```(?:json)?\s*', '', text)
    text = re.sub(r'\s*```$', '', text)
    return text.strip()


def generate_session_title(message: str) -> str:
    """
    Generate a concise 2-5 word title for a chat session based on the first user message.
    Called in a background thread — failures are silently logged.
    """
    api_key = _get_api_key()
    if not api_key:
        return ''
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    payload = {
        "model": COHERE_MODEL,
        "messages": [
            {
                "role": "user",
                "content": (
                    f'Give a concise 2-5 word title for a chat conversation that starts with:\n'
                    f'"{message[:300]}"\n\n'
                    'Rules:\n'
                    '- 2 to 5 words only\n'
                    '- Title Case\n'
                    '- No quotes, no punctuation at the end\n'
                    'Return ONLY the title, nothing else.'
                ),
            }
        ],
        "max_tokens": 20,
        "temperature": 0.3,
    }
    try:
        resp = requests.post(COHERE_API_URL, headers=headers, json=payload, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        title = data.get('message', {}).get('content', [{}])[0].get('text', '').strip()
        title = title.strip('"\'').replace('\n', ' ').strip()
        return title[:80] if title else ''
    except Exception as exc:
        logger.warning("generate_session_title failed: %s", exc)
        return ''


def _load_intent_prompt() -> str:
    """
    Load the active intent_detection prompt from the PromptTemplate DB table.
    Falls back to _FALLBACK_INTENT_PROMPT if the DB is unavailable or no record exists.
    The template text must contain {{conversation_context}} and {{user_message}} placeholders.
    """
    try:
        from .models import PromptTemplate  # local import avoids AppRegistry issues at module load
        template = (
            PromptTemplate.objects
            .filter(name='intent_detection', is_active=True)
            .order_by('-version')
            .first()
        )
        if template:
            logger.debug("Loaded intent_detection prompt from DB (v%s)", template.version)
            return template.template_text
        logger.warning("No active intent_detection PromptTemplate found; using fallback.")
    except Exception as exc:
        logger.warning("Could not load intent prompt from DB: %s", exc)
    return _FALLBACK_INTENT_PROMPT


# ── Tool-calling intent detection (E1) ───────────────────────────────────────
# Each supported intent is registered as a Cohere tool.  The model picks the
# best-matching tool and fills its parameters structurally — no fragile JSON
# parsing of free-text output needed.

_INTENT_TOOLS = [
    # ── Query commands (no required parameters) ───────────────────────────
    {"type": "function", "function": {"name": "show_my_feedback",      "description": "Show the current user their received peer feedback summary.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "show_my_report",        "description": "Show the current user their personal performance report, scores, or results.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "show_pending_reviews",  "description": "List feedback reviews that the user needs to WRITE and SUBMIT for others (reviewer perspective — writing feedback about peers/team).", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "show_cycle_status",     "description": "Show the status of all review cycles in the system.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "show_team_summary",     "description": "Show a manager's team feedback overview or summary.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "show_participation",    "description": "Show participation statistics or completion rates for cycles.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "show_my_tasks",         "description": "Show all reviewer tasks assigned to the current user — includes PENDING, SUBMITTED, LOCKED tasks across all cycles. Use for 'my tasks', 'tasks assigned to me', 'what tasks do I have'.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "show_cycle_deadlines",  "description": "Show upcoming cycle deadlines or due dates.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "show_my_nominations",   "description": "Show peer nominations that the current user has submitted.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {
        "name": "show_my_cycles",
        "description": "Show cycles that the current user participates in. Optionally filter by a specific cycle state.",
        "parameters": {"type": "object", "required": [], "properties": {
            "state_filter": {
                "type": "string",
                "description": "Filter cycles by their state. Use when the user mentions words like active, nomination, closed, draft, released, results, archived, finalized.",
                "enum": ["ACTIVE", "NOMINATION", "CLOSED", "DRAFT", "RESULTS_RELEASED", "ARCHIVED", "FINALIZED"],
            },
        }},
    }},
    {"type": "function", "function": {"name": "show_templates",        "description": "List available review templates.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "show_team_nominations", "description": "Show team nomination approval requests pending for a manager.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "show_employees",        "description": "List all employees in the organisation.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "show_announcements",    "description": "Show active announcements or latest updates.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "show_audit_logs",       "description": "Show recent audit logs or activity history.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "show_my_profile",       "description": "Show the current user's profile or personal details.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "show_my_manager",       "description": "Show who the current user's manager is.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "show_my_team",          "description": "Show the current manager's direct reports or team members.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "when_is_my_review_due", "description": "Tell the user when their next review is due.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "who_has_not_submitted", "description": "List employees who have not yet submitted their feedback.", "parameters": {"type": "object", "properties": {}, "required": []}}},
    {"type": "function", "function": {"name": "help",                  "description": "Show what commands are available or how the assistant works.", "parameters": {"type": "object", "properties": {}, "required": []}}},

    # ── Action commands (with optional extractable parameters) ────────────
    {"type": "function", "function": {
        "name": "create_cycle",
        "description": "Create a new feedback review cycle.",
        "parameters": {"type": "object", "required": [], "properties": {
            "name":                 {"type": "string", "description": "Name of the cycle"},
            "description":          {"type": "string", "description": "Description of the cycle"},
            "quarter_year":         {"type": "string", "description": "Quarter and year, e.g. Q1 2026"},
            "review_deadline":      {"type": "string", "description": "Date by which reviews must be submitted"},
            "nomination_deadline":  {"type": "string", "description": "Date by which nominations must be submitted"},
            "nomination_approval":  {"type": "string", "description": "Whether manager approval is required for nominations"},
            "peer_enabled":         {"type": "string", "description": "Whether peer review is enabled"},
            "peer_count":           {"type": "string", "description": "Maximum number of peer nominations allowed"},
            "participant_emails":   {"type": "string", "description": "Comma-separated list of participant email addresses"},
        }},
    }},
    {"type": "function", "function": {
        "name": "create_template",
        "description": "Create a new review template.",
        "parameters": {"type": "object", "required": [], "properties": {
            "name":        {"type": "string", "description": "Name of the template"},
            "description": {"type": "string", "description": "Description of the template"},
        }},
    }},
    {"type": "function", "function": {
        "name": "nominate_peers",
        "description": "Nominate peers for a review cycle.",
        "parameters": {"type": "object", "required": [], "properties": {
            "peer_emails": {"type": "string", "description": "Comma-separated email addresses of peers to nominate"},
            "cycle_id":    {"type": "string", "description": "ID of the cycle to nominate for"},
        }},
    }},
    {"type": "function", "function": {
        "name": "activate_cycle",
        "description": "Activate a draft feedback cycle so nominations can begin.",
        "parameters": {"type": "object", "required": [], "properties": {
            "cycle_id": {"type": "string", "description": "ID or name of the cycle to activate"},
        }},
    }},
    {"type": "function", "function": {
        "name": "close_cycle",
        "description": "Close an active feedback cycle.",
        "parameters": {"type": "object", "required": [], "properties": {
            "cycle_id": {"type": "string", "description": "ID or name of the cycle to close"},
        }},
    }},
    {"type": "function", "function": {
        "name": "finalize_cycle",
        "description": "Finalize nominations for a cycle and generate reviewer tasks.",
        "parameters": {"type": "object", "required": [], "properties": {
            "cycle_id": {"type": "string", "description": "ID or name of the cycle to finalize"},
        }},
    }},
    {"type": "function", "function": {
        "name": "cancel_cycle",
        "description": "Cancel or archive a feedback cycle.",
        "parameters": {"type": "object", "required": [], "properties": {
            "cycle_id": {"type": "string", "description": "ID or name of the cycle to cancel"},
        }},
    }},
    {"type": "function", "function": {
        "name": "release_results",
        "description": "Release feedback results for a closed cycle.",
        "parameters": {"type": "object", "required": [], "properties": {
            "cycle_id": {"type": "string", "description": "ID or name of the cycle whose results to release"},
        }},
    }},
    {"type": "function", "function": {
        "name": "approve_nomination",
        "description": "Approve a specific peer nomination.",
        "parameters": {"type": "object", "required": [], "properties": {
            "nomination_id": {"type": "string", "description": "ID of the nomination to approve"},
        }},
    }},
    {"type": "function", "function": {
        "name": "reject_nomination",
        "description": "Reject a specific peer nomination with an optional reason.",
        "parameters": {"type": "object", "required": [], "properties": {
            "nomination_id":  {"type": "string", "description": "ID of the nomination to reject"},
            "rejection_note": {"type": "string", "description": "Reason for rejecting the nomination"},
        }},
    }},
    {"type": "function", "function": {
        "name": "approve_all_nominations",
        "description": "Bulk-approve all pending peer nominations for the current manager's team.",
        "parameters": {"type": "object", "required": [], "properties": {}},
    }},

    {"type": "function", "function": {
        "name": "retract_nomination",
        "description": "Remove a specific peer from the user's current nominations for a cycle.",
        "parameters": {"type": "object", "required": [], "properties": {
            "cycle_id":   {"type": "string", "description": "ID or name of the cycle"},
            "peer_email": {"type": "string", "description": "Email address of the peer to remove"},
        }},
    }},
    {"type": "function", "function": {
        "name": "create_template_from_text",
        "description": "Parse a pasted block of questions or document text and create a review template from it.",
        "parameters": {"type": "object", "required": [], "properties": {
            "name":    {"type": "string", "description": "Name for the new template"},
            "content": {"type": "string", "description": "The raw text/questions to parse into the template"},
        }},
    }},

    # ── Phase 3: Compound / summary ────────────────────────────────────────
    {"type": "function", "function": {
        "name": "summarize_my_status",
        "description": (
            "Give the user a complete overview of their current status across the 360° review system. "
            "Use when the user asks for a summary, overview, full status, or says things like "
            "'catch me up', 'what's my status', 'give me everything', 'am I behind', "
            "'what do I need to do', or 'how am I doing'."
        ),
        "parameters": {"type": "object", "required": [], "properties": {}},
    }},

    # ── Fallback ───────────────────────────────────────────────────────────
    {"type": "function", "function": {
        "name": "unknown",
        "description": "Use this when the user's message does not match any supported command.",
        "parameters": {"type": "object", "required": [], "properties": {
            "reason": {"type": "string", "description": "Brief reason why no command matched"},
        }},
    }},
]

_TOOL_CALL_SYSTEM = (
    "You are an intent-classification assistant for a 360° Feedback System.\n"
    "Your ONLY job is to pick the correct tool that matches the user's request and extract any "
    "parameter values mentioned in the message.\n"
    "Rules:\n"
    "1. Always call exactly one tool.\n"
    "2. Never invent parameter values not explicitly mentioned by the user.\n"
    "3. If nothing matches, call the 'unknown' tool.\n"
)


def detect_intent_tool_call(user_message: str, conversation_context: str = '', conversation_history: list = None) -> dict:
    """
    Use Cohere's tool-calling API to classify the user's message into a structured intent.
    Returns {"intent": str, "parameters": dict} — same contract as detect_intent().
    Falls back to detect_intent() if tool calling is unavailable or fails.

    Phase 3: conversation_history is a list of {role, content} dicts (last 5 exchanges).
    When provided, it is injected as real messages so the LLM understands follow-up questions.
    """
    api_key = _get_api_key()
    if not api_key:
        return {"intent": "unknown", "parameters": {}}

    messages = [{"role": "system", "content": _TOOL_CALL_SYSTEM}]
    if conversation_history:
        # Inject real conversation turns so LLM resolves pronouns and follow-up context
        for entry in conversation_history[-6:]:  # last 3 exchanges
            role = entry.get("role", "user")
            content = entry.get("content", "")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})
    elif conversation_context:
        messages.append({"role": "user", "content": f"Previous context:\n{conversation_context}"})
        messages.append({"role": "assistant", "content": "Understood. I will use this context."})
    messages.append({"role": "user", "content": user_message})

    try:
        response = requests.post(
            COHERE_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": COHERE_MODEL,
                "messages": messages,
                "tools": _INTENT_TOOLS,
            },
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()

        tool_calls = data.get("message", {}).get("tool_calls") or []
        if not tool_calls:
            logger.warning("Tool-calling returned no tool_calls; falling back to text detection.")
            return detect_intent(user_message, conversation_context)

        tc = tool_calls[0]
        intent = tc.get("function", {}).get("name", "unknown")
        raw_args = tc.get("function", {}).get("arguments", "{}")
        try:
            params = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
        except json.JSONDecodeError:
            params = {}

        if intent == "unknown":
            intent = "unknown"
            params = {}

        logger.debug("Tool-call detected intent=%s params=%s", intent, params)
        return {"intent": intent, "parameters": params}

    except Exception as e:
        logger.error("Tool-calling intent detection failed: %s — falling back to text detection.", e)
        return detect_intent(user_message, conversation_context)


def parse_template_content(raw_text: str) -> list:
    """
    Use Cohere to parse a raw text block (questions/document) into structured template sections.
    Returns: [{"title": str, "questions": [{"question_text": str, "type": str}]}]
    Falls back to a single-section template if parsing fails.
    """
    api_key = _get_api_key()
    if not api_key:
        return [{"title": "General", "questions": [{"question_text": raw_text[:300].strip(), "type": "TEXT"}]}]

    prompt = (
        "You are a template parser for a 360° performance review system.\n"
        "Parse the following text into a structured template with sections and questions.\n\n"
        "Return ONLY valid JSON (no explanation, no markdown) in this exact format:\n"
        '{"sections": [{"title": "Section Name", "questions": [{"question_text": "...", "type": "RATING"}]}]}\n\n'
        "Question types:\n"
        "  RATING — numeric ratings (e.g. 1–5 scale); use for skill/performance questions\n"
        "  TEXT — open-ended written answers; use for 'describe', 'explain', 'what' questions\n"
        "  MULTI_CHOICE — multiple choice options\n\n"
        "Rules:\n"
        "1. If no sections are explicitly marked, group related questions logically.\n"
        "2. Keep question_text close to the original wording.\n"
        "3. Return at least one section with at least one question.\n"
        "4. Respond ONLY with JSON.\n\n"
        f"Text to parse:\n{raw_text}\n\nJSON:"
    )

    try:
        response = requests.post(
            COHERE_API_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": COHERE_MODEL, "messages": [{"role": "user", "content": prompt}]},
            timeout=45,
        )
        response.raise_for_status()
        raw_out = response.json()["message"]["content"][0]["text"]
        parsed  = json.loads(_strip_json(raw_out))
        sections = parsed.get("sections", [])
        if sections:
            return sections
    except Exception as e:
        logger.error("parse_template_content failed: %s", e)

    return [{"title": "General", "questions": [{"question_text": raw_text[:500].strip(), "type": "TEXT"}]}]


def parse_template_content_with_clarifications(raw_text: str) -> dict:
    """
    Parse a raw text block into template sections/questions AND return a list
    of ambiguous items that need clarification from the user.

    Returns:
    {
        "sections": [...],           # LLM best-guess structured sections
        "template_name_guess": str,  # Guessed name from content, or ""
        "clarifications": [          # List of questions to ask the user
            {"id": "confirm_sections", "question": "...", "type": "confirm"},
            {"id": "ambiguous_types",  "question": "...", "type": "choice", "items": [...]},
            {"id": "mandatory",        "question": "...", "type": "yesno"},
        ]
    }
    """
    api_key = _get_api_key()
    if not api_key:
        return {"sections": [], "template_name_guess": "", "clarifications": []}

    prompt = (
        "You are a template parser for a 360° performance review system.\n"
        "Analyze the following text and:\n"
        "1. Parse it into sections and questions (best guess)\n"
        "2. Identify ambiguous items that need human clarification\n\n"
        "Return ONLY valid JSON (no explanation, no markdown) in this exact format:\n"
        "{\n"
        '  "template_name_guess": "2-5 word name inferred from the content, or empty string",\n'
        '  "sections": [\n'
        '    {"title": "Section Name", "questions": [{"question_text": "...", "type": "RATING", "is_required": true}]}\n'
        "  ],\n"
        '  "ambiguous_type_questions": [\n'
        '    "question text that could be RATING or TEXT"\n'
        "  ],\n"
        '  "possible_section_headers": [\n'
        '    "text that might be a section header or a question"\n'
        "  ],\n"
        '  "has_clear_mandatory_info": true\n'
        "}\n\n"
        "Question types:\n"
        "  RATING — numeric scale (1-5); use for skill/performance questions\n"
        "  TEXT   — open-ended written answer; use for describe/explain/what questions\n\n"
        "Rules:\n"
        "1. Always make your best guess for sections and questions.\n"
        "2. Flag any question where the type is genuinely ambiguous in ambiguous_type_questions.\n"
        "3. Flag any text item that could be either a section header or a question.\n"
        "4. Set has_clear_mandatory_info=false if the document doesn't specify which questions are required.\n"
        "5. Respond ONLY with JSON.\n\n"
        f"Text to parse:\n{raw_text}\n\nJSON:"
    )

    try:
        response = requests.post(
            COHERE_API_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": COHERE_MODEL, "messages": [{"role": "user", "content": prompt}]},
            timeout=45,
        )
        response.raise_for_status()
        raw_out = response.json()["message"]["content"][0]["text"]
        parsed  = json.loads(_strip_json(raw_out))

        sections          = parsed.get("sections", [])
        name_guess        = parsed.get("template_name_guess", "").strip()
        ambiguous_types   = parsed.get("ambiguous_type_questions", [])
        possible_headers  = parsed.get("possible_section_headers", [])
        has_mandatory     = parsed.get("has_clear_mandatory_info", True)

        # Build clarification queue
        clarifications = []

        # 1. Always confirm the section structure
        section_names = [s.get("title", "Untitled") for s in sections]
        q_count = sum(len(s.get("questions", [])) for s in sections)
        clarifications.append({
            "id":       "confirm_sections",
            "type":     "confirm",
            "question": (
                f"I found **{len(sections)} section(s)** and **{q_count} question(s)**:\n"
                + "\n".join(f"  • **{n}**" for n in section_names)
                + "\n\nDoes this structure look correct? (yes / describe what to change)"
            ),
        })

        # 2. Ambiguous section headers
        if possible_headers:
            clarifications.append({
                "id":       "section_headers",
                "type":     "choice",
                "question": (
                    "These items could be **section headers** or **questions** — I've treated them as sections. "
                    "Should any of them be questions instead?\n"
                    + "\n".join(f"  {i+1}. {h}" for i, h in enumerate(possible_headers))
                    + "\n\n(Say 'ok' if correct, or list the numbers that should be questions)"
                ),
                "items": possible_headers,
            })

        # 3. Ambiguous question types
        if ambiguous_types:
            clarifications.append({
                "id":       "ambiguous_types",
                "type":     "choice",
                "question": (
                    "These questions have **unclear types** — I've made a best guess. "
                    "Should any be changed to TEXT (written answer) instead of RATING (1-5 scale)?\n"
                    + "\n".join(f"  {i+1}. {q}" for i, q in enumerate(ambiguous_types))
                    + "\n\n(Say 'ok' if correct, or list the numbers to change to TEXT)"
                ),
                "items": ambiguous_types,
            })

        # 4. Mandatory fields
        if not has_mandatory:
            clarifications.append({
                "id":       "mandatory",
                "type":     "yesno",
                "question": "Should **all questions** be mandatory? (yes / no — if no, I'll make all optional)",
            })

        return {
            "sections":           sections,
            "template_name_guess": name_guess,
            "clarifications":     clarifications,
        }

    except Exception as e:
        logger.error("parse_template_content_with_clarifications failed: %s", e)
        # Fall back to basic parse
        sections = parse_template_content(raw_text)
        return {"sections": sections, "template_name_guess": "", "clarifications": []}


def detect_intent(user_message: str, conversation_context: str = '') -> dict:
    """
    Call Cohere to detect intent and extract parameters from user message.
    Loads the system prompt from the PromptTemplate DB table; falls back to
    the hardcoded _FALLBACK_INTENT_PROMPT if the DB is unavailable.
    Returns: {"intent": str, "parameters": dict}
    """
    raw_template = _load_intent_prompt()
    full_prompt  = (
        raw_template
        .replace('{{conversation_context}}', conversation_context or 'None')
        .replace('{{user_message}}', user_message)
    )

    api_key = _get_api_key()
    if not api_key:
        return {"intent": "unknown", "parameters": {}}

    try:
        response = requests.post(
            COHERE_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": COHERE_MODEL,
                "messages": [{"role": "user", "content": full_prompt}],
            },
            timeout=30,
        )
        response.raise_for_status()
        data     = response.json()
        raw_text = data["message"]["content"][0]["text"]
        clean    = _strip_json(raw_text)
        parsed   = json.loads(clean)
        return {
            "intent":     parsed.get("intent", "unknown"),
            "parameters": parsed.get("parameters", {}),
        }
    except Exception as e:
        logger.error("LLM intent detection failed: %s", e)
        return {"intent": "unknown", "parameters": {}}


def _build_response_prompt(user_message: str, system_data: dict) -> str:
    return (
        "You are an assistant helping users interact with the 360° Feedback System.\n"
        "Your job is to generate a helpful natural language response based on system data.\n\n"
        "Rules:\n"
        "1. Be concise and professional.\n"
        "2. Do not expose sensitive information.\n"
        "3. Respect anonymity rules.\n"
        "4. Never reveal reviewer identities.\n\n"
        f"Context:\n{json.dumps(system_data, indent=2)}\n\n"
        f"User Request:\n{user_message}\n\n"
        "Generate a clear and helpful response for the user."
    )


def _format_context_as_text(context_data: dict) -> str:
    """
    Local fallback formatter — converts raw context dicts into readable markdown
    when the Cohere API is unavailable (rate-limit, timeout, etc.).
    """
    parts = []
    for key, val in context_data.items():
        if not isinstance(val, dict):
            continue
        if val.get("error"):
            parts.append(f"⚠️ {val['error']}")
            continue
        ctype = val.get("type", key)

        if ctype == "top_performers":
            performers = val.get("performers", [])
            cycle = val.get("cycle", "")
            parts.append(f"**Top Performers** ({cycle})\n")
            for p in performers:
                dept = f" — {p['department']}" if p.get("department") else ""
                parts.append(
                    f"{p['rank']}. **{p['name']}**{dept} — Overall: **{p['overall_score']:.1f}**"
                    + (f" (Peer: {p['peer_score']:.1f}" if p.get("peer_score") else "")
                    + (f", Mgr: {p['manager_score']:.1f})" if p.get("manager_score") else (")" if p.get("peer_score") else ""))
                )

        elif ctype == "bottom_performers":
            # Note: get_bottom_performers() returns 'employees' key (not 'performers')
            performers = val.get("employees", val.get("performers", []))
            cycle = val.get("cycle", "")
            parts.append(f"**Employees Needing Support** ({cycle})\n")
            for p in performers:
                score = p.get('overall_score')
                score_str = f"{score:.1f}" if score is not None else "N/A"
                parts.append(f"• **{p['name']}** — Overall: {score_str}")

        elif ctype == "org_overview":
            parts.append("**Organisation Overview**\n")
            emp = val.get('total_active_employees') or val.get('total_employees')
            if emp is not None:
                parts.append(f"• Total active employees: {emp}")
            if val.get('active_cycles') is not None:
                parts.append(f"• Active cycles: {val['active_cycles']}")
            released = val.get('results_released_cycles') or val.get('released_cycles')
            if released is not None:
                parts.append(f"• Results-released cycles: {released}")
            if val.get('closed_cycles') is not None:
                parts.append(f"• Closed cycles: {val['closed_cycles']}")
            if val.get("avg_overall_score"):
                parts.append(f"• Org average score: **{val['avg_overall_score']:.2f} / 5.0**")
            if val.get("pending_reviewer_tasks") is not None:
                parts.append(f"• Pending review tasks: {val['pending_reviewer_tasks']}")

        elif ctype == "department_stats":
            depts = val.get("departments", [])
            parts.append("**Department Scores**\n")
            for d in depts:
                score = d.get('avg_overall_score') or d.get('avg_score')
                score_str = f"{score:.2f}" if score is not None else "N/A"
                parts.append(
                    f"• **{d.get('department', 'Unknown')}**: avg **{score_str}** / 5.0"
                    f" ({d.get('employee_count', '?')} employees)"
                )

        elif ctype == "cycle_summary":
            cname = val.get('cycle_name') or val.get('name', '')
            cstate = val.get('cycle_state') or val.get('state', 'N/A')
            parts.append(f"**Cycle Summary: {cname}**\n")
            parts.append(f"• State: {cstate}")
            if val.get('total_participants') is not None:
                parts.append(f"• Participants: {val['total_participants']}")
            rate = val.get('submission_rate_pct') or val.get('completion_rate')
            if rate is not None:
                parts.append(f"• Submission rate: {rate:.0f}%")
            if val.get('avg_overall_score'):
                parts.append(f"• Avg score: {val['avg_overall_score']:.2f}")

        elif ctype == "team_overview":
            members = val.get("members", [])
            parts.append(f"**Team Overview** ({len(members)} members)\n")
            for m in members:
                score_str = f" — Score: {m['overall_score']:.1f}" if m.get("overall_score") else ""
                parts.append(f"• {m.get('name', m.get('email', 'Unknown'))}{score_str}")

    return "\n".join(parts) if parts else "No data available for this query."


def generate_data_analysis_stream(user_question: str, context_data: dict, user_role: str, chat_history: list = None):
    """
    Stream a data-driven analytical response using live DB context.
    The LLM receives real numbers/feedback from the DB and answers grounded in that data.
    Reviewer identities are never included in context_data — anonymity is preserved.
    chat_history: last N {role, content} exchanges from Redis — injected for follow-up continuity.
    """
    api_key = _get_api_key()
    if not api_key:
        yield "I was unable to generate an analysis. Please try again."
        return

    system_prompt = (
        f"You are Gamyam 360° Analytics Assistant — an expert at analyzing 360° performance review data.\n"
        f"You are speaking to a user with role: {user_role}.\n\n"
        "You have been given live data fetched directly from the 360° feedback database. "
        "Use ONLY this data to answer the user's question. Be analytical, specific, and insightful.\n\n"
        "Rules:\n"
        "1. Reference specific numbers, names, scores, and trends from the data.\n"
        "2. For improvement suggestions: be constructive and specific based on feedback text.\n"
        "3. For cross-cycle comparisons: highlight the delta and what it means.\n"
        "4. Never reveal reviewer identities — all feedback is anonymized.\n"
        "5. If data is missing or incomplete, say so clearly rather than guessing.\n"
        "6. Keep the response clear and professional. Use bullet points where helpful.\n"
        "7. If the user is asking a follow-up question about a previous response, use the conversation history.\n\n"
        f"Live Database Context:\n{json.dumps(context_data, indent=2, default=str)}\n\n"
        "Provide a clear, data-driven analysis:"
    )

    # Build message list with conversation history injected
    messages = [{"role": "system", "content": system_prompt}]
    if chat_history:
        for entry in chat_history[-6:]:
            role = entry.get("role", "user")
            content = entry.get("content", "")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content[:600]})
    messages.append({"role": "user", "content": user_question})

    try:
        response = requests.post(
            COHERE_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": COHERE_MODEL,
                "messages": messages,
                "stream": True,
            },
            timeout=45,
            stream=True,
        )
        response.raise_for_status()
        for raw_line in response.iter_lines():
            if not raw_line:
                continue
            if isinstance(raw_line, bytes):
                raw_line = raw_line.decode("utf-8")
            if not raw_line.startswith("data: "):
                continue
            try:
                event = json.loads(raw_line[6:])
            except json.JSONDecodeError:
                continue
            if event.get("type") == "content-delta":
                text = (
                    event.get("delta", {})
                    .get("message", {})
                    .get("content", {})
                    .get("text", "")
                )
                if text:
                    yield text
    except Exception as e:
        logger.error("generate_data_analysis_stream failed: %s", e)
        # Local fallback: format the raw DB data as readable text so the user
        # still gets useful information even when the Cohere API is unavailable.
        fallback_text = _format_context_as_text(context_data)
        yield fallback_text


def pdf_template_conversation_stream(pdf_text: str, pdf_history: list, user_message: str):
    """
    Stream a conversational LLM response for PDF → template creation.

    The LLM reads the PDF text, chats naturally with the user, and — when the user
    confirms creation — outputs the __CREATE_TEMPLATE__:{json} signal on the final line.

    Handles all cases:
      • Natural questions about the PDF content
      • Add / remove / rename / reorder sections and questions
      • Add manual questions not in the PDF
      • Change question types (RATING ↔ TEXT)
      • Make questions mandatory or optional
      • Abandon / cancel

    Returns a generator of text chunks (SSE streaming).
    The caller must detect the __CREATE_TEMPLATE__: signal in the accumulated output.
    """
    api_key = _get_api_key()
    if not api_key:
        yield "I was unable to process your request. Please try again."
        return

    system_prompt = (
        "You are a helpful AI assistant for a 360° performance review system.\n"
        "You are helping the user create a feedback template from an uploaded document.\n\n"
        "## DOCUMENT\n"
        f"{pdf_text[:10000]}\n\n"
        "## YOUR JOB\n"
        "1. Read the document, understand its structure (sections, questions, topics).\n"
        "2. On the first turn, greet the user, summarise what you found (sections + question count), "
        "and show a clear numbered outline. Ask if they'd like to adjust anything.\n"
        "3. Chat naturally — the user may:\n"
        "   • Add questions not in the PDF (\"Add a question about leadership\")\n"
        "   • Remove questions (\"Remove question 3\" or \"Remove the teamwork section\")\n"
        "   • Rename sections or questions\n"
        "   • Reorder sections or questions (\"Move question 5 to the top\")\n"
        "   • Change question types (\"Make question 2 a rating scale\" / \"Change to text\")\n"
        "   • Mark questions mandatory or optional (\"Make all questions required\")\n"
        "   • Ask questions about the PDF content (\"What does section 2 cover?\")\n"
        "   • Say 'abandon', 'cancel', or 'start over' to stop\n"
        "   • Say 'looks good', 'create it', 'go ahead', 'yes create', 'confirm', "
        "'that's good', 'proceed' to finalise\n\n"
        "## QUESTION TYPES\n"
        "  RATING       — numeric scale 1-5; for skill/performance questions\n"
        "  TEXT         — open-ended written answer; for describe/explain/what questions\n"
        "  MULTI_CHOICE — multiple choice options\n\n"
        "## WHEN USER CONFIRMS CREATION\n"
        "When the user says 'create it', 'looks good', 'go ahead', 'yes create', 'confirm', "
        "'proceed', 'that's good', or any clear confirmation:\n"
        "1. Write a short, natural confirmation message to the user.\n"
        "2. On the VERY LAST LINE, with no trailing text, output EXACTLY:\n"
        "__CREATE_TEMPLATE__:{valid_json}\n\n"
        "The JSON schema:\n"
        "{\n"
        '  "name": "Template name (2-6 words, inferred from content)",\n'
        '  "description": "One-line description or null",\n'
        '  "sections": [\n'
        '    {\n'
        '      "title": "Section name",\n'
        '      "questions": [\n'
        '        {\n'
        '          "question_text": "Question text",\n'
        '          "type": "RATING",\n'
        '          "is_required": true\n'
        '        }\n'
        '      ]\n'
        '    }\n'
        '  ]\n'
        '}\n\n'
        "## IMPORTANT RULES\n"
        "- Keep responses concise and professional.\n"
        "- When showing the template outline, number sections and questions clearly.\n"
        "- After each change, show the updated relevant section so the user can verify.\n"
        "- If the document is a scanned image with no readable text, say so clearly.\n"
        "- If document content is empty or garbled, say it appears unreadable.\n"
        "- If user says 'abandon' / 'cancel' / 'start over': acknowledge and stop (do NOT output __CREATE_TEMPLATE__).\n"
        "- NEVER output __CREATE_TEMPLATE__ unless the user has explicitly confirmed creation.\n"
        "- The __CREATE_TEMPLATE__ JSON must be valid — no trailing text after the JSON.\n"
    )

    # Build message list: system + conversation history
    messages = [{"role": "system", "content": system_prompt}]
    for entry in (pdf_history or []):
        role = entry.get("role", "user")
        content = entry.get("content", "")
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_message})

    try:
        response = requests.post(
            COHERE_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": COHERE_MODEL,
                "messages": messages,
                "stream": True,
            },
            timeout=60,
            stream=True,
        )
        response.raise_for_status()
        for raw_line in response.iter_lines():
            if not raw_line:
                continue
            if isinstance(raw_line, bytes):
                raw_line = raw_line.decode("utf-8")
            if not raw_line.startswith("data: "):
                continue
            try:
                event = json.loads(raw_line[6:])
            except json.JSONDecodeError:
                continue
            if event.get("type") == "content-delta":
                text = (
                    event.get("delta", {})
                    .get("message", {})
                    .get("content", {})
                    .get("text", "")
                )
                if text:
                    yield text
    except Exception as e:
        logger.error("pdf_template_conversation_stream failed: %s", e)
        yield "I was unable to process your request. Please try again."


def generate_response(user_message: str, system_data: dict) -> str:
    """
    Call Cohere to generate a natural language response based on system data.
    """
    api_key = _get_api_key()
    if not api_key:
        return "I was unable to generate a response. Please try again."

    system_prompt = _build_response_prompt(user_message, system_data)
    try:
        response = requests.post(
            COHERE_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": COHERE_MODEL,
                "messages": [{"role": "user", "content": system_prompt}],
            },
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        return data["message"]["content"][0]["text"].strip()
    except Exception as e:
        logger.error(f"LLM response generation failed: {e}")
        return "I was unable to generate a response. Please try again."


def generate_suggestions(question: str, user_role: str) -> list[str]:
    """
    Generate 3 contextual follow-up suggestions after a data analysis response.
    Used for open-ended LLM questions (Option B of the hybrid approach).
    Returns a list of up to 3 short command/question strings, or [] on failure.
    """
    api_key = _get_api_key()
    if not api_key:
        return []

    prompt = (
        f'A user with role "{user_role}" in an HR 360° feedback system just asked:\n'
        f'"{question}"\n\n'
        'Generate exactly 3 short follow-up questions or commands they would naturally '
        'want to ask next. Keep each under 8 words. Make them specific to HR analytics, '
        '360 feedback, or org insights.\n'
        'Return ONLY a JSON array of 3 strings, nothing else.\n'
        'Example: ["Who are the top performers?", "Show participation stats", '
        '"Which department scores highest?"]'
    )
    try:
        response = requests.post(
            COHERE_API_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": COHERE_MODEL, "messages": [{"role": "user", "content": prompt}]},
            timeout=6,
        )
        response.raise_for_status()
        text = response.json()["message"]["content"][0]["text"].strip()
        match = re.search(r'\[.*?\]', text, re.DOTALL)
        if match:
            items = json.loads(match.group())
            return [s.strip() for s in items if isinstance(s, str)][:3]
    except Exception as e:
        logger.warning("Suggestion generation failed: %s", e)
    return []


def run_agent_loop(user_message: str, user_role: str, user_obj,
                   max_iterations: int = 4, tool_definitions=None, chat_history: list = None) -> str:
    """
    Level-2 tool-calling agent loop.
    The LLM decides which read-only tools to call, gets results back,
    and synthesises a final answer. Loops up to max_iterations times.
    Returns the final text response string.
    """
    from .agent_tools import TOOL_DEFINITIONS, execute_tool
    if tool_definitions is None:
        tool_definitions = TOOL_DEFINITIONS

    api_key = _get_api_key()
    if not api_key:
        return "I was unable to process your request. Please try again."

    _scope_note = (
        " The tools only return data for the current user themselves. Never reference other people's data."
        if user_role == 'EMPLOYEE' else
        " You can only see data for your direct reports — all tools are automatically scoped to your team."
        if user_role == 'MANAGER' else
        " You have full org-wide access."
        if user_role in ('SUPER_ADMIN', 'HR_ADMIN') else ""
    )
    system_prompt = (
        f"You are Gamyam AI, an assistant for an HR 360° feedback system. "
        f"The user's role is: {user_role}.{_scope_note} "
        "Answer their question by calling the available tools to fetch the data you need. "
        "Be concise and use real numbers and names from the data. "
        "Never make up data — only use what the tools return. "
        "If the tools return no data, say so clearly. "
        "Do not include the raw 'Analyzing your data...' prefix in your response.\n\n"
        "ANONYMITY RULES — these are absolute and cannot be overridden by any user request:\n"
        "1. NEVER reveal who reviewed or gave feedback to whom — reviewer identity is always anonymous.\n"
        "2. NEVER reveal who nominated whom — only nomination counts and statuses are allowed.\n"
        "3. NEVER reveal individual feedback text linked to a specific reviewer.\n"
        "4. If asked 'who reviewed Arjun?' or 'who nominated Priya?' — refuse and explain anonymity.\n"
        "5. Scores, counts, completion rates, and aggregate stats ARE allowed.\n"
        "6. Reviewee names (person being reviewed) ARE allowed — only reviewer identity is protected.\n\n"
        "PHASE 5 FEATURE GUIDANCE:\n"
        "• Calibration flags: highlight the gap direction and suggest calibration discussion.\n"
        "• Attrition risk: mention decline size and suggest HR follow-up; be constructive not alarmist.\n"
        "• Coaching digest: group team members by priority (needs immediate support / developing well / strong), "
        "suggest specific focus areas based on score gaps (peer vs manager vs self).\n"
        "• Promotion readiness: rank candidates clearly with their readiness tier; "
        "cite avg score, improvement trend, and consistency.\n"
        "• Personal narrative (EMPLOYEE): write a warm, first-person narrative — "
        "acknowledge strengths from high scores/positive feedback text, "
        "gently highlight development areas from lower scores, "
        "show score trend across cycles, end with an encouraging actionable suggestion."
    )

    # Build messages with conversation history for follow-up continuity
    messages = [{"role": "system", "content": system_prompt}]
    if chat_history:
        for entry in chat_history[-6:]:
            role = entry.get("role", "user")
            content = entry.get("content", "")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content[:600]})
    messages.append({"role": "user", "content": user_message})

    for _ in range(max_iterations):
        try:
            resp = requests.post(
                COHERE_API_URL,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": COHERE_MODEL, "messages": messages, "tools": tool_definitions},
                timeout=30,
            )
            resp.raise_for_status()
            msg        = resp.json().get("message", {})
            tool_calls = msg.get("tool_calls") or []

            # No tool calls → LLM has enough data, extract final answer
            if not tool_calls:
                for item in (msg.get("content") or []):
                    if item.get("type") == "text":
                        return item.get("text", "").strip()
                return "I was unable to generate a response."

            # Add assistant turn (with tool_calls) to conversation
            messages.append({
                "role":       "assistant",
                "tool_calls": tool_calls,
                "content":    msg.get("content") or [],
            })

            # Execute each tool call and feed results back
            for tc in tool_calls:
                fn        = tc.get("function", {})
                tool_name = fn.get("name", "")
                try:
                    tool_args = json.loads(fn.get("arguments", "{}"))
                except (json.JSONDecodeError, TypeError):
                    tool_args = {}

                result = execute_tool(tool_name, tool_args, user_obj)
                messages.append({
                    "role":         "tool",
                    "tool_call_id": tc.get("id", ""),
                    "content":      result,
                })

        except Exception as e:
            logger.error("Agent loop error: %s", e)
            break

    return "I was unable to complete the analysis. Please try again."


def generate_response_stream(user_message: str, system_data: dict):
    """
    Yield text chunks from Cohere's streaming API.
    Falls back to a single error chunk if the API key is missing or the call fails.
    """
    api_key = _get_api_key()
    if not api_key:
        yield "I was unable to generate a response. Please try again."
        return

    system_prompt = _build_response_prompt(user_message, system_data)
    try:
        response = requests.post(
            COHERE_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": COHERE_MODEL,
                "messages": [{"role": "user", "content": system_prompt}],
                "stream": True,
            },
            timeout=30,
            stream=True,
        )
        response.raise_for_status()
        for raw_line in response.iter_lines():
            if not raw_line:
                continue
            if isinstance(raw_line, bytes):
                raw_line = raw_line.decode("utf-8")
            # Cohere streaming uses SSE format: skip non-data lines (e.g. "event: content-delta")
            if not raw_line.startswith("data: "):
                continue
            try:
                event = json.loads(raw_line[6:])  # strip "data: " prefix
            except json.JSONDecodeError:
                continue
            if event.get("type") == "content-delta":
                # Cohere v2 path: delta.message.content.text
                text = (
                    event.get("delta", {})
                    .get("message", {})
                    .get("content", {})
                    .get("text", "")
                )
                if text:
                    yield text
    except Exception as e:
        logger.error("LLM streaming failed: %s", e)
        yield "I was unable to generate a response. Please try again."

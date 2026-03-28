"""
app_knowledge.py — App guide & FAQ layer

Handles questions about how the Gamyam 360° feedback app works.
Option A: Static FAQ dict  — instant, free, no LLM
Option B: LLM fallback     — command-light model, cheap + fast

Sits between the agent and out-of-scope in the pipeline.
"""
import re
import logging

logger = logging.getLogger(__name__)

# ── Keywords that signal "how does this app work?" questions ──────────────────
_APP_KNOWLEDGE_PATTERNS = [
    r'\bwhat is (a |the |this )?(360|gamyam|app|system|platform|tool)',
    r'\bhow does (the |this |a )?(360|nomination|cycle|feedback|review|scoring|result)',
    r'\bhow (do|can|should) (i|we|employees|managers)',
    r'\bwhat (is|are|does) (a |the )?(cycle|nomination|template|peer review|self review|manager review|score|result|360)',
    r'\bexplain (the |a |this )?(cycle|nomination|process|flow|scoring|review|360|system)',
    r'\bwhat happen(s)? when',
    r'\bwhat (can|should) (i|a manager|an employee|hr)',
    r'\bwho (can|should|is supposed to)',
    r'\bwhy (do|does|is|are)',
    r'\bget started',
    r'\bhow (to|do i) (start|begin|use|access|submit|nominate|view|see)',
    r'\bwhat (is|are) my (role|responsibility|responsibilities|access|permission)',
    r'\bguide|tutorial|walkthrough|help me understand|confused|new here|first time',
    r'\bwhat does (results released|closed|active|draft|nomination|finalized|archived) mean',
    r'\bdifference between',
    r'\bwhat does (gamyam|the app|this app|the system) do',
]

_APP_PATTERN = re.compile('|'.join(_APP_KNOWLEDGE_PATTERNS), re.IGNORECASE)


def is_app_knowledge_question(message: str) -> bool:
    """Return True if the message is asking about how the app works."""
    return bool(_APP_PATTERN.search(message))


# ── Static FAQ (Option A) ─────────────────────────────────────────────────────
# Keys are lowercase keyword phrases. First match wins.

_STATIC_FAQ = {
    'what is a 360': (
        "**What is a 360° Review?**\n\n"
        "A 360° review collects feedback about an employee from multiple sources:\n"
        "• **Self** — the employee rates themselves\n"
        "• **Peers** — colleagues nominated by the employee provide feedback\n"
        "• **Manager** — the employee's direct manager gives ratings\n"
        "• **Direct Reports** — if the employee manages others, their reports also give feedback\n\n"
        "This gives a well-rounded (360°) view of performance instead of just a top-down review."
    ),
    'what is gamyam': (
        "**Gamyam 360° Feedback System**\n\n"
        "Gamyam AI is your all-in-one 360° performance review platform. It helps your organisation:\n"
        "• Run structured feedback cycles for all employees\n"
        "• Collect peer, manager, self, and direct-report feedback\n"
        "• Track participation, nominations, and review submissions\n"
        "• View analytics and performance scores\n\n"
        "Just ask me anything — I can run commands, show data, or answer questions about how the system works."
    ),
    'how does nomination': (
        "**How Nominations Work**\n\n"
        "1. HR activates a cycle — employees receive a notification\n"
        "2. Each employee **nominates peers** they want feedback from (e.g. 3–5 peers)\n"
        "3. If the cycle requires manager approval, the manager reviews and approves/rejects nominations\n"
        "4. Once nominations are finalised, reviewer tasks are created for each nominated peer\n"
        "5. Peers then receive tasks to submit feedback about the employee\n\n"
        "You can nominate peers by saying: **\"nominate peers\"**"
    ),
    'how does the cycle': (
        "**Review Cycle Lifecycle**\n\n"
        "A cycle moves through these states:\n"
        "1. **DRAFT** — HR creates the cycle, sets deadlines and participants\n"
        "2. **ACTIVE (Nomination)** — HR activates it; employees nominate peers\n"
        "3. **FINALIZED** — HR finalises nominations; reviewer tasks are generated\n"
        "4. **ACTIVE (Review)** — Peers submit their feedback forms\n"
        "5. **CLOSED** — Deadline passed; HR closes the cycle\n"
        "6. **RESULTS RELEASED** — HR releases scores; employees can view results\n"
        "7. **ARCHIVED** — Cycle is archived for historical records"
    ),
    'what happen when cycle close': (
        "**When a Cycle is Closed:**\n\n"
        "• No more feedback submissions are accepted\n"
        "• HR can view all submitted responses and scores\n"
        "• Scores are calculated (peer average, manager score, self score → overall)\n"
        "• HR then releases results to make them visible to employees\n\n"
        "Employees can only see their scores after HR does **Release Results**."
    ),
    'what happen when results released': (
        "**When Results are Released:**\n\n"
        "• Employees can view their overall score, peer score, manager score, and self score\n"
        "• Anonymous feedback text (if configured) becomes visible\n"
        "• Managers can view their team's scores\n"
        "• HR and Super Admins see full org-wide analytics\n\n"
        "Say **\"show my feedback\"** to see your results."
    ),
    'how is score calculated': (
        "**How Scores are Calculated**\n\n"
        "Scores are on a **1–5 scale**:\n"
        "• **Peer Score** — average of all ratings given by nominated peers\n"
        "• **Manager Score** — rating given by the direct manager\n"
        "• **Self Score** — employee's self-rating\n"
        "• **Overall Score** — weighted average of all the above\n\n"
        "The exact weights are configured per review template. Typically peers carry the most weight."
    ),
    'what is a template': (
        "**What is a Review Template?**\n\n"
        "A template is the set of questions used in a feedback form. It defines:\n"
        "• **Sections** — groups of related questions (e.g. Communication, Leadership)\n"
        "• **Questions** — either rating scale (1–5) or open-ended text\n"
        "• **Mandatory/Optional** — which questions must be answered\n\n"
        "HR Admins can create templates. Say **\"show templates\"** to see available ones."
    ),
    'what can i do as employee': (
        "**As an Employee, you can:**\n\n"
        "• **Nominate peers** for a feedback cycle\n"
        "• **Submit feedback** for peers who nominated you\n"
        "• **View your own results** after they are released\n"
        "• **See your tasks** — pending feedback forms to complete\n"
        "• **Track cycle deadlines** — so you never miss a submission\n\n"
        "Try: *\"show my tasks\"*, *\"show my feedback\"*, *\"nominate peers\"*"
    ),
    'what can i do as manager': (
        "**As a Manager, you can:**\n\n"
        "• **Review and approve** your team's peer nominations\n"
        "• **Submit feedback** for your direct reports\n"
        "• **View team summary** — see your team's participation and scores\n"
        "• **See pending reviews** — your own reviewer tasks\n\n"
        "Try: *\"show team nominations\"*, *\"show team summary\"*, *\"show pending reviews\"*"
    ),
    'what can i do as hr': (
        "**As an HR Admin, you can:**\n\n"
        "• **Create and manage cycles** — draft, activate, close, release results\n"
        "• **Create review templates** — define questions and scoring\n"
        "• **View participation stats** — who has submitted, who hasn't\n"
        "• **Manage employees** — add, update, bulk import\n"
        "• **Ask analytics questions** — top performers, department scores, trends\n\n"
        "Try: *\"create a cycle\"*, *\"show participation\"*, *\"who are the top performers?\"*"
    ),
    'how do i submit feedback': (
        "**How to Submit Feedback**\n\n"
        "1. Say **\"show my tasks\"** or **\"show pending reviews\"** to see your reviewer tasks\n"
        "2. Click on a task — it will open the feedback form\n"
        "3. Fill in ratings (1–5) and written feedback for each question\n"
        "4. Submit before the cycle deadline\n\n"
        "You can also ask: *\"when is my review due?\"* to check deadlines."
    ),
    'difference between closed and results released': (
        "**Closed vs Results Released**\n\n"
        "• **CLOSED** — The cycle has ended and no more submissions are accepted. "
        "Scores are calculated but **not yet visible** to employees.\n\n"
        "• **RESULTS RELEASED** — HR has made scores visible. "
        "Employees can now see their feedback and ratings.\n\n"
        "Think of it as: Closed = marking done, Results Released = report cards given out."
    ),
    'get started': (
        "**Getting Started with Gamyam 360°**\n\n"
        "Here's what to do based on your role:\n\n"
        "**Employee:**\n"
        "1. Check if you're in an active cycle → *\"show my cycles\"*\n"
        "2. Nominate your peers → *\"nominate peers\"*\n"
        "3. Complete your review tasks → *\"show my tasks\"*\n\n"
        "**Manager:**\n"
        "1. Approve team nominations → *\"show team nominations\"*\n"
        "2. Submit reviews for your reports → *\"show pending reviews\"*\n\n"
        "**HR Admin:**\n"
        "1. Create a cycle → *\"create a cycle\"*\n"
        "2. Activate it → *\"activate cycle\"*\n"
        "3. Monitor participation → *\"show participation\"*\n\n"
        "Ask me anything — I'm here to help!"
    ),
}


def get_static_answer(message: str) -> str | None:
    """
    Check message against the static FAQ dict.
    Returns the answer string if a keyword matches, else None.
    """
    lower = message.lower()
    for keyword, answer in _STATIC_FAQ.items():
        if keyword in lower:
            return answer
    return None


# ── LLM fallback (Option B) ───────────────────────────────────────────────────

_APP_GUIDE_SYSTEM_PROMPT = """You are Gamyam AI, a helpful assistant embedded inside the Gamyam 360° Feedback System.

Your job is to answer questions about HOW the app works — explaining features, processes, and concepts to users.

## About Gamyam 360°
Gamyam is an enterprise 360° performance review platform with these features:
- **Review Cycles**: HR creates cycles with deadlines. Employees nominate peers, managers approve, peers submit feedback.
- **Roles**: EMPLOYEE (nominate peers, submit reviews, view own results), MANAGER (approve nominations, submit reviews, view team), HR_ADMIN (manage cycles, templates, view org analytics), SUPER_ADMIN (full access + audit logs).
- **Cycle States**: DRAFT → ACTIVE(Nomination) → FINALIZED → ACTIVE(Review) → CLOSED → RESULTS_RELEASED → ARCHIVED
- **Scoring**: Peer score (avg of peer ratings), Manager score, Self score → Overall score (weighted avg, scale 1-5)
- **Templates**: HR creates question templates (RATING 1-5 or TEXT open-ended) organised into sections
- **Nominations**: Employees pick 3-5 peers → manager approves → peers get reviewer tasks
- **Chat Commands**: Users can type natural language commands like "show my tasks", "nominate peers", "activate cycle"
- **Analytics**: HR/SA can ask free-form data questions like "who are the top performers?", "show department stats"

## Rules
1. Be concise, friendly, and helpful.
2. If the user asks how to do something in the app, also tell them the chat command they can use.
3. Keep responses under 200 words unless a detailed explanation is needed.
4. Use bullet points and bold text for clarity.
5. Never make up features that don't exist — if unsure, say so.
"""


def answer_app_question_stream(user_question: str, user_role: str, chat_history: list = None):
    """
    Stream a response for an app knowledge question using command-light (cheap + fast).
    Injects chat history for conversational follow-up support.
    Returns a generator of text chunks.
    """
    import requests
    from django.conf import settings

    api_key = getattr(settings, 'COHERE_API_KEY', None)
    if not api_key:
        yield "I'm having trouble connecting right now. Please try again shortly."
        return

    messages = [{"role": "system", "content": _APP_GUIDE_SYSTEM_PROMPT}]

    # Inject last 4 exchanges for follow-up continuity
    if chat_history:
        for entry in (chat_history or [])[-8:]:
            role = entry.get("role", "user")
            content = entry.get("content", "")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content[:600]})

    messages.append({"role": "user", "content": user_question})

    try:
        response = requests.post(
            "https://api.cohere.com/v2/chat",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": "command-r-08-2024",  # cheaper + fast, good for FAQ
                "messages": messages,
                "stream": True,
            },
            timeout=30,
            stream=True,
        )
        response.raise_for_status()
        import json
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
        logger.error("answer_app_question_stream failed: %s", e)
        yield (
            "I'm Gamyam AI, here to help you with the 360° feedback system. "
            "You can ask me how the nomination process works, what a review cycle is, "
            "or say commands like 'show my tasks' or 'show my feedback'."
        )

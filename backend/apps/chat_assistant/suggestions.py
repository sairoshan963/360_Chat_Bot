"""
Contextual next-step suggestions for each chat command intent.

Rule-based (Option A of hybrid): for every known command that completes
successfully, return 2-3 logical follow-up commands the user is likely to
want next — based on natural workflow progressions.

LLM-generated suggestions (Option B) are handled in llm_service.generate_suggestions()
and used only for open-ended data analysis responses.
"""

# intent → [suggestion label, ...]
# Suggestions are ordered by likelihood; frontend shows the first 3.
INTENT_SUGGESTIONS: dict[str, list[str]] = {

    # ── Employee ──────────────────────────────────────────────────────────────
    'show_my_tasks':            ['Show my feedback', 'Show my nominations', 'Show cycle deadlines'],
    'show_my_feedback':         ['Show my tasks', 'Show my report', 'Show my cycles'],
    'show_my_report':           ['Show my tasks', 'Show my cycles', 'Show cycle deadlines'],
    'show_my_nominations':      ['Nominate peers', 'Show my cycles', 'Show my tasks'],
    'show_my_cycles':           ['Show my tasks', 'Show cycle deadlines', 'Show announcements'],
    'show_deadlines':           ['Show my tasks', 'Show cycle status', 'Show announcements'],
    'show_announcements':       ['Show my tasks', 'Show my cycles', 'Show cycle deadlines'],
    'nominate_peers':           ['Show my nominations', 'Show cycle deadlines', 'Show my tasks'],
    'retract_nomination':       ['Show my nominations', 'Nominate peers', 'Show my cycles'],

    # ── Manager ───────────────────────────────────────────────────────────────
    'show_team_summary':        ['Show team nominations', 'Show pending reviews', 'Show cycle status'],
    'show_team_nominations':    ['Show team summary', 'Show pending reviews', 'Show cycle status'],
    'show_pending_reviews':     ['Show team summary', 'Show team nominations', 'Show cycle status'],
    'approve_nomination':       ['Show team nominations', 'Show pending reviews', 'Show cycle status'],
    'reject_nomination':        ['Show team nominations', 'Show pending reviews', 'Show cycle status'],
    'bulk_approve_nominations': ['Show team nominations', 'Show cycle status', 'Show participation stats'],

    # ── HR Admin / Super Admin ────────────────────────────────────────────────
    'show_cycle_status':        ['Show participation stats', 'Show employees', 'Show cycle deadlines'],
    'show_participation_stats': ['Who are the top performers?', 'Show cycle status', 'Which department scores highest?'],
    'show_templates':           ['Create a template', 'Create a cycle', 'Show cycle status'],
    'show_employees':           ['Show cycle status', 'Show participation stats', 'Give me an org overview'],
    'show_audit_logs':          ['Show cycle status', 'Show employees', 'Show participation stats'],
    'show_cycle_results':       ['Show participation stats', 'Show employees', 'Show cycle status'],
    'export_nominations':       ['Show cycle status', 'Show participation stats', 'Show team nominations'],

    # ── Cycle lifecycle ───────────────────────────────────────────────────────
    'create_cycle':             ['Show cycle status', 'Show participation stats', 'Show templates'],
    'activate_cycle':           ['Show cycle status', 'Show participation stats', 'Show team nominations'],
    'finalize_cycle':           ['Activate cycle', 'Show cycle status', 'Show participation stats'],
    'close_cycle':              ['Release results', 'Show cycle status', 'Show participation stats'],
    'release_results':          ['Show cycle status', 'Show participation stats', 'Show employees'],
    'cancel_cycle':             ['Show cycle status', 'Show templates', 'Create a cycle'],
    'remind_team':              ['Show cycle status', 'Show participation stats', 'Show team nominations'],

    # ── Templates ─────────────────────────────────────────────────────────────
    'create_template':          ['Show templates', 'Create a cycle', 'Show cycle status'],
    'create_template_from_text': ['Show templates', 'Create a cycle', 'Show cycle status'],

    # ── Cross-role ────────────────────────────────────────────────────────────
    'catch_me_up':              ['Show my tasks', 'Show cycle status', 'Show announcements'],
}


def get_intent_suggestions(intent: str) -> list[str]:
    """Return contextual next-step suggestion labels for a completed command."""
    return INTENT_SUGGESTIONS.get(intent, [])

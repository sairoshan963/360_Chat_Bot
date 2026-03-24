from .command_handlers import (
    SummarizeMyStatusCommand,
    ShowMyFeedbackCommand,
    ShowMyReportCommand,
    ShowPendingReviewsCommand,
    ShowCycleStatusCommand,
    ShowTeamSummaryCommand,
    ShowParticipationCommand,
    ShowMyTasksCommand,
    ShowCycleDeadlinesCommand,
    ShowMyNominationsCommand,
    ShowMyCyclesCommand,
    ShowTemplatesCommand,
    ShowTeamNominationsCommand,
    ShowEmployeesCommand,
    ShowAnnouncementsCommand,
    ShowAuditLogsCommand,
    ShowPendingApprovalsCommand,
    ShowCycleResultsCommand,
    RemindTeamCommand,
    ExportNominationsCommand,
    ShowMyProfileCommand,
    ShowMyManagerCommand,
    ShowMyTeamCommand,
    WhenIsMyReviewDueCommand,
    WhoHasNotSubmittedCommand,
    HelpCommand,
    CreateCycleCommand,
    CreateTemplateCommand,
    NominatePeersCommand,
    ReleaseResultsCommand,
    CancelCycleCommand,
    ActivateCycleCommand,
    CloseCycleCommand,
    FinalizeCycleCommand,
    ApproveNominationCommand,
    RejectNominationCommand,
    ApproveAllNominationsCommand,
    RetractNominationCommand,
    CreateTemplateFromTextCommand,
    CreateTemplateFromPDFCommand,
)

# Maps intent name → command handler class
COMMAND_REGISTRY = {
    # ── Query commands ───────────────────────────────────
    'show_my_feedback':       ShowMyFeedbackCommand,
    'show_my_report':         ShowMyReportCommand,
    'show_pending_reviews':   ShowPendingReviewsCommand,
    'show_cycle_status':      ShowCycleStatusCommand,
    'show_team_summary':      ShowTeamSummaryCommand,
    'show_participation':     ShowParticipationCommand,
    'show_my_tasks':          ShowMyTasksCommand,
    'show_cycle_deadlines':   ShowCycleDeadlinesCommand,
    'show_my_nominations':    ShowMyNominationsCommand,
    'show_my_cycles':         ShowMyCyclesCommand,
    'show_templates':         ShowTemplatesCommand,
    'show_team_nominations':  ShowTeamNominationsCommand,
    'show_employees':         ShowEmployeesCommand,
    'show_announcements':     ShowAnnouncementsCommand,
    'show_audit_logs':        ShowAuditLogsCommand,
    'show_my_profile':        ShowMyProfileCommand,
    'show_my_manager':        ShowMyManagerCommand,
    'show_my_team':           ShowMyTeamCommand,
    'when_is_my_review_due':  WhenIsMyReviewDueCommand,
    'who_has_not_submitted':  WhoHasNotSubmittedCommand,
    'help':                   HelpCommand,
    'summarize_my_status':    SummarizeMyStatusCommand,
    'show_pending_approvals': ShowPendingApprovalsCommand,
    'show_cycle_results':     ShowCycleResultsCommand,
    'remind_team':            RemindTeamCommand,
    'export_nominations':     ExportNominationsCommand,
    # ── Action commands ──────────────────────────────────
    'create_cycle':                CreateCycleCommand,
    'create_template':             CreateTemplateCommand,
    'create_template_from_text':   CreateTemplateFromTextCommand,
    'create_template_from_pdf':    CreateTemplateFromPDFCommand,
    'nominate_peers':              NominatePeersCommand,
    'retract_nomination':          RetractNominationCommand,
    'release_results':             ReleaseResultsCommand,
    'cancel_cycle':                CancelCycleCommand,
    'activate_cycle':              ActivateCycleCommand,
    'close_cycle':                 CloseCycleCommand,
    'finalize_cycle':              FinalizeCycleCommand,
    'approve_nomination':          ApproveNominationCommand,
    'reject_nomination':           RejectNominationCommand,
    'approve_all_nominations':     ApproveAllNominationsCommand,
}


def get_command(intent: str):
    """Returns an instance of the command handler for the given intent, or None."""
    handler_class = COMMAND_REGISTRY.get(intent)
    if handler_class:
        return handler_class()
    return None


def is_known_intent(intent: str) -> bool:
    return intent in COMMAND_REGISTRY

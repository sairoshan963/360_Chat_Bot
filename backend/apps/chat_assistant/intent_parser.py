import re
import logging
from difflib import SequenceMatcher
from . import llm_service

logger = logging.getLogger(__name__)

# Rule-based patterns: (regex pattern, intent)
# More specific patterns must come BEFORE broader ones.
RULE_PATTERNS = [
    # ── create_template_from_pdf ─────────────────────────────────────────────
    # MUST come FIRST — PDF upload prefix is injected by the frontend and must
    # never be intercepted by any other pattern.
    (r'^__PDF__:',                                              'create_template_from_pdf'),

    # ── help ──────────────────────────────────────────────────────────────────
    # MUST come first — "help" is a single common word that would otherwise
    # match broad patterns further down (e.g. "what can you do" → show_announcements).
    (r'^\s*help\s*$',                                           'help'),
    (r'\bwhat\b.*\bcan\b.*\byou\b.*\bdo\b',                    'help'),
    (r'\b(list|show)\b.*\bcommand[s]?\b',                      'help'),
    (r'\bwhat\b.*\bcommand[s]?\b',                             'help'),
    (r'\bhow\b.*\bdoes\b.*\bthis\b.*\bwork\b',                 'help'),

    # ── show_user_profile (must be before show_my_profile) ────────────────────
    # Matches "profile of X@email", "details of X@email", "show X@email profile"
    (r'\bprofile\b.*\bof\b.*@',                                'show_user_profile'),
    (r'\bdetails\b.*\bof\b.*@',                                'show_user_profile'),
    (r'\bshow\b.*\bprofile\b.*@',                              'show_user_profile'),
    (r'\bshow\b.*\bdetails\b.*@',                              'show_user_profile'),
    (r'@\S+\s+profile',                                        'show_user_profile'),

    # ── show_my_profile ───────────────────────────────────────────────────────
    # MUST come before show_my_manager and show_my_team to avoid partial matches.
    (r'\bshow\b.*\bmy\b.*\bprofile\b',                         'show_my_profile'),
    (r'\bmy\b.*\bprofile\b',                                   'show_my_profile'),
    (r'\bmy\b.*\bdetails\b',                                   'show_my_profile'),
    (r'\bwho\b.*\bam\b.*\bi\b',                                'show_my_profile'),
    (r'\bmy\b.*\binfo\b',                                      'show_my_profile'),

    # ── show_my_manager ───────────────────────────────────────────────────────
    # MUST come before show_my_team ("my manager" could loosely match "my team").
    (r'\bwho\b.*\bis\b.*\bmy\b.*\bmanager\b',                  'show_my_manager'),
    (r'\bshow\b.*\bmy\b.*\bmanager\b',                         'show_my_manager'),
    (r'\bmy\b.*\bmanager\b',                                   'show_my_manager'),
    (r'\bmanager\b.*\bdetails\b',                              'show_my_manager'),
    # Natural language: "who do I report to", "who is my boss"
    (r'\bwho\b.*\b(do i|i)\b.*\breport\b.*\bto\b',            'show_my_manager'),
    (r'\bwho\b.*\b(is|are)\b.*\bmy\b.*\b(boss|lead|head|supervisor|superior)\b', 'show_my_manager'),
    (r'\bmy\b.*\b(boss|supervisor|superior|reporting\s+manager)\b', 'show_my_manager'),
    (r'\btell\b.*\bme\b.*\bwho\b.*\b(i report|my manager|my boss)\b', 'show_my_manager'),
    (r'\bwho\b.*\b(is above me|do i answer to)\b',             'show_my_manager'),
    (r'\bwho.s\b.*\babove\b.*\bme\b',                          'show_my_manager'),
    (r'\babove\b.*\bme\b.*\b(in\s+the\s+org|in\s+org|in\s+hierarchy)\b', 'show_my_manager'),
    (r'\breporting\b.*\bline\b',                               'show_my_manager'),

    # ── show_team_summary (performance queries — must come BEFORE show_my_team) ─
    # Queries about HOW the team performed go to show_team_summary, not show_my_team.
    (r'\bhow\b.*\b(is|are)\b.*\bmy\b.*\bteam\b.*\b(perform|doing|going|score)\b', 'show_team_summary'),
    (r'\bhow\b.*\b(is|are)\b.*\bmy\b.*\bteam\b',               'show_team_summary'),
    (r'\bmy\b.*\bteam\b.*\b(perform|score[s]?|rating[s]?|progress|result|number[s]?)\b', 'show_team_summary'),
    (r'\bmy\b.*\bteam.s\b.*\b(performance|score[s]?|result[s]?|number[s]?)\b', 'show_team_summary'),
    (r'\bdirect\b.*\breport[s]?\b.*\b(score|perform|highest|lowest|rating|result)\b', 'show_team_summary'),
    (r'\bwhich\b.*\b(direct report[s]?|team member[s]?)\b.*\b(score|perform|highest|best|lowest)\b', 'show_team_summary'),
    (r'\bhow\b.*\b(are|is)\b.*\bmy\b.*\b(report[s]?|direct report[s]?)\b.*\b(do|doing|perform)\b', 'show_team_summary'),
    (r'\bgive\b.*\bme\b.*\bmy\b.*\bteam.s\b.*\b(performance|score[s]?|number[s]?)\b', 'show_team_summary'),

    # ── show_my_team ──────────────────────────────────────────────────────────
    (r'\bshow\b.*\bmy\b.*\bteam\b',                            'show_my_team'),
    (r'\bwho\b.*\breport[s]?\b.*\bto\b.*\bme\b',              'show_my_team'),
    (r'\bmy\b.*\bdirect\b.*\breport[s]?\b',                   'show_my_team'),
    (r'\bmy\b.*\bteam\b',                                      'show_my_team'),

    # ── when_is_my_review_due ─────────────────────────────────────────────────
    # MUST come before show_cycle_deadlines (which also matches "deadline"/"due date").
    (r'\bwhen\b.*\bis\b.*\bmy\b.*\breview\b',                  'when_is_my_review_due'),
    (r'\bmy\b.*\bnext\b.*\breview\b',                          'when_is_my_review_due'),
    (r'\bmy\b.*\breview\b.*\bdue\b',                           'when_is_my_review_due'),
    (r'\bwhen\b.*\bmy\b.*\bnext\b.*\breview\b',               'when_is_my_review_due'),

    # ── who_has_not_submitted ─────────────────────────────────────────────────
    (r'\bwho\b.*\bhas\b.*\bnot\b.*\bsubmit',                  'who_has_not_submitted'),
    (r'\bwho\b.*\bhasn.t\b.*\bsubmit',                        'who_has_not_submitted'),
    (r'\bpending\b.*\bsubmission[s]?\b',                       'who_has_not_submitted'),
    (r'\bnot\b.*\bsubmit',                                     'who_has_not_submitted'),

    # ── show_my_report ────────────────────────────────────────────────────────
    # MUST come before show_my_feedback to prevent "my report" matching
    # the broader feedback pattern.
    (r'\bmy\b.*\b(performance\b.*\breport|report\b.*\bperformance)\b', 'show_my_report'),
    (r'\b(show|view|get)\b.*\bmy\b.*\breport\b',                'show_my_report'),
    (r'\bmy\b.*\breport\b',                                     'show_my_report'),
    (r'\bmy\b.*\bscore[s]?\b',                                  'show_my_report'),
    (r'\bhow\b.*\bi\b.*\bscored\b',                             'show_my_report'),
    (r'\bmy\b.*\bresult[s]?\b',                                 'show_my_report'),
    # Natural language variants
    (r'\bhow\b.*\b(did\b.*\bi|i\b.*\bdo)\b.*\b(in\b.*\b(the|this|last)|this\s+cycle|overall)\b', 'show_my_report'),
    (r'\bhow\b.*\bi\b.*\b(perform(ed)?|do(ing)?)\b',            'show_my_report'),
    (r'\bwhat\b.*\b(were|are|was)\b.*\bmy\b.*\b(rating[s]?|score[s]?|grade[s]?)\b', 'show_my_report'),
    (r'\bmy\b.*\b(rating[s]?|grade[s]?|assessment)\b',          'show_my_report'),
    (r'\bhow\b.*\b(am|was)\b.*\bi\b.*\b(rated|assessed|evaluated)\b', 'show_my_report'),
    (r'\bmy\b.*\bperformance\b.*\b(score|result|data|number)\b', 'show_my_report'),
    (r'\bwhat\b.*\b(grade|mark|score)\b.*\b(did i|i)\b.*\bget\b', 'show_my_report'),
    (r'\bcan\b.*\bi\b.*\bsee\b.*\bmy\b.*\b(performance|score|result|rating)\b', 'show_my_report'),

    # ── show_my_feedback — INDIRECT patterns (must come BEFORE show_my_manager) ──
    # These catch phrasing like "what did my manager say" before the broad
    # \bmy\b.*\bmanager\b pattern (which would route to show_my_manager).
    (r'\b(what|how)\b.*\b(people|peers?|reviewer[s]?|colleague[s]?|manager)\b.*\b(say|said|wrote|written|think|thought|rate|rated|score|scored)\b', 'show_my_feedback'),
    (r'\bhow\b.*\b(did|have|has)\b.*\b(reviewer[s]?|peer[s]?|colleague[s]?|people)\b.*\b(rate|rated|score|scored)\b.*\bme\b', 'show_my_feedback'),
    (r'\bhow\b.*\bthey\b.*\brat(e|ed)\b.*\bme\b',             'show_my_feedback'),
    (r'\bwhat\b.*\b(was|has been|have been)\b.*\b(written|said)\b.*\babout\b', 'show_my_feedback'),
    (r'\bwhat\b.*\bhas\b.*\bbeen\b.*\bsaid\b.*\babout\b',      'show_my_feedback'),
    (r'\bany\b.*\b(comment[s]?|rating[s]?)\b.*\b(about me|i should|to know)\b', 'show_my_feedback'),
    (r'\b(comment[s]?|rating[s]?)\b.*\bi\b.*\bshould\b.*\bknow\b', 'show_my_feedback'),
    (r'\bhow\b.*\bi\b.*\bdo\b.*\baccording\b',                 'show_my_feedback'),
    (r'\bappraisal\b.*\b(written|result|comment|rating|review|see|view|pull)\b', 'show_my_feedback'),
    (r'\b(can i see|can you pull|pull up)\b.*\bwhat\b.*\b(they|people|peers?)\b.*\b(said|wrote)\b', 'show_my_feedback'),
    (r'\bpeer[s]?\b.*\b(submitted|completed)\b.*\breview[s]?\b', 'show_my_feedback'),

    # ── show_my_feedback — direct patterns ────────────────────────────────────
    (r'\b(show|view|get|list)\b.*\bmy\b.*\bfeedback\b',        'show_my_feedback'),
    (r'\bmy\b.*\bfeedback\b',                                   'show_my_feedback'),
    (r'\bfeedback\b.*\b(i have|i.ve|have i)\b.*\b(received|got|gotten)\b', 'show_my_feedback'),
    (r'\bwhat\b.*\bfeedback\b.*\b(have i|did i|have been)\b',  'show_my_feedback'),
    # More natural language variants
    (r'\bwhat\b.*\b(people|everyone|others?|team)\b.*\b(saying|think|said|say)\b.*\bme\b', 'show_my_feedback'),
    (r'\b(pull up|show me|read)\b.*\breview\b.*\bcomment[s]?\b', 'show_my_feedback'),
    (r'\breview\b.*\bcomment[s]?\b.*\b(for me|about me|i received)\b', 'show_my_feedback'),
    (r'\bcomment[s]?\b.*\b(from\b.*\bmy|my\b.*\breviewer[s]?)\b', 'show_my_feedback'),
    (r'\bfeedback\b.*\b(received|given to me|about me)\b',      'show_my_feedback'),
    (r'\bread\b.*\bwhat\b.*\b(they|people|reviewers?)\b.*\b(wrote|said)\b', 'show_my_feedback'),
    (r'\blet\b.*\bme\b.*\bread\b.*\b(what|the\s+review|the\s+comment)\b', 'show_my_feedback'),
    (r'\breview\b.*\b(is done|is complete|was done|was submitted)\b.*\b(let me|show|read|see)\b', 'show_my_feedback'),
    (r'\bwhat.s\b.*\bbeen\b.*\b(said|written)\b.*\babout\b.*\b(my\s+work|me|my\s+performance)\b', 'show_my_feedback'),
    (r'\bwhat\b.*\b(was|has been|have been)\b.*\b(said|written|noted)\b.*\babout\b.*\b(my\s+work|me)\b', 'show_my_feedback'),

    # ── show_my_tasks ─────────────────────────────────────────────────────────
    (r'\b(show|view|get|list)\b.*\bmy\b.*\btask[s]?\b',        'show_my_tasks'),
    (r'\bmy\b.*\btask[s]?\b',                                   'show_my_tasks'),
    # Natural language: "who do I still need to review", "pending for me"
    (r'\bwho\b.*\b(do i|i still|else|i need)\b.*\b(review|assess|evaluate)\b', 'show_my_tasks'),
    (r'\bwhat\b.*\b(is|still)\b.*\bpending\b.*\b(for me|this cycle)\b', 'show_my_tasks'),
    (r'\bstill\b.*\b(need to|have to)\b.*\breview\b',          'show_my_tasks'),
    (r'\b(review[s]?\b.*\bpending|pending\b.*\breview[s]?)\b.*\b(complete|finish|do)\b', 'show_my_tasks'),
    (r'\blist\b.*\bwhat\b.*\b(i still|i need|i have)\b.*\b(do|complete|finish)\b', 'show_my_tasks'),
    (r'\bwhat\b.*\bdo\b.*\bi\b.*\bneed\b.*\b(to do|to complete|to finish)\b', 'show_my_tasks'),
    (r'\bwhat\b.*\bstill\b.*\b(left|pending|remaining)\b.*\b(for me|to do)\b', 'show_my_tasks'),

    # ── retract_nomination ────────────────────────────────────────────────────
    # MUST come BEFORE show_my_nominations — action verbs must beat the broad
    # "my nominations" noun pattern which would otherwise steal these phrases.
    (r'\bretract\b.*\bnominat',                                 'retract_nomination'),
    (r'\bremove\b.*\bnominat',                                  'retract_nomination'),
    (r'\bwithdraw\b.*\bnominat',                                'retract_nomination'),
    (r'\bremove\b.*\bpeer\b.*\bfrom\b.*\bnominat',             'retract_nomination'),
    (r'\btake\s+back\b.*\bnominat',                            'retract_nomination'),
    (r'\bundo\b.*\bnominat',                                    'retract_nomination'),
    (r'\bcancel\b.*\bnominat',                                  'retract_nomination'),

    # ── show_my_nominations ───────────────────────────────────────────────────
    (r'\bmy\b.*\bnomination[s]?\b',                             'show_my_nominations'),
    (r'\bwho\b.*\bi\b.*\bnominat',                              'show_my_nominations'),
    (r'\bnomination[s]?\b.*\b(status|list|history)\b',          'show_my_nominations'),
    (r'\bmy\b.*\bnominat',                                      'show_my_nominations'),
    # Natural language: "who did I add as reviewers", "which colleagues I selected"
    (r'\b(which|who)\b.*\bcolleague[s]?\b.*\b(did i|have i)\b.*\b(add|pick|select|choose|nominate)\b', 'show_my_nominations'),
    (r'\bcolleague[s]?\b.*\b(i.ve\s+added|i added|selected|i nominated)\b.*\b(reviewer|peer|review)\b', 'show_my_nominations'),
    (r'\bwho\b.*\bdid\b.*\bi\b.*\b(add|select|pick|choose)\b.*\b(as\s+reviewer|for\s+peer|as\s+peer)\b', 'show_my_nominations'),
    (r'\b(reviewer[s]?|peer[s]?)\b.*\b(i.ve\s+added|i added|i selected|i chose|i nominated)\b', 'show_my_nominations'),

    # ── show_my_cycles ────────────────────────────────────────────────────────
    (r'\bmy\b.*\bcycle[s]?\b',                                  'show_my_cycles'),
    (r'\bcycle[s]?\b.*\bi\b.*\b(join|participat|enroll)',       'show_my_cycles'),
    (r'\bwhich\b.*\bcycle[s]?\b.*\bi\b',                        'show_my_cycles'),
    (r'\b(show|view|get|list)\b.*\bcycle[s]?\b.*\b(i am|am in)\b', 'show_my_cycles'),
    (r'\bcycle[s]?\b.*\b(i am|am in)\b',                        'show_my_cycles'),
    # "show cycles" / "list cycles" without "all" or "status" → personal view
    # (HR users who want system-wide view should say "show cycle status" or "all cycles")
    (r'^(show|list|view|get)\s+cycles?\s*$',                    'show_my_cycles'),
    # Natural language: "am I enrolled", "part of any cycle", "review cycles I'm in"
    (r'\b(am i|i am)\b.*\b(enrolled|part of|included|participating|assigned)\b.*\bcycle\b', 'show_my_cycles'),
    (r'\b(what|which)\b.*\bcycle[s]?\b.*\b(am i|i am|i.m)\b.*\b(in|part|enrolled)\b', 'show_my_cycles'),
    (r'\bcycle[s]?\b.*\b(i.m|i am|am i)\b.*\b(in|part|part of|enrolled)\b', 'show_my_cycles'),
    (r'\b(review\s+process(es)?|cycle[s]?)\b.*\b(am i|i am)\b.*\bpart\b', 'show_my_cycles'),
    (r'\bwhat\b.*\b(review\s+process(es)?|process(es)?)\b.*\b(am i|i am)\b.*\bpart\b', 'show_my_cycles'),

    # ── show_pending_reviews ──────────────────────────────────────────────────
    (r'\b(show|view|get|list)\b.*\bpending\b.*\breview[s]?\b',  'show_pending_reviews'),
    (r'\bpending\b.*\breview[s]?\b',                            'show_pending_reviews'),
    # Natural language: "do I have reviews to complete", "who do I need to review"
    (r'\b(do i have|have i got)\b.*\b(review[s]?\b.*\bto\b|pending\b.*\breview)\b', 'show_pending_reviews'),
    (r'\b(review[s]?|assessment[s]?)\b.*\b(i need to|i have to|i must)\b.*\b(complete|do|finish|submit)\b', 'show_pending_reviews'),
    (r'\bwho\b.*\bdo i\b.*\b(still\s+)?(need to|have to)\b.*\breview\b', 'show_pending_reviews'),
    (r'\breviews?\b.*\b(left|remaining|outstanding|incomplete)\b.*\bfor me\b', 'show_pending_reviews'),

    # ── create_template_from_text ─────────────────────────────────────────────
    # MUST come BEFORE create_template — more specific (requires text/paste/questions keyword)
    (r'\bcreate\b.*\btemplate\b.*\bfrom\b.*\b(text|document|content|questions?|paste)\b',
                                                                'create_template_from_text'),
    (r'\bparse\b.*\b(text|questions?|document|content)\b.*\btemplate\b',
                                                                'create_template_from_text'),
    (r'\btemplate\b.*\bfrom\b.*\b(text|document|questions?|content|paste)\b',
                                                                'create_template_from_text'),
    (r'\bimport\b.*\btemplate\b',                              'create_template_from_text'),
    (r'\bpaste\b.*\bquestions?\b',                             'create_template_from_text'),

    # ── approve_all_nominations ───────────────────────────────────────────────
    # MUST come BEFORE approve_nomination — "approve all nominations" contains
    # both "approve" and "nominat" which would otherwise match approve_nomination.
    (r'\bapprove\b.*\ball\b.*\bnominat',                        'approve_all_nominations'),
    (r'\bbulk\b.*\bapprove\b.*\bnominat',                       'approve_all_nominations'),
    (r'\bapprove\b.*\bnominat.*\ball\b',                        'approve_all_nominations'),
    (r'\bapprove\b.*\ball\b.*\bpending\b',                      'approve_all_nominations'),
    (r'\bapprove\b.*\beverything\b.*\bnominat',                 'approve_all_nominations'),

    # ── approve_nomination ────────────────────────────────────────────────────
    # MUST come BEFORE show_team_nominations AND nominate_peers.
    # Reason: show_team_nominations has \bnomination.*\bteam\b which catches
    # phrases like "deny nomination reason: not in same team", and nominate_peers
    # has \b(nominate|nominating)\b which is a substring of "nomination".
    # Specific action verbs (approve/reject/accept/deny/decline) must always
    # be matched before broad noun-based query patterns.
    (r'\bapprove\b.*\bnominat',                                 'approve_nomination'),
    (r'\baccept\b.*\bnominat',                                  'approve_nomination'),
    (r'\bnominat.*\bapprove\b',                                 'approve_nomination'),

    # ── reject_nomination ─────────────────────────────────────────────────────
    # MUST come BEFORE show_team_nominations AND nominate_peers — same reason.
    (r'\breject\b.*\bnominat',                                  'reject_nomination'),
    (r'\bdeny\b.*\bnominat',                                    'reject_nomination'),
    (r'\bdecline\b.*\bnominat',                                 'reject_nomination'),
    (r'\bnominat.*\breject\b',                                  'reject_nomination'),

    # ── show_pending_approvals ────────────────────────────────────────────────
    # MUST come BEFORE show_team_nominations — "pending approvals" is more specific
    (r'\bpending\b.*\bapprov',                                  'show_pending_approvals'),
    (r'\bapprov\w*\b.*\bwaiting\b',                             'show_pending_approvals'),
    (r'\bany\b.*\bapprov\w*\b.*\bwaiting\b',                   'show_pending_approvals'),
    (r'\bnomination[s]?\b.*\bto\b.*\bapprov',                  'show_pending_approvals'),
    (r'\bnomination[s]?\b.*\bpending\b.*\bapprov',              'show_pending_approvals'),
    # Natural language: "nominations need my approval", "approvals in my queue"
    (r'\bnomination[s]?\b.*\b(need|require|await)\b.*\bmy\b.*\bapprov', 'show_pending_approvals'),
    (r'\bwhich\b.*\bnomination[s]?\b.*\b(need|require|want)\b.*\bapprov', 'show_pending_approvals'),
    (r'\bapprov\w*\b.*\b(in my queue|queue|waiting for me|need my)\b', 'show_pending_approvals'),
    (r'\bmy\b.*\bapprov\w*\b.*\b(queue|list|inbox)\b',         'show_pending_approvals'),

    # ── export_nominations ────────────────────────────────────────────────────
    # MUST come BEFORE show_team_nominations to avoid "nominations" pattern clash
    (r'\bexport\b.*\bnomination[s]?\b',                         'export_nominations'),
    (r'\bdownload\b.*\bnomination[s]?\b',                       'export_nominations'),
    (r'\bnomination[s]?\b.*\b(report|csv|export)\b',            'export_nominations'),

    # ── show_team_nominations ─────────────────────────────────────────────────
    # Comes AFTER approve/reject_nomination — the "nomination.*team" pattern
    # below would otherwise steal rejection reasons containing the word "team".
    (r'\bteam\b.*\bnomination[s]?\b',                           'show_team_nominations'),
    (r'\bnomination[s]?\b.*\b(pending|team)\b',                 'show_team_nominations'),
    (r'\bpending\b.*\bnomination[s]?\b',                        'show_team_nominations'),

    # ── show_cycle_deadlines ──────────────────────────────────────────────────
    # NOTE: must come BEFORE show_cycle_status (which has broad cycle patterns)
    (r'\b(show|view|get)\b.*\b(cycle\b.*\bdeadline|deadline[s]?\b.*\bcycle)\b', 'show_cycle_deadlines'),
    (r'\b(show|view|get|list)\b.*\bdeadline[s]?\b',             'show_cycle_deadlines'),
    (r'\bdeadline[s]?\b',                                       'show_cycle_deadlines'),
    (r'\bdue\b.*\bdate[s]?\b',                                  'show_cycle_deadlines'),

    # ── show_cycle_results ────────────────────────────────────────────────────
    # MUST come BEFORE show_cycle_status — "cycle results" is more specific than
    # "cycle status" and would otherwise fall through to the broader status pattern.
    (r'\bcycle\b.*\bresult[s]?\b',                              'show_cycle_results'),
    (r'\b(show|view)\b.*\bresult[s]?\b.*\bcycle\b',             'show_cycle_results'),
    (r'\bresult[s]?\b.*\bfor\b.*\bcycle\b',                     'show_cycle_results'),

    # ── remind_team ───────────────────────────────────────────────────────────
    (r'\bremind\b.*\b(my\s+|the\s+)?team\b',                   'remind_team'),
    (r'\bsend\b.*\breminder[s]?\b',                             'remind_team'),
    (r'\bnudge\b.*\bteam\b',                                    'remind_team'),

    # ── show_cycle_status ─────────────────────────────────────────────────────
    (r'\b(show|view|get)\b.*\bcycle\b.*\bstatus\b',             'show_cycle_status'),
    (r'\bcycle\b.*\bstatus\b',                                  'show_cycle_status'),
    (r'\bstatus\b.*\bcycle[s]?\b',                              'show_cycle_status'),
    (r'\ball\b.*\bcycle[s]?\b',                                 'show_cycle_status'),
    (r'\b(list|show)\b.*\bcycle[s]?\b',                         'show_cycle_status'),
    # Natural language: "what cycles are running", "active performance cycles"
    (r'\bwhat\b.*\b(review\s+)?cycle[s]?\b.*\b(running|active|open|going on)\b', 'show_cycle_status'),
    (r'\b(any|are there)\b.*\bactive\b.*\b(cycle[s]?|review[s]?|performance)\b', 'show_cycle_status'),
    (r'\bactive\b.*\b(performance\b.*\bcycle|cycle[s]?\b.*\bnow)\b', 'show_cycle_status'),
    (r'\bwhat\b.*\b(is|are)\b.*\b(running|happening)\b.*\b(review|cycle)\b', 'show_cycle_status'),
    (r'\bwhat\b.*\bcycle[s]?\b.*\b(are there|exist|do we have|have we got)\b', 'show_cycle_status'),
    (r'\b(overview|summary)\b.*\b(of\s+all|all)\b.*\b(performance|review)\b.*\bcycle[s]?\b', 'show_cycle_status'),

    # ── show_team_summary ─────────────────────────────────────────────────────
    (r'\b(show|view|get)\b.*\bteam\b.*\b(summary|overview)\b',  'show_team_summary'),
    (r'\bteam\b.*\b(summary|overview|progress|report)\b',       'show_team_summary'),
    # Natural language: "how is my team performing", "direct reports scored"
    (r'\bhow\b.*\bmy\b.*\bteam\b.*\b(perform|doing|score)\b',  'show_team_summary'),
    (r'\bmy\b.*\bteam\b.*\b(perform|score[s]?|rating[s]?|highest|lowest)\b', 'show_team_summary'),
    (r'\bdirect\b.*\breport[s]?\b.*\b(score|perform|highest|lowest|rating)\b', 'show_team_summary'),
    (r'\bwhich\b.*\b(direct report[s]?|team member[s]?)\b.*\b(score|perform|highest|best)\b', 'show_team_summary'),
    (r'\bhow\b.*\b(is|are)\b.*\bmy\b.*\bteam\b',               'show_team_summary'),

    # ── show_participation ────────────────────────────────────────────────────
    (r'\b(show|view|get)\b.*\bparticipation\b',                 'show_participation'),
    (r'\bparticipation\b.*\b(stats|statistics|rate|status)\b',  'show_participation'),
    (r'\bcompletion\b.*\brate[s]?\b',                           'show_participation'),

    # ── show_templates ────────────────────────────────────────────────────────
    (r'\b(show|list|view|get)\b.*\btemplate[s]?\b',             'show_templates'),
    (r'\bavailable\b.*\btemplate[s]?\b',                        'show_templates'),
    (r'\btemplate[s]?\b.*\b(list|available|all)\b',             'show_templates'),

    # ── show_employees ────────────────────────────────────────────────────────
    (r'\b(show|list|view|get)\b.*\bemployee[s]?\b',             'show_employees'),
    (r'\ball\b.*\bemployee[s]?\b',                              'show_employees'),
    (r'\b(list|show)\b.*\buser[s]?\b',                          'show_employees'),
    (r'\buser[s]?\b.*\blist\b',                                 'show_employees'),

    # ── summarize_my_status (catch me up / what's my status) ─────────────────
    (r'\bcatch\b.*\bme\b.*\bup\b',                              'summarize_my_status'),
    (r'\bwhat.s\b.*\bmy\b.*\bstatus\b',                        'summarize_my_status'),
    (r'\bmy\b.*\bstatus\b.*\bupdate\b',                        'summarize_my_status'),
    (r'\bsummariz\b.*\bmy\b.*\bstatus\b',                      'summarize_my_status'),
    (r'\bgive\b.*\bme\b.*\bsummary\b',                         'summarize_my_status'),
    (r'\bbrief\b.*\bme\b',                                      'summarize_my_status'),
    # Natural language: "overview of where things stand", "what do I need to know"
    (r'\b(overview|picture|snapshot)\b.*\b(where|things|stand|for me)\b', 'summarize_my_status'),
    (r'\bwhere\b.*\b(things|do i|i)\b.*\bstand\b',             'summarize_my_status'),
    (r'\bquick\b.*\b(overview|update|summary)\b.*\b(for me|of where|things)\b', 'summarize_my_status'),
    (r'\bwhat\b.*\b(do i need to know|should i know|is going on with me)\b', 'summarize_my_status'),
    (r'\bgive\b.*\bme\b.*\b(the\s+)?(full\s+)?(picture|overview|rundown)\b', 'summarize_my_status'),
    (r'\bwhat.s\b.*\b(going on|happening)\b.*\b(for me|with me|my end)\b', 'summarize_my_status'),
    (r'\bwhat\b.*\bdo\b.*\bi\b.*\bneed\b.*\bto\b.*\bdo\b.*\b(today|now|this week)?\b', 'summarize_my_status'),
    (r'\bbring\b.*\bme\b.*\bup\b.*\bto\b.*\bspeed\b',          'summarize_my_status'),

    # ── show_announcements ────────────────────────────────────────────────────
    (r'\b(show|view|get|list)\b.*\bannouncement[s]?\b',         'show_announcements'),
    (r'\bannouncement[s]?\b',                                   'show_announcements'),
    (r'\bwhat.*(new|happening|update[s]?)\b',                   'show_announcements'),
    # Natural language: "anything new", "company updates", "what's going on"
    (r'\banything\b.*\b(new|I should know|important)\b',        'show_announcements'),
    (r'\b(company|org|organization)\b.*\bupdate[s]?\b',         'show_announcements'),
    (r'\bany\b.*\b(news|update[s]?|notice[s]?|message[s]?)\b', 'show_announcements'),
    (r'\bwhat.s\b.*\b(going on|new around|happening)\b',        'show_announcements'),
    (r'\b(latest|recent)\b.*\b(news|update[s]?|notice[s]?)\b', 'show_announcements'),
    (r'\bnotice\b.*\b(board|from\s+(hr|management|company))\b', 'show_announcements'),

    # ── show_audit_logs ───────────────────────────────────────────────────────
    (r'\baudit\b.*\blog[s]?\b',                                 'show_audit_logs'),
    (r'\blog[s]?\b.*\baudit\b',                                 'show_audit_logs'),
    (r'\brecent\b.*\bactivit',                                  'show_audit_logs'),
    (r'\bactivit.*\blog[s]?\b',                                 'show_audit_logs'),
    (r'\bwho\b.*\bdid\b',                                       'show_audit_logs'),

    # ── create_cycle ─────────────────────────────────────────────────────────
    (r'\bcreate\b.*\bcycle\b',                                  'create_cycle'),
    (r'\bnew\b.*\bcycle\b',                                     'create_cycle'),
    (r'\badd\b.*\bcycle\b',                                     'create_cycle'),

    # ── create_template ───────────────────────────────────────────────────────
    (r'\bcreate\b.*\btemplate\b',                               'create_template'),
    (r'\bnew\b.*\btemplate\b',                                  'create_template'),
    (r'\badd\b.*\btemplate\b',                                  'create_template'),

    # ── activate_cycle ────────────────────────────────────────────────────────
    (r'\bactivate\b.*\bcycle\b',                                'activate_cycle'),
    (r'\bcycle\b.*\bactivate\b',                                'activate_cycle'),
    (r'\bstart\b.*\bcycle\b',                                   'activate_cycle'),
    (r'\blaunch\b.*\bcycle\b',                                  'activate_cycle'),
    (r'\bbegin\b.*\bcycle\b',                                   'activate_cycle'),

    # ── close_cycle ───────────────────────────────────────────────────────────
    (r'\bclose\b.*\bcycle\b',                                   'close_cycle'),
    (r'\bcycle\b.*\bclose\b',                                   'close_cycle'),
    (r'\bend\b.*\bcycle\b',                                     'close_cycle'),
    (r'\bfinish\b.*\bcycle\b',                                  'close_cycle'),
    (r'\bwrap\b.*\bcycle\b',                                    'close_cycle'),

    # ── nominate_peers ────────────────────────────────────────────────────────
    # Comes AFTER approve/reject_nomination (defined above) to avoid
    # substring collisions — "nomination" contains "nominat".
    (r'\b(nominate|nominating)\b',                              'nominate_peers'),
    (r'\bpeer[s]?\b.*\b(nominate|nominating)\b',               'nominate_peers'),
    (r'\bi\b.*\bwant\b.*\bnominat',                            'nominate_peers'),

    # ── release_results ───────────────────────────────────────────────────────
    (r'\brelease\b.*\bresult[s]?\b',                            'release_results'),
    (r'\bpublish\b.*\bresult[s]?\b',                            'release_results'),
    (r'\bresult[s]?\b.*\brelease\b',                            'release_results'),

    # ── cancel_cycle ──────────────────────────────────────────────────────────
    (r'\bcancel\b.*\bcycle\b',                                  'cancel_cycle'),
    (r'\bcycle\b.*\bcancel\b',                                  'cancel_cycle'),
    (r'\barchive\b.*\bcycle\b',                                 'cancel_cycle'),

    # ── finalize_cycle ────────────────────────────────────────────────────────
    # MUST come AFTER close/cancel_cycle — "finalize" is unambiguous but guard
    # broad cycle phrases from being stolen by close/cancel patterns above.
    (r'\bfinali[sz]e\b.*\bcycle\b',                             'finalize_cycle'),
    (r'\bcycle\b.*\bfinali[sz]e\b',                             'finalize_cycle'),
    (r'\block\b.*\bnomination[s]?\b.*\bcycle\b',                'finalize_cycle'),
    (r'\bcycle\b.*\bgenerate\b.*\btask[s]?\b',                  'finalize_cycle'),
]


_STOP = {'a', 'an', 'the', 'is', 'are', 'to', 'for', 'of', 'in', 'on', 'at', 'by', 'with'}

# Canonical phrase sets used for fuzzy matching (D1/B4).
# Each intent maps to one or more representative phrase strings.
_FUZZY_CANONICAL = {
    'show_my_tasks':          ['show my tasks', 'my tasks', 'list tasks', 'what do i need to do', 'pending for me'],
    'show_my_nominations':    ['show my nominations', 'my nominations', 'who i nominated', 'my nominated peers'],
    'show_my_cycles':         ['show my cycles', 'cycles i am in', 'my cycles', 'which cycles am i in', 'am i in any cycle'],
    'show_my_report':         ['show my report', 'my report', 'my scores', 'my results', 'how i scored', 'how i performed', 'my ratings', 'my performance results'],
    'show_my_feedback':       ['show my feedback', 'my feedback', 'what people said about me', 'my review comments'],
    'show_cycle_status':      ['show cycle status', 'all cycles', 'cycle status', 'what cycles are running', 'active cycles'],
    'show_cycle_deadlines':   ['show cycle deadlines', 'deadlines', 'due dates'],
    'show_participation':     ['show participation', 'participation stats', 'completion rate'],
    'show_templates':         ['show templates', 'list templates', 'all templates'],
    'show_employees':         ['show employees', 'list employees', 'all employees'],
    'show_announcements':     ['show announcements', 'announcements', 'latest updates', 'anything new', 'company updates', "what's new"],
    'summarize_my_status':    ['catch me up', "what's my status", 'my status update', 'give me a summary', 'brief me', 'overview of where things stand', 'quick update for me'],
    'show_audit_logs':        ['show audit logs', 'audit logs', 'recent activity'],
    'show_team_summary':      ['show team summary', 'team summary', 'team overview', 'how is my team performing', 'team performance', 'direct reports scores'],
    'show_team_nominations':  ['show team nominations', 'team nominations', 'pending nominations'],
    'show_pending_reviews':   ['show pending reviews', 'pending reviews', 'reviews i need to complete', 'who do i need to review'],
    'show_user_profile':      ['profile of user', 'show profile of', 'details of user', 'show user profile'],
    'show_my_profile':        ['show my profile', 'my profile', 'my details', 'who am i'],
    'show_my_manager':        ['show my manager', 'my manager', 'who is my manager', 'who do i report to', 'my boss', 'who is my boss'],
    'show_my_team':           ['show my team', 'my team', 'direct reports'],
    'when_is_my_review_due':  ['when is my review due', 'my review due', 'next review'],
    'who_has_not_submitted':  ['who has not submitted', 'pending submissions'],
    'create_cycle':           ['create cycle', 'new cycle', 'add cycle'],
    'create_template':        ['create template', 'new template', 'add template'],
    'activate_cycle':         ['activate cycle', 'start cycle', 'launch cycle'],
    'close_cycle':            ['close cycle', 'end cycle', 'finish cycle'],
    'cancel_cycle':           ['cancel cycle', 'archive cycle'],
    'finalize_cycle':         ['finalize cycle', 'finalise cycle', 'lock nominations cycle'],
    'nominate_peers':         ['nominate peers', 'nominate someone', 'peer nomination'],
    'release_results':        ['release results', 'publish results'],
    'approve_nomination':          ['approve nomination'],
    'reject_nomination':           ['reject nomination', 'deny nomination'],
    'approve_all_nominations':     ['approve all nominations', 'bulk approve nominations', 'approve all pending'],
    'retract_nomination':          ['retract nomination', 'remove nomination', 'withdraw nomination', 'cancel nomination'],
    'create_template_from_text':   ['create template from text', 'create template from questions', 'parse questions into template', 'import template'],
    'show_pending_approvals':      ['show pending approvals', 'pending approvals', 'nominations pending approval', 'approvals waiting'],
    'show_cycle_results':          ['show cycle results', 'cycle results', 'view results for cycle'],
    'remind_team':                 ['remind my team', 'send reminder', 'nudge team', 'remind team'],
    'export_nominations':          ['export nominations', 'download nominations', 'nominations report', 'nominations csv'],
    'help':                        ['help', 'what can you do', 'list commands'],
}

# Human-friendly canonical phrase to send when a "did you mean" chip is tapped.
_FUZZY_SEND_PHRASE = {
    'show_my_tasks':          'show my tasks',
    'show_my_nominations':    'show my nominations',
    'show_my_cycles':         'show my cycles',
    'show_my_report':         'show my report',
    'show_my_feedback':       'show my feedback',
    'show_cycle_status':      'show cycle status',
    'show_cycle_deadlines':   'show cycle deadlines',
    'show_participation':     'show participation',
    'show_templates':         'show templates',
    'show_employees':         'show employees',
    'show_announcements':     'show announcements',
    'summarize_my_status':    'catch me up on everything',
    'show_audit_logs':        'show audit logs',
    'show_team_summary':      'show team summary',
    'show_team_nominations':  'show team nominations',
    'show_pending_reviews':   'show pending reviews',
    'show_my_profile':        'show my profile',
    'show_my_manager':        'who is my manager',
    'show_my_team':           'show my team',
    'when_is_my_review_due':  'when is my review due',
    'who_has_not_submitted':  'who has not submitted',
    'create_cycle':           'create a cycle',
    'create_template':        'create a template',
    'activate_cycle':         'activate a cycle',
    'close_cycle':            'close a cycle',
    'cancel_cycle':           'cancel a cycle',
    'finalize_cycle':         'finalize a cycle',
    'nominate_peers':         'nominate peers',
    'release_results':        'release results',
    'approve_nomination':         'approve a nomination',
    'reject_nomination':          'reject a nomination',
    'approve_all_nominations':    'approve all nominations',
    'retract_nomination':         'retract a nomination',
    'create_template_from_text':  'create template from text',
    'show_pending_approvals':     'show pending approvals',
    'show_cycle_results':         'show cycle results',
    'remind_team':                'remind my team',
    'export_nominations':         'export nominations',
    'help':                       'help',
}


def _tokenize(text: str) -> list:
    words = re.findall(r"[a-z']+", text.lower())
    return [w for w in words if w not in _STOP and len(w) > 1]


def _word_sim(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def _fuzzy_score(input_words: list, phrase_words: list) -> float:
    """
    Word-level fuzzy score using edit-distance similarity.
    Each input word is matched to its closest phrase word (sim >= 0.7).
    Score = matched_pairs / max(len(input), len(phrase)).
    """
    if not input_words or not phrase_words:
        return 0.0
    used = set()
    matched = 0
    for iw in input_words:
        best_sim, best_j = 0.0, -1
        for j, pw in enumerate(phrase_words):
            if j in used:
                continue
            s = _word_sim(iw, pw)
            if s > best_sim:
                best_sim, best_j = s, j
        if best_sim >= 0.70 and best_j >= 0:
            matched += 1
            used.add(best_j)
    return matched / max(len(input_words), len(phrase_words))


def fuzzy_match_intent(message: str):
    """
    Returns (intent, score, send_phrase) for the best fuzzy match,
    or (None, 0.0, '') if no match is strong enough to suggest.
    """
    input_words = _tokenize(message)
    best_intent, best_score = None, 0.0
    for intent, phrases in _FUZZY_CANONICAL.items():
        for phrase in phrases:
            score = _fuzzy_score(input_words, _tokenize(phrase))
            if score > best_score:
                best_score = score
                best_intent = intent
    if best_intent is None or best_score == 0.0:
        return None, 0.0, ''
    send_phrase = _FUZZY_SEND_PHRASE.get(best_intent, '')
    return best_intent, best_score, send_phrase


def _extract_inline_params(intent: str, message: str) -> dict:
    """
    Extract obvious parameter values inline from the message to avoid
    an unnecessary slot-fill round-trip.
    Examples:
      "create cycle named Q1 2026 Review"  → {name: "Q1 2026 Review"}
      "create template called Eng Review"  → {name: "Eng Review"}
      "nominate bob@co.com, alice@co.com"  → {peer_emails: "bob@co.com,alice@co.com"}
    """
    params = {}

    if intent in ('create_cycle', 'create_template'):
        # Match: "named/called/name: <value>" — grab everything after the keyword to EOL
        m = re.search(r'\b(?:named?|call(?:ed)?|name\s*:)\s+(.+)', message, re.IGNORECASE)
        if m:
            name = m.group(1).strip().strip('"\'')
            if name:
                params['name'] = name

    elif intent == 'nominate_peers':
        # Extract all email addresses from the message
        emails = re.findall(r'[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}', message)
        if emails:
            params['peer_emails'] = ','.join(emails)

    elif intent == 'create_template_from_text':
        # Extract name from "called/named X:" or "called X\n"
        m_name = re.search(
            r'\b(?:named?|call(?:ed)?|name\s*:)\s+(.+?)(?:\s*[:\n]|$)',
            message, re.IGNORECASE
        )
        if m_name:
            name = m_name.group(1).strip().strip('"\'')
            if name:
                params['name'] = name
                # Content is everything after the colon/newline that follows the name
                after_name = message[m_name.end():].strip()
                if len(after_name) > 10:
                    params['content'] = after_name

    elif intent == 'create_template_from_pdf':
        # Message format: "__PDF__:<filename>||<extracted_text>"
        # Extract filename (as optional name hint) and content
        rest = re.sub(r'^__PDF__:', '', message).strip()
        if '||' in rest:
            filename, content = rest.split('||', 1)
            # Derive a name hint from the filename (strip extension)
            name_hint = re.sub(r'\.(pdf|txt)$', '', filename, flags=re.IGNORECASE).strip()
            name_hint = re.sub(r'[_\-]+', ' ', name_hint).title()
            if name_hint:
                params['name']    = name_hint
            params['content'] = content.strip()
        else:
            params['content'] = rest

    elif intent in ('show_my_cycles', 'show_cycle_status'):
        # Parameters are extracted by LLM tool calling (state_filter, cycle_name).
        # Regex fallback: only used when LLM is unavailable.
        if not params.get('state_filter'):
            _STATE_WORDS = {
                'active': 'ACTIVE', 'nomination': 'NOMINATION', 'closed': 'CLOSED',
                'draft': 'DRAFT', 'released': 'RESULTS_RELEASED', 'result': 'RESULTS_RELEASED',
                'archived': 'ARCHIVED', 'cancelled': 'ARCHIVED', 'finalized': 'FINALIZED',
            }
            msg_lower = message.lower()
            for word, state in _STATE_WORDS.items():
                if word in msg_lower:
                    params['state_filter'] = state
                    break

    elif intent == 'show_user_profile':
        # Extract email from message
        emails = re.findall(r'[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}', message)
        if emails:
            params['email'] = emails[0]

    elif intent == 'reject_nomination':
        # Extract rejection reason from phrases like:
        #   "reject nomination reason: bias"
        #   "reject nomination because outside department"
        #   "reject nomination note: performance concerns"
        #   "reject nomination reason being: conflict of interest"
        # Pattern: keyword (optional colon/dash) then capture everything after
        m = re.search(
            r'\b(?:reason\s*being|reason|note|because)\s*[:\-]?\s*(.+)',
            message, re.IGNORECASE
        )
        if m:
            note = m.group(1).strip().strip('"\'')
            if note:
                params['rejection_note'] = note

    return params


def parse_intent(user_message: str, conversation_context: str = '', conversation_history: list = None) -> dict:
    """
    Returns {"intent": str, "parameters": dict, "used_llm": bool}

    Phase 3 — Tool-Calling Primary with Conversation Memory:
    Step 1: LLM tool-calling with full conversation history (handles natural language + follow-ups).
    Step 2: If LLM unavailable → fall back to regex + fuzzy match.
    """
    # ── Pre-step: System-injected prefixes bypass LLM entirely ────────────────
    # These are generated by the frontend (e.g. after file upload) and are not
    # natural language — they must NOT be sent to the LLM classifier.
    _SYSTEM_PREFIX_PATTERNS = [
        (r'^__PDF__:', 'create_template_from_pdf'),
    ]
    for pattern, intent in _SYSTEM_PREFIX_PATTERNS:
        if re.search(pattern, user_message):
            params = _extract_inline_params(intent, user_message)
            logger.debug("System-prefix match: %s for %r", intent, user_message[:60])
            return {"intent": intent, "parameters": params, "used_llm": False}

    # ── Pre-LLM high-confidence patterns ─────────────────────────────────────
    # These patterns are so specific that the LLM classifier would add noise.
    # Run them BEFORE the LLM so they can't be overridden by ambiguous LLM routing.
    _lower_norm = user_message.lower().replace('\n', ' ').replace('\r', ' ')
    _PRE_LLM_PATTERNS = [
        # "what has been said/written about my performance" — always feedback, not manager info
        (r'\bwhat\b.*\bhas\b.*\bbeen\b.*\b(said|written)\b.*\b(about\b.*\bmy|my\b.*\bperformance)\b', 'show_my_feedback'),
        (r'\bwhat\b.*\b(was|have been|has been)\b.*\b(written|said)\b.*\babout\b.*\b(my|me)\b', 'show_my_feedback'),
        (r'\b(comments?|ratings?)\b.*\b(i should know|should know about|about me)\b', 'show_my_feedback'),
        # "what they wrote/said" — review comments, not manager lookup
        (r'\blet me read\b.*\bwhat\b.*\b(they|everyone|people)\b.*\b(wrote|said)\b', 'show_my_feedback'),
        (r'\bread\b.*\bwhat\b.*\bthey\b.*\bwrote\b',              'show_my_feedback'),
        # "am I enrolled in cycles" — personal, not system cycle status
        (r'\b(am i|i am)\b.*\b(enrolled|part of|assigned|participating)\b.*\bcycle[s]?\b', 'show_my_cycles'),
        # "how is my team performing" / "team's performance numbers" — performance summary, not roster
        (r'\bhow\b.*\b(is|are)\b.*\bmy\b.*\bteam\b',              'show_team_summary'),
        (r'\bmy\b.*\bteam.s\b.*\b(performance|score[s]?|result[s]?|number[s]?)\b', 'show_team_summary'),
        (r'\bhow\b.*\b(are|is)\b.*\bmy\b.*\b(report[s]?|direct\s+report[s]?)\b.*\b(do|doing|perform)\b', 'show_team_summary'),
        (r'\bdirect\b.*\breport[s]?\b.*\b(score|perform|highest|result)\b', 'show_team_summary'),
        # "how did I score" — my results
        (r'\bhow\b.*\b(did i|i)\b.*\b(score|do|fare)\b(?!\s*according\b)', 'show_my_report'),
    ]
    for pattern, intent in _PRE_LLM_PATTERNS:
        if re.search(pattern, _lower_norm):
            params = _extract_inline_params(intent, user_message)
            logger.debug("Pre-LLM high-confidence match: %s for %r", intent, user_message[:60])
            return {"intent": intent, "parameters": params, "used_llm": False}

    # ── Step 1: LLM tool calling — PRIMARY path, always used ─────────────────
    # LLM understands full context, extracts intent + all parameters in one shot.
    api_key = llm_service._get_api_key()
    if api_key:
        logger.debug("LLM tool-call (primary): %r", user_message)
        result = llm_service.detect_intent_tool_call(user_message, conversation_context, conversation_history)
        result["used_llm"] = True
        if result.get("intent") and result["intent"] != "unknown":
            return result
        # LLM returned unknown (rate-limited or genuinely unclear) —
        # fall back to regex + fuzzy before giving up.
        logger.debug("LLM returned unknown — trying regex/fuzzy fallback")

    else:
        logger.warning("Cohere API key missing — skipping LLM, using regex intent detection.")

    # ── Step 2: Regex + fuzzy fallback ───────────────────────────────────────
    # Used when: (a) API key is missing, or (b) LLM returned unknown/failed.
    lower = user_message.lower().replace('\n', ' ').replace('\r', ' ')
    for pattern, intent in RULE_PATTERNS:
        if re.search(pattern, lower):
            logger.debug("Regex fallback matched: %s for %r", intent, user_message[:80])
            params = _extract_inline_params(intent, user_message)
            return {"intent": intent, "parameters": params, "used_llm": False}

    fz_intent, fz_score, fz_phrase = fuzzy_match_intent(user_message)
    if fz_score >= 0.50 and fz_intent:
        params = _extract_inline_params(fz_intent, user_message)
        return {"intent": fz_intent, "parameters": params, "used_llm": False, "fuzzy_corrected": True}
    if fz_score >= 0.30 and fz_intent:
        return {"intent": "UNKNOWN", "parameters": {}, "used_llm": False, "suggestion": fz_intent, "suggestion_phrase": fz_phrase}

    return {"intent": "unknown", "parameters": {}, "used_llm": False}

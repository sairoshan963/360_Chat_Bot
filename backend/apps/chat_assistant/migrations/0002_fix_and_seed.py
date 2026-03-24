"""
Migration 0002:
  1. Remove unique constraint on PromptTemplate.name (was unique=True)
  2. Add unique_together constraint on (name, version) — correct per spec
  3. Add 'cancelled' to ChatLog.execution_status choices
  4. Seed the default intent_detection prompt template
"""
from django.db import migrations, models

DEFAULT_INTENT_PROMPT = (
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


def seed_prompt_template(apps, schema_editor):
    PromptTemplate = apps.get_model('chat_assistant', 'PromptTemplate')
    PromptTemplate.objects.get_or_create(
        name='intent_detection',
        version=1,
        defaults={
            'template_text': DEFAULT_INTENT_PROMPT,
            'is_active': True,
        }
    )


def remove_prompt_template(apps, schema_editor):
    PromptTemplate = apps.get_model('chat_assistant', 'PromptTemplate')
    PromptTemplate.objects.filter(name='intent_detection', version=1).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('chat_assistant', '0001_initial'),
    ]

    operations = [
        # 1. Remove old unique=True on name
        migrations.AlterField(
            model_name='prompttemplate',
            name='name',
            field=models.CharField(max_length=100),
        ),
        # 2. Add unique_together on (name, version)
        migrations.AlterUniqueTogether(
            name='prompttemplate',
            unique_together={('name', 'version')},
        ),
        # 3. Add 'cancelled' to ChatLog execution_status choices
        migrations.AlterField(
            model_name='chatlog',
            name='execution_status',
            field=models.CharField(
                choices=[
                    ('pending',   'Pending'),
                    ('success',   'Success'),
                    ('failed',    'Failed'),
                    ('rejected',  'Rejected'),
                    ('clarify',   'Clarification Requested'),
                    ('cancelled', 'Cancelled'),
                ],
                default='pending',
                max_length=50,
            ),
        ),
        # 4. Seed default intent_detection prompt template
        migrations.RunPython(seed_prompt_template, remove_prompt_template),
    ]

import logging
import threading
from .models import ChatLog

logger = logging.getLogger(__name__)


def log_interaction(user, session_id: str, message: str, intent: str,
                    parameters: dict, status: str, response: str, used_llm: bool,
                    response_data: dict | None = None) -> ChatLog | None:
    """Log a chat interaction to the chat_logs table (append-only). Returns the created ChatLog."""
    try:
        return ChatLog.objects.create(
            user=user,
            session_id=session_id,
            message=message,
            intent=intent,
            parameters=parameters,
            execution_status=status,
            response_message=response,
            response_data=response_data or {},
            used_llm=used_llm,
        )
    except Exception as e:
        logger.error(f"Failed to log chat interaction: {e}")
        return None


def maybe_generate_title(session_id: str, message: str) -> None:
    """
    If the session has no title yet (i.e. this is the first message), generate one in
    a background thread using the LLM and save it on the earliest ChatLog entry.
    """
    def _run():
        try:
            from . import llm_service
            # Only generate for the very first message of the session
            logs = ChatLog.objects.filter(session_id=session_id).order_by('created_at')[:1]
            if not logs:
                return
            first_log = logs[0]
            if first_log.session_title:
                return  # title already exists
            title = llm_service.generate_session_title(message)
            if title:
                first_log.session_title = title
                first_log.save(update_fields=['session_title'])
                logger.debug("Generated session title %r for session %s", title, session_id[:8])
        except Exception as exc:
            logger.warning("maybe_generate_title failed: %s", exc)

    threading.Thread(target=_run, daemon=True).start()

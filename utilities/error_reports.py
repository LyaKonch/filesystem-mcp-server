"""Persistent storage helpers for user-submitted error reports."""

import json
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from config import settings

module_logger = logging.getLogger(__name__)


def save_error_report(
    *,
    summary: str,
    error_id: str | None,
    reproduction_steps: str | None,
    system_info: str | None,
    attachments: list[str] | None,
    request_id: str,
    trace_id: str,
    user_id: str,
    operation: str,
) -> str:
    """Append user error report to JSONL storage.

    Args:
        summary: User summary of the problem.
        error_id: Optional server error identifier.
        reproduction_steps: Optional steps to reproduce.
        system_info: Optional user-provided environment info.
        attachments: Optional related file references.
        request_id: Request correlation id.
        trace_id: Trace correlation id.
        user_id: User identifier.
        operation: Operation name where issue happened.

    Returns:
        str: Generated report identifier.
    """
    report_id = str(uuid.uuid4())
    report_path = Path(settings.ERROR_REPORTS_FILE)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    payload: dict[str, Any] = {
        "report_id": report_id,
        "timestamp": datetime.now(UTC).isoformat(),
        "summary": summary,
        "error_id": error_id,
        "reproduction_steps": reproduction_steps,
        "system_info": system_info,
        "attachments": attachments or [],
        "request_id": request_id,
        "trace_id": trace_id,
        "user_id": user_id,
        "operation": operation,
    }

    with report_path.open("a", encoding="utf-8") as file_handle:
        file_handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    module_logger.info("Stored user error report report_id=%s error_id=%s", report_id, error_id)
    return report_id

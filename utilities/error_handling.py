"""Unified error formatting, localization, and tool exception boundaries."""

import logging
import uuid
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, cast

from config import settings
from utilities import logging as log_context
from utilities.logging import log_exception_with_id

_MESSAGES: dict[str, dict[str, str]] = {
    "uk": {
        "access_denied": "Доступ заборонено для цієї операції.",
        "not_found": "Ресурс не знайдено або недоступний.",
        "auth_required": "Потрібна автентифікація для виконання операції.",
        "validation": "Некоректні вхідні дані.",
        "operation_failed": "Операцію не вдалося виконати.",
        "unexpected": "Сталася неочікувана помилка на сервері.",
        "details": "Технічні деталі",
        "actions": "Що можна зробити",
        "report": "Щоб повідомити про проблему, передайте цей Error ID до підтримки.",
    },
    "en": {
        "access_denied": "Access is denied for this operation.",
        "not_found": "Resource was not found or is unavailable.",
        "auth_required": "Authentication is required for this operation.",
        "validation": "Input data is invalid.",
        "operation_failed": "The operation could not be completed.",
        "unexpected": "An unexpected server error occurred.",
        "details": "Technical details",
        "actions": "What you can do",
        "report": "To report this issue, share this Error ID with support.",
    },
}


def _locale() -> str:
    """Resolve active locale code for localized error responses.

    Returns:
        str: ``"uk"`` or ``"en"``.
    """
    locale = (settings.ERROR_LOCALE or "uk").lower()
    if locale.startswith("en"):
        return "en"
    return "uk"


def _infer_error_code(error_text: str) -> str:
    """Infer normalized error code from technical error text.

    Args:
        error_text: Raw error text.

    Returns:
        str: Normalized error code key.
    """
    lowered = error_text.lower()

    if (
        "access denied" in lowered
        or "permission" in lowered
        or "not within allowed roots" in lowered
    ):
        return "access_denied"
    if "not found" in lowered or "does not exist" in lowered or "not exist" in lowered:
        return "not_found"
    if "auth" in lowered or "token" in lowered or "unauth" in lowered:
        return "auth_required"
    if "invalid" in lowered or "expected" in lowered or "required" in lowered:
        return "validation"
    return "operation_failed"


def format_localized_error(
    *,
    error_code: str,
    error_id: str,
    trace_id: str | None = None,
    details: str | None = None,
) -> str:
    """Build localized user-facing error message.

    Args:
        error_code: Error category key.
        error_id: Correlation identifier.
        trace_id: Optional request trace identifier.
        details: Optional technical details.

    Returns:
        str: Formatted localized error text.
    """
    locale = _locale()
    i18n = _MESSAGES[locale]

    actions_uk = [
        "1) Перевірте параметри запиту.",
        "2) Спробуйте повторити операцію пізніше.",
        "3) Якщо помилка повторюється, зверніться до підтримки.",
    ]
    actions_en = [
        "1) Check request parameters.",
        "2) Try again later.",
        "3) If the problem persists, contact support.",
    ]
    actions = actions_en if locale == "en" else actions_uk

    base = i18n.get(error_code, i18n["unexpected"])
    lines = [base]

    if details:
        lines.append(f"{i18n['details']}: {details}")

    lines.append(f"Error ID: {error_id}")
    if trace_id:
        lines.append(f"Trace ID: {trace_id}")
    lines.append(f"{i18n['actions']}:")
    lines.extend(actions)
    lines.append(i18n["report"])
    return "\n".join(lines)


def build_error_response(
    logger: logging.Logger,
    *,
    error_code: str,
    technical_details: str | None = None,
    exc: Exception | None = None,
    **context: Any,
) -> str:
    """Create formatted error response and log event with identifiers.

    Args:
        logger: Logger to write error events.
        error_code: Normalized error code key.
        technical_details: Optional technical error detail.
        exc: Optional original exception.
        **context: Additional structured logging context.

    Returns:
        str: Localized message for client response.
    """
    trace_id = log_context.trace_id_ctx.get()
    if exc is not None:
        error_id = log_exception_with_id(
            logger,
            "Tool execution failed",
            exc,
            error_code=error_code,
            trace_id=trace_id,
            **context,
        )
    else:
        error_id = str(uuid.uuid4())
        logger.error(
            "Tool returned recoverable error",
            extra={
                "error_id": error_id,
                "trace_id": trace_id,
                "error_code": error_code,
                **context,
            },
        )

    return format_localized_error(
        error_code=error_code,
        error_id=error_id,
        trace_id=trace_id if trace_id != "-" else None,
        details=technical_details,
    )


def tool_error_boundary[F: Callable[..., Awaitable[Any]]](func: F, logger: logging.Logger) -> F:
    """Wrap tool call with standardized exception handling.

    Args:
        func: Async tool function.
        logger: Logger for error events.

    Returns:
        F: Wrapped function with uniform error boundary.
    """

    @wraps(func)
    async def wrapped(*args: Any, **kwargs: Any):
        try:
            result = await func(*args, **kwargs)
            if isinstance(result, str) and result.startswith("Error"):
                error_code = _infer_error_code(result)
                return build_error_response(
                    logger,
                    error_code=error_code,
                    technical_details=result,
                    operation=func.__name__,
                )
            return result
        except Exception as exc:
            return build_error_response(
                logger,
                error_code="unexpected",
                technical_details=str(exc),
                exc=exc,
                operation=func.__name__,
            )

    return cast(F, wrapped)

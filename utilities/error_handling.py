import logging
import uuid
from collections.abc import Awaitable, Callable
from functools import wraps
from inspect import isawaitable
from typing import Any, cast, get_type_hints

from config import settings
from utilities import logging as log_context
from utilities.logging import log_exception_with_id

_MESSAGES: dict[str, dict[str, str]] = {
    "uk": {
        "access_denied": "Доступ заборонено для цієї операції.",
        "permission_denied": "Нема дозволу на виклик цього інструменту.",
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
        "permission_denied": "You do not have permission to invoke this tool.",
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


class ToolOperationError(Exception):
    def __init__(
        self,
        error_code: str,
        technical_details: str,
        *,
        actions: list[str] | None = None,
    ):
        super().__init__(technical_details)
        self.error_code = error_code
        self.technical_details = technical_details
        self.actions = actions


def _locale() -> str:
    locale = (settings.ERROR_LOCALE or "uk").lower()
    if locale.startswith("en"):
        return "en"
    return "uk"


def _infer_error_code(error_text: str) -> str:
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
    actions: list[str] | None = None,
) -> str:
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
    default_actions = actions_en if locale == "en" else actions_uk
    action_lines = actions if actions else default_actions

    base = i18n.get(error_code, i18n["unexpected"])
    lines = [base]

    if details:
        lines.append(f"{i18n['details']}: {details}")

    lines.append(f"Error ID: {error_id}")
    if trace_id:
        lines.append(f"Trace ID: {trace_id}")
    lines.append(f"{i18n['actions']}:")
    lines.extend(action_lines)
    lines.append(i18n["report"])
    return "\n".join(lines)


def build_error_response(
    logger: logging.Logger,
    *,
    error_code: str,
    technical_details: str | None = None,
    actions: list[str] | None = None,
    exc: Exception | None = None,
    **context: Any,
) -> str:
    trace_id = log_context.trace_id_ctx.get()
    if isinstance(exc, ToolOperationError):
        error_code = exc.error_code
        technical_details = technical_details or exc.technical_details
        actions = exc.actions or actions

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
        actions=actions,
    )


def tool_error_boundary[F: Callable[..., Awaitable[Any]]](func: F, logger: logging.Logger) -> F:
    @wraps(func)
    async def wrapped(*args: Any, **kwargs: Any):
        try:
            result = func(*args, **kwargs)
            if isawaitable(result):
                result = await cast(Awaitable[Any], result)
            if isinstance(result, str) and result.startswith("Error"):
                error_code = _infer_error_code(result)
                return build_error_response(
                    logger,
                    error_code=error_code,
                    technical_details=result,
                    operation=func.__name__,
                )
            return result
        except ToolOperationError as exc:
            return build_error_response(
                logger,
                error_code=exc.error_code,
                technical_details=exc.technical_details,
                actions=exc.actions,
                exc=exc,
                operation=func.__name__,
            )
        except Exception as exc:
            cause = exc.__cause__
            if isinstance(cause, ToolOperationError):
                return build_error_response(
                    logger,
                    error_code=cause.error_code,
                    technical_details=cause.technical_details,
                    actions=cause.actions,
                    exc=exc,
                    operation=func.__name__,
                )
            return build_error_response(
                logger,
                error_code="unexpected",
                technical_details=str(exc),
                exc=exc,
                operation=func.__name__,
            )

    try:
        wrapped.__annotations__ = get_type_hints(func)
    except Exception as e:
        logger.warning(f"Failed to resolve type hints for {func.__name__}: {e}")
    return cast(F, wrapped)

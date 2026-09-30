"""Structured logging setup using structlog with JSON rendering and security redaction."""

import logging
import sys
from typing import Any
import structlog
from structlog.types import EventDict, WrappedLogger
from app.config import get_settings

# Sensitive keys that must always be masked in logs
SENSITIVE_KEYS = {
    "password",
    "secret",
    "token",
    "api_key",
    "authorization",
    "clerk_webhook_secret",
    "encryption_key",
}

# Payload keys that should be redacted/truncated when REDACT_PROMPTS_IN_LOGS is enabled
PROMPT_KEYS = {
    "prompt",
    "seed_prompt",
    "mutated_prompt",
    "target_response",
    "seed_prompts",
    "raw_response",
}


def redact_sensitive_data(
    logger: WrappedLogger,  # noqa: ARG001
    method_name: str,       # noqa: ARG001
    event_dict: EventDict,
) -> EventDict:
    """Processor that redacts passwords, tokens, API keys, and sensitive payload prompts."""
    settings = get_settings()

    def _clean_value(k: str, v: Any) -> Any:
        lower_k = k.lower()
        if any(secret_term in lower_k for secret_term in SENSITIVE_KEYS):
            return "[REDACTED_SECRET]"
        if settings.REDACT_PROMPTS_IN_LOGS and any(p_term == lower_k for p_term in PROMPT_KEYS):
            if isinstance(v, str):
                return f"[REDACTED_PROMPT length={len(v)} preview={v[:24]}...]"
            if isinstance(v, list):
                return f"[REDACTED_PROMPT_LIST count={len(v)}]"
        if isinstance(v, dict):
            return {inner_k: _clean_value(inner_k, inner_v) for inner_k, inner_v in v.items()}
        return v

    return {k: _clean_value(k, v) for k, v in event_dict.items()}


def setup_logging() -> None:
    """Configure structlog and standard library logging for production/development."""
    settings = get_settings()
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        redact_sensitive_data,
    ]

    if settings.LOG_JSON:
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=shared_processors + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(log_level)

    # Silence overly verbose third-party loggers
    for noisy in ("uvicorn.access", "httpcore", "httpx", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Get a bound structlog logger instance."""
    return structlog.get_logger(name or "adversarial_arena")

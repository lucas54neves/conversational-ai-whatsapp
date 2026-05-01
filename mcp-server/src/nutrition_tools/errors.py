"""Tool error envelope for the nutrition MCP server.

Maps raw exceptions raised by `tools.py` (validation `ValueError`s and
`psycopg2` exceptions) to a small set of classified `ToolError`
subclasses with stable `code` strings. The agent reads the code to
decide whether to translate a constraint, ask the user to retry, or
apologize and stop.
"""

from __future__ import annotations

import functools
import logging
from collections.abc import Callable
from typing import Any, TypeVar

import psycopg2
import psycopg2.pool

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


class ToolError(Exception):
    code: str = "tool_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


class ValidationError(ToolError):
    code = "validation_error"


class TransientDBError(ToolError):
    code = "transient_db_error"

    def __init__(self, message: str = "database temporarily unavailable") -> None:
        super().__init__(message)


class PermanentDBError(ToolError):
    code = "permanent_db_error"

    def __init__(self, message: str = "database operation failed") -> None:
        super().__init__(message)


def classify(exc: BaseException) -> ToolError | None:
    if isinstance(exc, ValueError):
        return ValidationError(str(exc))
    if isinstance(exc, psycopg2.pool.PoolError):
        return TransientDBError()
    if isinstance(exc, (psycopg2.OperationalError, psycopg2.InterfaceError)):
        return TransientDBError()
    if isinstance(exc, psycopg2.Error):
        return PermanentDBError()
    return None


def mcp_safe(func: F) -> F:
    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            logger.exception("tool %s failed", func.__name__)
            wrapped = classify(exc)
            if wrapped is None:
                raise
            raise wrapped from exc

    return wrapper  # type: ignore[return-value]

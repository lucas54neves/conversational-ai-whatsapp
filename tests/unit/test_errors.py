import logging

import psycopg2
import psycopg2.pool
import pytest
from nutrition_tools.errors import (
    PermanentDBError,
    TransientDBError,
    ValidationError,
    classify,
    mcp_safe,
)


def test_classify_value_error_preserves_message():
    wrapped = classify(ValueError("weight_kg must be between 20 and 300"))
    assert isinstance(wrapped, ValidationError)
    assert wrapped.message == "weight_kg must be between 20 and 300"


def test_classify_operational_error_is_transient():
    assert isinstance(classify(psycopg2.OperationalError("boom")), TransientDBError)


def test_classify_interface_error_is_transient():
    assert isinstance(classify(psycopg2.InterfaceError("boom")), TransientDBError)


def test_classify_pool_error_is_transient():
    # PoolError does not inherit from psycopg2.Error — must be matched explicitly.
    assert isinstance(classify(psycopg2.pool.PoolError("boom")), TransientDBError)


def test_classify_integrity_error_is_permanent():
    assert isinstance(classify(psycopg2.IntegrityError("boom")), PermanentDBError)


def test_classify_data_error_is_permanent():
    assert isinstance(classify(psycopg2.DataError("boom")), PermanentDBError)


def test_classify_programming_error_is_permanent():
    assert isinstance(classify(psycopg2.ProgrammingError("boom")), PermanentDBError)


def test_classify_unrelated_exception_returns_none():
    assert classify(KeyError("k")) is None
    assert classify(AssertionError()) is None


def test_mcp_safe_passes_return_value_through(caplog):
    caplog.set_level(logging.ERROR)
    decorated = mcp_safe(lambda x: x * 2)
    assert decorated(21) == 42
    assert caplog.records == []


def test_mcp_safe_wraps_value_error(caplog):
    caplog.set_level(logging.ERROR)

    @mcp_safe
    def boom():
        raise ValueError("bad input")

    with pytest.raises(ValidationError) as ei:
        boom()
    assert ei.value.message == "bad input"
    assert ei.value.__cause__ is not None  # `raise X from exc` preserved
    assert any("tool boom failed" in r.message for r in caplog.records)


def test_mcp_safe_does_not_wrap_unknown_exceptions(caplog):
    caplog.set_level(logging.ERROR)

    @mcp_safe
    def boom():
        raise KeyError("k")

    with pytest.raises(KeyError):
        boom()
    # Still logged so programmer bugs surface in the MCP server log.
    assert any("tool boom failed" in r.message for r in caplog.records)


def test_str_format_matches_wire_payload():
    assert str(ValidationError("x")) == "validation_error: x"
    assert str(TransientDBError()) == "transient_db_error: database temporarily unavailable"
    assert str(PermanentDBError()) == "permanent_db_error: database operation failed"

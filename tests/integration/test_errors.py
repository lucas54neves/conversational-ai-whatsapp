"""Prove that the @mcp_safe decorator is wired into the real
@mcp.tool() registrations and translates raw psycopg2 errors at the
boundary."""

from __future__ import annotations

import pytest
from nutrition_tools import db, server
from nutrition_tools.errors import TransientDBError

PHONE = "+5511900000099"


def _decorated_callable(mcp_tool):
    """Resolve the underlying callable wrapped by FastMCP's @mcp.tool().

    FastMCP versions differ in how they expose the original function —
    try the common attribute names, fall back to calling the object
    directly if it stayed callable.
    """
    for attr in ("fn", "func", "callback", "handler"):
        fn = getattr(mcp_tool, attr, None)
        if callable(fn):
            return fn
    if callable(mcp_tool):
        return mcp_tool
    raise AssertionError(f"could not find underlying callable on {type(mcp_tool).__name__}")


def test_transient_error_when_pool_closed(db_url):
    # The session-scoped db_url fixture already initialized db._pool against
    # the testcontainer. Close it to force psycopg2.pool.PoolError on getconn.
    assert db._pool is not None
    db._pool.closeall()
    try:
        fn = _decorated_callable(server.get_user_profile)
        with pytest.raises(TransientDBError) as ei:
            fn(PHONE)
        assert ei.value.code == "transient_db_error"
    finally:
        # Re-init so any subsequent test in the session keeps a working pool.
        db.init_pool()

import os
from contextlib import contextmanager

from psycopg2.pool import ThreadedConnectionPool

_pool: ThreadedConnectionPool | None = None


def init_pool() -> None:
    global _pool
    _pool = ThreadedConnectionPool(1, 10, os.environ["DATABASE_URL"])


@contextmanager
def get_conn():
    assert _pool is not None, "Database pool not initialized"
    conn = _pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _pool.putconn(conn)

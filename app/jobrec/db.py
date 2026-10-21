"""Shared SQLAlchemy declarative base and engine construction for the application.

Kept in its own module so that table definitions can be imported without
pulling in modules that have side effects at import time (such as creating
an OpenAI client).
"""

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase

# The Postgres driver this project installs (psycopg 3).
_POSTGRES_DRIVER = "postgresql+psycopg://"


class Base(DeclarativeBase):
    pass


def make_engine(url: str) -> Engine:
    """Create an engine from a database URL, accepting the forms hosting providers hand out.

    Providers issue ``postgres://`` or ``postgresql://`` URLs. SQLAlchemy rejects the
    first and maps the second to a driver this project does not install, so both are
    rewritten to the psycopg 3 driver. Postgres connections are checked before use
    (hosted databases drop idle connections) and server-side prepared statements are
    disabled so connection poolers in transaction mode work.
    """
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            url = _POSTGRES_DRIVER + url[len(prefix):]
            break
    if url.startswith("postgresql"):
        return create_engine(url, pool_pre_ping=True, connect_args={"prepare_threshold": None})
    return create_engine(url)

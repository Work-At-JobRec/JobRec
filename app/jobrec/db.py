"""Shared SQLAlchemy declarative base for every table in the application.

Kept in its own module so that table definitions can be imported without
pulling in modules that have side effects at import time (such as creating
an OpenAI client).
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass

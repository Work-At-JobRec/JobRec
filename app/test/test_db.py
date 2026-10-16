import os
import sys

# Lets this test import app/src/db.py
SRC_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "src")
)
sys.path.insert(0, SRC_DIR)

from jobrec.db import make_engine  # noqa: E402


# Hosting providers hand out postgres:// URLs, which SQLAlchemy does not accept as written
def test_postgres_scheme_is_rewritten_to_the_installed_driver():
    engine = make_engine("postgres://user:secret@db.example.com:5432/jobrec")

    assert engine.url.drivername == "postgresql+psycopg"
    assert engine.url.host == "db.example.com"
    assert engine.url.database == "jobrec"


# A plain postgresql:// URL would select a driver that is not installed
def test_postgresql_scheme_is_rewritten_to_the_installed_driver():
    assert make_engine("postgresql://user:secret@db.example.com/jobrec").url.drivername == "postgresql+psycopg"


# A URL that already names the driver is left alone
def test_explicit_psycopg_url_is_kept():
    engine = make_engine("postgresql+psycopg://user:secret@db.example.com/jobrec?sslmode=require")

    assert engine.url.drivername == "postgresql+psycopg"
    assert engine.url.query["sslmode"] == "require"


# Postgres connections are checked before use, since a hosted database drops idle ones
def test_postgres_engine_checks_connections_before_use():
    assert make_engine("postgres://user:secret@db.example.com/jobrec").pool._pre_ping is True


# SQLite URLs pass through unchanged
def test_sqlite_url_is_unchanged(tmp_path):
    engine = make_engine(f"sqlite+pysqlite:///{tmp_path / 'x.db'}")

    assert engine.url.drivername == "sqlite+pysqlite"

import pytest
from sqlalchemy import create_engine

from jobrec.db import Base
import jobrec.job_store  # noqa: F401  (registers job_listings on Base)


def pytest_addoption(parser):
    parser.addoption(
        "--run-openai",
        action="store_true",
        default=False,
        help="Run tests that connect to the OpenAI API"
    )


@pytest.fixture
def engine(tmp_path):
    """SQLite schema for the link checker. Modules that define their own engine keep it."""
    test_engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'jobs.db'}")
    Base.metadata.create_all(test_engine)
    return test_engine
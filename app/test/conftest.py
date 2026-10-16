import os

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--run-openai",
        action="store_true",
        default=False,
        help="Run tests that connect to the OpenAI API"
    )


@pytest.fixture
def engine(tmp_path):
    """A fresh database with every table created, matching how the app creates its schema.

    Uses SQLite under tmp_path by default. When TEST_DATABASE_URL is set (the Postgres
    CI job), the same tests run against that database instead; its tables are dropped
    and recreated for each test, so the name must contain "test" to protect real data.
    """
    from jobrec.db import Base, make_engine
    import jobrec.job_store  # noqa: F401  (registers the job_listings table with Base)

    url = os.environ.get("TEST_DATABASE_URL")
    if url:
        if "test" not in url.rsplit("/", 1)[-1].lower():
            raise RuntimeError("TEST_DATABASE_URL must point at a database whose name contains 'test'")
        test_engine = make_engine(url)
        Base.metadata.drop_all(test_engine)
    else:
        test_engine = make_engine(f"sqlite+pysqlite:///{tmp_path / 'jobs.db'}")
    Base.metadata.create_all(test_engine)
    yield test_engine
    test_engine.dispose()

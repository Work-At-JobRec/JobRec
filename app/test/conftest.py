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
    """A fresh SQLite database with every table created, matching how the app creates its schema."""
    from sqlalchemy import create_engine

    from jobrec.db import Base
    import jobrec.job_store  # noqa: F401  (registers the job_listings table with Base)

    test_engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'jobs.db'}")
    Base.metadata.create_all(test_engine)
    yield test_engine
    test_engine.dispose()

"""
imports listings from a local skill database.
will fail if the target database contains listings.
only to be used for building an initial database from locally parsed jobs
"""

from sqlalchemy import select
from jobrec.db import Base, make_engine
from jobrec.job_store import JobListingTable
from jobrec.skill_detection import CanonicalSkillTable, SkillConnectionTable, ListingSkillTable
from jobrec.openaiapi import UserInfoTable
from dotenv import load_dotenv
from os import environ

load_dotenv()

engine_sqlite = make_engine("sqlite:///user_skills.db")
engine_postgres = make_engine(environ.get("DATABASE_URL"))

with engine_sqlite.connect() as conn_sqlite:
    with engine_postgres.connect() as conn_postgres:
        for table in Base.metadata.sorted_tables:
            print(f"processing table {table.name}"
            for row in conn_sqlite.execute(select(table.c)):
                conn_postgres.execute(table.insert().values(row._mapping))
        conn_postgres.commit()
from datetime import datetime
import os
import random

from dotenv import load_dotenv
from jobrec.db import make_engine, Base
from jobrec.job_store import JobListingTable
from sqlalchemy.orm import Session
from sqlalchemy import func, select
from jobrec.skill_detection import (
    CanonicalSkillTable,
    ListingSkillTable,
    SkillConnectionTable,
)
from sys import argv

if __name__ == "__main__":
    prod_db_engine = make_engine("sqlite+pysqlite:///user_skills.db")
    with Session(prod_db_engine) as session:
        listings = session.scalars(
            select(JobListingTable).where(JobListingTable.skills_pending == False)
        ).all()
        listing_count = 0
        listing_average_skills = 0
        for listing in listings:
            listing_count += 1
            skills = (
                session.scalars(
                    select(func.count())
                    .select_from(ListingSkillTable)
                    .where(ListingSkillTable.listing_id == listing.id)
                )
                or 0
            ).one()
            listing_average_skills += skills
        listing_average_skills /= listing_count

        skills_average_connections = 0
        skill_count = 0
        skills = session.scalars(select(CanonicalSkillTable)).all()
        for skill in skills:
            skill_count += 1
            connections = (
                session.scalar(
                    select(func.count())
                    .select_from(SkillConnectionTable)
                    .where(
                        SkillConnectionTable.skill_a_id == skill.id
                        or SkillConnectionTable.skill_b_id == skill.id
                    )
                )
                or 0
            )
            skills_average_connections += connections
        skills_average_connections /= skill_count

    if len(argv) == 1:
        desired_listing_count = 1000
    else:
        desired_listing_count = int(argv[1])

    test_db_engine = make_engine("sqlite+pysqlite:///mock_jobrec.db")
    Base.metadata.create_all(test_db_engine)
    with Session(test_db_engine) as session:
        mock_skill_count = (
            session.scalar(select(func.count()).select_from(CanonicalSkillTable)) or 0
        )
        mock_listing_count = (
            session.scalar(select(func.count()).select_from(JobListingTable)) or 0
        )
    to_create = desired_listing_count - mock_listing_count
    skills_per_listing = int(listing_average_skills)
    skills_to_create = int(to_create * (skill_count / listing_count))
    connections_per_skill = int(skills_average_connections)
    print(
        f"creating {to_create} listings with {skills_per_listing} skills. creating {skills_to_create} skills with {connections_per_skill} connections"
    )

    test_db_engine = make_engine("sqlite+pysqlite:///mock_jobrec.db")
    Base.metadata.create_all(test_db_engine)
    with Session(test_db_engine) as session:
        # create skills
        for skill in range(
            mock_skill_count + 1, mock_skill_count + 1 + skills_to_create
        ):
            new_skill = CanonicalSkillTable(
                normalized_name=f"mock_skill_{skill}", skill_name=f"mock_skill_{skill}"
            )
            session.add(new_skill)
            connections = session.scalars(
                select(CanonicalSkillTable)
                .order_by(func.random())
                .limit(connections_per_skill)
            ).all()
            for connection in connections:
                new_connection = SkillConnectionTable(
                    skill_a_id=new_skill.id,
                    skill_b_id=connection.id,
                    distance=random.random(),
                )
                session.add(new_connection)
        session.commit()

    with Session(test_db_engine) as session:
        for listing in range(
            mock_listing_count + 1, mock_listing_count + 1 + to_create
        ):
            new_listing = JobListingTable(
                dedupe_key=f"mock_job_{listing}",
                source=f"test",
                title=f"test {listing}",
                company_name=f"kirijo group",
                description="none",
                application_url="www.example.com",
                status="open",
                skills_pending=False,
                scraped_at=datetime.now(),
                first_seen_at=datetime.now(),
                last_seen_at=datetime.now(),
                updated_at=datetime.now(),
            )
            session.add(new_listing)
            skill_selection = connections = session.scalars(
                select(CanonicalSkillTable)
                .order_by(func.random())
                .limit(skills_per_listing)
            ).all()

            for skill in skill_selection:
                new_listing_skill = ListingSkillTable(
                    listing_id=new_listing.id,
                    skill_id=skill.id,
                    proficiency_level=random.choice([1, 2, 3, 4]),
                )
                session.add(new_listing_skill)
        session.commit()

from openai import OpenAI
from dotenv import load_dotenv
from typing import Annotated
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy import select
from sqlalchemy.orm import DeclarativeBase, Session
import sqlalchemy

_ = load_dotenv()

client = OpenAI()

class Base(DeclarativeBase):
    pass

class UserInfoTable(Base):
    __tablename__ = "user_info"

    user_id = sqlalchemy.Column("user_id", sqlalchemy.BLOB, primary_key=True)
    info = sqlalchemy.Column("skills", sqlalchemy.JSON)
    done_processing = sqlalchemy.Column("done_processing", sqlalchemy.Boolean)

class SkillRanking(BaseModel):
    skill_name: str = Field(
        ...,
        description="Human-readable and distinct name representing a specific skill",
    )
    proficiency_level: int = Field(
        ...,
        le=4,
        ge=1,
        description="Numerical ranking of an applicant's proficiency in this skill from 1-4, where 1 is basic familiarity, 2 is extensive amateur experience, 3 is professional or academic experience, and 4 is proven, long-term mastery.",
    )

class Education(BaseModel):
    school: str = Field(..., description="School that the degree was earned from")
    degree: str = Field(..., description="Degree level and field of study achieved from this university (e.g. bachelor's in art history). Do not include GPA.")

class Social(BaseModel):
    platform: str = Field(..., description="Name of platform where this account is hosted")
    url: str = Field(..., description="Full URL of the user's account on this platform, including hostname")

class Employment(BaseModel):
    company_name: str = Field(..., description="Name of the company where the user worked")
    role: str = Field(..., description="User's role at the company")



class UserInfo(BaseModel):
    skills: list[SkillRanking] = Field(
        ..., description="All skills that the applicant has any experience with."
    )
    education: list[Education] = Field(..., description="All education experience the applicant has")
    projects: list[str] = Field(..., description="Names of all projects the user has experience with (do not include other information)")
    socials: list[Social] = Field(..., description="All personal (not organizational) social media included in the user's resume")
    employment_history: list[Employment] = Field(..., description="All previous work experience of the user")



def update_skill_db(user_id: bytes, engine: sqlalchemy.Engine, filename: str):
    user_info = parse_resume(filename)
    with Session(engine) as session:

        stmt = select(UserInfoTable).where(UserInfoTable.user_id == user_id)
        try:
            skill_ranking = session.scalars(stmt).one()
        except:
            return None

        if user_info is None:
            skill_ranking.done_processing = True
            return
        else:

            unique_socials = {}
            for s in user_info.socials:
                unique_socials[s.platform.lower()] = s

            user_info.socials = list(unique_socials.values())

            for s in user_info.socials:
                if s.url and not s.url.startswith("http"):
                    s.url = "https://" + s.url

            skill_ranking.info = user_info.model_dump()
            skill_ranking.done_processing = True

        session.commit()


def parse_resume(filename: str) -> UserInfo | None:

    uploaded = client.files.create(file=open(filename, "rb"), purpose="assistants")
    response = client.responses.parse(
        model="gpt-5.2",
        instructions="""You are an HR manager who is an expert in reading and parsing resumes.
        First, determine the user's employment history, project experience, education, and any linked social media presences. 
        Then, determine what skills the applicant has from their PDF resume. 
        Furthermore, rank their proficiency in each skill on a scale from 1-4, where 1 is basic familiarity, 2 is extensive amateur experience, 3 is professional or academic experience, and 4 is proven, long-term mastery.""",
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_file", "file_id": uploaded.id},
                ],
            }
        ],
        text_format=UserInfo,
    )

    return response.output_parsed
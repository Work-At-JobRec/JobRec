import os
from os import environ as env
from urllib.parse import urlparse
from flask import (
    Flask,
    flash,
    request,
    redirect,
    render_template,
    url_for,
    jsonify,
    Response,
)
from werkzeug.utils import secure_filename
from sqlalchemy import create_engine, select, delete
from sqlalchemy.orm import Session
from openaiapi import UserInfoTable, update_skill_db, UserInfo, Base, update_user_info
from job_store import (
    JobListingTable,
)
from threading import Thread
from pypdf import PdfReader
from docx import Document
from dotenv import load_dotenv
import auth
from jobs import get_jobs, get_job
from auth import require_auth, get_user_id
from listing_search.find_listings import (
    find_percentile,
    find_skill_gaps,
    get_job_recommendations,
)

load_dotenv()


RESUME_FOLDER = env.get("RESUME_FOLDER", "uploads")
ALLOWED_EXTENSIONS = {"pdf", "docx"}

os.makedirs(RESUME_FOLDER, exist_ok=True)
app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = RESUME_FOLDER
app.secret_key = "test"

os.makedirs(RESUME_FOLDER, mode=600, exist_ok=True)

mock_userid: str = "test|mockuser1"


engine = create_engine(env.get("DATABASE_URL", "sqlite+pysqlite:///user_skills.db"))
Base.metadata.create_all(engine)

# Development only: clear user data whenever app starts
if env.get("DEV") is not None:
    with Session(engine) as session:
        session.execute(delete(UserInfoTable))

Base.metadata.create_all(engine)


# Given a user, their search preferences, and a pagination number, return the next page of job search results
@app.route("/api/job_feed", methods=["GET"])
@require_auth
def get_job_feed():
    data = request.get_json()
    user_id = get_user_id()

    salary_low = data.get("salary_low")
    salary_high = data.get("salary_high")
    radius = data.get("location_radius")
    position_type = data.get("position_type")
    location_override = data.get("location_override")
    position_name = data.get("position_name")
    company_name = data.get("company_name")
    page = data.get("page")

    try:
        return jsonify(
            get_job_recommendations(
                user_id,
                page,
                salary_low,
                salary_high,
                radius,
                position_type,
                location_override,
                position_name,
                company_name,
            )
        )
    except TypeError:
        return Response(status=400)


@app.route("/api/update_profile", methods=["PUT"])
@require_auth
def update_profile():
    data = request.get_json()
    user_id = get_user_id()

    name = data.get("name")
    email = data.get("email")
    phone = data.get("phone")
    address = data.get("address")
    # TODO: validation
    skills = data.get("skills")
    education = data.get("education")
    projects = data.get("projects")
    socials = data.get("socials")
    employment_history = data.get("employment_history")
    # TODO: probably needs some model_validates before this point
    return jsonify(
        update_user_info(
            user_id,
            name,
            email,
            phone,
            address,
            skills,
            education,
            projects,
            socials,
            employment_history,
        )
    )


# given a user and a listing, identify the skill gaps the user has
@app.route("/api/skill_gap")
@require_auth
def request_skill_gaps():
    data = request.get_json()
    user_id = get_user_id()

    listing_id = data.get("listing_id")
    return jsonify(find_skill_gaps(user_id, listing_id))


# given a user and a listing, estimate the percentage of candidates the user exceeds in qualifications
@app.route("/api/candidate_percentile")
@require_auth
def get_candidate_percentile():
    data = request.get_json()
    user_id = get_user_id()

    listing_id = data.get("listing_id")
    return jsonify(find_percentile(user_id, listing_id))


# prune jobs from the database which are closed
@app.route("/api/prune", methods=["POST"])
@require_auth
def prune_old_jobs():
    # TODO: ensure user is admin, then prune
    raise NotImplementedError


@app.route("/api/onboarding", methods=["POST"])
@require_auth
def complete_onboarding():
    user_id = get_user_id()
    with Session(engine) as session:
        stmt = select(UserInfoTable).where(UserInfoTable.user_id == user_id)
        try:
            user_info_raw = session.scalars(stmt).one()
            user_info = UserInfo.model_validate(user_info_raw.info)
            user_info.name = request.form.get("name")
            user_info.email = request.form.get("email")
            user_info.phone = request.form.get("phone")
            user_info.location = request.form.get("address")
            user_info_raw.info = user_info.model_dump()
        except:
            new_user_personals = UserInfo(
                name=request.form.get("name"),
                email=request.form.get("email"),
                phone=request.form.get("phone"),
                location=request.form.get("address"),
                skills=[],
                education=[],
                projects=[],
                socials=[],
                employment_history=[],
            )
            new_user = UserInfoTable(
                user_id=user_id,
                info=new_user_personals.model_dump(),
                done_processing=True,
            )
            session.add(new_user)
        session.commit()
    return Response(status=200)


# new home page
@app.route("/")
@require_auth
def home():
    return Response(status=404)


@app.route("/api/profile")
@require_auth
def profile():
    user_id = get_user_id()
    with Session(engine) as session:
        stmt = select(UserInfoTable).where(UserInfoTable.user_id == user_id)
        try:
            user_info_raw = session.scalars(stmt).one()
        except:
            return jsonify(status="empty", user_info=None)
    if user_info_raw.done_processing:
        try:
            user_info = UserInfo.model_validate(user_info_raw.info)
            return jsonify(status="done", user_info=user_info.model_dump())
        except:
            return jsonify(status="done", user_info=None)
    return jsonify(status="processing", user_info=None)


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route('/api/jobs')
def jobs_api():
    return jsonify(get_jobs(engine, limit=request.args.get("limit", type=int)))

@app.route('/api/jobs/<job_id>')
def job_detail_api(job_id):
    job = get_job(job_id, engine)
    if job is None:
        return jsonify(error="Job not found"), 404
    return jsonify(job)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
           
def valid_resume_file(filepath):
    try:
        extension = filepath.rsplit(".", 1)[1].lower()

        if extension == "pdf":
            reader = PdfReader(filepath)

            # Make sure the PDF can actually be read
            if len(reader.pages) == 0:
                return False

        elif extension == "docx":
            # Document() will raise an exception if the file is corrupted
            Document(filepath)

        else:
            return False

        return True

    except Exception:
        return False


@app.route("/upload", methods=["POST"])
@require_auth
def upload_file():
    user_id = get_user_id()
    # check if the post request has the file part
    if "resume" not in request.files:
        flash("No file part")
        return redirect(request.url)
    print(request.files)
    file = request.files["resume"]
    # If the user does not select a file, the browser submits an
    # empty file without a filename.
    if file.filename == "":
        flash("No selected file")
        return redirect(request.url)
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(filepath)
        # Check that the uploaded file is actually a valid PDF/DOCX
        if not valid_resume_file(filepath):
            os.remove(filepath)
            return Response(status=400)
        # add empty user info to db if not already present
        with Session(engine) as session:
            stmt = select(UserInfoTable).where(UserInfoTable.user_id == user_id)
            try:
                user_info = session.scalars(stmt).one()
                user_info.done_processing = False
            except:
                user_info = UserInfoTable(
                    user_id=user_id, info={}, done_processing=False
                )
                session.add(user_info)
            session.commit()
            p = Thread(target=update_skill_db, args=[user_id, engine, filepath])
            p.start()
            print("finished scheduling process")
            # change made so when resumes upload it goes to the profile
            # instead of default title page
            return Response(status=200)
    return Response(status=400)


if __name__ == "__main__":
    url = urlparse(env.get("APP_BASE_URL"))
    app.run(host=url.hostname, port=url.port or 5001, debug=True)

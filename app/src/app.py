import os
from os import environ as env
from urllib.parse import urlparse
from flask import Flask, flash, request, redirect, render_template, url_for, jsonify, Response
from werkzeug.utils import secure_filename
from sqlalchemy import create_engine, select, delete
from sqlalchemy.orm import Session
from openaiapi import UserInfoTable, update_skill_db, UserInfo, Base
from threading import Thread
from pypdf import PdfReader
from docx import Document
from dotenv import load_dotenv
from auth import require_auth, get_user_id

load_dotenv()


RESUME_FOLDER = "uploads"
ALLOWED_EXTENSIONS = {'pdf', 'docx'}

os.makedirs(RESUME_FOLDER, exist_ok=True)
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = RESUME_FOLDER
app.secret_key = "test"

mock_userid: str = "test|mockuser1"


engine = create_engine(env.get("DATABASE_URL", "sqlite+pysqlite:///user_skills.db"))
Base.metadata.create_all(engine)

# Development only: clear user data whenever app starts
if(env.get("DEV") is not None):
    with Session(engine) as session:
        session.execute(delete(UserInfoTable))

Base.metadata.create_all(engine)


@app.route('/api/onboarding', methods=["POST"])
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
                email = request.form.get("email"),
                phone = request.form.get("phone"),
                location = request.form.get("address"),
                skills=[],
                education=[],
                projects=[],
                socials=[],
                employment_history=[]
            )
            new_user = UserInfoTable(user_id = user_id, info = new_user_personals.model_dump(), done_processing = True)
            session.add(new_user)
        session.commit()
    return Response(status=200)

#new home page
@app.route('/')
@require_auth
def home():
    return Response(status=404)

@app.route('/api/profile')
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
@app.route('/upload', methods=['POST'])
@require_auth
def upload_file():
    user_id = get_user_id()
    # check if the post request has the file part
    if 'resume' not in request.files:
        flash('No file part')
        return redirect(request.url)
    print(request.files)
    file = request.files['resume']
    # If the user does not select a file, the browser submits an
    # empty file without a filename.
    if file.filename == '':
        flash('No selected file')
        return redirect(request.url)
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(
            app.config['UPLOAD_FOLDER'],
            filename
        )
        file.save(filepath)
        # Check that the uploaded file is actually a valid PDF/DOCX
        if not valid_resume_file(filepath):
            os.remove(filepath)
            return Response(status=400)
        # add empty user info to db if not already present
        with Session(engine) as session:
            stmt = select(UserInfoTable).where(
                UserInfoTable.user_id == user_id
            )
            try:
                user_info = session.scalars(stmt).one()
                user_info.done_processing = False
            except:
                user_info = UserInfoTable(user_id = user_id, info = {}, done_processing = False)
                session.add(user_info)
            session.commit()
            p = Thread(
                target=update_skill_db,
                args=[user_id, engine, filepath]
            )
            p.start()
            print("finished scheduling process")
            # change made so when resumes upload it goes to the profile
            # instead of default title page
            return Response(status=200)
    return Response(status=400)

if __name__ == "__main__":
    url = urlparse(env.get("APP_BASE_URL"))
    app.run(host=url.hostname, port=url.port or 5001, debug=True)
import os
from flask import Flask, flash, request, redirect, render_template, url_for, jsonify
from werkzeug.utils import secure_filename
from sqlalchemy import create_engine, select, delete
from sqlalchemy.orm import Session
from openaiapi import UserInfoTable, update_skill_db, UserInfo, Base
from threading import Thread
from pypdf import PdfReader
from docx import Document

RESUME_FOLDER = "uploads"
ALLOWED_EXTENSIONS = {'pdf', 'docx'}

os.makedirs(RESUME_FOLDER, exist_ok=True)
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = RESUME_FOLDER
app.secret_key = "test"

mock_userid: bytes = b"team 6"

engine = create_engine("sqlite+pysqlite:///user_skills.db")
Base.metadata.create_all(engine)

# Development only: clear user data whenever app starts
with Session(engine) as session:
    session.execute(delete(UserInfoTable))
    session.commit()
    
#new home page
@app.route('/')
def home():
    return render_template("index.html")

@app.route('/profile')
def profile():
    with Session(engine) as session:
        stmt = select(UserInfoTable).where(UserInfoTable.user_id == mock_userid)
        try:
            user_info_raw = session.scalars(stmt).one()
        except:
            return jsonify(status="empty", user_info=None)
    if user_info_raw.done_processing:
        user_info = UserInfo.model_validate(user_info_raw.info)
        return jsonify(status="done", user_info=user_info.model_dump())
    return jsonify(status="processing", user_info=None)

@app.route('/api/profile')
def profile_api():
    with Session(engine) as session:
        stmt = select(UserInfoTable).where(
            UserInfoTable.user_id == mock_userid
        )

        user_info_raw = session.scalars(stmt).one_or_none()

        if user_info_raw is None:
            return jsonify({"error": "User not found"}), 404

        if not user_info_raw.done_processing:
            return jsonify({"processing": True}), 202

        user_info = UserInfo.model_validate(user_info_raw.info)

        return jsonify(user_info.model_dump())

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
@app.route('/upload', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
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
                flash('Uploaded resume is corrupted or invalid')
                return redirect(url_for('profile'))
            # add empty user info to db if not already present
            with Session(engine) as session:
                stmt = select(UserInfoTable).where(
                    UserInfoTable.user_id == mock_userid
                )
                try:
                    user_info = session.scalars(stmt).one()
                    user_info.done_processing = False
                except:
                    user_info = UserInfoTable(
                        user_id=mock_userid,
                        info="{}",
                        done_processing=False
                    )
                session.add(user_info)
                session.commit()
                p = Thread(
                    target=update_skill_db,
                    args=[mock_userid, engine, filepath]
                )
                p.start()
                print("finished scheduling process")
                # change made so when resumes upload it goes to the profile
                # instead of default title page
                return redirect(url_for('profile'))

    return redirect(url_for('home'))

if __name__ == "__main__":
    # Port 5000 conflicts with macOS's AirPlay Receiver (ControlCenter),
    # which silently steals a share of requests on that port.
    app.run(debug=True, port=5001)
import os
from flask import Flask, jsonify, request
from werkzeug.utils import secure_filename
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from openaiapi import UserInfoTable, update_skill_db, UserInfo, Base
from threading import Thread


RESUME_FOLDER = "uploads"
ALLOWED_EXTENSIONS = {'pdf', 'txt'}

os.makedirs(RESUME_FOLDER, exist_ok=True)
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = RESUME_FOLDER
app.secret_key = "test"

mock_userid: bytes = b"team 6"

engine = create_engine("sqlite+pysqlite:///user_skills.db")
Base.metadata.create_all(engine)

#removes old user data
with Session(engine) as session:
    session.query(UserInfoTable).delete()
    session.commit()

@app.route('/api/profile')
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

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/upload', methods=['POST'])
def upload_file():
    # check if the post request has the file part
    if 'resume' not in request.files:
        return jsonify(error="No file part"), 400
    file = request.files['resume']
    # If the user does not select a file, the browser submits an
    # empty file without a filename.
    if file.filename == '':
        return jsonify(error="No selected file"), 400
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        # add empty user info to db if not already present
        with Session(engine) as session:
            stmt = select(UserInfoTable).where(UserInfoTable.user_id == mock_userid)
            try:
                user_info = session.scalars(stmt).one()
                user_info.done_processing=False
            except:
                user_info = UserInfoTable(
                    user_id=mock_userid, info="{}", done_processing=False
                )
            session.add(user_info)
            session.commit()
            p = Thread(target=update_skill_db, args=[mock_userid, engine, f"uploads/{filename}"])
            p.start()
        return jsonify(status="processing")
    return jsonify(error="File type not allowed"), 400


if __name__ == "__main__":
    # Port 5000 conflicts with macOS's AirPlay Receiver (ControlCenter),
    # which silently steals a share of requests on that port.
    app.run(debug=True, port=5001)
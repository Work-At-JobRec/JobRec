import os
from os import environ as env
from urllib.parse import urlparse
from flask import Flask, flash, request, redirect, render_template, url_for, jsonify, after_this_request
from werkzeug.utils import secure_filename
from sqlalchemy import create_engine, select, delete
from sqlalchemy.orm import Session
from openaiapi import UserInfoTable, update_skill_db, UserInfo, UserPersonal, Base
from threading import Thread
from pypdf import PdfReader
from docx import Document
from auth0_server_python.auth_server.server_client import ServerClient
from auth0_server_python.auth_types import LogoutOptions, StartInteractiveLoginOptions, StateData, TransactionData
from auth0_server_python.store.abstract import AbstractDataStore
from dotenv import load_dotenv

load_dotenv()


RESUME_FOLDER = "uploads"
ALLOWED_EXTENSIONS = {'pdf', 'docx'}

os.makedirs(RESUME_FOLDER, exist_ok=True)
app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = RESUME_FOLDER
app.secret_key = "test"

mock_userid: str = "test|mockuser1"

engine = create_engine("sqlite+pysqlite:///user_skills.db")
Base.metadata.create_all(engine)

# Development only: clear user data whenever app starts
with Session(engine) as session:
    session.execute(delete(UserInfoTable))
    session.execute(delete(UserPersonal))
    session.commit()

Base.metadata.create_all(engine)


#TODO: can we move this to a subsystem?
# BEGIN: Auth0 boilerplate
#auth0 authentication cookie store
class CookieStore(AbstractDataStore):
    def __init__(self, secret, cookie_name, max_age, model):
        super().__init__({"secret": secret})
        self.cookie_name = cookie_name
        self.max_age = max_age
        self.model = model

    async def set(self, identifier, state, **_):
        @after_this_request
        def apply(response):
            data = state.model_dump() if hasattr(state, "model_dump") else state
            response.set_cookie(
                self.cookie_name,
                self.encrypt(identifier, data),
                httponly=True,
                samesite="Lax",
                secure=not env.get("APP_BASE_URL", "").startswith("http://"),
                max_age=self.max_age,
            )
            return response

    async def get(self, identifier, options=None):
        try:
            encrypted = options["request"].cookies.get(self.cookie_name)
            return self.model.model_validate(self.decrypt(identifier, encrypted)) if encrypted else None
        except Exception:
            app.logger.warning("Failed to decrypt cookie %s", self.cookie_name, exc_info=True)
            return None

    async def delete(self, *_, **__):
        @after_this_request
        def apply(response):
            response.delete_cookie(self.cookie_name)
            return response

def auth0():
    session_secret = env.get("AUTH0_SECRET")

    return ServerClient(
        domain=env.get("AUTH0_DOMAIN"),
        client_id=env.get("AUTH0_CLIENT_ID"),
        client_secret=env.get("AUTH0_CLIENT_SECRET"),
        redirect_uri=env.get("APP_BASE_URL") + "/callback",
        authorization_params={"scope": "openid profile email"},
        secret=session_secret,
        state_store=CookieStore(session_secret, "_a0_session", 259200, StateData),  # 3 days
        transaction_store=CookieStore(session_secret, "_a0_tx", 300, TransactionData),  # 5 min
    )

@app.route("/login")
async def login():
    url = await auth0().start_interactive_login(
        options=StartInteractiveLoginOptions(
            authorization_params=dict(request.args),
        ),
        store_options={"request": request},
    )
    return redirect(url)


@app.route("/callback")
async def callback():
    try:
        await auth0().complete_interactive_login(
            url=request.url, store_options={"request": request},
        )
        return redirect("/")
    except Exception:
        app.logger.exception("Callback error")
        return "Something went wrong. Check server logs for details.", 400


@app.route("/logout")
async def logout():
    url = await auth0().logout(
        options=LogoutOptions(return_to=env.get("APP_BASE_URL")),
        store_options={"request": request},
    )
    return redirect(url)

# END: auth0 boilerplate

@app.route('/onboarding')


#new home page
@app.route('/')
async def home():
    user = await auth0().get_user({"request": request})
    if not (user is None):
        with Session(engine) as session:
            stmt = select(UserInfoTable).where(UserInfoTable.user_id == user.get("sub"))
            try:
                _ = session.scalars(stmt).one()
            except:
                new_user = UserInfoTable(user_id = user.get("sub"), info = '{}', done_processing = True)
                new_user_personals = UserPersonal(user_id = user.get("sub"), name = "New User", email = user.get("email", ""), phone = "", address = "", location = "")
                session.add(new_user)
                session.add(new_user_personals)
                session.commit()
    return render_template("index.html")

@app.route('/profile')
async def profile():
    user = await auth0().get_user({"request": request})
    if user is None:
        return redirect(url_for("login"))
    with Session(engine) as session:
        stmt = select(UserInfoTable).where(UserInfoTable.user_id == user.get("sub"))
        try:
            user_info_raw = session.scalars(stmt).one()
        except:
            return render_template("jobprofile.html")
        stmt = select(UserPersonal).where(UserPersonal.user_id == user.get("sub"))
        try:
            user_personal = session.scalars(stmt).one()
        except:
            return render_template("jobprofile.html")
    
    if user_info_raw.done_processing:
        try:
            user_info = UserInfo.model_validate(user_info_raw.info)
            return render_template("jobprofile.html", user_personal=user_personal, user_info=user_info)
        except:
            return render_template("jobprofile.html", user_personal=user_personal)
    return render_template("jobprofile_processing.html")

@app.route('/api/profile')
async def profile_api():
    user = await auth0().get_user({"request": request})
    if user is None:
        return 403
    with Session(engine) as session:
        stmt = select(UserInfoTable).where(
            UserInfoTable.user_id == user.get("sub")
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
async def upload_file():
    user = await auth0().get_user({"request": request})
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
                    UserInfoTable.user_id == user.get("sub")
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
                    args=[user.get("sub"), engine, filepath]
                )
                p.start()
                print("finished scheduling process")
                # change made so when resumes upload it goes to the profile
                # instead of default title page
                return redirect(url_for('profile'))

    return redirect(url_for('home'))

if __name__ == "__main__":
    url = urlparse(env.get("APP_BASE_URL"))
    app.run(host=url.hostname, port=url.port or 5000, debug=True)
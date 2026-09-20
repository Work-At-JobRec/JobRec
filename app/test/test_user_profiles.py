import os
import sys
from unittest.mock import patch


# Lets this test import files from app/src
SRC_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "src")
)
sys.path.insert(0, SRC_DIR)

mock_user = {"sub": "test|mockuser"}
class mock_auth_server:
    async def get_user(self, _: dict): # type: ignore
        return mock_user

from sqlalchemy import create_engine, delete
from sqlalchemy.orm import Session
from openaiapi import Base, UserPersonal, UserInfo
from  app import app

def test_persistence(tmp_path):
    # disable automatic database clearing
    if not (os.environ.get("DEV") is None):
        os.environ.pop("DEV")

    test_db = tmp_path / "test_user_info.db"
    test_engine = create_engine(f"sqlite+pysqlite:///{test_db}")
    Base.metadata.create_all(test_engine)

    app.config["TESTING"] = True
    client = app.test_client()
    personal_data = {
        "name": "Kanade Yoisaki",
        "email": "k@gmail.com",
        "address": "here",
        "phone": "(555) 393-9393"
    }
    with patch("app.engine", test_engine):
        with patch("app.auth0") as mock_auth0:
            mock_auth0.return_value = mock_auth_server()
            response = client.post("/onboarding", data=personal_data)

    assert response.status_code == 302
    # restart client
    del(client)
    app.config["TESTING"] = True
    client = app.test_client()
    personal_data = {
        "name": "Kanade Yoisaki",
        "email": "k@gmail.com",
        "address": "here",
        "phone": "(555) 393-9393"
    }
    with patch("app.engine", test_engine):
        with patch("app.auth0") as mock_auth0:
            mock_auth0.return_value = mock_auth_server()
            response = client.get("/api/personal_info")

    assert response.status_code == 200
    data = response.get_json()
    assert not (data is None)
    assert data.get("address") == personal_data.get("address")
    assert data.get("email") == personal_data.get("email")
    assert data.get("name") == personal_data.get("name")
    assert data.get("phone") == personal_data.get("phone")



def test_api_returns_correct_personals(tmp_path):
    test_db = tmp_path / "test_user_info.db"
    test_engine = create_engine(f"sqlite+pysqlite:///{test_db}")
    Base.metadata.create_all(test_engine)

    with Session(test_engine) as session:
        dummy_user_personal = UserPersonal(user_id = mock_user.get("sub"), name = "Kanade Yoisaki", email = "k@gmail.com", address = "N/A", phone = "(555) 393-9393")
        session.add(dummy_user_personal)
        session.commit()

        app.config["TESTING"] = True
        client = app.test_client()

        with patch("app.engine", test_engine):
            with patch("app.auth0") as mock_auth0:
                mock_auth0.return_value = mock_auth_server()
                response = client.get("/api/personal_info")

        assert response.status_code == 200

        data = response.get_json()

        assert not (data is None)
        assert data.get("address") == dummy_user_personal.address
        assert data.get("email") == dummy_user_personal.email
        assert data.get("name") == dummy_user_personal.name
        assert data.get("phone") == dummy_user_personal.phone




    

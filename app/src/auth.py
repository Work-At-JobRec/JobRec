from os import environ as env
import asyncio
from flask import request, redirect, after_this_request, g, jsonify
from functools import wraps
from dotenv import load_dotenv
from auth0_api_python import ApiClient, ApiClientOptions
from auth0_api_python.errors import BaseAuthError
from auth0_api_python import get_current_actor

_ = load_dotenv()
# BEGIN: Auth0 boilerplate
api_client = ApiClient(ApiClientOptions(
    domain=env.get("AUTH0_DOMAIN"),
    audience=env.get("AUTH0_AUDIENCE")
))

def require_auth(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Missing or invalid authorization header"}), 401
        
        token = auth_header.split(" ")[1]
        
        try:
            claims = asyncio.run(api_client.verify_access_token(token))
            g.user_claims = claims
            return f(*args, **kwargs)
        except BaseAuthError as e:
            return (
                jsonify({"error": str(e)}),
                e.get_status_code(),
                e.get_headers()
            )
    
    return decorated_function

def get_user_id() -> str: 
    return g.user_claims.get("sub")
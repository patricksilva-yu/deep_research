import datetime
import os
import httpx
from dotenv import load_dotenv

from flask import Flask, render_template, redirect, url_for, g, request, jsonify, make_response
from auth.flask_auth import init_auth, login_required

load_dotenv()

app = Flask(__name__)

# Initialize authentication
init_auth(app)

# API Configuration
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

@app.context_processor
def inject_context():
    return {
        "current_year": datetime.date.today().year,
        "api_base_url": API_BASE_URL
    }

@app.route("/")
def index():
    return render_template("index.html", title="Hivemind – Deep Research Chatbot")

@app.route("/chat")
@login_required
def chat():
    return render_template("chat.html", title="Chat – Hivemind")

@app.route("/sign-in")
def sign_in():
    # Redirect to chat if already logged in
    if g.get("user"):
        return redirect(url_for("chat"))
    return render_template("signin.html", title="Sign in – Hivemind")

@app.route("/register")
def register():
    # Redirect to chat if already logged in
    if g.get("user"):
        return redirect(url_for("chat"))
    return render_template("register.html", title="Register – Hivemind")

@app.route("/api/login", methods=["POST"])
def api_login():
    """
    Flask login endpoint that relays to FastAPI and sets cookies on Flask domain.
    This solves the cross-domain cookie issue.
    """
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")

    if not email or not password:
        return jsonify({"detail": "Missing email or password"}), 400

    try:
        # Call FastAPI login endpoint
        response = httpx.post(
            f"{API_BASE_URL}/auth/login",
            json={"email": email, "password": password},
            timeout=10
        )

        if response.status_code != 200:
            error_data = response.json()
            return jsonify(error_data), response.status_code

        # Get response data
        data = response.json()

        # Create Flask response
        flask_response = make_response(jsonify(data))

        # Extract cookies from FastAPI response and set them on Flask domain
        # httpx.Headers.get_list() returns all Set-Cookie headers as separate strings
        set_cookie_headers = response.headers.get_list("set-cookie")

        # Add each Set-Cookie header to the Flask response
        # Flask Response.headers is a Werkzeug Headers object that supports add()
        for cookie_header in set_cookie_headers:
            flask_response.headers.add("Set-Cookie", cookie_header)

        return flask_response

    except Exception as e:
        return jsonify({"detail": f"Login failed: {str(e)}"}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000)

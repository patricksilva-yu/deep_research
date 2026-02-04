import datetime
import os
import httpx
import logging
from dotenv import load_dotenv

from flask import Flask, render_template, redirect, url_for, g, request, jsonify, make_response
from auth.flask_auth import init_auth, login_required

load_dotenv()

logger = logging.getLogger(__name__)

app = Flask(__name__)

# Initialize authentication (which sets up before_request hooks)
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

@app.route("/api/register", methods=["POST"])
def api_register():
    """
    Flask registration endpoint that relays to FastAPI.
    """
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")

    if not email or not password:
        return jsonify({"detail": "Missing email or password"}), 400

    try:
        # Call FastAPI register endpoint
        response = httpx.post(
            f"{API_BASE_URL}/auth/register",
            json={"email": email, "password": password},
            timeout=10
        )

        if response.status_code != 200:
            error_data = response.json()
            return jsonify(error_data), response.status_code

        # Return success response
        return jsonify(response.json()), 200

    except Exception as e:
        logger.error(f"Registration failed: {e}")
        return jsonify({"detail": "Registration failed"}), 500


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
        logger.error(f"Login failed: {e}")
        return jsonify({"detail": "Login failed"}), 500


@app.route("/api/orchestrator/plan", methods=["POST", "OPTIONS"])
def api_orchestrator_plan():
    """
    Flask proxy endpoint for orchestrator plan that relays to FastAPI.
    This solves the cross-origin file upload issue.
    """
    if request.method == "OPTIONS":
        # Handle preflight request
        response = make_response()
        response.headers["Access-Control-Allow-Origin"] = request.headers.get("Origin", "*")
        response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-CSRF-Token"
        response.headers["Access-Control-Allow-Credentials"] = "true"
        return response

    try:
        # Forward the multipart form data to FastAPI
        # Get all form fields and files
        files_to_send = []
        form_data = {}

        logger.info(f"Received request with form keys: {list(request.form.keys())}, files: {list(request.files.keys())}")

        # Collect form fields
        for key in request.form:
            form_data[key] = request.form[key]

        # Collect files
        for key in request.files:
            file = request.files[key]
            logger.info(f"Processing file: {file.filename}")
            files_to_send.append((key, (file.filename, file.stream, file.content_type)))

        # Get headers to forward
        headers_to_forward = {}
        if request.headers.get("X-CSRF-Token"):
            headers_to_forward["X-CSRF-Token"] = request.headers.get("X-CSRF-Token")

        # Forward cookies
        if request.cookies:
            headers_to_forward["Cookie"] = "; ".join([f"{k}={v}" for k, v in request.cookies.items()])

        # Make request to FastAPI
        response = httpx.post(
            f"{API_BASE_URL}/orchestrator/plan",
            data=form_data,
            files=files_to_send if files_to_send else None,
            headers=headers_to_forward,
            timeout=600.0  # 10 minute timeout for long-running research requests
        )

        # Return FastAPI response
        return jsonify(response.json()), response.status_code

    except httpx.TimeoutException:
        logger.error("Orchestrator plan request timed out")
        return jsonify({"detail": "Request timed out"}), 504
    except Exception as e:
        logger.error(f"Orchestrator plan failed: {e}")
        return jsonify({"detail": "Failed to create research plan"}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000)

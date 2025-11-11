import datetime
import os

from flask import Flask, render_template

app = Flask(__name__)

@app.context_processor
def inject_year():
    return {"current_year": datetime.date.today().year}

@app.route("/")
def index():
    return render_template("index.html", title="Hivemind – Deep Research Chatbot")

@app.route("/chat")
def chat():
    return render_template("chat.html", title="Chat – Hivemind")

@app.route("/sign-in")
def sign_in():
    # Placeholder page since original project had Next.js auth routes
    return render_template("signin.html", title="Sign in – Hivemind")

if __name__ == "__main__":
    app.run()

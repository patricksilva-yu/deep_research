#!/bin/bash
# Production startup script for Deep Research Chatbot

# Start Flask frontend on port 3000 in background
gunicorn -w 4 -b 0.0.0.0:3000 app:app --daemon --access-logfile - --error-logfile -

# Start FastAPI backend on port 8000 (auth + API)
exec uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4

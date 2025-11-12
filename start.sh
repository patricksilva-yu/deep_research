#!/bin/bash
# Production startup script for Deep Research Chatbot

# Start FastAPI backend with Uvicorn
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4 &

# Start Flask frontend with Gunicorn
gunicorn --bind 0.0.0.0:5000 --workers 2 --threads 2 --timeout 120 app:app

# Wait for all background processes
wait

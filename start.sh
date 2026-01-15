#!/bin/bash
# Production startup script for Deep Research Chatbot

# Start FastAPI with Uvicorn (serves both API and frontend)
exec uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4

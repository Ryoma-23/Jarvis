@echo off

start "Jarvis Server" cmd /k "call .venv\Scripts\activate && uvicorn main:app --reload"

timeout /t 3 /nobreak > nul

start "" http://127.0.0.1:8000
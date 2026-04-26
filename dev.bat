@echo off
setlocal

:: Start Backend in a new window
echo Starting Backend...
start cmd /k "call run.bat --dev"

:: Start Frontend
echo Starting Frontend...
cd frontend
npm run dev

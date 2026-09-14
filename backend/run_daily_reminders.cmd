@echo off
rem Daily Phahendra Babu Library membership reminder job (expire overdue + 7-day/daily expiry emails).
cd /d "%~dp0"
".venv\Scripts\python.exe" manage.py send_membership_reminders >> "%TEMP%\opencode\reminders.log" 2>&1

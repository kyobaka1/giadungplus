@echo off
echo ========================================
echo Running Products Migration
echo ========================================
echo.

cd /d "%~dp0"

echo Step 1: Making migrations...
python manage.py makemigrations
if %errorlevel% neq 0 (
    echo ERROR: makemigrations failed!
    pause
    exit /b %errorlevel%
)

echo.
echo Step 2: Running migrations...
python manage.py migrate
if %errorlevel% neq 0 (
    echo ERROR: migrate failed!
    pause
    exit /b %errorlevel%
)

echo.
echo ========================================
echo Migration completed successfully!
echo ========================================
pause

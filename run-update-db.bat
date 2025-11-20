set DJANGO_HOME=TEST
set PRINTER_DEFAULTS=Microsoft Print to PDF
set SERVER_ID=TEST
python manage.py makemigrations
python manage.py sqlmigrate
python manage.py migrate
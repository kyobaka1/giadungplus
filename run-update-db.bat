set DJANGO_HOME=TEST
set PRINTER_DEFAULTS=Microsoft Print to PDF
set SERVER_ID=TEST
python manage.py makemigrations quantri
python manage.py sqlmigrate quantri 0001
python manage.py migrate
python manage.py migrate --database=packing
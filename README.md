# Django HTMX Secure App

## Setup
1. Create and activate a virtualenv.
2. Install dependencies: `pip install -r requirements/dev.txt`
3. For Ubuntu mysqlclient build deps: `sudo apt-get install pkg-config default-libmysqlclient-dev build-essential`
4. Configure `.env`.
5. Run migrations: `python manage.py migrate`
6. Create admin user: `python manage.py createsuperuser`
7. Run server: `python manage.py runserver`
8. Run celery worker: `celery -A config worker -l info`

## Notes
- `MAIL_DRIVER=log` stores generated emails in `logs/mail/`.
- `MAIL_DRIVER=smtp` sends via SMTP regardless of environment.
- Login is blocked until email is verified.

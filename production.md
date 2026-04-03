# Production Deployment Guide

This document describes how to deploy this Django application on a Linux VPS.

---

## Production Architecture

The application requires these long-running processes:

| Process         | Role                                              |
|-----------------|---------------------------------------------------|
| Gunicorn        | WSGI server running the Django app                |
| Celery worker   | Processes async tasks (email delivery)            |
| Nginx           | Reverse proxy, TLS termination, static files      |
| MySQL 8         | Primary relational database                       |
| Redis 7         | Celery broker and result backend                  |

The web process and the Celery worker are separate processes. If the worker is down, email-dependent flows (registration, password reset) still succeed — tasks are queued in Redis with automatic retries — but delivery is delayed until the worker recovers.

---

## Server Requirements

| Component   | Minimum requirement                           |
|-------------|-----------------------------------------------|
| OS          | Ubuntu 22.04 LTS or Debian 12                 |
| Python      | 3.12+                                         |
| Node.js     | 18+ (only needed to rebuild Tailwind CSS)     |
| MySQL       | 8.0                                           |
| Redis       | 7.x                                           |
| RAM         | 1 GB minimum; 2 GB+ recommended               |
| Disk        | 20 GB+ depending on log and media volume      |

---

## Server Packages

Install the base services and build dependencies:

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y \
    python3 python3-venv python3-pip \
    nginx \
    redis-server \
    mysql-server \
    build-essential pkg-config default-libmysqlclient-dev \
    certbot python3-certbot-nginx \
    git
```

If MySQL or Redis are provided by your host as managed services, skip those packages and point `.env` to the managed endpoints instead.

---

## Database Setup (MySQL)

### Secure Installation

Run the MySQL hardening wizard:

```bash
sudo mysql_secure_installation
```

Follow the prompts to set a root password, remove anonymous users, disallow remote root login, and remove test databases.

### Create the Application Database and User

```bash
sudo mysql -u root -p
```

```sql
CREATE DATABASE django_htmx CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'django_htmx'@'localhost' IDENTIFIED BY 'strong-db-password';
GRANT ALL PRIVILEGES ON django_htmx.* TO 'django_htmx'@'localhost';
FLUSH PRIVILEGES;
EXIT;
```

Use a dedicated database user with the minimum privileges required. Do not use the root user in production.

---

## Redis Setup

Enable and start Redis:

```bash
sudo systemctl enable redis-server
sudo systemctl start redis-server
```

Verify it is running:

```bash
redis-cli ping
# Expected output: PONG
```

To restrict Redis to localhost only (recommended), confirm `/etc/redis/redis.conf` contains:

```
bind 127.0.0.1
```

Then restart: `sudo systemctl restart redis-server`.

---

## Application Setup

### Create the Application Directory

```bash
sudo mkdir -p /opt/django-htmx
sudo chown -R "$USER":"$USER" /opt/django-htmx
cd /opt/django-htmx
```

### Clone the Repository

```bash
git clone https://github.com/your-username/django-htmx.git .
```

### Create a Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### Install Python Dependencies

```bash
pip install --upgrade pip
pip install -r requirements/prod.txt
```

This installs the base dependencies plus Gunicorn.

### Build Tailwind CSS

If Node.js is available on the server:

```bash
npm install
npm run build
```

If Node.js is not available, generate `static/build/output.css` on your local machine and commit it, or copy it to the server before running `collectstatic`.

### Configure the Production `.env` File

```bash
cp .env.example .env
```

Edit `.env` with production values:

```env
DJANGO_SECRET_KEY=use-a-long-random-secret-here
DJANGO_DEBUG=false
DJANGO_ALLOWED_HOSTS=your-domain.com,www.your-domain.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://your-domain.com,https://www.your-domain.com

FERNET_KEY=generate-a-stable-fernet-key-here

DB_ENGINE=django.db.backends.mysql
DB_NAME=django_htmx
DB_USER=django_htmx
DB_PASSWORD=strong-db-password
DB_HOST=127.0.0.1
DB_PORT=3306
DB_CONN_MAX_AGE=60

REDIS_URL=redis://127.0.0.1:6379/0

MAIL_DRIVER=smtp
MAIL_FROM_EMAIL=no-reply@your-domain.com
SMTP_HOST=smtp.your-provider.com
SMTP_PORT=587
SMTP_USER=your-smtp-username
SMTP_PASSWORD=your-smtp-password
SMTP_USE_TLS=true
SMTP_USE_SSL=false

SECURE_HSTS_SECONDS=31536000
```

**Generating a `FERNET_KEY`:**

```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Store the output as `FERNET_KEY`. This key encrypts TOTP secrets. If it changes, existing 2FA secrets become unreadable.

**Generating a `DJANGO_SECRET_KEY`:**

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(64))"
```

Protect the `.env` file:

```bash
chmod 600 /opt/django-htmx/.env
```

### Run Migrations

```bash
source .venv/bin/activate
python manage.py migrate --settings=config.settings.prod
```

### Collect Static Files

```bash
python manage.py collectstatic --no-input --settings=config.settings.prod
```

This copies all static files into `STATIC_ROOT` (`staticfiles/`), from which Nginx serves them.

### Create a Superuser

```bash
python manage.py createsuperuser --settings=config.settings.prod
```

---

## Gunicorn Configuration

### Manual Start (Smoke Test)

Before setting up systemd, verify Gunicorn starts cleanly:

```bash
cd /opt/django-htmx
source .venv/bin/activate
gunicorn config.wsgi:application \
    --bind 127.0.0.1:8000 \
    --workers 3 \
    --timeout 60 \
    --access-logfile - \
    --error-logfile -
```

Visit `http://127.0.0.1:8000` from the server to confirm it responds. Press `Ctrl+C` to stop.

**Worker count guidance:** A common rule of thumb is `(2 × CPU cores) + 1`. For a 2-core VPS, use 5 workers.

---

## systemd Services

### Django / Gunicorn Service

Create `/etc/systemd/system/django-htmx-web.service`:

```ini
[Unit]
Description=Django HTMX Web App (Gunicorn)
After=network.target mysql.service redis-server.service

[Service]
User=www-data
Group=www-data
WorkingDirectory=/opt/django-htmx
EnvironmentFile=/opt/django-htmx/.env
Environment=DJANGO_SETTINGS_MODULE=config.settings.prod
ExecStart=/opt/django-htmx/.venv/bin/gunicorn config.wsgi:application \
    --bind 127.0.0.1:8000 \
    --workers 3 \
    --timeout 60 \
    --access-logfile /var/log/django-htmx/access.log \
    --error-logfile /var/log/django-htmx/error.log
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

### Celery Worker Service

Create `/etc/systemd/system/django-htmx-worker.service`:

```ini
[Unit]
Description=Django HTMX Celery Worker
After=network.target redis-server.service

[Service]
User=www-data
Group=www-data
WorkingDirectory=/opt/django-htmx
EnvironmentFile=/opt/django-htmx/.env
Environment=DJANGO_SETTINGS_MODULE=config.settings.prod
ExecStart=/opt/django-htmx/.venv/bin/celery \
    -A config worker \
    --loglevel=info \
    --logfile=/var/log/django-htmx/celery-worker.log
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

### Create Log Directory

```bash
sudo mkdir -p /var/log/django-htmx
sudo chown www-data:www-data /var/log/django-htmx
```

### Enable and Start Services

```bash
sudo systemctl daemon-reload
sudo systemctl enable django-htmx-web django-htmx-worker
sudo systemctl start django-htmx-web django-htmx-worker
```

### Check Service Status

```bash
sudo systemctl status django-htmx-web
sudo systemctl status django-htmx-worker
```

### View Logs

```bash
# Live web logs
sudo journalctl -u django-htmx-web -f

# Live worker logs
sudo journalctl -u django-htmx-worker -f

# Application access/error logs
tail -f /var/log/django-htmx/access.log
tail -f /var/log/django-htmx/error.log
```

---

## Nginx Reverse Proxy

### Initial HTTP Configuration

Create `/etc/nginx/sites-available/django-htmx`:

```nginx
server {
    listen 80;
    server_name your-domain.com www.your-domain.com;

    # Serve collected static files directly (no Django overhead)
    location /static/ {
        alias /opt/django-htmx/staticfiles/;
        expires 7d;
        add_header Cache-Control "public, max-age=604800, immutable";
    }

    # Proxy everything else to Gunicorn
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_http_version 1.1;
        proxy_read_timeout 60s;
        proxy_connect_timeout 10s;
    }
}
```

Enable the site:

```bash
sudo ln -s /etc/nginx/sites-available/django-htmx /etc/nginx/sites-enabled/django-htmx
sudo nginx -t
sudo systemctl reload nginx
```

---

## HTTPS with Let's Encrypt

Issue a TLS certificate using Certbot:

```bash
sudo certbot --nginx -d your-domain.com -d www.your-domain.com
```

Certbot automatically modifies the Nginx config to add HTTPS and set up HTTP → HTTPS redirect. Verify the renewal timer is active:

```bash
sudo systemctl status certbot.timer
```

After TLS is active, confirm:
1. The app loads over `https://`
2. HTTP requests redirect to HTTPS at the Nginx level
3. `SESSION_COOKIE_SECURE` and `CSRF_COOKIE_SECURE` are `True` (already set in `prod.py`)

---

## Email Setup (SMTP)

Set `MAIL_DRIVER=smtp` in `.env` and configure all `SMTP_*` variables.

**Common providers:**

| Provider            | `SMTP_HOST`              | `SMTP_PORT` | `SMTP_USE_TLS` |
|---------------------|--------------------------|-------------|----------------|
| AWS SES             | email-smtp.us-east-1.amazonaws.com | 587 | true |
| SendGrid            | smtp.sendgrid.net        | 587         | true           |
| Mailgun             | smtp.mailgun.org         | 587         | true           |
| Google Workspace    | smtp.gmail.com           | 587         | true           |
| Postfix (local MTA) | 127.0.0.1                | 25          | false          |

After configuring, send a test email:

```bash
source .venv/bin/activate
python manage.py shell --settings=config.settings.prod
```

```python
from django.core.mail import send_mail
send_mail('Test', 'Test body', 'noreply@your-domain.com', ['you@example.com'])
```

---

## Security Best Practices

### Settings (already enforced in `prod.py`)

| Setting                          | Value                              |
|----------------------------------|------------------------------------|
| `DEBUG`                          | `False`                            |
| `SECURE_SSL_REDIRECT`            | `True`                             |
| `SESSION_COOKIE_SECURE`          | `True`                             |
| `CSRF_COOKIE_SECURE`             | `True`                             |
| `SECURE_HSTS_SECONDS`            | `31536000`                         |
| `SECURE_HSTS_INCLUDE_SUBDOMAINS` | `True`                             |
| `SECURE_HSTS_PRELOAD`            | `True`                             |
| `X_FRAME_OPTIONS`                | `DENY`                             |
| `SECURE_CONTENT_TYPE_NOSNIFF`    | `True`                             |

### Additional Hardening

1. **Never commit `.env`** — add it to `.gitignore`
2. **Restrict `.env` permissions:** `chmod 600 /opt/django-htmx/.env`
3. **Firewall:** Allow only ports 80, 443, and 22. Block direct access to MySQL (3306) and Redis (6379) from the internet
4. **Database:** Use a least-privileged MySQL user (not `root`)
5. **Redis:** Bind to `127.0.0.1` only; set a password if the server is multi-tenant
6. **Keep packages updated:** `pip install --upgrade -r requirements/prod.txt` after pulling updates
7. **Review `DJANGO_ALLOWED_HOSTS`** — include only your actual domain names
8. **Set `DJANGO_CSRF_TRUSTED_ORIGINS`** to your HTTPS origin when behind Nginx

### Firewall (UFW Example)

```bash
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

---

## Deploying Updates

When you push new code to the server:

```bash
cd /opt/django-htmx
git pull origin main

source .venv/bin/activate
pip install -r requirements/prod.txt

# Rebuild CSS if templates or JS changed
npm run build
python manage.py collectstatic --no-input --settings=config.settings.prod

# Apply any new migrations
python manage.py migrate --settings=config.settings.prod

sudo systemctl restart django-htmx-web django-htmx-worker
```

If only Python source files changed (no new deps, no migrations, no static files), you can skip the corresponding steps and only restart the services.

---

## Scaling Considerations

### Horizontal Scaling (Multiple App Servers)

To run multiple Gunicorn instances behind a load balancer:

1. Use a shared MySQL instance reachable by all app servers
2. Use a shared Redis instance for Celery and Django's session backend
3. Move `django.contrib.sessions` to database or Redis-backed storage (default database sessions work out of the box with a shared DB)
4. Serve static files from a CDN or a dedicated Nginx node
5. Configure Nginx upstream blocks to balance across instances

### Celery Worker Scaling

Each Celery worker process handles tasks concurrently via threads or sub-processes. To handle higher email volume:

```bash
# Increase concurrency on a single node
celery -A config worker --concurrency=8 --loglevel=info

# Or run additional worker instances (each as a separate systemd service)
```

For periodic background tasks (e.g. expired token cleanup), add a Celery Beat scheduler:

```ini
# /etc/systemd/system/django-htmx-beat.service
[Unit]
Description=Django HTMX Celery Beat Scheduler
After=network.target redis-server.service

[Service]
User=www-data
Group=www-data
WorkingDirectory=/opt/django-htmx
EnvironmentFile=/opt/django-htmx/.env
Environment=DJANGO_SETTINGS_MODULE=config.settings.prod
ExecStart=/opt/django-htmx/.venv/bin/celery \
    -A config beat \
    --loglevel=info \
    --logfile=/var/log/django-htmx/celery-beat.log \
    --schedule=/opt/django-htmx/celerybeat-schedule
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

**Important:** Run exactly **one** Beat instance per deployment. Running multiple Beat schedulers causes duplicate task execution.

---

## Monitoring and Logging

### Log Locations

| Log                    | Path                                          |
|------------------------|-----------------------------------------------|
| Gunicorn access log    | `/var/log/django-htmx/access.log`             |
| Gunicorn error log     | `/var/log/django-htmx/error.log`              |
| Celery worker log      | `/var/log/django-htmx/celery-worker.log`      |
| Celery beat log        | `/var/log/django-htmx/celery-beat.log`        |
| Nginx access log       | `/var/log/nginx/access.log`                   |
| Nginx error log        | `/var/log/nginx/error.log`                    |
| MySQL error log        | `/var/log/mysql/error.log`                    |
| Django dev email log   | `logs/mail/` (only when `MAIL_DRIVER=log`)    |

### Basic Monitoring Checks

**Check all services are running:**
```bash
sudo systemctl status django-htmx-web django-htmx-worker nginx mysql redis-server
```

**Verify the app responds:**
```bash
curl -s -o /dev/null -w "%{http_code}" https://your-domain.com/
# Expected: 200
```

**Check Redis connectivity:**
```bash
redis-cli ping
# Expected: PONG
```

**Check MySQL connectivity:**
```bash
mysql -u django_htmx -p -e "SELECT 1;" django_htmx
```

**Monitor Celery task throughput:**
```bash
celery -A config inspect active
celery -A config inspect stats
```

### Log Rotation

Gunicorn and Celery logs can grow large. Set up logrotate:

Create `/etc/logrotate.d/django-htmx`:

```
/var/log/django-htmx/*.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    create 0640 www-data www-data
    postrotate
        systemctl reload django-htmx-web > /dev/null 2>&1 || true
    endscript
}
```

---

## Failure Modes

### App Process Down

**Symptom:** Nginx returns 502 Bad Gateway.

```bash
sudo systemctl status django-htmx-web
sudo journalctl -u django-htmx-web -n 50 --no-pager
```

Common causes: missing `.env`, failed migrations, import error in code.

### Celery Worker Down

**Symptoms:** Pages load normally, but emails are never delivered.

```bash
sudo systemctl status django-htmx-worker
sudo journalctl -u django-htmx-worker -n 50 --no-pager
```

Tasks accumulate in Redis until the worker restarts and processes them.

### Redis Down

**Symptoms:** Celery tasks fail to enqueue; sessions may be affected.

```bash
sudo systemctl status redis-server
redis-cli ping
```

Restart: `sudo systemctl restart redis-server`

### MySQL Down

**Symptoms:** All request that touch the database fail with a 500 error.

```bash
sudo systemctl status mysql
sudo journalctl -u mysql -n 50 --no-pager
```

Restart: `sudo systemctl restart mysql`

### SMTP Misconfigured

**Symptoms:** Workers process email tasks but delivery fails; error logs show SMTP connection errors.

Check worker logs and re-verify all `SMTP_*` values in `.env`. Send a test email from the Django shell.

---

## Backup Recommendations

At minimum, back up:

| Item                          | Method                                   |
|-------------------------------|------------------------------------------|
| MySQL database                | `mysqldump django_htmx > backup.sql`     |
| Production `.env`             | Store encrypted, outside the repo        |
| Nginx site config             | `/etc/nginx/sites-available/django-htmx` |
| systemd unit files            | `/etc/systemd/system/django-htmx-*.service` |
| Let's Encrypt certificates    | `/etc/letsencrypt/` (managed by Certbot) |

Automate MySQL backups with a cron job:

```bash
0 3 * * * mysqldump -u django_htmx -pPASSWORD django_htmx | gzip > /backups/db-$(date +\%F).sql.gz
```

---

## Production Readiness Checklist

Before going live, verify all of the following:

- [ ] `.env` is present at `/opt/django-htmx/.env` with production values
- [ ] `DJANGO_DEBUG=false`
- [ ] `DJANGO_ALLOWED_HOSTS` set to real domain names
- [ ] `DJANGO_CSRF_TRUSTED_ORIGINS` set to your HTTPS origin
- [ ] `FERNET_KEY` is a stable, generated key (not derived from SECRET_KEY)
- [ ] MySQL is reachable and migrations are applied
- [ ] Redis is reachable and bound to `127.0.0.1`
- [ ] `MAIL_DRIVER=smtp` with valid SMTP credentials
- [ ] Static files collected: `manage.py collectstatic`
- [ ] Tailwind CSS built: `npm run build`
- [ ] `django-htmx-web` service is running
- [ ] `django-htmx-worker` service is running
- [ ] Nginx is proxying traffic and serving `/static/` directly
- [ ] TLS certificate is installed and Certbot renewal is configured
- [ ] HTTP redirects to HTTPS
- [ ] Firewall allows only ports 22, 80, and 443
- [ ] A real registration email is received end-to-end
- [ ] A real password reset email is received end-to-end
- [ ] Log directory `/var/log/django-htmx/` is writable by `www-data`

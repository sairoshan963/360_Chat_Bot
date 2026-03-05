# Gamyam 360° Feedback — Django Edition

A full-stack 360° performance feedback platform built with **Django REST Framework** (backend) and **React + Vite** (frontend), deployed via **Docker Compose**.

**Live (HTTPS):** When Cloudflare quick tunnel is running on the server, the app is available at a URL like `https://meetings-colored-nurses-genuine.trycloudflare.com` — see [Cloudflare Tunnel (HTTPS)](#cloudflare-tunnel-https) for how to get the current URL.

---

## Table of Contents

- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Ports & Access URLs](#ports--access-urls)
- [Cloudflare Tunnel (HTTPS)](#cloudflare-tunnel-https)
- [Local Development Setup](#local-development-setup)
- [Server Deployment (First Time)](#server-deployment-first-time)
- [Deploy Updates (After First Setup)](#deploy-updates-after-first-setup)
- [Environment Variables](#environment-variables)
- [Default Credentials](#default-credentials)
- [Useful Commands](#useful-commands)
- [Google OAuth Setup](#google-oauth-setup)
- [Troubleshooting](#troubleshooting)

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Django 6 + Django REST Framework |
| Frontend | React 18 + Vite + Ant Design |
| Database | PostgreSQL 16 |
| Cache / Queue | Redis 7 |
| Task Queue | Celery + Celery Beat |
| Web Server | Nginx (frontend) + Gunicorn (backend) |
| Containerization | Docker + Docker Compose |
| Deployment | Ansible |

---

## Project Structure

```
360_Django/
├── backend/                  # Django backend
│   ├── apps/                 # Django apps (auth, users, cycles, etc.)
│   ├── config/               # Django settings (base, local, production, test)
│   ├── shared/               # Shared utilities (email, permissions, health)
│   ├── requirements.txt      # Python dependencies
│   ├── Dockerfile            # Multi-stage Docker build
│   ├── .env.example          # Example environment variables
│   └── .env.docker           # Production secrets (NOT in GitHub — stays on server)
├── frontend/                 # React frontend
│   ├── src/                  # React source code
│   ├── nginx.conf            # Nginx config (proxies /api/ to backend)
│   ├── Dockerfile            # Multi-stage Docker build
│   └── .env                  # Frontend env (VITE_USE_MOCK, VITE_GOOGLE_CLIENT_ID)
├── ansible/
│   ├── inventory.ini         # Server IP and SSH user
│   └── playbook.yml          # Full deploy automation
├── docker-compose.yml        # All 6 services wired together
├── deploy.sh                 # One-command deploy script
└── Makefile                  # Dev shortcuts
```

---

## Ports & Access URLs

### Production Server (`164.52.215.113`)

| Service | Host Port | URL |
|---|---|---|
| **Frontend (React)** | `5173` | `http://164.52.215.113:5173/` |
| **Backend (Django API)** | `8000` | `http://164.52.215.113:8000/api/v1/` |
| **PostgreSQL** | `5433` | `164.52.215.113:5433` |
| **Redis** | `6380` | `164.52.215.113:6380` |
| **API Docs (Swagger)** | `8000` | `http://164.52.215.113:8000/api/docs/` |

> **Note:** Users only need port `5173`. All `/api/` calls are automatically proxied by Nginx to the backend on port `8000`. Ports `5433` and `6380` are for DB access only.

> **Note:** Port `5433` (not `5432`) is used for Postgres to avoid conflict with the Node.js project running on the same server on port `5432`.

### Node.js Project (running in parallel on same server)

| Service | Port |
|---|---|
| Node.js Frontend | `80` |
| Node.js Backend | `5000` |
| Node.js Postgres | `5432` |

### Local Development

| Service | URL |
|---|---|
| Frontend (Vite dev server) | `http://localhost:5173/` |
| Backend (Django runserver) | `http://localhost:8000/` |
| API Docs | `http://localhost:8000/api/docs/` |

---

## Cloudflare Tunnel (HTTPS)

You can expose the app over **HTTPS** for free using [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/) (no SSL certs or port forwarding needed).

### Quick tunnel (no Cloudflare account)

On the server, run:

```bash
# Frontend (what users open in the browser)
cloudflared tunnel --url http://localhost:5173

# Backend API (optional; frontend already proxies /api/ via Nginx)
cloudflared tunnel --url http://localhost:8000
```

Each command prints a **temporary HTTPS URL** like:

| Service | Example URL (changes on restart) |
|---|---|
| **Frontend** | `https://something-random.trycloudflare.com` |
| **Backend** | `https://another-random.trycloudflare.com` |

> **Note:** These `*.trycloudflare.com` URLs are **temporary** — they change every time the tunnel process restarts. Good for demos and testing. For a **permanent** HTTPS URL, use a [named tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/tunnel-guide/) with your own domain (e.g. `https://360.gamyam.co`).

### Example live URLs (for reference)

When the quick tunnel is running on the current server, you may see URLs similar to:

- **App (HTTPS):** `https://meetings-colored-nurses-genuine.trycloudflare.com` *(example; replace with the URL printed when you run `cloudflared tunnel --url http://localhost:5173`)*
- **API (HTTPS):** `https://olive-puzzles-flooring-presents.trycloudflare.com` *(example; optional)*

If you use the frontend Cloudflare URL, add it to **Google OAuth → Authorized redirect URIs** in Google Cloud Console, e.g.  
`https://<your-tunnel-hostname>.trycloudflare.com/auth/callback`

---

## Local Development Setup

### Prerequisites

- Python 3.12+
- Node.js 20+
- PostgreSQL (local) or Docker

### 1. Backend setup

```bash
cd backend

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy and fill in environment variables
cp .env.example .env
# Edit .env with your local DB credentials

# Run migrations
python manage.py migrate

# Create super admin
python manage.py init_superadmin

# (Optional) Seed demo data
python manage.py seed_users
python manage.py seed_cycle
python manage.py seed_demo

# Start dev server
python manage.py runserver
```

### 2. Frontend setup

```bash
cd frontend

# Install dependencies
npm install

# Start dev server (proxies /api/ to localhost:8000 automatically)
npm run dev
```

### 3. Or run everything with Docker locally

```bash
# From project root
docker compose up -d --build
```

---

## Server Deployment (First Time)

> Do this **once** when setting up a new server.

### Prerequisites on server

- Ubuntu 22.04+
- Docker + Docker Compose installed
- SSH access as `root`

### Step 1 — SSH into the server

```bash
ssh root@164.52.215.113
```

### Step 2 — Clone the repo

```bash
git clone https://github.com/sairoshan963/360-feedback-django-FS.git /opt/360-django
cd /opt/360-django
```

### Step 3 — Create the production secrets file

```bash
cp backend/.env.example backend/.env.docker
nano backend/.env.docker
```

Fill in the following values (see [Environment Variables](#environment-variables)):

```env
SECRET_KEY=<generate a long random string>
ALLOWED_HOSTS=<your-server-ip>,localhost
CORS_ALLOWED_ORIGINS=http://<your-server-ip>:5173
FRONTEND_URL=http://<your-server-ip>:5173
DB_PASSWORD=<strong-password>
GOOGLE_CLIENT_ID=<from Google Cloud Console>
GOOGLE_CLIENT_SECRET=<from Google Cloud Console>
EMAIL_HOST_USER=<your-gmail>
EMAIL_HOST_PASSWORD=<gmail-app-password>
SUPERADMIN_EMAIL=admin@yourdomain.com
SUPERADMIN_PASSWORD=<strong-password>
```

### Step 4 — Start all containers

```bash
cd /opt/360-django
VITE_GOOGLE_CLIENT_ID=<your-google-client-id> docker compose up -d --build
```

### Step 5 — Verify

```bash
docker ps
curl http://localhost:5173/        # Should return 200
curl http://localhost:8000/health/ # Should return OK
```

---

## Deploy Updates (After First Setup)

> Every time you push code changes to GitHub, run this to update the server.

### From your laptop (one command)

```bash
# Make sure ansible is installed
pip install ansible

# Deploy
./deploy.sh
```

### Or manually

```bash
ansible-playbook -i ansible/inventory.ini ansible/playbook.yml
```

### What the deploy does automatically

1. SSHes into server
2. `git pull` latest code from GitHub
3. `docker compose up -d --build` (rebuilds changed containers)
4. Health checks frontend and backend
5. Prints final status

### Manual server update (without Ansible)

```bash
ssh root@164.52.215.113
cd /opt/360-django
git pull
VITE_GOOGLE_CLIENT_ID=<your-client-id> docker compose up -d --build
```

---

## Environment Variables

### `backend/.env.docker` (production — stays on server, never in GitHub)

| Variable | Description | Example |
|---|---|---|
| `SECRET_KEY` | Django secret key (long random string) | `abc123...` |
| `DEBUG` | Debug mode | `False` |
| `ALLOWED_HOSTS` | Comma-separated allowed hosts | `164.52.215.113,localhost` |
| `DB_NAME` | PostgreSQL database name | `gamyam_360_django` |
| `DB_USER` | PostgreSQL username | `gamyam_user` |
| `DB_PASSWORD` | PostgreSQL password | `StrongPass@123` |
| `DB_HOST` | DB host (use `db` for Docker) | `db` |
| `REDIS_URL` | Redis URL | `redis://redis:6379/0` |
| `GOOGLE_CLIENT_ID` | Google OAuth client ID | `581506...apps.googleusercontent.com` |
| `GOOGLE_CLIENT_SECRET` | Google OAuth client secret | `GOCSPX-...` |
| `EMAIL_HOST_USER` | Gmail address for sending emails | `you@gmail.com` |
| `EMAIL_HOST_PASSWORD` | Gmail App Password (not regular password) | `abcd efgh ijkl mnop` |
| `ENABLE_EMAIL_NOTIFICATIONS` | `true` = send real emails; `false` = no delivery (console only, for testing) | `true` or `false` |
| `FRONTEND_URL` | Frontend URL (used in OAuth redirect + emails) | `http://164.52.215.113:5173` |
| `SUPERADMIN_EMAIL` | Auto-created admin email | `admin@gamyam.com` |
| `SUPERADMIN_PASSWORD` | Auto-created admin password | `Admin@123` |
| `CORS_ALLOWED_ORIGINS` | Allowed CORS origins | `http://164.52.215.113:5173` |
| `JWT_EXPIRY_DAYS` | JWT access token lifetime in days | `1` |
| `TIME_ZONE` | App timezone | `Asia/Kolkata` |

### `frontend/.env` (safe to commit — no secrets)

| Variable | Description |
|---|---|
| `VITE_USE_MOCK` | `false` for real backend, `true` for mock data |
| `VITE_API_BASE_URL` | Leave empty for local dev (Vite proxy handles it) |
| `VITE_GOOGLE_CLIENT_ID` | Google OAuth client ID (public, safe in frontend) |

---

## Default Credentials

| Role | Email | Password |
|---|---|---|
| Super Admin | `admin@gamyam.com` | `Admin@123` |

> Change these immediately after first login in production.

---

## Useful Commands

### Docker

```bash
# View all running containers
docker ps

# View logs for a service
docker logs 360-django-backend-1 -f
docker logs 360-django-frontend-1 -f
docker logs 360-django-celery_worker-1 -f

# Restart a single service
docker compose restart backend

# Stop everything
docker compose down

# Full rebuild
VITE_GOOGLE_CLIENT_ID=<id> docker compose up -d --build
```

### Django Management (via Makefile)

```bash
# From project root
make migrate          # Run migrations
make seed             # Seed users and departments
make seed-cycle       # Create a demo cycle
make seed-demo        # Create 4 demo cycles in various states
make test             # Run all tests
make shell            # Django shell
make superuser        # Create superuser interactively
```

### Run Tests

```bash
cd backend
source venv/bin/activate
pytest                          # All tests
pytest apps/auth_app/tests.py   # Specific app
pytest -v                       # Verbose
```

---

## Google OAuth Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. **APIs & Services → Credentials → Create OAuth 2.0 Client ID**
3. Application type: **Web application**
4. Add **Authorized redirect URIs**:
   ```
   http://localhost:5173/auth/callback        ← local dev
   http://164.52.215.113:5173/auth/callback   ← production server
   https://your-domain.com/auth/callback      ← if using custom domain
   ```
5. Copy **Client ID** and **Client Secret** into:
   - `backend/.env.docker` → `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`
   - `frontend/.env` → `VITE_GOOGLE_CLIENT_ID`

---

## Troubleshooting

### Docker: "permission denied while trying to connect to the Docker API"

**Symptom:** `permission denied while trying to connect to the docker API at unix:///var/run/docker.sock`

**Fix:** Add your user to the `docker` group so you can run Docker without `sudo`:

```bash
sudo usermod -aG docker $USER
```

Then log out and log back in (or run `newgrp docker` in the same terminal). After that, `docker compose up -d` will work without sudo.

**Quick workaround:** Run with sudo: `sudo docker compose up -d`

### Backend won't start — DB authentication failed

**Symptom:** `FATAL: password authentication failed for user "gamyam_user"`

**Fix:** The `DB_PASSWORD` in `backend/.env.docker` must match what Postgres was initialized with. If you changed the password, delete the volume and restart:

```bash
docker compose down -v   # WARNING: deletes all data
docker compose up -d --build
```

### Frontend shows blank page

**Check:**
```bash
docker logs 360-django-frontend-1
```
Usually means Nginx can't reach the backend. Verify `360-django-backend-1` is running.

### Google OAuth not working

- Make sure `http://<your-url>/auth/callback` is in Google Cloud Console redirect URIs
- Make sure `FRONTEND_URL` in `backend/.env.docker` matches the URL users are accessing
- Make sure `VITE_GOOGLE_CLIENT_ID` matches `GOOGLE_CLIENT_ID` in backend

### Port already in use

The Django project uses non-standard ports to avoid conflicts with the Node.js project:
- `5433` instead of `5432` for Postgres
- `6380` instead of `6379` for Redis
- `5173` instead of `80` for frontend

If you're deploying **without** the Node.js project, you can change these back to standard ports in `docker-compose.yml`.

### Celery Beat keeps restarting

Usually a DB connection issue on startup. Wait for DB to be healthy first:
```bash
docker compose restart celery_beat
```

---

## Architecture Overview

```
Internet
    │
    ▼
Cloudflare Tunnel (optional — free HTTPS)
    │
    ▼
Nginx (frontend container — port 5173)
    │  serves React SPA
    │  proxies /api/ and /media/ →
    ▼
Gunicorn (backend container — port 8000)
    │
    ├──► PostgreSQL (db container — port 5433)
    ├──► Redis (redis container — port 6380)
    └──► Celery Worker + Beat (background tasks)
```

---

## Server Info

| Detail | Value |
|---|---|
| Server IP | `164.52.215.113` |
| SSH User | `root` |
| App Path | `/opt/360-django` |
| GitHub Repo | [sairoshan963/360-feedback-django-FS](https://github.com/sairoshan963/360-feedback-django-FS) |
| Node.js App | Running in parallel on ports `80` / `5000` / `5432` |

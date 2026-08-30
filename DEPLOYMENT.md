# 🚢 Production Deployment Guide

This guide details how to deploy the **LinkedIn Profile Viewer REST API** to production environments using **Docker**, **AWS EC2 / DigitalOcean VPS**, or **Cloud PaaS (Render / Railway / Fly.io)**.

---

## Option 1: Docker & Docker Compose (Recommended)

Docker provides an isolated environment pre-configured with Playwright Chromium & system libraries.

### 1. Build and Run Container
```bash
docker-compose up -d --build
```

### 2. Verify Container Health
```bash
docker-compose ps
curl http://localhost:8000/health
```

### 3. View Logs
```bash
docker-compose logs -f
```

---

## Option 2: Linux VPS (Ubuntu / Debian / AWS EC2)

Deploy directly onto a Linux Virtual Private Server using `systemd` and `uvicorn`.

### 1. System Dependencies
```bash
sudo apt update && sudo apt install -y python3 python3-pip python3-venv git
```

### 2. Install Playwright System Dependencies
```bash
pip install -r requirements.txt
playwright install-deps chromium
playwright install chromium
```

### 3. Create Systemd Service File
Create `/etc/systemd/system/linkedin_api.service`:

```ini
[Unit]
Description=LinkedIn Profile Viewer REST API Server
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/linkedin_profile_viewer
ExecStart=/home/ubuntu/linkedin_profile_viewer/.venv/bin/python3 api_server.py
Restart=always
RestartSec=5
EnvironmentFile=/home/ubuntu/linkedin_profile_viewer/.env

[Install]
WantedBy=multi-user.target
```

### 4. Enable and Start Service
```bash
sudo systemctl daemon-reload
sudo systemctl enable linkedin_api
sudo systemctl start linkedin_api
sudo systemctl status linkedin_api
```

---

## Option 3: Cloud PaaS (Render / Railway / Fly.io)

### Render.com
1. Connect your GitHub repository to Render.
2. Select **Web Service** and choose **Docker** as the Runtime environment.
3. Add Environment Variables under **Environment**:
   - `LINKEDIN_EMAIL`
   - `LINKEDIN_PASSWORD`
   - `GEMINI_API_KEY`
   - `GEMINI_MODEL` = `gemini-3.6-flash`
4. Deploy! Render will build using the included `Dockerfile`.

---

## Option 4: Google Cloud Run Deployment

Google Cloud Run is an excellent serverless platform for deploying containerized Playwright applications.

### 1. Requirements for Cloud Run:
- **Memory**: Set to at least **2 GiB** (`--memory 2GiB`) so Playwright Chromium has enough RAM.
- **CPU**: Set to **2 vCPUs** (`--cpu 2`).
- **CPU Allocation**: Use `--no-cpu-throttling` (CPU always allocated) so Playwright browser operations don't freeze between HTTP requests.
- **Timeout**: Set `--timeout 300s` (5 minutes).

### 2. Deploy using `gcloud` CLI:
Run this single command from your repository directory:

```bash
gcloud run deploy linkedin-profile-viewer \
  --source . \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 2GiB \
  --cpu 2 \
  --no-cpu-throttling \
  --timeout 300s \
  --set-env-vars LINKEDIN_EMAIL="your_email@example.com",LINKEDIN_PASSWORD="your_password",GEMINI_API_KEY="your_api_key",GEMINI_MODEL="gemini-3.6-flash"
```

### 3. Deploy via Google Cloud Console:
1. Go to **Google Cloud Console > Cloud Run > Create Service**.
2. Select **Continuously deploy from a repository** (or upload your Dockerfile).
3. Under **Container(s), Volumes, Networking, Security**:
   - **Memory**: Select `2 GiB`
   - **CPU**: Select `2`
   - **CPU allocation**: Check `CPU is always allocated`
   - **Container port**: Set to `8000`
4. Under **Variables & Secrets**, add:
   - `LINKEDIN_EMAIL`
   - `LINKEDIN_PASSWORD`
   - `GEMINI_API_KEY`
   - `GEMINI_MODEL` = `gemini-3.6-flash`
5. Click **Create** to deploy.

---

## 🔒 Session & Credential Security

- **Session Persistence**: On Cloud Run, `api_server.py` will automatically perform automated login on container startup using `LINKEDIN_EMAIL` and `LINKEDIN_PASSWORD` from environment variables and save `linkedin_session.json` in container RAM.
- **Environment Variables**: Use Cloud Run Secrets Manager or Environment Variables for sensitive credentials.


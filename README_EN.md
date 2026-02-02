# TG-SignPulse

[中文说明](README.md)

TG-SignPulse is an automation management panel for Telegram. It provides multi-account management, auto check-ins, scheduled tasks, and button interactions, offering an efficient and intelligent automation workflow.

> AI-assisted: This project integrates AI helpers, and some logic was co-developed with AI.

## ✨ Features

- Multi-account management and scheduling
- Automated check-ins, scheduled messages, and button clicks
- Time randomization to reduce risk
- Modern Next.js-based admin UI
- AI helpers (image option recognition, calculation replies)
- Docker-first deployment

## Quick Start

Default credentials:

- Username: `admin`
- Password: `admin123`

### Docker Run

```bash
docker run -d \
  --name tg-signpulse \
  --restart unless-stopped \
  -p 8080:8080 \
  -v $(pwd)/data:/data \
  -e PORT=8080 \
  -e TZ=Asia/Shanghai \
  # Optional: Telegram API (recommended)
  # -e TG_API_ID=123456 \
  # -e TG_API_HASH=xxxxxxxxxxxxxxxx \
  # Optional: arm64 recommended no-SQLite session mode
  # -e TG_SESSION_MODE=string \
  # -e TG_SESSION_NO_UPDATES=1 \
  # -e TG_GLOBAL_CONCURRENCY=1 \
  # Optional: panel 2FA tolerance window (default 0)
  # -e APP_TOTP_VALID_WINDOW=1 \
  # Optional: backend secret key
  # -e APP_SECRET_KEY=your_secret_key \
  # Optional: AI settings
  # -e OPENAI_API_KEY=sk-xxxx \
  # -e OPENAI_BASE_URL=https://api.openai.com/v1 \
  # -e OPENAI_MODEL=gpt-4o \
  ghcr.io/akasls/tg-signpulse:latest
```

### Docker Compose

```yaml
services:
  app:
    image: ghcr.io/akasls/tg-signpulse:latest
    container_name: tg-signpulse
    ports:
      - "8080:8080"
    volumes:
      - ./data:/data
    environment:
      - PORT=8080
      - TZ=Asia/Shanghai
      # Optional: arm64 recommended no-SQLite session mode
      # - TG_SESSION_MODE=string
      # - TG_SESSION_NO_UPDATES=1
      # - TG_GLOBAL_CONCURRENCY=1
      # Optional: panel 2FA tolerance window (default 0)
      # - APP_TOTP_VALID_WINDOW=1
      # Optional: backend secret key
      # - APP_SECRET_KEY=your_secret_key
    restart: unless-stopped
```

### Zeabur Deployment

- Create project: Create a new project in the console.
- Service config: Choose Docker image and fill in:
  - Image: `ghcr.io/akasls/tg-signpulse:latest`
  - Env vars: `TZ=Asia/Shanghai` (arm64 recommended: `TG_SESSION_MODE=string`, `TG_SESSION_NO_UPDATES=1`, `TG_GLOBAL_CONCURRENCY=1`)
  - Port: `8080`, type `HTTP`
  - Volume: ID `data`, path `/data`
- Deploy: Click deploy.
- Domain: After deployment, click “Add domain” in service details to get a public URL.

## Optional Environment Variables

All are optional; when unset, behavior matches previous versions.

- `TG_SESSION_MODE`: `file` (default) or `string` (session_string + in_memory; arm64 recommended).
- `TG_SESSION_NO_UPDATES`: set `1` to enable `no_updates` in `string` mode (default `0`).
- `TG_GLOBAL_CONCURRENCY`: global concurrency limit (default `1`, arm64 recommended to keep `1`).
- `APP_TOTP_VALID_WINDOW`: panel 2FA tolerance window (default `0`, set `1` to allow ±1 time step).
- `PORT`: listen port (default `8080`, read by container command).

## Session Migration (Optional)

Export session_string from existing `.session` files (does not print session_string):

```bash
python -m tools.migrate_session
# or
python tools/migrate_session.py --account your_account
```

## Health Checks

- `GET /healthz`: instant 200, no external dependencies
- `GET /readyz`: returns 200 after background initialization

## Multi-arch Build

```bash
docker buildx build --platform linux/amd64,linux/arm64 -t ghcr.io/akasls/tg-signpulse:latest --push .
```

## Project Structure

```
backend/      # FastAPI backend and scheduler
tg_signer/    # Pyrogram-based automation core
frontend/     # Next.js admin panel
```

## Release Notes

### 2026-01-29

- Concurrency optimization: account-level shared locks to prevent `database is locked`.
- Write protection: avoid concurrent login/task/chat refresh conflicts.
- Login robustness improved.
- Config parsing for TG API, secrets, and AI envs improved.
- UI improvements (account name length limit, task modal time range).

### 2026-02-02

- Added `TG_SESSION_MODE=string`: session_string + in_memory to avoid `.session` SQLite locks (default remains file mode).
- Added migration script `python -m tools.migrate_session` (no secret output).
- Added global concurrency limit `TG_GLOBAL_CONCURRENCY` (default 1) and per-account serialization.
- Startup work moved out of startup hook; `/healthz` responds in ~1–2 seconds; added `/readyz`.
- Added panel 2FA tolerance window `APP_TOTP_VALID_WINDOW` (default 0, no behavior change).

## Acknowledgements

This project is based on and extended from the original project:
- tg-signer by amchii

Tech stack: FastAPI, Uvicorn, APScheduler, Pyrogram/Kurigram, Next.js, Tailwind CSS, OpenAI SDK.

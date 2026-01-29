# TG-SignPulse

[中文说明](README.md)

TG-SignPulse is a Telegram automation and management panel for multi-account sign-ins, scheduled tasks, and button clicks.

This project includes AI-assisted features and is developed with AI assistance.

## Features

- Multi-account tasks and scheduling
- Sign-in automation, message sending, button click flows
- Time range randomization to reduce risk
- Web UI for management (Next.js)
- Docker-first deployment
- Optional AI helpers: image option selection, calculation reply

## Deployment
Default account: admin  Default password: admin123
### Docker Run

```bash
docker run -d \
  --name tg-signpulse \
  --restart unless-stopped \
  -p 8080:8080 \
  -v $(pwd)/data:/data \
  -e TZ=Asia/Shanghai \
  # Optional: Telegram API (recommended to use your own)
  # -e TG_API_ID=123456 \
  # -e TG_API_HASH=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx \
  # Optional: backend secret key
  # -e APP_SECRET_KEY=your_secret \
  # Optional: AI features
  # -e OPENAI_API_KEY=sk-xxxxxxxx \
  # -e OPENAI_BASE_URL=https://api.openai.com/v1 \
  # -e OPENAI_MODEL=gpt-4.1 \
  ghcr.io/akasls/tg-signpulse:latest
```

- Data persistence: `./data` -> `/data`
- Open: `http://localhost:8080`

### Docker Compose

```yaml
version: "3.8"
services:
  app:
    image: ghcr.io/akasls/tg-signpulse:latest
    container_name: tg-signpulse
    ports:
      - "8080:8080"
    volumes:
      - ./data:/data
    environment:
      - TZ=Asia/Shanghai
    restart: unless-stopped
```

```bash
docker compose up -d
```

### Zeabur

<a href="https://zeabur.com/referral?referralCode=akasls&utm_source=7764877&utm_campaign=oss"><img src=https://zeabur.com/deployed-on-zeabur-dark.svg alt="Deployed on Zeabur"/></a>

1. Create a new project and deploy from GitHub.  
2. Add a persistent volume at `/data` (required).  
3. Ensure port `8080` is exposed.

## Optional Environment Variables
Note: These can also be set in the admin panel ?Settings?. Environment variables take precedence.
Empty values are ignored; the app falls back to panel/default settings if a value is missing or invalid.

- `TG_API_ID` / `TG_API_HASH`: Telegram API credentials (optional, recommended to use your own)

- `APP_SECRET_KEY`: backend secret key (optional, for extra security)
- `OPENAI_API_KEY`: required only if you enable AI features (optional)
- `OPENAI_BASE_URL`: custom OpenAI API base URL (optional)
- `OPENAI_MODEL`: custom model name (optional)

## Project Structure

```
backend/      # FastAPI backend, scheduler, services
tg_signer/    # Telegram automation core (Pyrogram)
frontend/     # Next.js admin panel
```

## Acknowledgements

This project is based on and extended from the original project:
- `tg-signer` by amchii  
  https://github.com/amchii/tg-signer

Thanks to:
- FastAPI, Uvicorn
- APScheduler
- Pyrogram / Kurigram
- Next.js, Tailwind CSS
- OpenAI SDK and related AI tooling

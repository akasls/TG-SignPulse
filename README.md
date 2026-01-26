# TG-SignPulse

TG-SignPulse is a Telegram automation and management panel for multi-account sign-ins, scheduled tasks, and button clicks.  
TG-SignPulse 是一个 Telegram 自动化与管理面板，面向多账号签到、定时任务与按钮点击。

This project includes AI-assisted features and is developed with AI assistance.  
本项目包含 AI 辅助能力，并由 AI 参与开发。

## Features | 功能特性

- Multi-account tasks and scheduling | 多账号任务与定时调度
- Sign-in automation, message sending, button click flows | 签到自动化、消息发送、按钮点击流程
- Time range randomization to reduce risk | 时间段随机执行，降低风险
- Web UI for management (Next.js) | 现代化管理面板
- Docker-first deployment | 原生 Docker 部署
- Optional AI helpers: image option selection, calculation reply | 可选 AI 辅助：图片选项识别、计算题回复

## Deployment | 部署

### Docker Run

```bash
docker run -d \
  --name tg-signpulse \
  --restart unless-stopped \
  -p 8080:8080 \
  -v $(pwd)/data:/data \
  -e TZ=Asia/Shanghai \
  ghcr.io/akasls/tg-signpulse:latest
```

- Data persistence: `./data` -> `/data` | 数据持久化：`./data` -> `/data`
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

1. Create a new project and deploy from GitHub.  
2. Add a persistent volume at `/data` (required).  
3. Ensure port `8080` is exposed.

## Project Structure | 项目结构

```
backend/      # FastAPI backend, scheduler, services
tg_signer/    # Telegram automation core (Pyrogram)
frontend/     # Next.js admin panel
docker/       # Additional docker assets (optional)
scripts/      # Utility scripts
tests/        # Tests
```

## Acknowledgements | 致谢

- FastAPI, Uvicorn
- APScheduler
- Pyrogram / Kurigram
- Next.js, Tailwind CSS
- OpenAI SDK and related AI tooling

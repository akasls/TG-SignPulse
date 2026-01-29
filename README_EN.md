# TG-SignPulse

TG-SignPulse is a powerful Telegram automation and management panel designed for multi-account check-ins, scheduled tasks, and interactive button automation.

> 💡 **AI-Enhanced**: This project features AI-assisted capabilities and is built with the collaboration of AI.

## ✨ Key Features

* **Multi-Account Management**: Centralized dashboard to manage and schedule tasks across multiple accounts.
* **Automated Workflows**: Streamlined processes for auto check-ins, message broadcasting, and button-click automation.
* **Risk Mitigation**: Execution with randomized time intervals to minimize account suspension risks.
* **Modern UI**: A responsive and intuitive management panel built with **Next.js**.
* **AI Power-ups**: Integrated AI for OCR (image option recognition) and automated math problem solving.
* **Docker Ready**: Native support for Docker and Docker Compose for seamless deployment.

## 🚀 Quick Start

**Default Credentials**:

* **Username**: `admin`
* **Password**: `admin123`

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
      - TZ=Asia/Shanghai
    restart: unless-stopped

```

## 📂 Project Structure

* `backend/`: FastAPI backend and task scheduler.
* `tg_signer/`: Telegram automation core based on Pyrogram.
* `frontend/`: Next.js-based management dashboard.

## 🔄 Recent Updates

### 2026-01-29

* **Concurrency Fix**: Added account-level shared locks to resolve "database is locked" issues.
* **Write Protection**: Prevented concurrent write conflicts during login, tasks, or chat refreshes for the same account.
* **Enhanced Login**: Strengthened the authentication and login workflow.
* **Logic Optimization**: Improved parsing for TG API, Secret, and AI environment variables.
* **UI Tweaks**: Added character limits for account inputs and aligned time ranges in task modals.

## 🤝 Acknowledgments

This project is a refactored and extended version of:

* **tg-signer** by [amchii](https://github.com/amchii/tg-signer)

**Powered by:**
FastAPI, APScheduler, Pyrogram/Kurigram, Next.js, Tailwind CSS, OpenAI SDK.

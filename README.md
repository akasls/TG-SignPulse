# TG-SignPulse

[English README](README_EN.md)

TG-SignPulse 是一个 Telegram 自动化与管理面板，面向多账号签到、定时任务与按钮点击。

本项目包含 AI 辅助能力，并由 AI 参与开发。

## 功能特性

- 多账号任务与定时调度
- 签到自动化、消息发送、按钮点击流程
- 时间段随机执行，降低风险
- 现代化管理面板（Next.js）
- 原生 Docker 部署
- 可选 AI 辅助：图片选项识别、计算题回复

## 部署

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

- 数据持久化：`./data` -> `/data`
- 访问地址：`http://localhost:8080`

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

1. 在 Zeabur 控制台创建新项目并从 GitHub 部署。  
2. 挂载持久化目录到 `/data`（必需）。  
3. 确保端口为 `8080`。

## ??????

- `TG_API_ID` / `TG_API_HASH`?Telegram API ???????????????

- `APP_SECRET_KEY`?????????????????
- `OPENAI_API_KEY`??? AI ??????????
- `OPENAI_BASE_URL`???? OpenAI API ??????
- `OPENAI_MODEL`????????????

## 项目结构

```
backend/      # FastAPI 后端与调度器
tg_signer/    # Telegram 自动化核心（Pyrogram）
frontend/     # Next.js 管理面板
```

## 致谢

本项目基于原项目改造与扩展，特别感谢：
- 原项目：`tg-signer` by amchii  
  https://github.com/amchii/tg-signer

并感谢以下依赖与社区：
- FastAPI, Uvicorn
- APScheduler
- Pyrogram / Kurigram
- Next.js, Tailwind CSS
- OpenAI SDK and related AI tooling

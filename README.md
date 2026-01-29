# TG-SignPulse

[English README](https://www.google.com/search?q=README_EN.md)

**TG-SignPulse** 是一款专为 Telegram 设计的自动化管理面板。它集成了多账号管理、自动签到、定时任务及按钮交互等功能，旨在为用户提供高效、智能的 Telegram 自动化方案。

> 💡 **AI 驱动**：本项目深度集成 AI 辅助能力，部分代码及逻辑由 AI 协作开发。

## ✨ 功能特性

* **多账号管理**：支持多账号同时在线，统一调度自动化任务。
* **全自动工作流**：涵盖自动签到、定时消息发送、模拟点击按钮等核心流程。
* **安全策略**：内置任务时间随机化机制，有效降低账号风控风险。
* **现代化 UI**：基于 **Next.js** 构建的响应式管理后台，简洁易用。
* **AI 辅助增强**：集成 AI 视觉与逻辑处理，支持图片选项识别及自动计算题解答。
* **容器化部署**：支持原生 Docker 及 Docker Compose，实现一键部署与迁移。

## 🚀 快速开始

**默认凭据**：

* **账号**: `admin`
* **密码**: `admin123`

### 使用 Docker Run

```bash
docker run -d \
  --name tg-signpulse \
  --restart unless-stopped \
  -p 8080:8080 \
  -v $(pwd)/data:/data \
  -e TZ=Asia/Shanghai \
  # 可选：配置 Telegram API 以获得更佳稳定性
  # -e TG_API_ID=123456 \
  # -e TG_API_HASH=xxxxxxxxxxxxxxxx \
  # 可选：自定义后端密钥
  # -e APP_SECRET_KEY=your_secret_key \
  # 可选：AI 接入 (OpenAI 或兼容接口)
  # -e OPENAI_API_KEY=sk-xxxx \
  # -e OPENAI_BASE_URL=https://api.openai.com/v1 \
  # -e OPENAI_MODEL=gpt-4o \
  ghcr.io/akasls/tg-signpulse:latest

```

### 使用 Docker Compose

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
      - APP_SECRET_KEY=pTyOBjWYarWrwThf9uXX81GR64mAEEZH
    restart: unless-stopped

```

### Zeabur 部署

1. 在 Zeabur 控制台创建项目并选择从 GitHub 部署。
2. **务必**挂载持久化目录到 `/data`。
3. 暴露端口 `8080`。

## 📂 项目结构

```text
backend/      # 基于 FastAPI 的后端服务与任务调度器
tg_signer/    # 基于 Pyrogram 的 Telegram 自动化核心引擎
frontend/     # 基于 Next.js 的现代化管理面板

```

## 🔄 最近更新

### 2026-01-29

* **并发优化**：引入账号级共享锁，彻底解决 `database is locked` 报错。
* **写入保护**：防止同一账号在登录、任务执行或聊天刷新时的并发冲突。
* **流程强化**：增强了登录流程的鲁棒性。
* **配置优化**：完善了 TG API、Secret 及 AI 相关环境变量的解析逻辑。
* **UI 改进**：新增账号字符长度限制，并优化了任务弹窗的时间范围显示。

## 🤝 致谢

本项目在原项目基础上进行了大量的重构与功能扩展，感谢：

* **tg-signer** by [amchii](https://github.com/amchii/tg-signer)

**技术栈支持：**
FastAPI, Uvicorn, APScheduler, Pyrogram/Kurigram, Next.js, Tailwind CSS, OpenAI SDK.

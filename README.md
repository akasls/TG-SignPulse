# TG-SignPulse

[English README](README_EN.md)

TG-SignPulse 是一款专为 Telegram 设计的自动化管理面板。它集成了多账号管理、自动签到、定时任务及按钮交互等功能，旨在为用户提供高效、智能的 Telegram 自动化方案。
> AI 驱动：本项目深度集成 AI 辅助能力，部分代码及逻辑由 AI 协作开发。

## ✨ 功能特色

- 多账号管理：支持多账号同时在线，统一调度自动化任务。
- 全自动工作流：涵盖自动签到、定时消息发送、模拟点击按钮等核心流程。
- 安全策略：内置任务时间随机化机制，有效降低账号风控风险。
- 现代化 UI：基于 Next.js 构建的响应式管理后台，简洁易用。
- AI 辅助增强：集成 AI 视觉与逻辑处理，支持图片选项识别及自动计算题解答。
- 容器化部署：支持原生 Docker 和 Docker Compose，实现一键部署与迁移。

## 快速开始

默认凭据：
- 账号: `admin`
- 密码: `admin123`

### 使用 Docker Run

```bash
docker run -d \
  --name tg-signpulse \
  --restart unless-stopped \
  -p 8080:8080 \
  -v $(pwd)/data:/data \
  -e PORT=8080 \
  -e TZ=Asia/Shanghai \
  # 可选：配置 Telegram API 以获得更佳稳定性
  # -e TG_API_ID=123456 \
  # -e TG_API_HASH=xxxxxxxxxxxxxxxx \
  # 可选：arm64 推荐启用 SQLite session 替代模式（避免 database is locked）
  # -e TG_SESSION_MODE=string \
  # -e TG_SESSION_NO_UPDATES=1 \
  # -e TG_GLOBAL_CONCURRENCY=1 \
  # 可选：面板 2FA 容错窗口（默认 0）
  # -e APP_TOTP_VALID_WINDOW=1 \
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
      - PORT=8080
      - TZ=Asia/Shanghai
      # 可选：arm64 推荐启用 SQLite session 替代模式（避免 database is locked）
      # - TG_SESSION_MODE=string
      # - TG_SESSION_NO_UPDATES=1
      # - TG_GLOBAL_CONCURRENCY=1
      # 可选：面板 2FA 容错窗口（默认 0）
      # - APP_TOTP_VALID_WINDOW=1
      # 可选：自定义后端密钥
      # - APP_SECRET_KEY=your_secret_key
    restart: unless-stopped
```

### Zeabur 部署

- 新建项目：在控制台创建一个新项目。
- 服务配置：选择 Docker 镜像，并填入以下参数：
  - 镜像地址：`ghcr.io/akasls/tg-signpulse:latest`
  - 环境变量：变量名 `TZ`，变量值 `Asia/Shanghai`（arm64 推荐额外设置 `TG_SESSION_MODE=string`、`TG_SESSION_NO_UPDATES=1`、`TG_GLOBAL_CONCURRENCY=1`）
  - 端口设置：端口 `8080`，类型选择 `HTTP`
  - 持久化卷：卷 ID 填 `data`，路径填 `/data`
- 开始部署：点击部署按钮。
- 域名绑定：部署完成后，在服务详情页点击“添加域名”即可生成公网访问地址。

## 非 root / NAS / ClawCloud 权限说明

- 默认数据目录是 `/data`。当 `/data` 可写时，所有数据（sessions/账号/任务/导入导出/日志）仍写入 `/data`，与旧版本一致。
- 当 `/data` 不可写时，系统会自动降级到 `/tmp/tg-signpulse` 并输出 warning（提示数据可能不持久化）。
- 生产环境建议为容器挂载可写的持久化卷到 `/data`，而不是依赖 `/tmp`。

排障命令（容器内，不要使用 chmod 777）：

```bash
id
ls -ld /data
touch /data/.probe && rm /data/.probe
```

如果是宿主机挂载目录，可检查：

```bash
ls -ld ./data
```

## 可选环境变量

以下变量均为可选，未设置时默认行为与旧版本一致：

- `TG_SESSION_MODE`: `file`（默认）或 `string`。`string` 模式使用 session_string + in_memory，避免 `.session` SQLite 锁（arm64 推荐）。
- `TG_SESSION_NO_UPDATES`: `1` 启用 `no_updates`（仅在 `string` 模式生效，默认 `0`）。
- `TG_GLOBAL_CONCURRENCY`: 全局并发限制（默认 `1`，arm64 建议保持 `1`）。
- `APP_TOTP_VALID_WINDOW`: 面板 2FA 容错窗口（默认 `0`，设为 `1` 允许前后各 1 个 30s 窗口）。
- `PORT`: 监听端口（默认 `8080`，由容器启动命令读取）。

## Session 迁移（可选）

从已有 `.session` 文件导出 session_string（不会输出 session_string）：

```bash
python -m tools.migrate_session
# 或 python tools/migrate_session.py --account your_account
```

## 健康检查

- `GET /healthz`：秒回 200，无外部依赖
- `GET /readyz`：后台初始化完成后返回 200

## 多架构镜像构建

```bash
docker buildx build --platform linux/amd64,linux/arm64 -t ghcr.io/akasls/tg-signpulse:latest --push .
```

GitHub Actions：推送到 `main` 或发布 `v*` 标签会自动构建并推送 GHCR 镜像（`latest` 与提交 SHA 标签）。

## 项目结构

```
backend/      # 基于 FastAPI 的后端服务与任务调度器
tg_signer/    # 基于 Pyrogram 的 Telegram 自动化核心引擎
frontend/     # 基于 Next.js 的现代化管理面板
```

## 最近更新

### 2026-02-03

- 权限兼容：启动时探测 `/data` 可写性，不可写自动降级到 `/tmp/tg-signpulse` 并输出 warning（/data 可写时路径与旧版本一致）。
- 启动稳定：移除 import 阶段的服务单例与数据库引擎初始化，避免 PaaS/ClawCloud 导入崩溃。
- 任务更新：scheduler 日志写入统一到 `logs/`，写入失败不影响更新结果。
- 代理体验：SOCKS5 输入提示文案更新为正确格式，旧输入兼容。

### 2026-02-02

- 新增 `TG_SESSION_MODE=string`：使用 session_string + in_memory，避免 `.session` SQLite 锁（默认仍为 file 模式）。
- 新增迁移脚本 `python -m tools.migrate_session`：从旧 `.session` 导出 session_string（不打印敏感信息）。
- 新增全局并发限制 `TG_GLOBAL_CONCURRENCY`（默认 1），并确保同账号串行。
- 启动阶段移除重活，`/healthz` 可在 1~2 秒内响应；新增 `/readyz`。
- 新增面板 2FA 容错窗口 `APP_TOTP_VALID_WINDOW`（默认 0，不影响旧行为）。
- 新增账号备注与代理编辑入口，账号卡片支持编辑。
- 任务执行/刷新聊天时自动使用账号代理（若配置）。
- Docker 构建：arm64 跳过 tgcrypto 编译，避免 NAS 本地构建报错。

### 2026-01-29

- 并发优化：引入账号级共享锁，彻底解决 `database is locked` 报错。
- 写入保护：防止同一账号在登录、任务执行或聊天刷新时的并发冲突。
- 流程强化：增强了登录流程的鲁棒性。
- 配置优化：完善了 TG API、Secret 与 AI 相关环境变量的解析逻辑。
- UI 改进：新增账号字符长度限制，并优化了任务弹窗的时间范围显示。

## 致谢

本项目在原项目基础上进行了大量重构与功能扩展，感谢：

- tg-signer by amchii

技术栈支持：FastAPI, Uvicorn, APScheduler, Pyrogram/Kurigram, Next.js, Tailwind CSS, OpenAI SDK.

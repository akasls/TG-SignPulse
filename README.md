# 🚀 TG SignPulse

**TG SignPulse** 是一款基于 `tg-signer` 核心开发的、拥有现代化 Web 界面的 Telegram 自动化任务管理系统。它不仅支持每日定时签到，还提供了实时监控、自动回复、多账号管理以及精美的可视化运行报告。

---

## ✨ 核心特性

- **💎 极简美学**: 全新的 **Glassmorphism (玻璃拟态)** 设计风格，极致的视觉体验与丝滑的微交互。
- **📅 智能调度**: 支持简单的 `HH:MM` 时间格式或复杂的 `Cron` 表达式，内置时区优化（默认 `Asia/Hong_Kong`）。
- **📊 运行历史**: 自动记录每个账号下任务的执行状态，保留 **最近 3 天** 的详细日志。
- **💾 日志导出**: 支持一键导出执行轨迹为 `.txt` 文件，方便排查与留存。
- **🔒 实时监控**: 任务运行期间 UI 全程锁定，配合 **实时日志流**，任务执行细节一览无余。
- **🧩 丰富动作**: 支持发送文本、点击内建键盘、AI 识别图片选项、AI 自动解答计算题等。
- **🤖 AI 构建**: 本项目 Web 端及核心逻辑优化均由 **AI (Google DeepMind Antigravity)** 协助完成。

---

## 🏗️ 项目架构

项目采用前后端分离架构，确保极致的响应速度与稳定性：

- **Frontend**: `Next.js 14` + `TypeScript` + `Tailwind CSS` + `Phosphor Icons`。
- **Backend**: `FastAPI` + `Python 3.12` + `APScheduler` (后台任务管理)。
- **Core Engine**: 基于 **Pyrogram** 的 `tg-signer` 核心。
- **Database**: `SQLite` (本地数据与任务状态持久化)。

---

## 🚀 部署教程

### ⚡ 方案一：Zeabur 一键部署 (推荐)

Zeabur 是一个非常友好的云端部署平台，本项目已针对 Zeabur 的环境变量进行了适配：

1. **Fork 本项目** 到您的 GitHub 账号下。
2. 在 [Zeabur 控制台](https://zeabur.com) 创建新服务，选择 **GitHub** 并连接您的仓库。
3. **环境变量配置**:
   - `TZ`: `Asia/Hong_Kong` (推荐)
   - `SECRET_KEY`: 随机字符串（用于 JWT 认证）
   - `ADMIN_USERNAME`: 初始管理员账号
   - `ADMIN_PASSWORD`: 初始管理员密码
4. Zeabur 会根据项目中的 `Dockerfile` 自动开始构建并分配域名。

### 🐳 方案二：VPS Docker 部署

得益于 GitHub Actions 的自动化流程，您可以直接拉取构建好的镜像：

```bash
# 1. 创建数据存储目录
mkdir -p /opt/tg-signer/data

# 2. 拉取并启动镜像
# 注意替换 <YOUR_USERNAME> 为您的 GitHub 用户名
docker run -d \
  --name tg-signer \
  -p 8080:8080 \
  -e TZ=Asia/Hong_Kong \
  -e SECRET_KEY=your_secret_key \
  -e ADMIN_USERNAME=admin \
  -e ADMIN_PASSWORD=admin_pass \
  -v /opt/tg-signer/data:/data \
  --restart always \
  ghcr.io/<YOUR_USERNAME>/tg-signer:latest
```

> **注意**: 初次部署后，请及时在 Web 端修改初始密码并配置 Telegram API ID/Hash。

---

## 🛠️ 进阶使用 (CLI)

虽然 Web 端已支持绝大部分功能，但您仍可通过以下方式直接调用核心能力：

```bash
# 本地运行 CLI 登录 (用于手动获取 Session)
pip install .
tg-signer login
```

更多 CLI 命令参考原作者文档。

---

## ❤️ 感谢

- **原作者**: 感谢 [Amchii](https://github.com/amchii) 优秀的 [tg-signer](https://github.com/amchii/tg-signer) 核心实现。
- **AI 赋能**: 本项目由 **Google DeepMind Antigravity** 构建并持续优化。

---

## ⚠️ 免责声明

本项目仅供学习交流使用。使用本程序进行自动化操作可能违反 Telegram 的服务条款或特定频道/群组的规则，由此产生的账号受限或违规风险由使用者自行承担。

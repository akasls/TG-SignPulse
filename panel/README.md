## tg-signer 可视化管理面板（Docker First）

本面板为 `tg-signer` 提供一个全新的、完全替代原 WebUI 的可视化控制台，所有逻辑通过 CLI (`tg-signer`) 子进程完成，不修改核心代码。

- 后端：Python 3.12 + FastAPI + SQLAlchemy + APScheduler
- 前端：Next.js App Router + Tailwind + 简化版 shadcn/ui
- 数据：SQLite（`/data/db.sqlite`）+ 本地日志与 session
- 部署：Docker / Docker Compose / Zeabur

---

## 目录结构（面板相关）

```text
backend/       # FastAPI 后端
frontend/      # Next.js 前端（构建后静态产物）
web/           # （容器内）前端静态文件根目录
data/          # （容器内 / 宿主机映射）数据目录
  ├─ .signer
  ├─ sessions
  ├─ logs
  └─ db.sqlite
Dockerfile     # 单容器镜像：后端 + 前端静态托管
docker-compose.panel.yml  # 默认 docker-compose 启动方式
panel/README.md           # 本说明
```

容器内固定路径约定：

```text
/app   # 后端代码 + tg-signer 包
/web   # 前端静态文件（Next.js 导出结果）
/data  # 数据卷（默认映射 ./data）
```

---

## 构建与运行（Docker 单容器：模式 A）

### 1. 构建镜像

```bash
docker build -t tg-signer-panel:latest .
```

### 2. docker run 启动示例

```bash
docker run -d \
  --name tg-signer-panel \
  -p 3000:3000 \
  -v $(pwd)/data:/data \
  tg-signer-panel:latest
```

Windows PowerShell 示例：

```powershell
docker run -d `
  --name tg-signer-panel `
  -p 3000:3000 `
  -v ${PWD}/data:/data `
  tg-signer-panel:latest
```

访问：`http://localhost:3000`

- `/`：前端控制台（静态网页，由 FastAPI 通过 `/web` 托管）
- `/auth/*` `/accounts/*` `/tasks/*` `/events/*`：后端 API

---

## 构建与运行（docker-compose：模式 A 默认方式）

使用仓库根目录中的 `docker-compose.panel.yml`：

```bash
docker compose -f docker-compose.panel.yml up -d
```

等价的停止与清理：

```bash
docker compose -f docker-compose.panel.yml down
```

默认：

- 服务名：`app`
- 端口映射：`3000:3000`
- 数据卷：`./data:/data`

可以通过环境变量覆盖端口（云平台常见的 `PORT`）：

```yaml
services:
  app:
    environment:
      - PORT=3000  # 在部分平台上可设置为 $PORT
```

---

## 模式 B：前后端分离（示意）

面板已支持完全静态构建的前端，因此可以：

1. **单独构建前端静态产物：**

```bash
cd frontend
npm install
npm run build   # 输出到 frontend/out
```

2. 将 `frontend/out` 部署到任意静态文件服务（如 Zeabur 静态页 / Vercel / Nginx）；

3. 后端容器仅运行 FastAPI API：

```bash
docker run -d \
  --name tg-signer-panel-api \
  -p 3000:3000 \
  -v $(pwd)/data:/data \
  tg-signer-panel:latest \
  uvicorn backend.main:app --host 0.0.0.0 --port 3000
```

4. 前端通过环境变量 `NEXT_PUBLIC_API_BASE` 指向后端 API 地址，例如：

```bash
# 构建前端前设置
export NEXT_PUBLIC_API_BASE="https://your-api.example.com"
```

然后重新 `npm run build`。

---

## Zeabur 部署说明

### 方案一：单服务（推荐，模式 A）

1. **在 Zeabur 新建服务**，选择 Docker 方式，从 GitHub 仓库导入当前项目；
2. 构建命令：使用仓库根目录 `Dockerfile`（无需额外命令）；
3. 暴露端口：设置 `PORT=3000`（Zeabur 会自动映射到外网端口）；
4. 存储卷：
   - 新建持久化存储并挂载到容器内 `/data`。

容器启动后：

- 后端监听 `0.0.0.0:$PORT`（由 `uvicorn` 启动），满足云平台健康检查；
- 前端由 FastAPI 静态托管，访问 Zeabur 分配的域名即可打开控制台。

### 方案二：前后端分离（模式 B）

1. **后端服务（API 服务）：**
   - 仍使用根目录 `Dockerfile` 构建；
   - 设置环境变量 `PORT=$PORT`；
   - 配置持久化存储挂载 `/data`；
   - 得到后端服务域名，例如 `https://tg-signer-api.zeabur.app`。

2. **前端服务：**
   - 新建一个 Next.js / 静态站点服务；
   - 构建命令（示例）：

     ```bash
     cd frontend
     npm install
     NEXT_PUBLIC_API_BASE="https://tg-signer-api.zeabur.app" npm run build
     ```

   - 发布 `frontend/out` 目录为静态资源；
   - 前端通过 `NEXT_PUBLIC_API_BASE` 与后端交互。

---

## 登录与基础使用

1. 启动容器后访问面板首页 `/`；
2. 默认管理员账户（首次启动自动创建）：

   - 用户名：`admin`
   - 密码：`admin123`

   > 上线后建议通过数据库或后续管理接口修改密码，并在环境变量中配置更安全的 `APP_SECRET_KEY`。

3. 登录后可完成：

   - 添加 Telegram 账号（`api_id` / `api_hash` / `proxy`）；
   - 触发登录流程并输入验证码 / 2FA；
   - 绑定账号创建签到任务（cron 表达式）；
   - 启停、删除、手动执行任务；
   - 查看任务运行日志与状态。

---

## 注意事项

- 所有与 `tg-signer` 的交互均通过 CLI 子进程完成：
  - 登录：`tg-signer --workdir /data/.signer --session_dir /data/sessions login <account>`
  - 运行任务：`tg-signer --workdir /data/.signer --session_dir /data/sessions --account <account> run <task_name>`
- 不直接 import 或调用 `tg_signer` 内部模块；
- `/data` 目录包含：
  - `.signer`：tg-signer 工作目录（配置、记录等）
  - `sessions`：Telegram Session 文件
  - `logs`：任务运行日志
  - `db.sqlite`：面板自身的 SQLite 数据库（账号、任务、日志索引）。




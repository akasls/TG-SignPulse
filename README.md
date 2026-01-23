# TG-SignPulse

Telegram 任务自动执行与管理面板。支持多账号管理、自动签到、定时任务随机化执行等功能。

## 功能特性

- **多账号管理**：支持导入和管理多个 Telegram 账号。
- **自动化任务**：支持定时签到、发送消息等任务。
- **随机执行模式**：支持设置时间范围（如 09:00 - 18:00），系统将在范围内随机时间点执行，避免封号风险。
- **Docker 部署**：原生支持 Docker 和 Docker Compose 一键部署。
- **现代化 UI**：基于 Next.js 的响应式管理面板。

## 部署方法

### 方式一：Docker Run (命令行)

如果您只需简单运行，可以使用以下命令：

```bash
docker run -d \
  --name tg-signpulse \
  --restart unless-stopped \
  -p 8080:8080 \
  -v $(pwd)/data:/data \
  -e TZ=Asia/Shanghai \
  ghcr.io/akasls/tg-signpulse:latest
```

*   **数据持久化**：您的数据将保存在当前目录下的 `data` 文件夹中。
*   **访问地址**：`http://localhost:8080`

### 方式二：Docker Compose (推荐)

创建 `docker-compose.yml`：

```yaml
version: '3.8'
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

然后运行：

```bash
docker-compose up -d
```

## 开发

本项目后端基于 Python (FastAPI)，前端基于 TypeScript (Next.js)。

1.  克隆项目
2.  `pip install -r requirements.txt`
3.  `npm install` (在 frontend 目录)
4.  参考 `local-test.sh` 启动本地开发环境。

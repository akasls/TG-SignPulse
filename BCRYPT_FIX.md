# bcrypt 密码哈希错误修复

## 问题描述

在部署到 Zeabur 时，容器启动失败，错误信息：

```
ValueError: password cannot be longer than 72 bytes, truncate manually if necessary
```

## 根本原因

这是 `passlib` 和 `bcrypt` 库的版本兼容性问题。错误发生在：

1. **启动时**: 应用尝试创建默认管理员用户
2. **密码哈希**: 使用 `passlib[bcrypt]` 对密码 "admin123" 进行哈希
3. **bcrypt 初始化**: passlib 在初始化 bcrypt 后端时检测到版本兼容性问题
4. **崩溃**: 导致应用启动失败

## 修复方案

### 1. 固定依赖版本

在 `Dockerfile` 中：

```dockerfile
# 先安装 bcrypt 4.0.1（稳定版本）
RUN pip install --no-cache-dir "bcrypt==4.0.1"

# 然后安装 passlib 1.7.4
RUN pip install --no-cache-dir "passlib[bcrypt]==1.7.4"
```

**为什么这样做**:
- bcrypt 4.0.1 是一个稳定版本，与 passlib 1.7.4 兼容
- 先安装 bcrypt 确保 passlib 使用正确的后端
- 固定版本避免未来的兼容性问题

### 2. 简化密码哈希配置

在 `backend/core/security.py` 中使用标准配置：

```python
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
)
```

**为什么这样做**:
- 使用默认配置，让 passlib 自动处理
- 避免手动指定可能不兼容的参数

## 技术细节

### bcrypt 密码长度限制

bcrypt 算法本身限制密码最大 72 字节。这不是 bug，而是设计决定：

- 72 字节对于大多数密码已经足够
- 如果需要更长的密码，应该先哈希（如使用 SHA256）再传给 bcrypt

### passlib 后端检测

passlib 在启动时会：

1. 检测可用的 bcrypt 后端（bcrypt 库、bcryptor 等）
2. 运行兼容性测试
3. 如果测试失败，抛出错误

错误日志中的 `detect_wrap_bug` 就是这个兼容性测试。

## 验证修复

### 本地测试

```bash
# 1. 重新构建镜像
docker build -t tg-signer .

# 2. 运行容器
docker run -p 3000:3000 \
  -e APP_SECRET_KEY=test-key \
  -v ./data:/data \
  tg-signer

# 3. 检查日志
docker logs -f <container_id>

# 应该看到:
# INFO:     Application startup complete.
```

### Zeabur 部署

```bash
# 1. 提交修改
git add .
git commit -m "修复 bcrypt 密码哈希错误"
git push

# 2. 在 Zeabur 重新部署
# 3. 检查日志，确认启动成功
```

## 相关依赖版本

| 包 | 版本 | 说明 |
|---|------|------|
| bcrypt | 4.0.1 | 密码哈希库 |
| passlib | 1.7.4 | 密码哈希框架 |
| pydantic | <2 | 数据验证 |
| fastapi | 0.109.2 | Web 框架 |

## 其他可能的解决方案

如果上述方案仍然失败，可以考虑：

### 方案 A: 使用 argon2 替代 bcrypt

```python
# backend/core/security.py
pwd_context = CryptContext(
    schemes=["argon2", "bcrypt"],
    deprecated="auto",
)
```

需要安装: `pip install argon2-cffi`

### 方案 B: 延迟创建管理员用户

修改 `backend/main.py`，不在启动时创建管理员：

```python
@app.on_event("startup")
def on_startup() -> None:
    ensure_data_dirs(settings)
    Base.metadata.create_all(bind=engine)
    # 注释掉这行
    # with SessionLocal() as db:
    #     ensure_admin(db)
    init_scheduler()
```

然后通过 API 或 CLI 手动创建管理员。

### 方案 C: 使用环境变量设置密码

```python
# backend/services/users.py
import os

def ensure_admin(db: Session):
    username = os.getenv("ADMIN_USERNAME", "admin")
    password = os.getenv("ADMIN_PASSWORD", "admin123")
    # ...
```

## 预防措施

为避免类似问题：

1. **固定依赖版本**: 在生产环境使用固定版本
2. **测试环境**: 在与生产环境相同的环境中测试
3. **CI/CD**: 添加自动化测试
4. **监控**: 监控应用启动和运行状态

## 更新日志

- **2024-12-24**: 修复 bcrypt 密码哈希错误
- **版本**: bcrypt 4.0.1, passlib 1.7.4

---

**状态**: ✅ 已修复  
**测试**: ⏳ 待验证

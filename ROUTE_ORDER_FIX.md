# 🔧 路由顺序修复

## 问题描述

部署成功后，访问网页只显示：
```json
{"detail":"Not Found"}
```

## 问题原因

FastAPI 的路由顺序问题：

1. API 路由：`/api/*`
2. 静态文件：`/` (捕获所有路径)
3. Health 路由：`/health` ❌ 被静态文件覆盖了

因为静态文件挂载在 `/`，它会捕获所有路径，包括 `/health`。

## 解决方案

调整路由注册顺序，确保所有 API 路由在静态文件之前：

```python
# 1. API 路由
app.include_router(api_router, prefix="/api")

# 2. Health 路由
@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}

# 3. 静态文件（必须放在最后）
app.mount(
    "/",
    StaticFiles(directory="/web", html=True),
    name="frontend",
)
```

## 已提交并推送

```
[main b731ff7] 修复路由顺序-health路由移到静态文件之前
 1 file changed, 6 insertions(+), 5 deletions(-)

To https://github.com/akasls/tg-signer.git
   1eeb206..b731ff7  main -> main
```

## FastAPI 路由优先级

FastAPI 按照注册顺序匹配路由：

1. ✅ 先注册的路由优先级高
2. ✅ `app.mount("/", ...)` 会捕获所有路径
3. ✅ 因此必须放在最后

## 正确的顺序

```python
# ✅ 正确顺序
1. API 路由 (/api/*)
2. 特定路由 (/health, /docs, 等)
3. 静态文件 (/)

# ❌ 错误顺序
1. 静态文件 (/)  # 会捕获所有路径
2. API 路由 (/api/*)  # 永远不会被访问
3. 特定路由 (/health)  # 永远不会被访问
```

## 下一步

**在 Zeabur 重新部署**

1. 进入 Zeabur 控制台
2. 找到 tg-signer 项目
3. 点击"Redeploy"
4. 等待部署完成
5. 访问应用 URL

## 预期结果

- ✅ 访问根路径 `/` → 显示前端页面
- ✅ 访问 `/api/*` → API 正常工作
- ✅ 访问 `/health` → 返回 `{"status": "ok"}`

## 验证步骤

1. **访问主页**
   - URL: `https://your-app.zeabur.app/`
   - 应该看到登录页面

2. **测试 API**
   - URL: `https://your-app.zeabur.app/api/health`
   - 或: `https://your-app.zeabur.app/health`
   - 应该返回: `{"status": "ok"}`

3. **登录系统**
   - 用户名: `admin`
   - 密码: `admin123`
   - 应该能成功登录

---

**状态**: ✅ 路由顺序已修复  
**下一步**: 在 Zeabur 重新部署  
**预计**: 应该能看到前端页面了！

**马上就能用了！** 🎉🚀

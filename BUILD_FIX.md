# 🔧 部署问题修复

## 问题
构建失败，错误信息：
```
Module '"../../lib/api"' has no exported member 'fetchAccounts'.
```

## 原因
`dashboard/page.tsx` 还在使用旧的 API 方法名，但新的 `api.ts` 已经重构，不再包含这些方法。

## 修复
✅ 已修复！重写了 `frontend/app/dashboard/page.tsx`：

1. **移除旧的账号管理代码** - 现在有专门的 `accounts/page.tsx`
2. **简化主页** - 只显示欢迎信息和快速导航
3. **添加导航链接** - 链接到账号管理和设置页面
4. **修复退出登录** - 使用 `logout()` 函数

## 新的主页功能

### 顶部导航
- 📱 账号管理 - 链接到 `/dashboard/accounts`
- ⚙️ 设置 - 链接到 `/dashboard/settings`
- 退出 - 退出登录

### 欢迎卡片
- 显示三个功能模块的快速入口
- 显示当前任务数量

### 快速开始指南
- 步骤 1: 添加 Telegram 账号
- 步骤 2: 配置签到任务
- 步骤 3: 运行和监控

## 现在可以部署了！

```bash
# 提交修复
git add .
git commit -m "修复构建错误，简化 dashboard 主页"
git push

# 在 Zeabur 重新部署
```

## 环境变量提醒

**必须设置**:
```bash
TG_API_ID=your_api_id
TG_API_HASH=your_api_hash
APP_SECRET_KEY=your-secret-key
```

## 页面结构

```
/dashboard (主页 - 欢迎和导航)
├── /dashboard/accounts (账号管理)
└── /dashboard/settings (设置)
```

---

**状态**: ✅ 已修复  
**可以部署**: ✅ 是

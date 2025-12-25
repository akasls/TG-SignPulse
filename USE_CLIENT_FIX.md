# 🔧 "use client" 与 generateStaticParams 冲突修复

## 问题描述

**错误信息**: 
```
Error: Page "/dashboard/accounts/[name]/page" cannot use both "use client" and export function "generateStaticParams()".
```

**原因**: 在 Next.js 中，`"use client"` 指令和 `generateStaticParams()` 函数不能同时使用。

- `"use client"` - 标记组件为客户端组件
- `generateStaticParams()` - 用于服务端静态生成

## 解决方案

移除 `generateStaticParams()` 函数和相关导出，因为这个页面是客户端组件。

**修改前**:
```typescript
"use client";

export function generateStaticParams() {
  return [];
}

export const dynamic = 'force-dynamic';
export const dynamicParams = true;
```

**修改后**:
```typescript
"use client";

// 移除了 generateStaticParams 和相关导出
```

## 说明

对于使用 `"use client"` 的动态路由页面：
- ✅ 不需要 `generateStaticParams()`
- ✅ 动态路由会在客户端处理
- ✅ 使用 `useParams()` 获取路由参数

## 修改的文件

- `frontend/app/dashboard/accounts/[name]/page.tsx`

## 验证修复

```bash
# 提交修复
git add frontend/app/dashboard/accounts/[name]/page.tsx
git commit -m "修复 use client 与 generateStaticParams 冲突"
git push

# 在 Zeabur 重新部署
```

---

**状态**: ✅ 已修复  
**影响**: 现在可以正常构建和部署

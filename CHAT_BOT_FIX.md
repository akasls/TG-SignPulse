# Chat列表机器人显示修复

## 问题描述
在创建签到任务时，点击"添加 Chat"后选择Chat列表，只能看到群组和频道，无法看到Telegram机器人选项。

## 问题原因
后端API在获取账号的Chat列表时，没有正确处理`ChatType.BOT`类型。

在 `backend/api/routes/sign_tasks.py` 的 `get_account_chats` 函数中：
- 原代码只在 `ChatType.PRIVATE` 分支中尝试通过 `getattr(chat, 'is_bot', False)` 来判断是否为机器人
- 但实际上，Pyrogram 的 `ChatType` 枚举中有独立的 `BOT` 类型
- 当 `chat.type == ChatType.BOT` 时，不会进入 `ChatType.PRIVATE` 分支，导致机器人被忽略

## 修复方案
在 `backend/api/routes/sign_tasks.py` 第 242-273 行，修改Chat类型判断逻辑：

1. 添加独立的 `ChatType.BOT` 分支处理
2. 为机器人添加 🤖 emoji 前缀，便于识别
3. 将 `ChatType.PRIVATE` 分支简化为只处理普通私聊

### 修改后的逻辑结构：
```python
if chat.type in [ChatType.GROUP, ChatType.SUPERGROUP, ChatType.CHANNEL]:
    # 处理群组、超级群组、频道
elif chat.type == ChatType.BOT:
    # 处理机器人（新增）
elif chat.type == ChatType.PRIVATE:
    # 处理普通私聊
```

## 测试建议
1. 重启后端服务
2. 登录前端，进入"创建签到任务"页面
3. 点击"添加 Chat"
4. 在Chat选择下拉列表中，应该能看到：
   - 群组（显示群组名称）
   - 频道（显示频道名称）
   - 机器人（显示 🤖 + 机器人名称）
   - 私聊（显示用户名）

## 相关文件
- `backend/api/routes/sign_tasks.py` - 修复的主要文件
- `frontend/app/dashboard/sign-tasks/create/page.tsx` - 前端Chat选择界面（无需修改）

## 修复日期
2025-12-25

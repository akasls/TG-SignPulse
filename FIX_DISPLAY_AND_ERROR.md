# Chat列表显示与任务创建修复

## 修复内容

### 1. Chat列表显示问题
**问题**：Telegram机器人和个人用户在列表中只显示用户名字母（username），而不是标题（如机器人名称或用户真实姓名）。
**原因**：前端优先显示 `chat.title`，但后端之前对于机器人和私聊用户将 `title` 设置为 `None`。
**修复**：修改 `backend/api/routes/sign_tasks.py` 中的 `get_account_chats`：
- 对于 **机器人**：`title` 设置为 `🤖 {display_name}`
- 对于 **私聊**：`title` 设置为 `{first_name} {last_name}`

### 2. 创建任务报错 (Internal Server Error)
**问题**：创建任务时出现 500 错误。
**原因推测**：
1. 可能是任务名称包含 Windows 文件系统非法字符（如 `:/\`），导致后端创建目录失败。
2. 可能是其他未捕获的运行时异常。

**修复**：
1. **输入验证**：在 `SignTaskCreate` 模型中添加 `field_validator`，禁止任务名称包含 `< > : " / \ | ? *` 等非法字符。这将 500 错误转化为 422 验证错误，提示更友好。
2. **异常捕获**：在 `create_sign_task` 和 `update_sign_task` 接口中添加 `try-except` 块，捕获所有异常并打印详细堆栈日志，确保返回更具体的错误信息而不是通用的 500。

## 验证方法
1. **验证显示**：
   - 进入"创建签到任务" -> "添加 Chat"。
   - 检查机器人是否显示为 `🤖 机器人名称`。
   - 检查私聊用户是否显示为真实姓名。

2. **验证任务创建**：
   - 尝试创建一个包含特殊字符（如 `invalid:name`）的任务，应收到 422 错误提示。
   - 创建正常任务，应成功。
   - 如果仍报错，请查看 Docker 日志 `docker logs tg-signer-test-container` 获取详细堆栈信息（已添加 traceback 打印）。

## 修改文件
- `backend/api/routes/sign_tasks.py`

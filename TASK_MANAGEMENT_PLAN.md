# 📋 可视化任务管理 - 完整实施方案

## 🎯 目标

在 Web UI 中实现完整的任务配置和编辑功能，包括：
1. 创建新任务
2. 编辑现有任务
3. 配置 Chat ID
4. 配置动作序列（发送文本、点击按钮、AI 识别等）
5. 配置 CRON 时间
6. 启用/禁用任务

## 📊 技术挑战

### 1. 配置结构复杂

原项目的任务配置（SignConfigV3）包含：
```python
class SignConfigV3:
    chats: List[SignChatV3]  # 多个 Chat 配置
    sign_at: str  # CRON 表达式
    random_seconds: int  # 随机延迟
    sign_interval: int  # 间隔时间

class SignChatV3:
    chat_id: int  # Chat ID
    name: str  # Chat 名称
    actions: List[ActionT]  # 动作序列
    delete_after: Optional[int]  # 删除延迟
    action_interval: int  # 动作间隔

# 支持的动作类型
- SendTextAction  # 发送文本
- SendDiceAction  # 发送骰子
- ClickKeyboardByTextAction  # 点击按钮
- ChooseOptionByImageAction  # AI 图片识别
- ReplyByCalculationProblemAction  # AI 计算题
```

### 2. 存储方式

原项目使用文件系统存储配置：
- 路径：`.signer/signs/<task_name>/config.json`
- 格式：JSON

### 3. 实施方案

由于代码量巨大（预计 2000+ 行），我提供两个方案：

## 方案 A：完整实施（推荐，但耗时）

### 后端部分（约 500 行）

#### 1. 创建签到任务 API
**文件**: `backend/api/routes/sign_tasks.py`

```python
# 需要实现的端点：
POST   /api/sign-tasks              # 创建任务
GET    /api/sign-tasks              # 列表
GET    /api/sign-tasks/{name}       # 获取详情
PUT    /api/sign-tasks/{name}       # 更新
DELETE /api/sign-tasks/{name}       # 删除
POST   /api/sign-tasks/{name}/run   # 手动运行
GET    /api/sign-tasks/{name}/chats # 获取 Chat 列表（用于选择）
```

#### 2. 创建签到任务服务
**文件**: `backend/services/sign_tasks.py`

```python
# 需要实现的功能：
- 读取/写入 JSON 配置文件
- 验证配置格式
- 执行任务
- 获取账号的 Chat 列表
```

### 前端部分（约 1500 行）

#### 1. 任务列表页面
**文件**: `frontend/app/dashboard/tasks/page.tsx`

功能：
- 显示所有任务
- 启用/禁用任务
- 删除任务
- 跳转到编辑页面

#### 2. 任务编辑器
**文件**: `frontend/app/dashboard/tasks/[name]/page.tsx`

功能：
- 基本信息（任务名、账号、CRON）
- Chat 配置（添加/删除/编辑）
- 动作编辑器（拖拽排序、添加/删除动作）
- 实时预览

#### 3. 组件

**Chat 选择器** (`components/ChatSelector.tsx`):
- 从账号获取 Chat 列表
- 搜索和过滤
- 显示 Chat 信息

**动作编辑器** (`components/ActionEditor.tsx`):
- 选择动作类型
- 配置动作参数
- 拖拽排序

**CRON 编辑器** (`components/CronEditor.tsx`):
- 可视化 CRON 配置
- 预设时间（每天 6:00、每周一等）
- 自定义表达式

### 预计工作量
- 后端：4-6 小时
- 前端：8-12 小时
- 测试：2-4 小时
- **总计：14-22 小时**

## 方案 B：简化版（快速，推荐）

### 功能范围

**支持**:
- ✅ 查看任务列表
- ✅ 启用/禁用任务
- ✅ 删除任务
- ✅ 手动运行任务
- ✅ 查看任务日志
- ✅ 简单的任务创建（单个 Chat，单个动作）

**不支持**（需要 CLI）:
- ❌ 复杂的多 Chat 配置
- ❌ 复杂的动作序列
- ❌ AI 识别动作

### 实施步骤

#### 1. 后端 API（约 200 行）
创建简化的任务 API，支持基本的 CRUD 操作

#### 2. 前端页面（约 500 行）
- 任务列表（卡片展示）
- 简单的创建表单
- 启用/禁用开关
- 运行按钮

### 预计工作量
- 后端：2-3 小时
- 前端：3-4 小时
- 测试：1 小时
- **总计：6-8 小时**

## 方案 C：混合方案（平衡）

### 实施策略

1. **Web UI 支持**:
   - 查看所有任务
   - 启用/禁用任务
   - 删除任务
   - 手动运行任务
   - 查看日志
   - **简单任务创建**（单个 Chat，发送文本）

2. **CLI 支持**:
   - 复杂任务配置
   - 多 Chat 配置
   - 复杂动作序列
   - AI 识别动作

3. **配置导入导出**:
   - 在 CLI 配置好后
   - 通过 Web UI 导出
   - 在其他环境导入

### 预计工作量
- 后端：3-4 小时
- 前端：4-6 小时
- 测试：1-2 小时
- **总计：8-12 小时**

## 💡 我的建议

考虑到：
1. 完整实施需要 14-22 小时
2. 配置结构非常复杂
3. CLI 已经很成熟

我建议采用 **方案 C（混合方案）**：

### 立即实施（2-3 小时）
1. 创建任务列表页面
2. 显示所有任务（从文件系统读取）
3. 启用/禁用任务
4. 删除任务
5. 手动运行任务

### 后续实施（可选）
1. 简单任务创建表单
2. 基础动作配置
3. CRON 可视化编辑器

### 复杂功能
继续使用 CLI 配置

## 🚀 立即开始

如果您同意方案 C，我会立即开始实施：

1. **第一步**（30 分钟）：创建任务列表 API
2. **第二步**（1 小时）：创建任务列表页面
3. **第三步**（30 分钟）：添加启用/禁用功能
4. **第四步**（30 分钟）：添加运行和删除功能

---

**请选择方案**：
- **A** - 完整实施（14-22 小时）
- **B** - 简化版（6-8 小时）
- **C** - 混合方案（8-12 小时，推荐）

或者告诉我您的具体需求，我可以定制方案。

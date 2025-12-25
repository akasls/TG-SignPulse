# ✅ 间隔设置已添加！

## 已完成的修改

### ✅ 在添加签到任务页面加入动作间隔和签到间隔

添加了两个间隔设置，并附带说明文字：

```typescript
<div className="grid grid-cols-2 gap-4">
    <div>
        <Label>动作间隔（秒）</Label>
        <Input
            type="number"
            value={newTask.action_interval}
            onChange={...}
        />
        <p className="text-xs text-gray-500 mt-1">
            同一 Chat 中动作之间的间隔
        </p>
    </div>

    <div>
        <Label>签到间隔（秒）</Label>
        <Input
            type="number"
            value={newTask.sign_interval}
            onChange={...}
        />
        <p className="text-xs text-gray-500 mt-1">
            不同 Chat 之间的间隔
        </p>
    </div>
</div>
```

## 两种间隔的区别

### 1. 动作间隔 (action_interval)
- **作用**: 同一个 Chat 中，多个动作之间的等待时间
- **默认值**: 1 秒
- **示例**:
  ```
  Chat: LinuxDo 论坛
  ├─ 动作1: 发送 "签到"
  ├─ ⏱️ 等待 1 秒 ← 动作间隔
  ├─ 动作2: 点击 "确认"
  ├─ ⏱️ 等待 1 秒 ← 动作间隔
  └─ 动作3: 发送骰子
  ```

### 2. 签到间隔 (sign_interval)
- **作用**: 不同 Chat 之间的等待时间
- **默认值**: 1 秒
- **示例**:
  ```
  Chat1: LinuxDo 论坛
    └─ 执行所有动作
  ⏱️ 等待 1 秒 ← 签到间隔
  Chat2: Telegram 机器人
    └─ 执行所有动作
  ⏱️ 等待 1 秒 ← 签到间隔
  Chat3: 另一个群组
    └─ 执行所有动作
  ```

## 完整的执行流程

```
任务: 每日签到
├─ Chat 1 (LinuxDo)
│   ├─ 动作1: 发送 "签到"
│   ├─ ⏱️ 等待 action_interval (2秒)
│   ├─ 动作2: 点击 "确认"
│   └─ ⏱️ 等待 action_interval (2秒)
│       动作3: 发送骰子
│
├─ ⏱️ 等待 sign_interval (3秒)
│
├─ Chat 2 (机器人)
│   ├─ 动作1: 发送 "/checkin"
│   └─ ⏱️ 等待 action_interval (2秒)
│       动作2: 点击按钮
│
└─ 任务结束
```

## 界面布局

创建任务时的配置项顺序：

```
基本信息
├─ 任务名称
└─ 签到时间（CRON）

Chat 配置
├─ 选择 Chat [刷新按钮]
└─ 或手动输入 Chat ID

间隔设置
├─ 动作间隔（秒） - 同一 Chat 中动作之间的间隔
└─ 签到间隔（秒） - 不同 Chat 之间的间隔

其他设置
├─ 删除延迟（秒）
└─ 随机延迟（秒）

动作序列
└─ [添加动作]
```

## 已提交并推送

```
[main 7e3c001] 添加动作间隔和签到间隔到任务创建表单
 2 files changed, 203 insertions(+), 1 deletion(-)

To https://github.com/akasls/tg-signer.git
   a974869..7e3c001  main -> main
```

## 下一步

1. **在 Zeabur 重新部署** - 间隔设置会生效
2. **测试功能**:
   - ✅ 创建任务时可以设置动作间隔
   - ✅ 创建任务时可以设置签到间隔
   - ✅ 说明文字清楚解释了两种间隔的区别

## 使用建议

### 动作间隔
- **推荐值**: 1-3 秒
- **用途**: 避免动作执行太快被检测为机器人
- **示例**: 发送消息后等待 2 秒再点击按钮

### 签到间隔
- **推荐值**: 1-5 秒
- **用途**: 避免同时操作多个 Chat 被限流
- **示例**: 在 LinuxDo 签到后等待 3 秒再去机器人签到

### 随机延迟
- **推荐值**: 0-60 秒
- **用途**: 让签到时间更随机，更像真人
- **示例**: 设置 30 秒，实际执行时间会在设定时间 ±30 秒内随机

---

**状态**: ✅ 间隔设置已添加  
**下一步**: 在 Zeabur 重新部署  
**预计**: 创建任务时可以灵活配置间隔时间！

**间隔设置已完成！** 🎉

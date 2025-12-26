"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { getToken } from "../../../lib/auth";
import {
    listSignTasks,
    deleteSignTask,
    runSignTask,
    getAccountChats,
    createSignTask,
    updateSignTask,
    SignTask,
    ChatInfo,
    CreateSignTaskRequest,
} from "../../../lib/api";
import { Button } from "../../../components/ui/button";
import { Card, CardContent } from "../../../components/ui/card";
import { Input } from "../../../components/ui/input";
import { Label } from "../../../components/ui/label";

export default function AccountTasksContent() {
    const router = useRouter();
    const searchParams = useSearchParams();
    const accountName = searchParams.get("name") || "";

    const [token, setLocalToken] = useState<string | null>(null);
    const [tasks, setTasks] = useState<SignTask[]>([]);
    const [chats, setChats] = useState<ChatInfo[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState("");
    const [success, setSuccess] = useState("");

    // 创建任务对话框
    const [showCreateDialog, setShowCreateDialog] = useState(false);
    const [newTask, setNewTask] = useState({
        name: "",
        sign_at: "0 6 * * *",
        random_minutes: 0,  // 改为分钟
        chat_id: 0,
        chat_id_manual: "",
        chat_name: "",
        actions: [{ action: 1, text: "" }],
        delete_after: undefined as number | undefined,
        action_interval: 1,
    });

    // 编辑任务对话框
    const [showEditDialog, setShowEditDialog] = useState(false);
    const [editingTaskName, setEditingTaskName] = useState("");
    const [editTask, setEditTask] = useState({
        sign_at: "0 6 * * *",
        random_minutes: 0,
        chats: [] as any[],
    });

    useEffect(() => {
        const t = getToken();
        if (!t) {
            router.replace("/");
            return;
        }
        if (!accountName) {
            router.replace("/dashboard");
            return;
        }
        setLocalToken(t);
        loadData(t);
    }, [router, accountName]);

    const loadData = async (t: string) => {
        try {
            setLoading(true);
            const [tasksData, chatsData] = await Promise.all([
                listSignTasks(t, accountName),  // 按账号名筛选任务
                getAccountChats(t, accountName),
            ]);

            setTasks(tasksData);
            setChats(chatsData);
        } catch (err: any) {
            setError(err.message || "加载数据失败");
        } finally {
            setLoading(false);
        }
    };

    const refreshChats = async () => {
        if (!token) return;
        try {
            setLoading(true);
            const chatsData = await getAccountChats(token, accountName);
            setChats(chatsData);
            setSuccess("Chat 列表已刷新");
        } catch (err: any) {
            setError(err.message || "刷新失败");
        } finally {
            setLoading(false);
        }
    };

    const handleDeleteTask = async (taskName: string) => {
        if (!token) return;

        if (!confirm(`确定要删除任务 ${taskName} 吗？`)) {
            return;
        }

        try {
            setLoading(true);
            setError("");
            await deleteSignTask(token, taskName);
            setSuccess(`任务 ${taskName} 已删除`);
            await loadData(token);
        } catch (err: any) {
            setError(err.message || "删除任务失败");
        } finally {
            setLoading(false);
        }
    };

    const handleRunTask = async (taskName: string) => {
        if (!token) return;

        try {
            setLoading(true);
            setError("");
            const result = await runSignTask(token, taskName, accountName);

            if (result.success) {
                setSuccess(`任务 ${taskName} 运行成功`);
            } else {
                setError(`任务运行失败: ${result.error}`);
            }
        } catch (err: any) {
            setError(err.message || "运行任务失败");
        } finally {
            setLoading(false);
        }
    };

    const handleCreateTask = async () => {
        if (!token) return;

        if (!newTask.name) {
            setError("请输入任务名称");
            return;
        }

        if (!newTask.sign_at) {
            setError("请输入签到时间");
            return;
        }

        // 确定使用哪个 Chat ID
        let chatId = newTask.chat_id;
        if (newTask.chat_id_manual) {
            chatId = parseInt(newTask.chat_id_manual);
            if (isNaN(chatId)) {
                setError("手动输入的 Chat ID 必须是数字");
                return;
            }
        }

        if (chatId === 0) {
            setError("请选择或输入 Chat ID");
            return;
        }

        if (newTask.actions.length === 0 || !newTask.actions[0].text) {
            setError("请至少添加一个动作");
            return;
        }

        try {
            setLoading(true);
            setError("");

            const request: CreateSignTaskRequest = {
                name: newTask.name,
                account_name: accountName,  // 关联当前账号
                sign_at: newTask.sign_at,
                chats: [{
                    chat_id: chatId,
                    name: newTask.chat_name || `Chat ${chatId}`,
                    actions: newTask.actions,
                    delete_after: newTask.delete_after,
                    action_interval: newTask.action_interval,
                }],
                random_seconds: newTask.random_minutes * 60,  // 分钟转换为秒
            };

            await createSignTask(token, request);
            setSuccess("任务创建成功！");
            setShowCreateDialog(false);
            setNewTask({
                name: "",
                sign_at: "0 6 * * *",
                random_minutes: 0,
                chat_id: 0,
                chat_id_manual: "",
                chat_name: "",
                actions: [{ action: 1, text: "" }],
                delete_after: undefined,
                action_interval: 1,
            });
            await loadData(token);
        } catch (err: any) {
            setError(err.message || "创建任务失败");
        } finally {
            setLoading(false);
        }
    };

    const handleAddAction = () => {
        setNewTask({
            ...newTask,
            actions: [...newTask.actions, { action: 1, text: "" }],
        });
    };

    const handleUpdateAction = (index: number, field: string, value: any) => {
        const newActions = [...newTask.actions];
        newActions[index] = { ...newActions[index], [field]: value };
        setNewTask({ ...newTask, actions: newActions });
    };

    const handleRemoveAction = (index: number) => {
        setNewTask({
            ...newTask,
            actions: newTask.actions.filter((_, i) => i !== index),
        });
    };

    const handleEditTask = (task: SignTask) => {
        setEditingTaskName(task.name);
        setEditTask({
            sign_at: task.sign_at,
            random_minutes: Math.round(task.random_seconds / 60),
            chats: task.chats,
        });
        setShowEditDialog(true);
    };

    const handleSaveEdit = async () => {
        if (!token) return;

        try {
            setLoading(true);
            setError("");

            await updateSignTask(token, editingTaskName, {
                sign_at: editTask.sign_at,
                random_seconds: editTask.random_minutes * 60,  // 转换回秒
                chats: editTask.chats,
            });

            setSuccess("任务更新成功！");
            setShowEditDialog(false);
            await loadData(token);
        } catch (err: any) {
            setError(err.message || "更新任务失败");
        } finally {
            setLoading(false);
        }
    };

    if (!token) {
        return null;
    }

    return (
        <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100">
            {/* 导航栏 */}
            <nav className="bg-white shadow-sm border-b">
                <div className="max-w-7xl mx-auto px-6 py-4">
                    <div className="flex items-center justify-between">
                        {/* 左边：返回箭头 + 面包屑导航 */}
                        <div className="flex items-center gap-3">
                            <Link
                                href="/dashboard"
                                className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
                                title="返回"
                            >
                                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                                </svg>
                            </Link>
                            <div className="flex items-center gap-2 text-sm">
                                <Link href="/dashboard" className="text-gray-500 hover:text-gray-700">
                                    首页
                                </Link>
                                <span className="text-gray-400">/</span>
                                <span className="text-gray-900 font-medium">{accountName}</span>
                            </div>
                        </div>

                        {/* 右边：新增任务图标 */}
                        <button
                            onClick={() => setShowCreateDialog(true)}
                            className="p-2 hover:bg-gray-100 rounded-lg transition-colors text-blue-600"
                            title="新增任务"
                        >
                            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                            </svg>
                        </button>
                    </div>
                </div>
            </nav>

            {/* 主内容 */}
            <div className="max-w-7xl mx-auto px-6 py-8">
                {/* 错误和成功提示 */}
                {error && (
                    <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 flex items-center justify-between">
                        <span>{error}</span>
                        <button onClick={() => setError("")} className="ml-2 font-bold">×</button>
                    </div>
                )}
                {success && (
                    <div className="mb-4 p-3 bg-green-50 border border-green-200 rounded-lg text-green-700 flex items-center justify-between">
                        <span>{success}</span>
                        <button onClick={() => setSuccess("")} className="ml-2 font-bold">×</button>
                    </div>
                )}

                {/* 任务列表 */}
                {loading && tasks.length === 0 ? (
                    <div className="text-center py-12 text-gray-500">加载中...</div>
                ) : tasks.length === 0 ? (
                    <Card>
                        <CardContent className="py-12 text-center text-gray-500">
                            <div className="text-4xl mb-4">📋</div>
                            <p className="mb-4">暂无任务</p>
                            <Button onClick={() => setShowCreateDialog(true)}>
                                创建第一个任务
                            </Button>
                        </CardContent>
                    </Card>
                ) : (
                    <div className="space-y-3">
                        {tasks.map((task) => (
                            <Card key={task.name} className="card-hover">
                                <CardContent className="p-4">
                                    <div className="flex items-center justify-between">
                                        <div className="flex-1 grid grid-cols-5 gap-4">
                                            {/* 任务名称 */}
                                            <div>
                                                <div className="text-xs text-gray-500 mb-1">任务名称</div>
                                                <div className="font-medium">{task.name}</div>
                                            </div>

                                            {/* Chat ID */}
                                            <div>
                                                <div className="text-xs text-gray-500 mb-1">Chat ID</div>
                                                <div className="font-mono text-sm">
                                                    {task.chats[0]?.chat_id || "-"}
                                                </div>
                                            </div>

                                            {/* 签到时间 */}
                                            <div>
                                                <div className="text-xs text-gray-500 mb-1">签到时间</div>
                                                <div className="font-mono text-sm">{task.sign_at}</div>
                                                {task.random_seconds > 0 && (
                                                    <div className="text-xs text-gray-400">+随机{Math.round(task.random_seconds / 60)}分钟</div>
                                                )}
                                            </div>

                                            {/* 最后执行 */}
                                            <div>
                                                <div className="text-xs text-gray-500 mb-1">最后执行</div>
                                                {task.last_run ? (
                                                    <div>
                                                        <div className={`text-sm ${task.last_run.success ? 'text-green-600' : 'text-red-600'}`}>
                                                            {task.last_run.success ? '✓ 成功' : '✗ 失败'}
                                                        </div>
                                                        <div className="text-xs text-gray-400">
                                                            {new Date(task.last_run.time).toLocaleString('zh-CN', {
                                                                month: '2-digit',
                                                                day: '2-digit',
                                                                hour: '2-digit',
                                                                minute: '2-digit'
                                                            })}
                                                        </div>
                                                    </div>
                                                ) : (
                                                    <div className="text-sm text-gray-400">从未执行</div>
                                                )}
                                            </div>

                                            {/* 状态 */}
                                            <div>
                                                <div className="text-xs text-gray-500 mb-1">状态</div>
                                                <div className="text-sm text-green-600">已启用</div>
                                            </div>
                                        </div>

                                        {/* 操作按钮 */}
                                        <div className="flex gap-2 ml-4">
                                            <Button
                                                variant="secondary"
                                                size="sm"
                                                onClick={() => handleEditTask(task)}
                                                disabled={loading}
                                            >
                                                编辑
                                            </Button>
                                            <Button
                                                variant="secondary"
                                                size="sm"
                                                onClick={() => handleRunTask(task.name)}
                                                disabled={loading}
                                            >
                                                运行
                                            </Button>
                                            <Button
                                                variant="destructive"
                                                size="sm"
                                                onClick={() => handleDeleteTask(task.name)}
                                                disabled={loading}
                                            >
                                                删除
                                            </Button>
                                        </div>
                                    </div>
                                </CardContent>
                            </Card>
                        ))}
                    </div>
                )
                }
            </div >

            {/* 创建任务对话框 - 与之前相同的代码 */}
            {
                showCreateDialog && (
                    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4 overflow-y-auto">
                        <Card className="w-full max-w-2xl my-8">
                            <CardContent className="p-6">
                                <h2 className="text-xl font-bold mb-4">创建签到任务</h2>

                                <div className="space-y-4 max-h-[70vh] overflow-y-auto px-1">
                                    {/* 基本信息 */}
                                    <div className="grid grid-cols-2 gap-4">
                                        <div>
                                            <Label htmlFor="taskName">任务名称</Label>
                                            <Input
                                                id="taskName"
                                                placeholder="例如: linuxdo_sign"
                                                value={newTask.name}
                                                onChange={(e) => setNewTask({ ...newTask, name: e.target.value })}
                                            />
                                        </div>

                                        <div>
                                            <Label htmlFor="signAt">签到时间（CRON）</Label>
                                            <Input
                                                id="signAt"
                                                placeholder="0 6 * * *"
                                                value={newTask.sign_at}
                                                onChange={(e) => setNewTask({ ...newTask, sign_at: e.target.value })}
                                            />
                                        </div>
                                    </div>

                                    {/* 随机延迟 - 放在签到时间下面 */}
                                    <div>
                                        <Label htmlFor="randomMinutes">随机延迟（分钟）</Label>
                                        <Input
                                            id="randomMinutes"
                                            type="number"
                                            placeholder="0"
                                            value={newTask.random_minutes}
                                            onChange={(e) => setNewTask({
                                                ...newTask,
                                                random_minutes: parseInt(e.target.value) || 0,
                                            })}
                                        />
                                        <p className="text-xs text-gray-500 mt-1">在签到时间基础上增加随机延迟，更自然</p>
                                    </div>

                                    {/* Chat 配置 */}
                                    <div className="border-t pt-4">
                                        <h3 className="font-medium mb-3">Chat 配置</h3>

                                        {/* 选择 Chat 和 手动输入 - 同一行 */}
                                        <div className="flex gap-4 mb-4">
                                            <div className="flex-1">
                                                <Label className="mb-2 block">选择 Chat</Label>
                                                <select
                                                    className="w-full p-2 border rounded"
                                                    value={newTask.chat_id}
                                                    onChange={(e) => {
                                                        const chatId = parseInt(e.target.value);
                                                        const chat = chats.find(c => c.id === chatId);
                                                        setNewTask({
                                                            ...newTask,
                                                            chat_id: chatId,
                                                            chat_id_manual: "",
                                                            chat_name: chat?.title || chat?.username || "",
                                                        });
                                                    }}
                                                >
                                                    <option value={0}>选择 Chat...</option>
                                                    {chats.map((chat) => (
                                                        <option key={chat.id} value={chat.id}>
                                                            {chat.title || chat.username || chat.first_name || `Chat ${chat.id}`}
                                                        </option>
                                                    ))}
                                                </select>
                                            </div>

                                            <div className="flex-1">
                                                <Label className="mb-2 block">或手动输入 Chat ID</Label>
                                                <Input
                                                    placeholder="输入 Chat ID"
                                                    value={newTask.chat_id_manual}
                                                    onChange={(e) => setNewTask({
                                                        ...newTask,
                                                        chat_id_manual: e.target.value,
                                                        chat_id: 0,
                                                    })}
                                                />
                                            </div>
                                        </div>

                                        {/* 删除延迟和动作间隔 - 同一行 */}
                                        <div className="flex gap-4">
                                            <div className="flex-1">
                                                <Label htmlFor="actionInterval">动作间隔（秒）</Label>
                                                <Input
                                                    id="actionInterval"
                                                    type="number"
                                                    value={newTask.action_interval}
                                                    onChange={(e) => setNewTask({
                                                        ...newTask,
                                                        action_interval: parseInt(e.target.value) || 1,
                                                    })}
                                                />
                                                <p className="text-xs text-gray-500 mt-1">动作之间的间隔</p>
                                            </div>
                                            <div className="flex-1">
                                                <Label htmlFor="deleteAfter">删除延迟（秒）</Label>
                                                <Input
                                                    id="deleteAfter"
                                                    type="number"
                                                    placeholder="不删除"
                                                    value={newTask.delete_after || ""}
                                                    onChange={(e) => setNewTask({
                                                        ...newTask,
                                                        delete_after: e.target.value ? parseInt(e.target.value) : undefined,
                                                    })}
                                                />
                                                <p className="text-xs text-gray-500 mt-1">发送后删除，留空不删除</p>
                                            </div>
                                        </div>
                                    </div>

                                    {/* 动作配置 */}
                                    <div className="border-t pt-4">
                                        <div className="flex items-center justify-between mb-3">
                                            <h3 className="font-medium">动作序列</h3>
                                            <button
                                                onClick={handleAddAction}
                                                className="p-1.5 hover:bg-gray-100 rounded-lg transition-colors text-blue-600"
                                                title="添加动作"
                                            >
                                                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                                                </svg>
                                            </button>
                                        </div>

                                        <div className="space-y-3">
                                            {newTask.actions.map((action, index) => (
                                                <div key={index} className="p-3 bg-gray-50 rounded flex items-start gap-3">
                                                    <div className="flex-1 space-y-2">
                                                        <select
                                                            className="w-full p-2 border rounded text-sm"
                                                            value={action.action}
                                                            onChange={(e) => handleUpdateAction(index, "action", parseInt(e.target.value))}
                                                        >
                                                            <option value={1}>发送文本</option>
                                                            <option value={2}>发送骰子</option>
                                                            <option value={3}>点击按钮</option>
                                                            <option value={4}>AI 图片识别</option>
                                                            <option value={5}>AI 计算题</option>
                                                        </select>

                                                        {(action.action === 1 || action.action === 3) && (
                                                            <Input
                                                                placeholder={action.action === 1 ? "输入要发送的文本" : "输入按钮文本"}
                                                                value={action.text || ""}
                                                                onChange={(e) => handleUpdateAction(index, "text", e.target.value)}
                                                            />
                                                        )}

                                                        {action.action === 2 && (
                                                            <Input
                                                                placeholder="输入骰子表情（如 🎲）"
                                                                value={(action as any).dice || ""}
                                                                onChange={(e) => handleUpdateAction(index, "dice", e.target.value)}
                                                            />
                                                        )}
                                                    </div>
                                                    <button
                                                        onClick={() => handleRemoveAction(index)}
                                                        className="p-1.5 hover:bg-red-100 rounded-lg transition-colors text-red-600"
                                                        title="删除动作"
                                                    >
                                                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                                                        </svg>
                                                    </button>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                </div>

                                {/* 按钮 */}
                                <div className="flex gap-2 pt-4 mt-4 border-t">
                                    <Button
                                        variant="secondary"
                                        onClick={() => setShowCreateDialog(false)}
                                        className="flex-1"
                                    >
                                        取消
                                    </Button>
                                    <Button
                                        onClick={handleCreateTask}
                                        disabled={loading}
                                        className="flex-1"
                                    >
                                        {loading ? "创建中..." : "创建任务"}
                                    </Button>
                                </div>
                            </CardContent>
                        </Card>
                    </div>
                )
            }

            {/* 编辑任务对话框 */}
            {
                showEditDialog && (
                    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
                        <Card className="w-full max-w-md">
                            <CardContent className="p-6">
                                <h2 className="text-xl font-bold mb-4">编辑任务: {editingTaskName}</h2>

                                <div className="space-y-4">
                                    <div>
                                        <Label htmlFor="editSignAt">签到时间（CRON）</Label>
                                        <Input
                                            id="editSignAt"
                                            placeholder="0 6 * * *"
                                            value={editTask.sign_at}
                                            onChange={(e) => setEditTask({ ...editTask, sign_at: e.target.value })}
                                        />
                                    </div>

                                    <div>
                                        <Label htmlFor="editRandomMinutes">随机延迟（分钟）</Label>
                                        <Input
                                            id="editRandomMinutes"
                                            type="number"
                                            placeholder="0"
                                            value={editTask.random_minutes}
                                            onChange={(e) => setEditTask({
                                                ...editTask,
                                                random_minutes: parseInt(e.target.value) || 0,
                                            })}
                                        />
                                        <p className="text-xs text-gray-500 mt-1">在签到时间基础上增加随机延迟</p>
                                    </div>

                                    <div className="flex gap-2 pt-4">
                                        <Button
                                            variant="secondary"
                                            onClick={() => setShowEditDialog(false)}
                                            className="flex-1"
                                        >
                                            取消
                                        </Button>
                                        <Button
                                            onClick={handleSaveEdit}
                                            disabled={loading}
                                            className="flex-1"
                                        >
                                            {loading ? "保存中..." : "保存"}
                                        </Button>
                                    </div>
                                </div>
                            </CardContent>
                        </Card>
                    </div>
                )
            }
        </div >
    );
}

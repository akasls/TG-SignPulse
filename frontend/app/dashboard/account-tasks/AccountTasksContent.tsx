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
        chat_id: 0,
        chat_id_manual: "",
        chat_name: "",
        actions: [{ action: 1, text: "" }] as any[],
        delete_after: undefined as number | undefined,
        action_interval: 1,
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
        const chat = task.chats[0];
        setEditTask({
            sign_at: task.sign_at,
            random_minutes: Math.round(task.random_seconds / 60),
            chat_id: chat?.chat_id || 0,
            chat_id_manual: chat?.chat_id?.toString() || "",
            chat_name: chat?.name || "",
            actions: chat?.actions || [{ action: 1, text: "" }],
            delete_after: chat?.delete_after,
            action_interval: chat?.action_interval || 1,
        });
        setShowEditDialog(true);
    };

    const handleSaveEdit = async () => {
        if (!token) return;

        // 验证 Chat ID
        const chatId = editTask.chat_id || parseInt(editTask.chat_id_manual) || 0;
        if (!chatId) {
            setError("请选择或输入 Chat ID");
            return;
        }

        if (editTask.actions.length === 0 || !editTask.actions[0].text) {
            setError("请至少添加一个动作");
            return;
        }

        try {
            setLoading(true);
            setError("");

            await updateSignTask(token, editingTaskName, {
                sign_at: editTask.sign_at,
                random_seconds: editTask.random_minutes * 60,
                chats: [{
                    chat_id: chatId,
                    name: editTask.chat_name || `Chat ${chatId}`,
                    actions: editTask.actions,
                    delete_after: editTask.delete_after,
                    action_interval: editTask.action_interval,
                }],
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

    const handleEditAddAction = () => {
        setEditTask({
            ...editTask,
            actions: [...editTask.actions, { action: 1, text: "" }],
        });
    };

    const handleEditRemoveAction = (index: number) => {
        if (editTask.actions.length <= 1) return;
        setEditTask({
            ...editTask,
            actions: editTask.actions.filter((_, i) => i !== index),
        });
    };

    if (!token) {
        return null;
    }

    return (
        <div className="min-h-screen">
            {/* 动态流光背景 */}
            <div className="fixed inset-0 overflow-hidden pointer-events-none">
                <div className="absolute top-1/4 left-1/4 w-[500px] h-[500px] bg-violet-600/20 rounded-full blur-[120px] animate-glow-move"></div>
                <div className="absolute bottom-1/3 right-1/4 w-[400px] h-[400px] bg-cyan-500/15 rounded-full blur-[100px] animate-glow-move-reverse"></div>
                <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-pink-500/10 rounded-full blur-[150px] animate-glow-pulse"></div>
            </div>

            {/* 导航栏 */}
            <nav className="glass border-b border-white/10 sticky top-0 z-50">
                <div className="max-w-7xl mx-auto px-6 py-4">
                    <div className="flex items-center justify-between">
                        {/* 左边：返回箭头 + 面包屑导航 */}
                        <div className="flex items-center gap-3">
                            <Link
                                href="/dashboard"
                                className="p-2.5 hover:bg-white/10 rounded-xl transition-all text-white/70 hover:text-white"
                                title="返回"
                            >
                                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                                </svg>
                            </Link>
                            <div className="flex items-center gap-2 text-sm">
                                <Link href="/dashboard" className="text-white/50 hover:text-white transition-colors">
                                    首页
                                </Link>
                                <span className="text-white/30">/</span>
                                <span className="text-white font-medium">{accountName}</span>
                            </div>
                        </div>

                        {/* 右边：新增任务图标 */}
                        <button
                            onClick={() => setShowCreateDialog(true)}
                            className="p-2.5 hover:bg-white/10 rounded-xl transition-all text-white/70 hover:text-white"
                            title="新增任务"
                        >
                            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                            </svg>
                        </button>
                    </div>
                </div>
            </nav>

            {/* 主内容 */}
            <div className="max-w-7xl mx-auto px-6 py-8 page-transition relative z-10">
                {/* 错误和成功提示 */}
                {error && (
                    <div className="mb-4 p-4 bg-rose-500/10 border border-rose-500/20 rounded-xl text-rose-300 flex items-center justify-between animate-fade-in">
                        <span>{error}</span>
                        <button onClick={() => setError("")} className="ml-2 text-rose-300 hover:text-rose-200">×</button>
                    </div>
                )}
                {success && (
                    <div className="mb-4 p-4 bg-emerald-500/10 border border-emerald-500/20 rounded-xl text-emerald-300 flex items-center justify-between animate-fade-in">
                        <span>{success}</span>
                        <button onClick={() => setSuccess("")} className="ml-2 text-emerald-300 hover:text-emerald-200">×</button>
                    </div>
                )}

                {/* 任务列表 */}
                {loading && tasks.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-16">
                        <div className="loading-spinner mb-4"></div>
                        <span className="text-white/50">加载中...</span>
                    </div>
                ) : tasks.length === 0 ? (
                    <Card>
                        <CardContent className="py-16 text-center text-white/50">
                            <div className="text-5xl mb-4">📋</div>
                            <p className="mb-6 text-lg">暂无任务</p>
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
                                    {/* 新的移动端优化布局 */}
                                    <div className="grid grid-cols-[1fr_auto] lg:grid-cols-[1fr_1fr_1fr_1fr_auto] gap-3 lg:gap-4 items-start lg:items-center">
                                        {/* 任务名称 */}
                                        <div>
                                            <div className="text-xs text-white/50 mb-1">任务名称</div>
                                            <div className="font-medium truncate text-white">{task.name}</div>
                                        </div>

                                        {/* Chat ID + 编辑按钮(移动端) */}
                                        <div className="flex items-start gap-2">
                                            <div className="flex-1">
                                                <div className="text-xs text-white/50 mb-1">Chat ID</div>
                                                <div className="font-mono text-sm truncate text-white/80">
                                                    {task.chats[0]?.chat_id || "-"}
                                                </div>
                                            </div>
                                            {/* 编辑按钮 - 移动端显示在右上 */}
                                            <button
                                                onClick={() => handleEditTask(task)}
                                                disabled={loading}
                                                className="lg:hidden p-2 text-white/60 hover:text-cyan-400 hover:bg-white/5 rounded-lg transition-all"
                                                title="编辑"
                                            >
                                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                                                </svg>
                                            </button>
                                        </div>

                                        {/* 签到时间 + 运行按钮(移动端) */}
                                        <div className="flex items-start gap-2">
                                            <div className="flex-1">
                                                <div className="text-xs text-white/50 mb-1">签到时间</div>
                                                <div className="font-mono text-sm text-white/80">{task.sign_at}</div>
                                                {task.random_seconds > 0 && (
                                                    <div className="text-xs text-white/40">+随机{Math.round(task.random_seconds / 60)}分钟</div>
                                                )}
                                            </div>
                                            {/* 运行按钮 - 移动端 */}
                                            <button
                                                onClick={() => handleRunTask(task.name)}
                                                disabled={loading}
                                                className="lg:hidden p-2 text-white/60 hover:text-emerald-400 hover:bg-white/5 rounded-lg transition-all"
                                                title="运行"
                                            >
                                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                                                </svg>
                                            </button>
                                        </div>

                                        {/* 最后执行 + 删除按钮(移动端) */}
                                        <div className="flex items-start gap-2">
                                            <div className="flex-1">
                                                <div className="text-xs text-white/50 mb-1">最后执行</div>
                                                {task.last_run ? (
                                                    <div>
                                                        <div className={`text-sm ${task.last_run.success ? 'text-emerald-400' : 'text-rose-400'}`}>
                                                            {task.last_run.success ? '✓ 成功' : '✗ 失败'}
                                                        </div>
                                                        <div className="text-xs text-white/40">
                                                            {new Date(task.last_run.time).toLocaleString('zh-CN', {
                                                                month: '2-digit',
                                                                day: '2-digit',
                                                                hour: '2-digit',
                                                                minute: '2-digit'
                                                            })}
                                                        </div>
                                                    </div>
                                                ) : (
                                                    <div className="text-sm text-white/40">从未执行</div>
                                                )}
                                            </div>
                                            {/* 删除按钮 - 移动端 */}
                                            <button
                                                onClick={() => handleDeleteTask(task.name)}
                                                disabled={loading}
                                                className="lg:hidden p-2 text-white/60 hover:text-rose-400 hover:bg-white/5 rounded-lg transition-all"
                                                title="删除"
                                            >
                                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                                                </svg>
                                            </button>
                                        </div>

                                        {/* 桌面端操作按钮 */}
                                        <div className="hidden lg:flex gap-1 flex-shrink-0">
                                            <button
                                                onClick={() => handleEditTask(task)}
                                                disabled={loading}
                                                className="p-2 text-white/60 hover:text-cyan-400 hover:bg-white/10 rounded-lg transition-all"
                                                title="编辑"
                                            >
                                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                                                </svg>
                                            </button>
                                            <button
                                                onClick={() => handleRunTask(task.name)}
                                                disabled={loading}
                                                className="p-2 text-white/60 hover:text-emerald-400 hover:bg-white/10 rounded-lg transition-all"
                                                title="运行"
                                            >
                                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                                                </svg>
                                            </button>
                                            <button
                                                onClick={() => handleDeleteTask(task.name)}
                                                disabled={loading}
                                                className="p-2 text-white/60 hover:text-rose-400 hover:bg-white/10 rounded-lg transition-all"
                                                title="删除"
                                            >
                                                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                                                </svg>
                                            </button>
                                        </div>
                                    </div>
                                </CardContent>
                            </Card>
                        ))}
                    </div>
                )
                }
            </div >

            {/* 创建任务对话框 */}
            {
                showCreateDialog && (
                    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4 overflow-y-auto">
                        <Card className="w-full max-w-2xl my-8">
                            <CardContent className="p-6">
                                <h2 className="text-xl font-bold mb-4">创建签到任务</h2>

                                <div className="space-y-4 max-h-[70vh] overflow-y-auto px-1">
                                    {/* 基本信息 - 与编辑对话框一致的布局 */}
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

                                    <div className="grid grid-cols-2 gap-4">
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
                                        </div>
                                        <div></div>
                                    </div>

                                    {/* Chat 设置 */}
                                    <div className="space-y-3">
                                        <div className="flex gap-4">
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
                                            </div>
                                        </div>
                                    </div>

                                    {/* 动作配置 */}
                                    <div>
                                        <div className="flex items-center justify-between mb-2">
                                            <Label>签到动作</Label>
                                            <Button
                                                type="button"
                                                variant="secondary"
                                                size="sm"
                                                onClick={handleAddAction}
                                            >
                                                添加动作
                                            </Button>
                                        </div>

                                        <div className="space-y-2">
                                            {newTask.actions.map((action, index) => (
                                                <div key={index} className="flex gap-2 items-start p-3 bg-white/5 rounded">
                                                    <select
                                                        className="p-2 border rounded min-w-[140px]"
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
                                                            className="flex-1"
                                                            placeholder={action.action === 1 ? "发送的文本" : "按钮文本"}
                                                            value={action.text || ""}
                                                            onChange={(e) => handleUpdateAction(index, "text", e.target.value)}
                                                        />
                                                    )}

                                                    {action.action === 2 && (
                                                        <Input
                                                            className="flex-1"
                                                            placeholder="骰子表情 (🎲🎯🏀⚽🎰🎳)"
                                                            value={(action as any).dice || ""}
                                                            onChange={(e) => handleUpdateAction(index, "dice", e.target.value)}
                                                        />
                                                    )}

                                                    {(action.action === 4 || action.action === 5) && (
                                                        <div className="flex-1 text-sm text-white/50 py-2">
                                                            {action.action === 4 ? "AI 将自动识别图片选项" : "AI 将自动计算答案"}
                                                        </div>
                                                    )}

                                                    {newTask.actions.length > 1 && (
                                                        <Button
                                                            type="button"
                                                            variant="destructive"
                                                            size="sm"
                                                            onClick={() => handleRemoveAction(index)}
                                                        >
                                                            删除
                                                        </Button>
                                                    )}
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                </div>

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
                    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4 overflow-y-auto">
                        <Card className="w-full max-w-2xl my-8">
                            <CardContent className="p-6">
                                <h2 className="text-xl font-bold mb-4">编辑任务: {editingTaskName}</h2>

                                <div className="space-y-4 max-h-[70vh] overflow-y-auto px-1">
                                    {/* 基本信息 */}
                                    <div className="grid grid-cols-2 gap-4">
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
                                        </div>
                                    </div>

                                    {/* Chat 设置 */}
                                    <div className="space-y-3">
                                        <div className="flex gap-4">
                                            <div className="flex-1">
                                                <Label className="mb-2 block">选择 Chat</Label>
                                                <select
                                                    className="w-full p-2 border rounded"
                                                    value={editTask.chat_id}
                                                    onChange={(e) => {
                                                        const id = parseInt(e.target.value);
                                                        const chat = chats.find(c => c.id === id);
                                                        setEditTask({
                                                            ...editTask,
                                                            chat_id: id,
                                                            chat_id_manual: "",
                                                            chat_name: chat?.title || "",
                                                        });
                                                    }}
                                                >
                                                    <option value={0}>选择 Chat...</option>
                                                    {chats.map(chat => (
                                                        <option key={chat.id} value={chat.id}>
                                                            {chat.title || chat.username || chat.id}
                                                        </option>
                                                    ))}
                                                </select>
                                            </div>

                                            <div className="flex-1">
                                                <Label className="mb-2 block">或手动输入 Chat ID</Label>
                                                <Input
                                                    placeholder="输入 Chat ID"
                                                    value={editTask.chat_id_manual}
                                                    onChange={(e) => setEditTask({
                                                        ...editTask,
                                                        chat_id_manual: e.target.value,
                                                        chat_id: 0,
                                                    })}
                                                />
                                            </div>
                                        </div>

                                        <div className="flex gap-4">
                                            <div className="flex-1">
                                                <Label htmlFor="editActionInterval">动作间隔（秒）</Label>
                                                <Input
                                                    id="editActionInterval"
                                                    type="number"
                                                    value={editTask.action_interval}
                                                    onChange={(e) => setEditTask({
                                                        ...editTask,
                                                        action_interval: parseInt(e.target.value) || 1,
                                                    })}
                                                />
                                            </div>
                                            <div className="flex-1">
                                                <Label htmlFor="editDeleteAfter">删除延迟（秒）</Label>
                                                <Input
                                                    id="editDeleteAfter"
                                                    type="number"
                                                    placeholder="不删除"
                                                    value={editTask.delete_after || ""}
                                                    onChange={(e) => setEditTask({
                                                        ...editTask,
                                                        delete_after: e.target.value ? parseInt(e.target.value) : undefined,
                                                    })}
                                                />
                                            </div>
                                        </div>
                                    </div>

                                    {/* 动作配置 */}
                                    <div>
                                        <div className="flex items-center justify-between mb-2">
                                            <Label>签到动作</Label>
                                            <Button
                                                type="button"
                                                variant="secondary"
                                                size="sm"
                                                onClick={handleEditAddAction}
                                            >
                                                添加动作
                                            </Button>
                                        </div>

                                        <div className="space-y-2">
                                            {editTask.actions.map((action, index) => (
                                                <div key={index} className="flex gap-2 items-start p-3 bg-white/5 rounded">
                                                    <select
                                                        className="p-2 border rounded min-w-[140px]"
                                                        value={action.action}
                                                        onChange={(e) => {
                                                            const newActions = [...editTask.actions];
                                                            newActions[index] = { action: parseInt(e.target.value), text: action.text || "" };
                                                            setEditTask({ ...editTask, actions: newActions });
                                                        }}
                                                    >
                                                        <option value={1}>发送文本</option>
                                                        <option value={2}>发送骰子</option>
                                                        <option value={3}>点击按钮</option>
                                                        <option value={4}>AI 图片识别</option>
                                                        <option value={5}>AI 计算题</option>
                                                    </select>

                                                    {(action.action === 1 || action.action === 3) && (
                                                        <Input
                                                            className="flex-1"
                                                            placeholder={action.action === 1 ? "发送的文本" : "按钮文本"}
                                                            value={action.text || ""}
                                                            onChange={(e) => {
                                                                const newActions = [...editTask.actions];
                                                                newActions[index] = { ...action, text: e.target.value };
                                                                setEditTask({ ...editTask, actions: newActions });
                                                            }}
                                                        />
                                                    )}

                                                    {action.action === 2 && (
                                                        <Input
                                                            className="flex-1"
                                                            placeholder="骰子表情 (🎲🎯🏀⚽🎰🎳)"
                                                            value={action.dice || action.text || ""}
                                                            onChange={(e) => {
                                                                const newActions = [...editTask.actions];
                                                                newActions[index] = { ...action, dice: e.target.value, text: e.target.value };
                                                                setEditTask({ ...editTask, actions: newActions });
                                                            }}
                                                        />
                                                    )}

                                                    {(action.action === 4 || action.action === 5) && (
                                                        <div className="flex-1 text-sm text-white/50 py-2">
                                                            {action.action === 4 ? "AI 将自动识别图片选项" : "AI 将自动计算答案"}
                                                        </div>
                                                    )}

                                                    {editTask.actions.length > 1 && (
                                                        <Button
                                                            type="button"
                                                            variant="destructive"
                                                            size="sm"
                                                            onClick={() => handleEditRemoveAction(index)}
                                                        >
                                                            删除
                                                        </Button>
                                                    )}
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                </div>

                                <div className="flex gap-2 pt-4 mt-4 border-t">
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
                            </CardContent>
                        </Card>
                    </div>
                )
            }
        </div >
    );
}

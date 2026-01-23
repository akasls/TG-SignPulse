"use client";

import { useEffect, useState, memo, useMemo } from "react";
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
import {
    CaretLeft,
    Plus,
    Play,
    PencilSimple,
    Trash,
    Spinner,
    Clock,
    ChatCircleText,
    CheckCircle,
    XCircle,
    Hourglass,
    ArrowClockwise,
    X,
    DotsThreeVertical,
    DiceFive,
    Robot,
    MathOperations,
    Lightning
} from "@phosphor-icons/react";
import { ToastContainer, useToast } from "../../../components/ui/toast";
import { ThemeLanguageToggle } from "../../../components/ThemeLanguageToggle";
import { useLanguage } from "../../../context/LanguageContext";

// Memoized Task Item Component
const TaskItem = memo(({ task, loading, onEdit, onRun, onDelete, t, language }: {
    task: SignTask;
    loading: boolean;
    onEdit: (task: SignTask) => void;
    onRun: (name: string) => void;
    onDelete: (name: string) => void;
    t: (key: string) => string;
    language: string;
}) => {
    return (
        <div className="glass-panel p-5 flex flex-col md:flex-row md:items-center justify-between gap-5 group hover:border-[#8a3ffc]/30 transition-all">
            <div className="flex items-center gap-4 flex-1 min-w-0">
                <div className="w-10 h-10 rounded-xl bg-[#8a3ffc]/10 flex items-center justify-center text-[#b57dff]">
                    <ChatCircleText weight="bold" size={20} />
                </div>
                <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 mb-1">
                        <h3 className="font-bold truncate text-sm" title={task.name}>{task.name}</h3>
                        <span className="text-[9px] font-mono text-main/30 bg-white/5 px-1.5 py-0.5 rounded border border-white/5">
                            {task.chats[0]?.chat_id || "-"}
                        </span>
                    </div>
                    <div className="flex items-center gap-3">
                        <div className="flex items-center gap-1.5 text-main/40">
                            <Clock weight="bold" size={12} />
                            <span className="text-[10px] font-bold font-mono uppercase tracking-wider">
                                {task.execution_mode === "range" && task.range_start && task.range_end
                                    ? `${task.range_start} - ${task.range_end}`
                                    : task.sign_at}
                            </span>
                        </div>
                        {task.random_seconds > 0 && (
                            <div className="flex items-center gap-1 text-[#8a3ffc]/60">
                                <Hourglass weight="bold" size={12} />
                                <span className="text-[10px] font-bold">~{Math.round(task.random_seconds / 60)}m</span>
                            </div>
                        )}
                    </div>
                </div>
            </div>

            <div className="flex items-center gap-8">
                {task.last_run ? (
                    <div className="flex flex-col items-end">
                        <div className={`flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-widest ${task.last_run.success ? 'text-emerald-400' : 'text-rose-400'}`}>
                            {task.last_run.success ? <CheckCircle weight="bold" /> : <XCircle weight="bold" />}
                            {task.last_run.success ? t("success") : t("failure")}
                        </div>
                        <div className="text-[10px] text-main/30 font-mono mt-0.5">
                            {new Date(task.last_run.time).toLocaleString(language === "zh" ? 'zh-CN' : 'en-US', {
                                month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit'
                            })}
                        </div>
                    </div>
                ) : (
                    <div className="text-[10px] text-main/20 font-bold uppercase tracking-widest italic">{t("no_data")}</div>
                )}

                <div className="flex items-center gap-1 bg-black/10 rounded-xl p-1 border border-white/5">
                    <button
                        onClick={() => onRun(task.name)}
                        disabled={loading}
                        className="action-btn !w-8 !h-8 !text-emerald-400 hover:bg-emerald-500/10"
                        title={t("run")}
                    >
                        <Play weight="fill" size={14} />
                    </button>
                    <button
                        onClick={() => onEdit(task)}
                        disabled={loading}
                        className="action-btn !w-8 !h-8"
                        title={t("edit")}
                    >
                        <PencilSimple weight="bold" size={14} />
                    </button>
                    <button
                        onClick={() => onDelete(task.name)}
                        disabled={loading}
                        className="action-btn !w-8 !h-8 !text-rose-400 hover:bg-rose-500/10"
                        title={t("delete")}
                    >
                        <Trash weight="bold" size={14} />
                    </button>
                </div>
            </div>
        </div>
    );
});

TaskItem.displayName = "TaskItem";

export default function AccountTasksContent() {
    const router = useRouter();
    const { t, language } = useLanguage();
    const searchParams = useSearchParams();
    const accountName = searchParams.get("name") || "";
    const { toasts, addToast, removeToast } = useToast();

    const [token, setLocalToken] = useState<string | null>(null);
    const [tasks, setTasks] = useState<SignTask[]>([]);
    const [chats, setChats] = useState<ChatInfo[]>([]);
    const [loading, setLoading] = useState(false);
    const [refreshingChats, setRefreshingChats] = useState(false);

    // 创建任务对话框
    const [showCreateDialog, setShowCreateDialog] = useState(false);
    const [newTask, setNewTask] = useState({
        name: "",
        sign_at: "0 6 * * *",
        random_minutes: 0,
        chat_id: 0,
        chat_id_manual: "",
        chat_name: "",
        actions: [{ action: 1, text: "" }],
        delete_after: undefined as number | undefined,
        action_interval: 1,
        execution_mode: "range" as "fixed" | "range",
        range_start: "09:00",
        range_end: "18:00",
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
        execution_mode: "fixed" as "fixed" | "range",
        range_start: "09:00",
        range_end: "18:00",
    });

    const [checking, setChecking] = useState(true);

    useEffect(() => {
        const tokenStr = getToken();
        if (!tokenStr) {
            window.location.replace("/");
            return;
        }
        if (!accountName) {
            window.location.replace("/dashboard");
            return;
        }
        setLocalToken(tokenStr);
        setChecking(false);
        loadData(tokenStr);
    }, [accountName]);

    const loadData = async (tokenStr: string) => {
        try {
            setLoading(true);
            const [tasksData, chatsData] = await Promise.all([
                listSignTasks(tokenStr, accountName),
                getAccountChats(tokenStr, accountName),
            ]);

            setTasks(tasksData);
            setChats(chatsData);
        } catch (err: any) {
            addToast(err.message || (language === "zh" ? "加载数据失败" : "Load failed"), "error");
        } finally {
            setLoading(false);
        }
    };

    const handleRefreshChats = async () => {
        if (!token || !accountName) return;
        try {
            setRefreshingChats(true);
            const chatsData = await getAccountChats(token, accountName, true);
            setChats(chatsData);
            addToast(language === "zh" ? "对话列表已刷新" : "Chat list refreshed", "success");
        } catch (err: any) {
            addToast(err.message || (language === "zh" ? "刷新失败" : "Refresh failed"), "error");
        } finally {
            setRefreshingChats(false);
        }
    };

    const refreshChats = async () => {
        if (!token) return;
        try {
            setLoading(true);
            const chatsData = await getAccountChats(token, accountName);
            setChats(chatsData);
            addToast(language === "zh" ? "Chat 列表已刷新" : "Chats refreshed", "success");
        } catch (err: any) {
            addToast(err.message || (language === "zh" ? "刷新失败" : "Refresh failed"), "error");
        } finally {
            setLoading(false);
        }
    };

    const handleDeleteTask = async (taskName: string) => {
        if (!token) return;

        if (!confirm(t("confirm_delete"))) {
            return;
        }

        try {
            setLoading(true);
            await deleteSignTask(token, taskName);
            // addToast(language === "zh" ? `任务 ${taskName} 已删除` : `Task ${taskName} deleted`, "success"); // Removed toast as per user request to just refresh
            await loadData(token);
        } catch (err: any) {
            // Only show error if it's NOT a 404 (already deleted/doesn't exist)
            if (err.status !== 404 && !err.message?.includes("not exist")) {
                addToast(err.message || (language === "zh" ? "删除任务失败" : "Delete failed"), "error");
            } else {
                await loadData(token); // Refresh anyway if it doesn't exist
            }
        } finally {
            setLoading(false);
        }
    };

    const handleRunTask = async (taskName: string) => {
        if (!token) return;

        try {
            setLoading(true);
            const result = await runSignTask(token, taskName, accountName);

            if (result.success) {
                addToast(language === "zh" ? `任务 ${taskName} 运行成功` : `Task ${taskName} running`, "success");
            } else {
                addToast((language === "zh" ? "任务运行失败: " : "Run failed: ") + result.error, "error");
            }
        } catch (err: any) {
            addToast(err.message || (language === "zh" ? "运行任务失败" : "Run failed"), "error");
        } finally {
            setLoading(false);
        }
    };

    const handleCreateTask = async () => {
        if (!token) return;

        if (!newTask.name) {
            addToast(language === "zh" ? "请输入任务名称" : "Enter task name", "error");
            return;
        }

        if (!newTask.sign_at) {
            addToast(language === "zh" ? "请输入签到时间" : "Enter sign-in time", "error");
            return;
        }

        let chatId = newTask.chat_id;
        if (newTask.chat_id_manual) {
            chatId = parseInt(newTask.chat_id_manual);
            if (isNaN(chatId)) {
                addToast(language === "zh" ? "手动输入的 Chat ID 必须是数字" : "Chat ID must be a number", "error");
                return;
            }
        }

        if (chatId === 0) {
            addToast(language === "zh" ? "请选择或输入 Chat ID" : "Select or enter Chat ID", "error");
            return;
        }

        if (newTask.actions.length === 0 || !newTask.actions[0].text && newTask.actions[0].action !== 2 && newTask.actions[0].action !== 4 && newTask.actions[0].action !== 5) {
            addToast(language === "zh" ? "请确认动作配置" : "Confirm action config", "error");
            return;
        }

        try {
            setLoading(true);

            const request: CreateSignTaskRequest = {
                name: newTask.name,
                account_name: accountName,
                sign_at: newTask.sign_at,
                chats: [{
                    chat_id: chatId,
                    name: newTask.chat_name || `Chat ${chatId}`,
                    actions: newTask.actions,
                    delete_after: newTask.delete_after,
                    action_interval: newTask.action_interval,
                }],
                random_seconds: newTask.random_minutes * 60,
                execution_mode: newTask.execution_mode,
                range_start: newTask.range_start,
                range_end: newTask.range_end,
            };

            await createSignTask(token, request);
            addToast(language === "zh" ? "任务创建成功！" : "Task created!", "success");
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
                execution_mode: "fixed",
                range_start: "09:00",
                range_end: "18:00",
            });
            await loadData(token);
        } catch (err: any) {
            addToast(err.message || (language === "zh" ? "创建任务失败" : "Create failed"), "error");
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
            execution_mode: task.execution_mode || "fixed",
            range_start: task.range_start || "09:00",
            range_end: task.range_end || "18:00",
        });
        setShowEditDialog(true);
    };

    const handleSaveEdit = async () => {
        if (!token) return;

        const chatId = editTask.chat_id || parseInt(editTask.chat_id_manual) || 0;
        if (!chatId) {
            addToast(language === "zh" ? "请选择或输入 Chat ID" : "Select or enter Chat ID", "error");
            return;
        }

        try {
            setLoading(true);

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
                execution_mode: editTask.execution_mode,
                range_start: editTask.range_start,
                range_end: editTask.range_end,
            });

            addToast(language === "zh" ? "任务更新成功！" : "Task updated!", "success");
            setShowEditDialog(false);
            await loadData(token);
        } catch (err: any) {
            addToast(err.message || (language === "zh" ? "更新任务失败" : "Update failed"), "error");
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

    if (!token || checking) {
        return null;
    }

    return (
        <div id="account-tasks-view" className="w-full h-full flex flex-col">
            <nav className="navbar">
                <div className="nav-brand">
                    <div className="flex items-center gap-4">
                        <Link href="/dashboard" className="action-btn !w-8 !h-8" title={t("sidebar_home")}>
                            <CaretLeft weight="bold" size={18} />
                        </Link>
                        <h1 className="text-lg font-bold tracking-tight">{accountName}</h1>
                    </div>
                </div>
                <div className="top-right-actions">
                    <button
                        onClick={refreshChats}
                        disabled={loading}
                        className="action-btn !w-8 !h-8"
                        title={t("refresh_chats")}
                    >
                        <ArrowClockwise weight="bold" size={18} className={loading ? 'animate-spin' : ''} />
                    </button>
                    <button onClick={() => setShowCreateDialog(true)} className="action-btn !w-8 !h-8 !text-[#8a3ffc] hover:bg-[#8a3ffc]/10" title={t("add_task")}>
                        <Plus weight="bold" size={18} />
                    </button>
                </div>
            </nav>

            <main className="main-content !pt-6">

                {loading && tasks.length === 0 ? (
                    <div className="w-full py-20 flex flex-col items-center justify-center text-main/20">
                        <Spinner size={40} weight="bold" className="animate-spin mb-4" />
                        <p className="text-xs uppercase tracking-widest font-bold font-mono">{t("loading")}</p>
                    </div>
                ) : tasks.length === 0 ? (
                    <div className="glass-panel p-20 flex flex-col items-center text-center justify-center border-dashed border-2 group hover:border-[#8a3ffc]/30 transition-all cursor-pointer" onClick={() => setShowCreateDialog(true)}>
                        <div className="w-20 h-20 rounded-3xl bg-main/5 flex items-center justify-center text-main/20 mb-6 group-hover:scale-110 transition-transform group-hover:bg-[#8a3ffc]/10 group-hover:text-[#8a3ffc]">
                            <Plus size={40} weight="bold" />
                        </div>
                        <h3 className="text-xl font-bold mb-2">{t("no_tasks")}</h3>
                        <p className="text-sm text-[#9496a1]">{t("no_tasks_desc")}</p>
                    </div>
                ) : (
                    <div className="flex flex-col gap-3">
                        {tasks.map((task) => (
                            <TaskItem
                                key={task.name}
                                task={task}
                                loading={loading}
                                onEdit={handleEditTask}
                                onRun={handleRunTask}
                                onDelete={handleDeleteTask}
                                t={t}
                                language={language}
                            />
                        ))}
                    </div>
                )}
            </main>

            {/* 创建/编辑对话框通用的渲染逻辑 */}
            {(showCreateDialog || showEditDialog) && (
                <div className="modal-overlay active">
                    <div className="glass-panel modal-content !max-w-xl flex flex-col" onClick={e => e.stopPropagation()}>
                        <header className="modal-header border-b border-white/5 pb-3 mb-2">
                            <div className="modal-title flex items-center gap-2 !text-base">
                                <div className="p-2 bg-[#8a3ffc]/10 rounded-lg text-[#b57dff]">
                                    <Lightning weight="fill" size={20} />
                                </div>
                                {showCreateDialog ? t("create_task") : `${t("edit_task")}: ${editingTaskName}`}
                            </div>
                            <div
                                onClick={() => { setShowCreateDialog(false); setShowEditDialog(false); }}
                                className="modal-close"
                            >
                                <X weight="bold" />
                            </div>
                        </header>

                        <div className="flex-1 overflow-y-auto p-5 space-y-4 custom-scrollbar">
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                {showCreateDialog && (
                                    <div className="mb-2">
                                        <label>{t("task_name")}</label>
                                        <input
                                            className="!mb-0"
                                            placeholder="linuxdo_sign"
                                            value={newTask.name}
                                            onChange={(e) => setNewTask({ ...newTask, name: e.target.value })}
                                        />
                                    </div>
                                )}

                                <div className={showEditDialog ? "md:col-span-2" : ""}>
                                    <div className="mb-2">
                                        <label className="text-xs font-bold uppercase tracking-wider text-main/40 mb-1 block">
                                            {language === "zh" ? "调度模式" : "Scheduling Mode"}
                                        </label>
                                        <select
                                            className="w-full"
                                            value={showCreateDialog ? newTask.execution_mode : editTask.execution_mode}
                                            onChange={(e) => {
                                                const mode = e.target.value as "fixed" | "range";
                                                showCreateDialog
                                                    ? setNewTask({ ...newTask, execution_mode: mode })
                                                    : setEditTask({ ...editTask, execution_mode: mode });
                                            }}
                                        >
                                            <option value="range">{language === "zh" ? "随机时间段 (推荐)" : "Random Range (Recommended)"}</option>
                                            <option value="fixed">{language === "zh" ? "固定时间 (Cron)" : "Fixed Time (Cron)"}</option>
                                        </select>
                                    </div>

                                    {(showCreateDialog ? newTask.execution_mode : editTask.execution_mode) === "fixed" ? (
                                        <div className="mb-2">
                                            <label>{language === "zh" ? "签到时间 (Cron 表达式)" : "Sign-in Time (Cron Expression)"}</label>
                                            <input
                                                className="!mb-0"
                                                placeholder="0 6 * * *"
                                                value={showCreateDialog ? newTask.sign_at : editTask.sign_at}
                                                onChange={(e) => showCreateDialog
                                                    ? setNewTask({ ...newTask, sign_at: e.target.value })
                                                    : setEditTask({ ...editTask, sign_at: e.target.value })
                                                }
                                            />
                                            <div className="text-[10px] text-main/30 mt-1 italic">
                                                Ex: <code>0 9 * * *</code> (9:00 AM)
                                            </div>
                                        </div>
                                    ) : (
                                        <>
                                            <div className="flex gap-2">
                                                <div className="flex-1">
                                                    <label className="text-[10px] font-bold text-main/40 uppercase tracking-wider">{language === "zh" ? "开始" : "Start"}</label>
                                                    <input
                                                        type="time"
                                                        className="!mb-0"
                                                        value={showCreateDialog ? newTask.range_start : editTask.range_start}
                                                        onChange={(e) => showCreateDialog
                                                            ? setNewTask({ ...newTask, range_start: e.target.value })
                                                            : setEditTask({ ...editTask, range_start: e.target.value })
                                                        }
                                                    />
                                                </div>
                                                <div className="flex-1">
                                                    <label className="text-[10px] font-bold text-main/40 uppercase tracking-wider">{language === "zh" ? "结束" : "End"}</label>
                                                    <input
                                                        type="time"
                                                        className="!mb-0"
                                                        value={showCreateDialog ? newTask.range_end : editTask.range_end}
                                                        onChange={(e) => showCreateDialog
                                                            ? setNewTask({ ...newTask, range_end: e.target.value })
                                                            : setEditTask({ ...editTask, range_end: e.target.value })
                                                        }
                                                    />
                                                </div>
                                            </div>
                                            <div className="text-[10px] text-main/30 mt-1 italic">
                                                {language === "zh" ? "将在该时间段内随机选择执行时间" : "Random execution time within this range"}
                                            </div>
                                        </>
                                    )}
                                </div>


                                <div className="mb-2">
                                    <label>{t("action_interval")}</label>
                                    <input
                                        type="text"
                                        className="!mb-0"
                                        value={showCreateDialog ? newTask.action_interval : editTask.action_interval}
                                        onChange={(e) => {
                                            const val = parseInt(e.target.value) || 1;
                                            showCreateDialog
                                                ? setNewTask({ ...newTask, action_interval: val })
                                                : setEditTask({ ...editTask, action_interval: val });
                                        }}
                                    />
                                </div>
                            </div>

                            <div className="glass-panel !bg-black/5 p-4 space-y-4 border-white/5">
                                <div className="flex flex-col md:flex-row gap-4">
                                    <div className="flex-1">
                                        <div className="flex items-center justify-between mb-1">
                                            <label className="!mb-0">{t("select_chat")}</label>
                                            <button
                                                onClick={handleRefreshChats}
                                                disabled={refreshingChats}
                                                className="text-[10px] text-[#8a3ffc] hover:text-[#8a3ffc]/80 transition-colors uppercase font-bold tracking-tighter flex items-center gap-1"
                                                title={language === "zh" ? "从 Telegram 重新获取对话" : "Re-fetch chats from Telegram"}
                                            >
                                                {refreshingChats ? (
                                                    <div className="w-3 h-3 border-2 border-[#8a3ffc] border-t-transparent rounded-full animate-spin"></div>
                                                ) : <ArrowClockwise weight="bold" size={12} />}
                                                {language === "zh" ? "刷新列表" : "Refresh"}
                                            </button>
                                        </div>
                                        <select
                                            className="!mb-0"
                                            value={showCreateDialog ? newTask.chat_id : editTask.chat_id}
                                            onChange={(e) => {
                                                const id = parseInt(e.target.value);
                                                const chat = chats.find(c => c.id === id);
                                                const chatName = chat?.title || chat?.username || "";
                                                if (showCreateDialog) {
                                                    setNewTask({
                                                        ...newTask,
                                                        name: newTask.name || chatName,
                                                        chat_id: id,
                                                        chat_id_manual: id !== 0 ? id.toString() : "",
                                                        chat_name: chatName,
                                                    });
                                                } else {
                                                    setEditTask({
                                                        ...editTask,
                                                        chat_id: id,
                                                        chat_id_manual: id !== 0 ? id.toString() : "",
                                                        chat_name: chatName,
                                                    });
                                                }
                                            }}
                                        >
                                            <option value={0}>{language === "zh" ? "从列表选择..." : "Select from list..."}</option>
                                            {chats.map(chat => (
                                                <option key={chat.id} value={chat.id}>
                                                    {chat.title || chat.username || chat.id}
                                                </option>
                                            ))}
                                        </select>
                                    </div>
                                    <div className="flex-1">
                                        <label className="mb-1 block">{t("manual_chat_id")}</label>
                                        <input
                                            placeholder={t("manual_id_placeholder")}
                                            className="!mb-0"
                                            value={showCreateDialog ? newTask.chat_id_manual : editTask.chat_id_manual}
                                            onChange={(e) => {
                                                if (showCreateDialog) {
                                                    setNewTask({ ...newTask, chat_id_manual: e.target.value, chat_id: 0 });
                                                } else {
                                                    setEditTask({ ...editTask, chat_id_manual: e.target.value, chat_id: 0 });
                                                }
                                            }}
                                        />
                                    </div>
                                </div>
                                <div className="mt-2">
                                    <label>{t("delete_after")}</label>
                                    <input
                                        type="text"
                                        placeholder={t("delete_after_placeholder")}
                                        className="!mb-0"
                                        value={(showCreateDialog ? newTask.delete_after : editTask.delete_after) || ""}
                                        onChange={(e) => {
                                            const val = e.target.value ? parseInt(e.target.value) : undefined;
                                            showCreateDialog
                                                ? setNewTask({ ...newTask, delete_after: val })
                                                : setEditTask({ ...editTask, delete_after: val });
                                        }}
                                    />
                                </div>
                            </div>

                            <div className="space-y-4">
                                <div className="flex items-center justify-between">
                                    <h3 className="text-sm font-bold uppercase tracking-widest text-main/40 flex items-center gap-2">
                                        <DotsThreeVertical weight="bold" />
                                        {t("action_sequence")}
                                    </h3>
                                    <button
                                        onClick={showCreateDialog ? handleAddAction : handleEditAddAction}
                                        className="btn-secondary !h-7 !px-3 !text-[10px]"
                                    >
                                        + {t("add_action")}
                                    </button>
                                </div>

                                <div className="flex flex-col gap-3">
                                    {(showCreateDialog ? newTask.actions : editTask.actions).map((action, index) => (
                                        <div key={index} className="flex gap-3 items-start animate-scale-in">
                                            <div className="shrink-0 w-6 h-10 flex items-center justify-center font-mono text-[10px] text-main/20 font-bold border-r border-white/5">
                                                {index + 1}
                                            </div>
                                            <select
                                                className="!w-[140px] !mb-0"
                                                value={action.action}
                                                onChange={(e) => {
                                                    const val = parseInt(e.target.value);
                                                    if (showCreateDialog) handleUpdateAction(index, "action", val);
                                                    else {
                                                        const newActions = [...editTask.actions];
                                                        newActions[index] = { ...newActions[index], action: val };
                                                        setEditTask({ ...editTask, actions: newActions });
                                                    }
                                                }}
                                            >
                                                <option value={1}>{t("action_send_text")}</option>
                                                <option value={2}>{t("action_send_dice")}</option>
                                                <option value={3}>{t("action_click_button")}</option>
                                                <option value={4}>{t("action_ai_vision")}</option>
                                                <option value={5}>{t("action_ai_logic")}</option>
                                            </select>

                                            <div className="flex-1">
                                                {(action.action === 1 || action.action === 3) && (
                                                    <input
                                                        placeholder={action.action === 1 ? t("placeholder_msg") : t("placeholder_btn")}
                                                        className="!mb-0"
                                                        value={action.text || ""}
                                                        onChange={(e) => {
                                                            if (showCreateDialog) handleUpdateAction(index, "text", e.target.value);
                                                            else {
                                                                const newActions = [...editTask.actions];
                                                                newActions[index] = { ...newActions[index], text: e.target.value };
                                                                setEditTask({ ...editTask, actions: newActions });
                                                            }
                                                        }}
                                                    />
                                                )}
                                                {action.action === 2 && (
                                                    <div className="flex gap-2">
                                                        {['🎲', '🎯', '🏀', '⚽', '🎰', '🎳'].map(d => (
                                                            <button
                                                                key={d}
                                                                className={`w-10 h-10 rounded-xl flex items-center justify-center text-lg transition-all ${((action as any).dice === d) ? 'bg-[#8a3ffc]/20 border border-[#8a3ffc]/40' : 'bg-white/5 border border-white/5 hover:bg-white/10'}`}
                                                                onClick={() => {
                                                                    if (showCreateDialog) handleUpdateAction(index, "dice", d);
                                                                    else {
                                                                        const newActions = [...editTask.actions];
                                                                        newActions[index] = { ...newActions[index], dice: d };
                                                                        setEditTask({ ...editTask, actions: newActions });
                                                                    }
                                                                }}
                                                            >
                                                                {d}
                                                            </button>
                                                        ))}
                                                    </div>
                                                )}
                                                {action.action === 4 && (
                                                    <div className="h-10 px-4 flex items-center gap-2 bg-indigo-500/10 border border-indigo-500/20 rounded-xl text-[#8183ff] text-xs font-bold uppercase tracking-wider">
                                                        <Robot weight="fill" size={16} />
                                                        AI Vision Mode
                                                    </div>
                                                )}
                                                {action.action === 5 && (
                                                    <div className="h-10 px-4 flex items-center gap-2 bg-amber-500/10 border border-amber-500/20 rounded-xl text-amber-400 text-xs font-bold uppercase tracking-wider">
                                                        <MathOperations weight="fill" size={16} />
                                                        AI Logic Solver
                                                    </div>
                                                )}
                                            </div>

                                            <button
                                                onClick={() => showCreateDialog ? handleRemoveAction(index) : handleEditRemoveAction(index)}
                                                className="action-btn !w-10 !h-10 !text-rose-400 !bg-rose-500/5 hover:!bg-rose-500/10"
                                            >
                                                <Trash weight="bold" size={16} />
                                            </button>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        </div>

                        <footer className="p-6 border-t border-white/5 flex gap-3">
                            <button
                                className="btn-secondary flex-1"
                                onClick={() => { setShowCreateDialog(false); setShowEditDialog(false); }}
                            >
                                {t("cancel")}
                            </button>
                            <button
                                className="btn-gradient flex-1"
                                onClick={showCreateDialog ? handleCreateTask : handleSaveEdit}
                                disabled={loading}
                            >
                                {loading ? <Spinner className="animate-spin" /> : (showCreateDialog ? (language === "zh" ? "添加任务" : t("add_task")) : t("save_changes"))}
                            </button>
                        </footer>
                    </div>
                </div>
            )
            }

            <ToastContainer toasts={toasts} removeToast={removeToast} />
        </div >
    );
}

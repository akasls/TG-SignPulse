"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { getToken } from "../../../lib/auth";
import {
    listSignTasks,
    deleteSignTask,
    runSignTask,
    getSignTaskLogs,
    listAccounts,
    SignTask,
    AccountInfo,
} from "../../../lib/api";
import {
    Plus,
    CaretLeft,
    Play,
    PencilSimple,
    Trash,
    Spinner,
    Lightning,
    Clock,
    ChatCircleText,
    ArrowClockwise,
    X,
} from "@phosphor-icons/react";
import { ToastContainer, useToast } from "../../../components/ui/toast";
import { ThemeLanguageToggle } from "../../../components/ThemeLanguageToggle";
import { useLanguage } from "../../../context/LanguageContext";

export default function SignTasksPage() {
    const router = useRouter();
    const { t } = useLanguage();
    const { toasts, addToast, removeToast } = useToast();
    const [token, setLocalToken] = useState<string | null>(null);
    const [tasks, setTasks] = useState<SignTask[]>([]);
    const [accounts, setAccounts] = useState<AccountInfo[]>([]);
    const [loading, setLoading] = useState(false);
    const [checking, setChecking] = useState(true);
    const [runningTask, setRunningTask] = useState<string | null>(null);
    const [runLogs, setRunLogs] = useState<string[]>([]);
    const [isDone, setIsDone] = useState(false);

    const addToastRef = useRef(addToast);
    const tRef = useRef(t);

    useEffect(() => {
        addToastRef.current = addToast;
        tRef.current = t;
    }, [addToast, t]);

    const loadData = useCallback(async (tokenStr: string) => {
        try {
            setLoading(true);
            const [tasksData, accountsData] = await Promise.all([
                listSignTasks(tokenStr),
                listAccounts(tokenStr),
            ]);
            setTasks(tasksData);
            setAccounts(accountsData.accounts);
        } catch (err: any) {
            const toast = addToastRef.current;
            const tr = tRef.current;
            if (toast) {
                toast(err.message || (tr ? tr("login_failed") : "Login failed"), "error");
            }
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        const tokenStr = getToken();
        if (!tokenStr) {
            window.location.replace("/");
            return;
        }
        setLocalToken(tokenStr);
        setChecking(false);
        loadData(tokenStr);
    }, [loadData]);

    const handleDelete = async (task: SignTask) => {
        if (!token) return;

        if (!confirm(t("confirm_delete"))) {
            return;
        }

        try {
            setLoading(true);
            await deleteSignTask(token, task.name, task.account_name);
            addToast(t("delete") + " " + task.name + " " + t("login_success"), "success");
            await loadData(token);
        } catch (err: any) {
            addToast(err.message || t("login_failed"), "error");
        } finally {
            setLoading(false);
        }
    };

    const handleRun = async (taskName: string) => {
        if (!token) return;

        const accountName = prompt(t("username"));
        if (!accountName) return;

        try {
            setLoading(true);
            setRunningTask(taskName);
            setRunLogs([]);
            setIsDone(false);

            // 建立 WebSocket 连接
            const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
            const host = window.location.host;
            // 注意：这里需要确保后端地址正确，如果是在开发环境（localhost:3000 -> localhost:8000）可能需要处理
            const wsParams = new URLSearchParams({
                token,
                account_name: accountName,
            });
            const wsUrl = `${protocol}//${host}/api/sign-tasks/ws/${taskName}?${wsParams.toString()}`;
            const ws = new WebSocket(wsUrl);

            ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                if (data.type === "logs") {
                    setRunLogs(prev => [...prev, ...data.data]);
                } else if (data.type === "done") {
                    setIsDone(true);
                }
            };

            ws.onerror = (err) => {
                console.error("WebSocket error:", err);
            };

            const result = await runSignTask(token, taskName, accountName);

            if (!result.success) {
                addToast(t("login_failed") + ": " + result.error, "error");
                setIsDone(true);
            } else {
                addToast(taskName + " " + t("run") + " " + t("login_success"), "success");
            }
        } catch (err: any) {
            addToast(err.message || t("login_failed"), "error");
            setRunningTask(null);
        } finally {
            setLoading(false);
        }
    };

    if (!token || checking) {
        return null;
    }

    return (
        <div id="tasks-view" className="w-full h-full flex flex-col">
            <nav className="navbar">
                <div className="nav-brand">
                    <div className="flex items-center gap-4">
                        <Link href="/dashboard" className="action-btn !w-8 !h-8" title={t("sidebar_home")}>
                            <CaretLeft weight="bold" size={18} />
                        </Link>
                        <h1 className="text-lg font-bold tracking-tight">{t("sidebar_tasks")}</h1>
                    </div>
                </div>
                <div className="top-right-actions">
                    <button
                        onClick={() => loadData(token)}
                        disabled={loading}
                        className="action-btn !w-8 !h-8"
                        title={t("refresh")}
                    >
                        <ArrowClockwise weight="bold" size={18} className={loading ? 'animate-spin' : ''} />
                    </button>
                    <Link
                        href="/dashboard/sign-tasks/create"
                        className={`action-btn !w-8 !h-8 !text-[#8a3ffc] hover:bg-[#8a3ffc]/10 ${loading ? 'pointer-events-none opacity-20' : ''}`}
                        title={t("add_task")}
                    >
                        <Plus weight="bold" size={18} />
                    </Link>
                </div>
            </nav>

            <main className="main-content !pt-6">

                {loading && tasks.length === 0 ? (
                    <div className="w-full py-20 flex flex-col items-center justify-center text-main/20">
                        <Spinner size={40} weight="bold" className="animate-spin mb-4" />
                        <p className="text-xs uppercase tracking-widest font-bold font-mono">{t("login_loading")}</p>
                    </div>
                ) : tasks.length === 0 ? (
                    <div className="glass-panel p-20 flex flex-col items-center text-center justify-center border-dashed border-2 group hover:border-[#8a3ffc]/30 transition-all cursor-pointer" onClick={() => router.push("/dashboard/sign-tasks/create")}>
                        <div className="w-20 h-20 rounded-3xl bg-main/5 flex items-center justify-center text-main/20 mb-6 group-hover:scale-110 transition-transform group-hover:bg-[#8a3ffc]/10 group-hover:text-[#8a3ffc]">
                            <Plus size={40} weight="bold" />
                        </div>
                        <h3 className="text-xl font-bold mb-2">部署第一个任务</h3>
                        <p className="text-sm text-[#9496a1] mb-8">点击此处或右上角按钮开始创建您的首个自动签到任务</p>
                    </div>
                ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
                        {tasks.map((task) => (
                            <div key={task.name} className="flex flex-col gap-3">
                                <div className="glass-panel p-4 sm:hidden flex items-start justify-between gap-3">
                                    <div className="min-w-0 flex-1 space-y-2">
                                        <div className="flex items-center gap-2">
                                            <span className="font-bold text-sm truncate" title={task.name}>{task.name}</span>
                                            <span className="text-[9px] font-mono text-main/30 bg-white/5 px-1.5 py-0.5 rounded border border-white/5 shrink-0">
                                                {task.chats[0]?.chat_id || "-"}
                                            </span>
                                        </div>
                                        <span className="text-[11px] font-mono text-main/50">
                                            {task.execution_mode === "range" && task.range_start && task.range_end
                                                ? `${task.range_start} - ${task.range_end}`
                                                : task.sign_at}
                                        </span>
                                        <span className={`inline-flex text-[9px] font-bold px-2 py-0.5 rounded-full uppercase tracking-widest border ${task.enabled ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' : 'bg-white/5 text-main/30 border-white/10'}`}>
                                            {task.enabled ? 'Active' : 'Paused'}
                                        </span>
                                    </div>
                                    <div className="flex flex-col items-end gap-2 shrink-0">
                                        <button
                                            onClick={() => handleRun(task.name)}
                                            disabled={loading}
                                            className="action-btn !w-8 !h-8 !text-emerald-400 hover:bg-emerald-500/10 disabled:opacity-20 disabled:cursor-not-allowed"
                                            title={t("run")}
                                        >
                                            <Play weight="fill" size={14} />
                                        </button>
                                        <Link
                                            href={`/dashboard/account-tasks/AccountTasksContent?name=${task.account_name}`}
                                            className={`action-btn !w-8 !h-8 ${loading ? 'pointer-events-none opacity-20' : ''}`}
                                            title={t("edit")}
                                        >
                                            <PencilSimple weight="bold" size={14} />
                                        </Link>
                                        <button
                                            onClick={() => handleDelete(task)}
                                            disabled={loading}
                                            className="action-btn !w-8 !h-8 !text-rose-400 hover:bg-rose-500/10 disabled:opacity-20 disabled:cursor-not-allowed"
                                            title={t("delete")}
                                        >
                                            <Trash weight="bold" size={14} />
                                        </button>
                                    </div>
                                </div>
                                <div className="glass-panel p-6 hidden sm:flex flex-col group hover:border-[#8a3ffc]/40 transition-all">
                                <div className="flex justify-between items-start mb-6">
                                    <div className="flex items-center gap-4">
                                        <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-[#8a3ffc]/20 to-[#e83ffc]/20 flex items-center justify-center text-[#b57dff] group-hover:scale-110 transition-transform">
                                            <Lightning weight="fill" size={24} />
                                        </div>
                                        <div className="min-w-0">
                                            <h3 className="font-bold text-lg truncate pr-2" title={task.name}>{task.name}</h3>
                                            <div className="flex items-center gap-2 mt-1">
                                                <span className={`text-[9px] font-bold px-2 py-0.5 rounded-full uppercase tracking-widest border ${task.enabled ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' : 'bg-white/5 text-main/30 border-white/10'}`}>
                                                    {task.enabled ? 'Active' : 'Paused'}
                                                </span>
                                            </div>
                                        </div>
                                    </div>
                                </div>

                                <div className="space-y-4 mb-8">
                                    <div className="flex items-center justify-between p-3 bg-white/2 rounded-xl border border-white/5">
                                        <div className="flex items-center gap-2 text-main/40">
                                            <Clock weight="bold" size={14} />
                                            <span className="text-[10px] font-bold uppercase tracking-wider">Schedule</span>
                                        </div>
                                        <span className="text-xs font-mono font-bold text-[#b57dff]">{task.sign_at}</span>
                                    </div>
                                    <div className="flex items-center justify-between p-3 bg-white/2 rounded-xl border border-white/5">
                                        <div className="flex items-center gap-2 text-main/40">
                                            <ChatCircleText weight="bold" size={14} />
                                            <span className="text-[10px] font-bold uppercase tracking-wider">Channels</span>
                                        </div>
                                        <span className="text-xs font-mono font-bold text-[#e83ffc]">{task.chats.length} Hits</span>
                                    </div>
                                </div>

                                <div className="mt-auto flex items-center justify-between bg-black/10 -mx-6 -mb-6 p-4 border-t border-white/5">
                                    <div className="flex items-center gap-2">
                                        <button
                                            onClick={() => handleRun(task.name)}
                                            disabled={loading}
                                            className="action-btn !text-emerald-400 hover:bg-emerald-500/10 disabled:opacity-20 disabled:cursor-not-allowed"
                                            title={t("run")}
                                        >
                                            <Play weight="fill" />
                                        </button>
                                        <Link
                                            href={`/dashboard/account-tasks/AccountTasksContent?name=${task.account_name}`}
                                            className={`action-btn ${loading ? 'pointer-events-none opacity-20' : ''}`}
                                            title={t("edit")}
                                        >
                                            <PencilSimple weight="bold" />
                                        </Link>
                                    </div>
                                    <button
                                        onClick={() => handleDelete(task)}
                                        disabled={loading}
                                        className="action-btn !text-rose-400 hover:bg-rose-500/10 disabled:opacity-20 disabled:cursor-not-allowed"
                                        title={t("delete")}
                                    >
                                        <Trash weight="bold" />
                                    </button>
                                </div>
                            </div>
                        </div>
                        ))}
                    </div>
                )}
            </main>

            <ToastContainer toasts={toasts} removeToast={removeToast} />

            {/* 运行日志 Modal */}
            {runningTask && (
                <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 sm:p-6 bg-black/60 backdrop-blur-sm animate-fade-in">
                    <div className="glass-panel w-full max-w-2xl h-[500px] flex flex-col shadow-2xl border border-white/10 overflow-hidden animate-zoom-in">
                        <div className="p-4 border-b border-white/5 flex justify-between items-center bg-white/2">
                            <div className="flex items-center gap-3">
                                <div className="w-8 h-8 rounded-lg bg-[#8a3ffc]/20 flex items-center justify-center text-[#b57dff]">
                                    <Lightning weight="fill" size={18} />
                                </div>
                                <h3 className="font-bold tracking-tight">任务运行日志: {runningTask}</h3>
                            </div>
                            {isDone && (
                                <button
                                    onClick={() => setRunningTask(null)}
                                    className="action-btn !w-8 !h-8 hover:bg-white/10"
                                >
                                    <X weight="bold" />
                                </button>
                            )}
                        </div>
                        <div className="flex-1 overflow-y-auto p-4 font-mono text-[11px] leading-relaxed bg-black/20">
                            {runLogs.length === 0 ? (
                                <div className="flex items-center gap-2 text-main/30 italic">
                                    <Spinner className="animate-spin" size={12} />
                                    等待日志输出...
                                </div>
                            ) : (
                                <div className="space-y-1">
                                    {runLogs.map((log, i) => (
                                        <div key={i} className="text-main/80 flex gap-2">
                                            <span className="text-main/20 select-none w-6 text-right">{(i + 1).toString().padStart(2, '0')}</span>
                                            <span className="break-all">{log}</span>
                                        </div>
                                    ))}
                                    {!isDone && (
                                        <div className="flex items-center gap-2 text-[#8a3ffc] mt-2 italic animate-pulse">
                                            <Spinner className="animate-spin" size={12} />
                                            正在运行中...
                                        </div>
                                    )}
                                    {isDone && (
                                        <div className="text-emerald-400 mt-4 font-bold border-t border-emerald-500/20 pt-4 flex items-center gap-2">
                                            <Lightning weight="fill" />
                                            任务执行完成
                                        </div>
                                    )}
                                </div>
                            )}
                        </div>
                        <div className="p-4 border-t border-white/5 bg-white/2 flex justify-end">
                            <button
                                onClick={() => setRunningTask(null)}
                                disabled={!isDone}
                                className={`px-6 py-2 rounded-xl font-bold text-xs transition-all ${isDone ? 'btn-gradient shadow-lg' : 'bg-white/5 text-main/20 cursor-not-allowed'}`}
                            >
                                {isDone ? '关闭' : '正在执行...'}
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}

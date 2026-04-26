"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { getToken } from "../../../lib/auth";
import {
    listSignTasks,
    deleteSignTask,
    runSignTask,
    getSignTaskHistory,
    listAccounts,
    SignTask,
    SignTaskHistoryItem,
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
    ListDashes,
    ArrowClockwise,
    X,
    Copy,
    ClipboardText
} from "@phosphor-icons/react";
import { ToastContainer, useToast } from "../../../components/ui/toast";
import { ThemeLanguageToggle } from "../../../components/ThemeLanguageToggle";
import { useLanguage } from "../../../context/LanguageContext";

export default function SignTasksPage() {
    const router = useRouter();
    const { t, language } = useLanguage();
    const { toasts, addToast, removeToast } = useToast();
    const [token, setLocalToken] = useState<string | null>(null);
    const [tasks, setTasks] = useState<SignTask[]>([]);
    const [accounts, setAccounts] = useState<AccountInfo[]>([]);
    const [loading, setLoading] = useState(false);
    const [checking, setChecking] = useState(true);
    const [runningTask, setRunningTask] = useState<string | null>(null);
    const [runLogs, setRunLogs] = useState<string[]>([]);
    const [isDone, setIsDone] = useState(false);
    const [historyTask, setHistoryTask] = useState<SignTask | null>(null);
    const [historyLogs, setHistoryLogs] = useState<SignTaskHistoryItem[]>([]);
    const [historyLoading, setHistoryLoading] = useState(false);

    const addToastRef = useRef(addToast);
    const tRef = useRef(t);

    useEffect(() => {
        addToastRef.current = addToast;
        tRef.current = t;
    }, [addToast, t]);

    const formatErrorMessage = useCallback((key: string, err?: any) => {
        const base = tRef.current ? tRef.current(key) : key;
        const code = err?.code;
        return code ? `${base} (${code})` : base;
    }, []);

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
            if (toast) {
                toast(formatErrorMessage("load_failed", err), "error");
            }
        } finally {
            setLoading(false);
        }
    }, [formatErrorMessage]);

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
            addToast(t("task_deleted").replace("{name}", task.name), "success");
            await loadData(token);
        } catch (err: any) {
            addToast(formatErrorMessage("delete_failed", err), "error");
        } finally {
            setLoading(false);
        }
    };

    const handleRun = async (taskName: string) => {
        if (!token) return;

        const accountName = prompt(t("account_name_prompt"));
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
                if (result.error && result.error.includes("运行中")) {
                    addToast(language === "zh" ? "该任务正在运行中，无法重复开始。正在为您展示其实时进度..." : "Task is currently running. Real-time logs are shown below.", "info");
                } else {
                    addToast(result.error || t("task_run_failed"), "error");
                    setIsDone(true);
                }
            } else {
                addToast(t("task_run_success").replace("{name}", taskName), "success");
            }
        } catch (err: any) {
            addToast(formatErrorMessage("task_run_failed", err), "error");
            setRunningTask(null);
        } finally {
            setLoading(false);
        }
    };

    const handleShowTaskHistory = async (task: SignTask) => {
        if (!token) return;
        setHistoryTask(task);
        setHistoryLogs([]);
        setHistoryLoading(true);
        try {
            const logs = await getSignTaskHistory(token, task.name, task.account_name, 30);
            setHistoryLogs(logs);
        } catch (err: any) {
            addToast(formatErrorMessage("logs_fetch_failed", err), "error");
        } finally {
            setHistoryLoading(false);
        }
    };

    const handleExportTasks = async () => {
        if (!token) return;
        try {
            setLoading(true);
            const { exportAllConfigs } = require("../../../lib/api");
            const configStr = await exportAllConfigs(token);
            await navigator.clipboard.writeText(configStr);
            addToast(t("export_success") || "Export successful, copied to clipboard", "success");
        } catch (err: any) {
            addToast(formatErrorMessage("export_failed", err), "error");
        } finally {
            setLoading(false);
        }
    };

    const handleImportTasks = async () => {
        if (!token) return;
        try {
            const text = await navigator.clipboard.readText();
            if (!text) {
                addToast(t("import_empty") || "Clipboard is empty", "error");
                return;
            }
            setLoading(true);
            const { importAllConfigs } = require("../../../lib/api");
            await importAllConfigs(token, text, false);
            addToast(t("import_success") || "Import successful", "success");
            await loadData(token);
        } catch (err: any) {
            addToast(formatErrorMessage("import_failed", err), "error");
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
                        <Link href="/dashboard" className="action-btn" title={t("sidebar_home")}>
                            <CaretLeft weight="bold" />
                        </Link>
                        <h1 className="text-lg font-bold tracking-tight">{t("sidebar_tasks")}</h1>
                    </div>
                </div>
                <div className="top-right-actions">
                    <button
                        onClick={handleExportTasks}
                        disabled={loading}
                        className="action-btn"
                        title={t("export_tasks") || "Export All Tasks to Clipboard"}
                    >
                        <Copy weight="bold" />
                    </button>
                    <button
                        onClick={handleImportTasks}
                        disabled={loading}
                        className="action-btn"
                        title={t("import_tasks") || "Paste to Import Tasks"}
                    >
                        <ClipboardText weight="bold" />
                    </button>
                    <button
                        onClick={() => loadData(token)}
                        disabled={loading}
                        className="action-btn"
                        title={t("refresh_list")}
                    >
                        <ArrowClockwise weight="bold" className={loading ? 'animate-spin' : ''} />
                    </button>
                    <Link
                        href="/dashboard/sign-tasks/create"
                        className={`action-btn !text-[#8a3ffc] hover:bg-[#8a3ffc]/10 ${loading ? 'pointer-events-none opacity-20' : ''}`}
                        title={t("add_task")}
                    >
                        <Plus weight="bold" />
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
                        <h3 className="text-xl font-bold mb-2">{t("no_tasks")}</h3>
                        <p className="text-sm text-[#9496a1] mb-8">{t("no_tasks_desc")}</p>
                    </div>
                ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
                        {tasks.map((task) => (
                            <div key={task.name} className="flex flex-col gap-3">
                                <div className="glass-panel p-4 sm:hidden">
                                    <div className="grid grid-cols-[1fr_auto] gap-3">
                                        <div className="min-w-0 space-y-2">
                                            <div className="flex items-center gap-2">
                                                <Lightning weight="fill" size={12} className="text-[#b57dff] shrink-0" />
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
                                            <div className="space-y-1 pt-2">
                                                <span className={`inline-flex text-[9px] font-bold px-2 py-0.5 rounded-full uppercase tracking-widest border ${task.enabled ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' : 'bg-white/5 text-main/30 border-white/10'}`}>
                                                    {task.enabled ? t("status_active") : t("status_paused")}
                                                </span>
                                                {task.last_run ? (
                                                    <div className="text-[10px] font-mono text-main/40 flex items-center gap-2">
                                                        <span className={task.last_run.success ? 'text-emerald-400' : 'text-rose-400'}>
                                                            {task.last_run.success ? t("success") : t("failure")}
                                                        </span>
                                                        <span>
                                                            {new Date(task.last_run.time).toLocaleString(undefined, {
                                                                month: '2-digit',
                                                                day: '2-digit',
                                                                hour: '2-digit',
                                                                minute: '2-digit'
                                                            })}
                                                        </span>
                                                    </div>
                                                ) : null}
                                            </div>
                                        </div>
                                        <div className="w-14 flex flex-col items-center gap-2 pt-[2px]">
                                            <button
                                                onClick={() => handleRun(task.name)}
                                                disabled={loading}
                                                className="action-btn !w-11 !h-11 !text-emerald-400 hover:bg-emerald-500/10 disabled:opacity-20 disabled:cursor-not-allowed"
                                                title={t("run")}
                                            >
                                                <Play weight="fill" size={14} />
                                            </button>
                                            <Link
                                                href={`/dashboard/account-tasks/AccountTasksContent?name=${task.account_name}`}
                                                className={`action-btn !w-11 !h-11 ${loading ? 'pointer-events-none opacity-20' : ''}`}
                                                title={t("edit")}
                                            >
                                                <PencilSimple weight="bold" size={14} />
                                            </Link>
                                            <button
                                                onClick={() => handleShowTaskHistory(task)}
                                                disabled={loading}
                                                className="action-btn !w-11 !h-11 !text-[#8a3ffc] hover:bg-[#8a3ffc]/10 disabled:opacity-20 disabled:cursor-not-allowed"
                                                title={t("task_history_logs")}
                                            >
                                                <ListDashes weight="bold" size={14} />
                                            </button>
                                            <button
                                                onClick={() => handleDelete(task)}
                                                disabled={loading}
                                                className="action-btn !w-11 !h-11 !text-rose-400 hover:bg-rose-500/10 disabled:opacity-20 disabled:cursor-not-allowed"
                                                title={t("delete")}
                                            >
                                                <Trash weight="bold" size={14} />
                                            </button>
                                        </div>
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
                                                    {task.enabled ? t("status_active") : t("status_paused")}
                                                </span>
                                            </div>
                                        </div>
                                    </div>
                                </div>

                                <div className="space-y-4 mb-8">
                                    <div className="flex items-center justify-between p-3 bg-white/2 rounded-xl border border-white/5">
                                        <div className="flex items-center gap-2 text-main/40">
                                            <Clock weight="bold" size={14} />
                                            <span className="text-[10px] font-bold uppercase tracking-wider">{t("task_schedule")}</span>
                                        </div>
                                        <span className="text-xs font-mono font-bold text-[#b57dff]">{task.sign_at}</span>
                                    </div>
                                    <div className="flex items-center justify-between p-3 bg-white/2 rounded-xl border border-white/5">
                                        <div className="flex items-center gap-2 text-main/40">
                                            <ChatCircleText weight="bold" size={14} />
                                            <span className="text-[10px] font-bold uppercase tracking-wider">{t("task_channels")}</span>
                                        </div>
                                        <span className="text-xs font-mono font-bold text-[#e83ffc]">
                                            {t("task_hits").replace("{count}", task.chats.length.toString())}
                                        </span>
                                    </div>
                                    <div className="flex items-center justify-between p-3 bg-white/2 rounded-xl border border-white/5">
                                        <div className="flex items-center gap-2 text-main/40">
                                            <Clock weight="bold" size={14} />
                                            <span className="text-[10px] font-bold uppercase tracking-wider">{t("task_last_run")}</span>
                                        </div>
                                        {task.last_run ? (
                                            <span className={`text-xs font-mono font-bold ${task.last_run.success ? 'text-emerald-400' : 'text-rose-400'}`}>
                                                {task.last_run.success ? t("success") : t("failure")} · {new Date(task.last_run.time).toLocaleString(language === "zh" ? 'zh-CN' : 'en-US', {
                                                    month: '2-digit',
                                                    day: '2-digit',
                                                    hour: '2-digit',
                                                    minute: '2-digit'
                                                })}
                                            </span>
                                        ) : (
                                            <span className="text-xs font-mono font-bold text-main/30">{t("no_data")}</span>
                                        )}
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
                                    <div className="flex items-center gap-2">
                                        <button
                                            onClick={() => handleShowTaskHistory(task)}
                                            disabled={loading}
                                            className="action-btn !text-[#8a3ffc] hover:bg-[#8a3ffc]/10 disabled:opacity-20 disabled:cursor-not-allowed"
                                            title={t("task_history_logs")}
                                        >
                                            <ListDashes weight="bold" />
                                        </button>
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
                                <h3 className="font-bold tracking-tight">
                                    {t("task_run_logs_title").replace("{name}", runningTask)}
                                </h3>
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
                                    {t("logs_waiting")}
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
                                            {t("task_running")}
                                        </div>
                                    )}
                                    {isDone && (
                                        <div className="text-emerald-400 mt-4 font-bold border-t border-emerald-500/20 pt-4 flex items-center gap-2">
                                            <Lightning weight="fill" />
                                            {t("task_done")}
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
                                {isDone ? t("close") : t("task_executing")}
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {historyTask && (
                <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 sm:p-6 bg-black/60 backdrop-blur-sm animate-fade-in">
                    <div className="glass-panel w-full max-w-4xl h-[78vh] flex flex-col shadow-2xl border border-white/10 overflow-hidden animate-zoom-in">
                        <div className="p-4 border-b border-white/5 flex justify-between items-center bg-white/2">
                            <div className="flex items-center gap-3">
                                <div className="w-8 h-8 rounded-lg bg-[#8a3ffc]/20 flex items-center justify-center text-[#b57dff]">
                                    <ListDashes weight="bold" size={18} />
                                </div>
                                <h3 className="font-bold tracking-tight">
                                    {t("task_history_logs_title").replace("{name}", historyTask.name)}
                                </h3>
                            </div>
                            <button
                                onClick={() => setHistoryTask(null)}
                                className="action-btn !w-8 !h-8 hover:bg-white/10"
                            >
                                <X weight="bold" />
                            </button>
                        </div>
                        <div className="flex-1 overflow-y-auto p-4 font-mono text-[11px] leading-relaxed bg-black/20">
                            {historyLoading ? (
                                <div className="flex items-center gap-2 text-main/30 italic">
                                    <Spinner className="animate-spin" size={12} />
                                    {t("loading")}
                                </div>
                            ) : historyLogs.length === 0 ? (
                                <div className="text-main/30 italic">{t("task_history_empty")}</div>
                            ) : (
                                <div className="space-y-4">
                                    {historyLogs.map((log, i) => (
                                        <div key={`${log.time}-${i}`} className="rounded-xl border border-white/5 bg-white/5 overflow-hidden">
                                            <div className="flex justify-between items-center px-3 py-2 border-b border-white/5 text-[10px]">
                                                <span className="text-main/30">
                                                    {new Date(log.time).toLocaleString(language === "zh" ? "zh-CN" : "en-US")}
                                                </span>
                                                <span className={log.success ? "text-emerald-400" : "text-rose-400"}>
                                                    {log.success ? t("success") : t("failure")}
                                                </span>
                                            </div>
                                            <div className="p-3 space-y-1">
                                                {log.flow_logs && log.flow_logs.length > 0 ? (
                                                    log.flow_logs.map((line, lineIndex) => (
                                                        <div key={lineIndex} className="text-main/80 flex gap-2">
                                                            <span className="text-main/20 select-none w-6 text-right">
                                                                {(lineIndex + 1).toString().padStart(2, "0")}
                                                            </span>
                                                            <span className="break-all">{line}</span>
                                                        </div>
                                                    ))
                                                ) : (
                                                    <div className="text-main/50">
                                                        {log.message || t("task_history_no_flow")}
                                                    </div>
                                                )}
                                                {log.flow_truncated && (
                                                    <div className="text-[10px] text-amber-400/90 mt-2">
                                                        {t("task_history_truncated").replace("{count}", String(log.flow_line_count || 0))}
                                                    </div>
                                                )}
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}

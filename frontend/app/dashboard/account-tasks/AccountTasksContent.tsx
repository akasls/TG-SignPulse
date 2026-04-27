"use client";

import { useEffect, useState, memo, useCallback, useRef } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { getToken } from "../../../lib/auth";
import {
    listSignTasks,
    deleteSignTask,
    runSignTask,
    getSignTaskHistory,
    getAccountChats,
    searchAccountChats,
    createSignTask,
    updateSignTask,
    exportSignTask,
    importSignTask,
    importAllConfigs,
    getSignTaskLogs,
    SignTask,
    SignTaskHistoryItem,
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
    ListDashes,
    X,
    DotsThreeVertical,
    Robot,
    MathOperations,
    Lightning,
    Copy,
    ClipboardText
} from "@phosphor-icons/react";
import { ToastContainer, useToast } from "../../../components/ui/toast";
import { useLanguage } from "../../../context/LanguageContext";

type ActionTypeOption = "1" | "2" | "3" | "ai_vision" | "ai_logic" | "keyword_notify";

const DICE_OPTIONS = [
    "\uD83C\uDFB2",
    "\uD83C\uDFAF",
    "\uD83C\uDFC0",
    "\u26BD",
    "\uD83C\uDFB3",
    "\uD83C\uDFB0",
] as const;

// Memoized Task Item Component
const TaskItem = memo(({ task, loading, running, onEdit, onRun, onViewLogs, onCopy, onDelete, t, language }: {
    task: SignTask;
    loading: boolean;
    running: boolean;
    onEdit: (task: SignTask) => void;
    onRun: (name: string) => void;
    onViewLogs: (task: SignTask) => void;
    onCopy: (name: string) => void;
    onDelete: (name: string) => void;
    t: (key: string) => string;
    language: string;
}) => {
    const copyTaskTitle = language === "zh" ? "\u590D\u5236\u4EFB\u52A1" : "Copy Task";

    return (
        <div className={`glass-panel p-4 md:p-5 group hover:border-[#8a3ffc]/30 transition-all ${running ? "border-emerald-500/40 shadow-[0_0_0_1px_rgba(16,185,129,0.25)]" : ""}`}>
            <div className="flex items-start gap-4 min-w-0">
                <div className="w-10 h-10 rounded-xl bg-[#8a3ffc]/10 flex items-center justify-center text-[#b57dff] shrink-0">
                    <ChatCircleText weight="bold" size={20} />
                </div>
                <div className="min-w-0 flex-1 flex flex-col gap-2">
                    <div className="flex items-center gap-2">
                        <h3 className="font-bold truncate text-sm" title={task.name}>{task.name}</h3>
                        {running && (
                            <span className="inline-flex items-center gap-1 text-[9px] text-emerald-400 font-bold uppercase">
                                <Spinner className="animate-spin" size={10} />
                                {t("task_running")}
                            </span>
                        )}
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

            <div className="mt-3 md:hidden">
                {task.last_run ? (
                    <div className="text-[10px] font-mono text-main/40 flex items-center gap-2 pt-2 border-t border-white/5">
                        <span className={task.last_run.success ? "text-emerald-400" : "text-rose-400"}>
                            {task.last_run.success ? t("success") : t("failure")}
                        </span>
                        <span>
                            {new Date(task.last_run.time).toLocaleString(language === "zh" ? 'zh-CN' : 'en-US', {
                                month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit'
                            })}
                        </span>
                    </div>
                ) : (
                    <div className="pt-2 border-t border-white/5 text-[10px] text-main/20 font-bold uppercase tracking-widest italic">{t("no_data")}</div>
                )}
            </div>

            <div className="mt-3 grid grid-cols-5 gap-2 md:hidden">
                <button
                    onClick={() => onRun(task.name)}
                    disabled={loading || running}
                    className="action-btn !w-full !h-10 !text-emerald-400 hover:bg-emerald-500/10"
                    title={t("run")}
                >
                    {running ? <Spinner className="animate-spin" size={14} /> : <Play weight="fill" size={14} />}
                </button>
                <button
                    onClick={() => onEdit(task)}
                    disabled={loading}
                    className="action-btn !w-full !h-10"
                    title={t("edit")}
                >
                    <PencilSimple weight="bold" size={14} />
                </button>
                <button
                    onClick={() => onViewLogs(task)}
                    disabled={loading}
                    className="action-btn !w-full !h-10 !text-[#8a3ffc] hover:bg-[#8a3ffc]/10"
                    title={t("task_history_logs")}
                >
                    <ListDashes weight="bold" size={14} />
                </button>
                <button
                    onClick={() => onCopy(task.name)}
                    disabled={loading}
                    className="action-btn !w-full !h-10 !text-sky-400 hover:bg-sky-500/10"
                    title={copyTaskTitle}
                >
                    <Copy weight="bold" size={14} />
                </button>
                <button
                    onClick={() => onDelete(task.name)}
                    disabled={loading}
                    className="action-btn !w-full !h-10 !text-rose-400 hover:bg-rose-500/10"
                    title={t("delete")}
                >
                    <Trash weight="bold" size={14} />
                </button>
            </div>

            <div className="hidden md:flex mt-4 items-center justify-between gap-4">
                {task.last_run ? (
                    <div className={`flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-widest ${task.last_run.success ? 'text-emerald-400' : 'text-rose-400'}`}>
                        <div className="flex items-center gap-1.5">
                            {task.last_run.success ? <CheckCircle weight="bold" /> : <XCircle weight="bold" />}
                            {task.last_run.success ? t("success") : t("failure")}
                        </div>
                        <div className="text-[10px] text-main/30 font-mono normal-case tracking-normal">
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
                        disabled={loading || running}
                        className="action-btn !w-8 !h-8 !text-emerald-400 hover:bg-emerald-500/10"
                        title={t("run")}
                    >
                        {running ? <Spinner className="animate-spin" size={14} /> : <Play weight="fill" size={14} />}
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
                        onClick={() => onViewLogs(task)}
                        disabled={loading}
                        className="action-btn !w-8 !h-8 !text-[#8a3ffc] hover:bg-[#8a3ffc]/10"
                        title={t("task_history_logs")}
                    >
                        <ListDashes weight="bold" size={14} />
                    </button>
                    <button
                        onClick={() => onCopy(task.name)}
                        disabled={loading}
                        className="action-btn !w-8 !h-8 !text-sky-400 hover:bg-sky-500/10"
                        title={copyTaskTitle}
                    >
                        <Copy weight="bold" size={14} />
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
    const fieldLabelClass = "text-xs font-bold uppercase tracking-wider text-main/40 mb-1 block";

    const [token, setLocalToken] = useState<string | null>(null);
    const [tasks, setTasks] = useState<SignTask[]>([]);
    const [chats, setChats] = useState<ChatInfo[]>([]);
    const [chatSearch, setChatSearch] = useState("");
    const [chatSearchResults, setChatSearchResults] = useState<ChatInfo[]>([]);
    const [chatSearchLoading, setChatSearchLoading] = useState(false);
    const [loading, setLoading] = useState(false);
    const [refreshingChats, setRefreshingChats] = useState(false);
    const [historyTaskName, setHistoryTaskName] = useState<string | null>(null);
    const [historyLogs, setHistoryLogs] = useState<SignTaskHistoryItem[]>([]);
    const [historyLoading, setHistoryLoading] = useState(false);
    const [expandedHistoryLogs, setExpandedHistoryLogs] = useState<Set<string>>(new Set());
    const [runningTaskNames, setRunningTaskNames] = useState<Set<string>>(new Set());
    const [liveLogTaskName, setLiveLogTaskName] = useState<string | null>(null);
    const [liveLogs, setLiveLogs] = useState<string[]>([]);

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
    const handleAccountSessionInvalid = useCallback((err: any) => {
        if (err?.code !== "ACCOUNT_SESSION_INVALID") return false;
        const toast = addToastRef.current;
        const message = tRef.current
            ? tRef.current("account_session_invalid")
            : "Account session expired, please login again";
        if (toast) {
            toast(message, "error");
        }
        setTimeout(() => {
            router.replace("/dashboard");
        }, 800);
        return true;
    }, [router]);

    // 闂傚倸鍊风粈渚€骞夐敍鍕殰婵°倕鍟伴惌娆撴煙鐎电啸缁惧彞绮欓弻鐔煎箚瑜滈崵鐔搞亜閳哄啫鍘撮柟顔肩秺瀹曞爼濡搁妷褏銈锋俊鐐€ら崑渚€宕愬┑瀣畺婵°倕鎳忛崑銊︾箾閸喎顕滈柡渚囧灦濮婄儤瀵煎▎鎴犳殺濠碘槅鍋勭€氫即濡?
    const [showCreateDialog, setShowCreateDialog] = useState(false);
    const [newTask, setNewTask] = useState({
        name: "",
        sign_at: "0 6 * * *",
        random_minutes: 0,
        chat_id: 0,
        chat_id_manual: "",
        chat_name: "",
        message_thread_id: undefined as number | undefined,
        actions: [{ action: 1, text: "" }],
        delete_after: undefined as number | undefined,
        action_interval: 1,
        execution_mode: "range" as "fixed" | "range",
        range_start: "09:00",
        range_end: "18:00",
    });

    // 缂傚倸鍊搁崐鎼佸磹閹间礁纾圭憸鐗堝笚閸嬪鏌ｉ幇顒備粵妞ゆ劘濮ら妵鍕箛閸撲焦鍋у銈傛櫇閸忔﹢骞冭ぐ鎺戠倞闁靛鍎崇粊宄邦渻閵堝骸浜栭柛濠冪箞楠炲啫螖閸涱喖浠哄┑鐐茬墛鐎笛囧极椤栫偞鈷戝ù鍏肩懅閻ｈ櫕淇婇銏狀伃闁?
    const [showEditDialog, setShowEditDialog] = useState(false);
    const [editingTaskName, setEditingTaskName] = useState("");
    const [editTask, setEditTask] = useState({
        sign_at: "0 6 * * *",
        random_minutes: 0,
        chat_id: 0,
        chat_id_manual: "",
        chat_name: "",
        message_thread_id: undefined as number | undefined,
        actions: [{ action: 1, text: "" }] as any[],
        delete_after: undefined as number | undefined,
        action_interval: 1,
        execution_mode: "fixed" as "fixed" | "range",
        range_start: "09:00",
        range_end: "18:00",
    });
    const [copyTaskDialog, setCopyTaskDialog] = useState<{ taskName: string; config: string } | null>(null);
    const [showPasteDialog, setShowPasteDialog] = useState(false);
    const [pasteTaskConfigInput, setPasteTaskConfigInput] = useState("");
    const [copyingConfig, setCopyingConfig] = useState(false);
    const [importingPastedConfig, setImportingPastedConfig] = useState(false);

    const [checking, setChecking] = useState(true);
    const isZh = language === "zh";
    const taskNamePlaceholder = isZh ? "\u7559\u7A7A\u4F7F\u7528\u9ED8\u8BA4\u540D\u79F0" : "Leave empty to use default name";
    const sendTextLabel = isZh ? "\u53D1\u9001\u6587\u672C\u6D88\u606F" : "Send Text Message";
    const clickTextButtonLabel = isZh ? "\u70B9\u51FB\u6587\u5B57\u6309\u94AE" : "Click Text Button";
    const sendDiceLabel = isZh ? "\u53D1\u9001\u9AB0\u5B50" : "Send Dice";
    const aiVisionLabel = isZh ? "AI\u8BC6\u56FE" : "AI Vision";
    const aiCalcLabel = isZh ? "AI\u8BA1\u7B97" : "AI Calculate";
    const keywordNotifyLabel = isZh ? "\u5173\u952E\u8BCD\u76D1\u542C" : "Keyword Monitor";
    const keywordPlaceholder = isZh ? "\u6BCF\u884C\u4E00\u4E2A\u5173\u952E\u8BCD\uFF0C\u4E5F\u652F\u6301\u9017\u53F7\u5206\u9694" : "One keyword per line, comma-separated also works";
    const pushUrlPlaceholder = isZh ? "Bark \u6216\u81EA\u5B9A\u4E49\u63A8\u9001 URL" : "Bark or custom push URL";
    const forwardChatIdLabel = isZh ? "\u8F6C\u53D1 Chat ID" : "Forward Chat ID";
    const forwardThreadIdLabel = isZh ? "\u8F6C\u53D1\u8BDD\u9898 ID" : "Forward Topic ID";
    const forwardChatIdPlaceholder = isZh ? "\u7559\u7A7A\u5219\u4E0D\u8F6C\u53D1" : "Leave empty to skip forwarding";
    const sendTextPlaceholder = isZh ? "\u53D1\u9001\u7684\u6587\u672C\u5185\u5BB9" : "Text to send";
    const clickButtonPlaceholder = isZh ? "\u8F93\u5165\u6309\u94AE\u6587\u5B57\uFF0C\u4E0D\u8981\u8868\u60C5\uFF01" : "Button text to click, no emoji";
    const aiVisionSendModeLabel = isZh ? "\u8BC6\u56FE\u540E\u53D1\u6587\u672C" : "Vision -> Send Text";
    const aiVisionClickModeLabel = isZh ? "\u8BC6\u56FE\u540E\u70B9\u6309\u94AE" : "Vision -> Click Button";
    const aiCalcSendModeLabel = isZh ? "\u8BA1\u7B97\u540E\u53D1\u6587\u672C" : "Math -> Send Text";
    const aiCalcClickModeLabel = isZh ? "\u8BA1\u7B97\u540E\u70B9\u6309\u94AE" : "Math -> Click Button";
    const pasteTaskTitle = isZh ? "\u7C98\u8D34\u5BFC\u5165\u4EFB\u52A1" : "Paste Task";
    const copyTaskDialogTitle = isZh ? "\u590D\u5236\u4EFB\u52A1\u914D\u7F6E" : "Copy Task Config";
    const copyTaskDialogDesc = isZh ? "\u4EE5\u4E0B\u662F\u4EFB\u52A1\u914D\u7F6E\uFF0C\u53EF\u624B\u52A8\u590D\u5236\u6216\u70B9\u51FB\u4E00\u952E\u590D\u5236\u3002" : "Task config is ready. Copy manually or use one-click copy.";
    const copyConfigAction = isZh ? "\u4E00\u952E\u590D\u5236" : "Copy";
    const pasteTaskDialogTitle = isZh ? "\u7C98\u8D34\u5BFC\u5165\u4EFB\u52A1" : "Paste Task Config";
    const pasteTaskDialogDesc = isZh ? "\u65E0\u6CD5\u76F4\u63A5\u8BFB\u53D6\u526A\u8D34\u677F\uFF0C\u8BF7\u5728\u4E0B\u65B9\u7C98\u8D34\u914D\u7F6E\u540E\u5BFC\u5165\u3002" : "Clipboard read failed. Paste config below and import.";
    const pasteTaskDialogPlaceholder = isZh ? "\u5728\u6B64\u7C98\u8D34\u4EFB\u52A1\u914D\u7F6E JSON..." : "Paste task config JSON here...";
    const importTaskAction = isZh ? "\u5BFC\u5165\u4EFB\u52A1" : "Import Task";
    const clipboardReadFailed = isZh ? "\u65E0\u6CD5\u8BFB\u53D6\u526A\u8D34\u677F\uFF0C\u5DF2\u5207\u6362\u4E3A\u624B\u52A8\u7C98\u8D34\u5BFC\u5165" : "Clipboard read failed, switched to manual paste import";
    const copyTaskSuccess = (taskName: string) =>
        isZh ? `\u4EFB\u52A1 ${taskName} \u5DF2\u590D\u5236\u5230\u526A\u8D34\u677F` : `Task ${taskName} copied to clipboard`;
    const copyTaskFailed = isZh ? "\u590D\u5236\u4EFB\u52A1\u5931\u8D25" : "Copy task failed";
    const pasteTaskSuccess = (taskName: string) =>
        isZh ? `\u4EFB\u52A1 ${taskName} \u5BFC\u5165\u6210\u529F` : `Task ${taskName} imported`;
    const pasteTaskFailed = isZh ? "\u7C98\u8D34\u4EFB\u52A1\u5931\u8D25" : "Paste task failed";
    const clipboardUnsupported = isZh ? "\u5F53\u524D\u73AF\u5883\u4E0D\u652F\u6301\u526A\u8D34\u677F\u64CD\u4F5C" : "Clipboard API is not available";
    const copyTaskFallbackManual = isZh ? "\u81EA\u52A8\u590D\u5236\u5931\u8D25\uFF0C\u8BF7\u5728\u5F39\u7A97\u5185\u624B\u52A8\u590D\u5236" : "Auto copy failed, please copy manually from dialog";
    const copyAllTasksTitle = t("export_all_tasks");

    const sanitizeTaskName = useCallback((raw: string) => {
        return raw
            .trim()
            .replace(/[<>:"/\\|?*]+/g, "_")
            .replace(/\s+/g, "_")
            .replace(/_+/g, "_")
            .replace(/^_+|_+$/g, "")
            .slice(0, 64);
    }, []);

    const toActionTypeOption = useCallback((action: any): ActionTypeOption => {
        const actionId = Number(action?.action);
        if (actionId === 1) return "1";
        if (actionId === 3) return "3";
        if (actionId === 2) return "2";
        if (actionId === 4 || actionId === 6) return "ai_vision";
        if (actionId === 5 || actionId === 7) return "ai_logic";
        if (actionId === 8) return "keyword_notify";
        return "1";
    }, []);

    const isActionValid = useCallback((action: any) => {
        const actionId = Number(action?.action);
        if (actionId === 1 || actionId === 3) {
            return Boolean((action?.text || "").trim());
        }
        if (actionId === 2) {
            return Boolean((action?.dice || "").trim());
        }
        if (actionId === 8) {
            const keywords = Array.isArray(action?.keywords) ? action.keywords : [];
            const hasKeywords = keywords.some((item: string) => (item || "").trim());
            if (!hasKeywords) return false;
            if (action?.push_channel === "bark") {
                return Boolean((action?.bark_url || "").trim());
            }
            if (action?.push_channel === "custom") {
                return Boolean((action?.custom_url || "").trim());
            }
            return true;
        }
        return [4, 5, 6, 7].includes(actionId);
    }, []);

    const loadData = useCallback(async (tokenStr: string) => {
        try {
            setLoading(true);
            const tasksData = await listSignTasks(tokenStr, accountName);
            setTasks(tasksData);
            try {
                const chatsData = await getAccountChats(tokenStr, accountName);
                setChats(chatsData);
            } catch (err: any) {
                if (handleAccountSessionInvalid(err)) return;
                const toast = addToastRef.current;
                if (toast) {
                    toast(formatErrorMessage("load_failed", err), "error");
                }
            }
        } catch (err: any) {
            if (handleAccountSessionInvalid(err)) return;
            const toast = addToastRef.current;
            if (toast) {
                toast(formatErrorMessage("load_failed", err), "error");
            }
        } finally {
            setLoading(false);
        }
    }, [accountName, formatErrorMessage, handleAccountSessionInvalid]);

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
    }, [accountName, loadData]);

    useEffect(() => {
        if (!token || !accountName) return;
        const query = chatSearch.trim();
        if (!query) {
            setChatSearchResults([]);
            setChatSearchLoading(false);
            return;
        }
        let cancelled = false;
        setChatSearchLoading(true);
        const timer = setTimeout(async () => {
            try {
                const res = await searchAccountChats(token, accountName, query, 50, 0);
                if (!cancelled) {
                    setChatSearchResults(res.items || []);
                }
            } catch (err: any) {
                if (!cancelled) {
                    if (handleAccountSessionInvalid(err)) return;
                    const toast = addToastRef.current;
                    if (toast) {
                        toast(formatErrorMessage("search_failed", err), "error");
                    }
                    setChatSearchResults([]);
                }
            } finally {
                if (!cancelled) {
                    setChatSearchLoading(false);
                }
            }
        }, 300);
        return () => {
            cancelled = true;
            clearTimeout(timer);
        };
    }, [chatSearch, token, accountName, formatErrorMessage, handleAccountSessionInvalid]);

    useEffect(() => {
        if (!showCreateDialog && !showEditDialog) {
            setChatSearch("");
            setChatSearchResults([]);
            setChatSearchLoading(false);
        }
    }, [showCreateDialog, showEditDialog, accountName]);

    useEffect(() => {
        if (!token || !accountName || !liveLogTaskName) return;
        let cancelled = false;
        const fetchLiveLogs = async () => {
            try {
                const logs = await getSignTaskLogs(token, liveLogTaskName, accountName);
                if (!cancelled) {
                    setLiveLogs(logs || []);
                }
            } catch {
                // Live logs are best-effort; the final result toast still reports errors.
            }
        };
        fetchLiveLogs();
        const timer = setInterval(fetchLiveLogs, 1000);
        return () => {
            cancelled = true;
            clearInterval(timer);
        };
    }, [token, accountName, liveLogTaskName]);

    const handleRefreshChats = async () => {
        if (!token || !accountName) return;
        try {
            setRefreshingChats(true);
            const chatsData = await getAccountChats(token, accountName, true);
            setChats(chatsData);
            addToast(t("chats_refreshed"), "success");
        } catch (err: any) {
            if (handleAccountSessionInvalid(err)) return;
            addToast(formatErrorMessage("refresh_failed", err), "error");
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
            addToast(t("chats_refreshed"), "success");
        } catch (err: any) {
            if (handleAccountSessionInvalid(err)) return;
            addToast(formatErrorMessage("refresh_failed", err), "error");
        } finally {
            setLoading(false);
        }
    };

    const applyChatSelection = (chatId: number, chatName: string) => {
        if (showCreateDialog) {
            setNewTask({
                ...newTask,
                name: newTask.name || chatName,
                chat_id: chatId,
                chat_id_manual: chatId !== 0 ? chatId.toString() : "",
                chat_name: chatName,
            });
        } else {
            setEditTask({
                ...editTask,
                chat_id: chatId,
                chat_id_manual: chatId !== 0 ? chatId.toString() : "",
                chat_name: chatName,
            });
        }
    };

    const handleDeleteTask = async (taskName: string) => {
        if (!token) return;

        if (!confirm(t("confirm_delete"))) {
            return;
        }

        try {
            setLoading(true);
            await deleteSignTask(token, taskName, accountName);
            // addToast(language === "zh" ? `濠电姷鏁搁崑娑㈩敋椤撶喐鍙忓Δ锝呭枤閺佸鎲告惔銊ョ疄?${taskName} 闂備浇顕уù鐑藉箠閹捐绠熼梽鍥Φ閹版澘绀冩い鏃傚帶閻庮參鎮峰鍛暭閻㈩垱顨婇崺娑㈠籍閳ь剟濡?: `Task ${taskName} deleted`, "success"); // Removed toast as per user request to just refresh
            await loadData(token);
        } catch (err: any) {
            // Only show error if it's NOT a 404 (already deleted/doesn't exist)
            if (err.status !== 404 && !err.message?.includes("not exist")) {
                addToast(formatErrorMessage("delete_failed", err), "error");
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
            setRunningTaskNames((prev) => new Set(prev).add(taskName));
            setLiveLogTaskName(taskName);
            setLiveLogs([]);
            const result = await runSignTask(token, taskName, accountName);
            try {
                const logs = await getSignTaskLogs(token, taskName, accountName);
                setLiveLogs(logs || []);
            } catch {
                // ignore live log refresh errors after completion
            }

            if (!result.success && result.error) {
                setLiveLogs((prev) => (prev.length > 0 ? prev : [result.error]));
            }
        } catch (err: any) {
            setLiveLogs((prev) => [
                ...prev,
                `${t("task_run_failed")}: ${err?.message || err}`,
            ]);
        } finally {
            setRunningTaskNames((prev) => {
                const next = new Set(prev);
                next.delete(taskName);
                return next;
            });
            await loadData(token);
        }
    };

    const handleShowTaskHistory = async (task: SignTask) => {
        if (!token) return;
        setHistoryTaskName(task.name);
        setHistoryLogs([]);
        setExpandedHistoryLogs(new Set());
        setHistoryLoading(true);
        try {
            const logs = await getSignTaskHistory(token, task.name, accountName, 30);
            setHistoryLogs(logs);
        } catch (err: any) {
            addToast(formatErrorMessage("logs_fetch_failed", err), "error");
        } finally {
            setHistoryLoading(false);
        }
    };

    const importTaskFromConfig = async (rawConfig: string): Promise<{ ok: boolean; error?: string }> => {
        if (!token) return { ok: false, error: "NO_TOKEN" };
        const taskConfig = (rawConfig || "").trim();
        if (!taskConfig) {
            addToast(t("import_empty"), "error");
            return { ok: false, error: t("import_empty") };
        }

        try {
            setLoading(true);
            let parsed: any = null;
            try {
                parsed = JSON.parse(taskConfig);
            } catch {
                parsed = null;
            }
            if (parsed && typeof parsed === "object" && parsed.signs && typeof parsed.signs === "object") {
                const taskOnlyBundle: { signs: Record<string, any>; monitors: Record<string, any>; settings: Record<string, any> } = {
                    signs: {},
                    monitors: {},
                    settings: {},
                };
                for (const [key, value] of Object.entries(parsed.signs)) {
                    if (!value || typeof value !== "object") continue;
                    const config: Record<string, any> = { ...(value as Record<string, any>), account_name: accountName };
                    const taskName = String(config.name || key).split("@")[0];
                    taskOnlyBundle.signs[`${taskName}@${accountName}`] = config;
                }
                await importAllConfigs(token, JSON.stringify(taskOnlyBundle), false);
                addToast(t("paste_all_tasks_success"), "success");
                await loadData(token);
                return { ok: true };
            }

            const result = await importSignTask(token, taskConfig, undefined, accountName);
            addToast(pasteTaskSuccess(result.task_name), "success");
            await loadData(token);
            return { ok: true };
        } catch (err: any) {
            const message = err?.message ? `${pasteTaskFailed}: ${err.message}` : pasteTaskFailed;
            addToast(message, "error");
            return { ok: false, error: message };
        } finally {
            setLoading(false);
        }
    };

    const handleCopyTask = async (taskName: string) => {
        if (!token) return;

        try {
            setLoading(true);
            const taskConfig = await exportSignTask(token, taskName, accountName);
            if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
                try {
                    await navigator.clipboard.writeText(taskConfig);
                    addToast(copyTaskSuccess(taskName), "success");
                    return;
                } catch {
                    addToast(copyTaskFallbackManual, "error");
                }
            }
            setCopyTaskDialog({ taskName, config: taskConfig });
        } catch (err: any) {
            const message = err?.message ? `${copyTaskFailed}: ${err.message}` : copyTaskFailed;
            addToast(message, "error");
        } finally {
            setLoading(false);
        }
    };

    const handleCopyAllTasks = async () => {
        if (!token) return;
        if (tasks.length === 0) {
            addToast(t("copy_all_tasks_empty"), "error");
            return;
        }
        if (typeof navigator === "undefined" || !navigator.clipboard?.writeText) {
            addToast(clipboardUnsupported, "error");
            return;
        }

        try {
            setLoading(true);
            const bundle: { signs: Record<string, any>; monitors: Record<string, any>; settings: Record<string, any> } = {
                signs: {},
                monitors: {},
                settings: {},
            };
            for (const task of tasks) {
                const raw = await exportSignTask(token, task.name, accountName);
                const parsed = JSON.parse(raw);
                const config = { ...(parsed.config || {}) };
                config.account_name = accountName;
                const key = `${parsed.task_name || task.name}@${accountName}`;
                bundle.signs[key] = config;
            }
            await navigator.clipboard.writeText(JSON.stringify(bundle, null, 2));
            addToast(t("copy_all_tasks_success"), "success");
        } catch (err: any) {
            const message = err?.message ? `${t("copy_all_tasks_failed")}: ${err.message}` : t("copy_all_tasks_failed");
            addToast(message, "error");
        } finally {
            setLoading(false);
        }
    };

    const handleCopyTaskConfig = async () => {
        if (!copyTaskDialog) return;
        if (typeof navigator === "undefined" || !navigator.clipboard?.writeText) {
            addToast(clipboardUnsupported, "error");
            return;
        }
        try {
            setCopyingConfig(true);
            await navigator.clipboard.writeText(copyTaskDialog.config);
            addToast(copyTaskSuccess(copyTaskDialog.taskName), "success");
            setCopyTaskDialog(null);
        } catch (err: any) {
            const message = err?.message ? `${copyTaskFailed}: ${err.message}` : copyTaskFailed;
            addToast(message, "error");
        } finally {
            setCopyingConfig(false);
        }
    };

    const handlePasteDialogImport = async () => {
        setImportingPastedConfig(true);
        const result = await importTaskFromConfig(pasteTaskConfigInput);
        if (result.ok) {
            setShowPasteDialog(false);
            setPasteTaskConfigInput("");
        }
        setImportingPastedConfig(false);
    };

    const handlePasteTask = async () => {
        if (!token) return;

        if (typeof navigator !== "undefined" && navigator.clipboard?.readText) {
            try {
                const taskConfig = (await navigator.clipboard.readText()).trim();
                if (taskConfig) {
                    const result = await importTaskFromConfig(taskConfig);
                    if (result.ok) {
                        return;
                    }
                    setPasteTaskConfigInput(taskConfig);
                    setShowPasteDialog(true);
                    return;
                }
            } catch {
                addToast(clipboardReadFailed, "error");
            }
        } else {
            addToast(clipboardUnsupported, "error");
        }

        setPasteTaskConfigInput("");
        setShowPasteDialog(true);
    };

    const closeCopyTaskDialog = () => {
        if (copyingConfig) {
            return;
        }
        setCopyTaskDialog(null);
    };

    const closePasteTaskDialog = () => {
        if (importingPastedConfig || loading) {
            return;
        }
        setShowPasteDialog(false);
        setPasteTaskConfigInput("");
    };

    const handleCreateTask = async () => {
        if (!token) return;

        if (!newTask.sign_at) {
            addToast(t("cron_required"), "error");
            return;
        }

        let chatId = newTask.chat_id;
        if (newTask.chat_id_manual) {
            chatId = parseInt(newTask.chat_id_manual);
            if (isNaN(chatId)) {
                addToast(t("chat_id_numeric"), "error");
                return;
            }
        }

        if (chatId === 0) {
            addToast(t("select_chat_error"), "error");
            return;
        }

        if (newTask.actions.length === 0 || newTask.actions.some((action) => !isActionValid(action))) {
            addToast(t("add_action_error"), "error");
            return;
        }

        try {
            setLoading(true);
            const fallbackTaskName =
                sanitizeTaskName(newTask.chat_name) ||
                sanitizeTaskName(newTask.chat_id_manual ? `chat_${newTask.chat_id_manual}` : "") ||
                `task_${Date.now()}`;
            const finalTaskName = sanitizeTaskName(newTask.name) || fallbackTaskName;

            const request: CreateSignTaskRequest = {
                name: finalTaskName,
                account_name: accountName,
                sign_at: newTask.sign_at,
                chats: [{
                    chat_id: chatId,
                    name: newTask.chat_name || t("chat_default_name").replace("{id}", String(chatId)),
                    message_thread_id: newTask.message_thread_id,
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
            addToast(t("create_success"), "success");
            setShowCreateDialog(false);
            setNewTask({
                name: "",
                sign_at: "0 6 * * *",
                random_minutes: 0,
                chat_id: 0,
                chat_id_manual: "",
                chat_name: "",
                message_thread_id: undefined,
                actions: [{ action: 1, text: "" }],
                delete_after: undefined,
                action_interval: 1,
                execution_mode: "fixed",
                range_start: "09:00",
                range_end: "18:00",
            });
            await loadData(token);
        } catch (err: any) {
            addToast(formatErrorMessage("create_failed", err), "error");
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
            message_thread_id: chat?.message_thread_id,
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
            addToast(t("select_chat_error"), "error");
            return;
        }
        if (editTask.actions.length === 0 || editTask.actions.some((action) => !isActionValid(action))) {
            addToast(t("add_action_error"), "error");
            return;
        }

        try {
            setLoading(true);

            await updateSignTask(token, editingTaskName, {
                sign_at: editTask.sign_at,
                random_seconds: editTask.random_minutes * 60,
                chats: [{
                    chat_id: chatId,
                    name: editTask.chat_name || t("chat_default_name").replace("{id}", String(chatId)),
                    message_thread_id: editTask.message_thread_id,
                    actions: editTask.actions,
                    delete_after: editTask.delete_after,
                    action_interval: editTask.action_interval,
                }],
                execution_mode: editTask.execution_mode,
                range_start: editTask.range_start,
                range_end: editTask.range_end,
            }, accountName);

            addToast(t("update_success"), "success");
            setShowEditDialog(false);
            await loadData(token);
        } catch (err: any) {
            addToast(formatErrorMessage("update_failed", err), "error");
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

    const updateCurrentDialogAction = useCallback((index: number, updater: (action: any) => any) => {
        if (showCreateDialog) {
            setNewTask((prev) => {
                if (index < 0 || index >= prev.actions.length) return prev;
                const nextActions = [...prev.actions];
                nextActions[index] = updater(nextActions[index] || { action: 1, text: "" });
                return { ...prev, actions: nextActions };
            });
            return;
        }

        setEditTask((prev) => {
            if (index < 0 || index >= prev.actions.length) return prev;
            const nextActions = [...prev.actions];
            nextActions[index] = updater(nextActions[index] || { action: 1, text: "" });
            return { ...prev, actions: nextActions };
        });
    }, [showCreateDialog]);

    if (!token || checking) {
        return null;
    }

    return (
        <div id="account-tasks-view" className="w-full h-full flex flex-col">
            <nav className="navbar">
                <div className="nav-brand">
                    <div className="flex items-center gap-4">
                        <Link href="/dashboard" className="action-btn" title={t("sidebar_home")}>
                            <CaretLeft weight="bold" />
                        </Link>
                        <h1 className="text-lg font-bold tracking-tight">{accountName}</h1>
                    </div>
                </div>
                <div className="top-right-actions">
                    <button
                        onClick={refreshChats}
                        disabled={loading}
                        className="action-btn"
                        title={t("refresh_chats")}
                    >
                        <ArrowClockwise weight="bold" className={loading ? 'animate-spin' : ''} />
                    </button>
                    <button
                        onClick={handleCopyAllTasks}
                        disabled={loading}
                        className="action-btn"
                        title={copyAllTasksTitle}
                    >
                        <Copy weight="bold" />
                    </button>
                    <button
                        onClick={handlePasteTask}
                        disabled={loading}
                        className="action-btn"
                        title={pasteTaskTitle}
                    >
                        <ClipboardText weight="bold" />
                    </button>
                    <button onClick={() => setShowCreateDialog(true)} className="action-btn" title={t("add_task")}>
                        <Plus weight="bold" />
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
                                running={runningTaskNames.has(task.name)}
                                onEdit={handleEditTask}
                                onRun={handleRunTask}
                                onViewLogs={handleShowTaskHistory}
                                onCopy={handleCopyTask}
                                onDelete={handleDeleteTask}
                                t={t}
                                language={language}
                            />
                        ))}
                    </div>
                )}
            </main>

            {/* 闂傚倸鍊风粈渚€骞夐敍鍕殰婵°倕鍟伴惌娆撴煙鐎电啸缁?缂傚倸鍊搁崐鎼佸磹閹间礁纾圭憸鐗堝笚閸嬪鏌ｉ幇顒備粵妞ゆ劘濮ら妵鍕箛閳轰讲鍋撻幇鏉跨；闁瑰墽绮崑銊︾箾閸喎顕滈柡渚囧灦濮婄儤瀵煎▎鎴犳殺濠碘槅鍋勭€氫即濡撮崨顔鹃檮缂佸鐏濋懓鍨攽閻愭潙鐏﹂悽顖涘笚缁傚秹鎮欓浣稿伎濠碘槅鍨板锟犲传濞差亝鐓涢柛鈩冾殘缁犲鏌″畝瀣М濠碘剝鎮傛俊鐑藉Ψ椤旇崵妫梻浣藉吹閸犳劕煤閺嶎灛娑樷攽閸♀晛娈ㄦ繝鐢靛У閼瑰墽绮绘繝姘厽闁瑰瓨姊瑰▍鍛瑰鍫㈢暫闁哄矉绻濆畷鐔碱敃閵堝浂鍞洪梺?*/}
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
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 items-start">
                                {showCreateDialog ? (
                                    <div className="space-y-2">
                                        <label className={fieldLabelClass}>{t("task_name")}</label>
                                        <input
                                            className="!mb-0"
                                            placeholder={taskNamePlaceholder}
                                            value={newTask.name}
                                            onChange={(e) => setNewTask({ ...newTask, name: e.target.value })}
                                        />
                                    </div>
                                ) : (
                                    <div className="space-y-2">
                                        <label className={fieldLabelClass}>{t("task_name")}</label>
                                        <input
                                            className="!mb-0"
                                            value={editingTaskName}
                                            readOnly
                                            aria-readonly="true"
                                        />
                                    </div>
                                )}

                                <div className="space-y-2">
                                    <label className={fieldLabelClass}>{t("scheduling_mode")}</label>
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
                                        <option value="range">{t("random_range_recommend")}</option>
                                        <option value="fixed">{t("fixed_time_cron")}</option>
                                    </select>
                                </div>

                                <div className="space-y-2">
                                    <label className={fieldLabelClass}>{t("action_interval")}</label>
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

                                <div className="space-y-2">
                                    {(showCreateDialog ? newTask.execution_mode : editTask.execution_mode) === "fixed" ? (
                                        <>
                                            <label className={fieldLabelClass}>{t("sign_time_cron")}</label>
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
                                                {t("cron_example")}
                                            </div>
                                        </>
                                    ) : (
                                        <>
                                            <label className={fieldLabelClass}>{t("time_range")}</label>
                                            <div className="grid grid-cols-2 gap-2">
                                                <input
                                                    type="time"
                                                    className="!mb-0"
                                                    aria-label={t("start_label")}
                                                    title={t("start_label")}
                                                    value={showCreateDialog ? newTask.range_start : editTask.range_start}
                                                    onChange={(e) => showCreateDialog
                                                        ? setNewTask({ ...newTask, range_start: e.target.value })
                                                        : setEditTask({ ...editTask, range_start: e.target.value })
                                                    }
                                                />
                                                <input
                                                    type="time"
                                                    className="!mb-0"
                                                    aria-label={t("end_label")}
                                                    title={t("end_label")}
                                                    value={showCreateDialog ? newTask.range_end : editTask.range_end}
                                                    onChange={(e) => showCreateDialog
                                                        ? setNewTask({ ...newTask, range_end: e.target.value })
                                                        : setEditTask({ ...editTask, range_end: e.target.value })
                                                    }
                                                />
                                            </div>
                                            <div className="text-[10px] text-main/30 mt-1 italic">
                                                {t("random_time_hint")}
                                            </div>
                                        </>
                                    )}
                                </div>
                            </div>

                            <div className="glass-panel !bg-black/5 p-4 space-y-4 border-white/5">
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                    <div className="space-y-2">
                                        <label className="text-[10px] text-main/40 uppercase tracking-wider">{t("search_chat")}</label>
                                        <input
                                            className="!mb-0"
                                            placeholder={t("search_chat_placeholder")}
                                            value={chatSearch}
                                            onChange={(e) => setChatSearch(e.target.value)}
                                        />
                                        {chatSearch.trim() ? (
                                            <div className="max-h-48 overflow-y-auto rounded-lg border border-white/5 bg-black/5">
                                                {chatSearchLoading ? (
                                                    <div className="px-3 py-2 text-xs text-main/40">{t("searching")}</div>
                                                ) : chatSearchResults.length > 0 ? (
                                                    <div className="flex flex-col">
                                                        {chatSearchResults.map((chat) => {
                                                            const title = chat.title || chat.username || String(chat.id);
                                                            return (
                                                                <button
                                                                    key={chat.id}
                                                                    type="button"
                                                                    className="text-left px-3 py-2 hover:bg-white/5 border-b border-white/5 last:border-b-0"
                                                                    onClick={() => {
                                                                        applyChatSelection(chat.id, title);
                                                                        setChatSearch("");
                                                                        setChatSearchResults([]);
                                                                    }}
                                                                >
                                                                    <div className="text-sm font-semibold truncate">{title}</div>
                                                                    <div className="text-[10px] text-main/40 font-mono truncate">
                                                                        {chat.id}{chat.username ? ` 路 @${chat.username}` : ""}
                                                                    </div>
                                                                </button>
                                                            );
                                                        })}
                                                    </div>
                                                ) : (
                                                    <div className="px-3 py-2 text-xs text-main/40">{t("search_no_results")}</div>
                                                )}
                                            </div>
                                        ) : null}
                                    </div>
                                    <div className="space-y-2">
                                        <div className="flex items-center justify-between">
                                            <label className="text-[10px] text-main/40 uppercase tracking-wider">{t("select_from_list")}</label>
                                            <button
                                                onClick={handleRefreshChats}
                                                disabled={refreshingChats}
                                                className="text-[10px] text-[#8a3ffc] hover:text-[#8a3ffc]/80 transition-colors uppercase font-bold tracking-tighter flex items-center gap-1"
                                                title={t("refresh_chat_title")}
                                            >
                                                {refreshingChats ? (
                                                    <div className="w-3 h-3 border-2 border-[#8a3ffc] border-t-transparent rounded-full animate-spin"></div>
                                                ) : <ArrowClockwise weight="bold" size={12} />}
                                                {t("refresh_list")}
                                            </button>
                                        </div>
                                        <select
                                            className="!mb-0"
                                            value={showCreateDialog ? newTask.chat_id : editTask.chat_id}
                                            onChange={(e) => {
                                                const id = parseInt(e.target.value);
                                                const chat = chats.find(c => c.id === id);
                                                const chatName = chat?.title || chat?.username || "";
                                                applyChatSelection(id, chatName);
                                            }}
                                        >
                                            <option value={0}>{t("select_from_list")}</option>
                                            {chats.map(chat => (
                                                <option key={chat.id} value={chat.id}>
                                                    {chat.title || chat.username || chat.id}
                                                </option>
                                            ))}
                                        </select>
                                    </div>
                                </div>
                                <div className="space-y-2 mt-4">
                                    <label className="text-[10px] text-main/40 uppercase tracking-wider">{t("topic_id_label") || "Topic/Thread ID (Optional)"}</label>
                                    <input
                                        inputMode="numeric"
                                        className="!mb-0"
                                        placeholder={t("topic_id_placeholder") || "Leave blank if not applicable"}
                                        value={showCreateDialog ? (newTask.message_thread_id || "") : (editTask.message_thread_id || "")}
                                        onChange={(e) => {
                                            const val = e.target.value ? parseInt(e.target.value) : undefined;
                                            showCreateDialog
                                                ? setNewTask({ ...newTask, message_thread_id: val })
                                                : setEditTask({ ...editTask, message_thread_id: val });
                                        }}
                                    />
                                </div>
                                    <div className="space-y-2">
                                        <label className="text-[10px] text-main/40 uppercase tracking-wider">{t("manual_chat_id")}</label>
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
                                    <div className="space-y-2">
                                        <label className="text-[10px] text-main/40 uppercase tracking-wider">{t("delete_after")}</label>
                                        <input
                                            type="text"
                                            inputMode="numeric"
                                            placeholder={t("delete_after_placeholder")}
                                            className="!mb-0"
                                            value={showCreateDialog ? (newTask.delete_after ?? "") : (editTask.delete_after ?? "")}
                                            onChange={(e) => {
                                                const cleaned = e.target.value.replace(/[^0-9]/g, "");
                                                const val = cleaned === "" ? undefined : Number(cleaned);
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
                                        <div key={index} className="flex gap-3 items-center animate-scale-in">
                                            <div className="shrink-0 w-6 h-10 flex items-center justify-center font-mono text-[10px] text-main/20 font-bold border-r border-white/5">
                                                {index + 1}
                                            </div>
                                            <select
                                                className="!w-[170px] !h-10 !mb-0"
                                                value={toActionTypeOption(action)}
                                                onChange={(e) => {
                                                    const selectedType = e.target.value as ActionTypeOption;
                                                    updateCurrentDialogAction(index, (currentAction) => {
                                                        const currentActionId = Number(currentAction?.action);
                                                        if (selectedType === "1") {
                                                            return { ...currentAction, action: 1, text: currentAction?.text || "" };
                                                        }
                                                        if (selectedType === "3") {
                                                            return { ...currentAction, action: 3, text: currentAction?.text || "" };
                                                        }
                                                        if (selectedType === "2") {
                                                            return { ...currentAction, action: 2, dice: currentAction?.dice || DICE_OPTIONS[0] };
                                                        }
                                                        if (selectedType === "keyword_notify") {
                                                            return {
                                                                ...currentAction,
                                                                action: 8,
                                                                keywords: currentAction?.keywords || [],
                                                                match_mode: currentAction?.match_mode || "contains",
                                                                ignore_case: currentAction?.ignore_case ?? true,
                                                                push_channel: currentAction?.push_channel || "telegram",
                                                                bark_url: currentAction?.bark_url || "",
                                                                custom_url: currentAction?.custom_url || "",
                                                                forward_chat_id: currentAction?.forward_chat_id || "",
                                                                forward_message_thread_id: currentAction?.forward_message_thread_id,
                                                            };
                                                        }
                                                        if (selectedType === "ai_vision") {
                                                            const nextActionId = (currentActionId === 4 || currentActionId === 6) ? currentActionId : 6;
                                                            return { ...currentAction, action: nextActionId };
                                                        }
                                                        const nextActionId = (currentActionId === 5 || currentActionId === 7) ? currentActionId : 5;
                                                        return { ...currentAction, action: nextActionId };
                                                    });
                                                }}
                                            >
                                                <option value="1">{sendTextLabel}</option>
                                                <option value="3">{clickTextButtonLabel}</option>
                                                <option value="2">{sendDiceLabel}</option>
                                                <option value="ai_vision">{aiVisionLabel}</option>
                                                <option value="ai_logic">{aiCalcLabel}</option>
                                                <option value="keyword_notify">{keywordNotifyLabel}</option>
                                            </select>

                                            <div className="flex-1 min-w-0">
                                                {(action.action === 1 || action.action === 3) && (
                                                    <input
                                                        placeholder={action.action === 1 ? sendTextPlaceholder : clickButtonPlaceholder}
                                                        className="!mb-0 !h-10"
                                                        value={action.text || ""}
                                                        onChange={(e) => {
                                                            updateCurrentDialogAction(index, (currentAction) => ({
                                                                ...currentAction,
                                                                text: e.target.value,
                                                            }));
                                                        }}
                                                    />
                                                )}
                                                {action.action === 2 && (
                                                    <div className="flex items-center gap-2 overflow-x-auto">
                                                        {DICE_OPTIONS.map((d) => (
                                                            <button
                                                                key={d}
                                                                type="button"
                                                                className={`w-10 h-10 shrink-0 rounded-xl flex items-center justify-center text-lg transition-all ${((action as any).dice === d) ? 'bg-[#8a3ffc]/20 border border-[#8a3ffc]/40' : 'bg-white/5 border border-white/5 hover:bg-white/10'}`}
                                                                onClick={() => {
                                                                    updateCurrentDialogAction(index, (currentAction) => ({
                                                                        ...currentAction,
                                                                        dice: d,
                                                                    }));
                                                                }}
                                                            >
                                                                {d}
                                                            </button>
                                                        ))}
                                                    </div>
                                                )}
                                                {(action.action === 4 || action.action === 6) && (
                                                    <div className="h-10 px-3 flex items-center gap-2 bg-indigo-500/10 border border-indigo-500/20 rounded-xl">
                                                        <Robot weight="fill" size={16} className="text-[#8183ff]" />
                                                        <select
                                                            className="!mb-0 !h-10 !py-0 !text-xs !w-[220px] max-w-full"
                                                            value={action.action === 4 ? "click" : "send"}
                                                            onChange={(e) => {
                                                                const nextActionId = e.target.value === "click" ? 4 : 6;
                                                                updateCurrentDialogAction(index, (currentAction) => ({
                                                                    ...currentAction,
                                                                    action: nextActionId,
                                                                }));
                                                            }}
                                                        >
                                                            <option value="send">{aiVisionSendModeLabel}</option>
                                                            <option value="click">{aiVisionClickModeLabel}</option>
                                                        </select>
                                                    </div>
                                                )}
                                                {(action.action === 5 || action.action === 7) && (
                                                    <div className="h-10 px-3 flex items-center gap-2 bg-amber-500/10 border border-amber-500/20 rounded-xl">
                                                        <MathOperations weight="fill" size={16} className="text-amber-400" />
                                                        <select
                                                            className="!mb-0 !h-10 !py-0 !text-xs !w-[220px] max-w-full"
                                                            value={action.action === 7 ? "click" : "send"}
                                                            onChange={(e) => {
                                                                const nextActionId = e.target.value === "click" ? 7 : 5;
                                                                updateCurrentDialogAction(index, (currentAction) => ({
                                                                    ...currentAction,
                                                                    action: nextActionId,
                                                                }));
                                                            }}
                                                        >
                                                            <option value="send">{aiCalcSendModeLabel}</option>
                                                            <option value="click">{aiCalcClickModeLabel}</option>
                                                        </select>
                                                    </div>
                                                )}
                                                {action.action === 8 && (
                                                    <div className="rounded-xl border border-cyan-500/20 bg-cyan-500/10 p-3 space-y-4">
                                                        <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1.2fr)_minmax(280px,0.8fr)] gap-3">
                                                            <div className="space-y-1.5">
                                                                <label className="text-[10px] uppercase tracking-wider text-main/40">{t("monitor_keywords")}</label>
                                                                <textarea
                                                                    className="w-full min-h-[104px] bg-white/2 rounded-xl p-3 text-[11px] text-main/70 border border-white/5 focus:border-[#8a3ffc]/30 outline-none transition-all placeholder:text-main/20 custom-scrollbar"
                                                                    value={(action.keywords || []).join("\n")}
                                                                    onChange={(e) => {
                                                                        updateCurrentDialogAction(index, (currentAction) => ({
                                                                            ...currentAction,
                                                                            keywords: e.target.value.split(/\n|,/).map((item) => item.trim()).filter(Boolean),
                                                                        }));
                                                                    }}
                                                                    placeholder={keywordPlaceholder}
                                                                />
                                                            </div>
                                                            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-1 gap-2">
                                                                <div className="space-y-1.5">
                                                                    <label className="text-[10px] uppercase tracking-wider text-main/40">{t("match_mode")}</label>
                                                                    <select
                                                                        className="!mb-0 !h-10 !py-0 !text-xs"
                                                                        value={action.match_mode || "contains"}
                                                                        onChange={(e) => {
                                                                            updateCurrentDialogAction(index, (currentAction) => ({
                                                                                ...currentAction,
                                                                                match_mode: e.target.value,
                                                                            }));
                                                                        }}
                                                                    >
                                                                        <option value="contains">{t("match_contains")}</option>
                                                                        <option value="exact">{t("match_exact")}</option>
                                                                        <option value="regex">{t("match_regex")}</option>
                                                                    </select>
                                                                </div>
                                                                <label className="h-10 mt-auto flex items-center gap-2 text-[11px] text-main/60">
                                                                    <input
                                                                        type="checkbox"
                                                                        checked={action.ignore_case ?? true}
                                                                        onChange={(e) => {
                                                                            updateCurrentDialogAction(index, (currentAction) => ({
                                                                                ...currentAction,
                                                                                ignore_case: e.target.checked,
                                                                            }));
                                                                        }}
                                                                    />
                                                                    {t("ignore_case")}
                                                                </label>
                                                            </div>
                                                        </div>
                                                        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                                                            <div className="space-y-2 rounded-lg border border-white/5 bg-black/10 p-3">
                                                                <div className="text-[10px] uppercase tracking-wider text-main/40 font-bold">{isZh ? "转发目标" : "Forward Target"}</div>
                                                                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                                                                    <div className="space-y-1">
                                                                        <label className="text-[10px] text-main/45">{forwardChatIdLabel}</label>
                                                                        <input
                                                                            className="!mb-0 !h-9 !text-xs"
                                                                            value={action.forward_chat_id || ""}
                                                                            onChange={(e) => {
                                                                                updateCurrentDialogAction(index, (currentAction) => ({
                                                                                    ...currentAction,
                                                                                    forward_chat_id: e.target.value,
                                                                                }));
                                                                            }}
                                                                            placeholder={forwardChatIdPlaceholder}
                                                                        />
                                                                    </div>
                                                                    <div className="space-y-1">
                                                                        <label className="text-[10px] text-main/45">{forwardThreadIdLabel}</label>
                                                                        <input
                                                                            inputMode="numeric"
                                                                            className="!mb-0 !h-9 !text-xs"
                                                                            value={action.forward_message_thread_id ?? ""}
                                                                            onChange={(e) => {
                                                                                updateCurrentDialogAction(index, (currentAction) => ({
                                                                                    ...currentAction,
                                                                                    forward_message_thread_id: e.target.value ? parseInt(e.target.value) : undefined,
                                                                                }));
                                                                            }}
                                                                            placeholder={forwardThreadIdLabel}
                                                                        />
                                                                    </div>
                                                                </div>
                                                            </div>
                                                            <div className="space-y-2 rounded-lg border border-white/5 bg-black/10 p-3">
                                                                <div className="text-[10px] uppercase tracking-wider text-main/40 font-bold">{t("push_channel")}</div>
                                                                <div className="grid grid-cols-1 sm:grid-cols-[140px_minmax(0,1fr)] gap-2">
                                                                    <select
                                                                        className="!mb-0 !h-9 !py-0 !text-xs"
                                                                        value={action.push_channel || "telegram"}
                                                                        onChange={(e) => {
                                                                            updateCurrentDialogAction(index, (currentAction) => ({
                                                                                ...currentAction,
                                                                                push_channel: e.target.value,
                                                                            }));
                                                                        }}
                                                                    >
                                                                        <option value="telegram">{t("telegram_bot_notify")}</option>
                                                                        <option value="bark">Bark</option>
                                                                        <option value="custom">{t("custom_push_url")}</option>
                                                                    </select>
                                                                    <input
                                                                        className="!mb-0 !h-9 !text-xs"
                                                                        value={action.push_channel === "bark" ? (action.bark_url || "") : (action.custom_url || "")}
                                                                        onChange={(e) => {
                                                                            updateCurrentDialogAction(index, (currentAction) => action.push_channel === "bark"
                                                                                ? { ...currentAction, bark_url: e.target.value }
                                                                                : { ...currentAction, custom_url: e.target.value });
                                                                        }}
                                                                        placeholder={action.push_channel === "telegram" ? t("use_telegram_bot_settings") : pushUrlPlaceholder}
                                                                        disabled={(action.push_channel || "telegram") === "telegram"}
                                                                    />
                                                                </div>
                                                            </div>
                                                        </div>
                                                    </div>
                                                )}
                                            </div>

                                            <button
                                                onClick={() => showCreateDialog ? handleRemoveAction(index) : handleEditRemoveAction(index)}
                                                className="action-btn shrink-0 !w-10 !h-10 !text-rose-400 !bg-rose-500/5 hover:!bg-rose-500/10"
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
                                {loading ? <Spinner className="animate-spin" /> : (showCreateDialog ? t("add_task") : t("save_changes"))}
                            </button>
                        </footer>
                    </div>
                </div>
            )
            }

            {copyTaskDialog && (
                <div className="modal-overlay active">
                    <div className="glass-panel modal-content !max-w-3xl flex flex-col" onClick={(e) => e.stopPropagation()}>
                        <header className="modal-header border-b border-white/5 pb-3 mb-0">
                            <div className="modal-title flex items-center gap-2 !text-base">
                                <Copy weight="bold" size={18} />
                                {copyTaskDialogTitle}: {copyTaskDialog.taskName}
                            </div>
                            <button onClick={closeCopyTaskDialog} className="modal-close" disabled={copyingConfig}>
                                <X weight="bold" />
                            </button>
                        </header>
                        <div className="p-5 space-y-3">
                            <p className="text-xs text-main/60">{copyTaskDialogDesc}</p>
                            <textarea
                                className="w-full h-72 !mb-0 font-mono text-xs"
                                value={copyTaskDialog.config}
                                readOnly
                            />
                        </div>
                        <footer className="p-5 border-t border-white/5 flex gap-3">
                            <button
                                className="btn-secondary flex-1"
                                onClick={closeCopyTaskDialog}
                                disabled={copyingConfig}
                            >
                                {t("close")}
                            </button>
                            <button
                                className="btn-gradient flex-1"
                                onClick={handleCopyTaskConfig}
                                disabled={copyingConfig}
                            >
                                {copyingConfig ? <Spinner className="animate-spin" /> : copyConfigAction}
                            </button>
                        </footer>
                    </div>
                </div>
            )}

            {showPasteDialog && (
                <div className="modal-overlay active">
                    <div className="glass-panel modal-content !max-w-3xl flex flex-col" onClick={(e) => e.stopPropagation()}>
                        <header className="modal-header border-b border-white/5 pb-3 mb-0">
                            <div className="modal-title flex items-center gap-2 !text-base">
                                <ClipboardText weight="bold" size={18} />
                                {pasteTaskDialogTitle}
                            </div>
                            <button onClick={closePasteTaskDialog} className="modal-close" disabled={importingPastedConfig || loading}>
                                <X weight="bold" />
                            </button>
                        </header>
                        <div className="p-5 space-y-3">
                            <p className="text-xs text-main/60">{pasteTaskDialogDesc}</p>
                            <textarea
                                className="w-full h-72 !mb-0 font-mono text-xs"
                                placeholder={pasteTaskDialogPlaceholder}
                                value={pasteTaskConfigInput}
                                onChange={(e) => setPasteTaskConfigInput(e.target.value)}
                            />
                        </div>
                        <footer className="p-5 border-t border-white/5 flex gap-3">
                            <button
                                className="btn-secondary flex-1"
                                onClick={closePasteTaskDialog}
                                disabled={importingPastedConfig || loading}
                            >
                                {t("cancel")}
                            </button>
                            <button
                                className="btn-gradient flex-1"
                                onClick={handlePasteDialogImport}
                                disabled={importingPastedConfig || loading}
                            >
                                {importingPastedConfig ? <Spinner className="animate-spin" /> : importTaskAction}
                            </button>
                        </footer>
                    </div>
                </div>
            )}

            {liveLogTaskName && (
                <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 sm:p-6 bg-black/60 backdrop-blur-sm animate-fade-in">
                    <div className="glass-panel w-full max-w-4xl h-[72vh] flex flex-col shadow-2xl border border-white/10 overflow-hidden animate-zoom-in">
                        <div className="p-4 border-b border-white/5 flex justify-between items-center bg-white/2">
                            <div className="flex items-center gap-3">
                                <div className="w-8 h-8 rounded-lg bg-emerald-500/15 flex items-center justify-center text-emerald-400">
                                    {runningTaskNames.has(liveLogTaskName) ? (
                                        <Spinner className="animate-spin" size={18} />
                                    ) : (
                                        <ListDashes weight="bold" size={18} />
                                    )}
                                </div>
                                <h3 className="font-bold tracking-tight">
                                    {t("task_run_logs_title").replace("{name}", liveLogTaskName)}
                                </h3>
                            </div>
                            <button
                                onClick={() => setLiveLogTaskName(null)}
                                className="action-btn !w-8 !h-8 hover:bg-white/10"
                            >
                                <X weight="bold" />
                            </button>
                        </div>
                        <div className="flex-1 overflow-y-auto p-4 font-mono text-[11px] leading-relaxed bg-black/20">
                            {liveLogs.length === 0 ? (
                                <div className="flex items-center gap-2 text-main/30 italic">
                                    {runningTaskNames.has(liveLogTaskName) ? (
                                        <Spinner className="animate-spin" size={12} />
                                    ) : null}
                                    {t("logs_waiting")}
                                </div>
                            ) : (
                                <div className="space-y-1">
                                    {liveLogs.map((line, index) => (
                                        <div key={`${index}-${line}`} className="text-main/80 flex gap-2">
                                            <span className="text-main/20 select-none w-8 text-right">
                                                {(index + 1).toString().padStart(2, "0")}
                                            </span>
                                            <span className="break-all">{line}</span>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            )}

            {historyTaskName && (
                <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 sm:p-6 bg-black/60 backdrop-blur-sm animate-fade-in">
                    <div className="glass-panel w-full max-w-4xl h-[78vh] flex flex-col shadow-2xl border border-white/10 overflow-hidden animate-zoom-in">
                        <div className="p-4 border-b border-white/5 flex justify-between items-center bg-white/2">
                            <div className="flex items-center gap-3">
                                <div className="w-8 h-8 rounded-lg bg-[#8a3ffc]/20 flex items-center justify-center text-[#b57dff]">
                                    <ListDashes weight="bold" size={18} />
                                </div>
                                <h3 className="font-bold tracking-tight">
                                    {t("task_history_logs_title").replace("{name}", historyTaskName)}
                                </h3>
                            </div>
                            <button
                                onClick={() => setHistoryTaskName(null)}
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
                                    {historyLogs.map((log, i) => {
                                        const logKey = `${log.time}-${i}`;
                                        const hasMultiLineLogs = Boolean(log.flow_logs && log.flow_logs.length > 1);
                                        const isExpanded = expandedHistoryLogs.has(logKey);
                                        const visibleFlowLogs = hasMultiLineLogs && !isExpanded
                                            ? (log.flow_logs || []).slice(0, 1)
                                            : (log.flow_logs || []);
                                        return (
                                        <div key={logKey} className="rounded-xl border border-white/5 bg-white/5 overflow-hidden">
                                            <div className="flex justify-between items-center px-3 py-2 border-b border-white/5 text-[10px]">
                                                <div className="flex items-center gap-2 min-w-0">
                                                    <span className="text-main/30 truncate">
                                                        {new Date(log.time).toLocaleString(language === "zh" ? "zh-CN" : "en-US")}
                                                    </span>
                                                    {hasMultiLineLogs && (
                                                        <button
                                                            type="button"
                                                            className="text-[#8a3ffc] hover:text-[#b57dff] font-bold shrink-0"
                                                            onClick={() => {
                                                                setExpandedHistoryLogs((prev) => {
                                                                    const next = new Set(prev);
                                                                    if (next.has(logKey)) {
                                                                        next.delete(logKey);
                                                                    } else {
                                                                        next.add(logKey);
                                                                    }
                                                                    return next;
                                                                });
                                                            }}
                                                        >
                                                            {isExpanded ? (isZh ? "鏀剁缉" : "Collapse") : (isZh ? "灞曞紑瀹屾暣鏃ュ織" : "Expand full log")}
                                                        </button>
                                                    )}
                                                </div>
                                                <span className={log.success ? "text-emerald-400" : "text-rose-400"}>
                                                    {log.success ? t("success") : t("failure")}
                                                </span>
                                            </div>
                                            <div className="p-3 space-y-1">
                                                <div className="text-main/90">
                                                    {isZh
                                                        ? `浠诲姟锛?{historyTaskName}${log.success ? "鎵ц鎴愬姛" : "鎵ц澶辫触"}`
                                                        : `Task: ${historyTaskName} ${log.success ? "succeeded" : "failed"}`}
                                                </div>
                                                {log.message ? (
                                                    <div className="text-main/60 break-all">
                                                        {isZh ? `鏈哄櫒浜烘秷鎭細${log.message}` : `Bot message: ${log.message}`}
                                                    </div>
                                                ) : null}
                                                {visibleFlowLogs.length > 0 ? (
                                                    visibleFlowLogs.map((line, lineIndex) => (
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
                                        );
                                    })}
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            )}

            <ToastContainer toasts={toasts} removeToast={removeToast} />
        </div >
    );
}

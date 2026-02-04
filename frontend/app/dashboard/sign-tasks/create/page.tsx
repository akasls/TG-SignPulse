"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { getToken } from "../../../../lib/auth";
import {
    createSignTask,
    listAccounts,
    getAccountChats,
    searchAccountChats,
    AccountInfo,
    ChatInfo,
    SignTaskChat,
} from "../../../../lib/api";
import {
    CaretLeft,
    Plus,
    X,
    ChatCircleText,
    Clock,
    Trash,
    Spinner,
    DiceFive,
    Robot,
    MathOperations,
    Lightning,
    Check
} from "@phosphor-icons/react";
import { ThemeLanguageToggle } from "../../../../components/ThemeLanguageToggle";
import { useLanguage } from "../../../../context/LanguageContext";
import { ToastContainer, useToast } from "../../../../components/ui/toast";

export default function CreateSignTaskPage() {
    const router = useRouter();
    const { t } = useLanguage();
    const { toasts, addToast, removeToast } = useToast();
    const [token, setLocalToken] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);

    // 表单数据
    const [taskName, setTaskName] = useState("");
    const [executionMode, setExecutionMode] = useState<"fixed" | "range">("range");
    const [signAt, setSignAt] = useState("0 6 * * *");
    const [rangeStart, setRangeStart] = useState("09:00");
    const [rangeEnd, setRangeEnd] = useState("18:00");
    const [randomSeconds, setRandomSeconds] = useState(0);
    const [chatId, setChatId] = useState(0);
    const [signInterval, setSignInterval] = useState(1);
    const [chats, setChats] = useState<SignTaskChat[]>([]);

    // 账号和 Chat 数据
    const [accounts, setAccounts] = useState<AccountInfo[]>([]);
    const [selectedAccount, setSelectedAccount] = useState("");
    const [availableChats, setAvailableChats] = useState<ChatInfo[]>([]);
    const [chatSearch, setChatSearch] = useState("");
    const [chatSearchResults, setChatSearchResults] = useState<ChatInfo[]>([]);
    const [chatSearchLoading, setChatSearchLoading] = useState(false);

    const formatErrorMessage = useCallback((key: string, err?: any) => {
        const base = t(key);
        const code = err?.code;
        return code ? `${base} (${code})` : base;
    }, [t]);

    // 当前编辑的 Chat
    const [editingChat, setEditingChat] = useState<{
        chat_id: number;
        name: string;
        actions: any[];
        delete_after?: number;
        action_interval: number;
    } | null>(null);

    const loadChats = useCallback(async (tokenStr: string, accountName: string) => {
        try {
            const chatsData = await getAccountChats(tokenStr, accountName);
            setAvailableChats(chatsData);
        } catch (err: any) {
            console.error("加载 Chat 失败:", err);
        }
    }, []);

    const loadAccounts = useCallback(async (tokenStr: string) => {
        try {
            const data = await listAccounts(tokenStr);
            setAccounts(data.accounts);
            if (data.accounts.length > 0) {
                setSelectedAccount(data.accounts[0].name);
                loadChats(tokenStr, data.accounts[0].name);
            }
        } catch (err: any) {
            addToast(formatErrorMessage("load_failed", err), "error");
        }
    }, [addToast, loadChats, formatErrorMessage]);

    useEffect(() => {
        const tokenStr = getToken();
        if (!tokenStr) {
            router.replace("/");
            return;
        }
        setLocalToken(tokenStr);
        loadAccounts(tokenStr);
    }, [router, loadAccounts]);

    const handleAccountChange = (accountName: string) => {
        setSelectedAccount(accountName);
        if (token) {
            loadChats(token, accountName);
        }
    };

    useEffect(() => {
        if (!token || !selectedAccount) return;
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
                const res = await searchAccountChats(token, selectedAccount, query, 50, 0);
                if (!cancelled) {
                    setChatSearchResults(res.items || []);
                }
            } catch (err: any) {
                if (!cancelled) {
                    addToast(formatErrorMessage("search_failed", err), "error");
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
    }, [chatSearch, token, selectedAccount, addToast, t, formatErrorMessage]);

    useEffect(() => {
        if (!editingChat) {
            setChatSearch("");
            setChatSearchResults([]);
            setChatSearchLoading(false);
        }
    }, [editingChat, selectedAccount]);

    const handleAddChat = () => {
        setEditingChat({
            chat_id: 0,
            name: "",
            actions: [],
            action_interval: 1,
        });
    };

    const handleSaveChat = () => {
        if (!editingChat) return;
        if (editingChat.chat_id === 0) {
            addToast(t("select_chat_error"), "error");
            return;
        }
        if (editingChat.actions.length === 0) {
            addToast(t("add_action_error"), "error");
            return;
        }
        setChats([...chats, editingChat]);
        setEditingChat(null);
    };

    const handleSubmit = async () => {
        if (!token) return;
        if (!taskName) {
            addToast(t("task_name_required"), "error");
            return;
        }
        if (executionMode === "fixed" && !signAt) {
            addToast(t("cron_required"), "error");
            return;
        }
        if (executionMode === "range" && (!rangeStart || !rangeEnd)) {
            addToast(t("range_required"), "error");
            return;
        }
        if (chats.length === 0) {
            addToast(t("chat_required"), "error");
            return;
        }

        try {
            setLoading(true);
            await createSignTask(token, {
                name: taskName,
                account_name: selectedAccount,
                sign_at: executionMode === "fixed" ? signAt : "0 0 * * *", // 占位，后端会处理
                chats: chats,
                random_seconds: randomSeconds,
                sign_interval: signInterval,
                execution_mode: executionMode,
                range_start: rangeStart,
                range_end: rangeEnd,
            });
            addToast(t("create_success"), "success");
            setTimeout(() => router.push("/dashboard/sign-tasks"), 1500);
        } catch (err: any) {
            addToast(formatErrorMessage("create_failed", err), "error");
        } finally {
            setLoading(false);
        }
    };

    if (!token) return null;

    return (
        <div id="create-task-view" className="w-full h-full flex flex-col pt-[72px]">
            <nav className="navbar fixed top-0 left-0 right-0 z-50 h-[72px] px-5 md:px-10 flex justify-between items-center glass-panel rounded-none border-x-0 border-t-0 bg-white/2 dark:bg-black/5">
                <div className="flex items-center gap-4">
                    <Link href="/dashboard/sign-tasks" className="action-btn" title={t("cancel")}>
                        <CaretLeft weight="bold" />
                    </Link>
                    <div className="flex items-center gap-2 text-sm font-medium">
                        <span className="text-main/40 uppercase tracking-widest text-[10px]">{t("sidebar_tasks")}</span>
                        <span className="text-main/20">/</span>
                        <span className="text-main uppercase tracking-widest text-[10px]">{t("add_task")}</span>
                    </div>
                </div>
                <div className="flex items-center gap-4">
                    <ThemeLanguageToggle />
                </div>
            </nav>

            <main className="flex-1 p-5 md:p-10 w-full max-w-[900px] mx-auto overflow-y-auto animate-float-up pb-20">
                <header className="mb-10">
                    <h1 className="text-3xl font-bold tracking-tight mb-2">{t("add_task")}</h1>
                    <p className="text-[#9496a1] text-sm">{t("define_global_rules")}</p>
                </header>

                <div className="grid gap-8">
                    {/* 基本配置 */}
                    <section className="glass-panel p-6 space-y-6">
                        <div className="flex items-center gap-3 mb-2">
                            <div className="p-2 bg-[#8a3ffc]/10 rounded-lg text-[#b57dff]">
                                <Lightning weight="fill" size={18} />
                            </div>
                            <h2 className="text-lg font-bold">{t("basic_config")}</h2>
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                            <div className="space-y-2">
                                <label className="text-xs font-bold text-main/40 uppercase tracking-wider">{t("task_name")}</label>
                                <input
                                    className="!mb-0"
                                    value={taskName}
                                    onChange={(e) => setTaskName(e.target.value)}
                                    placeholder={t("task_name_placeholder")}
                                />
                            </div>
                            <div className="space-y-2">
                                <label className="text-xs font-bold text-main/40 uppercase tracking-wider">{t("associated_account")}</label>
                                <select
                                    className="!mb-0"
                                    value={selectedAccount}
                                    onChange={(e) => handleAccountChange(e.target.value)}
                                >
                                    {accounts.map(acc => <option key={acc.name} value={acc.name}>{acc.name}</option>)}
                                </select>
                            </div>
                        </div>

                        {/* 调度模式 (Only Range Mode Displayed) */}
                        <div className="p-4 glass-panel !bg-black/5 space-y-4 border-white/5">
                            <div className="flex items-center justify-between mb-4">
                                <label className="text-xs font-bold text-main/40 uppercase tracking-wider">
                                    {t("scheduling_mode")}
                                </label>
                                <div className="text-xs font-bold text-[#8a3ffc] bg-[#8a3ffc]/10 px-2 py-1 rounded">
                                    {t("random_range_default")}
                                </div>
                            </div>

                            <p className="text-xs text-[#9496a1] mb-4">
                                {t("random_range_desc")}
                            </p>

                            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 animate-fade-in">
                                <div className="space-y-2">
                                    <label className="text-xs font-bold text-main/40 uppercase tracking-wider">{t("start_time")}</label>
                                    <input
                                        type="time"
                                        className="!mb-0"
                                        value={rangeStart}
                                        onChange={(e) => setRangeStart(e.target.value)}
                                    />
                                </div>
                                <div className="space-y-2">
                                    <label className="text-xs font-bold text-main/40 uppercase tracking-wider">{t("end_time")}</label>
                                    <input
                                        type="time"
                                        className="!mb-0"
                                        value={rangeEnd}
                                        onChange={(e) => setRangeEnd(e.target.value)}
                                    />
                                </div>
                            </div>
                        </div>


                    </section>

                    {/* Chat 配置 */}
                    <section className="glass-panel p-6 space-y-6">
                        <div className="flex items-center justify-between">
                            <div className="flex items-center gap-3">
                                <div className="p-2 bg-[#8a3ffc]/10 rounded-lg text-[#b57dff]">
                                    <ChatCircleText weight="fill" size={18} />
                                </div>
                                <h2 className="text-lg font-bold">{t("target_chat_config")} ({chats.length})</h2>
                            </div>
                            <button onClick={handleAddChat} className="btn-secondary !h-8 !px-3 font-bold !text-[10px]">
                                + {t("add_chat")}
                            </button>
                        </div>

                        {
                            chats.length === 0 ? (
                                <div className="py-10 text-center border-2 border-dashed border-white/5 rounded-2xl text-main/20">
                                    <p className="text-sm">{t("no_target_chat")}</p>
                                </div>
                            ) : (
                                <div className="flex flex-col gap-3">
                                    {chats.map((chat, idx) => (
                                        <div key={idx} className="glass-panel !bg-black/5 p-4 flex items-center justify-between group">
                                            <div className="flex items-center gap-4">
                                                <div className="w-10 h-10 rounded-xl bg-white/5 flex items-center justify-center font-bold text-xs">
                                                    {idx + 1}
                                                </div>
                                                <div>
                                                    <div className="font-bold text-sm">{chat.name}</div>
                                                    <div className="text-[10px] text-main/30 font-mono mt-0.5">
                                                        {t("id_label")}: {chat.chat_id} | <span className="text-[#8a3ffc]/60 font-bold">{chat.actions.length} {t("actions_count")}</span>
                                                    </div>
                                                </div>
                                            </div>
                                            <button
                                                onClick={() => setChats(chats.filter((_, i) => i !== idx))}
                                                className="action-btn !text-rose-400 hover:!bg-rose-500/10"
                                            >
                                                <Trash weight="bold" />
                                            </button>
                                        </div>
                                    ))}
                                </div>
                            )
                        }
                    </section>

                    <div className="flex gap-4 pt-4">
                        <button onClick={() => router.back()} className="btn-secondary flex-1">{t("cancel")}</button>
                        <button onClick={handleSubmit} disabled={loading} className="btn-gradient flex-1">
                            {loading ? <Spinner className="animate-spin mx-auto" weight="bold" /> : t("deploy_task")}
                        </button>
                    </div>
                </div>
            </main>

            {/* Editing Dialog */}
            {
                editingChat && (
                    <div className="modal-overlay fixed inset-0 z-[100] flex items-center justify-center p-4">
                        <div className="glass-panel modal-content w-full max-w-lg animate-scale-in flex flex-col overflow-hidden">
                            <header className="p-6 border-b border-white/5 flex justify-between items-center bg-black/5">
                                <h2 className="text-xl font-bold flex items-center gap-3">
                                    <div className="p-2 bg-[#8a3ffc]/10 rounded-lg text-[#b57dff]">
                                        <Plus weight="bold" size={20} />
                                    </div>
                                    {t("configure_target_chat")}
                                </h2>
                                <button onClick={() => setEditingChat(null)} className="action-btn !w-8 !h-8">
                                    <X weight="bold" />
                                </button>
                            </header>

                            <div className="p-6 space-y-6">
                                <div className="space-y-2">
                                    <label className="text-xs uppercase tracking-widest font-bold text-main/40">{t("select_target_chat")}</label>
                                    <div className="space-y-2">
                                        <label className="text-[10px] text-main/40 uppercase tracking-wider">{t("search_chat")}</label>
                                        <input
                                            className="!mb-0"
                                            placeholder={t("search_chat_placeholder")}
                                            value={chatSearch}
                                            onChange={(e) => setChatSearch(e.target.value)}
                                        />
                                    </div>
                                    {chatSearch.trim() ? (
                                        <div className="mt-2 max-h-48 overflow-y-auto rounded-lg border border-white/5 bg-black/5">
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
                                                                    setEditingChat({ ...editingChat, chat_id: chat.id, name: title });
                                                                    setChatSearch("");
                                                                    setChatSearchResults([]);
                                                                }}
                                                            >
                                                                <div className="text-sm font-semibold truncate">{title}</div>
                                                                <div className="text-[10px] text-main/40 font-mono truncate">
                                                                    {chat.id}{chat.username ? ` · @${chat.username}` : ""}
                                                                </div>
                                                            </button>
                                                        );
                                                    })}
                                                </div>
                                            ) : (
                                                <div className="px-3 py-2 text-xs text-main/40">{t("search_no_results")}</div>
                                            )}
                                        </div>
                                    ) : (
                                        <select
                                            className="mt-2"
                                            value={editingChat.chat_id}
                                            onChange={(e) => {
                                                const cid = parseInt(e.target.value);
                                                const chat = availableChats.find(c => c.id === cid);
                                                setEditingChat({ ...editingChat, chat_id: cid, name: chat?.title || chat?.username || "" });
                                            }}
                                        >
                                            <option value={0}>{t("select_chat_placeholder")}</option>
                                            {availableChats.map(c => <option key={c.id} value={c.id}>{c.title || c.username}</option>)}
                                        </select>
                                    )}
                                </div>

                                <div className="space-y-4">
                                    <div className="flex items-center justify-between">
                                        <label className="text-xs uppercase tracking-widest font-bold text-main/40">{t("action_sequence_title")}</label>
                                        <button
                                            onClick={() => setEditingChat({ ...editingChat, actions: [...editingChat.actions, { action: 1, text: "" }] })}
                                            className="text-[10px] font-bold text-[#8a3ffc] hover:underline"
                                        >
                                            + {t("add_sign_action")}
                                        </button>
                                    </div>

                                    <div className="max-h-[200px] overflow-y-auto space-y-3 custom-scrollbar pr-2">
                                        {editingChat.actions.map((act, i) => (
                                            <div key={i} className="flex gap-3 items-center animate-scale-in">
                                                <div className="w-6 h-6 rounded-lg bg-white/5 flex items-center justify-center text-[10px] font-bold text-main/30">
                                                    {i + 1}
                                                </div>
                                                <input
                                                    className="!h-9 !text-sm"
                                                    value={act.text}
                                                    onChange={(e) => {
                                                        const newActs = [...editingChat.actions];
                                                        newActs[i] = { ...newActs[i], text: e.target.value };
                                                        setEditingChat({ ...editingChat, actions: newActs });
                                                    }}
                                                />
                                                <button
                                                    onClick={() => {
                                                        const newActs = editingChat.actions.filter((_, idx) => idx !== i);
                                                        setEditingChat({ ...editingChat, actions: newActs });
                                                    }}
                                                    className="action-btn !w-9 !h-9 !text-rose-400"
                                                >
                                                    <X weight="bold" />
                                                </button>
                                            </div>
                                        ))}
                                        {editingChat.actions.length === 0 && (
                                            <div className="text-center py-4 text-xs text-main/20 italic">
                                                {t("no_actions_hint")}
                                            </div>
                                        )}
                                    </div>
                                </div>
                            </div>

                            <footer className="p-6 border-t border-white/5 flex gap-4 bg-black/10">
                                <button onClick={() => setEditingChat(null)} className="btn-secondary flex-1">{t("cancel")}</button>
                                <button onClick={handleSaveChat} className="btn-gradient flex-1 flex items-center justify-center gap-2">
                                    <Check weight="bold" />
                                    {t("confirm_add")}
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

"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { getToken } from "../../../lib/auth";
import {
    changePassword,
    changeUsername,
    getTOTPStatus,
    setupTOTP,
    getTOTPQRCode,
    enableTOTP,
    disableTOTP,
    exportAllConfigs,
    importAllConfigs,
    getAIConfig,
    saveAIConfig,
    testAIConnection,
    deleteAIConfig,
    AIConfig,
    getGlobalSettings,
    saveGlobalSettings,
    GlobalSettings,
    getTelegramConfig,
    saveTelegramConfig,
    resetTelegramConfig,
    TelegramConfig,
} from "../../../lib/api";
import {
    CaretLeft,
    User,
    Lock,
    ShieldCheck,
    Gear,
    Cpu,
    DownloadSimple,
    SignOut,
    Spinner,
    ArrowUDownLeft,
    FloppyDisk,
    WarningCircle,
    Trash,
    Robot as BotIcon,
    Terminal,
    GithubLogo
} from "@phosphor-icons/react";
import { ToastContainer, useToast } from "../../../components/ui/toast";
import { ThemeLanguageToggle } from "../../../components/ThemeLanguageToggle";
import { useLanguage } from "../../../context/LanguageContext";

export default function SettingsPage() {
    const router = useRouter();
    const { t } = useLanguage();
    const { toasts, addToast, removeToast } = useToast();
    const [token, setLocalToken] = useState<string | null>(null);
    const [userLoading, setUserLoading] = useState(false);
    const [pwdLoading, setPwdLoading] = useState(false);
    const [totpLoading, setTotpLoading] = useState(false);
    const [configLoading, setConfigLoading] = useState(false);
    const [telegramLoading, setTelegramLoading] = useState(false);

    // 用户名修改
    const [usernameForm, setUsernameForm] = useState({
        newUsername: "",
        password: "",
    });

    // 密码修改
    const [passwordForm, setPasswordForm] = useState({
        oldPassword: "",
        newPassword: "",
        confirmPassword: "",
    });

    // 2FA 状态
    const [totpEnabled, setTotpEnabled] = useState(false);
    const [totpSecret, setTotpSecret] = useState("");
    const [totpCode, setTotpCode] = useState("");
    const [showTotpSetup, setShowTotpSetup] = useState(false);

    // 配置导入导出
    const [importConfig, setImportConfig] = useState("");
    const [overwriteConfig, setOverwriteConfig] = useState(false);

    // AI 配置
    const [aiConfig, setAIConfigState] = useState<AIConfig | null>(null);
    const [aiForm, setAIForm] = useState({
        api_key: "",
        base_url: "",
        model: "gpt-4o",
    });
    const [aiTestResult, setAITestResult] = useState<string | null>(null);
    const [aiTestStatus, setAITestStatus] = useState<"success" | "error" | null>(null);
    const [aiTesting, setAITesting] = useState(false);

    // 全局设置
    const [globalSettings, setGlobalSettings] = useState<GlobalSettings>({ sign_interval: null, log_retention_days: 7 });

    // Telegram API 配置
    const [telegramConfig, setTelegramConfig] = useState<TelegramConfig | null>(null);
    const [telegramForm, setTelegramForm] = useState({
        api_id: "",
        api_hash: "",
    });

    const [checking, setChecking] = useState(true);

    const formatErrorMessage = (key: string, err?: any) => {
        const base = t(key);
        const code = err?.code;
        return code ? `${base} (${code})` : base;
    };

    useEffect(() => {
        const tokenStr = getToken();
        if (!tokenStr) {
            window.location.replace("/");
            return;
        }
        setLocalToken(tokenStr);
        setChecking(false);
        loadTOTPStatus(tokenStr);
        loadAIConfig(tokenStr);
        loadGlobalSettings(tokenStr);
        loadTelegramConfig(tokenStr);
    }, []);

    const loadTOTPStatus = async (tokenStr: string) => {
        try {
            const res = await getTOTPStatus(tokenStr);
            setTotpEnabled(res.enabled);
        } catch (err) { }
    };

    const loadAIConfig = async (tokenStr: string) => {
        try {
            const config = await getAIConfig(tokenStr);
            setAIConfigState(config);
            if (config) {
                setAIForm({
                    api_key: "", // 不回填密钥
                    base_url: config.base_url || "",
                    model: config.model || "gpt-4o",
                });
            }
        } catch (err) { }
    };

    const loadGlobalSettings = async (tokenStr: string) => {
        try {
            const settings = await getGlobalSettings(tokenStr);
            setGlobalSettings(settings);
        } catch (err) { }
    };

    const loadTelegramConfig = async (tokenStr: string) => {
        try {
            const config = await getTelegramConfig(tokenStr);
            setTelegramConfig(config);
            if (config) {
                setTelegramForm({
                    api_id: config.api_id?.toString() || "",
                    api_hash: config.api_hash || "",
                });
            }
        } catch (err) { }
    };

    const handleChangeUsername = async () => {
        if (!token) return;
        if (!usernameForm.newUsername || !usernameForm.password) {
            addToast(t("form_incomplete"), "error");
            return;
        }
        try {
            setUserLoading(true);
            const res = await changeUsername(token, usernameForm.newUsername, usernameForm.password);
            addToast(t("username_changed"), "success");
            if (res.access_token) {
                localStorage.setItem("tg-signer-token", res.access_token);
                setLocalToken(res.access_token);
            }
            setUsernameForm({ newUsername: "", password: "" });
        } catch (err: any) {
            addToast(formatErrorMessage("change_failed", err), "error");
        } finally {
            setUserLoading(false);
        }
    };

    const handleChangePassword = async () => {
        if (!token) return;
        if (!passwordForm.oldPassword || !passwordForm.newPassword) {
            addToast(t("form_incomplete"), "error");
            return;
        }
        if (passwordForm.newPassword !== passwordForm.confirmPassword) {
            addToast(t("password_mismatch"), "error");
            return;
        }
        try {
            setPwdLoading(true);
            await changePassword(token, passwordForm.oldPassword, passwordForm.newPassword);
            addToast(t("password_changed"), "success");
            setPasswordForm({ oldPassword: "", newPassword: "", confirmPassword: "" });
        } catch (err: any) {
            addToast(formatErrorMessage("change_failed", err), "error");
        } finally {
            setPwdLoading(false);
        }
    };

    const handleSetupTOTP = async () => {
        if (!token) return;
        try {
            setTotpLoading(true);
            const res = await setupTOTP(token);
            setTotpSecret(res.secret);
            setShowTotpSetup(true);
        } catch (err: any) {
            addToast(formatErrorMessage("setup_failed", err), "error");
        } finally {
            setTotpLoading(false);
        }
    };

    const handleEnableTOTP = async () => {
        if (!token) return;
        if (!totpCode) {
            addToast(t("login_code_required"), "error");
            return;
        }
        try {
            setTotpLoading(true);
            await enableTOTP(token, totpCode);
            addToast(t("two_factor_enabled"), "success");
            setTotpEnabled(true);
            setShowTotpSetup(false);
            setTotpCode("");
        } catch (err: any) {
            addToast(formatErrorMessage("enable_failed", err), "error");
        } finally {
            setTotpLoading(false);
        }
    };

    const handleDisableTOTP = async () => {
        if (!token) return;
        const msg = t("two_factor_disable_prompt");
        const code = prompt(msg);
        if (!code) return;
        try {
            setTotpLoading(true);
            await disableTOTP(token, code);
            addToast(t("two_factor_disabled"), "success");
            setTotpEnabled(false);
        } catch (err: any) {
            addToast(formatErrorMessage("disable_failed", err), "error");
        } finally {
            setTotpLoading(false);
        }
    };

    const handleExport = async () => {
        if (!token) return;
        try {
            setConfigLoading(true);
            const config = await exportAllConfigs(token);
            const blob = new Blob([config], { type: "application/json" });
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = "tg-signer-config.json";
            a.click();
            addToast(t("export_success"), "success");
        } catch (err: any) {
            addToast(formatErrorMessage("export_failed", err), "error");
        } finally {
            setConfigLoading(false);
        }
    };

    const handleImport = async () => {
        if (!token) return;
        if (!importConfig) {
            addToast(t("import_empty"), "error");
            return;
        }
        try {
            setConfigLoading(true);
            await importAllConfigs(token, importConfig, overwriteConfig);
            addToast(t("import_success"), "success");
            setImportConfig("");
            loadAIConfig(token);
            loadGlobalSettings(token);
            loadTelegramConfig(token);
        } catch (err: any) {
            addToast(formatErrorMessage("import_failed", err), "error");
        } finally {
            setConfigLoading(false);
        }
    };

    const handleSaveAI = async () => {
        if (!token) return;
        try {
            setConfigLoading(true);
            await saveAIConfig(token, aiForm);
            addToast(t("ai_save_success"), "success");
            loadAIConfig(token);
        } catch (err: any) {
            addToast(formatErrorMessage("save_failed", err), "error");
        } finally {
            setConfigLoading(false);
        }
    };

    const handleTestAI = async () => {
        if (!token) return;
        try {
            setAITesting(true);
            setAITestResult(null);
            setAITestStatus(null);
            const res = await testAIConnection(token);
            if (res.success) {
                setAITestStatus("success");
                setAITestResult(t("connect_success"));
            } else {
                setAITestStatus("error");
                setAITestResult(t("connect_failed"));
            }
        } catch (err: any) {
            setAITestStatus("error");
            setAITestResult(formatErrorMessage("test_failed", err));
        } finally {
            setAITesting(false);
        }
    };

    const handleDeleteAI = async () => {
        if (!token) return;
        if (!confirm(t("confirm_delete_ai"))) return;
        try {
            setConfigLoading(true);
            await deleteAIConfig(token);
            addToast(t("ai_delete_success"), "success");
            setAIConfigState(null);
            setAIForm({ api_key: "", base_url: "", model: "gpt-4o" });
        } catch (err: any) {
            addToast(formatErrorMessage("delete_failed", err), "error");
        } finally {
            setConfigLoading(false);
        }
    };

    const handleSaveGlobal = async () => {
        if (!token) return;
        try {
            setConfigLoading(true);
            await saveGlobalSettings(token, globalSettings);
            addToast(t("global_save_success"), "success");
        } catch (err: any) {
            addToast(formatErrorMessage("save_failed", err), "error");
        } finally {
            setConfigLoading(false);
        }
    };

    const handleSaveTelegram = async () => {
        if (!token) return;
        if (!telegramForm.api_id || !telegramForm.api_hash) {
            addToast(t("form_incomplete"), "error");
            return;
        }
        try {
            setTelegramLoading(true);
            await saveTelegramConfig(token, {
                api_id: telegramForm.api_id,
                api_hash: telegramForm.api_hash,
            });
            addToast(t("telegram_save_success"), "success");
            loadTelegramConfig(token);
        } catch (err: any) {
            addToast(formatErrorMessage("save_failed", err), "error");
        } finally {
            setTelegramLoading(false);
        }
    };

    const handleResetTelegram = async () => {
        if (!token) return;
        if (!confirm(t("confirm_reset_telegram"))) return;
        try {
            setTelegramLoading(true);
            await resetTelegramConfig(token);
            addToast(t("config_reset"), "success");
            loadTelegramConfig(token);
        } catch (err: any) {
            addToast(formatErrorMessage("operation_failed", err), "error");
        } finally {
            setTelegramLoading(false);
        }
    };

    if (!token || checking) {
        return null;
    }

    return (
        <div id="settings-view" className="w-full h-full flex flex-col">
            <nav className="navbar">
                <div className="nav-brand">
                    <div className="flex items-center gap-4">
                        <Link href="/dashboard" className="action-btn !w-8 !h-8" title={t("sidebar_home")}>
                            <CaretLeft weight="bold" size={18} />
                        </Link>
                        <h1 className="text-lg font-bold tracking-tight">{t("sidebar_settings")}</h1>
                    </div>
                </div>
                <div className="top-right-actions">
                    <a
                        href="https://github.com/akasls/TG-SignPulse"
                        target="_blank"
                        rel="noreferrer"
                        className="action-btn"
                        title={t("github_repo")}
                    >
                        <GithubLogo weight="bold" />
                    </a>
                    <div
                        className="action-btn !text-rose-400 hover:bg-rose-500/10"
                        title={t("logout")}
                        onClick={() => {
                            const { logout } = require("../../../lib/auth");
                            logout();
                            router.push("/");
                        }}
                    >
                        <SignOut weight="bold" />
                    </div>
                </div>
            </nav>

            <main className="main-content">
                <div className="space-y-6 animate-float-up pb-10">
                    {/* 用户名修改 */}
                    <div className="glass-panel p-4">
                        <div className="flex items-center gap-3 mb-4">
                            <div className="p-2 bg-blue-500/10 rounded-xl text-blue-400">
                                <User weight="bold" size={18} />
                            </div>
                            <h2 className="text-lg font-bold">{t("username")}</h2>
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-5 mb-5">
                            <div>
                                <label className="text-[12px] mb-1.5">{t("new_username")}</label>
                                <input
                                    type="text"
                                    className="!py-2.5 !px-4"
                                    placeholder={t("new_username_placeholder")}
                                    value={usernameForm.newUsername}
                                    onChange={(e) => setUsernameForm({ ...usernameForm, newUsername: e.target.value })}
                                />
                            </div>
                            <div>
                                <label className="text-[12px] mb-1.5">{t("current_password")}</label>
                                <input
                                    type="password"
                                    className="!py-2.5 !px-4"
                                    placeholder={t("current_password_placeholder")}
                                    value={usernameForm.password}
                                    onChange={(e) => setUsernameForm({ ...usernameForm, password: e.target.value })}
                                />
                            </div>
                        </div>
                        <button className="btn-gradient w-fit px-6 !py-2.5 !text-xs" onClick={handleChangeUsername} disabled={userLoading}>
                            {userLoading ? <Spinner className="animate-spin" /> : t("change_username")}
                        </button>
                    </div>

                    {/* 密码修改 */}
                    <div className="glass-panel p-4">
                        <div className="flex items-center gap-3 mb-4">
                            <div className="p-2 bg-amber-500/10 rounded-xl text-amber-400">
                                <Lock weight="bold" size={18} />
                            </div>
                            <h2 className="text-lg font-bold">{t("change_password")}</h2>
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-3 gap-5 mb-5">
                            <div>
                                <label className="text-[12px] mb-1.5">{t("old_password")}</label>
                                <input
                                    type="password"
                                    className="!py-2.5 !px-4"
                                    value={passwordForm.oldPassword}
                                    onChange={(e) => setPasswordForm({ ...passwordForm, oldPassword: e.target.value })}
                                />
                            </div>
                            <div>
                                <label className="text-[12px] mb-1.5">{t("new_password")}</label>
                                <input
                                    type="password"
                                    className="!py-2.5 !px-4"
                                    value={passwordForm.newPassword}
                                    onChange={(e) => setPasswordForm({ ...passwordForm, newPassword: e.target.value })}
                                />
                            </div>
                            <div>
                                <label className="text-[12px] mb-1.5">{t("confirm_new_password")}</label>
                                <input
                                    type="password"
                                    className="!py-2.5 !px-4"
                                    value={passwordForm.confirmPassword}
                                    onChange={(e) => setPasswordForm({ ...passwordForm, confirmPassword: e.target.value })}
                                />
                            </div>
                        </div>
                        <button className="btn-gradient w-fit px-6 !py-2.5 !text-xs" onClick={handleChangePassword} disabled={pwdLoading}>
                            {pwdLoading ? <Spinner className="animate-spin" /> : t("change_password")}
                        </button>
                    </div>

                    {/* 2FA 设置 */}
                    <div className="glass-panel p-4 overflow-hidden">
                        <div className="flex justify-between items-center mb-4">
                            <div className="flex items-center gap-3">
                                <div className="p-2 bg-emerald-500/10 rounded-xl text-emerald-400">
                                    <ShieldCheck weight="bold" size={18} />
                                </div>
                                <h2 className="text-lg font-bold">{t("2fa_settings")}</h2>
                            </div>
                            <div className={`shrink-0 bg-${totpEnabled ? 'emerald' : 'rose'}-500/10 border border-${totpEnabled ? 'emerald' : 'rose'}-500/20 text-${totpEnabled ? 'emerald' : 'rose'}-400 px-3 py-0.5 rounded-full text-[10px] font-bold`}>
                                {totpEnabled ? t("status_enabled") : t("status_disabled")}
                            </div>
                        </div>

                        {!totpEnabled && !showTotpSetup && (
                            <div className="bg-emerald-500/5 border border-emerald-500/10 rounded-xl p-4 flex gap-4 items-start">
                                <div className="p-2 bg-emerald-500/10 rounded-lg text-emerald-400">
                                    <WarningCircle weight="bold" size={18} />
                                </div>
                                <div>
                                    <p className="text-[11px] text-main/70 leading-relaxed max-w-2xl">
                                        {t("2fa_enable_desc")}
                                    </p>
                                    <button onClick={handleSetupTOTP} className="btn-secondary mt-3 w-fit h-8 px-4 text-[11px]" disabled={totpLoading}>
                                        {totpLoading ? <Spinner className="animate-spin" /> : t("start_setup")}
                                    </button>
                                </div>
                            </div>
                        )}

                        {showTotpSetup && (
                            <div className="animate-float-up space-y-4">
                                <div className="flex flex-col md:flex-row gap-4 items-center md:items-start p-4 bg-white/2 rounded-xl border border-white/5 shadow-inner">
                                    <div className="bg-white p-2 rounded-lg shrink-0">
                                        {/* eslint-disable-next-line @next/next/no-img-element */}
                                        <img
                                            src={`/api/user/totp/qrcode?token=${token}`}
                                            alt={t("qr_alt")}
                                            className="w-28 h-28"
                                        />
                                    </div>
                                    <div className="flex-1 space-y-3">
                                        <div>
                                            <h4 className="font-bold text-xs text-main mb-1">{t("scan_qr")}</h4>
                                            <p className="text-[10px] text-[#9496a1]">{t("scan_qr_desc")}</p>
                                        </div>
                                        <div>
                                            <h4 className="font-bold text-xs text-main mb-1">{t("backup_secret")}</h4>
                                            <input
                                                readOnly
                                                value={totpSecret}
                                                className="!p-2.5 !bg-white/2 !border-white/8 !rounded-lg !text-[10px] break-all !font-mono !text-[#b57dff] !mb-0 cursor-text"
                                                onClick={(e) => (e.target as HTMLInputElement).select()}
                                            />
                                        </div>
                                    </div>
                                </div>
                                <div className="space-y-3 w-full max-w-2xl">
                                    <label className="text-[12px] font-bold text-main/60 uppercase tracking-widest">{t("verify_code")}</label>
                                    <div className="flex gap-4">
                                        <input
                                            value={totpCode}
                                            onChange={(e) => setTotpCode(e.target.value)}
                                            placeholder={t("totp_code_placeholder")}
                                            className="text-center text-3xl tracking-[0.8em] h-14 !py-0 w-full min-w-0 flex-[2] border-2 border-black/10 dark:border-white/10 focus:border-[#8a3ffc]/50 bg-white/5 dark:bg-white/5 rounded-2xl font-bold transition-all shadow-inner"
                                        />
                                        <button onClick={handleEnableTOTP} className="btn-gradient px-8 shrink-0 h-14 !text-sm font-bold shadow-lg flex-1" disabled={totpLoading}>
                                            {totpLoading ? <Spinner className="animate-spin" /> : t("verify")}
                                        </button>
                                    </div>
                                </div>
                            </div>
                        )}

                        {totpEnabled && (
                            <button onClick={handleDisableTOTP} className="btn-secondary !text-rose-400 hover:bg-rose-500/10 w-fit px-6 !py-2.5 !text-xs" disabled={totpLoading}>
                                {totpLoading ? <Spinner className="animate-spin" /> : t("disable_2fa")}
                            </button>
                        )}
                    </div>

                    {/* AI 配置 */}
                    <div className="glass-panel p-4">
                        <div className="flex justify-between items-center mb-4">
                            <div className="flex items-center gap-3">
                                <div className="p-2 bg-indigo-500/10 rounded-xl text-indigo-400">
                                    <BotIcon weight="bold" size={18} />
                                </div>
                                <h2 className="text-lg font-bold">{t("ai_config")}</h2>
                            </div>
                            {aiConfig && (
                                <button onClick={handleDeleteAI} className="action-btn !w-8 !h-8 !text-rose-400" title={t("delete_ai_config")}>
                                    <Trash weight="bold" size={16} />
                                </button>
                            )}
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                            <div className="md:col-span-2">
                                <label className="text-[11px] mb-1">{t("api_key")}</label>
                                <input
                                    type="password"
                                    className="!py-2 !px-4"
                                    value={aiForm.api_key}
                                    onChange={(e) => setAIForm({ ...aiForm, api_key: e.target.value })}
                                    placeholder={t("api_key")}
                                />
                            </div>
                            <div>
                                <label className="text-[11px] mb-1">{t("base_url")}</label>
                                <input
                                    className="!py-2 !px-4"
                                    value={aiForm.base_url}
                                    onChange={(e) => setAIForm({ ...aiForm, base_url: e.target.value })}
                                    placeholder={t("ai_base_url_placeholder")}
                                />
                            </div>
                            <div>
                                <label className="text-[11px] mb-1">{t("model")}</label>
                                <input
                                    className="!py-2 !px-4"
                                    value={aiForm.model}
                                    onChange={(e) => setAIForm({ ...aiForm, model: e.target.value })}
                                />
                            </div>
                        </div>

                        <div className="flex gap-3">
                            <button onClick={handleSaveAI} className="btn-gradient w-fit px-5 !py-2 !text-[11px]" disabled={configLoading}>
                                {configLoading ? <Spinner className="animate-spin" /> : t("save")}
                            </button>
                            <button onClick={handleTestAI} className="btn-secondary w-fit px-5 !py-2 !text-[11px]" disabled={aiTesting || configLoading}>
                                {aiTesting ? <Spinner className="animate-spin" /> : t("test_connection")}
                            </button>
                        </div>

                        {aiTestResult && (
                            <div className={`mt-4 p-3 rounded-xl text-[11px] border ${aiTestStatus === "success" ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20' : 'bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/20'} animate-float-up`}>
                                <div className="flex items-center gap-2 font-bold mb-0.5 uppercase tracking-wider text-[9px]">
                                    {aiTestStatus === "success" ? t("process_successful") : t("process_error")}
                                </div>
                                {aiTestResult}
                            </div>
                        )}
                    </div>

                    {/* 全局设置 */}
                    <div className="glass-panel p-4">
                        <div className="flex items-center gap-3 mb-4">
                            <div className="p-2 bg-violet-500/10 rounded-xl text-violet-400">
                                <Gear weight="bold" size={18} />
                            </div>
                            <h2 className="text-lg font-bold">{t("global_settings")}</h2>
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                            <div>
                                <label className="text-[11px] mb-1">{t("sign_interval")}</label>
                                <input
                                    type="number"
                                    className="!py-2 !px-4"
                                    value={globalSettings.sign_interval === null ? "" : globalSettings.sign_interval}
                                    onChange={(e) => setGlobalSettings({ ...globalSettings, sign_interval: e.target.value ? parseInt(e.target.value) : null })}
                                    placeholder={t("sign_interval_placeholder")}
                                />
                                <p className="mt-1 text-[9px] text-[#9496a1]">{t("sign_interval_desc")}</p>
                            </div>
                            <div>
                                <label className="text-[11px] mb-1">{t("log_retention")}</label>
                                <input
                                    type="number"
                                    className="!py-2 !px-4"
                                    value={globalSettings.log_retention_days}
                                    onChange={(e) => setGlobalSettings({ ...globalSettings, log_retention_days: parseInt(e.target.value) || 0 })}
                                />
                            </div>
                        </div>
                        <button className="btn-gradient w-fit px-5 !py-2 !text-[11px]" onClick={handleSaveGlobal} disabled={configLoading}>
                            {configLoading ? <Spinner className="animate-spin" /> : t("save_global_params")}
                        </button>
                    </div>

                    {/* Telegram API 配置 */}
                    <div className="glass-panel p-4">
                        <div className="flex justify-between items-center mb-4">
                            <div className="flex items-center gap-3">
                                <div className="p-2 bg-sky-500/10 rounded-xl text-sky-400">
                                    <Cpu weight="bold" size={18} />
                                </div>
                                <h2 className="text-lg font-bold">{t("tg_api_config")}</h2>
                            </div>
                            <button onClick={handleResetTelegram} className="action-btn !w-8 !h-8" title={t("restore_default")} disabled={telegramLoading}>
                                {telegramLoading ? <Spinner className="animate-spin" size={14} /> : <ArrowUDownLeft weight="bold" size={16} />}
                            </button>
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                            <div>
                                <label className="text-[11px] mb-1">{t("api_id")}</label>
                                <input
                                    className="!py-2 !px-4"
                                    value={telegramForm.api_id}
                                    onChange={(e) => setTelegramForm({ ...telegramForm, api_id: e.target.value })}
                                    placeholder={t("tg_api_id_placeholder")}
                                />
                            </div>
                            <div>
                                <label className="text-[11px] mb-1">{t("api_hash")}</label>
                                <input
                                    className="!py-2 !px-4"
                                    value={telegramForm.api_hash}
                                    onChange={(e) => setTelegramForm({ ...telegramForm, api_hash: e.target.value })}
                                    placeholder={t("tg_api_hash_placeholder")}
                                />
                            </div>
                        </div>
                        <button className="btn-gradient w-fit px-5 !py-2 !text-[11px]" onClick={handleSaveTelegram} disabled={telegramLoading}>
                            {telegramLoading ? <Spinner className="animate-spin" /> : t("apply_api_config")}
                        </button>
                        <div className="mt-4 p-3.5 rounded-xl bg-amber-500/10 dark:bg-amber-500/10 border border-amber-500/30 dark:border-amber-500/20 text-[10px] text-amber-700 dark:text-amber-200/60 leading-relaxed shadow-sm font-medium">
                            <div className="flex items-center gap-2 mb-1.5">
                                <Terminal weight="bold" className="text-amber-600 dark:text-amber-400" size={12} />
                                <span className="font-bold uppercase tracking-wider text-amber-600 dark:text-amber-400">{t("warning_notice")}</span>
                            </div>
                            {t("tg_config_warning")}
                        </div>
                    </div>

                    {/* 配置导出导入 */}
                    <div className="glass-panel p-4">
                        <div className="flex items-center gap-3 mb-4">
                            <div className="p-2 bg-pink-500/10 rounded-xl text-pink-400">
                                <DownloadSimple weight="bold" size={18} />
                            </div>
                            <h2 className="text-lg font-bold">{t("backup_migration")}</h2>
                        </div>

                        <div className="flex flex-col md:flex-row gap-6">
                            <div className="flex-1">
                                <label className="mb-2 text-[11px]">{t("export_config")}</label>
                                <p className="text-[10px] text-[#9496a1] mb-3 leading-relaxed">{t("export_desc")}</p>
                                <button onClick={handleExport} className="btn-secondary w-full flex items-center justify-center gap-2 h-9 !text-[11px]" disabled={configLoading}>
                                    {configLoading ? <Spinner className="animate-spin" /> : <FloppyDisk weight="bold" />}
                                    {t("download_json")}
                                </button>
                            </div>

                            <div className="w-px bg-white/5 self-stretch hidden md:block"></div>

                            <div className="flex-1 flex flex-col">
                                <div className="flex justify-between items-center mb-2">
                                    <label className="text-[11px]">{t("import_config")}</label>
                                    <label className="text-[10px] text-[#8a3ffc] dark:text-[#b57dff] cursor-pointer hover:underline font-bold">
                                        {t("upload_json")}
                                        <input
                                            type="file"
                                            accept=".json"
                                            className="hidden"
                                            onChange={(e) => {
                                                const file = e.target.files?.[0];
                                                if (file) {
                                                    const reader = new FileReader();
                                                    reader.onload = (ev) => {
                                                        const content = ev.target?.result as string;
                                                        setImportConfig(content);
                                                    };
                                                    reader.readAsText(file);
                                                }
                                            }}
                                        />
                                    </label>
                                </div>
                                <textarea
                                    className="w-full flex-1 min-h-[80px] bg-white/2 rounded-xl p-3 text-[10px] font-mono text-main/60 border border-white/5 focus:border-[#8a3ffc]/30 outline-none transition-all placeholder:text-main/20 custom-scrollbar"
                                    placeholder={t("paste_json")}
                                    value={importConfig}
                                    onChange={(e) => setImportConfig(e.target.value)}
                                ></textarea>

                                <div className="flex items-center gap-3 mt-3 mb-4 group cursor-pointer" onClick={() => setOverwriteConfig(!overwriteConfig)}>
                                    <div
                                        className={`w-12 h-7 rounded-full relative transition-all shadow-sm border-2 ${overwriteConfig ? 'bg-[#8a3ffc] border-[#8a3ffc]' : 'bg-black/20 dark:bg-white/10 border-black/10 dark:border-white/30'}`}
                                    >
                                        <div className={`absolute top-0.5 w-5 h-5 rounded-full bg-white transition-all shadow-md ${overwriteConfig ? 'left-6' : 'left-0.5'}`}></div>
                                    </div>
                                    <span className={`text-[13px] cursor-pointer select-none transition-colors ${overwriteConfig ? 'text-main font-bold' : 'text-main/40'}`}>
                                        {t("overwrite_conflict")}
                                    </span>
                                </div>

                                <button onClick={handleImport} className="btn-gradient w-full h-10 !text-xs" disabled={configLoading}>
                                    {configLoading ? <Spinner className="animate-spin" /> : t("execute_import")}
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            </main>

            <ToastContainer toasts={toasts} removeToast={removeToast} />
        </div>
    );
}

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
import { Button } from "../../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../../components/ui/card";
import { Input } from "../../../components/ui/input";
import { Label } from "../../../components/ui/label";
import { ToastContainer, useToast } from "../../../components/ui/toast";
import { ThemeLanguageToggle } from "../../../components/ThemeLanguageToggle";
import { useLanguage } from "../../../context/LanguageContext";

export default function SettingsPage() {
    const router = useRouter();
    const { t } = useLanguage();
    const { toasts, addToast, removeToast } = useToast();
    const [token, setLocalToken] = useState<string | null>(null);
    const [loading, setLoading] = useState(false);

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

    useEffect(() => {
        const t = getToken();
        if (!t) {
            window.location.replace("/");
            return;
        }
        setLocalToken(t);
        setChecking(false);
        loadTOTPStatus(t);
        loadAIConfig(t);
        loadGlobalSettings(t);
        loadTelegramConfig(t);
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
                    api_key: config.api_key || "",
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
            addToast("请填写完整信息", "error");
            return;
        }
        try {
            setLoading(true);
            const res = await changeUsername(token, usernameForm.newUsername, usernameForm.password);
            addToast("用户名修改成功", "success");
            if (res.access_token) {
                localStorage.setItem("tg-signer-token", res.access_token);
                setLocalToken(res.access_token);
            }
            setUsernameForm({ newUsername: "", password: "" });
        } catch (err: any) {
            addToast(err.message || "修改失败", "error");
        } finally {
            setLoading(false);
        }
    };

    const handleChangePassword = async () => {
        if (!token) return;
        if (!passwordForm.oldPassword || !passwordForm.newPassword) {
            addToast("请填写完整信息", "error");
            return;
        }
        if (passwordForm.newPassword !== passwordForm.confirmPassword) {
            addToast("两次输入的密码不一致", "error");
            return;
        }
        try {
            setLoading(true);
            await changePassword(token, passwordForm.oldPassword, passwordForm.newPassword);
            addToast("密码修改成功", "success");
            setPasswordForm({ oldPassword: "", newPassword: "", confirmPassword: "" });
        } catch (err: any) {
            addToast(err.message || "修改失败", "error");
        } finally {
            setLoading(false);
        }
    };

    const handleSetupTOTP = async () => {
        if (!token) return;
        try {
            setLoading(true);
            const res = await setupTOTP(token);
            setTotpSecret(res.secret);
            setShowTotpSetup(true);
        } catch (err: any) {
            addToast(err.message || "准备失败", "error");
        } finally {
            setLoading(false);
        }
    };

    const handleEnableTOTP = async () => {
        if (!token) return;
        if (!totpCode) {
            addToast("请输入验证码", "error");
            return;
        }
        try {
            setLoading(true);
            await enableTOTP(token, totpCode);
            addToast("两步验证已启用", "success");
            setTotpEnabled(true);
            setShowTotpSetup(false);
            setTotpCode("");
        } catch (err: any) {
            addToast(err.message || "启用失败", "error");
        } finally {
            setLoading(false);
        }
    };

    const handleDisableTOTP = async () => {
        if (!token) return;
        const code = prompt("请输入两步验证码以停用：");
        if (!code) return;
        try {
            setLoading(true);
            await disableTOTP(token, code);
            addToast("两步验证已停用", "success");
            setTotpEnabled(false);
        } catch (err: any) {
            addToast(err.message || "停用失败", "error");
        } finally {
            setLoading(false);
        }
    };

    const handleExport = async () => {
        if (!token) return;
        try {
            setLoading(true);
            const config = await exportAllConfigs(token);
            const blob = new Blob([config], { type: "application/json" });
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = "tg-signer-config.json";
            a.click();
            addToast("配置导出成功", "success");
        } catch (err: any) {
            addToast(err.message || "导出失败", "error");
        } finally {
            setLoading(false);
        }
    };

    const handleImport = async () => {
        if (!token) return;
        if (!importConfig) {
            addToast("请粘贴配置内容", "error");
            return;
        }
        try {
            setLoading(true);
            await importAllConfigs(token, importConfig, overwriteConfig);
            addToast("配置导入成功", "success");
            setImportConfig("");
            loadAIConfig(token);
            loadGlobalSettings(token);
            loadTelegramConfig(token);
        } catch (err: any) {
            addToast(err.message || "导入失败", "error");
        } finally {
            setLoading(false);
        }
    };

    const handleSaveAI = async () => {
        if (!token) return;
        try {
            setLoading(true);
            await saveAIConfig(token, aiForm);
            addToast("AI 配置保存成功", "success");
            loadAIConfig(token);
        } catch (err: any) {
            addToast(err.message || "保存失败", "error");
        } finally {
            setLoading(false);
        }
    };

    const handleTestAI = async () => {
        if (!token) return;
        try {
            setAITesting(true);
            setAITestResult(null);
            const res = await testAIConnection(token);
            if (res.success) {
                setAITestResult("连接成功: " + res.message);
            } else {
                setAITestResult("连接失败: " + res.message);
            }
        } catch (err: any) {
            setAITestResult("测试出错: " + err.message);
        } finally {
            setAITesting(false);
        }
    };

    const handleDeleteAI = async () => {
        if (!token) return;
        if (!confirm("确定要删除 AI 配置吗？")) return;
        try {
            setLoading(true);
            await deleteAIConfig(token);
            addToast("AI 配置已删除", "success");
            setAIConfigState(null);
            setAIForm({ api_key: "", base_url: "", model: "gpt-4o" });
        } catch (err: any) {
            addToast(err.message || "删除失败", "error");
        } finally {
            setLoading(false);
        }
    };

    const handleSaveGlobal = async () => {
        if (!token) return;
        try {
            setLoading(true);
            await saveGlobalSettings(token, globalSettings);
            addToast("全局设置保存成功", "success");
        } catch (err: any) {
            addToast(err.message || "保存失败", "error");
        } finally {
            setLoading(false);
        }
    };

    const handleSaveTelegram = async () => {
        if (!token) return;
        if (!telegramForm.api_id || !telegramForm.api_hash) {
            addToast("请填写完整信息", "error");
            return;
        }
        try {
            setLoading(true);
            await saveTelegramConfig(token, {
                api_id: parseInt(telegramForm.api_id),
                api_hash: telegramForm.api_hash,
            });
            addToast("Telegram 配置保存成功", "success");
            loadTelegramConfig(token);
        } catch (err: any) {
            addToast(err.message || "保存失败", "error");
        } finally {
            setLoading(false);
        }
    };

    const handleResetTelegram = async () => {
        if (!token) return;
        if (!confirm("确定要重置 Telegram 配置为默认值吗？")) return;
        try {
            setLoading(true);
            await resetTelegramConfig(token);
            addToast("配置已重置", "success");
            loadTelegramConfig(token);
        } catch (err: any) {
            addToast(err.message || "操作失败", "error");
        } finally {
            setLoading(false);
        }
    };

    if (!token || checking) {
        return null;
    }

    return (
        <div className="min-h-screen">
            <nav className="glass border-b border-white/10 sticky top-0 z-50">
                <div className="max-w-7xl mx-auto px-6 py-4">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                            <Link
                                href="/dashboard"
                                className="p-2.5 hover:bg-white/10 rounded-xl transition-all text-white/70 hover:text-white"
                                title={t("cancel")}
                            >
                                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                                </svg>
                            </Link>
                            <div className="flex items-center gap-2 text-sm">
                                <Link href="/dashboard" className="text-white/50 hover:text-white transition-colors">
                                    {t("sidebar_home")}
                                </Link>
                                <span className="text-white/30">/</span>
                                <span className="text-white font-medium">{t("sidebar_settings")}</span>
                            </div>
                        </div>
                        <div className="flex items-center gap-2">
                            <ThemeLanguageToggle />
                        </div>
                    </div>
                </div>
            </nav>

            <div className="max-w-4xl mx-auto px-6 py-8 relative z-0">
                <header className="mb-10">
                    <h1 className="text-3xl font-bold text-white mb-2">{t("settings_title")}</h1>
                    <p className="text-white/50">管理您的账户安全、AI 配置及系统偏好设置</p>
                </header>

                <div className="grid gap-8 pb-20">
                    {/* 用户名修改 */}
                    <Card className="card-hover">
                        <CardHeader>
                            <CardTitle className="text-xl flex items-center gap-2">
                                <span className="p-2 bg-blue-500/10 rounded-lg text-blue-400">👤</span>
                                {t("username")}
                            </CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-4">
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                <div className="space-y-2">
                                    <Label>新用户名</Label>
                                    <Input
                                        value={usernameForm.newUsername}
                                        onChange={(e) => setUsernameForm({ ...usernameForm, newUsername: e.target.value })}
                                        className="glass-input"
                                        placeholder="输入新用户名"
                                    />
                                </div>
                                <div className="space-y-2">
                                    <Label>当前密码</Label>
                                    <Input
                                        type="password"
                                        value={usernameForm.password}
                                        onChange={(e) => setUsernameForm({ ...usernameForm, password: e.target.value })}
                                        className="glass-input"
                                        placeholder="验证当前密码"
                                    />
                                </div>
                            </div>
                            <Button onClick={handleChangeUsername} className="btn-primary" disabled={loading}>
                                {loading ? "处理中..." : "修改用户名"}
                            </Button>
                        </CardContent>
                    </Card>

                    {/* 密码修改 */}
                    <Card className="card-hover">
                        <CardHeader>
                            <CardTitle className="text-xl flex items-center gap-2">
                                <span className="p-2 bg-amber-500/10 rounded-lg text-amber-400">🔒</span>
                                修改密码
                            </CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-4">
                            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                                <div className="space-y-2">
                                    <Label>旧密码</Label>
                                    <Input
                                        type="password"
                                        value={passwordForm.oldPassword}
                                        onChange={(e) => setPasswordForm({ ...passwordForm, oldPassword: e.target.value })}
                                        className="glass-input"
                                    />
                                </div>
                                <div className="space-y-2">
                                    <Label>新密码</Label>
                                    <Input
                                        type="password"
                                        value={passwordForm.newPassword}
                                        onChange={(e) => setPasswordForm({ ...passwordForm, newPassword: e.target.value })}
                                        className="glass-input"
                                    />
                                </div>
                                <div className="space-y-2">
                                    <Label>确认新密码</Label>
                                    <Input
                                        type="password"
                                        value={passwordForm.confirmPassword}
                                        onChange={(e) => setPasswordForm({ ...passwordForm, confirmPassword: e.target.value })}
                                        className="glass-input"
                                    />
                                </div>
                            </div>
                            <Button onClick={handleChangePassword} className="btn-primary" disabled={loading}>
                                {loading ? "处理中..." : "修改密码"}
                            </Button>
                        </CardContent>
                    </Card>

                    {/* 2FA 设置 */}
                    <Card className="card-hover overflow-hidden">
                        <CardHeader>
                            <div className="flex justify-between items-center">
                                <CardTitle className="text-xl flex items-center gap-2">
                                    <span className="p-2 bg-emerald-500/10 rounded-lg text-emerald-400">🛡️</span>
                                    两步验证 (2FA)
                                </CardTitle>
                                <div className={`px-3 py-1 rounded-full text-xs font-medium ${totpEnabled ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' : 'bg-rose-500/10 text-rose-400 border border-rose-500/20'}`}>
                                    {totpEnabled ? "已启用" : "未启用"}
                                </div>
                            </div>
                        </CardHeader>
                        <CardContent className="space-y-6">
                            {!totpEnabled && !showTotpSetup && (
                                <div className="bg-emerald-500/5 border border-emerald-500/10 rounded-xl p-4 flex gap-4 items-start">
                                    <div className="p-2 bg-emerald-500/10 rounded-lg text-emerald-400 text-xl">💡</div>
                                    <div>
                                        <p className="text-sm text-white/70 leading-relaxed">
                                            启用两步验证将显著提升您的账户安全性。启用后，登录时除了密码外，还需要输入由身份验证器生成的动态代码。
                                        </p>
                                        <Button onClick={handleSetupTOTP} variant="outline" className="mt-4" disabled={loading}>
                                            开始设置
                                        </Button>
                                    </div>
                                </div>
                            )}

                            {showTotpSetup && (
                                <div className="space-y-6 animate-scale-in">
                                    <div className="flex flex-col md:flex-row gap-8 items-center md:items-start p-6 bg-white/5 rounded-2xl border border-white/5">
                                        <div className="bg-white p-4 rounded-xl">
                                            <img
                                                src={`/api/user/totp/qrcode?secret=${totpSecret}`}
                                                alt="QR Code"
                                                className="w-40 h-40"
                                            />
                                        </div>
                                        <div className="flex-1 space-y-4">
                                            <div>
                                                <h4 className="font-bold text-white mb-2">1. 扫描二维码</h4>
                                                <p className="text-sm text-white/50">使用 Google Authenticator 或其他身份验证器扫描左侧二维码</p>
                                            </div>
                                            <div>
                                                <h4 className="font-bold text-white mb-2">2. 备份密钥</h4>
                                                <div className="p-3 bg-white/5 border border-white/10 rounded-xl text-sm break-all font-mono text-cyan-300">
                                                    {totpSecret}
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                    <div className="space-y-2 max-w-xs">
                                        <Label>验证代码</Label>
                                        <div className="flex gap-2">
                                            <Input
                                                value={totpCode}
                                                onChange={(e) => setTotpCode(e.target.value)}
                                                placeholder="6 位数字代码"
                                                className="glass-input text-center text-lg tracking-widest"
                                            />
                                            <Button onClick={handleEnableTOTP} className="btn-primary" disabled={loading}>
                                                验证并启用
                                            </Button>
                                        </div>
                                    </div>
                                </div>
                            )}

                            {totpEnabled && (
                                <Button onClick={handleDisableTOTP} variant="destructive" disabled={loading}>
                                    停用两步验证
                                </Button>
                            )}
                        </CardContent>
                    </Card>

                    {/* AI 配置 */}
                    <Card className="card-hover">
                        <CardHeader>
                            <div className="flex justify-between items-center">
                                <CardTitle className="text-xl flex items-center gap-2">
                                    <span className="p-2 bg-indigo-500/10 rounded-lg text-indigo-400">🤖</span>
                                    AI 模型配置 (用于自动答题)
                                </CardTitle>
                                {aiConfig && (
                                    <Button variant="ghost" size="sm" onClick={handleDeleteAI} className="text-rose-400 hover:text-rose-300 hover:bg-rose-500/10">
                                        删除配置
                                    </Button>
                                )}
                            </div>
                        </CardHeader>
                        <CardContent className="space-y-5">
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                <div className="space-y-2">
                                    <Label>API 密钥</Label>
                                    <Input
                                        type="password"
                                        value={aiForm.api_key}
                                        onChange={(e) => setAIForm({ ...aiForm, api_key: e.target.value })}
                                        className="glass-input"
                                        placeholder={aiConfig ? "******** (已保存)" : "sk-..."}
                                    />
                                </div>
                                <div className="space-y-2">
                                    <Label>基础 URL (Base URL)</Label>
                                    <Input
                                        value={aiForm.base_url}
                                        onChange={(e) => setAIForm({ ...aiForm, base_url: e.target.value })}
                                        className="glass-input"
                                        placeholder="https://api.openai.com/v1"
                                    />
                                </div>
                                <div className="space-y-2">
                                    <Label>预设模型 (Model)</Label>
                                    <Input
                                        value={aiForm.model}
                                        onChange={(e) => setAIForm({ ...aiForm, model: e.target.value })}
                                        className="glass-input"
                                    />
                                </div>
                            </div>

                            <div className="flex gap-3 pt-2">
                                <Button onClick={handleSaveAI} className="btn-primary" disabled={loading}>
                                    {loading ? "保存中..." : "保存 AI 配置"}
                                </Button>
                                <Button onClick={handleTestAI} variant="outline" disabled={aiTesting || !aiConfig}>
                                    {aiTesting ? "测试中..." : "连接测试"}
                                </Button>
                            </div>

                            {aiTestResult && (
                                <div className={`p-4 rounded-xl text-sm ${aiTestResult.includes("成功") ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' : 'bg-rose-500/10 text-rose-400 border border-rose-500/20'}`}>
                                    {aiTestResult}
                                </div>
                            )}
                        </CardContent>
                    </Card>

                    {/* 全局设置 */}
                    <Card className="card-hover">
                        <CardHeader>
                            <CardTitle className="text-xl flex items-center gap-2">
                                <span className="p-2 bg-violet-500/10 rounded-lg text-violet-400">⚙️</span>
                                全局设置
                            </CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-5">
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                <div className="space-y-2">
                                    <Label>签到间隔 (cron 表达式，可选)</Label>
                                    <Input
                                        value={globalSettings.sign_interval || ""}
                                        onChange={(e) => setGlobalSettings({ ...globalSettings, sign_interval: e.target.value || null })}
                                        className="glass-input"
                                        placeholder="例如: 0 9 * * *"
                                    />
                                    <p className="text-[10px] text-white/30">设置将应用于所有启用全局间隔的任务</p>
                                </div>
                                <div className="space-y-2">
                                    <Label>日志保留天数</Label>
                                    <Input
                                        type="number"
                                        value={globalSettings.log_retention_days}
                                        onChange={(e) => setGlobalSettings({ ...globalSettings, log_retention_days: parseInt(e.target.value) || 0 })}
                                        className="glass-input"
                                    />
                                </div>
                            </div>
                            <Button onClick={handleSaveGlobal} className="btn-primary" disabled={loading}>
                                {loading ? "保存中..." : "保存全局设置"}
                            </Button>
                        </CardContent>
                    </Card>

                    {/* Telegram API 配置 */}
                    <Card className="card-hover">
                        <CardHeader>
                            <CardTitle className="text-xl flex items-center gap-2">
                                <span className="p-2 bg-sky-500/10 rounded-lg text-sky-400">💻</span>
                                Telegram API 凭据
                            </CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-5">
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                <div className="space-y-2">
                                    <Label>API ID</Label>
                                    <Input
                                        value={telegramForm.api_id}
                                        onChange={(e) => setTelegramForm({ ...telegramForm, api_id: e.target.value })}
                                        className="glass-input"
                                        placeholder="从 my.telegram.org 获取"
                                    />
                                </div>
                                <div className="space-y-2">
                                    <Label>API Hash</Label>
                                    <Input
                                        value={telegramForm.api_hash}
                                        onChange={(e) => setTelegramForm({ ...telegramForm, api_hash: e.target.value })}
                                        className="glass-input"
                                        placeholder="从 my.telegram.org 获取"
                                    />
                                </div>
                            </div>
                            <div className="flex gap-3">
                                <Button onClick={handleSaveTelegram} className="btn-primary" disabled={loading}>
                                    {loading ? "保存中..." : "保存 API 配置"}
                                </Button>
                                <Button onClick={handleResetTelegram} variant="outline" disabled={loading}>
                                    恢复默认
                                </Button>
                            </div>
                            <p className="text-[10px] text-white/30">
                                注意：修改此配置可能导致现有登录会话失效，建议在添加账号出现问题时才自定义。
                            </p>
                        </CardContent>
                    </Card>

                    {/* 配置导出导入 */}
                    <Card className="card-hover">
                        <CardHeader>
                            <CardTitle className="text-xl flex items-center gap-2">
                                <span className="p-2 bg-pink-500/10 rounded-lg text-pink-400">💾</span>
                                数据备份与迁移
                            </CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-6">
                            <div className="flex flex-col md:flex-row gap-4">
                                <div className="flex-1 space-y-4">
                                    <Label>导出全部配置 (导出包含任务与账号基础信息的 JSON)</Label>
                                    <Button onClick={handleExport} variant="outline" className="w-full flex items-center gap-2" disabled={loading}>
                                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a2 2 0 002 2h12a2 2 0 002-2v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                                        </svg>
                                        下载备份文件
                                    </Button>
                                </div>
                                <div className="flex-1 space-y-2">
                                    <Label>导入配置内容</Label>
                                    <textarea
                                        className="w-full h-24 glass rounded-xl p-3 text-sm font-mono text-white/70 border border-white/10 focus:border-white/20 outline-none transition-all placeholder:text-white/20"
                                        placeholder="在此粘贴导出的 JSON 文本..."
                                        value={importConfig}
                                        onChange={(e) => setImportConfig(e.target.value)}
                                    ></textarea>
                                    <div className="flex items-center gap-2">
                                        <input
                                            type="checkbox"
                                            id="overwrite"
                                            checked={overwriteConfig}
                                            onChange={(e) => setOverwriteConfig(e.target.checked)}
                                            className="rounded border-white/10 bg-white/5"
                                        />
                                        <Label htmlFor="overwrite" className="text-white/50 cursor-pointer">覆盖现有重复任务</Label>
                                    </div>
                                    <Button onClick={handleImport} className="w-full mt-2" disabled={loading}>
                                        执行导入
                                    </Button>
                                </div>
                            </div>
                        </CardContent>
                    </Card>
                </div>
            </div>

            <ToastContainer toasts={toasts} removeToast={removeToast} />
        </div>
    );
}

"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { getToken } from "../../lib/auth";
import {
  listAccounts,
  startAccountLogin,
  verifyAccountLogin,
  deleteAccount,
  getAccountLogs,
  listSignTasks,
  AccountInfo,
  AccountLog,
  SignTask,
} from "../../lib/api";
import {
  Lightning,
  Plus,
  Gear,
  ListDashes,
  Clock,
  Spinner,
  X,
  PaperPlaneRight,
  Trash
} from "@phosphor-icons/react";
import { ToastContainer, useToast } from "../../components/ui/toast";
import { ThemeLanguageToggle } from "../../components/ThemeLanguageToggle";
import { useLanguage } from "../../context/LanguageContext";

export default function Dashboard() {
  const router = useRouter();
  const { t, language } = useLanguage();
  const { toasts, addToast, removeToast } = useToast();
  const [token, setLocalToken] = useState<string | null>(null);
  const [accounts, setAccounts] = useState<AccountInfo[]>([]);
  const [tasks, setTasks] = useState<SignTask[]>([]);
  const [loading, setLoading] = useState(false);

  // 日志弹窗
  const [showLogsDialog, setShowLogsDialog] = useState(false);
  const [logsAccountName, setLogsAccountName] = useState("");
  const [accountLogs, setAccountLogs] = useState<AccountLog[]>([]);
  const [logsLoading, setLogsLoading] = useState(false);

  // 添加账号对话框
  const [showAddDialog, setShowAddDialog] = useState(false);
  const [loginData, setLoginData] = useState({
    account_name: "",
    phone_number: "",
    proxy: "",
    phone_code: "",
    password: "",
    phone_code_hash: "",
  });

  const [checking, setChecking] = useState(true);

  useEffect(() => {
    const tokenStr = getToken();
    if (!tokenStr) {
      window.location.replace("/");
      return;
    }
    setLocalToken(tokenStr);
    setChecking(false);
    loadData(tokenStr);
  }, []);

  const loadData = async (tokenStr: string) => {
    try {
      setLoading(true);
      const [accountsData, tasksData] = await Promise.all([
        listAccounts(tokenStr),
        listSignTasks(tokenStr),
      ]);
      setAccounts(accountsData.accounts);
      setTasks(tasksData);
    } catch (err: any) {
      addToast(err.message || t("login_failed"), "error");
    } finally {
      setLoading(false);
    }
  };

  const getAccountTaskCount = (accountName: string) => {
    return tasks.filter(task => task.account_name === accountName).length;
  };

  const handleStartLogin = async () => {
    if (!token) return;
    if (!loginData.account_name || !loginData.phone_number) {
      addToast(language === "zh" ? "请填写账号名称和手机号" : "Please fill in account name and phone number", "error");
      return;
    }
    try {
      setLoading(true);
      const res = await startAccountLogin(token, {
        phone_number: loginData.phone_number,
        account_name: loginData.account_name
      });
      setLoginData({ ...loginData, phone_code_hash: res.phone_code_hash });
      addToast(t("code_sent"), "success");
    } catch (err: any) {
      addToast(err.message || (language === "zh" ? "发送失败" : "Failed to send"), "error");
    } finally {
      setLoading(false);
    }
  };

  const handleVerifyLogin = async () => {
    if (!token) return;
    if (!loginData.phone_code) {
      addToast(language === "zh" ? "请输入验证码" : "Please enter code", "error");
      return;
    }
    try {
      setLoading(true);
      await verifyAccountLogin(token, {
        account_name: loginData.account_name,
        phone_number: loginData.phone_number,
        phone_code: loginData.phone_code,
        phone_code_hash: loginData.phone_code_hash,
        password: loginData.password || undefined,
        proxy: loginData.proxy || undefined,
      });
      addToast(t("login_success"), "success");
      setShowAddDialog(false);
      loadData(token);
    } catch (err: any) {
      addToast(err.message || (language === "zh" ? "验证失败" : "Verification failed"), "error");
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteAccount = async (name: string) => {
    if (!token) return;
    if (!confirm(language === "zh" ? `确定要删除账号 ${name} 吗？` : `Are you sure you want to delete ${name}?`)) return;
    try {
      setLoading(true);
      await deleteAccount(token, name);
      addToast(language === "zh" ? "账号已删除" : "Account deleted", "success");
      loadData(token);
    } catch (err: any) {
      addToast(err.message || (language === "zh" ? "删除失败" : "Failed to delete"), "error");
    } finally {
      setLoading(false);
    }
  };

  const handleShowLogs = async (name: string) => {
    if (!token) return;
    setLogsAccountName(name);
    setShowLogsDialog(true);
    setLogsLoading(true);
    try {
      const logs = await getAccountLogs(token, name);
      setAccountLogs(logs);
    } catch (err: any) {
      addToast(err.message || (language === "zh" ? "获取日志失败" : "Failed to get logs"), "error");
    } finally {
      setLogsLoading(false);
    }
  };

  if (!token || checking) {
    return null;
  }

  return (
    <div id="dashboard-view" className="w-full h-full flex flex-col">
      <nav className="navbar">
        <div className="nav-brand" style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <Lightning weight="fill" style={{ fontSize: '28px', color: '#fcd34d' }} />
          <span className="nav-title font-bold tracking-tight text-lg">TG SignPulse</span>
        </div>
        <div className="top-right-actions">
          <ThemeLanguageToggle />
          <div className="w-px h-4 bg-white/10 mx-1"></div>
          <Link href="/dashboard/settings" title={t("sidebar_settings")} className="action-btn">
            <Gear weight="bold" />
          </Link>
        </div>
      </nav>

      <main className="main-content">
        <header className="mb-8 overflow-hidden">
          <h1 className="text-2xl font-bold tracking-tight mb-1">{t("dashboard_title")}</h1>
          <p className="text-[#9496a1] text-xs">{t("dashboard_desc")}</p>
        </header>

        {loading && accounts.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-main/30">
            <Spinner className="animate-spin mb-4" size={32} />
            <p>{t("loading")}</p>
          </div>
        ) : (
          <div className="card-grid">
            {accounts.map((acc) => {
              const initial = acc.name.charAt(0).toUpperCase();
              return (
                <div
                  key={acc.name}
                  className="glass-panel card !h-44 group cursor-pointer"
                  onClick={() => router.push(`/dashboard/account-tasks?name=${acc.name}`)}
                >
                  <div className="card-top">
                    <div className="account-name">
                      <div className="account-avatar">{initial}</div>
                      <span className="font-bold">{acc.name}</span>
                    </div>
                    <div className="task-badge">
                      {getAccountTaskCount(acc.name)} {t("sidebar_tasks")}
                    </div>
                  </div>

                  <div className="flex-1"></div>

                  <div className="card-bottom !pt-3">
                    <div className="create-time">
                      <Clock weight="fill" className="text-emerald-400/50" />
                      <span className="text-[11px] font-medium">{t("connected")}</span>
                    </div>
                    <div className="card-actions">
                      <div
                        className="action-icon !w-8 !h-8"
                        title={t("logs")}
                        onClick={(e) => { e.stopPropagation(); handleShowLogs(acc.name); }}
                      >
                        <ListDashes weight="bold" size={16} />
                      </div>
                      <div
                        className="action-icon delete !w-8 !h-8"
                        title={t("remove")}
                        onClick={(e) => { e.stopPropagation(); handleDeleteAccount(acc.name); }}
                      >
                        <Trash weight="bold" size={16} />
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}

            {/* 添加新账号卡片 */}
            <div
              className="card card-add !h-44"
              onClick={() => { setShowAddDialog(true); }}
            >
              <div className="add-icon-circle !w-10 !h-10">
                <Plus weight="bold" size={20} />
              </div>
              <span className="text-xs font-bold" style={{ color: 'var(--text-sub)' }}>{t("add_account")}</span>
            </div>
          </div>
        )}
      </main>

      {showAddDialog && (
        <div className="modal-overlay active" onClick={() => setShowAddDialog(false)}>
          <div className="glass-panel modal-content !max-w-[420px] !p-6" onClick={e => e.stopPropagation()}>
            <div className="modal-header !mb-5">
              <div className="modal-title !text-lg">{t("add_account")}</div>
              <div className="modal-close" onClick={() => setShowAddDialog(false)}><X weight="bold" /></div>
            </div>

            <div className="animate-float-up space-y-4">
              <div>
                <label className="text-[11px] mb-1">{t("session_name")}</label>
                <input
                  type="text"
                  className="!py-2.5 !px-4 !mb-4"
                  placeholder="e.g. Work_Account_01"
                  value={loginData.account_name}
                  onChange={(e) => setLoginData({ ...loginData, account_name: e.target.value })}
                />

                <label className="text-[11px] mb-1">{t("phone_number")}</label>
                <input
                  type="text"
                  className="!py-2.5 !px-4 !mb-4"
                  placeholder="+86 138 0000 0000"
                  value={loginData.phone_number}
                  onChange={(e) => setLoginData({ ...loginData, phone_number: e.target.value })}
                />

                <label className="text-[11px] mb-1">{t("login_code")}</label>
                <div className="input-group !mb-4">
                  <input
                    type="text"
                    className="!py-2.5 !px-4"
                    placeholder={t("login_code_placeholder")}
                    value={loginData.phone_code}
                    onChange={(e) => setLoginData({ ...loginData, phone_code: e.target.value })}
                  />
                  <button className="btn-code !h-[42px] !w-[42px] !text-lg" onClick={handleStartLogin} disabled={loading} title={t("send_code")}>
                    {loading ? <Spinner className="animate-spin" size={16} /> : <PaperPlaneRight weight="bold" />}
                  </button>
                </div>

                <label className="text-[11px] mb-1">{t("two_step_pass")}</label>
                <input
                  type="password"
                  className="!py-2.5 !px-4 !mb-4"
                  placeholder={t("two_step_placeholder")}
                  value={loginData.password}
                  onChange={(e) => setLoginData({ ...loginData, password: e.target.value })}
                />

                <label className="text-[11px] mb-1">{t("proxy")}</label>
                <input
                  type="text"
                  className="!py-2.5 !px-4"
                  placeholder={t("proxy_placeholder")}
                  style={{ marginBottom: 0 }}
                  value={loginData.proxy}
                  onChange={(e) => setLoginData({ ...loginData, proxy: e.target.value })}
                />
              </div>

              <div className="flex gap-3 mt-6">
                <button className="btn-secondary flex-1 h-10 !py-0 !text-xs" onClick={() => setShowAddDialog(false)}>{t("cancel")}</button>
                <button className="btn-gradient flex-1 h-10 !py-0 !text-xs" onClick={handleVerifyLogin} disabled={loading}>
                  {loading ? <Spinner className="animate-spin" /> : t("confirm_connect")}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {showLogsDialog && (
        <div className="modal-overlay active" onClick={() => setShowLogsDialog(false)}>
          <div className="glass-panel modal-content !max-w-4xl max-h-[90vh] flex flex-col overflow-hidden !p-0" onClick={e => e.stopPropagation()}>
            <div className="p-5 border-b border-white/5 flex justify-between items-center bg-white/2">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-[#8a3ffc]/10 rounded-lg text-[#8a3ffc]">
                  <ListDashes weight="bold" size={18} />
                </div>
                <div className="font-bold text-lg">{logsAccountName} {t("running_logs")}</div>
              </div>
              <div className="modal-close" onClick={() => setShowLogsDialog(false)}><X weight="bold" /></div>
            </div>

            <div className="flex-1 overflow-y-auto p-5 font-mono text-[13px] bg-black/10 custom-scrollbar">
              {logsLoading ? (
                <div className="flex flex-col items-center justify-center py-20 text-main/30">
                  <Spinner className="animate-spin mb-4" size={32} />
                  {t("loading")}
                </div>
              ) : accountLogs.length === 0 ? (
                <div className="text-center py-20 text-main/20 font-sans">{t("no_logs")}</div>
              ) : (
                <div className="space-y-3">
                  {accountLogs.map((log, i) => (
                    <div key={i} className="p-4 rounded-xl bg-white/2 border border-white/5 group hover:border-white/10 transition-colors">
                      <div className="flex justify-between items-center mb-2.5 text-[10px] uppercase tracking-wider font-bold">
                        <span className="text-main/20 group-hover:text-main/40 transition-colors">{new Date(log.created_at).toLocaleString()}</span>
                        <span className={`px-2 py-0.5 rounded-md ${log.success ? 'bg-emerald-500/10 text-emerald-400' : 'bg-rose-500/10 text-rose-400'}`}>
                          {log.success ? t("success") : t("failure")}
                        </span>
                      </div>
                      <pre className="whitespace-pre-wrap text-main/60 leading-relaxed overflow-x-auto max-h-[150px] scrollbar-none font-medium">
                        {log.message}
                      </pre>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="p-4 border-t border-white/5 text-center bg-white/2">
              <button className="btn-secondary px-8 h-9 !py-0 mx-auto !text-xs" onClick={() => setShowLogsDialog(false)}>
                {t("close")}
              </button>
            </div>
          </div>
        </div>
      )}

      <ToastContainer toasts={toasts} removeToast={removeToast} />
    </div>
  );
}

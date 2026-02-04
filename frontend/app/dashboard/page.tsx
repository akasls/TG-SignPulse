"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { getToken } from "../../lib/auth";
import {
  listAccounts,
  startAccountLogin,
  startQrLogin,
  getQrLoginStatus,
  cancelQrLogin,
  updateAccount,
  verifyAccountLogin,
  deleteAccount,
  getAccountLogs,
  exportAccountLogs,
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
  PencilSimple,
  PaperPlaneRight,
  Trash,
  GithubLogo,
  DownloadSimple
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
  const [loginMode, setLoginMode] = useState<"phone" | "qr">("phone");
  const [qrLogin, setQrLogin] = useState<{
    login_id: string;
    qr_uri: string;
    qr_image?: string | null;
    expires_at: string;
  } | null>(null);
  type QrPhase = "idle" | "loading" | "ready" | "scanning" | "success" | "expired" | "error";
  const [qrStatus, setQrStatus] = useState<
    "waiting_scan" | "scanned_wait_confirm" | "success" | "expired" | "failed"
  >("waiting_scan");
  const [qrPhase, setQrPhase] = useState<QrPhase>("idle");
  const [qrMessage, setQrMessage] = useState<string>("");
  const [qrCountdown, setQrCountdown] = useState<number>(0);
  const [qrLoading, setQrLoading] = useState(false);

  const qrPollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const qrCountdownTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const qrActiveLoginIdRef = useRef<string | null>(null);
  const qrPollSeqRef = useRef(0);
  const qrPhaseRef = useRef<QrPhase>(qrPhase);
  const qrToastShownRef = useRef<Record<string, { expired?: boolean; error?: boolean }>>({});

  useEffect(() => {
    qrPhaseRef.current = qrPhase;
  }, [qrPhase]);

  // 编辑账号对话框
  const [showEditDialog, setShowEditDialog] = useState(false);
  const [editData, setEditData] = useState({
    account_name: "",
    remark: "",
    proxy: "",
  });

  const normalizeAccountName = (name: string) => name.trim();

  const sanitizeAccountName = (name: string) =>
    name.replace(/[^A-Za-z0-9\u4e00-\u9fff]/g, "");

  const isDuplicateAccountName = (name: string) => {
    const normalized = normalizeAccountName(name).toLowerCase();
    if (!normalized) return false;
    return accounts.some(acc => acc.name.toLowerCase() === normalized);
  };

  const [checking, setChecking] = useState(true);

  const addToastRef = useRef(addToast);
  const tRef = useRef(t);

  useEffect(() => {
    addToastRef.current = addToast;
  }, [addToast]);

  useEffect(() => {
    tRef.current = t;
  }, [t]);

  const loadData = useCallback(async (tokenStr: string) => {
    try {
      setLoading(true);
      const [accountsData, tasksData] = await Promise.all([
        listAccounts(tokenStr),
        listSignTasks(tokenStr),
      ]);
      setAccounts(accountsData.accounts);
      setTasks(tasksData);
    } catch (err: any) {
      addToastRef.current(err.message || tRef.current("login_failed"), "error");
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

  const getAccountTaskCount = (accountName: string) => {
    return tasks.filter(task => task.account_name === accountName).length;
  };

  const handleStartLogin = async () => {
    if (!token) return;
    const trimmedAccountName = normalizeAccountName(loginData.account_name);
    if (!trimmedAccountName || !loginData.phone_number) {
      addToast(language === "zh" ? "?????????????????" : "Please fill in account name and phone number", "error");
      return;
    }
    if (isDuplicateAccountName(trimmedAccountName)) {
      addToast(language === "zh" ? "???????????" : "Account name already exists. Please change it.", "error");
      return;
    }
    try {
      setLoading(true);
      const res = await startAccountLogin(token, {
        phone_number: loginData.phone_number,
        account_name: trimmedAccountName,
        proxy: loginData.proxy || undefined,
      });
      setLoginData({ ...loginData, account_name: trimmedAccountName, phone_code_hash: res.phone_code_hash });
      addToast(t("code_sent"), "success");
    } catch (err: any) {
      addToast(err.message || (language === "zh" ? "???????" : "Failed to send"), "error");
    } finally {
      setLoading(false);
    }
  };

  const handleVerifyLogin = async () => {
    if (!token) return;
    if (!loginData.phone_code) {
      addToast(language === "zh" ? "?????????" : "Please enter code", "error");
      return;
    }
    const trimmedAccountName = normalizeAccountName(loginData.account_name);
    if (!trimmedAccountName) {
      addToast(language === "zh" ? "???????" : "Please fill in account name", "error");
      return;
    }
    if (isDuplicateAccountName(trimmedAccountName)) {
      addToast(language === "zh" ? "???????????" : "Account name already exists. Please change it.", "error");
      return;
    }
    try {
      setLoading(true);
      await verifyAccountLogin(token, {
        account_name: trimmedAccountName,
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
      addToast(err.message || (language === "zh" ? "??????" : "Verification failed"), "error");
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

  const handleEditAccount = (acc: AccountInfo) => {
    setEditData({
      account_name: acc.name,
      remark: acc.remark || "",
      proxy: acc.proxy || "",
    });
    setShowEditDialog(true);
  };

  const handleSaveEdit = async () => {
    if (!token) return;
    if (!editData.account_name) return;
    try {
      setLoading(true);
      await updateAccount(token, editData.account_name, {
        remark: editData.remark || "",
        proxy: editData.proxy || "",
      });
      addToast(t("save_changes"), "success");
      setShowEditDialog(false);
      loadData(token);
    } catch (err: any) {
      addToast(err.message || (language === "zh" ? "保存失败" : "Save failed"), "error");
    } finally {
      setLoading(false);
    }
  };

  const debugQr = useCallback((payload: Record<string, any>) => {
    if (process.env.NODE_ENV !== "production") {
      // eslint-disable-next-line no-console
      console.debug("[qr-login]", payload);
    }
  }, []);

  const clearQrTimers = useCallback(() => {
    if (qrPollTimerRef.current) {
      clearInterval(qrPollTimerRef.current);
      qrPollTimerRef.current = null;
    }
    if (qrCountdownTimerRef.current) {
      clearInterval(qrCountdownTimerRef.current);
      qrCountdownTimerRef.current = null;
    }
  }, []);

  const setQrPhaseSafe = useCallback((next: QrPhase, reason: string, extra?: Record<string, any>) => {
    setQrPhase((prev) => {
      if (prev !== next) {
        debugQr({
          login_id: qrActiveLoginIdRef.current,
          prev,
          next,
          reason,
          ...extra,
        });
      }
      return next;
    });
  }, [debugQr]);

  const markToastShown = useCallback((loginId: string, kind: "expired" | "error") => {
    if (!loginId) return;
    if (!qrToastShownRef.current[loginId]) {
      qrToastShownRef.current[loginId] = {};
    }
    qrToastShownRef.current[loginId][kind] = true;
  }, []);

  const hasToastShown = useCallback((loginId: string, kind: "expired" | "error") => {
    if (!loginId) return false;
    return Boolean(qrToastShownRef.current[loginId]?.[kind]);
  }, []);

  const resetQrState = useCallback(() => {
    clearQrTimers();
    qrActiveLoginIdRef.current = null;
    setQrLogin(null);
    setQrStatus("waiting_scan");
    setQrPhase("idle");
    setQrMessage("");
    setQrCountdown(0);
    setQrLoading(false);
  }, [clearQrTimers]);

  const handleStartQrLogin = async () => {
    if (!token) return;
    const trimmedAccountName = normalizeAccountName(loginData.account_name);
    if (!trimmedAccountName) {
      addToast(language === "zh" ? "请输入账号名称" : "Please enter account name", "error");
      return;
    }
    if (isDuplicateAccountName(trimmedAccountName)) {
      addToast(language === "zh" ? "账号名已存在，请更换" : "Account name already exists. Please change it.", "error");
      return;
    }
    try {
      clearQrTimers();
      setQrLoading(true);
      setQrPhaseSafe("loading", "start");
      qrPollSeqRef.current += 1;
      const res = await startQrLogin(token, {
        account_name: trimmedAccountName,
        proxy: loginData.proxy || undefined,
      });
      setLoginData({ ...loginData, account_name: trimmedAccountName });
      setQrLogin(res);
      qrActiveLoginIdRef.current = res.login_id;
      qrToastShownRef.current[res.login_id] = {};
      setQrStatus("waiting_scan");
      setQrPhaseSafe("ready", "qr_ready", { expires_at: res.expires_at });
      setQrMessage("");
    } catch (err: any) {
      setQrPhaseSafe("error", "start_failed");
      addToast(err.message || (language === "zh" ? "生成二维码失败" : "Failed to create QR"), "error");
    } finally {
      setQrLoading(false);
    }
  };

  const handleCancelQrLogin = async () => {
    if (!token || !qrLogin?.login_id) {
      resetQrState();
      return;
    }
    try {
      setQrLoading(true);
      await cancelQrLogin(token, qrLogin.login_id);
    } catch (err: any) {
      addToast(err.message || (language === "zh" ? "取消失败" : "Cancel failed"), "error");
    } finally {
      setQrLoading(false);
      resetQrState();
    }
  };

  const handleCloseAddDialog = () => {
    if (qrLogin?.login_id) {
      handleCancelQrLogin();
    }
    setShowAddDialog(false);
  };

  const handleShowLogs = async (name: string) => {
    if (!token) return;
    setLogsAccountName(name);
    setShowLogsDialog(true);
    setLogsLoading(true);
    try {
      const logs = await getAccountLogs(token, name, 100);
      setAccountLogs(logs);
    } catch (err: any) {
      addToast(err.message || (language === "zh" ? "获取日志失败" : "Failed to get logs"), "error");
    } finally {
      setLogsLoading(false);
    }
  };

  const handleExportLogs = async () => {
    if (!token || !logsAccountName) return;
    try {
      setLoading(true);
      await exportAccountLogs(token, logsAccountName);
      addToast(language === "zh" ? "日志导出成功" : "Logs exported", "success");
    } catch (err: any) {
      addToast(err.message || "Export failed", "error");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!qrLogin?.expires_at || !qrActiveLoginIdRef.current) {
      setQrCountdown(0);
      clearQrTimers();
      return;
    }
    if (!(qrPhase === "ready" || qrPhase === "scanning")) {
      setQrCountdown(0);
      if (qrCountdownTimerRef.current) {
        clearInterval(qrCountdownTimerRef.current);
        qrCountdownTimerRef.current = null;
      }
      return;
    }
    const update = () => {
      const expires = new Date(qrLogin.expires_at).getTime();
      const diff = Math.max(0, Math.floor((expires - Date.now()) / 1000));
      setQrCountdown(diff);
    };
    update();
    if (qrCountdownTimerRef.current) {
      clearInterval(qrCountdownTimerRef.current);
    }
    qrCountdownTimerRef.current = setInterval(update, 1000);
    return () => {
      if (qrCountdownTimerRef.current) {
        clearInterval(qrCountdownTimerRef.current);
        qrCountdownTimerRef.current = null;
      }
    };
  }, [qrLogin?.expires_at, qrPhase, clearQrTimers]);

  useEffect(() => {
    if (!token || !qrLogin?.login_id || loginMode !== "qr" || !showAddDialog) return;
    if (!(qrPhase === "ready" || qrPhase === "scanning")) return;
    const loginId = qrLogin.login_id;
    qrActiveLoginIdRef.current = loginId;
    qrPollSeqRef.current += 1;
    const seq = qrPollSeqRef.current;
    let stopped = false;

    const stopPolling = () => {
      if (qrPollTimerRef.current) {
        clearInterval(qrPollTimerRef.current);
        qrPollTimerRef.current = null;
      }
    };

    const poll = async () => {
      try {
        const res = await getQrLoginStatus(token, loginId);
        if (stopped) return;
        if (qrActiveLoginIdRef.current !== loginId) return;
        if (qrPollSeqRef.current !== seq) return;

        const status = res.status as "waiting_scan" | "scanned_wait_confirm" | "success" | "expired" | "failed";
        if (status === "failed" && qrPhaseRef.current === "ready") {
          debugQr({ login_id: loginId, pollResult: status, ignored: true, reason: "failed_before_scan" });
          return;
        }
        debugQr({ login_id: loginId, pollResult: status, message: res.message || "" });
        setQrStatus(status);
        setQrMessage(res.message || "");
        if (res.expires_at) {
          setQrLogin((prev) => (prev ? { ...prev, expires_at: res.expires_at } : prev));
        }

        if (status === "success") {
          setQrPhaseSafe("success", "poll_success", { status });
          addToast(t("login_success"), "success");
          stopPolling();
          resetQrState();
          setShowAddDialog(false);
          loadData(token);
          return;
        }

        if (status === "scanned_wait_confirm") {
          setQrPhaseSafe("scanning", "poll_scanned", { status });
          return;
        }

        if (status === "waiting_scan") {
          setQrPhaseSafe("ready", "poll_waiting", { status });
          return;
        }

        if (status === "expired" && qrPhaseRef.current === "scanning") {
          debugQr({ login_id: loginId, status, ignored: true, reason: "scanning_ignore_expired" });
          return;
        }

        if (status === "expired" || status === "failed") {
          const nextPhase: QrPhase = status === "expired" ? "expired" : "error";
          setQrPhaseSafe(nextPhase, "poll_terminal", { status });
          stopPolling();
          if (!hasToastShown(loginId, "expired") && status === "expired") {
            addToast(res.message || (language === "zh" ? "二维码已过期或不存在" : "QR expired or not found"), "error");
            markToastShown(loginId, "expired");
          }
          if (!hasToastShown(loginId, "error") && status === "failed") {
            addToast(res.message || (language === "zh" ? "扫码登录失败" : "QR login failed"), "error");
            markToastShown(loginId, "error");
          }
        }
      } catch (err: any) {
        if (stopped) return;
        if (qrActiveLoginIdRef.current !== loginId) return;
        if (qrPollSeqRef.current !== seq) return;
        if (!hasToastShown(loginId, "error")) {
          addToast(err.message || (language === "zh" ? "获取扫码状态失败" : "Failed to get QR status"), "error");
          markToastShown(loginId, "error");
        }
        stopPolling();
        setQrPhaseSafe("error", "poll_error");
      }
    };

    poll();
    stopPolling();
    qrPollTimerRef.current = setInterval(poll, 1500);
    return () => {
      stopped = true;
      stopPolling();
    };
  }, [token, qrLogin?.login_id, loginMode, showAddDialog, qrPhase, addToast, language, loadData, resetQrState, t, hasToastShown, markToastShown, setQrPhaseSafe, debugQr]);

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
          <Link href="/dashboard/settings" title={t("sidebar_settings")} className="action-btn">
            <Gear weight="bold" />
          </Link>
        </div>
      </nav>

      <main className="main-content">
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
                      <div className="min-w-0">
                        <div className="font-bold leading-tight truncate">{acc.name}</div>
                        {acc.remark ? (
                          <div className="text-xs text-main/40 leading-tight truncate">
                            {acc.remark}
                          </div>
                        ) : null}
                      </div>
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
                        className="action-icon !w-8 !h-8"
                        title={t("edit_account")}
                        onClick={(e) => { e.stopPropagation(); handleEditAccount(acc); }}
                      >
                        <PencilSimple weight="bold" size={16} />
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
        <div className="modal-overlay active">
          <div className="glass-panel modal-content !max-w-[420px] !p-6" onClick={e => e.stopPropagation()}>
            <div className="modal-header !mb-5">
              <div className="modal-title !text-lg">{t("add_account")}</div>
              <div className="modal-close" onClick={handleCloseAddDialog}><X weight="bold" /></div>
            </div>

            <div className="animate-float-up space-y-4">
              <div className="flex gap-2">
                <button
                  className={`flex-1 h-9 text-xs font-bold rounded-lg ${loginMode === "phone" ? "btn-gradient" : "btn-secondary"}`}
                  onClick={() => {
                    if (loginMode !== "phone" && qrLogin?.login_id) {
                      handleCancelQrLogin();
                    }
                    setLoginMode("phone");
                  }}
                >
                  {t("login_method_phone")}
                </button>
                <button
                  className={`flex-1 h-9 text-xs font-bold rounded-lg ${loginMode === "qr" ? "btn-gradient" : "btn-secondary"}`}
                  onClick={() => setLoginMode("qr")}
                >
                  {t("login_method_qr")}
                </button>
              </div>

              {loginMode === "phone" ? (
                <>
                  <div>
                    <label className="text-[11px] mb-1">{t("session_name")}</label>
                    <input
                      type="text"
                      className="!py-2.5 !px-4 !mb-4"
                      placeholder="e.g. Work_Account_01"
                      value={loginData.account_name}
                      onChange={(e) => {
                        const cleaned = sanitizeAccountName(e.target.value);
                        setLoginData({ ...loginData, account_name: cleaned });
                      }}
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
                    <button className="btn-secondary flex-1 h-10 !py-0 !text-xs" onClick={handleCloseAddDialog}>{t("cancel")}</button>
                    <button className="btn-gradient flex-1 h-10 !py-0 !text-xs" onClick={handleVerifyLogin} disabled={loading}>
                      {loading ? <Spinner className="animate-spin" /> : t("confirm_connect")}
                    </button>
                  </div>
                </>
              ) : (
                <>
                  <div>
                    <label className="text-[11px] mb-1">{t("session_name")}</label>
                    <input
                      type="text"
                      className="!py-2.5 !px-4 !mb-4"
                      placeholder="e.g. Work_Account_01"
                      value={loginData.account_name}
                      onChange={(e) => {
                        const cleaned = sanitizeAccountName(e.target.value);
                        setLoginData({ ...loginData, account_name: cleaned });
                      }}
                    />

                    <label className="text-[11px] mb-1">{t("proxy")}</label>
                    <input
                      type="text"
                      className="!py-2.5 !px-4 !mb-4"
                      placeholder={t("proxy_placeholder")}
                      value={loginData.proxy}
                      onChange={(e) => setLoginData({ ...loginData, proxy: e.target.value })}
                    />
                  </div>

                  <div className="glass-panel !bg-black/5 p-4 rounded-xl space-y-3">
                    <div className="text-xs text-main/60">{t("qr_tip")}</div>
                    <div className="flex items-center justify-center">
                      {qrLogin?.qr_image ? (
                        <Image src={qrLogin.qr_image} alt="QR" width={160} height={160} className="rounded-lg bg-white p-2" />
                      ) : (
                        <div className="w-40 h-40 rounded-lg bg-white/5 flex items-center justify-center text-xs text-main/40">
                          {t("qr_start")}
                        </div>
                      )}
                    </div>
                    {qrLogin && (qrPhase === "ready" || qrPhase === "scanning") ? (
                      <div className="text-[11px] text-main/40 font-mono text-center">
                        {t("qr_expires_in").replace("{seconds}", qrCountdown.toString())}
                      </div>
                    ) : null}
                    <div className="text-xs text-center font-bold">
                      {(qrPhase === "loading" || qrPhase === "ready") && t("qr_waiting")}
                      {qrPhase === "scanning" && t("qr_scanned")}
                      {qrPhase === "success" && t("qr_success")}
                      {qrPhase === "expired" && t("qr_expired")}
                      {qrPhase === "error" && t("qr_failed")}
                    </div>
                    {qrMessage ? (
                      <div className="text-[11px] text-rose-400 text-center">{qrMessage}</div>
                    ) : null}
                  </div>

                  <div className="flex gap-3 mt-2">
                    <button className="btn-secondary flex-1 h-10 !py-0 !text-xs" onClick={handleCloseAddDialog}>{t("cancel")}</button>
                    <button
                      className="btn-gradient flex-1 h-10 !py-0 !text-xs"
                      onClick={handleStartQrLogin}
                      disabled={qrLoading}
                    >
                      {qrLoading ? <Spinner className="animate-spin" /> : (qrLogin ? t("qr_refresh") : t("qr_start"))}
                    </button>
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {showEditDialog && (
        <div className="modal-overlay active">
          <div className="glass-panel modal-content !max-w-[420px] !p-6" onClick={e => e.stopPropagation()}>
            <div className="modal-header !mb-5">
              <div className="modal-title !text-lg">{t("edit_account")}</div>
              <div className="modal-close" onClick={() => setShowEditDialog(false)}><X weight="bold" /></div>
            </div>

            <div className="animate-float-up space-y-4">
              <div>
                <label className="text-[11px] mb-1">{t("session_name")}</label>
                <input
                  type="text"
                  className="!py-2.5 !px-4 !mb-4"
                  value={editData.account_name}
                  disabled
                />

                <label className="text-[11px] mb-1">{t("remark")}</label>
                <input
                  type="text"
                  className="!py-2.5 !px-4 !mb-4"
                  placeholder={t("remark_placeholder")}
                  value={editData.remark}
                  onChange={(e) => setEditData({ ...editData, remark: e.target.value })}
                />

                <label className="text-[11px] mb-1">{t("proxy")}</label>
                <input
                  type="text"
                  className="!py-2.5 !px-4"
                  placeholder={t("proxy_placeholder")}
                  style={{ marginBottom: 0 }}
                  value={editData.proxy}
                  onChange={(e) => setEditData({ ...editData, proxy: e.target.value })}
                />
              </div>

              <div className="flex gap-3 mt-6">
                <button className="btn-secondary flex-1 h-10 !py-0 !text-xs" onClick={() => setShowEditDialog(false)}>{t("cancel")}</button>
                <button className="btn-gradient flex-1 h-10 !py-0 !text-xs" onClick={handleSaveEdit} disabled={loading}>
                  {loading ? <Spinner className="animate-spin" /> : t("save")}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {showLogsDialog && (
        <div className="modal-overlay active">
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

            <div className="px-5 py-3 border-b border-white/5 flex justify-between items-center bg-white/2">
              <div className="text-[10px] text-main/30 font-bold uppercase tracking-wider">
                {t("logs_summary")
                  .replace("{count}", accountLogs.length.toString())
                  .replace("{days}", "3")}
              </div>
              {accountLogs.length > 0 && (
                <button
                  onClick={handleExportLogs}
                  disabled={loading}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#8a3ffc]/10 text-[#8a3ffc] text-[10px] font-bold hover:bg-[#8a3ffc]/20 transition-all disabled:opacity-50"
                >
                  <DownloadSimple weight="bold" size={14} />
                  {t("export_logs")}
                </button>
              )}
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

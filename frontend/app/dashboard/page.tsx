"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { getToken, logout } from "../../lib/auth";
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
  GithubLogo,
  Trash,
  ListDashes,
  Clock,
  Spinner,
  X,
  PaperPlaneRight
} from "@phosphor-icons/react";
import { ToastContainer, useToast } from "../../components/ui/toast";
import { ThemeLanguageToggle } from "../../components/ThemeLanguageToggle";
import { useLanguage } from "../../context/LanguageContext";

export default function Dashboard() {
  const router = useRouter();
  const { t } = useLanguage();
  const { toasts, addToast, removeToast } = useToast();
  const [token, setLocalToken] = useState<string | null>(null);
  const [accounts, setAccounts] = useState<AccountInfo[]>([]);
  const [tasks, setTasks] = useState<SignTask[]>([]);
  const [loading, setLoading] = useState(false);

  // 设置菜单
  const [showSettingsMenu, setShowSettingsMenu] = useState(false);

  // 日志弹窗
  const [showLogsDialog, setShowLogsDialog] = useState(false);
  const [logsAccountName, setLogsAccountName] = useState("");
  const [accountLogs, setAccountLogs] = useState<AccountLog[]>([]);
  const [logsLoading, setLogsLoading] = useState(false);

  // 添加账号对话框
  const [showAddDialog, setShowAddDialog] = useState(false);
  const [loginStep, setLoginStep] = useState<"input" | "verify">("input");
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
      addToast("请填写账号名称和手机号", "error");
      return;
    }
    try {
      setLoading(true);
      const res = await startAccountLogin(token, {
        account_name: loginData.account_name,
        phone_number: loginData.phone_number,
        proxy: loginData.proxy || undefined,
      });
      setLoginData({ ...loginData, phone_code_hash: res.phone_code_hash });
      setLoginStep("verify");
      addToast("验证码已发送", "success");
    } catch (err: any) {
      addToast(err.message || "发送失败", "error");
    } finally {
      setLoading(false);
    }
  };

  const handleVerifyLogin = async () => {
    if (!token) return;
    if (!loginData.phone_code) {
      addToast("请输入验证码", "error");
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
      });
      addToast("登录成功", "success");
      setShowAddDialog(false);
      loadData(token);
    } catch (err: any) {
      addToast(err.message || "验证失败", "error");
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteAccount = async (name: string) => {
    if (!token) return;
    if (!confirm(t("confirm_delete"))) return;
    try {
      setLoading(true);
      await deleteAccount(token, name);
      addToast("账号已删除", "success");
      loadData(token);
    } catch (err: any) {
      addToast(err.message || "删除失败", "error");
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
      addToast(err.message || "获取日志失败", "error");
    } finally {
      setLogsLoading(false);
    }
  };

  const handleLogout = () => {
    logout();
    router.push("/");
  };

  if (!token || checking) {
    return null;
  }

  return (
    <div id="dashboard-view" className="w-full h-full flex flex-col pt-[72px]">
      <nav className="navbar fixed top-0 left-0 right-0 z-50 h-[72px] px-5 md:px-10 flex justify-between items-center glass-panel rounded-none border-x-0 border-t-0 bg-white/2 dark:bg-black/5">
        <div className="flex items-center gap-3">
          <Lightning weight="fill" style={{ fontSize: '28px', color: '#fcd34d' }} />
          <span className="nav-title font-bold text-lg tracking-tight">TG SignPulse</span>
        </div>
        <div className="flex items-center gap-4">
          <ThemeLanguageToggle />
          <a href="https://github.com" target="_blank" rel="noreferrer" className="action-btn" title="GitHub">
            <GithubLogo weight="bold" />
          </a>
          <Link href="/dashboard/settings" className="action-btn" title={t("sidebar_settings")}>
            <Gear weight="bold" />
          </Link>
        </div>
      </nav>

      <main className="flex-1 p-5 md:p-10 w-full max-w-[1400px] mx-auto overflow-y-auto animate-float-up">
        {loading && accounts.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20">
            <Spinner className="animate-spin mb-4" size={40} weight="bold" />
            <span className="text-main/50">加载中...</span>
          </div>
        ) : (
          <div className="grid grid-cols-[repeat(auto-fill,minmax(300px,1fr))] gap-6 pb-10">
            {accounts.map((acc) => {
              const initial = acc.name.charAt(0).toUpperCase();
              return (
                <div
                  key={acc.name}
                  className="glass-panel h-[190px] p-6 flex flex-col justify-between transition-all hover:-translate-y-1 hover:border-[#8a3ffc] hover:shadow-[0_10px_30px_rgba(0,0,0,0.1)] relative group cursor-pointer"
                  onClick={() => router.push(`/dashboard/account-tasks?name=${acc.name}`)}
                >
                  <div className="flex justify-between items-start">
                    <div className="flex items-center gap-2.5 font-semibold text-base truncate pr-20">
                      <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-[#3c40c6] to-[#8a3ffc] flex items-center justify-center text-xs font-bold text-white shrink-0">
                        {initial}
                      </div>
                      <span className="truncate">{acc.name}</span>
                    </div>
                    <div className="shrink-0 bg-[#8a3ffc]/10 border border-[#8a3ffc]/20 text-[#b57dff] px-3 py-1 rounded-full text-xs font-semibold">
                      {getAccountTaskCount(acc.name)} {t("sidebar_tasks")}
                    </div>
                  </div>

                  <div className="flex justify-between items-center pt-4 border-t border-white/8">
                    <div className="text-[13px] text-[#9496a1] font-mono flex items-center gap-1.5">
                      <Clock weight="bold" />
                      {/* 如果有创建时间显示时间，否则显示占位 */}
                      <span>Connected</span>
                    </div>
                    <div className="flex gap-2">
                      <div
                        className="action-btn !w-8 !h-8 !text-base bg-white/10 hover:bg-white/20 transition-all rounded-md"
                        title="日志"
                        onClick={(e) => { e.stopPropagation(); handleShowLogs(acc.name); }}
                      >
                        <ListDashes weight="bold" />
                      </div>
                      <div
                        className="action-btn !w-8 !h-8 !text-base bg-white/10 hover:bg-rose-500/10 hover:text-[#ff4757] transition-all rounded-md"
                        title="移除"
                        onClick={(e) => { e.stopPropagation(); handleDeleteAccount(acc.name); }}
                      >
                        <Trash weight="bold" />
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}

            {/* 添加新账号卡片 */}
            <div
              className="h-[190px] border-2 border-dashed border-white/10 rounded-[20px] flex flex-col justify-center items-center gap-4 cursor-pointer transition-all hover:border-[#8a3ffc] hover:bg-[#8a3ffc]/3 hover:-translate-y-1 group"
              onClick={() => { setLoginStep("input"); setShowAddDialog(true); }}
            >
              <div className="w-12 h-12 rounded-full bg-white/10 flex items-center justify-center text-2xl text-[#9496a1] transition-all group-hover:bg-[#8a3ffc] group-hover:text-white">
                <Plus weight="bold" />
              </div>
              <span className="font-semibold text-[#9496a1]">{t("add_account")}</span>
            </div>
          </div>
        )}
      </main>

      {showAddDialog && (
        <div className="modal-overlay active" onClick={() => setShowAddDialog(false)}>
          <div className="glass-panel modal-content" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <div className="modal-title">{loginStep === "input" ? t("add_account") : "安全验证"}</div>
              <div className="modal-close" onClick={() => setShowAddDialog(false)}><X weight="bold" /></div>
            </div>

            {loginStep === "input" ? (
              <div className="animate-float-up">
                <div className="mb-5">
                  <label>{t("username")} (唯一标识)</label>
                  <input
                    type="text"
                    placeholder="e.g. Work_Account_01"
                    value={loginData.account_name}
                    onChange={(e) => setLoginData({ ...loginData, account_name: e.target.value })}
                  />
                </div>

                <div className="mb-5">
                  <label>手机号码 (带国家码)</label>
                  <input
                    type="text"
                    placeholder="+86 138 0000 0000"
                    value={loginData.phone_number}
                    onChange={(e) => setLoginData({ ...loginData, phone_number: e.target.value })}
                  />
                </div>

                <div className="mb-5">
                  <label>SOCKS5 代理 (可选)</label>
                  <input
                    type="text"
                    placeholder="socks5://user:pass@host:port"
                    value={loginData.proxy}
                    onChange={(e) => setLoginData({ ...loginData, proxy: e.target.value })}
                  />
                </div>

                <div className="flex gap-3 mt-8">
                  <button className="btn-secondary flex-1" onClick={() => setShowAddDialog(false)}>取消</button>
                  <button className="btn-gradient flex-1" onClick={handleStartLogin} disabled={loading}>
                    {loading ? <Spinner className="animate-spin" /> : "下一步"}
                  </button>
                </div>
              </div>
            ) : (
              <div className="animate-float-up text-center">
                <div className="w-20 h-20 bg-[#8a3ffc]/10 rounded-full flex items-center justify-center mx-auto mb-4 text-4xl">
                  <PaperPlaneRight weight="fill" className="text-[#8a3ffc]" />
                </div>
                <p className="text-main/60 text-sm mb-6">验证码已发送至您的手机/Telegram 客户端</p>

                <div className="text-left">
                  <div className="mb-5">
                    <label>5 位数验证码</label>
                    <input
                      type="text"
                      placeholder="XXXXX"
                      className="text-center text-xl tracking-[1em]"
                      value={loginData.phone_code}
                      onChange={(e) => setLoginData({ ...loginData, phone_code: e.target.value })}
                    />
                  </div>
                  <div className="mb-5">
                    <label>两步验证密码 (如未开启请留空)</label>
                    <input
                      type="password"
                      placeholder="Cloud Password"
                      value={loginData.password}
                      onChange={(e) => setLoginData({ ...loginData, password: e.target.value })}
                    />
                  </div>
                </div>

                <div className="flex gap-3 mt-8">
                  <button className="btn-secondary flex-1" onClick={() => setLoginStep("input")}>返回</button>
                  <button className="btn-gradient flex-1" onClick={handleVerifyLogin} disabled={loading}>
                    {loading ? <Spinner className="animate-spin" /> : "确认连接"}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {showLogsDialog && (
        <div className="modal-overlay active" onClick={() => setShowLogsDialog(false)}>
          <div className="glass-panel modal-content !max-w-4xl max-h-[85vh] flex flex-col overflow-hidden" onClick={e => e.stopPropagation()}>
            <div className="modal-header border-b border-white/10 pb-4 mb-0">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-[#8a3ffc]/10 rounded-lg text-[#8a3ffc]">
                  <ListDashes weight="bold" size={20} />
                </div>
                <div className="modal-title font-bold text-xl">{logsAccountName} 运行日志</div>
              </div>
              <div className="modal-close" onClick={() => setShowLogsDialog(false)}><X weight="bold" /></div>
            </div>

            <div className="flex-1 overflow-y-auto p-4 font-mono text-sm bg-black/20 custom-scrollbar mt-4 rounded-xl border border-white/10">
              {logsLoading ? (
                <div className="flex flex-col items-center justify-center py-20 text-main/30">
                  <Spinner className="animate-spin mb-4" size={32} />
                  读取中...
                </div>
              ) : accountLogs.length === 0 ? (
                <div className="text-center py-20 text-main/20">暂无运行日志</div>
              ) : (
                <div className="space-y-4">
                  {accountLogs.map((log, i) => (
                    <div key={i} className="p-4 rounded-xl bg-white/5 border border-white/5 hover:border-white/10 transition-colors">
                      <div className="flex justify-between items-center mb-3 text-xs">
                        <span className="text-main/30">{new Date(log.created_at).toLocaleString()}</span>
                        <span className={`px-2 py-0.5 rounded-full ${log.success ? 'bg-emerald-500/10 text-emerald-400' : 'bg-rose-500/10 text-rose-400'}`}>
                          {log.success ? 'SUCCESS' : 'FAILURE'}
                        </span>
                      </div>
                      <pre className="whitespace-pre-wrap text-main/70 leading-relaxed overflow-x-auto max-h-[200px] scrollbar-thin">
                        {log.message}
                      </pre>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="p-4 border-t border-white/10 text-center bg-white/5 mt-4">
              <button className="btn-secondary px-10 mx-auto" onClick={() => setShowLogsDialog(false)}>
                关闭
              </button>
            </div>
          </div>
        </div>
      )}

      <ToastContainer toasts={toasts} removeToast={removeToast} />
    </div>
  );
}

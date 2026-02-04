"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { login } from "../lib/api";
import { setToken } from "../lib/auth";
import {
  Lightning,
  Spinner,
  GithubLogo
} from "@phosphor-icons/react";
import { ThemeLanguageToggle } from "./ThemeLanguageToggle";
import { useLanguage } from "../context/LanguageContext";

export default function LoginForm() {
  const router = useRouter();
  const { t } = useLanguage();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [totp, setTotp] = useState("");
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setErrorMsg("");
    try {
      const res = await login({ username, password, totp_code: totp || undefined });
      setToken(res.access_token);
      router.push("/dashboard");
    } catch (err: any) {
      const msg = err?.message || "";
      let displayMsg = t("login_failed");
      const lowerMsg = msg.toLowerCase();

      if (lowerMsg.includes("totp")) {
        displayMsg = t("totp_error");
      } else if (lowerMsg.includes("invalid") || lowerMsg.includes("credentials") || lowerMsg.includes("password")) {
        displayMsg = t("user_or_pass_error");
      } else if (!msg) {
        displayMsg = t("login_failed");
      }
      setErrorMsg(displayMsg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div id="login-view" className="w-full min-h-screen flex flex-col justify-center items-center relative p-4 overflow-x-hidden bg-black/5 dark:bg-black/20">
      <div className="glass-panel w-full max-w-[420px] p-6 md:p-8 text-center animate-float-up border border-black/5 dark:border-white/5 shadow-2xl">
        <div className="mb-4">
          <Lightning
            weight="fill"
            className="inline-block"
            style={{ fontSize: '48px', color: '#fcd34d', filter: 'drop-shadow(0 0 12px rgba(252, 211, 77, 0.4))' }}
          />
          <div className="brand-text-grad mt-1 text-xl">TG SignPulse</div>
          <p className="text-[#9496a1] text-[11px] mt-1 leading-relaxed px-4 font-medium">{t("settings_desc")}</p>
        </div>

        <form onSubmit={handleSubmit} className="text-left" autoComplete="off">
          <div className="mb-4">
            <label className="text-[11px] mb-1.5 block font-bold text-main/60 uppercase tracking-widest">{t("username")}</label>
            <input
              type="text"
              name="username"
              className="!py-3 !px-4 bg-black/5 dark:bg-white/5 border border-black/5 dark:border-white/10 rounded-xl"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder={t("username")}
              autoComplete="off"
            />
          </div>
          <div className="mb-4">
            <label className="text-[11px] mb-1.5 block font-bold text-main/60 uppercase tracking-widest">{t("password")}</label>
            <input
              type="password"
              name="password"
              className="!py-3 !px-4 bg-black/5 dark:bg-white/5 border border-black/5 dark:border-white/10 rounded-xl"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={t("password")}
              autoComplete="new-password"
            />
          </div>
          <div className="mb-5">
            <label className="text-[11px] mb-1.5 block font-bold text-main/60 uppercase tracking-widest">{t("totp")}</label>
            <input
              type="text"
              name="totp"
              className="!py-3 !px-4 text-center tracking-[4px] bg-black/5 dark:bg-white/5 border border-black/5 dark:border-white/10 rounded-xl font-bold"
              value={totp}
              onChange={(e) => setTotp(e.target.value)}
              placeholder={t("totp_placeholder")}
              autoComplete="off"
            />
          </div>

          {errorMsg && (
            <div className="text-[#ff4757] text-[11px] mb-5 text-center bg-[#ff4757]/10 p-2.5 rounded-xl font-medium border border-[#ff4757]/20">
              {errorMsg}
            </div>
          )}

          <button className="btn-gradient w-full !py-3.5 font-bold shadow-xl rounded-xl transition-all" type="submit" disabled={loading}>
            {loading ? (
              <div className="flex items-center justify-center gap-2">
                <Spinner className="animate-spin" size={18} />
                <span>{t("login_loading")}</span>
              </div>
            ) : (
              <span className="text-sm">{t("login")}</span>
            )}
          </button>
        </form>

        <div className="login-footer-icons !mt-6 !pt-4 border-t border-black/5 dark:border-white/5 flex items-center justify-center gap-6">
          <ThemeLanguageToggle />
          <a
            href="https://github.com/akasls/TG-SignPulse"
            target="_blank"
            rel="noreferrer"
            className="action-btn !w-9 !h-9 !text-xl"
            title={t("github_repo")}
          >
            <GithubLogo weight="bold" />
          </a>
        </div>
      </div>
    </div>
  );
}

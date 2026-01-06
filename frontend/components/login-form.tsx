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
  const { t, language } = useLanguage();

  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("admin123");
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
      const msg = err?.message || t("login_failed");
      let displayMsg = msg;
      if (msg.includes("Invalid credentials") || msg.includes("Invalid username or password")) {
        displayMsg = t("user_or_pass_error");
      } else if (msg.includes("TOTP code required") || msg.includes("Invalid TOTP code")) {
        displayMsg = t("totp_error");
      }
      setErrorMsg(displayMsg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div id="login-view" className="w-full h-[100dvh] flex flex-col justify-center items-center relative p-4 overflow-hidden bg-black/5 dark:bg-black/20">
      <div className="glass-panel w-full max-w-[420px] p-8 md:p-10 text-center animate-float-up border border-black/5 dark:border-white/5 relative z-10">
        <div className="mb-6">
          <Lightning
            weight="fill"
            className="inline-block"
            style={{ fontSize: '48px', color: '#fcd34d', filter: 'drop-shadow(0 0 10px rgba(252, 211, 77, 0.4))' }}
          />
          <div className="brand-text-grad mt-2">TG SignPulse</div>
          <p className="text-[#9496a1] text-[11px] mt-1 leading-relaxed px-4">{t("settings_desc")}</p>
        </div>

        <form onSubmit={handleSubmit} className="text-left" autoComplete="off">
          <div className="mb-4">
            <label className="text-[12px] mb-1.5 font-bold text-main/60">{t("username")}</label>
            <input
              type="text"
              name="username"
              className="!py-3 !px-4 bg-white/5 dark:bg-white/5 border border-black/5 dark:border-white/10"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder={t("username")}
              autoComplete="off"
            />
          </div>
          <div className="mb-4">
            <label className="text-[12px] mb-1.5 font-bold text-main/60">{t("password")}</label>
            <input
              type="password"
              name="password"
              className="!py-3 !px-4 bg-white/5 dark:bg-white/5 border border-black/5 dark:border-white/10"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={t("password")}
              autoComplete="new-password"
            />
          </div>
          <div className="mb-5">
            <label className="text-[12px] mb-1.5 font-bold text-main/60">{t("totp")}</label>
            <input
              type="text"
              name="totp"
              className="!py-3 !px-4 text-center tracking-[4px] bg-white/5 dark:bg-white/5 border border-black/5 dark:border-white/10 font-bold"
              value={totp}
              onChange={(e) => setTotp(e.target.value)}
              placeholder={language === "zh" ? "留空即跳过" : "Skip if disabled"}
              autoComplete="off"
            />
          </div>

          {errorMsg && (
            <div className="text-[#ff4757] text-[11px] mb-4 text-center bg-[#ff4757]/10 p-2 rounded-lg font-medium border border-[#ff4757]/20">
              {errorMsg}
            </div>
          )}

          <button className="btn-gradient w-full !py-3.5 font-bold shadow-lg" type="submit" disabled={loading}>
            {loading ? (
              <div className="flex items-center justify-center gap-2">
                <Spinner className="animate-spin" size={18} />
                <span>{t("login_loading")}</span>
              </div>
            ) : (
              t("login")
            )}
          </button>
        </form>

        <div className="login-footer-icons !mt-8 !pt-6 border-t border-black/5 dark:border-white/5 flex items-center justify-center gap-6">
          <ThemeLanguageToggle />
          <a
            href="https://github.com/akasls/TG-SignPulse"
            target="_blank"
            rel="noreferrer"
            className="action-btn !w-9 !h-9 !text-xl"
            title="GitHub Repository"
          >
            <GithubLogo weight="bold" />
          </a>
        </div>
      </div>
    </div>
  );
}

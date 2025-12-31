"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { login, resetTOTP } from "../lib/api";
import { setToken } from "../lib/auth";
import { Button } from "./ui/button";
import { Card, CardContent } from "./ui/card";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import { useToast } from "./ui/toast";

export default function LoginForm() {
  const router = useRouter();
  const { addToast } = useToast();
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("admin123");
  const [totp, setTotp] = useState("");
  const [loading, setLoading] = useState(false);
  const [showTotpHelp, setShowTotpHelp] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      const res = await login({ username, password, totp_code: totp || undefined });
      setToken(res.access_token);
      addToast("登录成功", "success");
      router.push("/dashboard");
    } catch (err: any) {
      const errMsg = err?.message || "登录失败";
      // 常见错误中文转换
      let displayMsg = errMsg;
      if (errMsg.includes("Invalid credentials") || errMsg.includes("Invalid username or password")) {
        displayMsg = "用户名或密码错误";
      } else if (errMsg.includes("TOTP code required") || errMsg.includes("Invalid TOTP code")) {
        displayMsg = "两步验证码错误或已过期";
        setShowTotpHelp(true);
      } else if (errMsg.includes("Could not validate credentials")) {
        displayMsg = "认证失败，请重新登录";
      }

      addToast(displayMsg, "error");
    } finally {
      setLoading(false);
    }
  };

  const handleResetTOTP = async () => {
    if (!username || !password) {
      addToast("请先填写用户名和密码", "error");
      return;
    }

    setLoading(true);
    try {
      const res = await resetTOTP({ username, password });
      addToast(res.message || "重置成功", "success");
      setShowTotpHelp(false);
      setTotp("");
    } catch (err: any) {
      addToast(err?.message || "重置失败", "error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <Card className="w-full max-w-xl relative animate-scale-in">
        <CardContent className="p-8 sm:p-12">
          {/* Logo 和标题 */}
          <div className="text-center mb-8">
            <div className="text-5xl mb-4 animate-pulse-glow inline-block rounded-full p-2">⚡</div>
            <h1 className="text-2xl font-bold aurora-text mb-2">TG SignPulse</h1>
            <p className="text-white/50 text-sm">Telegram 自动签到控制台</p>
          </div>

          <form className="space-y-5" onSubmit={handleSubmit}>
            <div className="space-y-2">
              <Label>用户名</Label>
              <Input
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="请输入用户名"
                className="glass-input"
              />
            </div>
            <div className="space-y-2">
              <Label>密码</Label>
              <Input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="请输入密码"
                className="glass-input"
              />
            </div>
            <div className="space-y-2">
              <Label>两步验证码 (可选)</Label>
              <Input
                value={totp}
                onChange={(e) => setTotp(e.target.value)}
                placeholder="如未启用两步验证，请留空"
                className="glass-input"
              />
            </div>

            <Button className="w-full btn-primary" type="submit" disabled={loading}>
              {loading ? (
                <span className="flex items-center gap-2">
                  <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>
                  登录中...
                </span>
              ) : "登录"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}

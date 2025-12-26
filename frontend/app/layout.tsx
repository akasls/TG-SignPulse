import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "tg-signer 控制台",
  description: "Telegram 自动化签到工具 - 现代化 Web 管理界面",
  icons: {
    icon: '/favicon.svg',
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}



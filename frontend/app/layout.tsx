import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "tg-signer 控制台",
  description: "Docker First 的 tg-signer 可视化面板",
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



import type { Metadata } from "next";
import "./globals.css";
import { Shell } from "@/components/Shell";

export const metadata: Metadata = {
  title: "AlphaRadar | Executive Terminal",
  description: "AI 产业趋势雷达与十倍股早期特征发现系统"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body className="antialiased selection:bg-indigo-100">
        <Shell>{children}</Shell>
      </body>
    </html>
  );
}

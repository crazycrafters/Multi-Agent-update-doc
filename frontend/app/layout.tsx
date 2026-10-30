import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: "AI Resume Evolution",
  description: "An evidence-grounded resume workspace for your next role",
};
export default function Layout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

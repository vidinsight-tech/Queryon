import type { Metadata } from "next";
import dynamic from "next/dynamic";
import "./globals.css";
import { Providers } from "./providers";
import { Sidebar } from "@/components/layout/Sidebar";
import { Toaster } from "sonner";

const ChatPreviewPanel = dynamic(
  () => import("@/components/chat/ChatPreviewPanel").then((m) => m.ChatPreviewPanel),
  { ssr: false, loading: () => null }
);

export const metadata: Metadata = {
  title: "Queryon Admin",
  description: "Admin panel for the Queryon RAG platform",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="tr">
      <body className="bg-gray-50 text-gray-900 antialiased">
        <Providers>
          <div className="flex min-h-screen">
            <Sidebar />
            <main className="flex-1 min-w-0 p-6 md:p-8 overflow-auto">
              {children}
            </main>
          </div>
          <ChatPreviewPanel />
        </Providers>
        <Toaster
          position="bottom-right"
          toastOptions={{
            classNames: {
              toast: "font-sans text-sm",
              success: "border-green-200",
              error: "border-red-200",
            },
          }}
          richColors
          closeButton
        />
      </body>
    </html>
  );
}

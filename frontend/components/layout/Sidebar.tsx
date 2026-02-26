"use client";
import { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  GitBranch,
  Wrench,
  MessageSquare,
  FlaskConical,
  Brain,
  Layers,
  DatabaseZap,
  BookOpen,
  Calendar,
  CalendarCheck,
  BotMessageSquare,
  ShoppingBag,
  MessagesSquare,
  Plug,
  Menu,
  X,
} from "lucide-react";

type NavItem = { href: string; label: string; icon: React.ElementType };
type NavSection = { title: string; items: NavItem[] };

const sections: NavSection[] = [
  {
    title: "Genel",
    items: [{ href: "/", label: "Dashboard", icon: LayoutDashboard }],
  },
  {
    title: "Kurallar",
    items: [
      { href: "/rules", label: "Kurallar & Akışlar", icon: GitBranch },
      { href: "/rules/test", label: "Kural Test", icon: FlaskConical },
    ],
  },
  {
    title: "Modeller",
    items: [
      { href: "/llms", label: "LLM'ler", icon: Brain },
      { href: "/embeddings", label: "Embeddings", icon: Layers },
      { href: "/rag", label: "RAG", icon: DatabaseZap },
    ],
  },
  {
    title: "Veriler",
    items: [
      { href: "/documents", label: "Bilgi Tabanı", icon: BookOpen },
      { href: "/calendars", label: "Takvimler", icon: Calendar },
      { href: "/appointments", label: "Randevular", icon: CalendarCheck },
      { href: "/orders", label: "Siparişler", icon: ShoppingBag },
      { href: "/conversations", label: "Konuşmalar", icon: MessagesSquare },
    ],
  },
  {
    title: "Sistem",
    items: [
      { href: "/orchestrator", label: "Bot Ayarları", icon: BotMessageSquare },
      { href: "/tools", label: "Araçlar", icon: Wrench },
      { href: "/integrations", label: "Entegrasyonlar", icon: Plug },
    ],
  },
];

function NavContent({ onClose }: { onClose?: () => void }) {
  const pathname = usePathname();

  const isActive = (href: string) => {
    if (href === "/") return pathname === "/";
    if (href === "/rules") {
      return (
        pathname === "/rules" ||
        (pathname.startsWith("/rules/") && !pathname.startsWith("/rules/test"))
      );
    }
    return pathname === href || pathname.startsWith(href + "/");
  };

  return (
    <>
      <div className="px-5 py-5 border-b border-gray-200 flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2">
            <MessageSquare className="w-5 h-5 text-indigo-600" />
            <span className="font-bold text-lg tracking-tight">Queryon</span>
          </div>
          <p className="text-xs text-gray-400 mt-0.5">Admin Panel</p>
        </div>
        {onClose && (
          <button
            onClick={onClose}
            className="p-1 text-gray-400 hover:text-gray-600 transition-colors md:hidden"
          >
            <X className="w-5 h-5" />
          </button>
        )}
      </div>
      <nav className="flex-1 px-3 py-4 space-y-4 overflow-y-auto">
        {sections.map((section) => (
          <div key={section.title}>
            <p className="px-3 mb-1 text-[11px] font-semibold uppercase tracking-wider text-gray-400">
              {section.title}
            </p>
            <div className="space-y-0.5">
              {section.items.map(({ href, label, icon: Icon }) => {
                const active = isActive(href);
                return (
                  <Link
                    key={href}
                    href={href}
                    onClick={onClose}
                    className={`flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                      active
                        ? "bg-indigo-50 text-indigo-700"
                        : "text-gray-600 hover:bg-gray-100"
                    }`}
                  >
                    <Icon className="w-4 h-4 shrink-0" />
                    {label}
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </nav>
    </>
  );
}

export function Sidebar() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const pathname = usePathname();

  // Close mobile menu on route change
  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  return (
    <>
      {/* Mobile hamburger button */}
      <button
        onClick={() => setMobileOpen(true)}
        className="fixed top-4 left-4 z-40 p-2 rounded-md bg-white shadow-md border border-gray-200 text-gray-600 hover:text-gray-900 transition-colors md:hidden"
        aria-label="Menüyü aç"
      >
        <Menu className="w-5 h-5" />
      </button>

      {/* Mobile overlay */}
      {mobileOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/40 md:hidden"
          onClick={() => setMobileOpen(false)}
        />
      )}

      {/* Mobile drawer */}
      <aside
        className={`fixed inset-y-0 left-0 z-50 w-56 bg-white border-r border-gray-200 flex flex-col transform transition-transform md:hidden ${
          mobileOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <NavContent onClose={() => setMobileOpen(false)} />
      </aside>

      {/* Desktop sidebar — always visible */}
      <aside className="hidden md:flex w-56 shrink-0 bg-white border-r border-gray-200 flex-col min-h-screen sticky top-0">
        <NavContent />
      </aside>
    </>
  );
}

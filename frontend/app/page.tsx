"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { dashboardApi } from "@/lib/api";
import type { DashboardStats, DashboardRecentConversation } from "@/lib/types";
import {
  MessagesSquare,
  CalendarCheck,
  ShoppingBag,
  BookOpen,
  Clock,
  ArrowRight,
  Circle,
} from "lucide-react";
import { relativeTime } from "@/lib/utils";

const STATUS_COLORS: Record<string, string> = {
  active: "text-green-600",
  closed: "text-gray-400",
  pending: "text-amber-600",
  confirmed: "text-green-600",
  cancelled: "text-red-500",
  completed: "text-indigo-600",
};

// ── Sub-components ────────────────────────────────────────────────────────────

function StatCard({
  label,
  value,
  sub,
  icon: Icon,
  href,
  color,
}: {
  label: string;
  value: number;
  sub?: string;
  icon: React.ElementType;
  href: string;
  color: string;
}) {
  return (
    <Link
      href={href}
      className="bg-white rounded-xl border border-gray-200 p-5 flex items-start gap-4 hover:shadow-sm transition-shadow group"
    >
      <div className={`p-2.5 rounded-lg ${color}`}>
        <Icon className="w-5 h-5" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm text-gray-500">{label}</p>
        <p className="text-2xl font-bold text-gray-900 mt-0.5">{value.toLocaleString()}</p>
        {sub && <p className="text-xs text-gray-400 mt-0.5">{sub}</p>}
      </div>
      <ArrowRight className="w-4 h-4 text-gray-300 group-hover:text-gray-500 mt-1 transition-colors" />
    </Link>
  );
}

function StatusBreakdown({ items, total }: { items: { status: string; count: number }[]; total: number }) {
  if (total === 0) return <p className="text-xs text-gray-400">Henüz kayıt yok</p>;
  return (
    <div className="flex flex-wrap gap-2">
      {items.map((s) => (
        <span
          key={s.status}
          className={`text-xs font-medium px-2 py-0.5 rounded-full border ${
            s.status === "pending"
              ? "bg-amber-50 border-amber-200 text-amber-700"
              : s.status === "confirmed" || s.status === "completed"
              ? "bg-green-50 border-green-200 text-green-700"
              : s.status === "cancelled"
              ? "bg-red-50 border-red-200 text-red-700"
              : "bg-gray-50 border-gray-200 text-gray-600"
          }`}
        >
          {s.status}: {s.count}
        </span>
      ))}
    </div>
  );
}

function RecentConversationRow({ conv }: { conv: DashboardRecentConversation }) {
  const statusColor = STATUS_COLORS[conv.status] ?? "text-gray-400";
  return (
    <Link
      href="/conversations"
      className="flex items-center gap-3 px-4 py-2.5 hover:bg-gray-50 rounded-lg transition-colors"
    >
      <Circle className={`w-2 h-2 fill-current ${statusColor} shrink-0`} />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-gray-800 truncate">
          {conv.contact_name ?? "Anonim"}
        </p>
        <p className="text-xs text-gray-400">
          {conv.platform} · {conv.message_count} mesaj
        </p>
      </div>
      <p className="text-xs text-gray-400 shrink-0 text-right">
        {relativeTime(conv.last_message_at ?? conv.created_at)}
      </p>
    </Link>
  );
}

// ── Skeleton ──────────────────────────────────────────────────────────────────

function SkeletonCard() {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5 animate-pulse">
      <div className="flex items-start gap-4">
        <div className="w-10 h-10 bg-gray-100 rounded-lg" />
        <div className="flex-1 space-y-2">
          <div className="h-3 bg-gray-100 rounded w-24" />
          <div className="h-7 bg-gray-100 rounded w-16" />
        </div>
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function DashboardPage() {
  const { data: stats, isLoading, isError } = useQuery<DashboardStats>({
    queryKey: ["dashboard"],
    queryFn: dashboardApi.getStats,
    refetchInterval: 30_000,
  });

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
        <p className="text-sm text-gray-500 mt-1">
          Sisteme genel bakış — her 30 saniyede güncellenir.
        </p>
      </div>

      {isError && (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-3 text-sm">
          İstatistikler yüklenemedi. API erişilebilir mi?
        </div>
      )}

      {/* Stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {isLoading ? (
          Array.from({ length: 4 }).map((_, i) => <SkeletonCard key={i} />)
        ) : stats ? (
          <>
            <StatCard
              label="Toplam Konuşma"
              value={stats.conversations_total}
              sub={`${stats.conversations_today} bugün · ${stats.conversations_active} aktif`}
              icon={MessagesSquare}
              href="/conversations"
              color="bg-indigo-50 text-indigo-600"
            />
            <StatCard
              label="Randevular"
              value={stats.appointments_total}
              icon={CalendarCheck}
              href="/appointments"
              color="bg-green-50 text-green-600"
            />
            <StatCard
              label="Siparişler"
              value={stats.orders_total}
              icon={ShoppingBag}
              href="/orders"
              color="bg-amber-50 text-amber-600"
            />
            <StatCard
              label="Aktif Belgeler"
              value={stats.documents_active}
              icon={BookOpen}
              href="/documents"
              color="bg-purple-50 text-purple-600"
            />
          </>
        ) : null}
      </div>

      {/* Detail row */}
      {stats && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Appointments breakdown */}
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold text-gray-700 flex items-center gap-1.5">
                <CalendarCheck className="w-4 h-4 text-green-500" />
                Randevu Durumları
              </h2>
              <Link href="/appointments" className="text-xs text-indigo-600 hover:underline">
                Tümünü gör
              </Link>
            </div>
            <StatusBreakdown items={stats.appointments_by_status} total={stats.appointments_total} />
          </div>

          {/* Orders breakdown */}
          <div className="bg-white rounded-xl border border-gray-200 p-5">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold text-gray-700 flex items-center gap-1.5">
                <ShoppingBag className="w-4 h-4 text-amber-500" />
                Sipariş Durumları
              </h2>
              <Link href="/orders" className="text-xs text-indigo-600 hover:underline">
                Tümünü gör
              </Link>
            </div>
            <StatusBreakdown items={stats.orders_by_status} total={stats.orders_total} />
          </div>
        </div>
      )}

      {/* Recent conversations */}
      <div className="bg-white rounded-xl border border-gray-200">
        <div className="px-5 py-4 border-b border-gray-100 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-gray-700 flex items-center gap-1.5">
            <Clock className="w-4 h-4 text-gray-400" />
            Son Konuşmalar
          </h2>
          <Link href="/conversations" className="text-xs text-indigo-600 hover:underline flex items-center gap-1">
            Tümünü gör <ArrowRight className="w-3 h-3" />
          </Link>
        </div>

        {isLoading ? (
          <div className="p-5 space-y-3 animate-pulse">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="flex gap-3">
                <div className="w-2 h-2 bg-gray-100 rounded-full mt-1.5" />
                <div className="flex-1 space-y-1.5">
                  <div className="h-3 bg-gray-100 rounded w-32" />
                  <div className="h-2.5 bg-gray-100 rounded w-20" />
                </div>
                <div className="h-2.5 bg-gray-100 rounded w-14" />
              </div>
            ))}
          </div>
        ) : stats?.recent_conversations.length === 0 ? (
          <p className="text-gray-400 text-sm px-5 py-6">Henüz konuşma yok.</p>
        ) : (
          <div className="py-2 px-1">
            {stats?.recent_conversations.map((conv) => (
              <RecentConversationRow key={conv.id} conv={conv} />
            ))}
          </div>
        )}
      </div>

      {/* Quick links */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { href: "/orchestrator", label: "Bot Ayarları", desc: "Kimlik, modlar, kısıtlamalar" },
          { href: "/tools", label: "Araçlar", desc: "Webhook ve yerleşik araçlar" },
          { href: "/rules", label: "Kurallar", desc: "Tetikleyici ve yanıt akışları" },
          { href: "/documents", label: "Bilgi Tabanı", desc: "Belge yükle ve yönet" },
        ].map(({ href, label, desc }) => (
          <Link
            key={href}
            href={href}
            className="bg-gray-50 rounded-xl border border-gray-200 px-4 py-3 hover:bg-white hover:shadow-sm transition group"
          >
            <p className="text-sm font-medium text-gray-800 group-hover:text-indigo-700 transition-colors">{label}</p>
            <p className="text-xs text-gray-400 mt-0.5">{desc}</p>
          </Link>
        ))}
      </div>
    </div>
  );
}

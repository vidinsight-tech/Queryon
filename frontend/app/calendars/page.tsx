"use client";

import { useState } from "react";
import dynamic from "next/dynamic";
import { CalendarList } from "@/components/calendars/CalendarList";

const WeeklyCalendarGrid = dynamic(
  () => import("@/components/calendars/WeeklyCalendarGrid").then((m) => m.WeeklyCalendarGrid),
  { ssr: false, loading: () => <div className="py-8 text-center text-sm text-gray-400">Yükleniyor…</div> }
);
import { LayoutList, CalendarDays } from "lucide-react";

const TABS = [
  { id: "resources", label: "Kaynaklar", icon: LayoutList },
  { id: "weekly",    label: "Haftalık Plan", icon: CalendarDays },
] as const;

export default function CalendarsPage() {
  const [tab, setTab] = useState<"resources" | "weekly">("resources");

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Takvimler</h1>
        <p className="text-sm text-gray-500 mt-1">
          Kaynak takvimleri yönetin, Google Calendar bağlayın ve haftalık planı görüntüleyin.
        </p>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-gray-200">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors ${
              tab === id
                ? "border-indigo-600 text-indigo-600"
                : "border-transparent text-gray-500 hover:text-gray-700"
            }`}
          >
            <Icon className="w-4 h-4" />
            {label}
          </button>
        ))}
      </div>

      {tab === "resources" ? <CalendarList /> : <WeeklyCalendarGrid />}
    </div>
  );
}

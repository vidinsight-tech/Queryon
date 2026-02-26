"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { calendarsApi } from "@/lib/api";
import type { CalendarBlock, CalendarResource } from "@/lib/types";
import { ChevronLeft, ChevronRight, Calendar } from "lucide-react";

// ── Grid constants ────────────────────────────────────────────────────────────
const HOUR_HEIGHT = 64;   // px per 1 hour
const DAY_START   = 8;    // 08:00
const DAY_END     = 21;   // 21:00
const TOTAL_HOURS = DAY_END - DAY_START;
const TOTAL_HEIGHT = TOTAL_HOURS * HOUR_HEIGHT;

const TR_DAYS = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"];
const TR_MONTHS = [
  "Oca", "Şub", "Mar", "Nis", "May", "Haz",
  "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara",
];

// ── Helpers ───────────────────────────────────────────────────────────────────

/** Monday of the week that contains `date`. */
function getMonday(date: Date): Date {
  const d = new Date(date);
  const day = d.getDay(); // 0=Sun
  d.setDate(d.getDate() - ((day + 6) % 7));
  d.setHours(0, 0, 0, 0);
  return d;
}

/** Array of 7 Date objects starting from Monday. */
function weekDates(monday: Date): Date[] {
  return Array.from({ length: 7 }, (_, i) => {
    const d = new Date(monday);
    d.setDate(monday.getDate() + i);
    return d;
  });
}

function toISO(d: Date) {
  return d.toISOString().slice(0, 10);
}

/** "HH:MM" or "HH:MM:SS" → minutes elapsed since DAY_START */
function timeToOffsetMin(t: string): number {
  const [h, m] = t.split(":").map(Number);
  return (h - DAY_START) * 60 + m;
}

function blockTopPx(start: string): number {
  const min = timeToOffsetMin(start);
  return Math.max(0, (min / 60) * HOUR_HEIGHT);
}

function blockHeightPx(start: string, end: string): number {
  const dur = timeToOffsetMin(end) - timeToOffsetMin(start);
  return Math.max(20, (dur / 60) * HOUR_HEIGHT);
}

// ── Block colour ──────────────────────────────────────────────────────────────

function blockClasses(type: string): string {
  switch (type) {
    case "booked":  return "bg-indigo-100 border border-indigo-300 text-indigo-800";
    case "break":   return "bg-amber-100  border border-amber-300  text-amber-800";
    case "blocked": return "bg-red-100    border border-red-300    text-red-800";
    case "buffer":  return "bg-gray-100   border border-gray-300   text-gray-600";
    default:        return "bg-blue-100   border border-blue-300   text-blue-800";
  }
}

// ── Sub-components ────────────────────────────────────────────────────────────

function TimeColumn() {
  return (
    <div className="relative w-14 shrink-0" style={{ height: TOTAL_HEIGHT }}>
      {Array.from({ length: TOTAL_HOURS }, (_, i) => (
        <div
          key={i}
          className="absolute right-2 text-[11px] text-gray-400 leading-none"
          style={{ top: i * HOUR_HEIGHT - 6 }}
        >
          {String(DAY_START + i).padStart(2, "0")}:00
        </div>
      ))}
      {/* bottom label */}
      <div
        className="absolute right-2 text-[11px] text-gray-400 leading-none"
        style={{ top: TOTAL_HOURS * HOUR_HEIGHT - 6 }}
      >
        {String(DAY_END).padStart(2, "0")}:00
      </div>
    </div>
  );
}

function HourLines() {
  return (
    <>
      {Array.from({ length: TOTAL_HOURS + 1 }, (_, i) => (
        <div
          key={i}
          className="absolute left-0 right-0 border-t border-gray-100"
          style={{ top: i * HOUR_HEIGHT }}
        />
      ))}
    </>
  );
}

function DayColumn({
  date,
  blocks,
  isToday,
}: {
  date: Date;
  blocks: CalendarBlock[];
  isToday: boolean;
}) {
  const dayBlocks = blocks.filter((b) => b.date === toISO(date));

  return (
    <div className="flex-1 min-w-0 relative" style={{ height: TOTAL_HEIGHT }}>
      <HourLines />
      {dayBlocks.map((b) => {
        const top = blockTopPx(b.start_time);
        const height = blockHeightPx(b.start_time, b.end_time);
        // Only render blocks that fall within the visible range
        if (top >= TOTAL_HEIGHT || top + height <= 0) return null;
        return (
          <div
            key={b.id}
            className={`absolute left-1 right-1 rounded-md px-1.5 py-1 overflow-hidden cursor-default select-none ${blockClasses(b.block_type)}`}
            style={{ top, height }}
            title={`${b.start_time.slice(0, 5)}–${b.end_time.slice(0, 5)} · ${b.label || b.block_type}`}
          >
            <div className="text-[11px] font-semibold truncate leading-tight">
              {b.label || b.block_type}
            </div>
            {height >= 36 && (
              <div className="text-[10px] opacity-70 leading-tight">
                {b.start_time.slice(0, 5)}–{b.end_time.slice(0, 5)}
              </div>
            )}
          </div>
        );
      })}
      {isToday && (
        <div
          className="absolute left-0 right-0 h-0.5 bg-indigo-400 z-10"
          style={{
            top: blockTopPx(
              `${String(new Date().getHours()).padStart(2, "0")}:${String(new Date().getMinutes()).padStart(2, "0")}`
            ),
          }}
        />
      )}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export function WeeklyCalendarGrid() {
  const [selectedCalId, setSelectedCalId] = useState<string | null>(null);
  const [monday, setMonday] = useState<Date>(() => getMonday(new Date()));

  const days = weekDates(monday);
  const startDate = toISO(days[0]);
  const endDate   = toISO(days[6]);
  const todayStr  = toISO(new Date());

  // All calendar resources for the selector
  const { data: calendars = [] } = useQuery<CalendarResource[]>({
    queryKey: ["calendars"],
    queryFn: () => calendarsApi.list(),
  });

  // Blocks for the selected calendar for the current week
  const { data: blocks = [], isLoading } = useQuery<CalendarBlock[]>({
    queryKey: ["calendar-blocks-week", selectedCalId, startDate, endDate],
    queryFn: () =>
      calendarsApi.listBlocks(selectedCalId!, { start_date: startDate, end_date: endDate }),
    enabled: !!selectedCalId,
  });

  const selectedCal = calendars.find((c) => c.id === selectedCalId);

  const prevWeek = () => {
    const d = new Date(monday);
    d.setDate(d.getDate() - 7);
    setMonday(d);
  };
  const nextWeek = () => {
    const d = new Date(monday);
    d.setDate(d.getDate() + 7);
    setMonday(d);
  };
  const goToday = () => setMonday(getMonday(new Date()));

  const weekLabel = `${days[0].getDate()} ${TR_MONTHS[days[0].getMonth()]} – ${days[6].getDate()} ${TR_MONTHS[days[6].getMonth()]} ${days[6].getFullYear()}`;

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex items-center gap-3 flex-wrap">
        {/* Calendar selector */}
        <div className="flex items-center gap-2">
          <Calendar className="w-4 h-4 text-gray-400" />
          <select
            className="border border-gray-300 rounded-md px-3 py-1.5 text-sm text-gray-700 bg-white"
            value={selectedCalId ?? ""}
            onChange={(e) => setSelectedCalId(e.target.value || null)}
          >
            <option value="">Takvim seçin…</option>
            {calendars.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}{c.resource_name ? ` — ${c.resource_name}` : ""}
              </option>
            ))}
          </select>
        </div>

        {/* Week navigation */}
        <div className="flex items-center gap-1 ml-auto">
          <button
            onClick={goToday}
            className="px-3 py-1.5 text-xs font-medium border border-gray-300 rounded-md hover:bg-gray-50"
          >
            Bugün
          </button>
          <button
            onClick={prevWeek}
            className="p-1.5 border border-gray-300 rounded-md hover:bg-gray-50"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>
          <span className="px-3 text-sm font-medium text-gray-700 min-w-[200px] text-center">
            {weekLabel}
          </span>
          <button
            onClick={nextWeek}
            className="p-1.5 border border-gray-300 rounded-md hover:bg-gray-50"
          >
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Legend */}
      <div className="flex items-center gap-4 text-xs text-gray-500">
        {(["booked", "break", "blocked", "buffer"] as const).map((t) => (
          <span key={t} className="flex items-center gap-1.5">
            <span className={`inline-block w-3 h-3 rounded-sm ${blockClasses(t)}`} />
            {t === "booked" ? "Randevu" : t === "break" ? "Mola" : t === "blocked" ? "Blok" : "Tampon"}
          </span>
        ))}
        {selectedCal?.color && (
          <span className="flex items-center gap-1.5 ml-auto">
            <span
              className="inline-block w-3 h-3 rounded-full"
              style={{ backgroundColor: selectedCal.color }}
            />
            {selectedCal.name}
          </span>
        )}
      </div>

      {!selectedCalId ? (
        <div className="bg-white rounded-xl border border-gray-200 flex items-center justify-center h-64 text-gray-400 text-sm">
          Görüntülemek için bir takvim seçin.
        </div>
      ) : (
        <div className="bg-white rounded-xl border border-gray-200 overflow-auto">
          {isLoading && (
            <div className="absolute inset-0 flex items-center justify-center bg-white/70 z-20 rounded-xl">
              <p className="text-gray-400 text-sm">Yükleniyor…</p>
            </div>
          )}
          <div className="flex min-w-[640px]">
            {/* Time column */}
            <div className="flex flex-col">
              {/* Header spacer */}
              <div className="h-12 w-14 shrink-0 border-b border-gray-100" />
              <TimeColumn />
            </div>

            {/* Day columns */}
            {days.map((date, i) => {
              const isToday = toISO(date) === todayStr;
              return (
                <div key={i} className="flex-1 min-w-0 flex flex-col border-l border-gray-100">
                  {/* Day header */}
                  <div
                    className={`h-12 flex flex-col items-center justify-center border-b border-gray-100 shrink-0 ${
                      isToday ? "bg-indigo-50" : ""
                    }`}
                  >
                    <span className="text-[11px] text-gray-400 uppercase tracking-wide">
                      {TR_DAYS[i]}
                    </span>
                    <span
                      className={`text-sm font-semibold leading-tight ${
                        isToday
                          ? "w-6 h-6 bg-indigo-600 text-white rounded-full flex items-center justify-center text-xs"
                          : "text-gray-700"
                      }`}
                    >
                      {date.getDate()}
                    </span>
                  </div>

                  {/* Blocks */}
                  <div className="relative flex-1">
                    <DayColumn date={date} blocks={blocks} isToday={isToday} />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

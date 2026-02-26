"use client";

import { useState } from "react";
import { Trash2 } from "lucide-react";
import type { CalendarResource } from "@/lib/types";

export const DAYS = [
  { key: "monday", label: "Pzt" },
  { key: "tuesday", label: "Sal" },
  { key: "wednesday", label: "Çar" },
  { key: "thursday", label: "Per" },
  { key: "friday", label: "Cum" },
  { key: "saturday", label: "Cmt" },
  { key: "sunday", label: "Paz" },
];

export type WorkingDay = { open: boolean; slots: { start: string; end: string }[] };
export type WorkingHours = Record<string, WorkingDay>;

export const DEFAULT_WH: WorkingHours = Object.fromEntries(
  DAYS.map(({ key }) => [
    key,
    key === "sunday"
      ? { open: false, slots: [] }
      : { open: true, slots: [{ start: "09:00", end: "20:00" }] },
  ])
);

interface Props {
  mode: "create" | "edit";
  initial?: CalendarResource;
  onClose: () => void;
  onSubmit: (p: {
    name: string;
    resource_type?: string;
    resource_name?: string | null;
    calendar_type?: string;
    color?: string | null;
    timezone?: string | null;
    working_hours?: Record<string, unknown>;
    service_durations?: Record<string, unknown>;
  }) => void;
  isPending: boolean;
  error?: string;
}

export function CalendarFormModal({ mode, initial, onClose, onSubmit, isPending, error }: Props) {
  const [name, setName] = useState(initial?.name ?? "");
  const [resourceName, setResourceName] = useState(initial?.resource_name ?? "");
  const [resourceType, setResourceType] = useState(initial?.resource_type ?? "artist");
  const [calendarType, setCalendarType] = useState(initial?.calendar_type ?? "internal");
  const [color, setColor] = useState(initial?.color ?? "#6366F1");
  const [timezone, setTimezone] = useState(initial?.timezone ?? "Europe/Istanbul");
  const [wh, setWh] = useState<WorkingHours>(() => {
    const existing = (initial?.working_hours ?? {}) as WorkingHours;
    return Object.keys(existing).length > 0 ? existing : DEFAULT_WH;
  });
  const [durations, setDurations] = useState<Record<string, string>>(() => {
    const d = (initial?.service_durations ?? {}) as Record<string, unknown>;
    return Object.fromEntries(Object.entries(d).map(([k, v]) => [k, String(v)]));
  });
  const [newDurKey, setNewDurKey] = useState("");
  const [newDurVal, setNewDurVal] = useState("60");

  const updateDay = (dayKey: string, patch: Partial<WorkingDay>) =>
    setWh((prev) => ({ ...prev, [dayKey]: { ...prev[dayKey], ...patch } }));

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 overflow-y-auto py-8">
      <div className="bg-white rounded-xl shadow-xl p-6 w-full max-w-2xl mx-4">
        <h2 className="font-bold text-lg mb-4">
          {mode === "create" ? "Takvim Ekle" : "Takvim Düzenle"}
        </h2>

        <div className="grid grid-cols-2 gap-3 mb-4">
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">Ad</label>
            <input
              className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">
              Kaynak Adı (bot eşleşme)
            </label>
            <input
              className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm"
              value={resourceName}
              onChange={(e) => setResourceName(e.target.value)}
              placeholder="ör: İzel"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">Kaynak Türü</label>
            <select
              className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm"
              value={resourceType}
              onChange={(e) => setResourceType(e.target.value)}
            >
              <option value="artist">Sanatçı</option>
              <option value="room">Oda</option>
              <option value="equipment">Ekipman</option>
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">Takvim Tipi</label>
            <select
              className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm"
              value={calendarType}
              onChange={(e) => setCalendarType(e.target.value)}
            >
              <option value="internal">Dahili</option>
              <option value="google">Google Calendar</option>
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">Renk</label>
            <input
              type="color"
              className="w-12 h-8 rounded border border-gray-300 cursor-pointer"
              value={color}
              onChange={(e) => setColor(e.target.value)}
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">Saat Dilimi</label>
            <input
              className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm"
              value={timezone}
              onChange={(e) => setTimezone(e.target.value)}
            />
          </div>
        </div>

        {/* Working Hours */}
        <div className="mb-4">
          <h3 className="text-sm font-semibold text-gray-700 mb-2">Çalışma Saatleri</h3>
          <div className="space-y-1.5">
            {DAYS.map(({ key, label }) => {
              const day = wh[key] || { open: false, slots: [] };
              return (
                <div key={key} className="flex items-center gap-3 text-sm">
                  <label className="flex items-center gap-1.5 w-16 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={day.open}
                      onChange={(e) =>
                        updateDay(key, {
                          open: e.target.checked,
                          slots:
                            e.target.checked && day.slots.length === 0
                              ? [{ start: "09:00", end: "20:00" }]
                              : day.slots,
                        })
                      }
                      className="rounded"
                    />
                    <span className={day.open ? "text-gray-800 font-medium" : "text-gray-400"}>
                      {label}
                    </span>
                  </label>
                  {day.open && day.slots.length > 0 ? (
                    <div className="flex items-center gap-1.5">
                      <input
                        type="time"
                        className="border border-gray-300 rounded px-2 py-1 text-sm"
                        value={day.slots[0].start}
                        onChange={(e) =>
                          updateDay(key, { slots: [{ ...day.slots[0], start: e.target.value }] })
                        }
                      />
                      <span className="text-gray-400">–</span>
                      <input
                        type="time"
                        className="border border-gray-300 rounded px-2 py-1 text-sm"
                        value={day.slots[0].end}
                        onChange={(e) =>
                          updateDay(key, { slots: [{ ...day.slots[0], end: e.target.value }] })
                        }
                      />
                    </div>
                  ) : day.open ? null : (
                    <span className="text-gray-400 text-xs">Kapalı</span>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* Service Durations */}
        <div className="mb-4">
          <h3 className="text-sm font-semibold text-gray-700 mb-2">
            Hizmet Süreleri (dakika)
          </h3>
          <div className="space-y-1.5">
            {Object.entries(durations).map(([k, v]) => (
              <div key={k} className="flex items-center gap-2">
                <span className="text-sm text-gray-700 w-40 truncate">{k}</span>
                <input
                  type="number"
                  className="w-20 border border-gray-300 rounded px-2 py-1 text-sm"
                  value={v}
                  onChange={(e) => setDurations((prev) => ({ ...prev, [k]: e.target.value }))}
                />
                <button
                  onClick={() =>
                    setDurations((prev) => {
                      const n = { ...prev };
                      delete n[k];
                      return n;
                    })
                  }
                  className="text-red-400 hover:text-red-600"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            ))}
            <div className="flex items-center gap-2 mt-1">
              <input
                placeholder="Hizmet adı"
                className="w-40 border border-gray-300 rounded px-2 py-1 text-sm"
                value={newDurKey}
                onChange={(e) => setNewDurKey(e.target.value)}
              />
              <input
                type="number"
                placeholder="dk"
                className="w-20 border border-gray-300 rounded px-2 py-1 text-sm"
                value={newDurVal}
                onChange={(e) => setNewDurVal(e.target.value)}
              />
              <button
                onClick={() => {
                  if (newDurKey.trim()) {
                    setDurations((p) => ({ ...p, [newDurKey.trim()]: newDurVal || "60" }));
                    setNewDurKey("");
                    setNewDurVal("60");
                  }
                }}
                className="text-indigo-600 text-xs font-medium hover:underline"
              >
                + Ekle
              </button>
            </div>
          </div>
        </div>

        {error && <p className="text-red-600 text-sm mb-2">{error}</p>}
        <div className="flex gap-3">
          <button
            disabled={!name.trim() || isPending}
            onClick={() => {
              const serviceDurations = Object.fromEntries(
                Object.entries(durations).map(([k, v]) => [k, parseInt(v) || 60])
              );
              onSubmit({
                name,
                resource_name: resourceName || null,
                resource_type: resourceType,
                calendar_type: calendarType,
                color,
                timezone,
                working_hours: wh,
                service_durations: serviceDurations,
              });
            }}
            className="bg-indigo-600 text-white px-4 py-2 rounded-md text-sm hover:bg-indigo-700 disabled:opacity-50"
          >
            {isPending ? "Kaydediliyor…" : "Kaydet"}
          </button>
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-md text-sm border border-gray-300 hover:bg-gray-50"
          >
            İptal
          </button>
        </div>
      </div>
    </div>
  );
}

"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { calendarsApi } from "@/lib/api";
import type { CalendarBlock, CalendarResource } from "@/lib/types";
import { Clock, Trash2, X, AlertCircle } from "lucide-react";

interface Props {
  calendar: CalendarResource;
  onClose: () => void;
}

export function CalendarDetailModal({ calendar, onClose }: Props) {
  const qc = useQueryClient();
  const today = new Date().toISOString().slice(0, 10);
  const [selectedDate, setSelectedDate] = useState(today);

  const blocksQuery = useQuery({
    queryKey: ["calendar-blocks", calendar.id, selectedDate],
    queryFn: () => calendarsApi.listBlocks(calendar.id, { date: selectedDate }),
  });

  const availabilityQuery = useQuery({
    queryKey: ["calendar-availability", calendar.id, selectedDate],
    queryFn: () => calendarsApi.getAvailability(calendar.id, selectedDate),
  });

  const _invalidateAll = () => {
    qc.invalidateQueries({ queryKey: ["calendar-blocks", calendar.id, selectedDate] });
    qc.invalidateQueries({ queryKey: ["calendar-blocks-week"] });
    qc.invalidateQueries({ queryKey: ["calendar-availability", calendar.id, selectedDate] });
    qc.invalidateQueries({ queryKey: ["calendar-availability"] });
  };

  const createBlockMutation = useMutation({
    mutationFn: (p: { start_time: string; end_time: string; block_type: string; label?: string }) =>
      calendarsApi.createBlock(calendar.id, { date: selectedDate, ...p }),
    onSuccess: _invalidateAll,
  });

  const deleteBlockMutation = useMutation({
    mutationFn: (blockId: string) => calendarsApi.deleteBlock(calendar.id, blockId),
    onSuccess: _invalidateAll,
    onError: () => {
      // Block may have been deleted already (e.g. when its linked appointment was removed).
      // Refresh the list so stale entries disappear.
      _invalidateAll();
    },
  });

  const deleteBlockError = deleteBlockMutation.error
    ? (deleteBlockMutation.error as Error).message.includes("404")
      ? "Bu blok zaten silinmiş."
      : "Blok silinemedi."
    : null;

  const [newBlockStart, setNewBlockStart] = useState("12:00");
  const [newBlockEnd, setNewBlockEnd] = useState("13:00");
  const [newBlockType, setNewBlockType] = useState("blocked");
  const [newBlockLabel, setNewBlockLabel] = useState("");

  const blocks = blocksQuery.data ?? [];
  const slots = availabilityQuery.data?.available_slots ?? [];

  const BLOCK_STYLE: Record<string, string> = {
    booked: "bg-blue-100 text-blue-700",
    break: "bg-yellow-100 text-yellow-700",
    blocked: "bg-red-100 text-red-700",
    buffer: "bg-gray-100 text-gray-600",
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 overflow-y-auto py-8">
      <div className="bg-white rounded-xl shadow-xl p-6 w-full max-w-2xl mx-4">
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="font-bold text-lg">{calendar.name}</h2>
            <p className="text-sm text-gray-500">
              {calendar.resource_name} · {calendar.calendar_type}
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 text-gray-400 hover:text-gray-600 rounded-md hover:bg-gray-100"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Date picker */}
        <div className="flex items-center gap-3 mb-4">
          <label className="text-sm text-gray-600">Tarih:</label>
          <input
            type="date"
            className="border border-gray-300 rounded-md px-3 py-1.5 text-sm"
            value={selectedDate}
            onChange={(e) => setSelectedDate(e.target.value)}
          />
        </div>

        {/* Available slots */}
        <div className="mb-5">
          <h3 className="text-sm font-semibold text-gray-700 mb-2 flex items-center gap-1.5">
            <Clock className="w-4 h-4" /> Müsait Saatler
          </h3>
          {availabilityQuery.isLoading ? (
            <p className="text-gray-400 text-sm">Yükleniyor…</p>
          ) : slots.length === 0 ? (
            <p className="text-gray-400 text-sm">Bu tarihte müsait saat yok.</p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {slots.map((s) => (
                <span
                  key={s}
                  className="px-3 py-1.5 bg-green-50 text-green-700 rounded-lg text-sm font-medium border border-green-200"
                >
                  {s}
                </span>
              ))}
            </div>
          )}
        </div>

        {/* Existing blocks */}
        <div className="mb-5">
          <h3 className="text-sm font-semibold text-gray-700 mb-2">Bloklar</h3>
          {deleteBlockError && (
            <div className="flex items-center gap-1.5 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-md px-3 py-1.5 mb-2">
              <AlertCircle className="w-3.5 h-3.5 shrink-0" />
              {deleteBlockError}
            </div>
          )}
          {blocksQuery.isLoading ? (
            <p className="text-gray-400 text-sm">Yükleniyor…</p>
          ) : blocks.length === 0 ? (
            <p className="text-gray-400 text-sm">Bu tarihte blok yok.</p>
          ) : (
            <div className="space-y-1.5">
              {blocks.map((b: CalendarBlock) => (
                <div
                  key={b.id}
                  className="flex items-center justify-between bg-gray-50 rounded-lg px-3 py-2 text-sm"
                >
                  <div className="flex items-center flex-wrap gap-1.5">
                    <span className="font-mono text-gray-700">
                      {b.start_time}–{b.end_time}
                    </span>
                    <span
                      className={`px-1.5 py-0.5 rounded text-xs font-medium ${
                        BLOCK_STYLE[b.block_type] ?? "bg-gray-100 text-gray-600"
                      }`}
                    >
                      {b.block_type}
                    </span>
                    {b.appointment_id && (
                      <span className="px-1.5 py-0.5 rounded text-xs font-medium bg-indigo-50 text-indigo-600 border border-indigo-200">
                        randevu
                      </span>
                    )}
                    {b.label && <span className="text-gray-500 text-xs">{b.label}</span>}
                  </div>
                  <button
                    onClick={() => deleteBlockMutation.mutate(b.id)}
                    className="text-red-400 hover:text-red-600"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Add block */}
        <div className="border-t pt-4">
          <h3 className="text-sm font-semibold text-gray-700 mb-2">Blok Ekle</h3>
          <div className="flex items-end gap-2 flex-wrap">
            <div>
              <label className="block text-xs text-gray-500 mb-0.5">Başlangıç</label>
              <input
                type="time"
                className="border border-gray-300 rounded px-2 py-1.5 text-sm"
                value={newBlockStart}
                onChange={(e) => setNewBlockStart(e.target.value)}
              />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-0.5">Bitiş</label>
              <input
                type="time"
                className="border border-gray-300 rounded px-2 py-1.5 text-sm"
                value={newBlockEnd}
                onChange={(e) => setNewBlockEnd(e.target.value)}
              />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-0.5">Tür</label>
              <select
                className="border border-gray-300 rounded px-2 py-1.5 text-sm"
                value={newBlockType}
                onChange={(e) => setNewBlockType(e.target.value)}
              >
                <option value="blocked">Blok</option>
                <option value="break">Mola</option>
                <option value="buffer">Tampon</option>
              </select>
            </div>
            <div className="flex-1 min-w-[120px]">
              <label className="block text-xs text-gray-500 mb-0.5">Etiket</label>
              <input
                className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm"
                value={newBlockLabel}
                onChange={(e) => setNewBlockLabel(e.target.value)}
                placeholder="ör: Öğle arası"
              />
            </div>
            <button
              disabled={createBlockMutation.isPending}
              onClick={() =>
                createBlockMutation.mutate({
                  start_time: newBlockStart,
                  end_time: newBlockEnd,
                  block_type: newBlockType,
                  label: newBlockLabel || undefined,
                })
              }
              className="bg-indigo-600 text-white px-3 py-1.5 rounded-md text-sm hover:bg-indigo-700 disabled:opacity-50"
            >
              Ekle
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

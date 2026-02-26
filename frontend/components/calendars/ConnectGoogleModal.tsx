"use client";

import { useState } from "react";

interface Props {
  calendarId: string;
  onClose: () => void;
  onSubmit: (calendar_id: string, credentials_json?: string) => void;
  isPending: boolean;
  error?: string;
}

export function ConnectGoogleModal({ onClose, onSubmit, isPending, error }: Props) {
  const [calendarIdInput, setCalendarIdInput] = useState("primary");
  const [credentials, setCredentials] = useState("");

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl shadow-xl p-6 w-full max-w-lg">
        <h2 className="font-bold text-lg mb-1">Google Calendar Bağla</h2>
        <p className="text-sm text-gray-500 mb-4">
          Google Calendar ID girin. Opsiyonel olarak kaynak için service account JSON
          yapıştırabilirsiniz.
        </p>
        <div className="space-y-3">
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">Calendar ID</label>
            <input
              className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm font-mono"
              value={calendarIdInput}
              onChange={(e) => setCalendarIdInput(e.target.value)}
              placeholder="primary veya email@example.com"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">
              Credentials JSON (opsiyonel)
            </label>
            <textarea
              className="w-full h-32 border border-gray-300 rounded-md px-3 py-2 text-xs font-mono"
              value={credentials}
              onChange={(e) => setCredentials(e.target.value)}
              placeholder='{"type": "service_account", ...}'
            />
          </div>
        </div>
        {error && <p className="text-red-600 text-sm mt-2">{error}</p>}
        <div className="flex gap-3 mt-6">
          <button
            onClick={() =>
              onSubmit(calendarIdInput.trim() || "primary", credentials.trim() || undefined)
            }
            disabled={!calendarIdInput.trim() || isPending}
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

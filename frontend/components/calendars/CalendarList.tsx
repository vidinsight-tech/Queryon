"use client";

import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { calendarsApi } from "@/lib/api";
import { Plus, CheckCircle, ExternalLink } from "lucide-react";
import { CalendarFormModal } from "./CalendarFormModal";
import { CalendarDetailModal } from "./CalendarDetailModal";
import { ConnectGoogleModal } from "./ConnectGoogleModal";

const GOOGLE_ICON = (
  <svg viewBox="0 0 24 24" width="16" height="16" className="inline-block">
    <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="#4285F4" />
    <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853" />
    <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05" />
    <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335" />
  </svg>
);

export function CalendarList() {
  const qc = useQueryClient();
  const [showAdd, setShowAdd] = useState(false);
  const [connectId, setConnectId] = useState<string | null>(null);
  const [editId, setEditId] = useState<string | null>(null);
  const [detailId, setDetailId] = useState<string | null>(null);
  const [oauthLoading, setOauthLoading] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Handle Google OAuth callback redirect
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const connected = params.get("connected");
    const error = params.get("error");
    if (connected) {
      setSuccessMsg("Google Calendar başarıyla bağlandı!");
      qc.invalidateQueries({ queryKey: ["calendars"] });
      window.history.replaceState({}, "", window.location.pathname);
      setTimeout(() => setSuccessMsg(null), 5000);
    }
    if (error) {
      setSuccessMsg(null);
      window.history.replaceState({}, "", window.location.pathname);
    }
  }, [qc]);

  const { data: calendars = [], isLoading } = useQuery({
    queryKey: ["calendars"],
    queryFn: () => calendarsApi.list(),
  });

  const createMutation = useMutation({
    mutationFn: (payload: Parameters<typeof calendarsApi.create>[0]) =>
      calendarsApi.create(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["calendars"] });
      setShowAdd(false);
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({
      id,
      payload,
    }: {
      id: string;
      payload: Parameters<typeof calendarsApi.update>[1];
    }) => calendarsApi.update(id, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["calendars"] });
      setEditId(null);
    },
  });

  const connectMutation = useMutation({
    mutationFn: ({
      id,
      calendar_id,
      credentials_json,
    }: {
      id: string;
      calendar_id: string;
      credentials_json?: string;
    }) =>
      calendarsApi.connectGoogle(id, {
        calendar_id,
        credentials_json: credentials_json || undefined,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["calendars"] });
      setConnectId(null);
    },
  });

  const testMutation = useMutation({
    mutationFn: (id: string) => calendarsApi.testConnection(id),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => calendarsApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["calendars"] }),
  });

  const handleGoogleOAuth = async (calendarResourceId: string) => {
    setOauthLoading(calendarResourceId);
    try {
      const { url } = await calendarsApi.getGoogleAuthUrl(calendarResourceId);
      window.location.href = url;
    } catch {
      alert(
        "Google OAuth başlatılamadı. GOOGLE_CLIENT_ID ve GOOGLE_CLIENT_SECRET env var'ları ayarlı mı?"
      );
      setOauthLoading(null);
    }
  };

  if (isLoading) return <p className="text-gray-400">Loading calendars…</p>;

  const editCal = editId ? calendars.find((c) => c.id === editId) : null;
  const detailCal = detailId ? calendars.find((c) => c.id === detailId) : null;

  return (
    <div className="space-y-4">
      {successMsg && (
        <div className="bg-green-50 border border-green-200 text-green-700 rounded-lg px-4 py-3 text-sm flex items-center gap-2">
          <CheckCircle className="w-4 h-4" /> {successMsg}
        </div>
      )}

      <div className="flex justify-end">
        <button
          onClick={() => setShowAdd(true)}
          className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white text-sm font-medium rounded-lg hover:bg-indigo-700"
        >
          <Plus className="w-4 h-4" /> Takvim Ekle
        </button>
      </div>

      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        {calendars.length === 0 ? (
          <p className="text-gray-500 p-6 text-sm">Henüz takvim eklenmedi.</p>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-xs uppercase text-gray-500">
              <tr>
                <th className="px-4 py-3 text-left">Ad</th>
                <th className="px-4 py-3 text-left">Kaynak</th>
                <th className="px-4 py-3 text-left">Tip</th>
                <th className="px-4 py-3 text-center">Google</th>
                <th className="px-4 py-3 text-right">İşlemler</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {calendars.map((cal) => (
                <tr key={cal.id} className="hover:bg-gray-50">
                  <td
                    className="px-4 py-3 font-medium text-gray-900 cursor-pointer"
                    onClick={() => setDetailId(cal.id)}
                  >
                    {cal.color && (
                      <span
                        className="inline-block w-2.5 h-2.5 rounded-full mr-2"
                        style={{ backgroundColor: cal.color }}
                      />
                    )}
                    {cal.name}
                  </td>
                  <td className="px-4 py-3 text-gray-600">{cal.resource_name ?? "—"}</td>
                  <td className="px-4 py-3 text-gray-600">{cal.calendar_type}</td>
                  <td className="px-4 py-3 text-center">
                    {cal.calendar_type === "google" ? (
                      cal.has_credentials || cal.calendar_id ? (
                        <CheckCircle className="w-4 h-4 text-green-500 inline" />
                      ) : (
                        <span className="text-amber-600 text-xs">Bağlantı Gerekli</span>
                      )
                    ) : (
                      <span className="text-gray-300">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex items-center justify-end gap-1.5">
                      <button
                        onClick={() => setDetailId(cal.id)}
                        className="text-indigo-600 hover:underline text-xs"
                      >
                        Detay
                      </button>
                      <button
                        onClick={() => setEditId(cal.id)}
                        className="text-indigo-600 hover:underline text-xs"
                      >
                        Düzenle
                      </button>
                      {cal.calendar_type === "google" && (
                        <button
                          onClick={() => testMutation.mutate(cal.id)}
                          disabled={testMutation.isPending}
                          className="text-indigo-600 hover:underline text-xs disabled:opacity-50"
                        >
                          {testMutation.isPending ? "Test…" : "Test"}
                        </button>
                      )}

                      {/* Google OAuth */}
                      <button
                        onClick={() => handleGoogleOAuth(cal.id)}
                        disabled={oauthLoading === cal.id}
                        className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-white border border-gray-300 rounded-md text-xs font-medium text-gray-700 hover:bg-gray-50 hover:border-gray-400 transition-colors disabled:opacity-50 shadow-sm"
                      >
                        {GOOGLE_ICON}
                        {oauthLoading === cal.id
                          ? "Yönlendiriliyor…"
                          : cal.calendar_type === "google" && cal.has_credentials
                          ? "Yeniden Bağla"
                          : "Google ile Bağlan"}
                      </button>

                      {/* Manual service account */}
                      <button
                        onClick={() => setConnectId(cal.id)}
                        className="text-gray-400 hover:text-gray-600 text-xs"
                        title="Service Account ile manuel bağla"
                      >
                        <ExternalLink className="w-3.5 h-3.5 inline" />
                      </button>

                      <button
                        onClick={() => deleteMutation.mutate(cal.id)}
                        className="text-red-600 hover:underline text-xs"
                      >
                        Sil
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {testMutation.data && (
        <p className="text-sm text-green-600">{testMutation.data.message}</p>
      )}
      {testMutation.error && (
        <p className="text-sm text-red-600">Test başarısız: {String(testMutation.error)}</p>
      )}

      {/* Modals */}
      {showAdd && (
        <CalendarFormModal
          mode="create"
          onClose={() => setShowAdd(false)}
          onSubmit={(p) => createMutation.mutate(p)}
          isPending={createMutation.isPending}
          error={createMutation.error?.message}
        />
      )}
      {editCal && (
        <CalendarFormModal
          mode="edit"
          initial={editCal}
          onClose={() => setEditId(null)}
          onSubmit={(p) => updateMutation.mutate({ id: editCal.id, payload: p })}
          isPending={updateMutation.isPending}
          error={updateMutation.error?.message}
        />
      )}
      {connectId && (
        <ConnectGoogleModal
          calendarId={connectId}
          onClose={() => setConnectId(null)}
          onSubmit={(cid, creds) =>
            connectMutation.mutate({ id: connectId, calendar_id: cid, credentials_json: creds })
          }
          isPending={connectMutation.isPending}
          error={connectMutation.error?.message}
        />
      )}
      {detailCal && (
        <CalendarDetailModal calendar={detailCal} onClose={() => setDetailId(null)} />
      )}
    </div>
  );
}

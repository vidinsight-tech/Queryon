"use client";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { toolsApi } from "@/lib/api";
import type { Tool } from "@/lib/types";
import { Wrench, CalendarCheck, Globe, Database, Clock, Plus, Trash2, X, Play, CheckCircle, AlertCircle } from "lucide-react";
import { Toggle } from "@/components/ui/Toggle";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { WebhookToolForm } from "./WebhookToolForm";

const TOOL_ICONS: Record<string, React.ElementType> = {
  get_current_time: Clock,
  get_current_date: Clock,
  http_request: Globe,
  search_knowledge_base: Database,
  check_calendar_availability: CalendarCheck,
  create_calendar_event: CalendarCheck,
  list_calendar_events: CalendarCheck,
};

interface TestResult {
  ok: boolean;
  result?: Record<string, unknown>;
  error?: string;
}

function WebhookTestModal({
  tool,
  onClose,
}: {
  tool: Tool;
  onClose: () => void;
}) {
  const [payload, setPayload] = useState("{}");
  const [jsonError, setJsonError] = useState<string | null>(null);
  const [result, setResult] = useState<TestResult | null>(null);
  const [isPending, setIsPending] = useState(false);

  const handleTest = async () => {
    let kwargs: Record<string, unknown> = {};
    try {
      kwargs = JSON.parse(payload);
      setJsonError(null);
    } catch {
      setJsonError("Geçersiz JSON");
      return;
    }
    setIsPending(true);
    setResult(null);
    try {
      const res = await toolsApi.test(tool.name, kwargs);
      setResult(res);
    } catch (e) {
      setResult({ ok: false, error: String(e) });
    } finally {
      setIsPending(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl shadow-xl p-6 w-full max-w-lg">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="font-bold text-lg">Test: <span className="font-mono text-indigo-600">{tool.name}</span></h2>
            <p className="text-sm text-gray-500 mt-0.5">{tool.description}</p>
          </div>
          <button onClick={onClose} className="p-1.5 text-gray-400 hover:text-gray-600 rounded-md hover:bg-gray-100">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="mb-4">
          <label className="block text-xs font-medium text-gray-500 mb-1">
            Parametreler (JSON)
          </label>
          <textarea
            className={`w-full h-28 border rounded-md px-3 py-2 text-xs font-mono ${
              jsonError ? "border-red-400" : "border-gray-300"
            }`}
            value={payload}
            onChange={(e) => { setPayload(e.target.value); setJsonError(null); }}
            placeholder='{"key": "value"}'
          />
          {jsonError && <p className="text-red-500 text-xs mt-1">{jsonError}</p>}
        </div>

        <button
          onClick={handleTest}
          disabled={isPending}
          className="flex items-center gap-2 bg-indigo-600 text-white px-4 py-2 rounded-md text-sm hover:bg-indigo-700 disabled:opacity-50"
        >
          <Play className="w-3.5 h-3.5" />
          {isPending ? "Çalışıyor…" : "Çalıştır"}
        </button>

        {result && (
          <div className={`mt-4 rounded-lg p-3 text-sm ${result.ok ? "bg-green-50 border border-green-200" : "bg-red-50 border border-red-200"}`}>
            <div className="flex items-center gap-1.5 font-semibold mb-2">
              {result.ok
                ? <><CheckCircle className="w-4 h-4 text-green-600" /><span className="text-green-700">Başarılı</span></>
                : <><AlertCircle className="w-4 h-4 text-red-500" /><span className="text-red-700">Hata</span></>}
            </div>
            <pre className="text-xs font-mono overflow-auto max-h-48 whitespace-pre-wrap text-gray-700">
              {result.ok
                ? JSON.stringify(result.result, null, 2)
                : result.error}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
}

function GoogleCalendarModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const [credentials, setCredentials] = useState("");
  const mutation = useMutation({
    mutationFn: () => toolsApi.configureGoogleCalendar(credentials),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["tools"] });
      toast.success("Google Calendar yapılandırıldı.");
      onClose();
    },
    onError: () => toast.error("Yapılandırma kaydedilemedi."),
  });
  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl shadow-xl p-6 w-full max-w-lg">
        <h2 className="font-bold text-lg mb-1">Google Calendar Yapılandır</h2>
        <p className="text-sm text-gray-500 mb-4">
          Servis hesabı JSON kimlik bilgilerini yapıştırın.
        </p>
        <textarea
          className="w-full h-48 border border-gray-300 rounded-md p-3 text-xs font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500"
          placeholder='{"type": "service_account", ...}'
          value={credentials}
          onChange={(e) => setCredentials(e.target.value)}
        />
        <div className="flex gap-3 mt-4">
          <button
            onClick={() => mutation.mutate()}
            disabled={!credentials || mutation.isPending}
            className="bg-indigo-600 text-white px-4 py-2 rounded-md text-sm hover:bg-indigo-700 disabled:opacity-50"
          >
            {mutation.isPending ? "Kaydediliyor…" : "Kaydet"}
          </button>
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-md text-sm border border-gray-300 hover:bg-gray-50"
          >
            Vazgeç
          </button>
        </div>
      </div>
    </div>
  );
}

export function ToolList() {
  const qc = useQueryClient();
  const [showCalModal, setShowCalModal] = useState(false);
  const [showWebhookForm, setShowWebhookForm] = useState(false);
  const [editWebhook, setEditWebhook] = useState<Tool | null>(null);
  const [testTool, setTestTool] = useState<Tool | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);

  const { data: tools = [], isLoading } = useQuery({
    queryKey: ["tools"],
    queryFn: toolsApi.list,
  });

  const toggleMutation = useMutation({
    mutationFn: ({ name, enabled }: { name: string; enabled: boolean }) =>
      toolsApi.patch(name, { enabled }),
    onSuccess: (_, { enabled }) => {
      qc.invalidateQueries({ queryKey: ["tools"] });
      toast.success(enabled ? "Araç etkinleştirildi." : "Araç devre dışı bırakıldı.");
    },
    onError: () => toast.error("Durum güncellenemedi."),
  });

  const deleteMutation = useMutation({
    mutationFn: (name: string) => toolsApi.delete(name),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["tools"] });
      setDeleteTarget(null);
      toast.success("Araç silindi.");
    },
    onError: () => toast.error("Araç silinemedi."),
  });

  if (isLoading) return <p className="text-gray-400 text-sm">Araçlar yükleniyor…</p>;

  const deleteTargetTool = tools.find((t: Tool) => t.name === deleteTarget);

  return (
    <div>
      <div className="flex justify-end mb-3">
        <button
          onClick={() => { setEditWebhook(null); setShowWebhookForm(true); }}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-indigo-600 text-white text-sm font-medium rounded-md hover:bg-indigo-700 transition-colors"
        >
          <Plus className="w-4 h-4" />
          Webhook Aracı Ekle
        </button>
      </div>
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-xs uppercase text-gray-500">
            <tr>
              <th className="px-4 py-3 text-left">Araç</th>
              <th className="px-4 py-3 text-left">Açıklama</th>
              <th className="px-4 py-3 text-center">Tür</th>
              <th className="px-4 py-3 text-center">Aktif</th>
              <th className="px-4 py-3 text-right">İşlem</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {tools.map((tool: Tool) => {
              const Icon = TOOL_ICONS[tool.name] ?? Wrench;
              const isCalTool = tool.name.includes("calendar");
              return (
                <tr key={tool.name} className="hover:bg-gray-50">
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <Icon className="w-4 h-4 text-gray-400" />
                      <span className="font-mono text-xs text-gray-700">{tool.name}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-gray-600 max-w-xs truncate">{tool.description}</td>
                  <td className="px-4 py-3 text-center">
                    <span
                      className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${
                        tool.is_builtin
                          ? "bg-indigo-50 text-indigo-700"
                          : "bg-gray-100 text-gray-600"
                      }`}
                    >
                      {tool.is_builtin ? "yerleşik" : "özel"}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-center">
                    <div className="flex justify-center">
                      <Toggle
                        checked={tool.enabled}
                        onCheckedChange={(val) =>
                          toggleMutation.mutate({ name: tool.name, enabled: val })
                        }
                      />
                    </div>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex items-center justify-end gap-2">
                      {isCalTool && (
                        <button
                          onClick={() => setShowCalModal(true)}
                          className="text-xs text-indigo-600 hover:underline"
                        >
                          OAuth Yapılandır
                        </button>
                      )}
                      {!tool.is_builtin && (
                        <>
                          <button
                            onClick={() => setTestTool(tool)}
                            className="text-xs text-emerald-600 hover:underline"
                          >
                            Test
                          </button>
                          <button
                            onClick={() => { setEditWebhook(tool); setShowWebhookForm(true); }}
                            className="text-xs text-indigo-600 hover:underline"
                          >
                            Düzenle
                          </button>
                          <button
                            onClick={() => setDeleteTarget(tool.name)}
                            className="text-gray-400 hover:text-red-500 transition-colors"
                            title="Sil"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <ConfirmDialog
        open={deleteTarget != null}
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => deleteTarget && deleteMutation.mutate(deleteTarget)}
        loading={deleteMutation.isPending}
        title="Aracı Sil"
        description={`"${deleteTargetTool?.name ?? deleteTarget}" aracı kalıcı olarak silinecek.`}
        confirmLabel="Evet, sil"
      />

      {showCalModal && <GoogleCalendarModal onClose={() => setShowCalModal(false)} />}
      {showWebhookForm && (
        <WebhookToolForm
          existing={editWebhook ?? undefined}
          onClose={() => { setShowWebhookForm(false); setEditWebhook(null); }}
        />
      )}
      {testTool && (
        <WebhookTestModal tool={testTool} onClose={() => setTestTool(null)} />
      )}
    </div>
  );
}

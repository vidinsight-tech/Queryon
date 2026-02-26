"use client";
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { toolsApi } from "@/lib/api";
import type { Tool, WebhookCreatePayload, WebhookUpdatePayload } from "@/lib/types";
import { X } from "lucide-react";

type Method = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

interface Props {
  /** When provided, the form is in edit mode for this tool */
  existing?: Tool;
  onClose: () => void;
}

function parseJson(raw: string): { ok: true; value: Record<string, unknown> } | { ok: false; error: string } {
  if (!raw.trim()) return { ok: true, value: {} };
  try {
    const parsed = JSON.parse(raw);
    if (typeof parsed !== "object" || Array.isArray(parsed) || parsed === null) {
      return { ok: false, error: "Must be a JSON object" };
    }
    return { ok: true, value: parsed };
  } catch (e) {
    return { ok: false, error: "Invalid JSON" };
  }
}

export function WebhookToolForm({ existing, onClose }: Props) {
  const qc = useQueryClient();

  const [name, setName] = useState(existing?.name ?? "");
  const [description, setDescription] = useState(existing?.description ?? "");
  const [url, setUrl] = useState("");
  const [method, setMethod] = useState<Method>("POST");
  const [authToken, setAuthToken] = useState("");
  const [headersRaw, setHeadersRaw] = useState("");
  const [paramsRaw, setParamsRaw] = useState("");
  const [enabled, setEnabled] = useState(true);

  const [headersError, setHeadersError] = useState("");
  const [paramsError, setParamsError] = useState("");

  const isEdit = Boolean(existing);

  const createMutation = useMutation({
    mutationFn: (payload: WebhookCreatePayload) => toolsApi.createWebhook(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["tools"] });
      toast.success("Webhook aracı oluşturuldu.");
      onClose();
    },
    onError: () => toast.error("Webhook oluşturulamadı."),
  });

  const updateMutation = useMutation({
    mutationFn: (payload: WebhookUpdatePayload) => toolsApi.updateWebhook(existing!.name, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["tools"] });
      toast.success("Webhook aracı güncellendi.");
      onClose();
    },
    onError: () => toast.error("Webhook güncellenemedi."),
  });

  const isPending = createMutation.isPending || updateMutation.isPending;

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();

    const parsedHeaders = parseJson(headersRaw);
    const parsedParams = parseJson(paramsRaw);

    if (!parsedHeaders.ok) { setHeadersError(parsedHeaders.error); return; }
    if (!parsedParams.ok) { setParamsError(parsedParams.error); return; }
    setHeadersError("");
    setParamsError("");

    const headers = Object.keys(parsedHeaders.value).length > 0
      ? (parsedHeaders.value as Record<string, string>)
      : null;
    const parameters = Object.keys(parsedParams.value).length > 0 ? parsedParams.value : null;

    if (isEdit) {
      const payload: WebhookUpdatePayload = {
        description: description || undefined,
        url: url || undefined,
        method: url ? method : undefined,
        headers,
        auth_token: authToken || null,
        parameters,
        enabled,
      };
      updateMutation.mutate(payload);
    } else {
      const payload: WebhookCreatePayload = {
        name,
        description,
        url,
        method,
        headers,
        auth_token: authToken || null,
        parameters,
        enabled,
      };
      createMutation.mutate(payload);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between p-5 border-b border-gray-100">
          <h2 className="font-semibold text-base">
            {isEdit ? "Webhook Aracını Düzenle" : "Webhook Aracı Ekle"}
          </h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <X className="w-5 h-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-5 space-y-4">
          {/* Name */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">İsim</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              disabled={isEdit}
              required={!isEdit}
              placeholder="check_stock"
              pattern="[a-z][a-z0-9_]*"
              className="w-full text-sm border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:bg-gray-50 font-mono"
            />
            {!isEdit && (
              <p className="text-xs text-gray-400 mt-0.5">snake_case, örn: check_stock</p>
            )}
          </div>

          {/* Description */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Açıklama</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              required={!isEdit}
              rows={3}
              placeholder="Stok durumunu kontrol eder ve kullanıcıya bildirir."
              className="w-full text-sm border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-y"
            />
          </div>

          {/* URL + Method */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">URL</label>
            <div className="flex gap-2">
              <select
                value={method}
                onChange={(e) => setMethod(e.target.value as Method)}
                className="text-sm border border-gray-300 rounded-md px-2 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white"
              >
                {(["POST", "GET", "PUT", "PATCH", "DELETE"] as Method[]).map((m) => (
                  <option key={m} value={m}>{m}</option>
                ))}
              </select>
              <input
                type="url"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                required={!isEdit}
                placeholder="https://api.example.com/webhook"
                className="flex-1 text-sm border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>
          </div>

          {/* Auth Token */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Auth Token <span className="text-gray-400 font-normal">(opsiyonel)</span>
            </label>
            <input
              type="password"
              value={authToken}
              onChange={(e) => setAuthToken(e.target.value)}
              placeholder="Bearer token"
              className="w-full text-sm border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>

          {/* Headers JSON */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Headers JSON <span className="text-gray-400 font-normal">(opsiyonel)</span>
            </label>
            <textarea
              value={headersRaw}
              onChange={(e) => { setHeadersRaw(e.target.value); setHeadersError(""); }}
              rows={3}
              placeholder={'{"X-Custom-Header": "value"}'}
              className={`w-full text-xs font-mono border rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-y ${
                headersError ? "border-red-400" : "border-gray-300"
              }`}
            />
            {headersError && <p className="text-xs text-red-500 mt-0.5">{headersError}</p>}
          </div>

          {/* Parameters JSON Schema */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Parameters JSON Schema <span className="text-gray-400 font-normal">(opsiyonel)</span>
            </label>
            <textarea
              value={paramsRaw}
              onChange={(e) => { setParamsRaw(e.target.value); setParamsError(""); }}
              rows={4}
              placeholder={'{"type":"object","properties":{"product_id":{"type":"string"}},"required":["product_id"]}'}
              className={`w-full text-xs font-mono border rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-y ${
                paramsError ? "border-red-400" : "border-gray-300"
              }`}
            />
            {paramsError && <p className="text-xs text-red-500 mt-0.5">{paramsError}</p>}
          </div>

          {/* Enabled */}
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="webhook-enabled"
              checked={enabled}
              onChange={(e) => setEnabled(e.target.checked)}
              className="w-4 h-4 text-indigo-600 border-gray-300 rounded focus:ring-indigo-500"
            />
            <label htmlFor="webhook-enabled" className="text-sm text-gray-700">
              Aracı etkinleştir
            </label>
          </div>

          <div className="flex gap-3 pt-2">
            <button
              type="submit"
              disabled={isPending}
              className="flex-1 bg-indigo-600 text-white px-4 py-2 rounded-md text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 transition-colors"
            >
              {isPending ? "Kaydediliyor…" : isEdit ? "Güncelle" : "Oluştur"}
            </button>
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-md text-sm border border-gray-300 hover:bg-gray-50 transition-colors"
            >
              İptal
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

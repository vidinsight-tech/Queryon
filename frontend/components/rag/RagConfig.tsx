"use client";
import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { ragApi, llmsApi, embeddingsApi } from "@/lib/api";
import type { RagConfig as RagConfigType, LLM, EmbeddingModel } from "@/lib/types";
import { Info, CheckCircle2, XCircle } from "lucide-react";

export function RagConfig() {
  const qc = useQueryClient();

  const { data: ragConfig, isLoading: loadingConfig } = useQuery({
    queryKey: ["rag-config"],
    queryFn: ragApi.getConfig,
  });

  const { data: llms = [], isLoading: loadingLlms } = useQuery({
    queryKey: ["llms"],
    queryFn: llmsApi.list,
  });

  const { data: embeddings = [], isLoading: loadingEmbeddings } = useQuery({
    queryKey: ["embeddings"],
    queryFn: embeddingsApi.list,
  });

  const [llmId, setLlmId] = useState<string | null>(null);
  const [embeddingId, setEmbeddingId] = useState<string | null>(null);

  useEffect(() => {
    if (ragConfig) {
      setLlmId(ragConfig.llm_id);
      setEmbeddingId(ragConfig.embedding_model_id);
    }
  }, [ragConfig]);

  const mutation = useMutation({
    mutationFn: (cfg: RagConfigType) => ragApi.updateConfig(cfg),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["rag-config"] });
      toast.success("RAG yapılandırması kaydedildi.");
    },
    onError: () => toast.error("Yapılandırma kaydedilemedi."),
  });

  const isLoading = loadingConfig || loadingLlms || loadingEmbeddings;

  if (isLoading) return <p className="text-gray-400 text-sm">Yapılandırma yükleniyor…</p>;

  const activeLlms = (llms as LLM[]).filter((l) => l.is_active);
  const activeEmbeddings = (embeddings as EmbeddingModel[]).filter((e) => e.is_active);
  const ragActive = embeddingId !== null;

  const handleSave = () => {
    mutation.mutate({ llm_id: llmId, embedding_model_id: embeddingId });
  };

  return (
    <div className="max-w-xl space-y-6">
      {/* RAG Status */}
      <div
        className={`flex items-center gap-3 px-4 py-3 rounded-lg border text-sm font-medium ${
          ragActive
            ? "bg-green-50 border-green-200 text-green-700"
            : "bg-gray-50 border-gray-200 text-gray-500"
        }`}
      >
        {ragActive ? (
          <CheckCircle2 className="w-4 h-4 shrink-0" />
        ) : (
          <XCircle className="w-4 h-4 shrink-0" />
        )}
        {ragActive ? "RAG etkin" : "RAG devre dışı — embedding modeli seçilmedi"}
      </div>

      {/* Qdrant info */}
      <div className="flex items-start gap-3 px-4 py-3 rounded-lg border border-blue-100 bg-blue-50 text-sm text-blue-700">
        <Info className="w-4 h-4 mt-0.5 shrink-0" />
        <span>
          Qdrant bağlantısı ortam değişkenleriyle yapılandırılır (
          <code className="font-mono text-xs">QDRANT_URL</code>,{" "}
          <code className="font-mono text-xs">QDRANT_API_KEY</code>).
        </span>
      </div>

      {/* Config card */}
      <div className="bg-white rounded-xl border border-gray-200 p-5 space-y-5">
        {/* LLM dropdown */}
        <div>
          <label className="text-sm font-medium block mb-1">LLM</label>
          <select
            value={llmId ?? ""}
            onChange={(e) => setLlmId(e.target.value || null)}
            className="border border-gray-300 rounded-md px-3 py-2 text-sm w-full focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            <option value="">Yok / Global aktif LLM kullan</option>
            {activeLlms.map((llm) => (
              <option key={llm.id} value={llm.id}>
                {llm.name} ({llm.provider} — {(llm.config?.model as string) ?? "unknown"})
              </option>
            ))}
          </select>
          {activeLlms.length === 0 && (
            <p className="text-xs text-gray-400 mt-1">
              Aktif LLM yok. LLM sayfasından bir tane ekleyin.
            </p>
          )}
        </div>

        {/* Embedding model dropdown */}
        <div>
          <label className="text-sm font-medium block mb-1">Embedding Modeli</label>
          <select
            value={embeddingId ?? ""}
            onChange={(e) => setEmbeddingId(e.target.value || null)}
            className="border border-gray-300 rounded-md px-3 py-2 text-sm w-full focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            <option value="">Yok (RAG devre dışı)</option>
            {activeEmbeddings.map((em) => (
              <option key={em.id} value={em.id}>
                {em.name} ({em.provider} — {(em.config?.model as string) ?? "unknown"})
              </option>
            ))}
          </select>
          {activeEmbeddings.length === 0 && (
            <p className="text-xs text-gray-400 mt-1">
              Aktif embedding modeli yok. Embedding Modelleri sayfasından bir tane ekleyin.
            </p>
          )}
        </div>
      </div>

      <div className="flex items-center gap-3">
        <button
          onClick={handleSave}
          disabled={mutation.isPending}
          className="bg-indigo-600 text-white px-5 py-2 rounded-md text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 transition-colors"
        >
          {mutation.isPending ? "Kaydediliyor…" : "Kaydet & Uygula"}
        </button>
      </div>
    </div>
  );
}

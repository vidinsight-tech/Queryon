"use client";
import { useQuery } from "@tanstack/react-query";
import { orchestratorApi } from "@/lib/api";
import { Loader2, Copy, Check } from "lucide-react";
import { useState } from "react";

export function SystemPromptPreview() {
  const [copied, setCopied] = useState(false);

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["orchestrator-preview-prompt"],
    queryFn: orchestratorApi.previewPrompt,
    staleTime: Infinity,
  });

  function handleCopy() {
    if (data?.system_prompt) {
      navigator.clipboard.writeText(data.system_prompt).then(() => {
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      });
    }
  }

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 text-gray-400 py-8">
        <Loader2 className="w-4 h-4 animate-spin" /> Yükleniyor…
      </div>
    );
  }

  if (isError) {
    return (
      <div className="text-red-600 text-sm">
        Prompt yüklenemedi.{" "}
        <button onClick={() => refetch()} className="underline">
          Tekrar dene
        </button>
      </div>
    );
  }

  const prompt = data?.system_prompt ?? "";

  return (
    <div className="space-y-3 max-w-2xl">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-gray-600">
            Botun kullanacağı tam sistem promptu (salt okunur).
          </p>
          <p className="text-xs text-gray-400 mt-0.5">
            Identity ve Modlar sekmesindeki ayarlardan otomatik oluşturulur.
          </p>
        </div>
        <button
          onClick={handleCopy}
          disabled={!prompt}
          className="flex items-center gap-1.5 px-3 py-1.5 border border-gray-200 text-gray-600 text-sm rounded-md hover:bg-gray-50 transition-colors disabled:opacity-40"
        >
          {copied ? (
            <>
              <Check className="w-3.5 h-3.5 text-green-600" /> Kopyalandı
            </>
          ) : (
            <>
              <Copy className="w-3.5 h-3.5" /> Kopyala
            </>
          )}
        </button>
      </div>

      {prompt ? (
        <pre className="bg-gray-950 text-gray-100 rounded-xl p-4 text-xs font-mono leading-relaxed whitespace-pre-wrap overflow-x-auto max-h-[520px] overflow-y-auto">
          {prompt}
        </pre>
      ) : (
        <div className="bg-gray-50 border border-gray-200 rounded-xl p-6 text-center text-gray-400 text-sm">
          Henüz bir sistem promptu oluşturulmamış. Identity sekmesinden bot adı ve kişilik ekleyin.
        </div>
      )}
    </div>
  );
}

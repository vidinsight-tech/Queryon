"use client";
import { useEffect } from "react";
import { useForm, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { orchestratorApi } from "@/lib/api";
import type { BotConfig } from "@/lib/types";
import { Toggle } from "@/components/ui/Toggle";

const schema = z.object({
  default_intent: z.enum(["rag", "direct", "rule", "tool"]),
  rules_first: z.boolean(),
  fallback_to_direct: z.boolean(),
  min_confidence: z.number().min(0).max(1),
  low_confidence_strategy: z.enum(["fallback", "ask_user"]),
  when_rag_unavailable: z.enum(["direct", "ask_user"]),
  embedding_confidence_threshold: z.number().min(0).max(1),
  llm_timeout_seconds: z.number().nullable(),
  max_conversation_turns: z.number().int().min(0).max(100),
  enabled_intents: z.array(z.enum(["rag", "direct", "rule", "tool", "character"])),
  classification_prompt_override: z.string().nullable(),
});

type FormValues = z.infer<typeof schema>;

export function ConfigForm() {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["orchestrator-config"],
    queryFn: orchestratorApi.getConfig,
  });

  const mutation = useMutation({
    mutationFn: (values: BotConfig) => orchestratorApi.updateConfig(values),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["orchestrator-config"] });
      toast.success("Gelişmiş ayarlar kaydedildi.");
    },
    onError: () => toast.error("Ayarlar kaydedilemedi."),
  });

  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: data as FormValues | undefined,
  });

  useEffect(() => {
    if (data) form.reset(data as FormValues);
  }, [data, form]);

  if (isLoading) return <p className="text-gray-400 text-sm">Yükleniyor…</p>;

  const onSubmit = (values: FormValues) =>
    mutation.mutate({ ...(data ?? {}), ...values } as BotConfig);

  const SliderField = ({
    name,
    label,
    hint,
    min = 0,
    max = 1,
    step = 0.05,
  }: {
    name: keyof FormValues;
    label: string;
    hint?: string;
    min?: number;
    max?: number;
    step?: number;
  }) => (
    <Controller
      control={form.control}
      name={name}
      render={({ field }) => (
        <div>
          <div className="flex justify-between mb-1">
            <div>
              <label className="text-sm font-medium">{label}</label>
              {hint && <p className="text-xs text-gray-400">{hint}</p>}
            </div>
            <span className="text-sm text-indigo-600 font-mono">
              {Number(field.value).toFixed(2)}
            </span>
          </div>
          <input
            type="range"
            min={min}
            max={max}
            step={step}
            value={Number(field.value)}
            onChange={(e) => field.onChange(parseFloat(e.target.value))}
            className="w-full accent-indigo-600"
          />
        </div>
      )}
    />
  );

  const ToggleField = ({ name, label, hint }: { name: keyof FormValues; label: string; hint?: string }) => (
    <Controller
      control={form.control}
      name={name}
      render={({ field }) => (
        <div className="flex items-center justify-between py-2">
          <div>
            <p className="text-sm font-medium">{label}</p>
            {hint && <p className="text-xs text-gray-400">{hint}</p>}
          </div>
          <Toggle checked={!!field.value} onCheckedChange={field.onChange} />
        </div>
      )}
    />
  );

  return (
    <form onSubmit={form.handleSubmit(onSubmit)} className="max-w-xl space-y-6">

      {/* Default Intent */}
      <div>
        <label className="text-sm font-medium block mb-1">Varsayılan Intent</label>
        <p className="text-xs text-gray-400 mb-2">
          Sınıflandırıcı emin olamadığında hangi intent'e düşülsün?
        </p>
        <Controller
          control={form.control}
          name="default_intent"
          render={({ field }) => (
            <div className="flex gap-2 flex-wrap">
              {(["rag", "direct", "rule", "tool"] as const).map((v) => (
                <button
                  key={v}
                  type="button"
                  onClick={() => field.onChange(v)}
                  className={`px-4 py-1.5 rounded-full text-sm border transition-colors ${
                    field.value === v
                      ? "bg-indigo-600 text-white border-indigo-600"
                      : "border-gray-300 text-gray-600 hover:bg-gray-50"
                  }`}
                >
                  {v.toUpperCase()}
                </button>
              ))}
            </div>
          )}
        />
      </div>

      {/* Toggle switches */}
      <div className="bg-white rounded-lg border border-gray-200 px-4 divide-y divide-gray-100">
        <ToggleField
          name="rules_first"
          label="Kurallar Önce"
          hint="Her mesajda önce kural eşleştirmesi yap, eşleşme yoksa sınıflandır."
        />
        <ToggleField
          name="fallback_to_direct"
          label="RAG Boşsa Direkte Dön"
          hint="Vektör araması sonuç döndürmezse LLM'e direkt sor."
        />
      </div>

      {/* Enabled intents */}
      <div>
        <label className="text-sm font-medium block mb-1">Aktif Intent'ler</label>
        <p className="text-xs text-gray-400 mb-3">
          Sınıflandırıcı bu intent'lerden birini seçebilir. Kapalı intent'ler devre dışıdır.
        </p>
        <Controller
          control={form.control}
          name="enabled_intents"
          render={({ field }) => {
            const INTENTS = [
              { value: "rag",       label: "RAG",       hint: "Bilgi tabanı araması" },
              { value: "direct",    label: "Direkt LLM", hint: "Genel LLM yanıtı" },
              { value: "rule",      label: "Kural",      hint: "Sabit kural yanıtları" },
              { value: "tool",      label: "Araç",       hint: "Harici araç çağrısı" },
              { value: "character", label: "Karakter",   hint: "Kişilik modlu yanıt" },
            ] as const;
            const toggle = (v: string) => {
              const current = field.value ?? [];
              field.onChange(
                current.includes(v as never)
                  ? current.filter((i) => i !== v)
                  : [...current, v as never]
              );
            };
            return (
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                {INTENTS.map(({ value, label, hint }) => {
                  const active = (field.value ?? []).includes(value as never);
                  return (
                    <button
                      key={value}
                      type="button"
                      onClick={() => toggle(value)}
                      className={`flex flex-col items-start px-3 py-2.5 rounded-lg border text-left transition-colors ${
                        active
                          ? "bg-indigo-50 border-indigo-300 text-indigo-800"
                          : "border-gray-200 text-gray-400 hover:bg-gray-50"
                      }`}
                    >
                      <span className="text-sm font-medium">{label}</span>
                      <span className="text-xs opacity-70 mt-0.5">{hint}</span>
                    </button>
                  );
                })}
              </div>
            );
          }}
        />
      </div>

      {/* Confidence sliders */}
      <div className="bg-white rounded-lg border border-gray-200 p-4 space-y-5">
        <SliderField
          name="min_confidence"
          label="Minimum Güven Eşiği"
          hint="Bu değerin altındaki sınıflandırma sonuçları düşük güven stratejisini tetikler."
        />
        <SliderField
          name="embedding_confidence_threshold"
          label="Embedding Güven Eşiği"
          hint="Vektör araması bu skorun altında ise RAG sonucu boş sayılır."
        />
      </div>

      {/* Low confidence strategy */}
      <div>
        <label className="text-sm font-medium block mb-1">Düşük Güven Stratejisi</label>
        <p className="text-xs text-gray-400 mb-2">
          Sınıflandırma güveni eşiğin altında kaldığında ne yapılsın?
        </p>
        <Controller
          control={form.control}
          name="low_confidence_strategy"
          render={({ field }) => (
            <select
              value={field.value}
              onChange={field.onChange}
              className="border border-gray-300 rounded-md px-3 py-2 text-sm w-full focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              <option value="fallback">Varsayılan intent'e düş</option>
              <option value="ask_user">Kullanıcıdan açıklama iste</option>
            </select>
          )}
        />
      </div>

      {/* When RAG unavailable */}
      <div>
        <label className="text-sm font-medium block mb-1">RAG Erişilemezse</label>
        <p className="text-xs text-gray-400 mb-2">
          Qdrant'a bağlanılamazsa (servis kapalı, hata vb.) ne yapılsın?
        </p>
        <Controller
          control={form.control}
          name="when_rag_unavailable"
          render={({ field }) => (
            <select
              value={field.value}
              onChange={field.onChange}
              className="border border-gray-300 rounded-md px-3 py-2 text-sm w-full focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              <option value="direct">Doğrudan LLM ile cevap ver</option>
              <option value="ask_user">Kullanıcıdan RAG bağlamı iste</option>
            </select>
          )}
        />
      </div>

      {/* Classification prompt override */}
      <div>
        <label className="text-sm font-medium block mb-1">Sınıflandırma Prompt Geçersizleştirme</label>
        <p className="text-xs text-gray-400 mb-2">
          Boş bırakılırsa sistem varsayılan sınıflandırma promptunu kullanır.
          Doldurulursa bu metin sınıflandırıcı LLM'e sistem promptu olarak gönderilir.
        </p>
        <Controller
          control={form.control}
          name="classification_prompt_override"
          render={({ field }) => (
            <textarea
              rows={4}
              value={field.value ?? ""}
              onChange={(e) => field.onChange(e.target.value || null)}
              placeholder="Boş bırakırsan varsayılan sınıflandırma promptu kullanılır."
              className="border border-gray-300 rounded-md px-3 py-2 text-sm w-full focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none font-mono"
            />
          )}
        />
      </div>

      {/* Numeric fields */}
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="text-sm font-medium block mb-1">LLM Zaman Aşımı (sn)</label>
          <p className="text-xs text-gray-400 mb-1">Boş → zaman aşımı yok</p>
          <Controller
            control={form.control}
            name="llm_timeout_seconds"
            render={({ field }) => (
              <input
                type="number"
                min={0}
                value={field.value ?? ""}
                onChange={(e) =>
                  field.onChange(e.target.value === "" ? null : parseFloat(e.target.value))
                }
                placeholder="Sınırsız"
                className="border border-gray-300 rounded-md px-3 py-2 text-sm w-full focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            )}
          />
        </div>
        <div>
          <label className="text-sm font-medium block mb-1">Maks. Konuşma Turu</label>
          <p className="text-xs text-gray-400 mb-1">0 → sınırsız</p>
          <Controller
            control={form.control}
            name="max_conversation_turns"
            render={({ field }) => (
              <input
                type="number"
                min={0}
                max={100}
                value={field.value}
                onChange={(e) => field.onChange(parseInt(e.target.value))}
                className="border border-gray-300 rounded-md px-3 py-2 text-sm w-full focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            )}
          />
        </div>
      </div>

      <button
        type="submit"
        disabled={mutation.isPending}
        className="bg-indigo-600 text-white px-5 py-2 rounded-md text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 transition-colors"
      >
        {mutation.isPending ? "Kaydediliyor…" : "Kaydet"}
      </button>
    </form>
  );
}

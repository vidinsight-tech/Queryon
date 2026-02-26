"use client";
import { useState } from "react";
import { useForm, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { rulesApi } from "@/lib/api";
import type { Rule } from "@/lib/types";
import { X, Plus, Trash2, Zap, ArrowRight, MessageSquare, GitBranch, Sparkles } from "lucide-react";

const schema = z.object({
  name: z.string().min(1),
  description: z.string(),
  trigger_patterns: z.array(z.string().min(1)).min(1, "En az bir tetikleyici gerekli"),
  response_template: z.string().min(1),
  variables: z.record(z.string(), z.string()),
  priority: z.number().int().min(0).max(1000),
  is_active: z.boolean(),
  is_flow_rule: z.boolean(),
  flow_id: z.string().nullable(),
  step_key: z.string().nullable(),
  required_step: z.string().nullable(),
  next_steps: z.record(z.string(), z.string()).nullable(),
});

type FormValues = z.infer<typeof schema>;

const TEMPLATES = [
  {
    label: "Basit Soru-Cevap",
    icon: <MessageSquare className="w-4 h-4" />,
    desc: "Kullanıcı bir şey sorduğunda sabit cevap ver",
    values: {
      name: "",
      description: "",
      trigger_patterns: [""],
      response_template: "",
      variables: {},
      priority: 5,
      is_active: true,
      is_flow_rule: false,
      flow_id: null,
      step_key: null,
      required_step: null,
      next_steps: null,
    } as FormValues,
  },
  {
    label: "Çok Adımlı Akış",
    icon: <GitBranch className="w-4 h-4" />,
    desc: "Kullanıcıya seçenekler sun, cevabına göre dallan",
    values: {
      name: "",
      description: "",
      trigger_patterns: [""],
      response_template: "Lütfen birini seçin:\nA) ...\nB) ...",
      variables: {},
      priority: 5,
      is_active: true,
      is_flow_rule: true,
      flow_id: "",
      step_key: "start",
      required_step: null,
      next_steps: { A: "", B: "" },
    } as FormValues,
  },
];

interface Props {
  rule?: Rule;
  onClose: () => void;
}

export function RuleForm({ rule, onClose }: Props) {
  const qc = useQueryClient();
  const isEdit = Boolean(rule);
  const [showTemplates, setShowTemplates] = useState(!isEdit);

  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: rule
      ? {
          ...rule,
          variables: (rule.variables as Record<string, string>) ?? {},
          next_steps: (rule.next_steps as Record<string, string>) ?? null,
          is_flow_rule: Boolean(rule.flow_id),
        }
      : { trigger_patterns: [""], variables: {}, is_flow_rule: false, priority: 0, is_active: true },
  });

  const isFlowRule = form.watch("is_flow_rule");
  const [patternInput, setPatternInput] = useState("");
  const [varKey, setVarKey] = useState("");
  const [varVal, setVarVal] = useState("");
  const [nextKey, setNextKey] = useState("");
  const [nextVal, setNextVal] = useState("");

  const createMutation = useMutation({
    mutationFn: (data: FormValues) => {
      const payload = {
        name: data.name,
        description: data.description,
        trigger_patterns: data.trigger_patterns,
        response_template: data.response_template,
        variables: data.variables,
        priority: data.priority,
        is_active: data.is_active,
        flow_id: data.is_flow_rule ? data.flow_id : null,
        step_key: data.is_flow_rule ? data.step_key : null,
        required_step: data.is_flow_rule ? data.required_step : null,
        next_steps: data.is_flow_rule ? data.next_steps : null,
      };
      return isEdit && rule
        ? rulesApi.update(rule.id, payload)
        : rulesApi.create(payload as any);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["rule-tree"] });
      onClose();
    },
  });

  const patterns = form.watch("trigger_patterns");
  const variables = form.watch("variables");
  const nextSteps = form.watch("next_steps") ?? {};

  const addPattern = () => {
    if (patternInput.trim()) {
      form.setValue("trigger_patterns", [...patterns, patternInput.trim()]);
      setPatternInput("");
    }
  };

  const removePattern = (i: number) =>
    form.setValue("trigger_patterns", patterns.filter((_, idx) => idx !== i));

  const addVar = () => {
    if (varKey.trim()) {
      form.setValue("variables", { ...variables, [varKey.trim()]: varVal });
      setVarKey("");
      setVarVal("");
    }
  };

  const removeVar = (k: string) => {
    const next = { ...variables };
    delete next[k];
    form.setValue("variables", next);
  };

  const addNextStep = () => {
    if (nextKey.trim()) {
      form.setValue("next_steps", { ...(nextSteps as Record<string, string>), [nextKey.trim()]: nextVal });
      setNextKey("");
      setNextVal("");
    }
  };

  const removeNextStep = (k: string) => {
    const next = { ...(nextSteps as Record<string, string>) };
    delete next[k];
    form.setValue("next_steps", Object.keys(next).length ? next : null);
  };

  const applyTemplate = (tpl: (typeof TEMPLATES)[number]) => {
    form.reset(tpl.values);
    setShowTemplates(false);
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-2xl max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
          <h2 className="font-bold text-lg flex items-center gap-2">
            <Zap className="w-5 h-5 text-indigo-500" />
            {isEdit ? "Kuralı Düzenle" : "Yeni Kural Oluştur"}
          </h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Template picker (only for new rules) */}
        {!isEdit && showTemplates && (
          <div className="px-6 py-4 bg-gray-50 border-b border-gray-100">
            <p className="text-sm text-gray-600 mb-3 flex items-center gap-1.5">
              <Sparkles className="w-4 h-4 text-amber-500" />
              Bir şablon seçerek hızlıca başlayın:
            </p>
            <div className="grid grid-cols-2 gap-3">
              {TEMPLATES.map((tpl) => (
                <button
                  key={tpl.label}
                  onClick={() => applyTemplate(tpl)}
                  className="text-left p-3 bg-white border border-gray-200 rounded-lg hover:border-indigo-300 hover:bg-indigo-50/50 transition-colors"
                >
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-indigo-600">{tpl.icon}</span>
                    <span className="text-sm font-medium text-gray-900">{tpl.label}</span>
                  </div>
                  <p className="text-xs text-gray-500">{tpl.desc}</p>
                </button>
              ))}
              <button
                onClick={() => setShowTemplates(false)}
                className="text-left p-3 bg-white border border-dashed border-gray-300 rounded-lg hover:border-gray-400 transition-colors"
              >
                <div className="flex items-center gap-2 mb-1">
                  <Plus className="w-4 h-4 text-gray-400" />
                  <span className="text-sm font-medium text-gray-600">Sıfırdan Oluştur</span>
                </div>
                <p className="text-xs text-gray-400">Boş formla başla</p>
              </button>
            </div>
          </div>
        )}

        <form
          onSubmit={form.handleSubmit((v: FormValues) => createMutation.mutate(v))}
          className="px-6 py-5 space-y-5"
        >
          {/* Name + Priority */}
          <div className="grid grid-cols-3 gap-4">
            <div className="col-span-2">
              <label className="text-sm font-medium block mb-1">Kural Adı *</label>
              <input
                {...form.register("name")}
                className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                placeholder="ör: Karşılama, Fiyat Bilgisi"
              />
              {form.formState.errors.name && (
                <p className="text-xs text-red-500 mt-1">Zorunlu alan</p>
              )}
            </div>
            <div>
              <label className="text-sm font-medium block mb-1">Öncelik</label>
              <input
                type="number"
                {...form.register("priority", { valueAsNumber: true })}
                className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
              <p className="text-xs text-gray-400 mt-0.5">Yüksek = önce kontrol edilir</p>
            </div>
          </div>

          {/* Description */}
          <div>
            <label className="text-sm font-medium block mb-1">
              Açıklama{" "}
              <span className="text-gray-400 font-normal">(LLM sınıflandırıcısına gösterilir)</span>
            </label>
            <input
              {...form.register("description")}
              className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              placeholder="ör: Kullanıcı merhaba dediğinde tetiklenir"
            />
          </div>

          {/* IF section */}
          <div className="bg-indigo-50/50 border border-indigo-100 rounded-lg p-4">
            <label className="text-sm font-semibold text-indigo-700 block mb-2 flex items-center gap-1.5">
              <Zap className="w-4 h-4" />
              EĞER — Kullanıcı şunları derse: *
              <span className="text-gray-400 font-normal text-xs ml-1">(regex için r: ön eki kullan)</span>
            </label>
            <div className="flex gap-2 mb-2">
              <input
                value={patternInput}
                onChange={(e) => setPatternInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addPattern())}
                className="flex-1 border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white"
                placeholder="kelime veya r:regex.*kalıp"
              />
              <button
                type="button"
                onClick={addPattern}
                className="px-3 py-2 bg-indigo-600 text-white rounded-md text-sm hover:bg-indigo-700"
              >
                <Plus className="w-4 h-4" />
              </button>
            </div>
            <div className="flex flex-wrap gap-2">
              {patterns.map((p, i) => (
                <span
                  key={i}
                  className="inline-flex items-center gap-1 bg-white text-indigo-700 px-2.5 py-1 rounded-md text-xs font-mono border border-indigo-200"
                >
                  "{p}"
                  <button type="button" onClick={() => removePattern(i)}>
                    <X className="w-3 h-3" />
                  </button>
                </span>
              ))}
            </div>
            {form.formState.errors.trigger_patterns && (
              <p className="text-xs text-red-500 mt-1">En az bir tetikleyici gerekli</p>
            )}
          </div>

          {/* THEN section */}
          <div className="bg-green-50/50 border border-green-100 rounded-lg p-4">
            <label className="text-sm font-semibold text-green-700 block mb-2 flex items-center gap-1.5">
              <ArrowRight className="w-4 h-4" />
              O ZAMAN — Bot şu cevabı versin: *
              <span className="text-gray-400 font-normal text-xs ml-1">({"{değişken}"} kullanılabilir)</span>
            </label>
            <textarea
              {...form.register("response_template")}
              rows={3}
              className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-500 bg-white"
              placeholder="Merhaba! Size nasıl yardımcı olabilirim?"
            />
            {form.formState.errors.response_template && (
              <p className="text-xs text-red-500 mt-1">Zorunlu alan</p>
            )}
          </div>

          {/* Variables */}
          <div>
            <label className="text-sm font-medium block mb-1">Değişkenler</label>
            <p className="text-xs text-gray-400 mb-2">Cevap şablonunda {"{anahtar}"} ile kullanılır</p>
            <div className="flex gap-2 mb-2">
              <input
                value={varKey}
                onChange={(e) => setVarKey(e.target.value)}
                className="flex-1 border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                placeholder="anahtar"
              />
              <input
                value={varVal}
                onChange={(e) => setVarVal(e.target.value)}
                className="flex-1 border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                placeholder="değer"
              />
              <button
                type="button"
                onClick={addVar}
                className="px-3 py-2 bg-gray-100 text-gray-700 rounded-md text-sm hover:bg-gray-200"
              >
                <Plus className="w-4 h-4" />
              </button>
            </div>
            {Object.entries(variables).map(([k, v]) => (
              <div key={k} className="flex items-center gap-2 text-xs mb-1">
                <span className="font-mono text-gray-600 bg-gray-100 px-2 py-1 rounded">{k}</span>
                <span className="text-gray-400">→</span>
                <span className="font-mono text-gray-700 flex-1">{String(v)}</span>
                <button type="button" onClick={() => removeVar(k)}>
                  <Trash2 className="w-3 h-3 text-red-400" />
                </button>
              </div>
            ))}
          </div>

          {/* Active toggle */}
          <Controller
            control={form.control}
            name="is_active"
            render={({ field }) => (
              <label className="flex items-center gap-3 cursor-pointer">
                <div
                  onClick={() => field.onChange(!field.value)}
                  className={`relative w-10 h-5 rounded-full transition-colors ${
                    field.value ? "bg-indigo-600" : "bg-gray-300"
                  }`}
                >
                  <span
                    className={`absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform ${
                      field.value ? "translate-x-5" : "translate-x-0"
                    }`}
                  />
                </div>
                <span className="text-sm font-medium">Aktif</span>
              </label>
            )}
          />

          {/* Flow rule toggle */}
          <div className="border-t border-gray-100 pt-4">
            <Controller
              control={form.control}
              name="is_flow_rule"
              render={({ field }) => (
                <label className="flex items-center gap-3 cursor-pointer">
                  <div
                    onClick={() => field.onChange(!field.value)}
                    className={`relative w-10 h-5 rounded-full transition-colors ${
                      field.value ? "bg-indigo-600" : "bg-gray-300"
                    }`}
                  >
                    <span
                      className={`absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform ${
                        field.value ? "translate-x-5" : "translate-x-0"
                      }`}
                    />
                  </div>
                  <span className="text-sm font-medium flex items-center gap-1.5">
                    <GitBranch className="w-4 h-4 text-purple-500" />
                    Çok adımlı akışın parçası
                  </span>
                </label>
              )}
            />

            {isFlowRule && (
              <div className="mt-4 space-y-3 pl-4 border-l-2 border-purple-200 bg-purple-50/30 rounded-r-lg py-3 pr-3">
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-xs font-medium block mb-1">Akış Kimliği</label>
                    <input
                      {...form.register("flow_id")}
                      className="w-full border border-gray-300 rounded-md px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
                      placeholder="ör: randevu_akisi"
                    />
                  </div>
                  <div>
                    <label className="text-xs font-medium block mb-1">Adım Anahtarı</label>
                    <input
                      {...form.register("step_key")}
                      className="w-full border border-gray-300 rounded-md px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
                      placeholder="ör: start"
                    />
                  </div>
                </div>
                <div>
                  <label className="text-xs font-medium block mb-1">
                    Gerekli Adım{" "}
                    <span className="text-gray-400">(giriş noktası için boş bırakın)</span>
                  </label>
                  <input
                    {...form.register("required_step")}
                    className="w-full border border-gray-300 rounded-md px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
                    placeholder="ör: start"
                  />
                </div>

                {/* Next steps — SONRA section */}
                <div>
                  <label className="text-xs font-semibold text-purple-700 block mb-1 flex items-center gap-1">
                    <ArrowRight className="w-3 h-3" />
                    SONRA — Kullanıcının cevabına göre:
                  </label>
                  <p className="text-xs text-gray-400 mb-2">Kullanıcı ne derse hangi adıma gidilsin?</p>
                  <div className="flex gap-2 mb-2">
                    <input
                      value={nextKey}
                      onChange={(e) => setNextKey(e.target.value)}
                      className="flex-1 border border-gray-300 rounded-md px-2 py-1.5 text-xs focus:outline-none bg-white"
                      placeholder="seçenek (ör: Evet, A, *)"
                    />
                    <input
                      value={nextVal}
                      onChange={(e) => setNextVal(e.target.value)}
                      className="flex-1 border border-gray-300 rounded-md px-2 py-1.5 text-xs focus:outline-none bg-white"
                      placeholder="gidilecek adım"
                    />
                    <button
                      type="button"
                      onClick={addNextStep}
                      className="px-2 py-1.5 bg-purple-100 text-purple-700 rounded-md text-sm hover:bg-purple-200"
                    >
                      <Plus className="w-3 h-3" />
                    </button>
                  </div>
                  {Object.entries(nextSteps as Record<string, string>).map(([k, v]) => (
                    <div key={k} className="flex items-center gap-2 text-xs mb-1">
                      <span className="font-medium text-purple-800 bg-purple-100 px-2 py-1 rounded">"{k}"</span>
                      <ArrowRight className="w-3 h-3 text-purple-400" />
                      <span className="font-mono text-purple-600 flex-1">{v} adımına geç</span>
                      <button type="button" onClick={() => removeNextStep(k)}>
                        <Trash2 className="w-3 h-3 text-red-400" />
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          <div className="flex gap-3 pt-2 border-t border-gray-100">
            <button
              type="submit"
              disabled={createMutation.isPending}
              className="bg-indigo-600 text-white px-5 py-2 rounded-md text-sm font-medium hover:bg-indigo-700 disabled:opacity-50"
            >
              {createMutation.isPending ? "Kaydediliyor…" : isEdit ? "Değişiklikleri Kaydet" : "Kural Oluştur"}
            </button>
            <button
              type="button"
              onClick={onClose}
              className="px-5 py-2 rounded-md text-sm border border-gray-300 hover:bg-gray-50"
            >
              İptal
            </button>
            {createMutation.isError && (
              <span className="text-sm text-red-600 self-center">Kaydetme başarısız</span>
            )}
          </div>
        </form>
      </div>
    </div>
  );
}

"use client";
import { useState, useEffect, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { orchestratorApi } from "@/lib/api";
import type { BotConfig } from "@/lib/types";
import { IdentityForm } from "./IdentityForm";
import { ModeCard } from "./ModeCard";
import { FieldsEditor } from "./FieldsEditor";
import { ConfigForm } from "@/components/orchestrator/ConfigForm";
import { SystemPromptPreview } from "./SystemPromptPreview";
import {
  MessageCircle,
  DatabaseZap,
  CalendarCheck,
  ShoppingBag,
  Save,
  Loader2,
  UserCircle,
  ToggleLeft,
  SlidersHorizontal,
  FileText,
  AlertCircle,
} from "lucide-react";

const TABS = ["Identity", "Modes", "Advanced", "Prompt"] as const;
type Tab = (typeof TABS)[number];

const TAB_LABELS: Record<Tab, string> = {
  Identity: "Kimlik",
  Modes: "Modlar",
  Advanced: "Gelişmiş",
  Prompt: "Prompt",
};

const TAB_ICONS: Record<Tab, React.ReactNode> = {
  Identity: <UserCircle className="w-4 h-4" />,
  Modes: <ToggleLeft className="w-4 h-4" />,
  Advanced: <SlidersHorizontal className="w-4 h-4" />,
  Prompt: <FileText className="w-4 h-4" />,
};

const DEFAULT_CONFIG: BotConfig = {
  bot_name: "Assistant",
  character_system_prompt: null,
  appointment_fields: [],
  order_mode_enabled: false,
  order_fields: [],
  restrictions: null,
  appointment_webhook_url: null,
  appointment_webhook_secret: null,
  enabled_intents: ["rag", "direct", "rule", "tool"],
  default_intent: "rag",
  rules_first: true,
  fallback_to_direct: true,
  when_rag_unavailable: "direct",
  min_confidence: 0.7,
  low_confidence_strategy: "fallback",
  embedding_confidence_threshold: 0.85,
  classification_prompt_override: null,
  llm_timeout_seconds: 60,
  max_conversation_turns: 10,
};

export function BotBuilderPanel() {
  const qc = useQueryClient();
  const [activeTab, setActiveTab] = useState<Tab>("Identity");
  const [local, setLocal] = useState<BotConfig>(DEFAULT_CONFIG);
  const [showUnsavedBar, setShowUnsavedBar] = useState(false);
  const [pendingTab, setPendingTab] = useState<Tab | null>(null);

  const { data: remote, isLoading } = useQuery({
    queryKey: ["orchestrator-config"],
    queryFn: orchestratorApi.getConfig,
  });

  useEffect(() => {
    if (remote) setLocal({ ...DEFAULT_CONFIG, ...remote });
  }, [remote]);

  // Dirty check: Identity and Modes tabs share the same local state
  const isDirty = useMemo(
    () =>
      remote != null &&
      JSON.stringify({ ...DEFAULT_CONFIG, ...remote }) !== JSON.stringify(local),
    [remote, local]
  );

  // Warn on browser/tab close when there are unsaved changes
  useEffect(() => {
    if (!isDirty) return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [isDirty]);

  const patch = (updates: Partial<BotConfig>) =>
    setLocal((prev) => ({ ...prev, ...updates }));

  const mutation = useMutation({
    mutationFn: () => orchestratorApi.updateConfig(local),
    onSuccess: (data) => {
      setLocal({ ...DEFAULT_CONFIG, ...data });
      qc.invalidateQueries({ queryKey: ["orchestrator-config"] });
      qc.invalidateQueries({ queryKey: ["orchestrator-preview-prompt"] });
      toast.success("Bot ayarları kaydedildi.");
      setShowUnsavedBar(false);
      if (pendingTab) {
        setActiveTab(pendingTab);
        setPendingTab(null);
      }
    },
    onError: () => toast.error("Bot ayarları kaydedilemedi."),
  });

  function handleTabClick(tab: Tab) {
    // Advanced and Prompt tabs don't share local state — no dirty check needed
    if (tab === activeTab) return;
    if (isDirty && activeTab !== "Advanced" && activeTab !== "Prompt" && tab !== activeTab) {
      setPendingTab(tab);
      setShowUnsavedBar(true);
      return;
    }
    setActiveTab(tab);
    setShowUnsavedBar(false);
    setPendingTab(null);
  }

  function handleDiscard() {
    if (remote) setLocal({ ...DEFAULT_CONFIG, ...remote });
    if (pendingTab) setActiveTab(pendingTab);
    setShowUnsavedBar(false);
    setPendingTab(null);
  }

  const appointmentEnabled = local.appointment_fields.length > 0;
  const toggleAppointment = (on: boolean) => {
    patch({
      appointment_fields: on
        ? [
            { key: "name", label: "Ad", question: "Adınız nedir?", required: true },
            { key: "phone", label: "Telefon", question: "Telefon numaranız?", required: true },
          ]
        : [],
    });
  };

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 text-gray-400 py-8">
        <Loader2 className="w-4 h-4 animate-spin" /> Yükleniyor…
      </div>
    );
  }

  return (
    <div className="space-y-5">
      {/* Sticky header */}
      <div className="flex items-center justify-between gap-3 pb-4 border-b border-gray-100">
        <div className="flex items-center gap-2">
          <h2 className="text-base font-semibold text-gray-800">Bot Ayarları</h2>
          {local.bot_name ? (
            <span className="px-2 py-0.5 bg-indigo-50 text-indigo-700 border border-indigo-200 text-xs font-medium rounded-full">
              {local.bot_name}
            </span>
          ) : (
            <span className="px-2 py-0.5 bg-gray-100 text-gray-400 text-xs rounded-full">
              Ayarlanmadı
            </span>
          )}
        </div>
        {activeTab !== "Advanced" && activeTab !== "Prompt" && (
          <button
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending || !isDirty}
            className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white text-sm font-medium rounded-md hover:bg-indigo-700 disabled:opacity-40 transition-colors"
          >
            {mutation.isPending ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Save className="w-4 h-4" />
            )}
            Kaydet
          </button>
        )}
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-200">
        <nav className="-mb-px flex gap-1">
          {TABS.map((tab) => {
            const showDot =
              isDirty &&
              tab !== activeTab &&
              tab !== "Advanced" &&
              tab !== "Prompt";
            return (
              <button
                key={tab}
                onClick={() => handleTabClick(tab)}
                className={`flex items-center gap-1.5 pb-3 px-3 text-sm font-medium border-b-2 transition-colors relative ${
                  activeTab === tab
                    ? "border-indigo-600 text-indigo-700"
                    : "border-transparent text-gray-500 hover:text-gray-700"
                }`}
              >
                {TAB_ICONS[tab]}
                {TAB_LABELS[tab]}
                {showDot && (
                  <span className="w-1.5 h-1.5 rounded-full bg-orange-400 inline-block ml-0.5" />
                )}
              </button>
            );
          })}
        </nav>
      </div>

      {/* Unsaved changes warning bar */}
      {showUnsavedBar && (
        <div className="flex items-center gap-3 px-4 py-3 bg-amber-50 border border-amber-200 rounded-lg text-sm">
          <AlertCircle className="w-4 h-4 text-amber-600 shrink-0" />
          <span className="flex-1 text-amber-800">Kaydedilmemiş değişiklikler var — kaydetmek ister misiniz?</span>
          <button
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending}
            className="px-3 py-1 bg-amber-600 text-white text-xs font-medium rounded-md hover:bg-amber-700 disabled:opacity-50 transition-colors"
          >
            Kaydet
          </button>
          <button
            onClick={handleDiscard}
            className="px-3 py-1 border border-amber-300 text-amber-700 text-xs font-medium rounded-md hover:bg-amber-100 transition-colors"
          >
            Yoksay
          </button>
        </div>
      )}

      {/* Tab content */}
      <div className="min-h-[300px]">
        {activeTab === "Identity" && (
          <IdentityForm config={local} onChange={patch} />
        )}

        {activeTab === "Modes" && (
          <div className="space-y-3 max-w-xl">
            {/* Chat — always on */}
            <ModeCard
              icon={<MessageCircle className="w-4 h-4" />}
              title="Sohbet"
              description="LLM tabanlı doğal dil konuşması"
              enabled={true}
              alwaysOn
            >
              <p className="text-xs text-gray-500">
                Kişilik &quot;Identity&quot; sekmesinden ayarlanır.
              </p>
            </ModeCard>

            {/* RAG */}
            <ModeCard
              icon={<DatabaseZap className="w-4 h-4" />}
              title="RAG (Bilgi Tabanı)"
              description="Belgelere dayalı cevaplar"
              enabled={local.enabled_intents.includes("rag")}
              onToggle={(on) =>
                patch({
                  enabled_intents: on
                    ? [...local.enabled_intents.filter((i) => i !== "rag"), "rag"]
                    : local.enabled_intents.filter((i) => i !== "rag"),
                })
              }
            >
              <p className="text-xs text-gray-500">
                RAG ayarları için{" "}
                <a href="/rag" className="text-indigo-600 underline">
                  RAG sayfasına
                </a>{" "}
                gidin.
              </p>
            </ModeCard>

            {/* Take Appointment */}
            <ModeCard
              icon={<CalendarCheck className="w-4 h-4" />}
              title="Randevu Al"
              description="Müşteri randevu bilgilerini topla"
              enabled={appointmentEnabled}
              onToggle={toggleAppointment}
            >
              <FieldsEditor
                value={local.appointment_fields}
                onChange={(fields) => patch({ appointment_fields: fields })}
              />
            </ModeCard>

            {/* Take Order */}
            <ModeCard
              icon={<ShoppingBag className="w-4 h-4" />}
              title="Sipariş Al"
              description="Müşteri sipariş bilgilerini topla"
              enabled={local.order_mode_enabled}
              onToggle={(on) => {
                patch({
                  order_mode_enabled: on,
                  order_fields:
                    on && local.order_fields.length === 0
                      ? [
                          { key: "name", label: "Ad", question: "Adınız nedir?", required: true },
                          { key: "phone", label: "Telefon", question: "Telefon numaranız?", required: true },
                        ]
                      : local.order_fields,
                });
              }}
            >
              <FieldsEditor
                value={local.order_fields}
                onChange={(fields) => patch({ order_fields: fields })}
              />
            </ModeCard>
          </div>
        )}

        {activeTab === "Advanced" && (
          <ConfigForm />
        )}

        {activeTab === "Prompt" && (
          <SystemPromptPreview />
        )}
      </div>

    </div>
  );
}

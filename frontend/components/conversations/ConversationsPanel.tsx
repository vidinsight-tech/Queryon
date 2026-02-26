"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { conversationsApi } from "@/lib/api";
import type { ConversationListItem, ConversationMessage } from "@/lib/types";
import { MessageSquare, RefreshCw, User, Phone, Mail, X, Clock, ChevronRight, XCircle, ChevronDown, ChevronUp } from "lucide-react";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { relativeTime } from "@/lib/utils";

// ── Thinking toggle (per-message) ─────────────────────────────────────────────
function ThinkingBlock({ thinking }: { thinking: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-1">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1 text-[10px] text-indigo-500 hover:text-indigo-700 transition-colors"
      >
        {open ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
        Düşünce zinciri
      </button>
      {open && (
        <pre className="mt-1 p-2 bg-indigo-50 border border-indigo-100 rounded text-[9px] text-indigo-700 whitespace-pre-wrap font-mono leading-relaxed max-h-32 overflow-y-auto">
          {thinking}
        </pre>
      )}
    </div>
  );
}

// ── Intent colours (matches ChatPreviewPanel) ──────────────────────────────────
const INTENT_COLORS: Record<string, string> = {
  character: "bg-purple-100 text-purple-700",
  rag: "bg-blue-100 text-blue-700",
  rule: "bg-amber-100 text-amber-700",
  tool: "bg-green-100 text-green-700",
  direct: "bg-gray-100 text-gray-600",
};

const LAYER_COLORS: Record<string, string> = {
  pre: "bg-orange-100 text-orange-700",
  embedding: "bg-cyan-100 text-cyan-700",
  llm: "bg-violet-100 text-violet-700",
  cache: "bg-emerald-100 text-emerald-700",
};

// ── Helpers ────────────────────────────────────────────────────────────────────

function shortId(id: string) {
  return id.slice(0, 8) + "…";
}

function contactLabel(conv: ConversationListItem) {
  if (conv.contact_name) return conv.contact_name;
  if (conv.contact_phone) return conv.contact_phone;
  if (conv.contact_email) return conv.contact_email;
  return null;
}

// ── Message thread ─────────────────────────────────────────────────────────────

function MessageThread({ conversationId, onClose }: { conversationId: string; onClose: () => void }) {
  const { data, isLoading } = useQuery({
    queryKey: ["conversation-history", conversationId],
    queryFn: () => conversationsApi.getHistory(conversationId),
    staleTime: 30_000,
  });

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200 bg-gray-50">
        <div>
          <p className="text-xs text-gray-400 font-mono">{conversationId}</p>
          <p className="text-sm font-semibold text-gray-800 mt-0.5">Mesaj Geçmişi</p>
        </div>
        <button onClick={onClose} className="p-1.5 text-gray-400 hover:text-gray-600 rounded-md hover:bg-gray-100">
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {isLoading ? (
          <p className="text-gray-400 text-sm text-center pt-8">Yükleniyor…</p>
        ) : !data || data.messages.length === 0 ? (
          <p className="text-gray-400 text-sm text-center pt-8">Mesaj bulunamadı.</p>
        ) : (
          data.messages.map((msg: ConversationMessage) => (
            <div
              key={msg.id}
              className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-[80%] rounded-2xl px-4 py-2.5 text-sm whitespace-pre-wrap shadow-sm ${
                  msg.role === "user"
                    ? "bg-indigo-600 text-white rounded-br-sm"
                    : "bg-white border border-gray-200 text-gray-800 rounded-bl-sm"
                }`}
              >
                {msg.content}
                {msg.role === "assistant" && msg.intent && (
                  <div className="mt-2 space-y-1">
                    {/* Row 1: intent badge + latency */}
                    <div className="flex items-center gap-2 flex-wrap">
                      <span
                        className={`text-xs px-1.5 py-0.5 rounded font-medium ${
                          INTENT_COLORS[msg.intent] ?? INTENT_COLORS.direct
                        }`}
                      >
                        {msg.intent}
                      </span>
                      {msg.total_ms != null && (
                        <span className="text-xs text-gray-400 flex items-center gap-0.5">
                          <Clock className="w-3 h-3" />
                          {Math.round(msg.total_ms)}ms
                        </span>
                      )}
                      {msg.fallback_used && (
                        <span className="text-xs text-amber-600 font-medium">↩ fallback</span>
                      )}
                    </div>
                    {/* Row 2: confidence + layer + rule/tool */}
                    {(msg.confidence != null || msg.classifier_layer || msg.rule_matched || msg.tool_called) && (
                      <div className="flex items-center gap-1.5 flex-wrap">
                        {msg.confidence != null && (
                          <span className="text-xs text-gray-400 font-mono">
                            {Math.round(msg.confidence * 100)}%
                          </span>
                        )}
                        {msg.classifier_layer && (
                          <span
                            className={`text-xs px-1 py-0.5 rounded font-mono ${
                              LAYER_COLORS[msg.classifier_layer] ?? "bg-gray-100 text-gray-500"
                            }`}
                          >
                            {msg.classifier_layer}
                          </span>
                        )}
                        {msg.rule_matched && (
                          <span className="text-xs text-amber-700 truncate max-w-[140px]" title={msg.rule_matched}>
                            rule: {msg.rule_matched}
                          </span>
                        )}
                        {msg.tool_called && (
                          <span className="text-xs text-green-700 truncate max-w-[140px]" title={msg.tool_called}>
                            tool: {msg.tool_called}
                          </span>
                        )}
                      </div>
                    )}
                    {msg.thinking && <ThinkingBlock thinking={msg.thinking} />}
                  </div>
                )}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

// ── Main panel ─────────────────────────────────────────────────────────────────

export function ConversationsPanel() {
  const qc = useQueryClient();
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const closeMutation = useMutation({
    mutationFn: (id: string) => conversationsApi.delete(id),
    onSuccess: (_, id) => {
      qc.invalidateQueries({ queryKey: ["conversations"] });
      if (selectedId === id) setSelectedId(null);
      toast.success("Konuşma kapatıldı.");
    },
    onError: () => toast.error("Konuşma kapatılamadı."),
  });

  const { data: conversations = [], isLoading, refetch, isFetching } = useQuery({
    queryKey: ["conversations", statusFilter],
    queryFn: () =>
      conversationsApi.list({
        status: statusFilter === "all" ? undefined : statusFilter,
        limit: 100,
      }),
    refetchInterval: 30_000,
  });

  return (
    <div className="flex gap-6 h-[calc(100vh-8rem)]">
      {/* Left: conversation list */}
      <div className="flex flex-col flex-1 min-w-0">
        {/* Toolbar */}
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            {(["all", "active", "closed"] as const).map((s) => (
              <button
                key={s}
                onClick={() => { setStatusFilter(s); setSelectedId(null); }}
                className={`px-3 py-1.5 rounded-full text-sm font-medium transition-colors ${
                  statusFilter === s
                    ? "bg-indigo-600 text-white"
                    : "bg-gray-100 text-gray-600 hover:bg-gray-200"
                }`}
              >
                {s === "all" ? "Tümü" : s === "active" ? "Aktif" : "Kapalı"}
              </button>
            ))}
          </div>
          <button
            onClick={() => refetch()}
            disabled={isFetching}
            className="p-2 text-gray-400 hover:text-gray-600 rounded-md hover:bg-gray-100 disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${isFetching ? "animate-spin" : ""}`} />
          </button>
        </div>

        {/* Table */}
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden flex-1 overflow-y-auto">
          {isLoading ? (
            <p className="text-gray-400 p-6 text-sm">Yükleniyor…</p>
          ) : conversations.length === 0 ? (
            <p className="text-gray-500 p-6 text-sm">Konuşma bulunamadı.</p>
          ) : (
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-xs uppercase text-gray-500 sticky top-0">
                <tr>
                  <th className="px-4 py-3 text-left">ID</th>
                  <th className="px-4 py-3 text-left">Kişi</th>
                  <th className="px-4 py-3 text-left">Platform</th>
                  <th className="px-4 py-3 text-center">Durum</th>
                  <th className="px-4 py-3 text-center">Mesaj</th>
                  <th className="px-4 py-3 text-right">Son Aktivite</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {conversations.map((conv) => {
                  const contact = contactLabel(conv);
                  const isSelected = selectedId === conv.conversation_id;
                  return (
                    <tr
                      key={conv.conversation_id}
                      onClick={() => setSelectedId(isSelected ? null : conv.conversation_id)}
                      className={`group cursor-pointer transition-colors ${
                        isSelected ? "bg-indigo-50" : "hover:bg-gray-50"
                      }`}
                    >
                      <td className="px-4 py-3 font-mono text-xs text-gray-500">
                        {shortId(conv.conversation_id)}
                      </td>
                      <td className="px-4 py-3">
                        {contact ? (
                          <div className="flex items-center gap-1.5 text-gray-700">
                            {conv.contact_phone ? (
                              <Phone className="w-3.5 h-3.5 text-gray-400 shrink-0" />
                            ) : conv.contact_email ? (
                              <Mail className="w-3.5 h-3.5 text-gray-400 shrink-0" />
                            ) : (
                              <User className="w-3.5 h-3.5 text-gray-400 shrink-0" />
                            )}
                            <span className="truncate max-w-[140px]">{contact}</span>
                          </div>
                        ) : (
                          <span className="text-gray-300 text-xs italic">Anonim</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-gray-500 capitalize">{conv.platform}</td>
                      <td className="px-4 py-3 text-center">
                        <StatusBadge status={conv.status} />
                      </td>
                      <td className="px-4 py-3 text-center">
                        <span className="flex items-center justify-center gap-1 text-gray-600">
                          <MessageSquare className="w-3.5 h-3.5 text-gray-300" />
                          {conv.message_count}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-right text-gray-400 text-xs">
                        {relativeTime(conv.last_message_at)}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center justify-end gap-1">
                          {conv.status !== "closed" && (
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                closeMutation.mutate(conv.conversation_id);
                              }}
                              disabled={closeMutation.isPending && closeMutation.variables === conv.conversation_id}
                              title="Konuşmayı kapat"
                              className="p-1 text-gray-300 hover:text-red-500 rounded transition-colors opacity-0 group-hover:opacity-100 disabled:opacity-30"
                            >
                              <XCircle className="w-3.5 h-3.5" />
                            </button>
                          )}
                          <ChevronRight
                            className={`w-4 h-4 transition-transform ${
                              isSelected ? "rotate-90 text-indigo-600" : "text-gray-300"
                            }`}
                          />
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* Right: message thread */}
      {selectedId && (
        <div className="w-[420px] shrink-0 bg-white rounded-xl border border-gray-200 overflow-hidden flex flex-col">
          <MessageThread
            conversationId={selectedId}
            onClose={() => setSelectedId(null)}
          />
        </div>
      )}
    </div>
  );
}

"use client";
import { useState, useRef, useEffect } from "react";
import { MessageCircle, X, RotateCcw, Send, Loader2, ChevronDown, ChevronUp } from "lucide-react";
import { chatApi } from "@/lib/api";
import type { ChatResponse } from "@/lib/types";

interface DebugInfo {
  intent?: string;
  confidence?: number | null;
  classifier_layer?: string | null;
  rule_matched?: string | null;
  tool_called?: string | null;
  fallback_used?: boolean;
  total_ms?: number | null;
  sources?: Array<{ title?: string; content?: string; score?: number }>;
  thinking?: string | null;
  reasoning?: string | null;
}

interface Message {
  role: "user" | "assistant";
  content: string;
  debug?: DebugInfo;
  debugOpen?: boolean;
}

const INTENT_COLORS: Record<string, string> = {
  character: "bg-purple-100 text-purple-700",
  rag: "bg-blue-100 text-blue-700",
  rule: "bg-amber-100 text-amber-700",
  tool: "bg-green-100 text-green-700",
  direct: "bg-gray-100 text-gray-600",
};

function DebugPanel({ debug }: { debug: DebugInfo }) {
  const [thinkingOpen, setThinkingOpen] = useState(false);
  return (
    <div className="mt-2 pt-2 border-t border-gray-200 space-y-1 text-[11px] text-gray-500">
      <div className="flex flex-wrap gap-x-3 gap-y-0.5">
        {debug.intent && (
          <span>
            <span className="font-medium">Intent:</span> {debug.intent}
            {debug.confidence != null && ` (${debug.confidence.toFixed(2)})`}
          </span>
        )}
        {debug.classifier_layer && (
          <span>
            <span className="font-medium">Layer:</span> {debug.classifier_layer}
          </span>
        )}
        {debug.total_ms != null && (
          <span>
            <span className="font-medium">Time:</span> {Math.round(debug.total_ms)}ms
          </span>
        )}
      </div>
      {debug.reasoning && (
        <div>
          <span className="font-medium">Reasoning:</span>{" "}
          <span className="italic">{debug.reasoning}</span>
        </div>
      )}
      {(debug.rule_matched || debug.tool_called || debug.fallback_used) && (
        <div className="flex flex-wrap gap-x-3 gap-y-0.5">
          {debug.rule_matched && (
            <span>
              <span className="font-medium">Rule:</span> {debug.rule_matched}
            </span>
          )}
          {debug.tool_called && (
            <span>
              <span className="font-medium">Tool:</span> {debug.tool_called}
            </span>
          )}
          {debug.fallback_used && (
            <span className="text-amber-600 font-medium">↩ fallback</span>
          )}
        </div>
      )}
      {debug.sources && debug.sources.length > 0 && (
        <div>
          <span className="font-medium">Sources ({debug.sources.length}):</span>
          <ul className="mt-0.5 ml-2 space-y-0.5">
            {debug.sources.slice(0, 3).map((s, i) => (
              <li key={i} className="truncate">
                {s.title ?? "(untitled)"}
                {s.score != null && (
                  <span className="ml-1 text-gray-400">({s.score.toFixed(2)})</span>
                )}
              </li>
            ))}
            {debug.sources.length > 3 && (
              <li className="text-gray-400 italic">+{debug.sources.length - 3} daha…</li>
            )}
          </ul>
        </div>
      )}
      {debug.thinking && (
        <div>
          <button
            onClick={() => setThinkingOpen((o) => !o)}
            className="flex items-center gap-1 text-indigo-500 hover:text-indigo-700 transition-colors"
          >
            {thinkingOpen ? (
              <ChevronUp className="w-3 h-3" />
            ) : (
              <ChevronDown className="w-3 h-3" />
            )}
            <span className="font-medium">Düşünce zinciri</span>
          </button>
          {thinkingOpen && (
            <pre className="mt-1 p-2 bg-indigo-50 border border-indigo-100 rounded text-[10px] text-indigo-700 whitespace-pre-wrap font-mono leading-relaxed max-h-40 overflow-y-auto">
              {debug.thinking}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}

export function ChatPreviewPanel() {
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (isOpen) {
      messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, isOpen]);

  function handleReset() {
    setMessages([]);
    setConversationId(null);
    setInput("");
  }

  function toggleDebug(idx: number) {
    setMessages((prev) =>
      prev.map((m, i) => (i === idx ? { ...m, debugOpen: !m.debugOpen } : m))
    );
  }

  async function handleSend() {
    const query = input.trim();
    if (!query || loading) return;

    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: query }]);
    setLoading(true);

    try {
      const res: ChatResponse = await chatApi.send(query, conversationId ?? undefined);
      if (!conversationId && res.conversation_id) {
        setConversationId(res.conversation_id);
      }
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: res.answer ?? "(boş yanıt)",
          debug: {
            intent: res.intent ?? undefined,
            confidence: res.confidence,
            classifier_layer: res.classifier_layer,
            rule_matched: res.rule_matched,
            tool_called: res.tool_called,
            fallback_used: res.fallback_used,
            total_ms: res.total_ms,
            sources: res.sources,
            thinking: res.thinking,
            reasoning: res.reasoning,
          },
          debugOpen: false,
        },
      ]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `Hata: ${(err as Error).message}`,
          debug: { intent: "direct" },
          debugOpen: false,
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  return (
    <>
      {/* Floating toggle button */}
      <button
        onClick={() => setIsOpen((o) => !o)}
        aria-label="Bot Testi"
        className="fixed bottom-6 right-6 z-50 w-12 h-12 bg-indigo-600 text-white rounded-full shadow-lg flex items-center justify-center hover:bg-indigo-700 transition-colors"
      >
        <MessageCircle className="w-5 h-5" />
      </button>

      {/* Chat panel */}
      {isOpen && (
        <div
          className="fixed bottom-22 right-6 z-50 w-[420px] h-[580px] bg-white rounded-2xl shadow-2xl border border-gray-200 flex flex-col overflow-hidden"
          style={{ bottom: "5rem" }}
        >
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100 bg-gray-50">
            <span className="font-semibold text-sm text-gray-800">Bot Test</span>
            <div className="flex items-center gap-2">
              <button
                onClick={handleReset}
                title="Yeni konuşma"
                className="text-gray-400 hover:text-gray-600 transition-colors"
              >
                <RotateCcw className="w-4 h-4" />
              </button>
              <button
                onClick={() => setIsOpen(false)}
                title="Kapat"
                className="text-gray-400 hover:text-gray-600 transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
            {messages.length === 0 && (
              <p className="text-xs text-gray-400 text-center mt-8">
                Botu test etmek için mesaj yaz…
              </p>
            )}
            {messages.map((msg, idx) => (
              <div
                key={idx}
                className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
              >
                <div
                  className={`max-w-[85%] ${
                    msg.role === "user"
                      ? "bg-indigo-600 text-white rounded-2xl rounded-tr-sm"
                      : "bg-gray-100 text-gray-800 rounded-2xl rounded-tl-sm"
                  } px-3.5 py-2.5`}
                >
                  {msg.role === "assistant" && msg.debug?.intent && (
                    <span
                      className={`inline-block text-[10px] font-medium px-1.5 py-0.5 rounded mb-1.5 ${
                        INTENT_COLORS[msg.debug.intent] ?? "bg-gray-100 text-gray-600"
                      }`}
                    >
                      {msg.debug.intent}
                    </span>
                  )}
                  <p className="text-sm whitespace-pre-wrap">{msg.content}</p>

                  {/* Debug toggle */}
                  {msg.role === "assistant" && msg.debug && (
                    <>
                      <button
                        onClick={() => toggleDebug(idx)}
                        className="mt-2 flex items-center gap-1 text-[11px] text-gray-400 hover:text-gray-600 transition-colors"
                      >
                        {msg.debugOpen ? (
                          <ChevronUp className="w-3 h-3" />
                        ) : (
                          <ChevronDown className="w-3 h-3" />
                        )}
                        Detay
                      </button>
                      {msg.debugOpen && <DebugPanel debug={msg.debug} />}
                    </>
                  )}
                </div>
              </div>
            ))}
            {loading && (
              <div className="flex justify-start">
                <div className="bg-gray-100 rounded-2xl rounded-tl-sm px-3.5 py-2.5">
                  <Loader2 className="w-4 h-4 text-gray-400 animate-spin" />
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Input */}
          <div className="px-3 py-3 border-t border-gray-100 bg-gray-50">
            <div className="flex gap-2">
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                disabled={loading}
                placeholder="Mesaj yaz…"
                className="flex-1 text-sm border border-gray-300 rounded-xl px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-50"
              />
              <button
                onClick={handleSend}
                disabled={!input.trim() || loading}
                className="w-9 h-9 bg-indigo-600 text-white rounded-xl flex items-center justify-center hover:bg-indigo-700 disabled:opacity-40 transition-colors"
              >
                <Send className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

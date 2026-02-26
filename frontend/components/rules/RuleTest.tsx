"use client";
import { useState, useRef, useEffect, KeyboardEvent } from "react";
import { chatApi } from "@/lib/api";
import type { ChatResponse } from "@/lib/types";
import { Send, RefreshCw, Loader2 } from "lucide-react";

type UserMessage = {
  role: "user";
  text: string;
};

type AssistantMessage = {
  role: "assistant";
  text: string;
  meta: ChatResponse;
};

type Message = UserMessage | AssistantMessage;

const INTENT_COLORS: Record<string, string> = {
  rule: "bg-indigo-50 text-indigo-700",
  direct: "bg-blue-50 text-blue-700",
  rag: "bg-green-50 text-green-700",
  tool: "bg-orange-50 text-orange-700",
};

function Badge({
  label,
  value,
  colorClass,
}: {
  label: string;
  value: string | number;
  colorClass?: string;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium ${
        colorClass ?? "bg-gray-100 text-gray-600"
      }`}
    >
      <span className="text-gray-400 font-normal">{label}:</span>
      {value}
    </span>
  );
}

function MetaBadges({ meta }: { meta: ChatResponse }) {
  const intentColor = INTENT_COLORS[meta.intent] ?? "bg-gray-100 text-gray-600";
  return (
    <div className="flex flex-wrap gap-1.5 mt-2">
      <Badge label="intent" value={meta.intent} colorClass={intentColor} />
      {meta.classifier_layer && (
        <Badge label="layer" value={meta.classifier_layer} />
      )}
      {meta.confidence !== null && (
        <Badge
          label="confidence"
          value={`${((meta.confidence ?? 0) * 100).toFixed(0)}%`}
        />
      )}
      {meta.rule_matched && (
        <Badge label="rule" value={meta.rule_matched} colorClass="bg-indigo-50 text-indigo-700" />
      )}
      {meta.tool_called && (
        <Badge label="tool" value={meta.tool_called} colorClass="bg-orange-50 text-orange-700" />
      )}
      {meta.needs_clarification && (
        <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-yellow-50 text-yellow-700">
          needs clarification
        </span>
      )}
      {meta.total_ms !== null && (
        <Badge label="ms" value={meta.total_ms} />
      )}
    </div>
  );
}

export function RuleTest() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [conversationId, setConversationId] = useState<string | undefined>(undefined);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const send = async () => {
    const text = input.trim();
    if (!text || loading) return;

    setInput("");
    setError(null);
    setMessages((prev) => [...prev, { role: "user", text }]);
    setLoading(true);

    try {
      const response = await chatApi.send(text, conversationId);
      if (!conversationId) {
        setConversationId(response.conversation_id);
      }
      setMessages((prev) => [
        ...prev,
        { role: "assistant", text: response.answer, meta: response },
      ]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  const handleNewConversation = () => {
    setMessages([]);
    setConversationId(undefined);
    setError(null);
    setInput("");
  };

  return (
    <div className="flex flex-col h-[calc(100vh-200px)] max-h-[700px]">
      {/* Toolbar */}
      <div className="flex items-center justify-between mb-3">
        <div className="text-xs text-gray-400">
          {conversationId ? (
            <span>
              Conversation:{" "}
              <code className="font-mono">{conversationId.slice(0, 8)}…</code>
            </span>
          ) : (
            <span>No active conversation</span>
          )}
        </div>
        <button
          onClick={handleNewConversation}
          className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-700 border border-gray-200 rounded-md px-3 py-1.5 hover:bg-gray-50 transition-colors"
        >
          <RefreshCw className="w-3.5 h-3.5" />
          New Conversation
        </button>
      </div>

      {/* Chat area */}
      <div className="flex-1 bg-white rounded-xl border border-gray-200 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 && !loading && (
          <div className="h-full flex items-center justify-center text-gray-400 text-sm">
            Type a message below to test your rules.
          </div>
        )}

        {messages.map((msg, idx) => {
          if (msg.role === "user") {
            return (
              <div key={idx} className="flex justify-end">
                <div className="max-w-sm bg-indigo-600 text-white text-sm rounded-2xl rounded-br-sm px-4 py-2.5">
                  {msg.text}
                </div>
              </div>
            );
          }

          return (
            <div key={idx} className="flex justify-start">
              <div className="max-w-lg">
                <div className="bg-gray-100 text-gray-800 text-sm rounded-2xl rounded-bl-sm px-4 py-2.5">
                  {msg.text}
                </div>
                <MetaBadges meta={msg.meta} />
              </div>
            </div>
          );
        })}

        {loading && (
          <div className="flex justify-start">
            <div className="bg-gray-100 text-gray-400 text-sm rounded-2xl rounded-bl-sm px-4 py-2.5 flex items-center gap-2">
              <Loader2 className="w-4 h-4 animate-spin" />
              Thinking…
            </div>
          </div>
        )}

        {error && (
          <div className="flex justify-start">
            <div className="bg-red-50 text-red-600 text-sm rounded-xl px-4 py-2.5 border border-red-100">
              {error}
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input area */}
      <div className="mt-3 flex gap-2 items-end">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={loading}
          rows={2}
          placeholder="Type a message… (Enter to send, Shift+Enter for newline)"
          className="flex-1 border border-gray-300 rounded-xl px-4 py-2.5 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-50"
        />
        <button
          onClick={send}
          disabled={loading || !input.trim()}
          className="bg-indigo-600 text-white p-2.5 rounded-xl hover:bg-indigo-700 disabled:opacity-50 transition-colors shrink-0"
        >
          {loading ? (
            <Loader2 className="w-5 h-5 animate-spin" />
          ) : (
            <Send className="w-5 h-5" />
          )}
        </button>
      </div>
    </div>
  );
}

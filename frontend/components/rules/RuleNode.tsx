"use client";
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { rulesApi } from "@/lib/api";
import type { Rule } from "@/lib/types";
import { RuleForm } from "./RuleForm";
import {
  Pencil,
  Trash2,
  ChevronRight,
  ArrowRight,
  MessageSquare,
  Zap,
  Clock,
  Monitor,
} from "lucide-react";

function buildSummary(rule: Rule): string {
  const triggers = rule.trigger_patterns.slice(0, 3).map((t) => `"${t}"`).join(", ");
  const more = rule.trigger_patterns.length > 3 ? ` +${rule.trigger_patterns.length - 3}` : "";
  const response = (rule.response_template || "").split("\n")[0].slice(0, 80);
  const respSuffix = (rule.response_template || "").length > 80 ? "…" : "";

  let summary = `Eğer ${triggers}${more} derse → ${response}${respSuffix}`;

  if (rule.required_step) {
    summary = `[${rule.required_step} adımındayken] ${summary}`;
  }

  return summary;
}

function ConditionBadges({ rule }: { rule: Rule }) {
  const conditions = (rule as any).conditions;
  if (!conditions) return null;

  const badges: { icon: React.ReactNode; text: string }[] = [];

  if (conditions.time_window) {
    const tw = conditions.time_window;
    badges.push({
      icon: <Clock className="w-3 h-3" />,
      text: `${tw.start || "?"} – ${tw.end || "?"}`,
    });
  }

  if (conditions.platforms && Array.isArray(conditions.platforms)) {
    badges.push({
      icon: <Monitor className="w-3 h-3" />,
      text: conditions.platforms.join(", "),
    });
  }

  if (badges.length === 0) return null;

  return (
    <div className="flex items-center gap-1.5 mt-1.5">
      <span className="text-xs text-gray-400">Koşullar:</span>
      {badges.map((b, i) => (
        <span
          key={i}
          className="inline-flex items-center gap-1 text-xs text-amber-700 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded-full"
        >
          {b.icon} {b.text}
        </span>
      ))}
    </div>
  );
}

interface Props {
  rule: Rule;
  showFlowArrow?: boolean;
}

export function RuleNode({ rule, showFlowArrow }: Props) {
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [expanded, setExpanded] = useState(false);

  const deleteMutation = useMutation({
    mutationFn: () => rulesApi.delete(rule.id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["rule-tree"] }),
  });

  const summary = buildSummary(rule);

  return (
    <>
      <div className="bg-white border border-gray-200 rounded-lg hover:border-indigo-300 transition-colors overflow-hidden">
        {/* Summary bar */}
        <div
          className="px-4 py-3 cursor-pointer flex items-start justify-between gap-3"
          onClick={() => setExpanded((v) => !v)}
        >
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap mb-1">
              <Zap className="w-3.5 h-3.5 text-indigo-500 shrink-0" />
              <span className="font-semibold text-sm text-gray-900 truncate">{rule.name}</span>
              <span
                className={`text-xs px-1.5 py-0.5 rounded-full font-medium ${
                  rule.is_active
                    ? "bg-green-50 text-green-700 border border-green-200"
                    : "bg-gray-100 text-gray-500 border border-gray-200"
                }`}
              >
                {rule.is_active ? "Aktif" : "Pasif"}
              </span>
              {rule.priority > 0 && (
                <span className="text-xs bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded-full">
                  Öncelik: {rule.priority}
                </span>
              )}
              {rule.step_key && (
                <span className="text-xs bg-indigo-50 text-indigo-600 px-1.5 py-0.5 rounded-full font-mono">
                  Adım: {rule.step_key}
                </span>
              )}
            </div>

            {/* Natural language summary */}
            <p className="text-xs text-gray-600 leading-relaxed">
              {summary}
            </p>

            <ConditionBadges rule={rule} />
          </div>

          <div className="flex items-center gap-1.5 shrink-0">
            <button
              onClick={(e) => { e.stopPropagation(); setEditing(true); }}
              className="p-1.5 text-gray-400 hover:text-indigo-600 rounded-md hover:bg-indigo-50 transition-colors"
              title="Düzenle"
            >
              <Pencil className="w-3.5 h-3.5" />
            </button>
            {confirming ? (
              <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
                <span className="text-xs text-red-600">Sil?</span>
                <button
                  onClick={() => deleteMutation.mutate()}
                  className="text-xs text-red-600 font-medium hover:underline"
                >
                  Evet
                </button>
                <button
                  onClick={() => setConfirming(false)}
                  className="text-xs text-gray-500 hover:underline"
                >
                  Hayır
                </button>
              </div>
            ) : (
              <button
                onClick={(e) => { e.stopPropagation(); setConfirming(true); }}
                className="p-1.5 text-gray-400 hover:text-red-500 rounded-md hover:bg-red-50 transition-colors"
                title="Sil"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
        </div>

        {/* Expanded detail */}
        {expanded && (
          <div className="border-t border-gray-100 px-4 py-3 bg-gray-50/50 space-y-3">
            {/* If section */}
            <div>
              <div className="flex items-center gap-1.5 mb-1.5">
                <span className="text-xs font-semibold text-indigo-600 uppercase tracking-wider">Eğer</span>
                <span className="text-xs text-gray-400">kullanıcı şunları derse:</span>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {rule.trigger_patterns.map((p, i) => (
                  <code
                    key={i}
                    className="text-xs bg-indigo-50 text-indigo-700 px-2.5 py-1 rounded-md border border-indigo-100"
                  >
                    {p}
                  </code>
                ))}
              </div>
            </div>

            {/* Then section */}
            <div>
              <div className="flex items-center gap-1.5 mb-1.5">
                <ArrowRight className="w-3 h-3 text-green-600" />
                <span className="text-xs font-semibold text-green-700 uppercase tracking-wider">O zaman</span>
                <span className="text-xs text-gray-400">bot şu cevabı verir:</span>
              </div>
              <div className="bg-white border border-gray-200 rounded-md px-3 py-2">
                <div className="flex items-start gap-2">
                  <MessageSquare className="w-3.5 h-3.5 text-gray-400 mt-0.5 shrink-0" />
                  <pre className="text-xs text-gray-700 whitespace-pre-wrap font-sans leading-relaxed">{rule.response_template}</pre>
                </div>
              </div>
            </div>

            {/* Next steps */}
            {rule.next_steps && Object.keys(rule.next_steps).length > 0 && (
              <div>
                <div className="flex items-center gap-1.5 mb-1.5">
                  <ChevronRight className="w-3 h-3 text-purple-600" />
                  <span className="text-xs font-semibold text-purple-700 uppercase tracking-wider">Sonra</span>
                  <span className="text-xs text-gray-400">kullanıcının cevabına göre:</span>
                </div>
                <div className="space-y-1">
                  {Object.entries(rule.next_steps).map(([choice, nextStep]) => (
                    <div
                      key={choice}
                      className="flex items-center gap-2 text-xs bg-purple-50 border border-purple-100 rounded-md px-3 py-1.5"
                    >
                      <span className="font-medium text-purple-800">"{choice}"</span>
                      <ArrowRight className="w-3 h-3 text-purple-400" />
                      <span className="font-mono text-purple-600">{nextStep}</span>
                      <span className="text-purple-400">adımına geç</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Description */}
            {rule.description && (
              <div className="pt-2 border-t border-gray-100">
                <span className="text-xs text-gray-400">Açıklama: </span>
                <span className="text-xs text-gray-600">{rule.description}</span>
              </div>
            )}
          </div>
        )}
      </div>

      {showFlowArrow && (
        <div className="flex justify-center py-0.5">
          <div className="flex flex-col items-center">
            <div className="w-0.5 h-3 bg-indigo-300" />
            <ChevronRight className="w-3 h-3 text-indigo-400 rotate-90" />
          </div>
        </div>
      )}
      {editing && <RuleForm rule={rule} onClose={() => setEditing(false)} />}
    </>
  );
}

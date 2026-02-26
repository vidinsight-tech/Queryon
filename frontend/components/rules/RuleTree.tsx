"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { rulesApi } from "@/lib/api";
import type { Flow, Rule, RuleTree } from "@/lib/types";
import dynamic from "next/dynamic";
import { RuleNode } from "./RuleNode";

const RuleForm = dynamic(
  () => import("./RuleForm").then((m) => m.RuleForm),
  { ssr: false, loading: () => null }
);
import {
  ChevronDown,
  ChevronRight,
  GitBranch,
  Plus,
  List,
  Zap,
  ArrowRight,
} from "lucide-react";

function FlowNode({ flow }: { flow: Flow }) {
  const [open, setOpen] = useState(true);

  const entryRule = flow.rules.find((r) => !r.required_step);
  const stepCount = flow.rules.length;

  return (
    <div className="mb-5">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 w-full text-left px-4 py-3 bg-purple-50 border border-purple-200 rounded-lg hover:bg-purple-100 transition-colors"
      >
        {open ? (
          <ChevronDown className="w-4 h-4 text-purple-600" />
        ) : (
          <ChevronRight className="w-4 h-4 text-purple-600" />
        )}
        <GitBranch className="w-4 h-4 text-purple-600" />
        <div className="flex-1 min-w-0">
          <span className="font-semibold text-sm text-purple-800">{flow.flow_id}</span>
          <span className="text-xs text-purple-500 ml-2">{stepCount} adım</span>
        </div>
        {entryRule && (
          <span className="text-xs text-purple-400 hidden sm:inline truncate max-w-[200px]">
            Giriş: "{entryRule.trigger_patterns[0]}"
          </span>
        )}
      </button>

      {open && (
        <div className="mt-2 ml-4 pl-4 border-l-2 border-purple-200 space-y-0.5">
          {flow.rules.map((rule, i) => (
            <div key={rule.id}>
              {i > 0 && (
                <div className="flex items-center gap-1.5 py-1 pl-2">
                  <div className="w-0.5 h-3 bg-purple-200" />
                </div>
              )}
              <RuleNode
                rule={rule}
                showFlowArrow={false}
              />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function RuleTreeView() {
  const [showForm, setShowForm] = useState(false);
  const [activeOnly, setActiveOnly] = useState(false);

  const { data, isLoading, isError } = useQuery<RuleTree>({
    queryKey: ["rule-tree", activeOnly],
    queryFn: () => rulesApi.tree(activeOnly),
  });

  const totalRules = data
    ? data.standalone_rules.length + data.flows.reduce((s, f) => s + f.rules.length, 0)
    : 0;

  return (
    <div>
      {/* Toolbar */}
      <div className="flex items-center justify-between mb-5">
        <div className="flex items-center gap-4">
          <label className="flex items-center gap-2 text-sm text-gray-600 cursor-pointer">
            <input
              type="checkbox"
              checked={activeOnly}
              onChange={(e) => setActiveOnly(e.target.checked)}
              className="rounded border-gray-300 accent-indigo-600"
            />
            Sadece aktifler
          </label>
          {data && (
            <span className="text-xs text-gray-400">
              Toplam {totalRules} kural
            </span>
          )}
        </div>
        <button
          onClick={() => setShowForm(true)}
          className="flex items-center gap-2 bg-indigo-600 text-white px-4 py-2 rounded-md text-sm font-medium hover:bg-indigo-700 transition-colors"
        >
          <Plus className="w-4 h-4" />
          Yeni Kural
        </button>
      </div>

      {isLoading && <p className="text-gray-400">Kurallar yükleniyor…</p>}
      {isError && <p className="text-red-500">Kurallar yüklenemedi.</p>}

      {data && (
        <div className="space-y-6">
          {/* Flows */}
          {data.flows.length > 0 && (
            <section>
              <h2 className="text-xs uppercase tracking-wider text-gray-400 font-semibold mb-3 flex items-center gap-2">
                <GitBranch className="w-3.5 h-3.5" />
                Çok Adımlı Akışlar ({data.flows.length})
              </h2>
              <p className="text-xs text-gray-400 mb-3">
                Kullanıcının cevabına göre dallanan, adım adım ilerleyen kurallar.
              </p>
              {data.flows.map((flow) => (
                <FlowNode key={flow.flow_id} flow={flow} />
              ))}
            </section>
          )}

          {/* Standalone rules */}
          {data.standalone_rules.length > 0 && (
            <section>
              <h2 className="text-xs uppercase tracking-wider text-gray-400 font-semibold mb-3 flex items-center gap-2">
                <Zap className="w-3.5 h-3.5" />
                Tekil Kurallar ({data.standalone_rules.length})
              </h2>
              <p className="text-xs text-gray-400 mb-3">
                Eğer X derse → Y cevabını ver. Tek seferlik, bağımsız kurallar.
              </p>
              <div className="space-y-2">
                {data.standalone_rules.map((rule) => (
                  <RuleNode key={rule.id} rule={rule} />
                ))}
              </div>
            </section>
          )}

          {data.flows.length === 0 && data.standalone_rules.length === 0 && (
            <div className="text-center py-16 text-gray-400">
              <Zap className="w-10 h-10 mx-auto mb-3 opacity-30" />
              <p className="text-sm">Henüz kural yok.</p>
              <p className="text-xs mt-1">Yukarıdaki "Yeni Kural" butonuyla başlayın.</p>
            </div>
          )}
        </div>
      )}

      {showForm && <RuleForm onClose={() => setShowForm(false)} />}
    </div>
  );
}

import { RuleTreeView } from "@/components/rules/RuleTree";

export const metadata = { title: "Rules — Queryon" };

export default function RulesPage() {
  return (
    <div>
      <h1 className="text-2xl font-bold mb-1">Rules & Flows</h1>
      <p className="text-sm text-gray-500 mb-6">
        Create deterministic rules and multi-step conversation flows.
      </p>
      <RuleTreeView />
    </div>
  );
}

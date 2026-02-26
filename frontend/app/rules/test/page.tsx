import { RuleTest } from "@/components/rules/RuleTest";

export const metadata = { title: "Test Rules — Queryon" };

export default function RuleTestPage() {
  return (
    <div>
      <h1 className="text-2xl font-bold mb-1">Test Rules</h1>
      <p className="text-sm text-gray-500 mb-6">
        Send messages to the orchestrator and see which rule or intent was matched.
      </p>
      <RuleTest />
    </div>
  );
}

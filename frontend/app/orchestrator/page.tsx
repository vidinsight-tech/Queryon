import { BotBuilderPanel } from "@/components/bot/BotBuilderPanel";

export const metadata = { title: "Bot Builder — Queryon" };

export default function OrchestratorPage() {
  return (
    <div>
      <h1 className="text-2xl font-bold mb-1">Bot Builder</h1>
      <p className="text-sm text-gray-500 mb-6">
        Botunuzun kimliğini, modlarını ve davranışını yapılandırın.
      </p>
      <BotBuilderPanel />
    </div>
  );
}

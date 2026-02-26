import { LLMList } from "@/components/llms/LLMList";

export const metadata = { title: "LLMs — Queryon" };

export default function LLMsPage() {
  return (
    <div>
      <h1 className="text-2xl font-bold mb-1">Language Models</h1>
      <p className="text-sm text-gray-500 mb-6">
        Add and manage LLM providers (OpenAI, Gemini). Active models are used by the orchestrator.
      </p>
      <LLMList />
    </div>
  );
}

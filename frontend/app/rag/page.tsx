import { RagConfig } from "@/components/rag/RagConfig";

export const metadata = { title: "RAG Config — Queryon" };

export default function RagPage() {
  return (
    <div>
      <h1 className="text-2xl font-bold mb-1">RAG Configuration</h1>
      <p className="text-sm text-gray-500 mb-6">
        Connect an LLM and embedding model to power the knowledge base search.
      </p>
      <RagConfig />
    </div>
  );
}

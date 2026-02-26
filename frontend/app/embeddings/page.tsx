import { EmbeddingList } from "@/components/embeddings/EmbeddingList";

export const metadata = { title: "Embedding Models — Queryon" };

export default function EmbeddingsPage() {
  return (
    <div>
      <h1 className="text-2xl font-bold mb-1">Embedding Models</h1>
      <p className="text-sm text-gray-500 mb-6">
        Configure embedding providers for RAG document search.
      </p>
      <EmbeddingList />
    </div>
  );
}

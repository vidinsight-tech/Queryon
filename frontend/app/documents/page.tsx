import { DocumentList } from "@/components/documents/DocumentList";

export const metadata = { title: "Knowledge Base — Queryon" };

export default function DocumentsPage() {
  return (
    <div>
      <h1 className="text-2xl font-bold mb-1">Knowledge Base</h1>
      <p className="text-sm text-gray-500 mb-6">
        Upload documents (PDF, DOCX, TXT) to the vector database. Requires an active embedding model configured in RAG settings.
      </p>
      <DocumentList />
    </div>
  );
}

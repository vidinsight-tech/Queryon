import { ConversationsPanel } from "@/components/conversations/ConversationsPanel";

export default function ConversationsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Konuşmalar</h1>
        <p className="text-sm text-gray-500 mt-1">
          Tüm bot konuşmalarını görüntüleyin ve mesaj geçmişini inceleyin.
        </p>
      </div>
      <ConversationsPanel />
    </div>
  );
}

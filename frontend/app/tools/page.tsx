import { ToolList } from "@/components/tools/ToolList";

export const metadata = { title: "Tools — Queryon" };

export default function ToolsPage() {
  return (
    <div>
      <h1 className="text-2xl font-bold mb-1">Tools</h1>
      <p className="text-sm text-gray-500 mb-6">
        Manage built-in and custom tools the chatbot can call.
      </p>
      <ToolList />
    </div>
  );
}

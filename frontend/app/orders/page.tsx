import { OrdersPanel } from "@/components/orders/OrdersPanel";

export const metadata = { title: "Orders — Queryon" };

export default function OrdersPage() {
  return (
    <div>
      <h1 className="text-2xl font-bold mb-1">Siparişler</h1>
      <p className="text-sm text-gray-500 mb-6">
        Chatbot aracılığıyla alınan sipariş kayıtları.
      </p>
      <OrdersPanel />
    </div>
  );
}

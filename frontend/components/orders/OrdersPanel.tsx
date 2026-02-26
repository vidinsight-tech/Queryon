"use client";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { ordersApi } from "@/lib/api";
import type { Order } from "@/lib/types";
import { ShoppingBag, Check, X, Trash2, RefreshCw, Phone, Mail, Eye, Loader2 } from "lucide-react";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { formatDateTime } from "@/lib/utils";
import dynamic from "next/dynamic";

const OrderDetailModal = dynamic(
  () => import("./OrderDetailModal").then((m) => m.OrderDetailModal),
  { ssr: false, loading: () => null }
);

const STATUS_FILTERS = [
  { value: "all",       label: "Tümü" },
  { value: "pending",   label: "Bekliyor" },
  { value: "confirmed", label: "Onaylandı" },
  { value: "cancelled", label: "İptal" },
] as const;

function TableSkeleton() {
  return (
    <div className="bg-white border border-gray-200 rounded-lg overflow-hidden animate-pulse">
      <div className="bg-gray-50 border-b border-gray-200 h-10" />
      {[...Array(5)].map((_, i) => (
        <div key={i} className="flex gap-4 px-4 py-3 border-b border-gray-100 last:border-0">
          {[...Array(6)].map((_, j) => (
            <div key={j} className="h-4 bg-gray-200 rounded flex-1" />
          ))}
        </div>
      ))}
    </div>
  );
}

export function OrdersPanel() {
  const qc = useQueryClient();
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [selectedOrder, setSelectedOrder] = useState<Order | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);

  const { data: orders = [], isLoading, refetch, isFetching } = useQuery({
    queryKey: ["orders", statusFilter],
    queryFn: () => ordersApi.list(statusFilter === "all" ? undefined : statusFilter),
    refetchInterval: 30_000,
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) =>
      ordersApi.updateStatus(id, status),
    onSuccess: (_, { status }) => {
      qc.invalidateQueries({ queryKey: ["orders"] });
      const label = status === "confirmed" ? "onaylandı" : status === "cancelled" ? "iptal edildi" : "güncellendi";
      toast.success(`Sipariş ${label}.`);
    },
    onError: () => toast.error("Durum güncellenemedi."),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => ordersApi.delete(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["orders"] });
      setDeleteTarget(null);
      toast.success("Sipariş silindi.");
    },
    onError: () => toast.error("Sipariş silinemedi."),
  });

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex gap-1.5 flex-wrap">
          {STATUS_FILTERS.map(({ value, label }) => (
            <button
              key={value}
              onClick={() => setStatusFilter(value)}
              className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                statusFilter === value
                  ? "bg-indigo-600 text-white"
                  : "bg-white border border-gray-200 text-gray-600 hover:bg-gray-50"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
        <button
          onClick={() => refetch()}
          disabled={isFetching}
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-gray-600 border border-gray-200 rounded-md hover:bg-gray-50 disabled:opacity-50 transition-colors"
        >
          {isFetching ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
          Yenile
        </button>
      </div>

      {isLoading ? (
        <TableSkeleton />
      ) : orders.length === 0 ? (
        <EmptyState
          icon={<ShoppingBag className="w-6 h-6" />}
          title="Henüz sipariş yok"
          description={statusFilter !== "all" ? "Bu filtrede kayıt bulunamadı." : "Müşteriler bot üzerinden sipariş verdiğinde burada görünecek."}
        />
      ) : (
        <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className="px-4 py-3 text-left font-semibold text-gray-600">Müşteri</th>
                  <th className="px-4 py-3 text-left font-semibold text-gray-600">İletişim</th>
                  <th className="px-4 py-3 text-left font-semibold text-gray-600">Notlar</th>
                  <th className="px-4 py-3 text-left font-semibold text-gray-600">Durum</th>
                  <th className="px-4 py-3 text-left font-semibold text-gray-600">Oluşturuldu</th>
                  <th className="px-4 py-3 text-right font-semibold text-gray-600">İşlem</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {orders.map((order: Order) => (
                  <tr key={order.id} className="hover:bg-gray-50 transition-colors">
                    <td className="px-4 py-3 font-medium text-gray-900 text-xs">
                      {[order.contact_name, order.contact_surname].filter(Boolean).join(" ") || "—"}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-col gap-0.5 text-xs text-gray-600">
                        {order.contact_phone && (
                          <span className="flex items-center gap-1"><Phone className="w-3 h-3" />{order.contact_phone}</span>
                        )}
                        {order.contact_email && (
                          <span className="flex items-center gap-1"><Mail className="w-3 h-3" />{order.contact_email}</span>
                        )}
                        {!order.contact_phone && !order.contact_email && "—"}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-gray-600 text-xs max-w-xs truncate">{order.notes ?? "—"}</td>
                    <td className="px-4 py-3"><StatusBadge status={order.status} /></td>
                    <td className="px-4 py-3 text-gray-400 text-xs">{formatDateTime(order.created_at)}</td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end gap-1">
                        <button onClick={() => setSelectedOrder(order)} className="p-1.5 rounded-md text-indigo-500 hover:bg-indigo-50 transition-colors" title="Detay">
                          <Eye className="w-4 h-4" />
                        </button>
                        {order.status === "pending" && (
                          <>
                            <button onClick={() => updateMutation.mutate({ id: order.id, status: "confirmed" })} disabled={updateMutation.isPending} className="p-1.5 rounded-md text-green-600 hover:bg-green-50 disabled:opacity-40 transition-colors" title="Onayla">
                              <Check className="w-4 h-4" />
                            </button>
                            <button onClick={() => updateMutation.mutate({ id: order.id, status: "cancelled" })} disabled={updateMutation.isPending} className="p-1.5 rounded-md text-red-500 hover:bg-red-50 disabled:opacity-40 transition-colors" title="İptal Et">
                              <X className="w-4 h-4" />
                            </button>
                          </>
                        )}
                        {order.status === "confirmed" && (
                          <button onClick={() => updateMutation.mutate({ id: order.id, status: "cancelled" })} disabled={updateMutation.isPending} className="p-1.5 rounded-md text-red-500 hover:bg-red-50 disabled:opacity-40 transition-colors" title="İptal Et">
                            <X className="w-4 h-4" />
                          </button>
                        )}
                        {order.status === "cancelled" && (
                          <button onClick={() => updateMutation.mutate({ id: order.id, status: "pending" })} disabled={updateMutation.isPending} className="p-1.5 rounded-md text-amber-600 hover:bg-amber-50 disabled:opacity-40 transition-colors" title="Bekleyene Al">
                            <RefreshCw className="w-4 h-4" />
                          </button>
                        )}
                        <button onClick={() => setDeleteTarget(order.id)} className="p-1.5 rounded-md text-gray-400 hover:bg-red-50 hover:text-red-500 transition-colors" title="Sil">
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={deleteTarget != null}
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => deleteTarget && deleteMutation.mutate(deleteTarget)}
        loading={deleteMutation.isPending}
        title="Siparişi Sil"
        description="Bu sipariş kalıcı olarak silinecek. Bu işlem geri alınamaz."
        confirmLabel="Evet, sil"
      />

      {selectedOrder && (
        <OrderDetailModal order={selectedOrder} onClose={() => setSelectedOrder(null)} />
      )}
    </div>
  );
}

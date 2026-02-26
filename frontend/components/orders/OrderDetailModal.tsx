"use client";
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ordersApi } from "@/lib/api";
import type { Order, OrderUpdatePayload } from "@/lib/types";
import { X, Pencil, Save, User, MessageSquare } from "lucide-react";

interface Props {
  order: Order;
  onClose: () => void;
  onOpenConversation?: (conversationId: string) => void;
}

function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    pending: "bg-yellow-50 text-yellow-700 border border-yellow-200",
    confirmed: "bg-green-50 text-green-700 border border-green-200",
    cancelled: "bg-red-50 text-red-700 border border-red-200",
  };
  const labels: Record<string, string> = {
    pending: "Bekliyor",
    confirmed: "Onaylandı",
    cancelled: "İptal",
  };
  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
        styles[status] ?? "bg-gray-100 text-gray-600"
      }`}
    >
      {labels[status] ?? status}
    </span>
  );
}

function Field({
  label,
  value,
  editing,
  inputType = "text",
  onChange,
}: {
  label: string;
  value: string;
  editing: boolean;
  inputType?: string;
  onChange: (v: string) => void;
}) {
  return (
    <div>
      <p className="text-xs text-gray-400 mb-0.5">{label}</p>
      {editing ? (
        <input
          type={inputType}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="w-full border border-gray-300 rounded-md px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
        />
      ) : (
        <p className="text-sm text-gray-800">{value || "—"}</p>
      )}
    </div>
  );
}

export function OrderDetailModal({ order: initial, onClose, onOpenConversation }: Props) {
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState<OrderUpdatePayload>({
    contact_name: initial.contact_name ?? "",
    contact_surname: initial.contact_surname ?? "",
    contact_phone: initial.contact_phone ?? "",
    contact_email: initial.contact_email ?? "",
    notes: initial.notes ?? "",
  });

  const patch = (k: keyof OrderUpdatePayload, v: string) =>
    setForm((prev) => ({ ...prev, [k]: v }));

  const mutation = useMutation({
    mutationFn: () => ordersApi.update(initial.id, form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["orders"] });
      setEditing(false);
      onClose();
    },
  });

  const statusMutation = useMutation({
    mutationFn: (status: string) => ordersApi.updateStatus(initial.id, status),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["orders"] });
      onClose();
    },
  });

  const extraEntries = Object.entries(initial.extra_fields ?? {}).filter(
    ([k]) => !["confirmed", "saved", "order_id"].includes(k)
  );

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-start justify-between px-5 pt-5 pb-4 border-b border-gray-100">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h2 className="text-base font-semibold text-gray-900 truncate">
                {[initial.contact_name, initial.contact_surname].filter(Boolean).join(" ") || "Sipariş Detayı"}
              </h2>
              <StatusBadge status={initial.status} />
            </div>
            {initial.created_at && (
              <p className="text-xs text-gray-400 mt-0.5">
                Oluşturuldu:{" "}
                {new Date(initial.created_at).toLocaleDateString("tr-TR", {
                  day: "2-digit", month: "short", year: "numeric",
                })}
              </p>
            )}
          </div>
          <div className="flex items-center gap-2 ml-3">
            {!editing && (
              <button
                onClick={() => setEditing(true)}
                className="flex items-center gap-1.5 px-3 py-1.5 text-sm border border-gray-200 rounded-md text-gray-600 hover:bg-gray-50 transition-colors"
              >
                <Pencil className="w-3.5 h-3.5" /> Düzenle
              </button>
            )}
            <button onClick={onClose} className="text-gray-400 hover:text-gray-600 transition-colors">
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        <div className="px-5 py-4 space-y-5">
          {/* Contact Info */}
          <section>
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3 flex items-center gap-1.5">
              <User className="w-3.5 h-3.5" /> İletişim Bilgileri
            </h3>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Ad" value={form.contact_name ?? ""} editing={editing} onChange={(v) => patch("contact_name", v)} />
              <Field label="Soyad" value={form.contact_surname ?? ""} editing={editing} onChange={(v) => patch("contact_surname", v)} />
              <Field label="Telefon" value={form.contact_phone ?? ""} editing={editing} inputType="tel" onChange={(v) => patch("contact_phone", v)} />
              <Field label="E-posta" value={form.contact_email ?? ""} editing={editing} inputType="email" onChange={(v) => patch("contact_email", v)} />
            </div>
          </section>

          {/* Notes */}
          <section>
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">Notlar</h3>
            {editing ? (
              <textarea
                rows={3}
                value={form.notes ?? ""}
                onChange={(e) => patch("notes", e.target.value)}
                className="w-full border border-gray-300 rounded-md px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
              />
            ) : (
              <p className="text-sm text-gray-700 whitespace-pre-wrap">{initial.notes || "—"}</p>
            )}
          </section>

          {/* Summary */}
          {initial.summary && (
            <section>
              <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">Özet</h3>
              <p className="text-sm text-gray-700 whitespace-pre-wrap">{initial.summary}</p>
            </section>
          )}

          {/* Extra Fields */}
          {extraEntries.length > 0 && (
            <section>
              <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">Ek Bilgiler</h3>
              <div className="bg-gray-50 border border-gray-200 rounded-lg overflow-hidden">
                <table className="w-full text-sm">
                  <tbody className="divide-y divide-gray-100">
                    {extraEntries.map(([k, v]) => (
                      <tr key={k}>
                        <td className="px-3 py-2 font-medium text-gray-600 w-1/3">{k}</td>
                        <td className="px-3 py-2 text-gray-800">{String(v)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          {/* Conversation Link */}
          {initial.conversation_id && (
            <section>
              <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                <MessageSquare className="w-3.5 h-3.5" /> Konuşma
              </h3>
              <button
                onClick={() => onOpenConversation?.(initial.conversation_id!)}
                className="text-sm text-indigo-600 hover:text-indigo-800 underline"
              >
                Konuşmayı Gör →
              </button>
            </section>
          )}
        </div>

        {/* Actions */}
        <div className="px-5 pb-5 border-t border-gray-100 pt-4">
          {editing ? (
            <div className="flex gap-2">
              <button
                onClick={() => mutation.mutate()}
                disabled={mutation.isPending}
                className="flex items-center gap-1.5 px-4 py-2 bg-indigo-600 text-white text-sm font-medium rounded-md hover:bg-indigo-700 disabled:opacity-50 transition-colors"
              >
                <Save className="w-4 h-4" />
                {mutation.isPending ? "Kaydediliyor…" : "Kaydet"}
              </button>
              <button
                onClick={() => setEditing(false)}
                className="px-4 py-2 border border-gray-200 text-gray-600 text-sm font-medium rounded-md hover:bg-gray-50 transition-colors"
              >
                İptal
              </button>
              {mutation.isError && (
                <span className="text-xs text-red-600 self-center">
                  Hata: {(mutation.error as Error).message}
                </span>
              )}
            </div>
          ) : (
            <div className="flex items-center gap-2 flex-wrap">
              {initial.status === "pending" && (
                <button
                  onClick={() => statusMutation.mutate("confirmed")}
                  disabled={statusMutation.isPending}
                  className="px-3 py-1.5 bg-green-600 text-white text-sm rounded-md hover:bg-green-700 disabled:opacity-50 transition-colors"
                >
                  Onayla
                </button>
              )}
              {initial.status !== "cancelled" && (
                <button
                  onClick={() => statusMutation.mutate("cancelled")}
                  disabled={statusMutation.isPending}
                  className="px-3 py-1.5 bg-red-50 text-red-600 border border-red-200 text-sm rounded-md hover:bg-red-100 disabled:opacity-50 transition-colors"
                >
                  İptal Et
                </button>
              )}
              {initial.status === "cancelled" && (
                <button
                  onClick={() => statusMutation.mutate("pending")}
                  disabled={statusMutation.isPending}
                  className="px-3 py-1.5 bg-yellow-50 text-yellow-700 border border-yellow-200 text-sm rounded-md hover:bg-yellow-100 disabled:opacity-50 transition-colors"
                >
                  Bekleyene Al
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

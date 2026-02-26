"use client";
import { useState, useEffect, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { appointmentsApi, orchestratorApi } from "@/lib/api";
import type { Appointment, FieldConfig } from "@/lib/types";
import { Calendar, Check, X, Trash2, RefreshCw, Phone, Mail, Eye, Clock, Loader2, Download, Square, CheckSquare } from "lucide-react";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { formatDateTime } from "@/lib/utils";
import dynamic from "next/dynamic";

const AppointmentDetailModal = dynamic(
  () => import("./AppointmentDetailModal").then((m) => m.AppointmentDetailModal),
  { ssr: false, loading: () => null }
);

const STATUS_FILTERS = [
  { value: "all",       label: "Tümü" },
  { value: "pending",   label: "Bekliyor" },
  { value: "confirmed", label: "Onaylandı" },
  { value: "cancelled", label: "İptal" },
] as const;

const STANDARD_COLUMN_MAP: Record<string, (a: Appointment) => string | null> = {
  name:       (a) => a.contact_name,
  surname:    (a) => a.contact_surname,
  phone:      (a) => a.contact_phone,
  email:      (a) => a.contact_email,
  service:    (a) => a.service,
  event_type: (a) => a.service,
  location:   (a) => a.location,
  artist:     (a) => a.artist,
  event_date: (a) => a.event_date,
  event_time: (a) => a.event_time,
  notes:      (a) => a.notes,
};

function getCellValue(appt: Appointment, field: FieldConfig): string {
  const getter = STANDARD_COLUMN_MAP[field.key];
  if (getter) return getter(appt) ?? "—";
  const val = (appt.extra_fields ?? {})[field.key];
  return val == null || val === "" ? "—" : String(val);
}

function mergeNameSurnameFields(fields: FieldConfig[]): FieldConfig[] {
  const hasName = fields.some((f) => f.key === "name");
  const hasSurname = fields.some((f) => f.key === "surname");
  if (!hasName || !hasSurname) return fields;
  const merged: FieldConfig[] = [];
  let inserted = false;
  for (const f of fields) {
    if (f.key === "name") { merged.push({ ...f, label: "Müşteri", key: "__name_surname__" }); inserted = true; }
    else if (f.key === "surname") { if (!inserted) merged.push({ ...f, label: "Müşteri", key: "__name_surname__" }); }
    else merged.push(f);
  }
  return merged;
}

function mergePhoneEmailFields(fields: FieldConfig[]): FieldConfig[] {
  const hasPhone = fields.some((f) => f.key === "phone");
  const hasEmail = fields.some((f) => f.key === "email");
  if (!hasPhone && !hasEmail) return fields;
  if (hasPhone && hasEmail) {
    const merged: FieldConfig[] = [];
    let inserted = false;
    for (const f of fields) {
      if (f.key === "phone") { merged.push({ ...f, label: "İletişim", key: "__contact__" }); inserted = true; }
      else if (f.key === "email") { if (!inserted) merged.push({ ...f, label: "İletişim", key: "__contact__" }); }
      else merged.push(f);
    }
    return merged;
  }
  return fields;
}

function mergeDateTimeFields(fields: FieldConfig[]): FieldConfig[] {
  const hasDate = fields.some((f) => f.key === "event_date");
  const hasTime = fields.some((f) => f.key === "event_time");
  if (!hasDate || !hasTime) return fields;
  const merged: FieldConfig[] = [];
  let inserted = false;
  for (const f of fields) {
    if (f.key === "event_date") { merged.push({ ...f, label: "Tarih", key: "__datetime__" }); inserted = true; }
    else if (f.key === "event_time") { if (!inserted) merged.push({ ...f, label: "Tarih", key: "__datetime__" }); }
    else merged.push(f);
  }
  return merged;
}

function CellRenderer({ appt, field }: { appt: Appointment; field: FieldConfig }) {
  if (field.key === "__name_surname__") {
    const full = `${appt.contact_name ?? ""} ${appt.contact_surname ?? ""}`.trim();
    return <span className="font-medium text-gray-900">{full || "—"}</span>;
  }
  if (field.key === "__contact__") {
    return (
      <div className="flex flex-col gap-0.5 text-xs text-gray-600">
        {appt.contact_phone && <span className="flex items-center gap-1"><Phone className="w-3 h-3" />{appt.contact_phone}</span>}
        {appt.contact_email && <span className="flex items-center gap-1"><Mail className="w-3 h-3" />{appt.contact_email}</span>}
        {!appt.contact_phone && !appt.contact_email && "—"}
      </div>
    );
  }
  if (field.key === "__datetime__") {
    return <>{`${appt.event_date ?? ""} ${appt.event_time ?? ""}`.trim() || "—"}</>;
  }
  return <>{getCellValue(appt, field)}</>;
}

function TableSkeleton({ cols }: { cols: number }) {
  return (
    <div className="bg-white border border-gray-200 rounded-lg overflow-hidden animate-pulse">
      <div className="bg-gray-50 border-b border-gray-200 h-10" />
      {[...Array(5)].map((_, i) => (
        <div key={i} className="flex gap-4 px-4 py-3 border-b border-gray-100 last:border-0">
          {[...Array(cols)].map((_, j) => (
            <div key={j} className="h-4 bg-gray-200 rounded flex-1" />
          ))}
        </div>
      ))}
    </div>
  );
}

const SKIP_SENTINEL = "__skip__";

export function AppointmentsPanel() {
  const qc = useQueryClient();
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [search, setSearch] = useState<string>("");
  const [debouncedSearch, setDebouncedSearch] = useState<string>("");
  const [dateFrom, setDateFrom] = useState<string>("");
  const [dateTo, setDateTo] = useState<string>("");
  const [selectedAppt, setSelectedAppt] = useState<Appointment | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  // Debounce search input (300ms)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => setDebouncedSearch(search), 300);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [search]);

  const buildListParams = () => {
    const params: Record<string, string> = {};
    if (statusFilter !== "all") params.status = statusFilter;
    if (debouncedSearch) params.search = debouncedSearch;
    if (dateFrom) params.date_from = dateFrom;
    if (dateTo) params.date_to = dateTo;
    return params;
  };

  const buildExportUrl = () => {
    const base = `${process.env.NEXT_PUBLIC_API_URL ?? ""}/api/v1/appointments/export`;
    const p = buildListParams();
    const qs = new URLSearchParams(p).toString();
    return qs ? `${base}?${qs}` : base;
  };

  const { data: appointments = [], isLoading, refetch, isFetching } = useQuery({
    queryKey: ["appointments", statusFilter, debouncedSearch, dateFrom, dateTo],
    queryFn: () => {
      const qs = new URLSearchParams(buildListParams()).toString();
      return appointmentsApi.list(undefined, qs || undefined);
    },
    refetchInterval: 30_000,
  });

  const { data: botConfig } = useQuery({
    queryKey: ["orchestrator-config"],
    queryFn: orchestratorApi.getConfig,
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) =>
      appointmentsApi.updateStatus(id, status),
    onSuccess: (_, { status }) => {
      qc.invalidateQueries({ queryKey: ["appointments"] });
      qc.invalidateQueries({ queryKey: ["calendar-blocks"] });
      qc.invalidateQueries({ queryKey: ["calendar-blocks-week"] });
      qc.invalidateQueries({ queryKey: ["calendar-availability"] });
      const label = status === "confirmed" ? "onaylandı" : status === "cancelled" ? "iptal edildi" : "güncellendi";
      toast.success(`Randevu ${label}.`);
    },
    onError: () => toast.error("Durum güncellenemedi."),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => appointmentsApi.delete(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["appointments"] });
      qc.invalidateQueries({ queryKey: ["calendar-blocks"] });
      qc.invalidateQueries({ queryKey: ["calendar-blocks-week"] });
      qc.invalidateQueries({ queryKey: ["calendar-availability"] });
      setDeleteTarget(null);
      toast.success("Randevu silindi.");
    },
    onError: () => toast.error("Randevu silinemedi."),
  });

  const bulkUpdateMutation = useMutation({
    mutationFn: async ({ ids, status }: { ids: string[]; status: string }) => {
      await Promise.all(ids.map((id) => appointmentsApi.updateStatus(id, status)));
    },
    onSuccess: (_, { status }) => {
      qc.invalidateQueries({ queryKey: ["appointments"] });
      qc.invalidateQueries({ queryKey: ["calendar-blocks"] });
      qc.invalidateQueries({ queryKey: ["calendar-blocks-week"] });
      qc.invalidateQueries({ queryKey: ["calendar-availability"] });
      setSelectedIds(new Set());
      const label = status === "confirmed" ? "onaylandı" : "iptal edildi";
      toast.success(`Seçili randevular ${label}.`);
    },
    onError: () => toast.error("Toplu işlem başarısız."),
  });

  const toggleSelect = (id: string) =>
    setSelectedIds((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  const toggleSelectAll = () => {
    if (selectedIds.size === appointments.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(appointments.map((a: Appointment) => a.id)));
    }
  };

  const rawFields: FieldConfig[] = botConfig?.appointment_fields ?? [];
  let displayFields = rawFields.length > 0
    ? rawFields.filter((f) => f.key !== SKIP_SENTINEL)
    : [
        { key: "name",       label: "Ad",      question: "", required: true },
        { key: "surname",    label: "Soyad",   question: "", required: true },
        { key: "phone",      label: "Telefon", question: "", required: true },
        { key: "service",    label: "Hizmet",  question: "", required: true },
        { key: "event_date", label: "Tarih",   question: "", required: true },
      ];
  displayFields = mergeDateTimeFields(mergePhoneEmailFields(mergeNameSurnameFields(displayFields)));

  return (
    <div className="space-y-4">
      {/* Search + date-range toolbar row */}
      <div className="flex items-center gap-2 flex-wrap">
        <input
          type="text"
          placeholder="Randevu no ara (RND-…)"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="border border-gray-200 rounded-md px-3 py-1.5 text-sm text-gray-700 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-indigo-400 w-52"
        />
        <input
          type="date"
          value={dateFrom}
          onChange={(e) => setDateFrom(e.target.value)}
          className="border border-gray-200 rounded-md px-3 py-1.5 text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-indigo-400"
          title="Başlangıç tarihi"
        />
        <span className="text-gray-400 text-sm">–</span>
        <input
          type="date"
          value={dateTo}
          onChange={(e) => setDateTo(e.target.value)}
          className="border border-gray-200 rounded-md px-3 py-1.5 text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-indigo-400"
          title="Bitiş tarihi"
        />
        {(search || dateFrom || dateTo) && (
          <button
            onClick={() => { setSearch(""); setDateFrom(""); setDateTo(""); }}
            className="text-xs text-gray-400 hover:text-gray-600 underline"
          >
            Temizle
          </button>
        )}
      </div>

      {/* Status filters + actions */}
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
        <div className="flex items-center gap-2">
          <a
            href={buildExportUrl()}
            download="appointments.csv"
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-gray-600 border border-gray-200 rounded-md hover:bg-gray-50 transition-colors"
          >
            <Download className="w-3.5 h-3.5" />
            Dışa Aktar
          </a>
          <button
            onClick={() => refetch()}
            disabled={isFetching}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-gray-600 border border-gray-200 rounded-md hover:bg-gray-50 disabled:opacity-50 transition-colors"
          >
            {isFetching ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
            Yenile
          </button>
        </div>
      </div>

      {/* Bulk action bar */}
      {selectedIds.size > 0 && (
        <div className="flex items-center gap-3 px-4 py-2.5 bg-indigo-50 border border-indigo-200 rounded-lg text-sm">
          <span className="text-indigo-700 font-medium">{selectedIds.size} randevu seçili</span>
          <button
            onClick={() => bulkUpdateMutation.mutate({ ids: Array.from(selectedIds), status: "confirmed" })}
            disabled={bulkUpdateMutation.isPending}
            className="px-3 py-1 bg-green-600 text-white rounded-md text-xs font-medium hover:bg-green-700 disabled:opacity-50 transition-colors"
          >
            Tümünü Onayla
          </button>
          <button
            onClick={() => bulkUpdateMutation.mutate({ ids: Array.from(selectedIds), status: "cancelled" })}
            disabled={bulkUpdateMutation.isPending}
            className="px-3 py-1 bg-red-50 text-red-600 border border-red-200 rounded-md text-xs font-medium hover:bg-red-100 disabled:opacity-50 transition-colors"
          >
            Tümünü İptal Et
          </button>
          <button
            onClick={() => setSelectedIds(new Set())}
            className="ml-auto text-indigo-400 hover:text-indigo-600 text-xs"
          >
            Seçimi Kaldır
          </button>
        </div>
      )}

      {isLoading ? (
        <TableSkeleton cols={displayFields.length + 5} />
      ) : appointments.length === 0 ? (
        <EmptyState
          icon={<Calendar className="w-6 h-6" />}
          title="Henüz randevu yok"
          description={statusFilter !== "all" ? "Bu filtrede kayıt bulunamadı." : "Müşteriler bot üzerinden randevu aldığında burada görünecek."}
        />
      ) : (
        <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className="px-3 py-3 w-8">
                    <button onClick={toggleSelectAll} className="text-gray-400 hover:text-indigo-600 transition-colors">
                      {selectedIds.size === appointments.length && appointments.length > 0
                        ? <CheckSquare className="w-4 h-4 text-indigo-600" />
                        : <Square className="w-4 h-4" />}
                    </button>
                  </th>
                  <th className="px-4 py-3 text-left font-semibold text-gray-600 whitespace-nowrap">Randevu No</th>
                  {displayFields.map((f) => (
                    <th key={f.key} className="px-4 py-3 text-left font-semibold text-gray-600 whitespace-nowrap">{f.label}</th>
                  ))}
                  <th className="px-4 py-3 text-left font-semibold text-gray-600">Durum</th>
                  <th className="px-4 py-3 text-left font-semibold text-gray-600">Takvim</th>
                  <th className="px-4 py-3 text-left font-semibold text-gray-600">Oluşturuldu</th>
                  <th className="px-4 py-3 text-right font-semibold text-gray-600">İşlem</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {appointments.map((appt: Appointment) => (
                  <tr key={appt.id} className={`hover:bg-gray-50 transition-colors ${selectedIds.has(appt.id) ? "bg-indigo-50/40" : ""}`}>
                    <td className="px-3 py-3 w-8">
                      <button onClick={() => toggleSelect(appt.id)} className="text-gray-400 hover:text-indigo-600 transition-colors">
                        {selectedIds.has(appt.id)
                          ? <CheckSquare className="w-4 h-4 text-indigo-600" />
                          : <Square className="w-4 h-4" />}
                      </button>
                    </td>
                    <td className="px-4 py-3">
                      {appt.appt_number ? (
                        <span className="font-mono text-xs bg-indigo-50 text-indigo-700 border border-indigo-200 px-2 py-0.5 rounded whitespace-nowrap">
                          {appt.appt_number}
                        </span>
                      ) : (
                        <span className="text-xs text-gray-300">—</span>
                      )}
                    </td>
                    {displayFields.map((f) => (
                      <td key={f.key} className="px-4 py-3 text-gray-600 text-xs">
                        <CellRenderer appt={appt} field={f} />
                      </td>
                    ))}
                    <td className="px-4 py-3"><StatusBadge status={appt.status} /></td>
                    <td className="px-4 py-3">
                      {appt.calendar_block ? (
                        <div className="flex items-center gap-1 text-xs text-indigo-700">
                          <Clock className="w-3 h-3" />
                          <span className="font-medium truncate max-w-[100px]">{appt.calendar_block.resource_name}</span>
                          <span className="text-indigo-400">{appt.calendar_block.start_time.slice(0, 5)}</span>
                        </div>
                      ) : (
                        <span className="flex items-center gap-1 text-xs text-amber-600">
                          <span className="w-1.5 h-1.5 rounded-full bg-amber-400 inline-block" />
                          Takvim Yok
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-gray-400 text-xs">{formatDateTime(appt.created_at)}</td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end gap-1">
                        <button onClick={() => setSelectedAppt(appt)} className="p-1.5 rounded-md text-indigo-500 hover:bg-indigo-50 transition-colors" title="Detay">
                          <Eye className="w-4 h-4" />
                        </button>
                        {appt.status === "pending" && (
                          <>
                            <button onClick={() => updateMutation.mutate({ id: appt.id, status: "confirmed" })} disabled={updateMutation.isPending} className="p-1.5 rounded-md text-green-600 hover:bg-green-50 disabled:opacity-40 transition-colors" title="Onayla">
                              <Check className="w-4 h-4" />
                            </button>
                            <button onClick={() => updateMutation.mutate({ id: appt.id, status: "cancelled" })} disabled={updateMutation.isPending} className="p-1.5 rounded-md text-red-500 hover:bg-red-50 disabled:opacity-40 transition-colors" title="İptal Et">
                              <X className="w-4 h-4" />
                            </button>
                          </>
                        )}
                        {appt.status === "confirmed" && (
                          <button onClick={() => updateMutation.mutate({ id: appt.id, status: "cancelled" })} disabled={updateMutation.isPending} className="p-1.5 rounded-md text-red-500 hover:bg-red-50 disabled:opacity-40 transition-colors" title="İptal Et">
                            <X className="w-4 h-4" />
                          </button>
                        )}
                        {appt.status === "cancelled" && (
                          <button onClick={() => updateMutation.mutate({ id: appt.id, status: "pending" })} disabled={updateMutation.isPending} className="p-1.5 rounded-md text-amber-600 hover:bg-amber-50 disabled:opacity-40 transition-colors" title="Bekleyene Al">
                            <RefreshCw className="w-4 h-4" />
                          </button>
                        )}
                        <button onClick={() => setDeleteTarget(appt.id)} className="p-1.5 rounded-md text-gray-400 hover:bg-red-50 hover:text-red-500 transition-colors" title="Sil">
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
        title="Randevuyu Sil"
        description="Bu randevu kalıcı olarak silinecek. Varsa takvim bloğu da kaldırılacak. Bu işlem geri alınamaz."
        confirmLabel="Evet, sil"
      />

      {selectedAppt && (
        <AppointmentDetailModal appointment={selectedAppt} onClose={() => setSelectedAppt(null)} />
      )}
    </div>
  );
}

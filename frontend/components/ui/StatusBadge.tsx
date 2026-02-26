import type { ReactNode } from "react";

type Variant = "pending" | "confirmed" | "cancelled" | "active" | "closed" | "unknown";

const VARIANT_CLASSES: Record<Variant, string> = {
  pending:   "bg-amber-100 text-amber-800",
  confirmed: "bg-green-100 text-green-800",
  cancelled: "bg-red-100   text-red-800",
  active:    "bg-blue-100  text-blue-800",
  closed:    "bg-gray-100  text-gray-600",
  unknown:   "bg-gray-100  text-gray-500",
};

const LABELS: Record<string, string> = {
  pending:   "Bekliyor",
  confirmed: "Onaylandı",
  cancelled: "İptal",
  active:    "Aktif",
  closed:    "Kapalı",
};

interface Props {
  status: string | null | undefined;
  /** Override label; defaults to Turkish mapping or raw status */
  label?: string;
  className?: string;
}

export function StatusBadge({ status, label, className = "" }: Props) {
  const key = (status ?? "unknown").toLowerCase() as Variant;
  const classes = VARIANT_CLASSES[key] ?? VARIANT_CLASSES.unknown;
  const text = label ?? LABELS[key] ?? status ?? "—";
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${classes} ${className}`}>
      {text}
    </span>
  );
}

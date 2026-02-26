"use client";
import { Trash2, Plus, ArrowUp, ArrowDown, GitBranch } from "lucide-react";
import type { FieldConfig, FieldValidation } from "@/lib/types";

interface Props {
  value: FieldConfig[];
  onChange: (fields: FieldConfig[]) => void;
}

const VALIDATION_OPTIONS: { value: FieldValidation; label: string }[] = [
  { value: "text",   label: "Serbest metin" },
  { value: "phone",  label: "Telefon" },
  { value: "email",  label: "E-posta" },
  { value: "date",   label: "Tarih" },
  { value: "time",   label: "Saat" },
  { value: "number", label: "Sayı" },
];

const VALIDATION_HINTS: Record<string, string> = {
  phone:  "Otomatik: 05XX XXX XX XX formatı beklenir",
  email:  "Otomatik: geçerli e-posta formatı beklenir",
  date:   "Otomatik: GG Ay YYYY (ör: 15 Mart 2026)",
  time:   "Otomatik: SS:DD (ör: 14:30, 09:00)",
  number: "Otomatik: sadece sayısal değer beklenir",
};

export function FieldsEditor({ value, onChange }: Props) {
  const update = (index: number, patch: Partial<FieldConfig>) => {
    const next = value.map((f, i) => (i === index ? { ...f, ...patch } : f));
    if ("label" in patch && patch.label !== undefined) {
      next[index].key = patch.label
        .toLowerCase()
        .replace(/\s+/g, "_")
        .replace(/[^a-z0-9_]/g, "");
    }
    onChange(next);
  };

  const remove = (index: number) => {
    const removedKey = value[index].key;
    // Clear any show_if references to the removed field
    const next = value
      .filter((_, i) => i !== index)
      .map((f) =>
        f.show_if?.field === removedKey ? { ...f, show_if: undefined } : f
      );
    onChange(next);
  };

  const add = () => {
    onChange([
      ...value,
      { key: "", label: "", question: "", required: false, validation: "text" },
    ]);
  };

  const moveUp = (index: number) => {
    if (index === 0) return;
    const next = [...value];
    [next[index - 1], next[index]] = [next[index], next[index - 1]];
    onChange(next);
  };

  const moveDown = (index: number) => {
    if (index === value.length - 1) return;
    const next = [...value];
    [next[index], next[index + 1]] = [next[index + 1], next[index]];
    onChange(next);
  };

  const optionsToText = (opts: string[] | undefined) =>
    opts && opts.length ? opts.join(", ") : "";
  const textToOptions = (text: string): string[] =>
    text.split(/[,\n]+/).map((s) => s.trim()).filter(Boolean);

  // Fields that come BEFORE index — only these can be dependencies (avoids circular)
  const candidateDeps = (index: number) =>
    value
      .slice(0, index)
      .filter((f) => f.key && (f.options?.length ?? 0) > 0);

  return (
    <div className="space-y-3">
      {value.length === 0 && (
        <p className="text-xs text-gray-400 italic">Henüz alan eklenmedi.</p>
      )}

      {value.map((field, i) => {
        const deps = candidateDeps(i);
        const hasShowIf = !!field.show_if?.field;

        // Current dependency field (to show its options in the value picker)
        const depField = field.show_if?.field
          ? value.find((f) => f.key === field.show_if?.field)
          : undefined;
        const depOptions = depField?.options ?? [];

        // Normalise show_if.value to string[]
        const selectedValues: string[] = field.show_if?.value
          ? Array.isArray(field.show_if.value)
            ? field.show_if.value
            : [field.show_if.value]
          : [];

        const toggleValue = (opt: string, checked: boolean) => {
          const next = checked
            ? [...selectedValues, opt]
            : selectedValues.filter((v) => v !== opt);
          update(i, {
            show_if: { field: field.show_if!.field, value: next },
          });
        };

        return (
          <div key={i} className={hasShowIf ? "ml-6 pl-3 border-l-2 border-indigo-200" : ""}>
            <div
              className={`border rounded-lg bg-white shadow-sm ${
                hasShowIf ? "border-indigo-200" : "border-gray-200"
              }`}
            >
              {hasShowIf && (
                <div className="px-3 pt-2">
                  <span className="inline-flex items-center gap-1 text-[10px] text-indigo-600 bg-indigo-50 border border-indigo-100 rounded-full px-2 py-0.5">
                    <GitBranch className="w-2.5 h-2.5" />
                    <span className="font-medium">{depField?.label || field.show_if?.field}</span>
                    {selectedValues.length > 0 ? (
                      <>{" = "}<strong>{selectedValues.join(" / ")}</strong></>
                    ) : (
                      <span className="text-amber-500"> — değer seçin</span>
                    )}
                  </span>
                </div>
              )}
            {/* ── Row 1: reorder + label/question/required/delete ── */}
            <div className="flex items-start gap-2 p-3">
              {/* Reorder */}
              <div className="flex flex-col gap-0.5 pt-0.5 shrink-0">
                <button
                  type="button"
                  onClick={() => moveUp(i)}
                  disabled={i === 0}
                  className="p-0.5 text-gray-300 hover:text-gray-600 disabled:opacity-20 transition-colors"
                  title="Yukarı taşı"
                >
                  <ArrowUp className="w-3.5 h-3.5" />
                </button>
                <span className="text-[10px] text-gray-300 text-center font-mono">{i + 1}</span>
                <button
                  type="button"
                  onClick={() => moveDown(i)}
                  disabled={i === value.length - 1}
                  className="p-0.5 text-gray-300 hover:text-gray-600 disabled:opacity-20 transition-colors"
                  title="Aşağı taşı"
                >
                  <ArrowDown className="w-3.5 h-3.5" />
                </button>
              </div>

              {/* Main inputs */}
              <div className="flex-1 space-y-2">
                <div className="flex items-center gap-2 flex-wrap">
                  <input
                    type="text"
                    placeholder="Etiket (ör: Ad)"
                    value={field.label}
                    onChange={(e) => update(i, { label: e.target.value })}
                    className="w-28 text-sm border border-gray-300 rounded-md px-2.5 py-1.5 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  />
                  <input
                    type="text"
                    placeholder="Soru (ör: Adınız nedir?)"
                    value={field.question}
                    onChange={(e) => update(i, { question: e.target.value })}
                    className="flex-1 min-w-[150px] text-sm border border-gray-300 rounded-md px-2.5 py-1.5 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  />
                  <label className="flex items-center gap-1.5 text-xs text-gray-600 cursor-pointer select-none whitespace-nowrap">
                    <input
                      type="checkbox"
                      checked={field.required}
                      onChange={(e) => update(i, { required: e.target.checked })}
                      className="rounded"
                    />
                    Zorunlu
                  </label>
                  <button
                    type="button"
                    onClick={() => remove(i)}
                    className="p-1.5 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded-md transition-colors"
                    title="Sil"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>

                {/* ── Row 2: validation + options ── */}
                <div className="flex gap-2 flex-wrap items-start">
                  <div className="shrink-0">
                    <label className="block text-[10px] text-gray-400 mb-0.5">Doğrulama</label>
                    <select
                      value={field.validation ?? "text"}
                      onChange={(e) =>
                        update(i, { validation: e.target.value as FieldValidation })
                      }
                      className="text-xs border border-gray-300 rounded-md px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-indigo-500 bg-white"
                    >
                      {VALIDATION_OPTIONS.map((opt) => (
                        <option key={opt.value} value={opt.value}>
                          {opt.label}
                        </option>
                      ))}
                    </select>
                  </div>

                  {(!field.validation || field.validation === "text") && (
                    <div className="flex-1 min-w-[180px]">
                      <label className="block text-[10px] text-gray-400 mb-0.5">
                        Seçenekler (virgülle ayır — boş = serbest metin)
                      </label>
                      <input
                        type="text"
                        placeholder="ör: Stüdyo, Şehir Dışı, Ev"
                        value={optionsToText(field.options)}
                        onChange={(e) =>
                          update(i, { options: textToOptions(e.target.value) })
                        }
                        className="w-full text-xs border border-gray-300 rounded-md px-2.5 py-1.5 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                      />
                    </div>
                  )}

                  {field.validation && field.validation !== "text" && (
                    <div className="flex-1 min-w-[180px]">
                      <label className="block text-[10px] text-gray-400 mb-0.5">Format ipucu</label>
                      <p className="text-xs text-indigo-600 bg-indigo-50 border border-indigo-100 rounded-md px-2.5 py-1.5">
                        {VALIDATION_HINTS[field.validation]}
                      </p>
                    </div>
                  )}
                </div>

                {/* ── Row 3: show_if (conditional) ── */}
                <div className="pt-1">
                  {/* Toggle */}
                  <label className="flex items-center gap-1.5 text-xs cursor-pointer select-none w-fit">
                    <input
                      type="checkbox"
                      checked={hasShowIf}
                      onChange={(e) => {
                        if (e.target.checked && deps.length > 0) {
                          update(i, {
                            show_if: { field: deps[0].key, value: [] },
                          });
                        } else {
                          update(i, { show_if: undefined });
                        }
                      }}
                      disabled={deps.length === 0}
                      className="rounded"
                    />
                    <GitBranch className="w-3 h-3 text-indigo-500" />
                    <span className={hasShowIf ? "text-indigo-700 font-medium" : "text-gray-500"}>
                      Koşullu göster
                    </span>
                    {deps.length === 0 && (
                      <span className="text-gray-400">(önceki alanda seçenek gerekli)</span>
                    )}
                  </label>

                  {/* Condition editor */}
                  {hasShowIf && (
                    <div className="mt-2 ml-4 pl-3 border-l-2 border-indigo-200 space-y-2">
                      {/* Dependency field selector */}
                      <div className="flex items-center gap-2 flex-wrap">
                        <label className="text-xs text-gray-500 shrink-0">Hangi alan:</label>
                        <select
                          value={field.show_if!.field}
                          onChange={(e) =>
                            update(i, {
                              show_if: { field: e.target.value, value: [] },
                            })
                          }
                          className="text-xs border border-gray-300 rounded-md px-2 py-1.5 bg-white focus:outline-none focus:ring-1 focus:ring-indigo-500"
                        >
                          {deps.map((d) => (
                            <option key={d.key} value={d.key}>
                              {d.label || d.key}
                            </option>
                          ))}
                        </select>
                      </div>

                      {/* Value checkboxes */}
                      {depOptions.length > 0 && (
                        <div>
                          <p className="text-xs text-gray-500 mb-1">
                            Bu değerlerde göster:
                          </p>
                          <div className="flex flex-wrap gap-2">
                            {depOptions.map((opt) => (
                              <label
                                key={opt}
                                className={`flex items-center gap-1 text-xs px-2.5 py-1 rounded-full border cursor-pointer transition-colors ${
                                  selectedValues.includes(opt)
                                    ? "bg-indigo-600 text-white border-indigo-600"
                                    : "bg-white text-gray-600 border-gray-300 hover:border-indigo-400"
                                }`}
                              >
                                <input
                                  type="checkbox"
                                  className="sr-only"
                                  checked={selectedValues.includes(opt)}
                                  onChange={(e) => toggleValue(opt, e.target.checked)}
                                />
                                {opt}
                              </label>
                            ))}
                          </div>
                          {selectedValues.length === 0 && (
                            <p className="text-[11px] text-amber-600 mt-1">
                              En az bir değer seçin, yoksa bu alan hiç gösterilmez.
                            </p>
                          )}
                        </div>
                      )}

                      {depOptions.length === 0 && (
                        <p className="text-xs text-amber-600">
                          Seçilen alanın seçenekleri yok — önce seçenek ekleyin.
                        </p>
                      )}

                      {/* Preview */}
                      {selectedValues.length > 0 && (
                        <p className="text-[11px] text-indigo-600 bg-indigo-50 rounded px-2 py-1">
                          "{field.label || field.key}" sorusu yalnızca "
                          {depField?.label || field.show_if?.field}" =&nbsp;
                          {selectedValues.map((v, vi) => (
                            <span key={v}>
                              <strong>{v}</strong>
                              {vi < selectedValues.length - 1 ? " veya " : ""}
                            </span>
                          ))}{" "}
                          olduğunda sorulur.
                        </p>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </div>
            </div>
          </div>
        );
      })}

      <button
        type="button"
        onClick={add}
        className="flex items-center gap-1.5 text-sm text-indigo-600 hover:text-indigo-800 font-medium mt-1"
      >
        <Plus className="w-4 h-4" /> Alan Ekle
      </button>
    </div>
  );
}

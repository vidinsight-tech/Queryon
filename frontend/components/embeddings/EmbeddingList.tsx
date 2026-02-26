"use client";
import { useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { embeddingsApi } from "@/lib/api";
import type { EmbeddingModel } from "@/lib/types";
import { Layers, Plus, Pencil, Trash2 } from "lucide-react";
import { Toggle } from "@/components/ui/Toggle";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";

const OPENAI_MODELS = [
  "text-embedding-3-small",
  "text-embedding-3-large",
  "text-embedding-ada-002",
];
const GEMINI_MODELS = ["text-embedding-004"];

const schema = z.object({
  name: z.string().min(1, "İsim zorunlu"),
  provider: z.enum(["openai", "gemini"]),
  model: z.string().min(1, "Model zorunlu"),
  api_key: z.string().min(1, "API anahtarı zorunlu"),
  is_active: z.boolean(),
});

type FormValues = z.infer<typeof schema>;

function ProviderBadge({ provider }: { provider: string }) {
  const classes =
    provider === "openai"
      ? "bg-indigo-50 text-indigo-700"
      : "bg-green-50 text-green-700";
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${classes}`}>
      {provider}
    </span>
  );
}

function EmbeddingModal({
  initial,
  onClose,
}: {
  initial?: EmbeddingModel;
  onClose: () => void;
}) {
  const qc = useQueryClient();

  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      name: initial?.name ?? "",
      provider: (initial?.provider as "openai" | "gemini") ?? "openai",
      model: (initial?.config?.model as string) ?? OPENAI_MODELS[0],
      api_key: (initial?.config?.api_key as string) ?? "",
      is_active: initial?.is_active ?? true,
    },
  });

  const provider = useWatch({ control: form.control, name: "provider" });
  const modelOptions = provider === "gemini" ? GEMINI_MODELS : OPENAI_MODELS;

  const createMutation = useMutation({
    mutationFn: (values: FormValues) =>
      embeddingsApi.create({
        name: values.name,
        provider: values.provider,
        config: { model: values.model, api_key: values.api_key },
        is_active: values.is_active,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["embeddings"] });
      toast.success("Embedding modeli eklendi.");
      onClose();
    },
    onError: () => toast.error("Model eklenemedi."),
  });

  const updateMutation = useMutation({
    mutationFn: (values: FormValues) =>
      embeddingsApi.update(initial!.id, {
        name: values.name,
        provider: values.provider,
        config: { model: values.model, api_key: values.api_key },
        is_active: values.is_active,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["embeddings"] });
      toast.success("Embedding modeli güncellendi.");
      onClose();
    },
    onError: () => toast.error("Model güncellenemedi."),
  });

  const isPending = createMutation.isPending || updateMutation.isPending;

  const onSubmit = (values: FormValues) => {
    if (initial) {
      updateMutation.mutate(values);
    } else {
      createMutation.mutate(values);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl shadow-xl p-6 w-full max-w-md">
        <h2 className="font-bold text-lg mb-4">
          {initial ? "Embedding Modeli Düzenle" : "Embedding Modeli Ekle"}
        </h2>
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
          <div>
            <label className="text-sm font-medium block mb-1">İsim</label>
            <input
              {...form.register("name")}
              className="border border-gray-300 rounded-md px-3 py-2 text-sm w-full focus:outline-none focus:ring-2 focus:ring-indigo-500"
              placeholder="örn. OpenAI Small"
            />
            {form.formState.errors.name && (
              <p className="text-xs text-red-600 mt-1">
                {form.formState.errors.name.message}
              </p>
            )}
          </div>

          <div>
            <label className="text-sm font-medium block mb-1">Sağlayıcı</label>
            <select
              {...form.register("provider")}
              onChange={(e) => {
                form.setValue("provider", e.target.value as "openai" | "gemini");
                const opts =
                  e.target.value === "gemini" ? GEMINI_MODELS : OPENAI_MODELS;
                form.setValue("model", opts[0]);
              }}
              className="border border-gray-300 rounded-md px-3 py-2 text-sm w-full focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              <option value="openai">OpenAI</option>
              <option value="gemini">Gemini</option>
            </select>
          </div>

          <div>
            <label className="text-sm font-medium block mb-1">Model</label>
            <select
              {...form.register("model")}
              className="border border-gray-300 rounded-md px-3 py-2 text-sm w-full focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              {modelOptions.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="text-sm font-medium block mb-1">API Anahtarı</label>
            <input
              {...form.register("api_key")}
              type="password"
              className="border border-gray-300 rounded-md px-3 py-2 text-sm w-full focus:outline-none focus:ring-2 focus:ring-indigo-500"
              placeholder="sk-..."
            />
            {form.formState.errors.api_key && (
              <p className="text-xs text-red-600 mt-1">
                {form.formState.errors.api_key.message}
              </p>
            )}
          </div>

          <div className="flex items-center justify-between py-1">
            <label className="text-sm font-medium">Aktif</label>
            <Toggle
              checked={form.watch("is_active")}
              onCheckedChange={(val) => form.setValue("is_active", val)}
            />
          </div>

          <div className="flex gap-3 pt-2">
            <button
              type="submit"
              disabled={isPending}
              className="bg-indigo-600 text-white px-4 py-2 rounded-md text-sm hover:bg-indigo-700 disabled:opacity-50 transition-colors"
            >
              {isPending ? "Kaydediliyor…" : initial ? "Kaydet" : "Ekle"}
            </button>
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 rounded-md text-sm border border-gray-300 hover:bg-gray-50"
            >
              Vazgeç
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export function EmbeddingList() {
  const qc = useQueryClient();
  const [showModal, setShowModal] = useState(false);
  const [editTarget, setEditTarget] = useState<EmbeddingModel | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);

  const { data: models = [], isLoading } = useQuery({
    queryKey: ["embeddings"],
    queryFn: embeddingsApi.list,
  });

  const toggleMutation = useMutation({
    mutationFn: ({ id, is_active }: { id: string; is_active: boolean }) =>
      embeddingsApi.update(id, { is_active }),
    onSuccess: (_, { is_active }) => {
      qc.invalidateQueries({ queryKey: ["embeddings"] });
      toast.success(is_active ? "Model etkinleştirildi." : "Model devre dışı bırakıldı.");
    },
    onError: () => toast.error("Durum güncellenemedi."),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => embeddingsApi.delete(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["embeddings"] });
      setDeleteTarget(null);
      toast.success("Embedding modeli silindi.");
    },
    onError: () => toast.error("Model silinemedi."),
  });

  if (isLoading) return <p className="text-gray-400 text-sm">Embedding modelleri yükleniyor…</p>;

  return (
    <div>
      <div className="flex justify-end mb-3">
        <button
          onClick={() => {
            setEditTarget(null);
            setShowModal(true);
          }}
          className="flex items-center gap-2 bg-indigo-600 text-white px-4 py-2 rounded-md text-sm hover:bg-indigo-700 transition-colors"
        >
          <Plus className="w-4 h-4" />
          Embedding Modeli Ekle
        </button>
      </div>

      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-xs uppercase text-gray-500">
            <tr>
              <th className="px-4 py-3 text-left">İsim</th>
              <th className="px-4 py-3 text-left">Sağlayıcı</th>
              <th className="px-4 py-3 text-left">Model</th>
              <th className="px-4 py-3 text-center">Aktif</th>
              <th className="px-4 py-3 text-right">İşlem</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {models.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-gray-400 text-sm">
                  Henüz embedding modeli yapılandırılmadı.
                </td>
              </tr>
            )}
            {models.map((model: EmbeddingModel) => (
              <tr key={model.id} className="hover:bg-gray-50">
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    <Layers className="w-4 h-4 text-gray-400" />
                    <span className="font-medium text-gray-800">{model.name}</span>
                  </div>
                </td>
                <td className="px-4 py-3">
                  <ProviderBadge provider={model.provider} />
                </td>
                <td className="px-4 py-3 font-mono text-xs text-gray-600">
                  {(model.config?.model as string) ?? "—"}
                </td>
                <td className="px-4 py-3 text-center">
                  <div className="flex justify-center">
                    <Toggle
                      checked={model.is_active}
                      onCheckedChange={(val) =>
                        toggleMutation.mutate({ id: model.id, is_active: val })
                      }
                    />
                  </div>
                </td>
                <td className="px-4 py-3 text-right">
                  <span className="flex items-center gap-3 justify-end">
                    <button
                      onClick={() => {
                        setEditTarget(model);
                        setShowModal(true);
                      }}
                      className="text-gray-400 hover:text-indigo-600 transition-colors"
                      title="Düzenle"
                    >
                      <Pencil className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => setDeleteTarget(model.id)}
                      className="text-gray-400 hover:text-red-600 transition-colors"
                      title="Sil"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <ConfirmDialog
        open={deleteTarget != null}
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => deleteTarget && deleteMutation.mutate(deleteTarget)}
        loading={deleteMutation.isPending}
        title="Embedding Modelini Sil"
        description="Bu model kalıcı olarak silinecek. Bu işlem geri alınamaz."
        confirmLabel="Evet, sil"
      />

      {showModal && (
        <EmbeddingModal
          initial={editTarget ?? undefined}
          onClose={() => {
            setShowModal(false);
            setEditTarget(null);
          }}
        />
      )}
    </div>
  );
}

"use client";
import { useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { documentsApi } from "@/lib/api";
import type { Document } from "@/lib/types";
import { FileText, Upload, X, Trash2, Loader2 } from "lucide-react";
import { Toggle } from "@/components/ui/Toggle";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { formatBytes } from "@/lib/utils";

function sourceTypeBadge(type: string) {
  const colors: Record<string, string> = {
    pdf: "bg-red-50 text-red-700",
    docx: "bg-blue-50 text-blue-700",
    doc: "bg-blue-50 text-blue-700",
    txt: "bg-gray-100 text-gray-600",
  };
  return colors[type] ?? "bg-gray-100 text-gray-600";
}

function fileNameWithoutExtension(name: string): string {
  return name.replace(/\.[^/.]+$/, "");
}

export function DocumentList() {
  const qc = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadTitle, setUploadTitle] = useState("");
  const [uploadTags, setUploadTags] = useState("");
  const [uploadLanguage, setUploadLanguage] = useState("");
  const [isUploading, setIsUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);

  const { data: documents = [], isLoading } = useQuery({
    queryKey: ["documents"],
    queryFn: () => documentsApi.list(true),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => documentsApi.delete(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["documents"] });
      setDeleteTarget(null);
      toast.success("Belge silindi.");
    },
    onError: () => toast.error("Belge silinemedi."),
  });

  const toggleMutation = useMutation({
    mutationFn: ({ id, is_active }: { id: string; is_active: boolean }) =>
      documentsApi.update(id, { is_active }),
    onSuccess: (_, { is_active }) => {
      qc.invalidateQueries({ queryKey: ["documents"] });
      toast.success(is_active ? "Belge etkinleştirildi." : "Belge devre dışı bırakıldı.");
    },
    onError: () => toast.error("Durum güncellenemedi."),
  });

  function handleFiles(files: FileList | null) {
    if (!files || files.length === 0) return;
    setSelectedFile(files[0]);
    setUploadTitle("");
    setUploadTags("");
    setUploadLanguage("");
  }

  function handleDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragOver(false);
    handleFiles(e.dataTransfer.files);
  }

  function cancelUpload() {
    setSelectedFile(null);
    setUploadTitle("");
    setUploadTags("");
    setUploadLanguage("");
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  async function handleUpload() {
    if (!selectedFile) return;
    setIsUploading(true);
    try {
      const result = await documentsApi.upload(
        selectedFile,
        uploadTitle || undefined,
        uploadTags || undefined,
        uploadLanguage || undefined
      );
      qc.invalidateQueries({ queryKey: ["documents"] });
      toast.success(`${result.title} — ${result.chunk_count} chunk oluşturuldu.`);
      cancelUpload();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Yükleme başarısız.");
    } finally {
      setIsUploading(false);
    }
  }

  return (
    <div className="space-y-6">
      {/* Upload Zone */}
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <div
          onDrop={handleDrop}
          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onClick={() => !selectedFile && fileInputRef.current?.click()}
          className={`border-2 border-dashed rounded-xl flex flex-col items-center justify-center py-10 gap-2 transition-colors ${
            dragOver
              ? "border-indigo-500 bg-indigo-50 cursor-copy"
              : selectedFile
              ? "border-gray-200 bg-gray-50 cursor-default"
              : "border-gray-300 hover:border-indigo-400 hover:bg-indigo-50/30 cursor-pointer"
          }`}
        >
          <Upload className={`w-8 h-8 ${dragOver ? "text-indigo-500" : "text-gray-400"}`} />
          <p className="text-sm font-medium text-gray-600">Dosyayı buraya bırakın veya tıklayın</p>
          <p className="text-xs text-gray-400">PDF, DOCX, DOC, TXT</p>
        </div>

        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.docx,.doc,.txt"
          className="hidden"
          onChange={(e) => handleFiles(e.target.files)}
        />

        {selectedFile && !isUploading && (
          <div className="mt-4 space-y-3">
            <div className="flex items-center gap-2 px-3 py-2 bg-gray-50 rounded-lg border border-gray-200">
              <FileText className="w-4 h-4 text-gray-400 shrink-0" />
              <span className="text-sm text-gray-700 font-medium truncate">{selectedFile.name}</span>
              <span className="text-xs text-gray-400 ml-auto shrink-0">{formatBytes(selectedFile.size)}</span>
              <button onClick={cancelUpload} className="ml-1 text-gray-300 hover:text-gray-500">
                <X className="w-3.5 h-3.5" />
              </button>
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">Başlık (isteğe bağlı)</label>
              <input
                type="text"
                value={uploadTitle}
                onChange={(e) => setUploadTitle(e.target.value)}
                placeholder={fileNameWithoutExtension(selectedFile.name)}
                className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">Etiketler (isteğe bağlı)</label>
              <input
                type="text"
                value={uploadTags}
                onChange={(e) => setUploadTags(e.target.value)}
                placeholder="etiket1, etiket2"
                className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-gray-500 mb-1">Dil (isteğe bağlı)</label>
              <input
                type="text"
                value={uploadLanguage}
                onChange={(e) => setUploadLanguage(e.target.value)}
                placeholder="tr, en, ..."
                className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>

            <div className="flex gap-3 pt-1">
              <button
                onClick={handleUpload}
                className="bg-indigo-600 text-white px-4 py-2 rounded-md text-sm font-medium hover:bg-indigo-700 transition-colors"
              >
                Yükle
              </button>
              <button
                onClick={cancelUpload}
                className="px-4 py-2 rounded-md text-sm font-medium border border-gray-300 text-gray-600 hover:bg-gray-50 transition-colors"
              >
                Vazgeç
              </button>
            </div>
          </div>
        )}

        {isUploading && (
          <div className="mt-4 flex items-center gap-3 text-sm text-indigo-700 bg-indigo-50 border border-indigo-200 rounded-lg px-4 py-3">
            <Loader2 className="w-4 h-4 animate-spin shrink-0" />
            Yükleniyor ve embedding oluşturuluyor…
          </div>
        )}
      </div>

      {/* Documents Table */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        {isLoading ? (
          <div className="animate-pulse">
            <div className="h-10 bg-gray-50 border-b border-gray-200" />
            {[...Array(4)].map((_, i) => (
              <div key={i} className="flex gap-4 px-4 py-3 border-b border-gray-100 last:border-0">
                {[...Array(7)].map((_, j) => <div key={j} className="h-4 bg-gray-200 rounded flex-1" />)}
              </div>
            ))}
          </div>
        ) : documents.length === 0 ? (
          <EmptyState
            icon={<FileText className="w-6 h-6" />}
            title="Henüz belge yüklenmedi"
            description="Bilgi tabanınıza PDF, DOCX veya TXT dosyaları yükleyin."
          />
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-xs uppercase text-gray-500">
              <tr>
                <th className="px-4 py-3 text-left">Başlık</th>
                <th className="px-4 py-3 text-left">Tür</th>
                <th className="px-4 py-3 text-center">Chunk</th>
                <th className="px-4 py-3 text-left">Boyut</th>
                <th className="px-4 py-3 text-left">Embedding Modeli</th>
                <th className="px-4 py-3 text-center">Aktif</th>
                <th className="px-4 py-3 text-right">İşlem</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {documents.map((doc: Document) => (
                <tr key={doc.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <FileText className="w-4 h-4 text-gray-400 shrink-0" />
                      <div>
                        <p className="font-medium text-gray-800 truncate max-w-[200px]">{doc.title}</p>
                        {doc.file_name && doc.file_name !== doc.title && (
                          <p className="text-xs text-gray-400 truncate max-w-[200px]">{doc.file_name}</p>
                        )}
                      </div>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${sourceTypeBadge(doc.source_type)}`}>
                      {doc.source_type}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-center text-gray-700">{doc.chunk_count}</td>
                  <td className="px-4 py-3 text-gray-600">{formatBytes(doc.file_size)}</td>
                  <td className="px-4 py-3 text-gray-500 text-xs truncate max-w-[160px]">
                    {doc.embedding_model ?? "—"}
                  </td>
                  <td className="px-4 py-3 text-center">
                    <div className="flex justify-center">
                      <Toggle
                        checked={doc.is_active}
                        onCheckedChange={(val) => toggleMutation.mutate({ id: doc.id, is_active: val })}
                      />
                    </div>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <button
                      onClick={() => setDeleteTarget(doc.id)}
                      className="inline-flex items-center gap-1 text-xs text-gray-400 hover:text-red-600 transition-colors"
                      title="Sil"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                      Sil
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <ConfirmDialog
        open={deleteTarget != null}
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => deleteTarget && deleteMutation.mutate(deleteTarget)}
        loading={deleteMutation.isPending}
        title="Belgeyi Sil"
        description="Bu belge ve tüm chunk'ları kalıcı olarak silinecek. Bu işlem geri alınamaz."
        confirmLabel="Evet, sil"
      />
    </div>
  );
}

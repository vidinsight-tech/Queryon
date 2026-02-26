"use client";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { channelsApi } from "@/lib/api";
import type { ChannelsResponse, TelegramWebhookInfo, WhatsAppConnectionTest } from "@/lib/types";
import {
  Send,
  MessageCircle,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Copy,
  Eye,
  EyeOff,
  Trash2,
  X,
  ExternalLink,
  ChevronRight,
  RefreshCw,
  Link2,
  Link2Off,
} from "lucide-react";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ── helpers ──────────────────────────────────────────────────────────────────

function StatusBadge({ configured }: { configured: boolean }) {
  return configured ? (
    <span className="inline-flex items-center gap-1 text-xs font-medium text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-full">
      <CheckCircle2 className="w-3 h-3" />
      Bağlı
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 text-xs font-medium text-gray-500 bg-gray-100 border border-gray-200 px-2 py-0.5 rounded-full">
      <XCircle className="w-3 h-3" />
      Bağlı Değil
    </span>
  );
}

function CopyableUrl({ path }: { path: string }) {
  const url = `${BASE_URL}${path}`;
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText(url).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };
  return (
    <div className="flex items-center gap-1.5">
      <code className="text-xs text-gray-600 bg-gray-100 px-2 py-0.5 rounded font-mono truncate max-w-xs">
        {url}
      </code>
      <button onClick={copy} className="text-gray-400 hover:text-gray-600 shrink-0" title="Kopyala">
        <Copy className="w-3.5 h-3.5" />
      </button>
      {copied && <span className="text-xs text-emerald-600 font-medium">Kopyalandı!</span>}
    </div>
  );
}

// ── Telegram webhook status panel ─────────────────────────────────────────────

function TelegramWebhookPanel() {
  const [publicUrl, setPublicUrl] = useState("");
  const [showRegister, setShowRegister] = useState(false);
  const qc = useQueryClient();

  const { data: info, isLoading, refetch, isError } = useQuery({
    queryKey: ["telegram-webhook-info"],
    queryFn: channelsApi.telegramWebhookInfo,
    retry: false,
  });

  const registerMutation = useMutation({
    mutationFn: () => channelsApi.registerTelegramWebhook(publicUrl.trim()),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ["telegram-webhook-info"] });
      setShowRegister(false);
      setPublicUrl("");
      toast.success(`Webhook kaydedildi: ${res.webhook_url}`);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  if (isLoading) {
    return (
      <p className="text-xs text-gray-400 flex items-center gap-1">
        <RefreshCw className="w-3 h-3 animate-spin" /> Webhook durumu kontrol ediliyor…
      </p>
    );
  }

  if (isError || !info) {
    return null; // don't show anything if token check fails
  }

  return (
    <div className="mt-3 space-y-2">
      {/* Webhook URL status */}
      <div className={`rounded-lg border p-3 text-xs ${
        info.registered
          ? info.last_error_message
            ? "bg-amber-50 border-amber-200"
            : "bg-emerald-50 border-emerald-200"
          : "bg-red-50 border-red-200"
      }`}>
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-1.5 font-medium">
            {info.registered ? (
              info.last_error_message ? (
                <><AlertTriangle className="w-3.5 h-3.5 text-amber-600" /><span className="text-amber-800">Webhook kayıtlı — hata var</span></>
              ) : (
                <><Link2 className="w-3.5 h-3.5 text-emerald-600" /><span className="text-emerald-800">Webhook aktif</span></>
              )
            ) : (
              <><Link2Off className="w-3.5 h-3.5 text-red-600" /><span className="text-red-800">Webhook kayıtlı değil — mesajlar iletilmiyor</span></>
            )}
          </div>
          <button
            onClick={() => refetch()}
            className="text-gray-400 hover:text-gray-600"
            title="Yenile"
          >
            <RefreshCw className="w-3 h-3" />
          </button>
        </div>

        {info.registered && (
          <p className="mt-1 font-mono text-gray-600 break-all">{info.url}</p>
        )}
        {info.last_error_message && (
          <p className="mt-1 text-amber-700">
            Son hata: {info.last_error_message}
          </p>
        )}
        {info.pending_update_count > 0 && (
          <p className="mt-1 text-gray-600">
            Bekleyen güncelleme: <strong>{info.pending_update_count}</strong>
          </p>
        )}
      </div>

      {/* Register / update webhook */}
      {!showRegister ? (
        <button
          onClick={() => setShowRegister(true)}
          className="flex items-center gap-1.5 text-xs text-indigo-600 hover:text-indigo-700 font-medium"
        >
          <Link2 className="w-3.5 h-3.5" />
          {info.registered ? "Webhook URL'ini güncelle" : "Webhook'u Telegram'a kaydet"}
        </button>
      ) : (
        <div className="space-y-2">
          <p className="text-xs text-gray-500">
            Sunucunuzun dışarıdan erişilebilir URL'sini girin (örn. ngrok, Render, VPS).
          </p>
          <div className="flex gap-2">
            <input
              type="url"
              value={publicUrl}
              onChange={(e) => setPublicUrl(e.target.value)}
              placeholder="https://abc123.ngrok.io"
              className="flex-1 border border-gray-300 rounded-md px-3 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
            <button
              onClick={() => registerMutation.mutate()}
              disabled={!publicUrl.trim() || registerMutation.isPending}
              className="px-3 py-1.5 bg-indigo-600 text-white text-xs rounded-md hover:bg-indigo-700 disabled:opacity-50"
            >
              {registerMutation.isPending ? "Kaydediliyor…" : "Kaydet"}
            </button>
            <button
              onClick={() => { setShowRegister(false); setPublicUrl(""); }}
              className="px-3 py-1.5 border border-gray-300 text-xs rounded-md hover:bg-gray-50"
            >
              Vazgeç
            </button>
          </div>
          <p className="text-xs text-gray-400">
            Webhook URL olarak şu eklenecek:{" "}
            <span className="font-mono">{publicUrl.trim() || "…"}/webhooks/telegram</span>
          </p>
        </div>
      )}
    </div>
  );
}

// ── WhatsApp connection test panel ────────────────────────────────────────────

function WhatsAppStatusPanel({ verifiedAt }: { verifiedAt: string | null }) {
  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ["whatsapp-test"],
    queryFn: channelsApi.whatsappTestConnection,
    retry: false,
    staleTime: 60_000,
  });

  const verifiedDate = verifiedAt
    ? new Date(verifiedAt).toLocaleString("tr-TR")
    : null;

  return (
    <div className="mt-3 space-y-2">
      {/* Token validity */}
      {isLoading ? (
        <p className="text-xs text-gray-400 flex items-center gap-1">
          <RefreshCw className="w-3 h-3 animate-spin" /> Token doğrulanıyor…
        </p>
      ) : data ? (
        <div className={`rounded-lg border p-3 text-xs ${
          data.ok ? "bg-emerald-50 border-emerald-200" : "bg-red-50 border-red-200"
        }`}>
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-1.5 font-medium">
              {data.ok ? (
                <><CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" /><span className="text-emerald-800">Token geçerli</span></>
              ) : (
                <><XCircle className="w-3.5 h-3.5 text-red-600" /><span className="text-red-800">Token hatası</span></>
              )}
            </div>
            <button onClick={() => refetch()} disabled={isFetching} className="text-gray-400 hover:text-gray-600 disabled:opacity-40" title="Yeniden test et">
              <RefreshCw className={`w-3 h-3 ${isFetching ? "animate-spin" : ""}`} />
            </button>
          </div>
          {data.ok && (
            <div className="mt-1.5 space-y-0.5 text-gray-600">
              {data.display_phone_number && <p>Numara: <span className="font-mono">{data.display_phone_number}</span></p>}
              {data.verified_name && <p>Hesap adı: <span className="font-medium">{data.verified_name}</span></p>}
            </div>
          )}
          {!data.ok && data.error_message && <p className="mt-1 text-red-700">{data.error_message}</p>}
        </div>
      ) : null}

      {/* Meta webhook verification status */}
      <div className={`rounded-lg border p-3 text-xs ${
        verifiedDate ? "bg-emerald-50 border-emerald-200" : "bg-amber-50 border-amber-200"
      }`}>
        <div className="flex items-center gap-1.5 font-medium">
          {verifiedDate ? (
            <><Link2 className="w-3.5 h-3.5 text-emerald-600" /><span className="text-emerald-800">Meta webhook doğruladı</span></>
          ) : (
            <><Link2Off className="w-3.5 h-3.5 text-amber-600" /><span className="text-amber-800">Meta henüz webhook doğrulamadı</span></>
          )}
        </div>
        {verifiedDate && (
          <p className="mt-1 text-emerald-700">Son doğrulama: {verifiedDate}</p>
        )}
        {!verifiedDate && (
          <div className="mt-2 space-y-0.5 text-amber-700">
            <p className="font-medium text-amber-800">Meta Console'da yapılandırın:</p>
            <ol className="list-decimal list-inside space-y-0.5">
              <li>
                <a href="https://developers.facebook.com" target="_blank" rel="noopener noreferrer" className="underline inline-flex items-center gap-0.5">
                  Meta Developer Console<ExternalLink className="w-2.5 h-2.5" />
                </a>
                {" "}→ Uygulamanız → WhatsApp → Configuration
              </li>
              <li>Callback URL: <span className="font-mono break-all">{BASE_URL}/webhooks/whatsapp</span></li>
              <li>Verify Token: yapılandırmada girdiğiniz değer</li>
              <li><strong>messages</strong> webhook alanına abone olun</li>
            </ol>
          </div>
        )}
      </div>
    </div>
  );
}


// ── Telegram config modal ─────────────────────────────────────────────────────

function TelegramModal({
  current,
  onClose,
}: {
  current: ChannelsResponse["telegram"];
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [token, setToken] = useState("");
  const [showToken, setShowToken] = useState(false);

  const mutation = useMutation({
    mutationFn: () => channelsApi.saveTelegram(token.trim()),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["channels"] });
      qc.invalidateQueries({ queryKey: ["telegram-webhook-info"] });
      toast.success("Telegram token kaydedildi.");
      onClose();
    },
    onError: () => toast.error("Kayıt başarısız oldu."),
  });

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl shadow-xl p-6 w-full max-w-md">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Send className="w-5 h-5 text-sky-500" />
            <h2 className="font-bold text-lg">Telegram Bot Yapılandır</h2>
          </div>
          <button onClick={onClose} className="p-1.5 text-gray-400 hover:text-gray-600 rounded-md hover:bg-gray-100">
            <X className="w-4 h-4" />
          </button>
        </div>

        <p className="text-sm text-gray-500 mb-4">
          <a
            href="https://t.me/BotFather"
            target="_blank"
            rel="noopener noreferrer"
            className="text-indigo-600 hover:underline inline-flex items-center gap-0.5"
          >
            @BotFather
            <ExternalLink className="w-3 h-3" />
          </a>{" "}
          ile oluşturduğunuz bot token'ını girin.
        </p>

        {current.configured && current.masked_token && (
          <div className="mb-3 p-3 rounded-lg bg-emerald-50 border border-emerald-200 text-xs text-emerald-700">
            Mevcut token: <span className="font-mono">{current.masked_token}</span>
          </div>
        )}

        <label className="block text-xs font-medium text-gray-600 mb-1">Bot Token</label>
        <div className="relative">
          <input
            type={showToken ? "text" : "password"}
            value={token}
            onChange={(e) => setToken(e.target.value)}
            placeholder="1234567890:ABCdef..."
            className="w-full border border-gray-300 rounded-md px-3 py-2 pr-9 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
          <button
            type="button"
            onClick={() => setShowToken((v) => !v)}
            className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
          >
            {showToken ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
          </button>
        </div>

        <div className="flex gap-3 mt-5">
          <button
            onClick={() => mutation.mutate()}
            disabled={!token.trim() || mutation.isPending}
            className="bg-indigo-600 text-white px-4 py-2 rounded-md text-sm hover:bg-indigo-700 disabled:opacity-50"
          >
            {mutation.isPending ? "Kaydediliyor…" : "Kaydet"}
          </button>
          <button onClick={onClose} className="px-4 py-2 rounded-md text-sm border border-gray-300 hover:bg-gray-50">
            Vazgeç
          </button>
        </div>
      </div>
    </div>
  );
}

// ── WhatsApp config modal ─────────────────────────────────────────────────────

function WhatsAppModal({
  current,
  onClose,
}: {
  current: ChannelsResponse["whatsapp"];
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [accessToken, setAccessToken] = useState("");
  const [phoneNumberId, setPhoneNumberId] = useState(current.phone_number_id ?? "");
  const [verifyToken, setVerifyToken] = useState("");
  const [showToken, setShowToken] = useState(false);

  const mutation = useMutation({
    mutationFn: () =>
      channelsApi.saveWhatsApp({
        access_token: accessToken.trim(),
        phone_number_id: phoneNumberId.trim(),
        verify_token: verifyToken.trim(),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["channels"] });
      toast.success("WhatsApp yapılandırması kaydedildi.");
      onClose();
    },
    onError: () => toast.error("Kayıt başarısız oldu."),
  });

  const isValid = accessToken.trim() && phoneNumberId.trim() && verifyToken.trim();

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl shadow-xl p-6 w-full max-w-md">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <MessageCircle className="w-5 h-5 text-emerald-500" />
            <h2 className="font-bold text-lg">WhatsApp Business Yapılandır</h2>
          </div>
          <button onClick={onClose} className="p-1.5 text-gray-400 hover:text-gray-600 rounded-md hover:bg-gray-100">
            <X className="w-4 h-4" />
          </button>
        </div>

        <p className="text-sm text-gray-500 mb-4">
          Meta Developer Console &rsaquo; WhatsApp &rsaquo; Configuration bölümünden alınan bilgileri girin.
        </p>

        {current.configured && current.masked_token && (
          <div className="mb-3 p-3 rounded-lg bg-emerald-50 border border-emerald-200 text-xs text-emerald-700">
            Mevcut token: <span className="font-mono">{current.masked_token}</span>
          </div>
        )}

        <div className="space-y-3">
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Access Token</label>
            <div className="relative">
              <input
                type={showToken ? "text" : "password"}
                value={accessToken}
                onChange={(e) => setAccessToken(e.target.value)}
                placeholder="EAABc..."
                className="w-full border border-gray-300 rounded-md px-3 py-2 pr-9 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
              <button
                type="button"
                onClick={() => setShowToken((v) => !v)}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
              >
                {showToken ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">Phone Number ID</label>
            <input
              type="text"
              value={phoneNumberId}
              onChange={(e) => setPhoneNumberId(e.target.value)}
              placeholder="123456789012345"
              className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">
              Verify Token{" "}
              <span className="font-normal text-gray-400">(Meta doğrulaması için rastgele bir değer)</span>
            </label>
            <input
              type="text"
              value={verifyToken}
              onChange={(e) => setVerifyToken(e.target.value)}
              placeholder="my-secret-verify-token"
              className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>
        </div>

        <div className="mt-4 p-3 bg-gray-50 border border-gray-200 rounded-lg text-xs text-gray-600">
          <p className="font-medium text-gray-700 mb-1">Meta Webhook Kurulumu</p>
          <ul className="space-y-0.5 list-disc list-inside text-gray-500">
            <li>Callback URL: <span className="font-mono">{BASE_URL}/webhooks/whatsapp</span></li>
            <li>Verify Token: <span className="italic">yukarıda girdiğiniz değer</span></li>
          </ul>
        </div>

        <div className="flex gap-3 mt-5">
          <button
            onClick={() => mutation.mutate()}
            disabled={!isValid || mutation.isPending}
            className="bg-indigo-600 text-white px-4 py-2 rounded-md text-sm hover:bg-indigo-700 disabled:opacity-50"
          >
            {mutation.isPending ? "Kaydediliyor…" : "Kaydet"}
          </button>
          <button onClick={onClose} className="px-4 py-2 rounded-md text-sm border border-gray-300 hover:bg-gray-50">
            Vazgeç
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Channel card ──────────────────────────────────────────────────────────────

function ChannelCard({
  icon: Icon,
  iconColor,
  title,
  description,
  webhookPath,
  configured,
  detail,
  extra,
  onConfigure,
  onDelete,
}: {
  icon: React.ElementType;
  iconColor: string;
  title: string;
  description: string;
  webhookPath: string;
  configured: boolean;
  detail?: React.ReactNode;
  extra?: React.ReactNode;
  onConfigure: () => void;
  onDelete: () => void;
}) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-start gap-3 flex-1 min-w-0">
          <div className={`mt-0.5 p-2 rounded-lg shrink-0 ${iconColor}`}>
            <Icon className="w-5 h-5" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-semibold text-gray-900">{title}</span>
              <StatusBadge configured={configured} />
            </div>
            <p className="text-sm text-gray-500 mt-0.5">{description}</p>
            {detail && <div className="mt-1 text-xs text-gray-500">{detail}</div>}
            <div className="mt-2">
              <span className="text-xs text-gray-400 font-medium">Webhook URL</span>
              <div className="mt-0.5">
                <CopyableUrl path={webhookPath} />
              </div>
            </div>
            {extra}
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {configured && (
            <button
              onClick={onDelete}
              className="p-1.5 text-gray-400 hover:text-red-500 transition-colors rounded-md hover:bg-red-50"
              title="Bağlantıyı kaldır"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          )}
          <button
            onClick={onConfigure}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-indigo-600 border border-indigo-200 rounded-md hover:bg-indigo-50 transition-colors"
          >
            {configured ? "Güncelle" : "Yapılandır"}
            <ChevronRight className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Main ──────────────────────────────────────────────────────────────────────

export function ChannelList() {
  const qc = useQueryClient();
  const [showTelegram, setShowTelegram] = useState(false);
  const [showWhatsApp, setShowWhatsApp] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<"telegram" | "whatsapp" | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["channels"],
    queryFn: channelsApi.get,
  });

  const deleteMutation = useMutation({
    mutationFn: (platform: "telegram" | "whatsapp") =>
      platform === "telegram" ? channelsApi.deleteTelegram() : channelsApi.deleteWhatsApp(),
    onSuccess: (_, platform) => {
      qc.invalidateQueries({ queryKey: ["channels"] });
      qc.invalidateQueries({ queryKey: ["telegram-webhook-info"] });
      setDeleteTarget(null);
      toast.success(
        platform === "telegram" ? "Telegram bağlantısı kaldırıldı." : "WhatsApp bağlantısı kaldırıldı."
      );
    },
    onError: () => toast.error("Bağlantı kaldırılamadı."),
  });

  if (isLoading) return <p className="text-sm text-gray-400">Entegrasyonlar yükleniyor…</p>;

  const tg = data?.telegram ?? { configured: false, masked_token: null };
  const wa = data?.whatsapp ?? { configured: false, masked_token: null, phone_number_id: null, verify_token_set: false, verified_at: null };

  return (
    <div className="space-y-4">
      <ChannelCard
        icon={Send}
        iconColor="bg-sky-50 text-sky-500"
        title="Telegram"
        description="Bot aracılığıyla Telegram mesajlarını alın ve yanıtlayın."
        webhookPath="/webhooks/telegram"
        configured={tg.configured}
        detail={tg.configured && tg.masked_token ? `Token: ${tg.masked_token}` : undefined}
        extra={tg.configured ? <TelegramWebhookPanel /> : undefined}
        onConfigure={() => setShowTelegram(true)}
        onDelete={() => setDeleteTarget("telegram")}
      />

      <ChannelCard
        icon={MessageCircle}
        iconColor="bg-emerald-50 text-emerald-600"
        title="WhatsApp Business"
        description="Meta Cloud API üzerinden WhatsApp mesajlarını alın ve yanıtlayın."
        webhookPath="/webhooks/whatsapp"
        configured={wa.configured}
        detail={
          wa.configured
            ? [
                wa.masked_token && `Token: ${wa.masked_token}`,
                wa.phone_number_id && `Phone ID: ${wa.phone_number_id}`,
                wa.verify_token_set && "Verify Token: ayarlı",
              ]
                .filter(Boolean)
                .join(" · ")
            : undefined
        }
        extra={wa.configured ? <WhatsAppStatusPanel verifiedAt={wa.verified_at} /> : undefined}
        onConfigure={() => setShowWhatsApp(true)}
        onDelete={() => setDeleteTarget("whatsapp")}
      />

      {showTelegram && <TelegramModal current={tg} onClose={() => setShowTelegram(false)} />}
      {showWhatsApp && <WhatsAppModal current={wa} onClose={() => setShowWhatsApp(false)} />}

      <ConfirmDialog
        open={deleteTarget != null}
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => deleteTarget && deleteMutation.mutate(deleteTarget)}
        loading={deleteMutation.isPending}
        title="Bağlantıyı Kaldır"
        description={`${deleteTarget === "telegram" ? "Telegram" : "WhatsApp"} yapılandırması kalıcı olarak silinecek.`}
        confirmLabel="Evet, kaldır"
      />
    </div>
  );
}

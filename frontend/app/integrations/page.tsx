import dynamic from "next/dynamic";

const ChannelList = dynamic(
  () => import("@/components/integrations/ChannelList").then((m) => m.ChannelList),
  { ssr: false, loading: () => <div className="py-8 text-center text-sm text-gray-400">Yükleniyor…</div> }
);

export default function IntegrationsPage() {
  return (
    <div className="max-w-3xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Entegrasyonlar</h1>
        <p className="text-sm text-gray-500 mt-1">
          Telegram ve WhatsApp kanallarını yapılandırın. Kayıtlı kimlik
          bilgileri webhook uç noktalarında otomatik olarak kullanılır.
        </p>
      </div>
      <ChannelList />
    </div>
  );
}

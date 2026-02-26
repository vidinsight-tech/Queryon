"use client";
import { useState } from "react";
import type { BotConfig } from "@/lib/types";
import { Eye, EyeOff } from "lucide-react";

interface Props {
  config: BotConfig;
  onChange: (patch: Partial<BotConfig>) => void;
}

const PERSONA_PLACEHOLDER = `Örnek:
Sen Bella, Bella Kuaför'ün yardımcı asistanısın.
Müşterilere sıcak ve profesyonel bir şekilde yardımcı olursun.
Randevu alabilir, fiyatlar ve hizmetler hakkında bilgi verebilirsin.`;

const RESTRICTIONS_PLACEHOLDER = `Örnek:
- Rakip firmalar hakkında yorum yapma
- Fiyat karşılaştırması yapma
- Siyasi konulara girme`;


export function IdentityForm({ config, onChange }: Props) {
  const [showSecret, setShowSecret] = useState(false);

  return (
    <div className="space-y-5 max-w-xl">
      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1.5">
          Bot Adı
        </label>
        <input
          type="text"
          value={config.bot_name ?? ""}
          onChange={(e) => onChange({ bot_name: e.target.value })}
          placeholder="Assistant"
          className="w-full text-sm border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500"
        />
        <p className="text-xs text-gray-400 mt-1">
          Chatbot&apos;un kendini tanıtırken kullandığı isim.
        </p>
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1.5">
          Kişilik / Sistem Promptu
        </label>
        <textarea
          value={config.character_system_prompt ?? ""}
          onChange={(e) => onChange({ character_system_prompt: e.target.value || null })}
          placeholder={PERSONA_PLACEHOLDER}
          rows={12}
          className="w-full text-sm border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500 font-mono resize-y"
        />
        <p className="text-xs text-gray-400 mt-1">
          Botun kim olduğunu, ne yapabileceğini ve nasıl konuşacağını açıkla.
          Randevu/sipariş alanları &quot;Modes&quot; sekmesinden eklenir ve bu prompta otomatik eklenir.
        </p>
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 mb-1.5">
          Kısıtlamalar / Yasaklar
        </label>
        <textarea
          value={config.restrictions ?? ""}
          onChange={(e) => onChange({ restrictions: e.target.value || null })}
          placeholder={RESTRICTIONS_PLACEHOLDER}
          rows={4}
          className="w-full text-sm border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-y"
        />
        <p className="text-xs text-gray-400 mt-1">
          Botun kesinlikle konuşmaması veya yardımcı olmaması gereken konuları belirt.
        </p>
      </div>

      {/* Webhook Integration */}
      <div className="border-t border-gray-100 pt-5">
        <h3 className="text-sm font-semibold text-gray-700 mb-1">Webhook Entegrasyonu</h3>
        <p className="text-xs text-gray-400 mb-4">
          Randevu oluşturulduğunda/değiştirildiğinde/iptal edildiğinde dış sisteminize
          HMAC-SHA256 imzalı JSON olayı gönderilir. Aynı secret ile inbound webhook
          endpoint&apos;ine ({" "}
          <code className="bg-gray-100 px-1 rounded text-xs">/api/v1/appointments/webhook/inbound</code>
          ) güvenli güncelleme yapabilirsiniz.
        </p>

        <div className="space-y-3">
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">
              Webhook URL
            </label>
            <input
              type="url"
              value={config.appointment_webhook_url ?? ""}
              onChange={(e) => onChange({ appointment_webhook_url: e.target.value || null })}
              placeholder="https://your-server.com/webhook"
              className="w-full text-sm border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1">
              Webhook Secret
            </label>
            <div className="flex items-center gap-2">
              <input
                type={showSecret ? "text" : "password"}
                value={config.appointment_webhook_secret ?? ""}
                onChange={(e) => onChange({ appointment_webhook_secret: e.target.value || null })}
                placeholder="güçlü-bir-secret"
                className="flex-1 text-sm border border-gray-300 rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500 font-mono"
              />
              <button
                type="button"
                onClick={() => setShowSecret((s) => !s)}
                className="p-2 text-gray-400 hover:text-gray-600 transition-colors"
                title={showSecret ? "Gizle" : "Göster"}
              >
                {showSecret ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
            <p className="text-xs text-gray-400 mt-1">
              Outbound event header: <code className="bg-gray-100 px-1 rounded">X-Queryon-Signature: sha256=…</code>
              {" "}· Inbound doğrulama header: <code className="bg-gray-100 px-1 rounded">X-Webhook-Secret: &lt;secret&gt;</code>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

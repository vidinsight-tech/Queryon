#!/usr/bin/env python3
"""Seed Turkish beauty studio chatbot — character mode with appointment booking.

Deletes all existing kuafor_* rules, re-seeds FAQ standalone rules,
writes the character system prompt and appointment_fields config into
OrchestratorConfigModel so the orchestrator handles natural conversation
and can create appointment records.

Run:
    python -m backend.scripts.seed_hairdresser
"""
from __future__ import annotations

import asyncio
import logging
import os

import backend.orchestrator.rules.models  # noqa: F401

from sqlalchemy import delete, select

from backend.infra.database.engine import (
    build_engine,
    build_session_factory,
    ensure_database_exists,
    init_db,
)
from backend.infra.database.models.tool_config import OrchestratorConfigModel
from backend.orchestrator.rules.models import OrchestratorRule
from backend.orchestrator.rules.repository import RuleRepository
from backend.orchestrator.types import OrchestratorConfig

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# ── Appointment fields ─────────────────────────────────────────────────────────
# Conversation flow order:
#   1. event_type  →  2. event_date  →  3. location  →  4. artist
#   →  5. extra_people  →  6. name  →  7. phone  →  8. notes

APPOINTMENT_FIELDS = [
    {
        "key": "event_type",
        "label": "Hazırlık Türü",
        "question": "Hangi hazırlık türünde hizmet almak istersiniz?",
        "required": True,
        "options": [
            "Düğün",
            "Nişan",
            "Kına",
            "Söz / İsteme",
            "Davetli / Nedime",
            "Profesyonel Makyaj",
        ],
    },
    {
        "key": "event_date",
        "label": "Hazırlık Tarihi",
        "question": "Hazırlık tarihiniz nedir?",
        "required": True,
    },
    {
        "key": "event_time",
        "label": "Hazırlık Saati",
        "question": "Hazırlığın kaçta başlamasını istersiniz? (Örn: 09:00, sabah 10 gibi belirtebilirsiniz.)",
        "required": True,
        "validation": "time",
    },
    {
        "key": "location",
        "label": "Lokasyon",
        "question": "Hazırlık lokasyonunuz neresi olsun?",
        "required": True,
        "options": ["Stüdyo", "Otel / Ev", "Şehir Dışı"],
    },
    # ── Stüdyo seçildiyse: hangi şube? ──────────────────────────────────────
    {
        "key": "studio_branch",
        "label": "Stüdyo Şubesi",
        "question": "Hangi stüdyomuzda hazırlanmak istersiniz?",
        "required": True,
        "options": ["Antep Stüdyosu", "İstanbul Stüdyosu"],
        "show_if": {"field": "location", "value": ["Stüdyo"]},
    },
    # ── Şehir dışı seçildiyse: şehir + adres ────────────────────────────────
    {
        "key": "city",
        "label": "Şehir",
        "question": "Organizasyon hangi şehirde gerçekleşecek?",
        "required": True,
        "show_if": {"field": "location", "value": ["Şehir Dışı"]},
    },
    {
        "key": "address",
        "label": "Mekan / Adres",
        "question": "Hazırlık yapılacak mekanın adresini veya adını paylaşır mısınız?",
        "required": True,
        "show_if": {"field": "location", "value": ["Şehir Dışı"]},
    },
    {
        "key": "artist",
        "label": "Makeup Artist",
        "question": "Hangi makeup artist ile çalışmak istersiniz?",
        "required": True,
        "options": ["İzel", "Merve", "Dicle", "İrem", "Gizem", "Neslihan", "Standart Ekip"],
    },
    {
        "key": "extra_people",
        "label": "Toplam Kişi Sayısı",
        "question": "Hazırlanacak toplam kişi sayısı kaç? (Sadece siz iseniz 1, yanınızda biri varsa 2 gibi yazabilirsiniz.)",
        "required": False,
        "validation": "number",
    },
    {
        "key": "name",
        "label": "İletişim Kişisi",
        "question": "İletişim kişisinin adı soyadı ve telefon numarasını paylaşır mısınız? (Örn: Ayşe Kaya — 0532 XXX XX XX)",
        "required": True,
    },
    {
        "key": "phone",
        "label": "Telefon",
        "question": "İletişim numaranız nedir?",
        "required": True,
        "validation": "phone",
    },
    {
        "key": "notes",
        "label": "Not / Özel İstek",
        "question": "Eklemek istediğiniz bir not veya özel isteğiniz var mı?",
        "required": False,
    },
]

# ── Full character system prompt ───────────────────────────────────────────────

CHARACTER_SYSTEM_PROMPT = """\
Sen Queryon Güzellik Stüdyosu'nun sanal asistanısın.
Türkçe konuşuyorsun. Sıcak, profesyonel ve kısa yanıtlar veriyorsun.
Sadece stüdyo konularında yardımcı olursun; konu dışı sorularda kibarca yönlendirirsin.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STÜDYO BİLGİLERİ
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
İsim     : Queryon Güzellik Stüdyosu
Adres    : Çankaya Mah. Güzellik Sok. No:15, Şişli / İstanbul
Telefon  : 0212 XXX XX XX
WhatsApp : 0532 XXX XX XX
Instagram: @queryon_guzellik (DM açık)
Saatler  : Pazartesi–Cumartesi 09:00–20:00 | Pazar Kapalı

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HİZMETLER VE PAKET İÇERİĞİ
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Seçenekler: Düğün · Nişan · Kına · Söz/İsteme · Davetli/Nedime · Profesyonel Makyaj

Tüm düğün/nişan/kına paketlerine dahil:
  • Saç yıkama + bakım
  • Saç tasarımı
  • Profesyonel makyaj
  • Kirpik uygulaması

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FİYAT TABLOSU (STÜDYO BAZFIYATLARI)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Artist       | Seviye   | Düğün   | Nişan   | Kına    | Söz     | Davetli | Prof.Makyaj
-------------|----------|---------|---------|---------|---------|---------|------------
İzel         | Kıdemli  | 20.000₺ | 15.000₺ | 12.000₺ | 10.000₺ |  5.000₺ |  3.000₺
Merve        | Kıdemli  | 18.000₺ | 12.000₺ | 10.000₺ |  8.000₺ |  4.000₺ |  2.500₺
Dicle        | Kıdemli  | 22.000₺ | 16.000₺ | 13.000₺ | 11.000₺ |  5.500₺ |  3.500₺
İrem         | Orta     | 15.000₺ | 10.000₺ |  9.000₺ |  7.000₺ |  3.500₺ |  2.000₺
Gizem        | Orta     | 15.000₺ | 10.000₺ |  9.000₺ |  7.000₺ |  3.500₺ |  2.000₺
Neslihan     | Orta     | 15.000₺ | 10.000₺ |  9.000₺ |  7.000₺ |  3.500₺ |  2.000₺
Standart Ekip| Standart | 10.000₺ |  5.000₺ |  5.000₺ |  4.000₺ |  2.500₺ |  1.500₺

Not: Kıdemli artistler (İzel, Merve, Dicle) yalnızca etkinlik bazlı çalışır;
     Profesyonel Makyaj da sunsalar günlük makyaj için ayrı randevu almaz.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
LOKASYON ZAMMI
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Stüdyo     → tablo fiyatı (ek ücret yok)
  Otel / Ev  → tablo fiyatı + 2.000₺ ulaşım
  Şehir Dışı → tablo fiyatı × 2  (konaklama + ulaşım organizatörce karşılanır)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EK KİŞİ (NEDİME / ARKADAŞ) ZAMMI
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Stüdyo     → kişi başı 5.000₺
  Otel / Ev  → kişi başı 6.000₺
  Şehir Dışı → kişi başı 7.000₺

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TOPLAM FİYAT HESAPLAMA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️  ÖNEMLİ: Randevu akışı sırasında fiyatlar sistem tarafından Python koduyla
hesaplanır ve sana "HESAPLANAN FİYATLAR" bloğu olarak verilir.
Bu bloktaki sayıları olduğu gibi kullan — kendin hesaplama yapma.

Bloğun olmadığı durumlarda (genel fiyat soruları için) aşağıdaki formülü kullan:
Adım 1 — Artist baz fiyatını tablodan al (hizmet türü × artist)
Adım 2 — Lokasyon zammını uygula:
    if lokasyon == "Otel / Ev"  → baz fiyat + 2.000₺
    if lokasyon == "Şehir Dışı" → baz fiyat × 2
    if lokasyon == "Stüdyo"     → baz fiyat (değişmez)
Adım 3 — Ek kişi ücretini ekle:
    ek_kişi = toplam_kişi - 1  (müşterinin kendisi 1 kişi sayılır)
    if ek_kişi > 0 → toplam += ek_kişi × ek_kişi_fiyatı(lokasyon)

Örnekler:
  • İrem + Nişan + Stüdyo + 1 kişi  = 10.000₺  (ek kişi yok)
  • İrem + Nişan + Stüdyo + 3 kişi  = 10.000 + 2×5.000 = 20.000₺
  • İzel + Düğün + Otel   + 1 kişi  = 20.000 + 2.000   = 22.000₺
  • İzel + Düğün + Şehir Dışı + 1 kişi = 20.000×2       = 40.000₺
  • İzel + Düğün + Şehir Dışı + 2 kişi = 40.000 + 7.000 = 47.000₺

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RANDEVU ALMA AKIŞI  (sırayla sor, her adımı bekle)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ADIM 1 — Hazırlık türü
    Seçenekler: Düğün / Nişan / Kına / Söz-İsteme / Davetli-Nedime / Profesyonel Makyaj

ADIM 2 — Hazırlık tarihi

ADIM 3 — Hazırlık saati
    "Hazırlığın kaçta başlamasını istersiniz?"
    Kullanıcı "akşam 6", "saat 9", "10:30" gibi ifadeler kullanabilir; bunları HH:MM formatına çevir.

ADIM 4 — Lokasyon
    Seçenekler: Stüdyo / Otel-Ev / Şehir Dışı

ADIM 5 — Lokasyona bağlı ek sorular:
    if lokasyon == "Stüdyo":
        → "Hangi şubemizde hazırlanmak istersiniz? Antep Stüdyosu mu, İstanbul Stüdyosu mu?"
    if lokasyon == "Şehir Dışı":
        → "Organizasyon hangi şehirde?" diye sor, cevabı al
        → ardından "Hazırlık yapılacak mekan veya adres nedir?" diye sor
    if lokasyon == "Otel / Ev":
        → ek soru yok, doğrudan ADIM 6'ya geç

ADIM 6 — Makeup artist seçimi
    Sistem sana "HESAPLANAN FİYATLAR" bloğu gönderir — o bloktaki artist fiyat
    listesini olduğu gibi kullan (yeniden hesaplama yapma).
    Her artist için tek satırda fiyatıyla birlikte listele.
    Örnek: "İzel — 22.000₺  |  Merve — 20.000₺  |  ..."

ADIM 7 — Toplam kişi sayısı (müşteri dahil)
    "Hazırlanacak toplam kişi sayısı kaç? (Sadece siz ise 1, yanınızda biri varsa 2 yazabilirsiniz.)"
    Kabul edilen ifadeler:
        "tek" / "bir" / "yalnız" → 1
        "iki" / "çift"           → 2
        "üç"                     → 3   (vb.)

ADIM 8 — Toplam fiyatı göster
    Sistem "HESAPLANAN FİYATLAR" bloğundaki TOPLAM değerini olduğu gibi kullan.
    Kendin hesaplama yapma — bloktaki rakamı yaz.

ADIM 9 — İletişim bilgileri (tek mesajda sor)
    "İletişim kişisinin adı soyadı ve telefon numarasını paylaşır mısınız?
     Örnek: Ayşe Kaya — 0532 XXX XX XX"

ADIM 10 — Notlar (isteğe bağlı)
    "Eklemek istediğiniz özel bir istek veya notunuz var mı?
     Yoksa 'geç' yazabilirsiniz."

ADIM 11 — Onay özeti sun (aşağıdaki formata bak), onay iste

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ONAY ÖZETİ FORMATI
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tüm bilgiler toplandığında kullanıcıya şu formatı kullan:

📋 Randevu Özetiniz:
  • Hazırlık Türü  : [tür]
  • Tarih          : [tarih]
  • Saat           : [saat]
  • Lokasyon       : [lokasyon]
        if lokasyon == "Stüdyo"     → • Şube : [Antep Stüdyosu veya İstanbul Stüdyosu]
        if lokasyon == "Şehir Dışı" → • Şehir : [şehir]
                                      • Mekan : [adres]
  • Makeup Artist  : [artist]
  • Toplam Kişi    : [sayı]
  • İletişim Kişisi: [ad soyad]
  • Telefon        : [telefon]
        if notlar var               → • Not : [not]
  • Toplam Fiyat   : [hesaplanan fiyat]₺

Bilgiler doğru mu? Onaylamak için "evet" veya "tamam" yazın.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ONAY SONRASI MESAJ
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Kullanıcı onayladıktan sonra tam olarak şu şablonu kullan:

"✅ Randevunuz başarıyla oluşturuldu!
[tarih] tarihinde [şube/lokasyon adı] adresimizde sizi ağırlamaktan mutluluk duyacağız.
Herhangi bir sorunuz veya değişiklik talebiniz için 0212 XXX XX XX numaralı hattımıza ulaşabilirsiniz.
Şimdiden güzel hazırlıklar dileriz! 🌸"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GENEL KURALLAR
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Fiyat sorulduğunda kesin fiyat ver; "değişebilir" deme — tabloyu kullan.
- Aynı bilgiyi tekrar sorma; konuşma geçmişini takip et.
- Kısa ve net yanıtlar ver.
- "kimsin" / "bot musun" → kendini tanıt.
- Konu dışı sorularda kibarca yönlendir.
- Grup randevuları (3+ kişi) için en az 1 hafta önceden rezervasyon gerektiğini belirt.
"""

# ── FAQ standalone rules ───────────────────────────────────────────────────────

FAQ_RULES = [
    {
        "name": "kuafor_adres",
        "description": "Stüdyo adresi ve ulaşım bilgisi",
        "trigger_patterns": [
            "adres", "nerede", "konum", "stüdyo nerede", "nasıl gidebilirim",
            "yol tarifi",
        ],
        "response_template": (
            "📍 Adresimiz\n\n"
            "Çankaya Mah. Güzellik Sok. No:15\n"
            "Şişli / İstanbul\n\n"
            "🚇 Metro: Şişli-Mecidiyeköy (5 dk yürüyüş)\n"
            "🚌 Otobüs: 25E, 559C\n\n"
            "📞 Yol tarifi için: 0212 XXX XX XX"
        ),
        "variables": {},
        "priority": 9,
    },
    {
        "name": "kuafor_calisma_saatleri",
        "description": "Çalışma saatleri — stüdyo mesai bilgisi",
        "trigger_patterns": [
            "açık mı", "mesai", "çalışma saati", "çalışma saatleri",
            "ne zaman açık", "kaçta kapanıyor", "kaçta açılıyor",
            "çalışıyor musunuz", "kaça kadar açık",
        ],
        "response_template": (
            "⏰ Çalışma Saatlerimiz\n\n"
            "Pazartesi – Cumartesi: 09:00 – 20:00\n"
            "Pazar: Kapalı\n\n"
            "📸 Özel günler için: @queryon_guzellik"
        ),
        "variables": {},
        "priority": 9,
    },
    {
        "name": "kuafor_paket_icerik",
        "description": "Paket içeriği — düğün/nişan/kına paketlerine dahil hizmetler",
        "trigger_patterns": [
            "ne dahil", "içeriği", "kapsıyor", "pakette ne var",
            "dahil mi", "paket içerik",
        ],
        "response_template": (
            "✅ Düğün / Nişan / Kına Paketlerine Dahil\n\n"
            "• Saç yıkama + bakım maskesi\n"
            "• Saç tasarımı (gelin saçı, yarım topuz vb.)\n"
            "• Profesyonel makyaj\n"
            "• Kirpik uygulaması\n"
            "• Rötuş seti (etkinlik günü)\n\n"
            "❌ Dahil Olmayan\n"
            "• Saç boyama (ayrıca fiyatlandırılır)\n"
            "• Ek nedime hizmetleri (ayrı ücretlendirilir)"
        ),
        "variables": {},
        "priority": 7,
    },
    {
        "name": "kuafor_nedime_fiyat",
        "description": "Nedime ve ek kişi fiyat bilgisi",
        "trigger_patterns": [
            "nedime", "nedime fiyat", "nedime paketi",
            "gelin arkadaşı", "arkadaş grubu", "grup fiyatı",
        ],
        "response_template": (
            "👯‍♀️ Ek Kişi (Nedime / Arkadaş) Fiyatları\n\n"
            "Stüdyo: kişi başı 5.000₺\n"
            "Otel / Ev: kişi başı 6.000₺\n"
            "Şehir Dışı: kişi başı 7.000₺\n\n"
            "⚠️ 3+ kişilik grup randevularında 1 hafta önceden rezervasyon gerekir.\n"
            "📞 Detay: 0212 XXX XX XX"
        ),
        "variables": {},
        "priority": 8,
    },
    {
        "name": "kuafor_fiyat_genel",
        "description": "Genel fiyat bilgisi ve fiyat tablosu",
        "trigger_patterns": [
            "fiyat listesi", "fiyat tablosu", "tarife",
            "fiyatlar nedir", "fiyatlarınız", "ücretler",
        ],
        "response_template": (
            "💰 Stüdyo Fiyatlarımız (başlangıç)\n\n"
            "| Hizmet | Başlangıç Fiyat |\n"
            "|--------|-----------------|\n"
            "| Düğün | 10.000₺ – 22.000₺ |\n"
            "| Nişan | 5.000₺ – 16.000₺ |\n"
            "| Kına | 5.000₺ – 13.000₺ |\n"
            "| Söz / İsteme | 4.000₺ – 11.000₺ |\n"
            "| Davetli | 2.500₺ – 5.500₺ |\n"
            "| Profesyonel Makyaj | 1.500₺ – 3.500₺ |\n\n"
            "💡 Fiyat, seçtiğiniz makeup artist ve lokasyona göre değişir.\n"
            "Detaylı fiyat almak için hazırlık türünüzü söyleyin!"
        ),
        "variables": {},
        "priority": 8,
    },
    {
        "name": "kuafor_iletisim",
        "description": "İletişim bilgileri",
        "trigger_patterns": [
            "iletişim", "telefon", "whatsapp", "instagram", "sosyal medya",
            "nasıl ulaşırım", "numara",
        ],
        "response_template": (
            "📞 İletişim Bilgilerimiz\n\n"
            "📱 Telefon: 0212 XXX XX XX\n"
            "💬 WhatsApp: 0532 XXX XX XX\n"
            "📸 Instagram: @queryon_guzellik (DM açık)\n\n"
            "Size en kısa sürede dönüş yapacağız!"
        ),
        "variables": {},
        "priority": 9,
    },
    {
        "name": "kuafor_artistler",
        "description": "Makeup artist kadrosu hakkında bilgi",
        "trigger_patterns": [
            "artistler", "sanatçılar", "kimler var", "kadro",
            "makeup artist kimler", "makyöz kadro", "ekibiniz",
        ],
        "response_template": (
            "👩‍🎨 Makeup Artist Kadromuz\n\n"
            "🌟 Kıdemli Artistler:\n"
            "• İzel — Premium, uzman gelin makyajı\n"
            "• Merve — Kıdemli, doğal ve elegant stiller\n"
            "• Dicle — Kıdemli, trend ve cesur tasarımlar\n\n"
            "💫 Orta Seviye Artistler:\n"
            "• İrem — Doğal ve modern stiller\n"
            "• Gizem — Klasik ve soft makyaj\n"
            "• Neslihan — Çok yönlü tasarımlar\n\n"
            "📋 Standart Ekip — Uygun fiyatlı profesyonel hizmet\n\n"
            "Detaylı fiyat için hazırlık türünüzü ve lokasyonunuzu söyleyin!"
        ),
        "variables": {},
        "priority": 7,
    },
]

# ── Restrictions ───────────────────────────────────────────────────────────────

RESTRICTIONS = """\
- Rakip güzellik salonları hakkında yorum yapma veya karşılaştırma yapma
- Fiyat indirimi veya pazarlık teklifi yapma
- Siyasi, dini veya kişisel tartışmalara girme
- Tıbbi tavsiye verme (saç/cilt problemleri için doktora yönlendir)
- Fiyat tablonuzda olmayan hizmetlere fiyat uydurmayın — "Bu hizmetimiz hakkında bilgi almak için bizi arayın" de
"""


async def seed() -> None:
    db_url = os.environ.get("DATABASE_URL", "postgresql://localhost:5432/queryon")
    os.environ.setdefault("DATABASE_URL", db_url)

    await ensure_database_exists()
    engine = build_engine()
    session_factory = build_session_factory(engine)
    await init_db()

    async with session_factory() as session:
        # ── Delete all existing kuafor_* rules ───────────────────────────────
        result = await session.execute(
            delete(OrchestratorRule).where(OrchestratorRule.name.like("kuafor_%"))
        )
        deleted = result.rowcount
        if deleted:
            logger.info("Deleted %d existing kuafor_* rules.", deleted)

        # ── Insert FAQ standalone rules ──────────────────────────────────────
        repo = RuleRepository(session)
        for rule_data in FAQ_RULES:
            await repo.create_rule(**rule_data)
            logger.info("  + FAQ rule: %s", rule_data["name"])

        # ── Upsert OrchestratorConfig ────────────────────────────────────────
        row = await session.scalar(
            select(OrchestratorConfigModel).where(OrchestratorConfigModel.id == 1)
        )
        if row is None:
            cfg = OrchestratorConfig()
            cfg.character_system_prompt = CHARACTER_SYSTEM_PROMPT
            cfg.appointment_fields = APPOINTMENT_FIELDS
            cfg.restrictions = RESTRICTIONS
            cfg.bot_name = "Bella"
            session.add(OrchestratorConfigModel(id=1, config_json=cfg.to_dict()))
            logger.info("Created OrchestratorConfigModel.")
        else:
            existing = OrchestratorConfig.from_dict(row.config_json or {})
            existing.character_system_prompt = CHARACTER_SYSTEM_PROMPT
            existing.appointment_fields = APPOINTMENT_FIELDS
            existing.restrictions = RESTRICTIONS
            existing.bot_name = "Bella"
            row.config_json = existing.to_dict()
            logger.info("Updated OrchestratorConfigModel.")

        await session.commit()

    logger.info(
        "Hairdresser seed complete: %d FAQ rules + character prompt + %d appointment fields.",
        len(FAQ_RULES),
        len(APPOINTMENT_FIELDS),
    )


if __name__ == "__main__":
    asyncio.run(seed())

-- Seed data: İzellik Makeup House hizmet akışı kuralları
-- Bu dosya örnek bir multi-step flow kural seti oluşturur.

-- ═══════════════════════════════════════════════════════
-- AKIŞ KURALLARI (flow_id = 'hizmet_akisi')
-- ═══════════════════════════════════════════════════════

-- Adım 1: Karşılama + Hizmet Listesi (giriş noktası)
INSERT INTO orchestrator_rules
    (id, name, description, trigger_patterns, response_template, variables, priority, is_active,
     flow_id, step_key, required_step, next_steps)
VALUES (
    gen_random_uuid(),
    'Karşılama',
    'Müşteri ilk mesaj yazdığında hizmet listesini göster',
    ARRAY['merhaba', 'selam', 'bilgi', 'fiyat', 'makyaj', 'randevu', 'merhabalar', 'iyi günler'],
    E'İzellik Makeup House Gaziantep şubesi ile iletişime geçtiğiniz için teşekkür ediyoruz. 😊\n\nTalebinizin daha hızlı karşılanabilmesi için hizmet kategorilerimizden seçim yapmanızı rica ediyoruz:\n\n1) Düğün Saç Makyaj\n2) Kına Saç Makyaj\n3) Nişan Saç Makyaj\n4) Düğün Türban Tasarım Makyaj\n5) Kına Türban Tasarım Makyaj\n6) Nişan Türban Tasarım Makyaj\n7) Profesyonel Saç Makyaj\n8) Profesyonel Makyaj',
    '{}',
    100, true,
    'hizmet_akisi', 'start', NULL,
    '{"düğün": "tarih_sor_dugun", "1": "tarih_sor_dugun", "gelin": "tarih_sor_dugun",
      "kına": "tarih_sor_kina", "2": "tarih_sor_kina",
      "nişan": "tarih_sor_nisan", "3": "tarih_sor_nisan",
      "türban": "turban_tipi_sor",
      "profesyonel": "fiyat_profesyonel", "7": "fiyat_profesyonel", "8": "fiyat_profesyonel"}'::jsonb
);

-- Adım 2a: Düğün seçildi → Tarih sor
INSERT INTO orchestrator_rules
    (id, name, description, trigger_patterns, response_template, variables, priority, is_active,
     flow_id, step_key, required_step, next_steps)
VALUES (
    gen_random_uuid(),
    'Tarih Sor - Düğün',
    'Düğün hizmeti seçildiğinde tarih sor',
    ARRAY['düğün', 'gelin', '1'],
    'Düğün tarihiniz nedir?',
    '{}',
    90, true,
    'hizmet_akisi', 'tarih_sor_dugun', 'start',
    '{"*": "fiyat_dugun"}'::jsonb
);

-- Adım 2b: Kına seçildi → Tarih sor
INSERT INTO orchestrator_rules
    (id, name, description, trigger_patterns, response_template, variables, priority, is_active,
     flow_id, step_key, required_step, next_steps)
VALUES (
    gen_random_uuid(),
    'Tarih Sor - Kına',
    'Kına hizmeti seçildiğinde tarih ve düğün birleşimi sor',
    ARRAY['kına', '2'],
    E'Kına tarihiniz nedir?\nDüğün ile birlikte mi olacak?',
    '{}',
    90, true,
    'hizmet_akisi', 'tarih_sor_kina', 'start',
    '{"evet": "fiyat_kina_dugun", "birlikte": "fiyat_kina_dugun", "hayır": "fiyat_kina", "*": "fiyat_kina"}'::jsonb
);

-- Adım 2c: Nişan seçildi → Tarih sor
INSERT INTO orchestrator_rules
    (id, name, description, trigger_patterns, response_template, variables, priority, is_active,
     flow_id, step_key, required_step, next_steps)
VALUES (
    gen_random_uuid(),
    'Tarih Sor - Nişan',
    'Nişan hizmeti seçildiğinde tarih sor',
    ARRAY['nişan', '3'],
    'Nişan tarihiniz nedir?',
    '{}',
    90, true,
    'hizmet_akisi', 'tarih_sor_nisan', 'start',
    '{"*": "fiyat_nisan"}'::jsonb
);

-- Adım 3a: Düğün fiyat listesi
INSERT INTO orchestrator_rules
    (id, name, description, trigger_patterns, response_template, variables, priority, is_active,
     flow_id, step_key, required_step, next_steps)
VALUES (
    gen_random_uuid(),
    'Fiyat - Düğün',
    'Düğün saç makyaj fiyat listesi',
    ARRAY['*'],
    E'Stüdyomuzda size eşlik edecek makeup artist takım arkadaşlarımızın fiyatlarını paylaşıyorum.\n\nSaç veya türban hizmeti bu fiyata dahildir.\n\n✨ İzel (izellikmua): 20.000 ₺\n✨ Merve (merveeorta): 13.000 ₺\n✨ Dicle (diclebayysal): 13.000 ₺\n✨ İrem (iremmuua): 11.000 ₺\n\nHangi makeup artist ile devam etmek istersiniz?',
    '{}',
    80, true,
    'hizmet_akisi', 'fiyat_dugun', 'tarih_sor_dugun',
    '{"*": "randevu_olustur"}'::jsonb
);

-- Adım 3b: Nişan fiyat listesi
INSERT INTO orchestrator_rules
    (id, name, description, trigger_patterns, response_template, variables, priority, is_active,
     flow_id, step_key, required_step, next_steps)
VALUES (
    gen_random_uuid(),
    'Fiyat - Nişan',
    'Nişan saç makyaj fiyat listesi',
    ARRAY['*'],
    E'Nişan hazırlığınızda size eşlik edecek makeup artist takım arkadaşlarımızın fiyatlarını paylaşıyorum.\n\nSaç veya türban hizmeti bu fiyata dahildir.\n\n✨ İzel (izellikmua): 15.000 ₺\n✨ Merve (merveeorta): 10.000 ₺\n✨ Dicle (diclebayysal): 10.000 ₺\n✨ İrem (iremmuua): 9.000 ₺\n\nHangi makeup artist ile devam etmek istersiniz?',
    '{}',
    80, true,
    'hizmet_akisi', 'fiyat_nisan', 'tarih_sor_nisan',
    '{"*": "randevu_olustur"}'::jsonb
);

-- Adım 3c: Kına tek gün fiyat listesi
INSERT INTO orchestrator_rules
    (id, name, description, trigger_patterns, response_template, variables, priority, is_active,
     flow_id, step_key, required_step, next_steps)
VALUES (
    gen_random_uuid(),
    'Fiyat - Kına',
    'Kına tek gün saç makyaj fiyat listesi',
    ARRAY['*'],
    E'Kına hazırlığınızda size eşlik edecek makeup artist takım arkadaşlarımızın fiyatlarını paylaşıyorum.\n\nSaç veya türban hizmeti bu fiyata dahildir.\n\n✨ İzel (izellikmua): 20.000 ₺\n✨ Merve (merveeorta): 13.000 ₺\n✨ Dicle (diclebayysal): 13.000 ₺\n✨ İrem (iremmuua): 11.000 ₺\n\nHangi makeup artist ile devam etmek istersiniz?',
    '{}',
    80, true,
    'hizmet_akisi', 'fiyat_kina', 'tarih_sor_kina',
    '{"*": "randevu_olustur"}'::jsonb
);

-- Adım 3d: Kına+Düğün combo fiyat listesi
INSERT INTO orchestrator_rules
    (id, name, description, trigger_patterns, response_template, variables, priority, is_active,
     flow_id, step_key, required_step, next_steps)
VALUES (
    gen_random_uuid(),
    'Fiyat - Kına+Düğün',
    'Kına ve düğün iki gün combo fiyat listesi',
    ARRAY['*'],
    E'Kına+Düğün iki gün stüdyo hazırlığınızda size eşlik edecek makeup artist takım arkadaşlarımızın fiyatlarını paylaşıyorum.\n\nKına ve düğün için makyaj, saç veya türban hizmeti bu fiyata dahildir.\n\n✨ İzel (izellikmua): 40.000 ₺\n✨ Merve (merveeorta): 22.000 ₺\n✨ Dicle (diclebayysal): 22.000 ₺\n\nHangi makeup artist ile devam etmek istersiniz?',
    '{}',
    80, true,
    'hizmet_akisi', 'fiyat_kina_dugun', 'tarih_sor_kina',
    '{"*": "randevu_olustur"}'::jsonb
);

-- Adım 4: Randevu oluştur (terminal adım)
INSERT INTO orchestrator_rules
    (id, name, description, trigger_patterns, response_template, variables, priority, is_active,
     flow_id, step_key, required_step, next_steps)
VALUES (
    gen_random_uuid(),
    'Randevu Oluştur',
    'Makeup artist seçimi sonrası randevu bilgisi',
    ARRAY['*'],
    E'Teşekkür ederiz! Randevu talebiniz alınmıştır. ✅\n\nHazır olmanız gereken saatten yaklaşık 2-3 saat önce stüdyomuza gelmenizi rica ediyoruz.\nKesin saat ve detaylar tarafınıza ayrıca iletilecektir.\n\nBaşka bir sorunuz var mı?',
    '{}',
    70, true,
    'hizmet_akisi', 'randevu_olustur', 'fiyat_dugun',
    NULL
);

-- Randevu oluştur (nişan fiyat üzerinden de gelebilir)
INSERT INTO orchestrator_rules
    (id, name, description, trigger_patterns, response_template, variables, priority, is_active,
     flow_id, step_key, required_step, next_steps)
VALUES (
    gen_random_uuid(),
    'Randevu Oluştur - Nişan',
    'Nişan fiyat sonrası randevu',
    ARRAY['*'],
    E'Teşekkür ederiz! Randevu talebiniz alınmıştır. ✅\n\nKesin saat ve detaylar tarafınıza ayrıca iletilecektir.\nBaşka bir sorunuz var mı?',
    '{}',
    70, true,
    'hizmet_akisi', 'randevu_olustur', 'fiyat_nisan',
    NULL
);

-- Randevu oluştur (kına fiyat üzerinden)
INSERT INTO orchestrator_rules
    (id, name, description, trigger_patterns, response_template, variables, priority, is_active,
     flow_id, step_key, required_step, next_steps)
VALUES (
    gen_random_uuid(),
    'Randevu Oluştur - Kına',
    'Kına fiyat sonrası randevu',
    ARRAY['*'],
    E'Teşekkür ederiz! Randevu talebiniz alınmıştır. ✅\n\nKesin saat ve detaylar tarafınıza ayrıca iletilecektir.\nBaşka bir sorunuz var mı?',
    '{}',
    70, true,
    'hizmet_akisi', 'randevu_olustur', 'fiyat_kina',
    NULL
);

-- Randevu oluştur (kına+düğün combo üzerinden)
INSERT INTO orchestrator_rules
    (id, name, description, trigger_patterns, response_template, variables, priority, is_active,
     flow_id, step_key, required_step, next_steps)
VALUES (
    gen_random_uuid(),
    'Randevu Oluştur - Kına+Düğün',
    'Kına+Düğün combo fiyat sonrası randevu',
    ARRAY['*'],
    E'Teşekkür ederiz! Randevu talebiniz alınmıştır. ✅\n\nKesin saat ve detaylar tarafınıza ayrıca iletilecektir.\nBaşka bir sorunuz var mı?',
    '{}',
    70, true,
    'hizmet_akisi', 'randevu_olustur', 'fiyat_kina_dugun',
    NULL
);

-- Profesyonel fiyat (terminal)
INSERT INTO orchestrator_rules
    (id, name, description, trigger_patterns, response_template, variables, priority, is_active,
     flow_id, step_key, required_step, next_steps)
VALUES (
    gen_random_uuid(),
    'Fiyat - Profesyonel',
    'Profesyonel makyaj fiyat bilgisi',
    ARRAY['profesyonel', '7', '8'],
    E'Tek gün için tek kişi profesyonel saç makyaj tasarım kirpik dahil fiyatımız 5.000 TL''dir.\n\nRandevu oluşturmak ister misiniz?',
    '{}',
    80, true,
    'hizmet_akisi', 'fiyat_profesyonel', 'start',
    NULL
);


-- ═══════════════════════════════════════════════════════
-- BAĞIMSIZ KURALLAR (flow dışı, her zaman geçerli)
-- ═══════════════════════════════════════════════════════

-- Nedime / Ek kişi fiyatı
INSERT INTO orchestrator_rules
    (id, name, description, trigger_patterns, response_template, variables, priority, is_active,
     flow_id, step_key, required_step, next_steps)
VALUES (
    gen_random_uuid(),
    'Nedime Fiyat',
    'Nedime veya ek kişi fiyat sorusu',
    ARRAY['nedime', 'yanımdaki', 'ek kişi', 'arkadaş', 'refakatçi', 'yanımda'],
    E'Tek gün için tek kişi profesyonel saç makyaj tasarım kirpik dahil fiyatımız 5.000 TL''dir.',
    '{}',
    50, true,
    NULL, NULL, NULL, NULL
);

-- İstanbul şubesi yönlendirme
INSERT INTO orchestrator_rules
    (id, name, description, trigger_patterns, response_template, variables, priority, is_active,
     flow_id, step_key, required_step, next_steps)
VALUES (
    gen_random_uuid(),
    'İstanbul Yönlendirme',
    'İstanbul şubesi hakkında soru',
    ARRAY['istanbul', 'ist şube'],
    E'İstanbul şubemiz için 0540 272 3434 nolu telefondan detaylı bilgi alabilirsiniz.',
    '{}',
    50, true,
    NULL, NULL, NULL, NULL
);

-- Randevu saati bilgisi
INSERT INTO orchestrator_rules
    (id, name, description, trigger_patterns, response_template, variables, priority, is_active,
     flow_id, step_key, required_step, next_steps)
VALUES (
    gen_random_uuid(),
    'Randevu Saati',
    'Kaçta gelinmeli sorusu',
    ARRAY['kaçta geleyim', 'saat kaç', 'ne zaman gelmeli', 'kaçta gelmeli'],
    E'Hazır olmanız gereken saatten yaklaşık 2-3 saat önce gelmenizi öneriyoruz.\nKesin saati randevu oluştururken netleştireceğiz.',
    '{}',
    50, true,
    NULL, NULL, NULL, NULL
);

-- Adres bilgisi
INSERT INTO orchestrator_rules
    (id, name, description, trigger_patterns, response_template, variables, priority, is_active,
     flow_id, step_key, required_step, next_steps)
VALUES (
    gen_random_uuid(),
    'Adres Bilgisi',
    'Stüdyo adresi sorusu',
    ARRAY['adres', 'nerede', 'konum', 'harita'],
    E'Stüdyomuz Gaziantep''te bulunmaktadır. Detaylı konum bilgisi için Instagram sayfamızı ziyaret edebilirsiniz.',
    '{}',
    50, true,
    NULL, NULL, NULL, NULL
);

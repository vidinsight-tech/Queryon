"""Mode engine: pure functions for progressive question collection.

These functions are intentionally side-effect-free so they can be unit-tested
without any I/O.  The orchestrator calls ``compute_mode_context`` before each
character-mode turn to obtain a mode-context string that is appended to the
system prompt, guiding the LLM to ask exactly one question at a time.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

SKIP_SENTINEL = "__skip__"

# ── Price calculator ──────────────────────────────────────────────────────────
# All prices in TRY. Keyed by artist name → event type → base studio price.
# Kept in sync with the system prompt price table in seed_hairdresser.py.

_PRICE_TABLE: Dict[str, Dict[str, int]] = {
    "İzel":          {"Düğün": 20000, "Nişan": 15000, "Kına": 12000, "Söz / İsteme": 10000, "Davetli / Nedime": 5000, "Profesyonel Makyaj": 3000},
    "Merve":         {"Düğün": 18000, "Nişan": 12000, "Kına": 10000, "Söz / İsteme":  8000, "Davetli / Nedime": 4000, "Profesyonel Makyaj": 2500},
    "Dicle":         {"Düğün": 22000, "Nişan": 16000, "Kına": 13000, "Söz / İsteme": 11000, "Davetli / Nedime": 5500, "Profesyonel Makyaj": 3500},
    "İrem":          {"Düğün": 15000, "Nişan": 10000, "Kına":  9000, "Söz / İsteme":  7000, "Davetli / Nedime": 3500, "Profesyonel Makyaj": 2000},
    "Gizem":         {"Düğün": 15000, "Nişan": 10000, "Kına":  9000, "Söz / İsteme":  7000, "Davetli / Nedime": 3500, "Profesyonel Makyaj": 2000},
    "Neslihan":      {"Düğün": 15000, "Nişan": 10000, "Kına":  9000, "Söz / İsteme":  7000, "Davetli / Nedime": 3500, "Profesyonel Makyaj": 2000},
    "Standart Ekip": {"Düğün": 10000, "Nişan":  5000, "Kına":  5000, "Söz / İsteme":  4000, "Davetli / Nedime": 2500, "Profesyonel Makyaj": 1500},
}

# Extra-person surcharge per location (per additional person beyond the first)
_EXTRA_PERSON_RATES: Dict[str, int] = {
    "Stüdyo":    5000,
    "Otel / Ev": 6000,
    "Şehir Dışı": 7000,
}

# Canonical event-type names (what the LLM might say → what _PRICE_TABLE uses)
_EVENT_ALIASES: Dict[str, str] = {
    "söz": "Söz / İsteme",
    "söz / isteme": "Söz / İsteme",
    "söz/isteme": "Söz / İsteme",
    "isteme": "Söz / İsteme",
    "davetli": "Davetli / Nedime",
    "nedime": "Davetli / Nedime",
    "davetli / nedime": "Davetli / Nedime",
    "davetli/nedime": "Davetli / Nedime",
    "profesyonel makyaj": "Profesyonel Makyaj",
    "prof. makyaj": "Profesyonel Makyaj",
    "prof.makyaj": "Profesyonel Makyaj",
    "düğün": "Düğün",
    "nişan": "Nişan",
    "kına": "Kına",
}

# Canonical location names
_LOCATION_ALIASES: Dict[str, str] = {
    "stüdyo":    "Stüdyo",
    "otel":      "Otel / Ev",
    "otel / ev": "Otel / Ev",
    "otel/ev":   "Otel / Ev",
    "ev":        "Otel / Ev",
    "şehir dışı": "Şehir Dışı",
    "şehirdışı":  "Şehir Dışı",
}


def _norm_event(event_type: str) -> Optional[str]:
    """Return canonical event-type name or None if unrecognised."""
    key = (event_type or "").strip().lower()
    if key in _EVENT_ALIASES:
        return _EVENT_ALIASES[key]
    for canonical in _PRICE_TABLE:
        if canonical.lower() == key:
            return canonical
    return None


def _norm_location(location: str) -> Optional[str]:
    """Return canonical location name or None if unrecognised."""
    key = (location or "").strip().lower()
    if key in _LOCATION_ALIASES:
        return _LOCATION_ALIASES[key]
    for canonical in _EXTRA_PERSON_RATES:
        if canonical.lower() == key:
            return canonical
    return None


def _fmt_try(amount: int) -> str:
    """Format integer TRY amount with Turkish thousands separator: 22000 → '22.000'."""
    return f"{amount:,}".replace(",", ".")


def calculate_price(
    artist: str,
    event_type: str,
    location: str,
    total_people: int = 1,
) -> Optional[int]:
    """Return exact total price in TRY using the hardcoded price table.

    Returns None when any input is unrecognised (caller should fall back to
    leaving the LLM to handle it rather than showing a wrong number).
    """
    norm_ev = _norm_event(event_type)
    norm_loc = _norm_location(location)
    if not norm_ev or not norm_loc:
        return None

    # Find artist (case-insensitive)
    artist_prices: Optional[Dict[str, int]] = None
    artist_key = (artist or "").strip().lower()
    for name, prices in _PRICE_TABLE.items():
        if name.lower() == artist_key:
            artist_prices = prices
            break
    if artist_prices is None:
        return None

    base = artist_prices.get(norm_ev)
    if base is None:
        return None

    # Apply location surcharge
    if norm_loc == "Otel / Ev":
        price = base + 2000
    elif norm_loc == "Şehir Dışı":
        price = base * 2
    else:  # Stüdyo
        price = base

    # Add extra-person surcharge
    extra = max(0, total_people - 1)
    extra_rate = _EXTRA_PERSON_RATES.get(norm_loc, 5000)
    price += extra * extra_rate

    return price


def _build_computed_price_block(collected: Dict[str, Any]) -> Optional[str]:
    """Return a pre-computed price block for injection into the mode context.

    When the LLM sees this block it must use these numbers verbatim and must
    NOT attempt to recalculate prices itself.
    """
    event_type = (collected.get("event_type") or "").strip()
    location   = (collected.get("location")   or "").strip()
    artist     = (collected.get("artist")     or "").strip()

    if not event_type or not location:
        return None

    norm_loc = _norm_location(location)
    norm_ev  = _norm_event(event_type)
    if not norm_loc or not norm_ev:
        return None

    lines = [
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "HESAPLANAN FİYATLAR (Python motoru — LLM bu sayıları değiştirmez)",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]

    if artist and artist != SKIP_SENTINEL:
        # Single-artist price with optional extra-people
        extra_str = (collected.get("extra_people") or "1").strip()
        try:
            total_people = max(1, int(extra_str))
        except (ValueError, TypeError):
            total_people = 1

        price = calculate_price(artist, event_type, location, total_people)
        if price is None:
            return None  # unrecognised inputs — don't inject anything wrong

        extra = total_people - 1
        extra_rate = _EXTRA_PERSON_RATES.get(norm_loc, 5000)
        base_price = calculate_price(artist, event_type, location, 1) or 0

        lines.append(f"Artist : {artist}")
        lines.append(f"Hizmet : {norm_ev}  |  Lokasyon : {norm_loc}")
        if extra > 0:
            lines.append(f"Kişi   : {total_people} ({extra} ek kişi × {_fmt_try(extra_rate)}₺)")
            lines.append(f"Hesap  : {_fmt_try(base_price)}₺ + {extra} × {_fmt_try(extra_rate)}₺ = {_fmt_try(price)}₺")
        else:
            lines.append(f"Kişi   : 1")
            lines.append(f"Hesap  : {_fmt_try(price)}₺")
            lines.append(f"(Her ek kişi için +{_fmt_try(extra_rate)}₺)")
        lines.append(f"TOPLAM : {_fmt_try(price)}₺  ← Bu rakamı kullan, değiştirme")
    else:
        # No artist selected yet — list all artist prices for current event+location
        lines.append(f"Hizmet : {norm_ev}  |  Lokasyon : {norm_loc}")
        lines.append("Artist fiyatları (aşağıdaki tabloyu olduğu gibi kullan):")
        for a_name, prices in _PRICE_TABLE.items():
            base = prices.get(norm_ev)
            if base is None:
                continue
            if norm_loc == "Otel / Ev":
                p = base + 2000
            elif norm_loc == "Şehir Dışı":
                p = base * 2
            else:
                p = base
            lines.append(f"  • {a_name}: {_fmt_try(p)}₺")
        extra_rate = _EXTRA_PERSON_RATES.get(norm_loc, 5000)
        lines.append(f"(Her ek kişi için ayrıca +{_fmt_try(extra_rate)}₺)")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)


# Validation format hints shown inline in questions
_VALIDATION_HINTS: Dict[str, str] = {
    "phone": "(Format: 05XX XXX XX XX — sadece rakam)",
    "email": "(Geçerli bir e-posta adresi)",
    "date": "(Format: GG Ay YYYY, örn: 15 Mart 2026)",
    "time": "(Format: SS:DD, örn: 14:30 veya 09:00)",
    "number": "(Sadece sayısal değer)",
}


def field_is_visible(field: Dict[str, Any], collected: Dict[str, Any]) -> bool:
    """Return True if this field should be asked/considered given collected data.

    A field without ``show_if`` is always visible.
    A field with ``show_if`` is only visible when the dependency field's
    collected value matches one of the configured trigger values.

    Example show_if structure::

        {"field": "location", "value": ["Şehir Dışı"]}
        {"field": "location", "value": "Şehir Dışı"}   # single string also ok
    """
    show_if = field.get("show_if")
    if not show_if:
        return True

    dep_key = show_if.get("field")
    if not dep_key:
        return True  # malformed show_if — treat as always visible

    trigger_values = show_if.get("value", [])
    if isinstance(trigger_values, str):
        trigger_values = [trigger_values]

    dep_val = collected.get(dep_key)
    if not dep_val or dep_val == SKIP_SENTINEL:
        return False  # dependency not yet collected → conditional field is invisible

    # Case-insensitive comparison so "stüdyo" matches "Stüdyo" etc.
    dep_val_lower = dep_val.strip().lower()
    return dep_val_lower in [v.lower() for v in trigger_values]


def is_complete(fields_config: List[Dict[str, Any]], collected: Dict[str, Any]) -> bool:
    """Return True when every *visible* required field has a non-empty value in *collected*.

    Invisible required fields (whose ``show_if`` condition is not met) are not
    required at the current state, so they are skipped.

    ``SKIP_SENTINEL`` does **not** count as filled for required fields.
    """
    for f in fields_config:
        if f.get("required") and field_is_visible(f, collected):
            val = collected.get(f["key"])
            if not val or val == SKIP_SENTINEL:
                return False
    return True


def all_fields_handled(fields_config: List[Dict[str, Any]], collected: Dict[str, Any]) -> bool:
    """Return True when every *visible* field (required + optional) is either filled or skipped.

    Invisible fields are not counted — they will be evaluated again if visibility changes.
    """
    for f in fields_config:
        if not field_is_visible(f, collected):
            continue
        val = collected.get(f["key"])
        if not val:
            return False
    return True


def get_next_field(
    fields_config: List[Dict[str, Any]], collected: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """Return the first *visible* required field that has not yet been collected, or None.

    A value of ``SKIP_SENTINEL`` is treated as *not filled* for required fields
    because required fields cannot be skipped.
    Invisible fields (show_if condition not met) are skipped entirely.
    """
    for f in fields_config:
        if f.get("required") and field_is_visible(f, collected):
            val = collected.get(f["key"])
            if not val or val == SKIP_SENTINEL:
                return f
    return None


def get_next_optional_field(
    fields_config: List[Dict[str, Any]], collected: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """Return the first *visible* optional field that has not been filled or skipped, or None."""
    for f in fields_config:
        if not f.get("required") and field_is_visible(f, collected):
            val = collected.get(f["key"])
            if not val:
                return f
    return None


def _format_question(field: Dict[str, Any], *, optional: bool = False) -> str:
    """Build the question string for a field, including options and validation hints."""
    question = field.get("question") or f"{field.get('label', field['key'])} nedir?"

    # Validation format hint (only when no options, since options is more specific)
    opts = field.get("options")
    validation = field.get("validation")
    if isinstance(opts, (list, tuple)) and len(opts) > 0:
        allowed = [str(o).strip() for o in opts if o is not None and str(o).strip()]
        if allowed:
            question = f"{question} (Seçenekler: {', '.join(allowed)})"
    elif validation and validation != "text":
        hint = _VALIDATION_HINTS.get(validation, "")
        if hint:
            question = f"{question} {hint}"

    if optional:
        question = f"{question} (Opsiyonel — istemiyorsanız 'geç' diyebilirsiniz)"
    return question


def _get_remaining_required(
    fields_config: List[Dict[str, Any]], collected: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Return all *visible* required fields not yet filled (in order)."""
    remaining = []
    for f in fields_config:
        if f.get("required") and field_is_visible(f, collected):
            val = collected.get(f["key"])
            if not val or val == SKIP_SENTINEL:
                remaining.append(f)
    return remaining


def build_mode_context(
    mode: str,
    fields_config: List[Dict[str, Any]],
    collected: Dict[str, Any],
    *,
    confirmed: bool,
    saved: bool,
) -> str:
    """Return a Turkish-language system-prompt suffix for the current collection state.

    Flow order:
      1. Ask required fields one by one (in array order, visibility-filtered)
      2. Ask optional fields one by one (user can skip with 'geç/yok/istemiyorum')
      3. Show summary + ask confirmation
    """
    lines = ["--- [MODE CONTEXT] ---"]

    if saved:
        lines.append("Kaydedildi. Kullanıcıya teşekkür et ve başka yardım isteyip istemediğini sor.")
    elif confirmed:
        lines.append("Bilgiler onaylandı ve şu an kaydediliyor.")
    elif all_fields_handled(fields_config, collected):
        summary_parts = []
        for f in fields_config:
            # Only show currently visible fields in the confirmation summary
            if not field_is_visible(f, collected):
                continue
            val = collected.get(f["key"])
            if val and val != SKIP_SENTINEL:
                label = f.get("label") or f["key"]
                summary_parts.append(f"  • {label}: {val}")
        # For appointment mode: inject Python-computed final price into summary
        if mode == "appointment":
            price_block = _build_computed_price_block(collected)
            if price_block:
                summary_parts.append(price_block)
        summary = "\n".join(summary_parts)
        lines.append(
            f"Tüm bilgiler toplandı. Kullanıcıya şu özeti göster ve "
            f"\"Bu bilgiler doğru mu? Onaylıyor musunuz?\" diye sor:\n{summary}"
        )
    else:
        # ── Already collected ──────────────────────────────────────────────
        _filled = []
        for f in fields_config:
            val = collected.get(f["key"])
            if val and val != SKIP_SENTINEL:
                _filled.append(f"  ✓ {f.get('label', f['key'])}: {val}")
        if _filled:
            lines.append(
                "Şu ana kadar ALINAN BİLGİLER (bunları TEKRAR SORMA):\n" + "\n".join(_filled)
            )

        # ── Pre-computed prices (appointment mode only) ─────────────────────
        # Inject Python-computed prices so the LLM never does arithmetic itself.
        # Shows per-artist prices when event+location are known but artist isn't
        # chosen yet; shows the exact total when artist (and optionally
        # extra_people) is also known.
        if mode == "appointment":
            price_block = _build_computed_price_block(collected)
            if price_block:
                lines.append(price_block)

        # ── Remaining required fields (full list for LLM awareness) ───────
        remaining_req = _get_remaining_required(fields_config, collected)
        if remaining_req:
            remaining_items = []
            for f in remaining_req:
                label = f.get("label", f["key"])
                show_if = f.get("show_if")
                if show_if:
                    dep_key = show_if.get("field", "")
                    trigger = show_if.get("value", [])
                    if isinstance(trigger, str):
                        trigger = [trigger]
                    dep_label = next(
                        (ff.get("label", dep_key) for ff in fields_config if ff.get("key") == dep_key),
                        dep_key,
                    )
                    remaining_items.append(
                        f"{label} (eğer {dep_label} = {' veya '.join(str(t) for t in trigger)})"
                    )
                else:
                    remaining_items.append(label)
            lines.append(
                "Henüz alınmayan zorunlu bilgiler: "
                + ", ".join(remaining_items)
                + "\n"
                "ÖNEMLİ: Eğer kullanıcı tek mesajda birden fazla bilgi verdiyse, "
                "hepsini aynı anda kabul et ve sadece en başta gelen EKSİK alanı sor."
            )

        # ── Phase 1: ask next required field ──────────────────────────────
        next_req = get_next_field(fields_config, collected)
        if next_req:
            question = _format_question(next_req)

            # Peek at the field after next_req for the "already answered" lookahead
            _temp_collected = {**collected, next_req["key"]: "<FILLED>"}
            _after = get_next_field(fields_config, _temp_collected)
            if not _after:
                _after = get_next_optional_field(fields_config, _temp_collected)
            _after_q = _format_question(_after, optional=not _after.get("required")) if _after else None

            hint = (
                f"KURAL: Eğer kullanıcı bu mesajda \"{next_req.get('label', next_req['key'])}\" "
                f"bilgisini zaten verdiyse, cevabı kabul et"
            )
            if _after_q:
                hint += f" ve şu soruyu sor: \"{_after_q}\""
            hint += ".\n"

            # Validation failure re-ask hint
            validation = next_req.get("validation")
            if validation and validation != "text":
                fmt_hint = _VALIDATION_HINTS.get(validation, "")
                if fmt_hint:
                    hint += (
                        f"DOĞRULAMA: Bu alan için {fmt_hint} beklenmektedir. "
                        f"Kullanıcı geçersiz bir format verirse, nazikçe doğru formatı iste.\n"
                    )
            elif isinstance(next_req.get("options"), (list, tuple)) and next_req.get("options"):
                allowed = [str(o).strip() for o in next_req["options"] if o]
                hint += (
                    f"DOĞRULAMA: Sadece şu seçeneklerden biri kabul edilir: {', '.join(allowed)}. "
                    f"Kullanıcı listede olmayan bir değer verirse, tekrar sor.\n"
                )

            lines.append(
                f"SONRAKİ SORU:\n"
                f"\"{question}\"\n"
                f"{hint}"
                f"Eğer kullanıcı henüz cevap vermediyse, SADECE bu soruyu sor. "
                f"Başka bilgi verme, liste gösterme."
            )
        else:
            # ── Phase 2: ask next optional field ──────────────────────────
            next_opt = get_next_optional_field(fields_config, collected)
            if next_opt:
                question = _format_question(next_opt, optional=True)
                _temp_collected2 = {**collected, next_opt["key"]: "<FILLED>"}
                _after2 = get_next_optional_field(fields_config, _temp_collected2)
                _after_q2 = _format_question(_after2, optional=True) if _after2 else None

                hint2 = ""
                if _after_q2:
                    hint2 = f"Eğer kullanıcı bu soruyu zaten cevapladıysa, sonraki soru: \"{_after_q2}\"\n"

                # Validation for optional fields
                validation_opt = next_opt.get("validation")
                if validation_opt and validation_opt != "text":
                    fmt_hint = _VALIDATION_HINTS.get(validation_opt, "")
                    if fmt_hint:
                        hint2 += (
                            f"DOĞRULAMA: Bu alan için {fmt_hint} beklenmektedir. "
                            f"Geçersiz format verilirse nazikçe tekrar iste veya 'geç' demelerine izin ver.\n"
                        )

                lines.append(
                    f"SONRAKİ SORU:\n"
                    f"\"{question}\"\n"
                    f"{hint2}"
                    f"Kullanıcı 'yok', 'geç', 'istemiyorum', 'pas', 'hayır', 'atla' gibi bir ifade "
                    f"kullanırsa bu soruyu KESİNLİKLE TEKRAR SORMA; bu alanı geç ve "
                    f"bir sonraki adıma geç (özet + onay)."
                )
            else:
                lines.append("Kullanıcıdan bilgi almaya devam et.")

    lines.append("--- [/MODE CONTEXT] ---")
    return "\n".join(lines)


def _build_reschedule_context(rs: Dict[str, Any]) -> str:
    """Build a Turkish mode-context string for an active reschedule flow."""
    lines = ["--- [MODE CONTEXT: reschedule] ---"]
    appt_number = rs.get("appt_number", "")
    updates: Dict[str, Any] = rs.get("updates") or {}

    lines.append(f"RANDEVU DEĞİŞİKLİĞİ AKTİF — Randevu No: {appt_number}")
    lines.append(
        "Kullanıcı bu randevu için yeni tarih/saat (ve isteğe bağlı sanatçı) istiyor."
    )

    if updates:
        lines.append("\nŞimdiye kadar toplanan bilgiler:")
        for k, v in updates.items():
            label = {"event_date": "Yeni Tarih", "event_time": "Yeni Saat", "artist": "Sanatçı"}.get(k, k)
            lines.append(f"  • {label}: {v}")

    missing = [k for k in ("event_date", "event_time") if not updates.get(k)]

    if rs.get("confirmed") and not rs.get("saved"):
        lines.append("\nKullanıcı onayladı — değişiklik kaydediliyor.")
    elif not missing and updates.get("event_date") and updates.get("event_time"):
        lines.append(
            f"\nTüm bilgiler toplandı: {updates.get('event_date')} saat {updates.get('event_time')}."
        )
        lines.append(
            "SONRAKİ SORU:\n\"Bu değişikliği onaylıyor musunuz? (Evet/Hayır)\""
        )
    elif "event_date" not in updates:
        lines.append(
            "\nSONRAKİ SORU:\n\"Yeni tarih için hangi günü tercih edersiniz?\""
        )
    elif "event_time" not in updates:
        lines.append(
            "\nSONRAKİ SORU:\n\"Uygun olduğunuz saati aşağıdan seçin (seçenekler bot tarafından sunulacak).\""
        )

    lines.append("--- [/MODE CONTEXT] ---")
    return "\n".join(lines)


def compute_mode_context(
    config_dict: Dict[str, Any],
    flow_state: Dict[str, Any],
) -> Tuple[Optional[str], Optional[str]]:
    """Determine the active mode and produce its context string.

    Returns ``(active_mode, mode_context_string)``.
    Returns ``(None, None)`` when no mode is active.
    """
    appointment_fields: List[Dict[str, Any]] = config_dict.get("appointment_fields") or []
    order_mode_enabled: bool = bool(config_dict.get("order_mode_enabled", False))
    order_fields: List[Dict[str, Any]] = config_dict.get("order_fields") or []

    appt_state: Dict[str, Any] = flow_state.get("appointment") or {}
    order_state: Dict[str, Any] = flow_state.get("order") or {}
    reschedule_state: Dict[str, Any] = flow_state.get("reschedule") or {}

    stored_mode: Optional[str] = flow_state.get("active_mode")

    def _reschedule_active() -> bool:
        return bool(reschedule_state.get("appt_number") and not reschedule_state.get("saved"))

    def _appt_active() -> bool:
        if not appointment_fields:
            return False
        if appt_state.get("saved"):
            return False
        return bool(stored_mode == "appointment" or (not stored_mode and appt_state))

    def _order_active() -> bool:
        if not (order_mode_enabled and order_fields):
            return False
        if order_state.get("saved"):
            return False
        return bool(stored_mode == "order" or (not stored_mode and order_state))

    # Reschedule takes priority over appointment/order modes
    if _reschedule_active():
        context = _build_reschedule_context(reschedule_state)
        return "reschedule", context

    appt_saved = bool(appt_state.get("saved"))
    order_saved = bool(order_state.get("saved"))

    # When appointment is saved, inject the reference number into every turn so the
    # character LLM can quote it and cancel/reschedule requests resolve without re-asking.
    if appt_saved and appt_state.get("appt_number"):
        rnd = appt_state["appt_number"]
        context = (
            f"[RANDEVU KAYITLI]\n"
            f"Bu müşterinin randevusu oluşturuldu. Randevu numarası: {rnd}\n"
            f"Müşteri iptal veya değişiklik isterse bu numarayı kullan ve "
            f"'{rnd} iptal' ya da '{rnd} tarihimi değiştir' gibi komutları hatırlat.\n"
            f"[/RANDEVU KAYITLI]"
        )
        return None, context

    if (stored_mode == "appointment" or (not stored_mode and _appt_active())) and not appt_saved:
        if not appointment_fields:
            return None, None
        context = build_mode_context(
            "appointment",
            appointment_fields,
            appt_state,
            confirmed=bool(appt_state.get("confirmed")),
            saved=False,
        )
        return "appointment", context

    if (stored_mode == "order" or (not stored_mode and _order_active())) and not order_saved:
        if not (order_mode_enabled and order_fields):
            return None, None
        context = build_mode_context(
            "order",
            order_fields,
            order_state,
            confirmed=bool(order_state.get("confirmed")),
            saved=False,
        )
        return "order", context

    return None, None

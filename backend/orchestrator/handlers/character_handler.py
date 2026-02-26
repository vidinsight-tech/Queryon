"""CharacterHandler: LLM-driven conversational handler with a bot persona.

Uses a character system prompt to give the LLM full context about who the bot
is, what it knows, and how to converse.  The LLM handles natural language
understanding — no rigid keyword flows needed.

Active flow modes (appointment / order / reschedule)
-----------------------------------------------------
When the user is in an active data-collection flow, a single LLM call is made
with a comprehensive system-prompt section that includes:
  • All fields to collect (labels, options, validation hints, show_if conditions)
  • What has already been collected
  • What is still missing (required vs optional)
  • Live availability slots (when injected by the orchestrator)
  • Pre-computed price info (appointment mode)
  • Behavioural rules (no re-asking, multi-field extraction, skip handling, etc.)
  • Mandatory structured output format: <extract>{...}</extract><response>...</response>

The LLM extracts data AND generates its response in one pass — no second
extraction call needed.  All decisions (what to ask next, confirmation,
skip handling) are made by the LLM based on full conversation context.

Passive extraction
------------------
For non-active-mode turns where the user mentions appointment/order details
in passing, a secondary focused extraction call still runs.
"""
from __future__ import annotations

import asyncio
import datetime
import json
import logging
import os
import re
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from backend.orchestrator.handlers.base import BaseHandler
from backend.orchestrator.types import ConversationTurn, IntentType, OrchestratorResult

if TYPE_CHECKING:
    from backend.clients.llm.base import BaseLLMClient

logger = logging.getLogger(__name__)

_DAYS_TR = ["pazartesi", "salı", "çarşamba", "perşembe", "cuma", "cumartesi", "pazar"]
_MONTHS_TR = [
    "ocak", "şubat", "mart", "nisan", "mayıs", "haziran",
    "temmuz", "ağustos", "eylül", "ekim", "kasım", "aralık",
]

# Keywords that trigger appointment extraction (passive mode — no active flow)
_APPT_KEYWORDS = {
    "randevu", "rezervasyon", "booking", "appointment",
    "ad", "soyad", "isim", "telefon", "email", "e-posta",
    "tarih", "tarihte", "günde", "gün", "evet", "tamam", "onayla",
    "05", "düzelt", "değiştir", "yarın", "bugün", "hafta",
    "saat", "sabah", "öğle", "akşam", "gece",
    "geç", "yok", "istemiyorum", "pas", "geçelim",
    "düğün", "nişan", "kına", "söz", "davetli", "nedime",
    "makyaj", "gelin", "hazırlık", "profesyonel",
    "stüdyo", "otel", "şehir dışı", "ev",
    "izel", "merve", "dicle", "irem", "gizem", "neslihan", "ekip",
    "kişi", "kişilik",
    *_DAYS_TR,
    *_MONTHS_TR,
}

# Keywords that trigger order extraction (passive mode)
_ORDER_KEYWORDS = {
    "sipariş", "order", "ürün", "product", "adet", "miktar", "quantity",
    "ad", "soyad", "isim", "telefon", "email", "e-posta",
    "adres", "teslimat", "delivery", "evet", "tamam", "onayla",
    "düzelt", "değiştir",
}

# Keywords that signal a cancellation intent
_CANCEL_KEYWORDS = {
    "iptal", "iptal et", "iptal etmek", "cancel", "randevumu iptal",
    "sil", "geri al", "randevu iptali",
}

# Keywords that signal a reschedule intent
_RESCHEDULE_KEYWORDS = {
    # Turkish verbs / phrases
    "tarihimi değiştir", "saatimi değiştir", "randevuyu değiştir",
    "randevumu değiştir", "tarih değişikliği", "saat değişikliği",
    "randevu değişikliği", "randevuyu güncelle", "randevumu güncelle",
    "randevuyu güncellemek istiyorum", "güncellemek istiyorum",
    "randevuyu güncelleyelim", "randevuyu güncelle",
    # Generic words (used in combination with context)
    "güncelle", "güncelleme", "ertele",
    # English fallback
    "reschedule",
}

# Matches reference numbers like RND-2026-0042 (case-insensitive).
# Kullanıcılar bazen baştaki "R" harfini atlayarak "ND-2026-0001" yazabiliyor.
# Bu durumda, bu paterni ayrıca yakalayıp "RND-..." olarak normalize edeceğiz.
_APPT_NUM_RE = re.compile(r"\bRND-\d{4}-\d{4}\b", re.IGNORECASE)
_APPT_NUM_NEAR_RE = re.compile(r"\bND-\d{4}-\d{4}\b", re.IGNORECASE)

# Words that signal the user wants to skip the current optional field.
# Used inside _extract_data() for passive extraction.
_SKIP_WORDS = {
    "geç", "yok", "istemiyorum", "pas", "geçelim",
    "hayır", "atla", "geçiyorum", "yok yok", "geçtim",
}

# Fields used during reschedule flow extraction
_RESCHEDULE_FIELDS: List[Dict[str, Any]] = [
    {"key": "event_date", "label": "Yeni Tarih", "required": False, "validation": "date"},
    {"key": "event_time", "label": "Yeni Saat",  "required": False, "validation": "time"},
    {"key": "artist",     "label": "Sanatçı",    "required": False, "validation": "text"},
]


class CharacterHandler(BaseHandler):
    """Sends conversation to the LLM with a character system prompt.

    For active appointment/order/reschedule flows, injects full context into
    the system prompt and parses structured output — one LLM call, no separate
    extraction step.

    For all other turns, uses a standard LLM call and optionally runs a second
    focused extraction call for passive appointment/order data capture.
    """

    def __init__(
        self,
        llm: "BaseLLMClient",
        system_prompt: str,
        *,
        timeout_seconds: Optional[float] = None,
        appointment_fields: Optional[List[Dict[str, Any]]] = None,
        order_fields: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        self._llm = llm
        self._system_prompt = system_prompt
        self._timeout_seconds = timeout_seconds
        self._appointment_fields: List[Dict[str, Any]] = appointment_fields or []
        self._order_fields: List[Dict[str, Any]] = order_fields or []

    async def handle(
        self,
        query: str,
        *,
        conversation_history: Optional[List[ConversationTurn]] = None,
        **kwargs: object,
    ) -> OrchestratorResult:
        mode_context: Optional[str] = kwargs.get("mode_context")  # type: ignore[assignment]
        active_mode: Optional[str] = kwargs.get("active_mode")  # type: ignore[assignment]
        appt_collected: Optional[Dict[str, Any]] = kwargs.get("appt_collected")  # type: ignore[assignment]
        order_collected: Optional[Dict[str, Any]] = kwargs.get("order_collected")  # type: ignore[assignment]
        appt_availability_slots: Dict[str, List[str]] = kwargs.get("appt_availability_slots") or {}  # type: ignore[assignment]

        metadata: Dict[str, Any] = {}

        # ── Cancel intent (regex, always run) ─────────────────────────────────
        cancel_intent = self._extract_cancel_intent(query)
        if not cancel_intent:
            q_lower = query.lower()
            if any(kw in q_lower for kw in _CANCEL_KEYWORDS):
                _saved_rnd = (appt_collected or {}).get("appt_number")
                if _saved_rnd:
                    cancel_intent = {"appt_number": _saved_rnd, "action": "cancel"}
        if cancel_intent:
            metadata["appointment_cancel"] = cancel_intent

        # ── Reschedule intent (regex, always run) ──────────────────────────────
        reschedule_intent = self._extract_reschedule_intent(query)
        if not reschedule_intent:
            q_lower = query.lower()
            if any(kw in q_lower for kw in _RESCHEDULE_KEYWORDS):
                _saved_rnd_rs = (appt_collected or {}).get("appt_number")
                if _saved_rnd_rs:
                    reschedule_intent = {"appt_number": _saved_rnd_rs, "action": "reschedule"}
        if reschedule_intent:
            metadata["appointment_reschedule_intent"] = reschedule_intent

        # ── Active flow: one LLM call with full context ───────────────────────
        _is_flow_mode = active_mode in ("appointment", "order", "reschedule")

        if _is_flow_mode:
            if active_mode == "appointment":
                _flow_fields = self._appointment_fields
                _flow_collected: Dict[str, Any] = appt_collected or {}
                _meta_key = "appointment_update"
                _avail = appt_availability_slots
            elif active_mode == "order":
                _flow_fields = self._order_fields
                _flow_collected = order_collected or {}
                _meta_key = "order_update"
                _avail = {}
            else:  # reschedule
                _flow_fields = _RESCHEDULE_FIELDS
                _flow_collected = kwargs.get("reschedule_collected") or {}  # type: ignore[assignment]
                _meta_key = "reschedule_update"
                _avail = kwargs.get("reschedule_availability_slots") or {}  # type: ignore[assignment]

            flow_section = self._build_flow_section(
                active_mode, _flow_fields, _flow_collected, _avail,
            )
            messages = self._build_messages(
                query, conversation_history, flow_section=flow_section,
            )

            try:
                coro = self._llm.chat(messages)
                if self._timeout_seconds and self._timeout_seconds > 0:
                    coro = asyncio.wait_for(coro, timeout=self._timeout_seconds)
                raw = await coro
            except asyncio.TimeoutError:
                logger.warning("CharacterHandler: LLM timed out (%.0fs)", self._timeout_seconds or 0)
                return OrchestratorResult(
                    query=query, intent=IntentType.CHARACTER, answer=None,
                    metadata={**metadata, "error": "timeout"},
                )
            except Exception as exc:
                logger.error("CharacterHandler: LLM call failed: %s", exc)
                return OrchestratorResult(
                    query=query, intent=IntentType.CHARACTER, answer=None,
                    metadata={**metadata, "error": str(exc)},
                )

            extracted, answer = self._parse_flow_response(raw, query)

            # Post-process extracted fields: normalize options, validate formats,
            # drop fields whose show_if condition is not yet satisfied.
            if extracted and _flow_fields:
                extracted = self._normalize_extraction_to_options(extracted, _flow_fields)
                extracted = self._validate_extracted(extracted, _flow_fields)
                extracted = self._filter_invisible_fields(extracted, _flow_fields, _flow_collected)

            if extracted:
                metadata[_meta_key] = extracted

            logger.debug(
                "CharacterHandler: flow=%s extracted=%s confirmed=%s",
                active_mode,
                [k for k in extracted if k != "confirmed"],
                extracted.get("confirmed", False),
            )

            return OrchestratorResult(
                query=query,
                intent=IntentType.CHARACTER,
                answer=answer.strip() if answer else answer,
                metadata=metadata,
            )

        # ── Non-flow mode: regular character LLM + optional passive extraction ─
        messages = self._build_messages(query, conversation_history, mode_context=mode_context)
        try:
            coro = self._llm.chat(messages)
            if self._timeout_seconds and self._timeout_seconds > 0:
                coro = asyncio.wait_for(coro, timeout=self._timeout_seconds)
            answer = await coro
        except asyncio.TimeoutError:
            logger.warning("CharacterHandler: LLM timed out (%.0fs)", self._timeout_seconds or 0)
            return OrchestratorResult(
                query=query, intent=IntentType.CHARACTER, answer=None,
                metadata={**metadata, "error": "timeout"},
            )
        except Exception as exc:
            logger.error("CharacterHandler: LLM call failed: %s", exc)
            return OrchestratorResult(
                query=query, intent=IntentType.CHARACTER, answer=None,
                metadata={**metadata, "error": str(exc)},
            )

        from backend.orchestrator.mode_engine import get_next_field, get_next_optional_field

        # Passive appointment extraction: only when signals present in message
        if (
            self._appointment_fields
            and self._should_extract(query, answer, _APPT_KEYWORDS)
        ):
            _nf = get_next_field(self._appointment_fields, appt_collected or {})
            if not _nf:
                _nf = get_next_optional_field(self._appointment_fields, appt_collected or {})
            _current_key = _nf["key"] if _nf else None
            appt_update = await self._extract_data(
                query, conversation_history, answer, self._appointment_fields, "randevu",
                already_collected=appt_collected,
                current_field_key=_current_key,
            )
            if appt_update:
                metadata["appointment_update"] = appt_update
                logger.info(
                    "CharacterHandler: passive appointment extraction: %s",
                    list(appt_update.keys()),
                )

        # Passive order extraction: only when signals present
        if (
            self._order_fields
            and self._should_extract(query, answer, _ORDER_KEYWORDS)
        ):
            _nf_o = get_next_field(self._order_fields, order_collected or {})
            if not _nf_o:
                _nf_o = get_next_optional_field(self._order_fields, order_collected or {})
            _current_key_o = _nf_o["key"] if _nf_o else None
            order_update = await self._extract_data(
                query, conversation_history, answer, self._order_fields, "sipariş",
                already_collected=order_collected,
                current_field_key=_current_key_o,
            )
            if order_update:
                metadata["order_update"] = order_update
                logger.info(
                    "CharacterHandler: passive order extraction: %s",
                    list(order_update.keys()),
                )

        return OrchestratorResult(
            query=query,
            intent=IntentType.CHARACTER,
            answer=answer.strip(),
            metadata=metadata,
        )

    # ── Flow section builder ──────────────────────────────────────────────────

    def _build_flow_section(
        self,
        active_mode: str,
        fields_config: List[Dict[str, Any]],
        collected: Dict[str, Any],
        availability_slots: Dict[str, List[str]],
    ) -> str:
        """Build the comprehensive flow-context section injected into the system prompt.

        This section gives the LLM everything it needs to:
        - Know what has been collected vs what is still missing
        - Understand field constraints (options, validation, conditional visibility)
        - See live availability slots
        - See pre-computed prices (appointment mode)
        - Follow the correct output format
        """
        from backend.orchestrator.mode_engine import field_is_visible, _build_computed_price_block

        mode_labels = {
            "appointment": "RANDEVU",
            "order": "SİPARİŞ",
            "reschedule": "RANDEVU DEĞİŞİKLİĞİ",
        }
        mode_label = mode_labels.get(active_mode, active_mode.upper())

        # Keys that are internal state metadata — never shown to LLM as collected data
        _meta_keys = {"confirmed", "saved", "appointment_id", "appt_number", "active_mode", "order_id"}

        lines: List[str] = [
            f"═══ GÖREV: {mode_label} BİLGİ TOPLAMA ═══",
            "",
        ]

        # Reschedule: show the appointment reference number
        if active_mode == "reschedule":
            appt_number = collected.get("appt_number", "")
            if appt_number:
                lines.append(f"Randevu No: {appt_number} için değişiklik yapılıyor.")
                lines.append("")

        # What has already been collected
        filled = {
            k: v for k, v in collected.items()
            if k not in _meta_keys and v and v != "__skip__"
        }
        if filled:
            lines.append("TOPLANAN BİLGİLER (bunları tekrar SORMA):")
            for k, v in filled.items():
                label = next(
                    (f.get("label", k) for f in fields_config if f.get("key") == k), k
                )
                lines.append(f"  ✓ {label}: {v}")
        else:
            lines.append("TOPLANAN BİLGİLER: (Henüz hiçbir bilgi toplanmadı)")
        lines.append("")

        # Missing fields summary
        missing_req: List[str] = []
        missing_opt: List[str] = []
        for f in fields_config:
            if not field_is_visible(f, collected):
                continue
            val = collected.get(f["key"])
            if val and val != "__skip__":
                continue
            if f.get("required"):
                missing_req.append(f.get("label", f["key"]))
            else:
                missing_opt.append(f.get("label", f["key"]))

        lines.append(
            f"EKSİK ZORUNLU ALANLAR: "
            f"{', '.join(missing_req) if missing_req else 'Tümü tamamlandı'}"
        )
        if missing_opt:
            lines.append(f"EKSİK OPSİYONEL ALANLAR: {', '.join(missing_opt)}")
        lines.append("")

        # Live availability slots (injected by orchestrator)
        if availability_slots:
            for slot_key, slots in availability_slots.items():
                slot_label = next(
                    (f.get("label", slot_key) for f in fields_config if f.get("key") == slot_key),
                    slot_key,
                )
                lines.append(f"UYGUN {slot_label.upper()} SEÇENEKLERİ:")
                for s in slots:
                    lines.append(f"  • {s}")
                lines.append("(Bu listedeki seçeneklerden biri istenmeli — listede olmayan saati kabul etme)")
                lines.append("")

        # Pre-computed prices (appointment mode only)
        if active_mode == "appointment":
            price_block = _build_computed_price_block(collected)
            if price_block:
                lines.append(price_block)
                lines.append("")

        # Field definitions
        lines.append("TOPLANACAK ALANLAR:")
        visible_idx = 0
        for f in fields_config:
            is_visible = field_is_visible(f, collected)
            show_if = f.get("show_if")
            if not is_visible:
                if show_if:
                    dep_key = show_if.get("field", "")
                    trigger = show_if.get("value", [])
                    if isinstance(trigger, str):
                        trigger = [trigger]
                    dep_label = next(
                        (ff.get("label", dep_key) for ff in fields_config if ff.get("key") == dep_key),
                        dep_key,
                    )
                    lines.append(
                        f"  (Koşullu) [{f['key']}] → "
                        f"Sadece {dep_label} = {' / '.join(str(t) for t in trigger)} olduğunda sorulur"
                    )
                continue

            visible_idx += 1
            req_label = "zorunlu" if f.get("required") else "opsiyonel"
            val = collected.get(f["key"])
            if val and val != "__skip__":
                status = "✓"
            elif val == "__skip__":
                status = "↷ (atlandı)"
            else:
                status = "→ (eksik)"

            field_line = (
                f"  {visible_idx}. {f.get('label', f['key'])} [{f['key']}] "
                f"[{req_label}] {status}"
            )

            # Use injected availability slots if available, otherwise field options
            opts = availability_slots.get(f["key"]) or f.get("options")
            if isinstance(opts, (list, tuple)) and opts:
                allowed = [str(o).strip() for o in opts if o is not None and str(o).strip()]
                if allowed:
                    field_line += f"\n       Seçenekler: {', '.join(allowed)}"

            validation = f.get("validation")
            if validation and validation not in ("text", None):
                _fmt_hints: Dict[str, str] = {
                    "phone": "Format: 05XX XXX XX XX (sadece rakam)",
                    "email": "Format: ad@domain.com",
                    "date": "Format: GG Ay YYYY — örn: 15 Mart 2026",
                    "time": "Format: SS:DD, 24 saat — örn: 14:30",
                    "number": "Sadece sayısal değer",
                }
                hint = _fmt_hints.get(validation, "")
                if hint:
                    field_line += f"\n       {hint}"

            lines.append(field_line)

        lines.append("")

        # Behavioural rules
        lines.append("ÇALIŞMA KURALLARI:")
        lines.append("  1. Konuşma geçmişine bak — önceden verilen cevapları ASLA tekrar sorma")
        lines.append("  2. Kullanıcı tek mesajda birden fazla bilgi verdiyse HEPSİNİ <extract> bloğunda çıkar")
        lines.append("     ÖNEMLİ: Tüm tespit edilen alanları extract bloğuna ekle, hiçbirini atlama!")
        lines.append("  3. Geçersiz format veya listede olmayan seçenek → kabul etme, doğru formatı iste")
        lines.append("  4. Opsiyonel alan için 'geç/yok/istemiyorum/hayır/pas' → {\"key\": \"__skip__\"} döndür")
        lines.append("  5. Tüm zorunlu alanlar toplandığında özet göster ve 'Bu bilgiler doğru mu?' diye sor")
        lines.append("  6. Kullanıcı onaylarsa (evet/tamam/onayla/olur) → {\"confirmed\": true} döndür")
        lines.append("  7. Kullanıcı önceki bir bilgiyi düzeltirse → sadece o alanı güncelle, devam et")
        lines.append("  8. Tarihleri zaman bağlamına göre çevir: 'yarın', 'bu Cuma', 'önümüzdeki Salı' vb.")
        lines.append("  9. Saatleri 24 saat formatına çevir: 'akşam 6' → '18:00', 'sabah 10' → '10:00'")
        lines.append(" 10. Sayı ifadelerini rakama çevir: 'bir/tek' → '1', 'iki' → '2', 'üç' → '3' vb.")
        lines.append(" 11. HER yanıtında mutlaka <extract>...</extract> ve <response>...</response> yapısını kullan")
        lines.append("")

        # Output format
        lines.append("ZORUNLU ÇIKTI FORMATI — Her yanıtta mutlaka bu yapıyı kullan:")
        lines.append("<extract>")
        lines.append('{"alan_key": "değer"}')
        lines.append("</extract>")
        lines.append("<response>")
        lines.append("Kullanıcıya gösterilecek Türkçe yanıt")
        lines.append("</response>")
        lines.append("")
        lines.append("Çıkarılacak yeni bilgi yoksa: <extract>{}</extract>")
        lines.append("Kullanıcı onaylarsa: <extract>{\"confirmed\": true}</extract>")
        lines.append(f"═══ /GÖREV ═══")

        return "\n".join(lines)

    @staticmethod
    def _parse_flow_response(raw: str, query: str) -> Tuple[Dict[str, Any], str]:
        """Parse <extract>...</extract> and <response>...</response> from LLM output.

        Returns (extracted_dict, response_text).
        Falls back gracefully if tags are missing or JSON is malformed.
        """
        extracted: Dict[str, Any] = {}

        # Parse <extract> block
        extract_match = re.search(r"<extract>(.*?)</extract>", raw, re.DOTALL | re.IGNORECASE)
        if extract_match:
            extract_text = extract_match.group(1).strip()
            if extract_text and extract_text != "{}":
                try:
                    parsed = json.loads(extract_text)
                    if isinstance(parsed, dict):
                        extracted = {
                            k: v for k, v in parsed.items()
                            if v is not None
                            and not (isinstance(v, str) and v.strip().lower() in ("null", "none", ""))
                        }
                except (json.JSONDecodeError, ValueError):
                    # Try to find a JSON object within the text
                    m = re.search(r"\{[^{}]+\}", extract_text, re.DOTALL)
                    if m:
                        try:
                            parsed = json.loads(m.group())
                            if isinstance(parsed, dict):
                                extracted = {k: v for k, v in parsed.items() if v is not None}
                        except (json.JSONDecodeError, ValueError):
                            pass
                    logger.warning(
                        "CharacterHandler: flow <extract> parse failed: %r", extract_text[:120]
                    )

        # Parse <response> block
        response_match = re.search(r"<response>(.*?)</response>", raw, re.DOTALL | re.IGNORECASE)
        if response_match:
            response = response_match.group(1).strip()
        else:
            # Fallback: strip the extract block and use the remainder
            response = re.sub(
                r"<extract>.*?</extract>", "", raw, flags=re.DOTALL | re.IGNORECASE
            ).strip()
            if not response:
                response = raw.strip()

        return extracted, response

    # ── Cancel / reschedule intent helpers ───────────────────────────────────

    def _extract_cancel_intent(self, query: str) -> Optional[Dict[str, Any]]:
        """Pure regex check for cancel + reference number — no LLM call needed."""
        q = query.lower()
        has_cancel = any(kw in q for kw in _CANCEL_KEYWORDS)
        match = _APPT_NUM_RE.search(query)
        if has_cancel and match:
            return {"appt_number": match.group(0).upper(), "action": "cancel"}
        # Yakın eşleşme: "ND-2026-0001" gibi yazımları "RND-2026-0001"e çevir.
        if has_cancel and not match:
            near = _APPT_NUM_NEAR_RE.search(query)
            if near:
                raw = near.group(0).upper()
                if raw.startswith("ND-"):
                    raw = "R" + raw  # RND-...
                return {"appt_number": raw, "action": "cancel"}
        return None

    def _extract_reschedule_intent(self, query: str) -> Optional[Dict[str, Any]]:
        """Pure regex check for reschedule keyword + reference number — no LLM call needed."""
        q = query.lower()
        has_reschedule = any(kw in q for kw in _RESCHEDULE_KEYWORDS)
        match = _APPT_NUM_RE.search(query)
        if has_reschedule and match:
            return {"appt_number": match.group(0).upper(), "action": "reschedule"}
        # Yakın eşleşme: "ND-2026-0001" gibi yazımları "RND-2026-0001"e çevir.
        if has_reschedule and not match:
            near = _APPT_NUM_NEAR_RE.search(query)
            if near:
                raw = near.group(0).upper()
                if raw.startswith("ND-"):
                    raw = "R" + raw
                return {"appt_number": raw, "action": "reschedule"}
        return None

    def _should_extract(self, query: str, answer: str, keywords: set) -> bool:
        """Quick heuristic: only call the extractor when relevant signals are present."""
        combined = (query + " " + answer).lower()
        return any(kw in combined for kw in keywords)

    # ── Passive extraction (non-active-flow turns) ────────────────────────────

    async def _extract_data(
        self,
        query: str,
        history: Optional[List[ConversationTurn]],
        assistant_answer: str,
        fields: List[Dict[str, Any]],
        mode_tag: str,
        *,
        already_collected: Optional[Dict[str, Any]] = None,
        current_field_key: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Secondary focused LLM call for passive data extraction.

        Used only for non-active-mode turns where the user mentions
        appointment/order details in passing.
        """
        field_names = ", ".join(f["key"] for f in fields)

        options_lines = self._build_field_options_instruction(fields)
        if options_lines:
            options_block = (
                "Kısıtlı alanlar (sadece şu değerlerden birini kullan, yoksa null bırak):\n"
                + options_lines + "\n\n"
            )
        else:
            options_block = ""

        history_text = ""
        for turn in (history or [])[-6:]:
            role = turn.get("role", "user")
            content = (turn.get("content") or "").strip()
            if content:
                history_text += f"{role}: {content}\n"
        history_text += f"user: {query}\n"
        history_text += f"assistant: {assistant_answer}\n"

        _skip_keys = {"confirmed", "saved", "appointment_id", "order_id", "active_mode"}
        already_lines = ""
        if already_collected:
            filled = {
                k: v for k, v in already_collected.items()
                if v and k not in _skip_keys
            }
            if filled:
                already_lines = (
                    "Zaten kaydedilmiş bilgiler (bunları tekrar döndürme, sadece değişirse güncelle):\n"
                    + "\n".join(f"  {k}: {v}" for k, v in filled.items())
                    + "\n\n"
                )

        optional_keys = [f["key"] for f in fields if not f.get("required")]
        optional_instruction = ""
        if optional_keys:
            optional_instruction = (
                f"Opsiyonel alanlar: {', '.join(optional_keys)}\n"
                f"  • Kullanıcı 'yok', 'geç', 'istemiyorum' vb. ile reddetmişse "
                f"\"__skip__\" döndür.\n\n"
            )

        current_field_instruction = ""
        if current_field_key:
            current_field_label = current_field_key
            for f in fields:
                if f["key"] == current_field_key:
                    current_field_label = f.get("label", current_field_key)
                    break
            current_field_instruction = (
                f"ŞU AN TOPLANMAKTA OLAN ALAN: {current_field_key} ({current_field_label})\n"
                f"Kullanıcının son mesajı bu alan için bir yanıt içeriyor. "
                f"Öncelikle '{current_field_key}' alanını çıkar.\n\n"
            )

        validation_lines = []
        for f in fields:
            val_type = f.get("validation")
            key = f.get("key", "")
            if not val_type or val_type == "text":
                continue
            hints = {
                "phone": "Türk telefon numarası — sadece rakam, 05XX ile başlamalı",
                "email": "Geçerli e-posta adresi — @ içermeli",
                "date": "Tarih — GG Ay YYYY formatında yaz (örn: 15 Mart 2026)",
                "time": "Saat — SS:DD formatında yaz (örn: 14:30)",
                "number": "Sayısal değer — sadece rakam",
            }
            hint = hints.get(val_type, "")
            if hint:
                validation_lines.append(f"  - {key}: {hint}")
        validation_block = ""
        if validation_lines:
            validation_block = (
                "Doğrulama kuralları:\n" + "\n".join(validation_lines) + "\n\n"
            )

        if current_field_key:
            _cur_is_optional = any(
                f.get("key") == current_field_key and not f.get("required")
                for f in fields
            )
            _skip_bullet = (
                f"- '{current_field_key}' opsiyonelse ve kullanıcı 'geç/yok/istemiyorum' "
                f"diyorsa __skip__ döndür.\n"
                if _cur_is_optional else ""
            )
            thinking_guide = (
                f"Önce <thinking> içinde düşün:\n"
                f"- ŞU AN SORULAN: '{current_field_key}'. Son user mesajında değer var mı?\n"
                f"{_skip_bullet}"
                f"- Zaten kaydedilmiş alanları tekrar döndürme.\n"
                f"<thinking>[reasoning]</thinking>\n\n"
            )
        else:
            thinking_guide = (
                f"Önce <thinking> içinde düşün:\n"
                f"- Son user mesajında hangi alanlar geçiyor?\n"
                f"- Zaten kaydedilmiş alanları tekrar döndürme.\n"
                f"<thinking>[reasoning]</thinking>\n\n"
            )

        dt_ctx = self._build_datetime_context()
        extraction_prompt = (
            f"{dt_ctx}\n\n"
            f"{current_field_instruction}"
            f"Konuşmada geçen {mode_tag} bilgilerini çıkar.\n"
            f"{thinking_guide}"
            f"Ardından SADECE JSON veya null yaz:\n"
            f"Çıkarılacak alanlar: {field_names}\n"
            f"{options_block}"
            f"{validation_block}"
            f"{optional_instruction}"
            f"{already_lines}"
            f"ÖNEMLİ — Tarih: 'yarın', 'bu Cuma' gibi göreceli ifadeleri zaman bilgisine göre çevir "
            f"(GG Ay YYYY formatı).\n"
            f"ÖNEMLİ — Saat: 'akşam 6' → '18:00', 'sabah 10' → '10:00'.\n"
            f"ÖNEMLİ — Sayı: 'tek/bir' → '1', 'iki' → '2', 'üç' → '3'.\n"
            f"Onay varsa 'confirmed: true' ekle.\n\n"
            f"KURALLAR:\n"
            f"  1. SADECE son 'user:' mesajındaki bilgiyi çıkar.\n"
            f"  2. Yeni bilgi yoksa null döndür.\n"
            f"  3. JSON'a null değer ekleme.\n\n"
            f"Konuşma:\n{history_text}\n"
            f"JSON veya null:"
        )

        # Fast-path: optional field skip
        if current_field_key:
            _fp_opt = next((f for f in fields if f.get("key") == current_field_key), None)
            if _fp_opt and not _fp_opt.get("required"):
                if query.strip().lower() in _SKIP_WORDS:
                    logger.info(
                        "CharacterHandler: fast-path skip %s (optional)",
                        current_field_key,
                    )
                    return {current_field_key: "__skip__"}

        # Fast-path: typed field validation
        if current_field_key:
            _fp_field = next((f for f in fields if f.get("key") == current_field_key), None)
            if _fp_field:
                _fp_val = _fp_field.get("validation")
                if _fp_val and _fp_val not in ("text", None):
                    _fp_ok, _fp_norm = self._validate_field_value(query.strip(), _fp_val)
                    if _fp_ok and _fp_norm:
                        logger.info(
                            "CharacterHandler: fast-path extraction %s=%r",
                            current_field_key, _fp_norm,
                        )
                        result = {current_field_key: _fp_norm}
                        result = self._filter_invisible_fields(result, fields, already_collected or {})
                        return result if result else None

        try:
            timeout = min(self._timeout_seconds or 15, 15)
            raw = await asyncio.wait_for(
                self._llm.complete(extraction_prompt),
                timeout=timeout,
            )
            parsed = self._parse_json(raw)
            if parsed and fields:
                parsed = self._normalize_extraction_to_options(parsed, fields)
                parsed = self._validate_extracted(parsed, fields)
                parsed = self._filter_invisible_fields(parsed, fields, already_collected or {})
            return parsed if parsed else None
        except (asyncio.TimeoutError, Exception) as exc:
            logger.warning("CharacterHandler: passive extraction failed (%s): %s", mode_tag, exc)
            return None

    # ── Static helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _build_field_options_instruction(fields: List[Dict[str, Any]]) -> str:
        lines = []
        for f in fields:
            opts = f.get("options")
            if isinstance(opts, (list, tuple)) and len(opts) > 0:
                key = f.get("key", "")
                values = " | ".join(str(v).strip() for v in opts if v is not None and str(v).strip())
                if values:
                    lines.append(f"  - {key}: sadece şunlardan biri: {values}")
        return "\n".join(lines) if lines else ""

    @staticmethod
    def _normalize_extraction_to_options(
        parsed: Dict[str, Any],
        fields: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Map extracted values to closest allowed option (exact → case-insensitive → substring)."""
        result = dict(parsed)
        for f in fields:
            opts = f.get("options")
            if not isinstance(opts, (list, tuple)) or not opts:
                continue
            key = f.get("key")
            if not key or key not in result:
                continue
            val = result.get(key)
            if val is None or (isinstance(val, str) and not val.strip()):
                continue
            val_str = str(val).strip()
            allowed = [str(o).strip() for o in opts if o is not None and str(o).strip()]
            if not allowed or val_str in allowed:
                continue
            low = val_str.lower()
            matched = False
            for a in allowed:
                if a.lower() == low:
                    result[key] = a
                    matched = True
                    break
            if not matched:
                for a in allowed:
                    if low in a.lower() or a.lower() in low:
                        result[key] = a
                        matched = True
                        break
            if not matched:
                result.pop(key, None)
                logger.info("CharacterHandler: dropped %s=%r (not in options)", key, val_str)
        return result

    @staticmethod
    def _validate_field_value(value: str, validation: str) -> Tuple[bool, Optional[str]]:
        """Check value against declared validation type. Returns (is_valid, normalised)."""
        v = value.strip()
        if not v:
            return False, None

        if validation == "phone":
            digits = re.sub(r"[\s\-\(\)\.]+", "", v)
            if re.fullmatch(r"0[0-9]{9,10}", digits):
                return True, digits
            if re.fullmatch(r"[0-9]{10}", digits):
                return True, "0" + digits[0:] if not digits.startswith("0") else digits
            return False, None

        if validation == "email":
            if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", v):
                return True, v.lower()
            return False, None

        if validation == "date":
            for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
                try:
                    datetime.datetime.strptime(v, fmt)
                    return True, v
                except ValueError:
                    pass
            _TR_MONTHS = {
                "ocak": 1, "şubat": 2, "mart": 3, "nisan": 4, "mayıs": 5, "haziran": 6,
                "temmuz": 7, "ağustos": 8, "eylül": 9, "ekim": 10, "kasım": 11, "aralık": 12,
            }
            parts = v.lower().split()
            if len(parts) == 3:
                try:
                    day = int(parts[0])
                    month = _TR_MONTHS.get(parts[1])
                    year = int(parts[2])
                    if month and 1 <= day <= 31 and 2000 <= year <= 2100:
                        return True, v
                except (ValueError, TypeError):
                    pass
            return False, None

        if validation == "time":
            if re.fullmatch(r"([01]?[0-9]|2[0-3]):[0-5][0-9]", v):
                return True, v
            return False, None

        if validation == "number":
            _TR_NUMS: Dict[str, str] = {
                "sıfır": "0", "yok": "0", "hayır": "0", "hiç": "0",
                "bir": "1", "tek": "1", "yalnız": "1", "yalnızca": "1",
                "sadece ben": "1", "sadece siz": "1", "sadece biz": "1",
                "iki": "2", "çift": "2",
                "üç": "3", "dört": "4", "beş": "5", "altı": "6",
                "yedi": "7", "sekiz": "8", "dokuz": "9", "on": "10",
            }
            v_lower = v.lower().strip()
            if v_lower in _TR_NUMS:
                return True, _TR_NUMS[v_lower]
            cleaned = re.sub(r"[,\s]", "", v)
            try:
                float(cleaned)
                return True, cleaned
            except ValueError:
                return False, None

        return True, v  # "text" or unknown — always valid

    @staticmethod
    def _validate_extracted(
        parsed: Dict[str, Any],
        fields: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Run format validation on each extracted field, dropping invalid values."""
        result = dict(parsed)
        field_map = {f["key"]: f for f in fields}

        for key, value in list(result.items()):
            if not isinstance(value, str):
                continue
            field = field_map.get(key)
            if field is None:
                continue
            validation = field.get("validation")
            if not validation or validation == "text":
                continue
            ok, normalised = CharacterHandler._validate_field_value(value, validation)
            if ok:
                if normalised is not None:
                    result[key] = normalised
            else:
                result.pop(key)
                logger.info(
                    "CharacterHandler: dropped %s=%r (failed %s validation)",
                    key, value, validation,
                )

        return result

    @staticmethod
    def _filter_invisible_fields(
        parsed: Dict[str, Any],
        fields: List[Dict[str, Any]],
        already_collected: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Remove extracted values for fields whose show_if condition is not satisfied."""
        from backend.orchestrator.mode_engine import field_is_visible

        merged = {**already_collected, **parsed}
        result = {}
        field_map = {f["key"]: f for f in fields}
        for key, value in parsed.items():
            field = field_map.get(key)
            if field is None:
                result[key] = value
                continue
            if field_is_visible(field, merged):
                result[key] = value
            else:
                logger.info(
                    "CharacterHandler: dropped %s=%r (show_if condition not met)", key, value
                )
        return result

    @staticmethod
    def _parse_json(raw: str) -> Optional[Dict[str, Any]]:
        """Parse JSON from extraction response, tolerating markdown fences and CoT tags."""
        text = raw.strip()
        text = re.sub(r"<thinking>.*?</thinking>", "", text, flags=re.DOTALL).strip()
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        text = text.strip()
        if text.lower() in ("null", "none", ""):
            return None
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict) and parsed:
                cleaned = {
                    k: v for k, v in parsed.items()
                    if v is not None
                    and not (isinstance(v, str) and v.strip().lower() in ("null", "none", ""))
                }
                return cleaned if cleaned else None
        except (json.JSONDecodeError, ValueError):
            match = re.search(r"\{[^{}]+\}", text, re.DOTALL)
            if match:
                try:
                    parsed = json.loads(match.group())
                    if isinstance(parsed, dict) and parsed:
                        return parsed
                except (json.JSONDecodeError, ValueError):
                    pass
            logger.warning("CharacterHandler: extraction parse failed: %r", raw[:200])
        return None

    def _build_messages(
        self,
        query: str,
        history: Optional[List[ConversationTurn]],
        *,
        mode_context: Optional[str] = None,
        flow_section: Optional[str] = None,
    ) -> list:
        dt_ctx = self._build_datetime_context()

        if flow_section:
            # Active flow mode: character prompt + datetime + comprehensive flow section
            system_content = (
                f"{dt_ctx}\n\n"
                f"{self._system_prompt}\n\n"
                f"{flow_section}"
            )
        elif mode_context:
            # Non-flow mode with context (e.g., RANDEVU KAYITLI block)
            system_content = (
                f"{mode_context}\n\n"
                f"─── KARAKTERİN ───\n{dt_ctx}\n\n{self._system_prompt}"
            )
        else:
            system_content = f"{dt_ctx}\n\n{self._system_prompt}"

        messages: list = [{"role": "system", "content": system_content}]
        for turn in (history or []):
            role = turn.get("role", "user")
            content = (turn.get("content") or "").strip()
            if content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": query})
        return messages

    @staticmethod
    def _build_datetime_context() -> str:
        """Return a Turkish-language current date/time block for the system prompt."""
        _DAYS_FULL = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
        _MONTHS_FULL = [
            "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
            "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",
        ]
        tz_name = os.environ.get("BOT_TIMEZONE", "Europe/Istanbul")
        try:
            from zoneinfo import ZoneInfo
            now = datetime.datetime.now(ZoneInfo(tz_name))
        except Exception:
            now = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=3)

        day_name = _DAYS_FULL[now.weekday()]
        month_name = _MONTHS_FULL[now.month - 1]
        tomorrow = now + datetime.timedelta(days=1)
        tomorrow_str = f"{tomorrow.day} {_MONTHS_FULL[tomorrow.month - 1]} {tomorrow.year}"

        monday = now - datetime.timedelta(days=now.weekday())
        week_parts = []
        for i in range(7):
            d = monday + datetime.timedelta(days=i)
            week_parts.append(f"{_DAYS_FULL[i]}: {d.day} {_MONTHS_FULL[d.month - 1]} {d.year}")

        return (
            "--- [GÜNCEL ZAMAN BİLGİSİ] ---\n"
            f"Bugün: {day_name}, {now.day} {month_name} {now.year} | Saat: {now.strftime('%H:%M')} (Türkiye / UTC+3)\n"
            f"Yarın: {tomorrow_str}\n"
            f"Bu hafta: {' | '.join(week_parts)}\n"
            "--- [/GÜNCEL ZAMAN BİLGİSİ] ---"
        )

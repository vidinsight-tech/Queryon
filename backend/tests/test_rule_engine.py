"""
Unit tests for RuleEngine: keyword/regex match, safe template rendering,
and multi-step flow matching.
"""
from __future__ import annotations

import unittest
from types import SimpleNamespace
from uuid import uuid4

from backend.orchestrator.rules.engine import FlowContext, RuleEngine


def _make_rule(
    name: str = "Test",
    trigger_patterns: list[str] | None = None,
    response_template: str = "Cevap",
    variables: dict | None = None,
    priority: int = 0,
    is_active: bool = True,
    description: str = "",
    flow_id: str | None = None,
    step_key: str | None = None,
    required_step: str | None = None,
    next_steps: dict | None = None,
) -> SimpleNamespace:
    """Minimal rule-like object for testing (no DB)."""
    ns = SimpleNamespace(
        id=uuid4(),
        name=name,
        description=description,
        trigger_patterns=trigger_patterns or [],
        response_template=response_template,
        variables=variables or {},
        priority=priority,
        is_active=is_active,
        flow_id=flow_id,
        step_key=step_key,
        required_step=required_step,
        next_steps=next_steps,
    )
    ns.is_flow_rule = flow_id is not None
    return ns


class TestRuleEngineMatch(unittest.TestCase):
    def test_keyword_match(self) -> None:
        r = _make_rule(
            name="Randevu",
            trigger_patterns=["randevu"],
            response_template="Randevu saatlerimiz: {hours}",
            variables={"hours": "09:00-17:00"},
        )
        engine = RuleEngine([r])
        result = engine.match("Randevu almak istiyorum")
        self.assertIsNotNone(result)
        self.assertEqual(result.rule.name, "Randevu")
        self.assertIn("09:00-17:00", result.rendered_answer)

    def test_no_match(self) -> None:
        r = _make_rule(trigger_patterns=["randevu"])
        engine = RuleEngine([r])
        self.assertIsNone(engine.match("Merhaba nasılsın"))

    def test_priority_order(self) -> None:
        low = _make_rule(name="Low", trigger_patterns=["saat"], priority=0)
        high = _make_rule(name="High", trigger_patterns=["saat"], priority=10)
        engine = RuleEngine([low, high])
        result = engine.match("Çalışma saati nedir")
        self.assertIsNotNone(result)
        self.assertEqual(result.rule.name, "High")

    def test_inactive_rule_skipped(self) -> None:
        r = _make_rule(trigger_patterns=["test"], is_active=False)
        engine = RuleEngine([r])
        self.assertIsNone(engine.match("test query"))

    def test_regex_pattern(self) -> None:
        r = _make_rule(
            name="Regex",
            trigger_patterns=[r"r:\b(randevu|appointment)\b"],
            response_template="Eşleşti",
        )
        engine = RuleEngine([r])
        result = engine.match("I want an appointment")
        self.assertIsNotNone(result)
        self.assertEqual(result.rule.name, "Regex")
        self.assertEqual(result.rendered_answer, "Eşleşti")


class TestRuleEngineRender(unittest.TestCase):
    """Safe template rendering: only {identifier} from variables, no format injection."""

    def test_simple_substitution(self) -> None:
        r = _make_rule(
            response_template="Saatler: {hours}. {extra}",
            variables={"hours": "09:00", "extra": "Pazartesi-Cuma"},
        )
        engine = RuleEngine([r])
        out = engine._render(r)  # type: ignore[arg-type]
        self.assertEqual(out, "Saatler: 09:00. Pazartesi-Cuma")

    def test_missing_variable_left_unchanged(self) -> None:
        r = _make_rule(
            response_template="Saat: {hours} ve {missing}",
            variables={"hours": "09:00"},
        )
        engine = RuleEngine([r])
        out = engine._render(r)  # type: ignore[arg-type]
        self.assertIn("09:00", out)
        self.assertIn("{missing}", out)

    def test_format_injection_not_executed(self) -> None:
        """Placeholders like {0.__class__} must not be evaluated."""
        r = _make_rule(
            response_template="Normal {x} and dangerous {0.__class__}",
            variables={"x": "value"},
        )
        engine = RuleEngine([r])
        out = engine._render(r)  # type: ignore[arg-type]
        self.assertIn("value", out)
        self.assertIn("{0.__class__}", out)

    def test_empty_variables_returns_template(self) -> None:
        r = _make_rule(response_template="No vars here")
        engine = RuleEngine([r])
        out = engine._render(r)  # type: ignore[arg-type]
        self.assertEqual(out, "No vars here")


class TestRuleEngineKeywords(unittest.TestCase):
    def test_keywords_excludes_regex(self) -> None:
        r = _make_rule(trigger_patterns=["randevu", "r:\\d+"])
        engine = RuleEngine([r])
        kws = engine.keywords
        self.assertIn("randevu", kws)
        self.assertNotIn("r:\\d+", kws)


class TestFlowContext(unittest.TestCase):
    def test_inactive_by_default(self) -> None:
        ctx = FlowContext()
        self.assertFalse(ctx.active)
        self.assertIsNone(ctx.to_dict())

    def test_active(self) -> None:
        ctx = FlowContext(flow_id="randevu", current_step="start")
        self.assertTrue(ctx.active)
        d = ctx.to_dict()
        self.assertEqual(d["flow_id"], "randevu")
        self.assertEqual(d["current_step"], "start")

    def test_roundtrip(self) -> None:
        original = FlowContext(
            flow_id="x", current_step="s1",
            data={"k": "v"}, selections={"start": "düğün"},
        )
        restored = FlowContext.from_dict(original.to_dict())
        self.assertEqual(restored.flow_id, "x")
        self.assertEqual(restored.current_step, "s1")
        self.assertEqual(restored.data, {"k": "v"})
        self.assertEqual(restored.selections, {"start": "düğün"})

    def test_from_none(self) -> None:
        ctx = FlowContext.from_dict(None)
        self.assertFalse(ctx.active)


class TestRuleEngineFlowMatch(unittest.TestCase):
    """Multi-step flow matching tests."""

    def _build_hizmet_flow(self):
        entry = _make_rule(
            name="Hizmet Giriş",
            trigger_patterns=["hizmet"],
            response_template="Ne hizmet istersiniz? A) Danışmanlık B) Eğitim",
            flow_id="hizmet",
            step_key="start",
            next_steps={"A": "danismanlik", "B": "egitim"},
        )
        step_a = _make_rule(
            name="Danışmanlık",
            trigger_patterns=["danışmanlık"],
            response_template="Danışmanlık hizmeti seçildi. Hangi alan? X) Hukuk Y) Finans",
            flow_id="hizmet",
            step_key="danismanlik",
            required_step="start",
            next_steps={"X": "hukuk", "Y": "finans"},
        )
        step_b = _make_rule(
            name="Eğitim",
            trigger_patterns=["eğitim"],
            response_template="Eğitim hizmeti seçildi.",
            flow_id="hizmet",
            step_key="egitim",
            required_step="start",
        )
        step_ax = _make_rule(
            name="Hukuk",
            trigger_patterns=["hukuk"],
            response_template="Hukuk danışmanlık başlatıldı.",
            flow_id="hizmet",
            step_key="hukuk",
            required_step="danismanlik",
        )
        standalone = _make_rule(
            name="Merhaba",
            trigger_patterns=["merhaba"],
            response_template="Merhaba!",
        )
        return [entry, step_a, step_b, step_ax, standalone]

    def test_entry_point_match(self) -> None:
        rules = self._build_hizmet_flow()
        engine = RuleEngine(rules)
        result = engine.match("hizmet almak istiyorum")
        self.assertIsNotNone(result)
        self.assertEqual(result.rule.name, "Hizmet Giriş")
        self.assertIsNotNone(result.next_flow_context)
        self.assertEqual(result.next_flow_context.flow_id, "hizmet")
        self.assertEqual(result.next_flow_context.current_step, "start")

    def test_step_match_via_choice(self) -> None:
        rules = self._build_hizmet_flow()
        engine = RuleEngine(rules)
        ctx = FlowContext(flow_id="hizmet", current_step="start")
        result = engine.match("A", flow_ctx=ctx)
        self.assertIsNotNone(result)
        self.assertEqual(result.rule.name, "Danışmanlık")

    def test_nested_step_match(self) -> None:
        rules = self._build_hizmet_flow()
        engine = RuleEngine(rules)
        ctx = FlowContext(flow_id="hizmet", current_step="danismanlik")
        result = engine.match("X", flow_ctx=ctx)
        self.assertIsNotNone(result)
        self.assertEqual(result.rule.name, "Hukuk")
        self.assertIn("Hukuk danışmanlık", result.rendered_answer)

    def test_terminal_step_clears_flow(self) -> None:
        rules = self._build_hizmet_flow()
        engine = RuleEngine(rules)
        ctx = FlowContext(flow_id="hizmet", current_step="start")
        result = engine.match("B", flow_ctx=ctx)
        self.assertIsNotNone(result)
        self.assertEqual(result.rule.name, "Eğitim")
        self.assertIsNone(result.next_flow_context)

    def test_standalone_accessible_inside_flow(self) -> None:
        rules = self._build_hizmet_flow()
        engine = RuleEngine(rules)
        ctx = FlowContext(flow_id="hizmet", current_step="start")
        result = engine.match("merhaba", flow_ctx=ctx)
        self.assertIsNotNone(result)
        self.assertEqual(result.rule.name, "Merhaba")
        self.assertIsNone(result.next_flow_context)

    def test_flow_rule_not_matched_without_flow_ctx(self) -> None:
        step = _make_rule(
            name="Step",
            trigger_patterns=["devam"],
            response_template="Devam",
            flow_id="f1",
            step_key="s2",
            required_step="s1",
        )
        engine = RuleEngine([step])
        result = engine.match("devam")
        self.assertIsNone(result)

    def test_wrong_step_no_match(self) -> None:
        step = _make_rule(
            name="Step",
            trigger_patterns=["devam"],
            response_template="Devam",
            flow_id="f1",
            step_key="s2",
            required_step="s1",
        )
        engine = RuleEngine([step])
        ctx = FlowContext(flow_id="f1", current_step="wrong")
        result = engine.match("devam", flow_ctx=ctx)
        self.assertIsNone(result)


class TestWildcardPattern(unittest.TestCase):
    """Wildcard `*` in trigger_patterns and next_steps."""

    def test_wildcard_trigger_matches_anything(self) -> None:
        rule = _make_rule(
            name="CatchAll",
            trigger_patterns=["*"],
            response_template="Tarihiniz alındı.",
            flow_id="f1",
            step_key="tarih_al",
            required_step="start",
        )
        engine = RuleEngine([rule])
        ctx = FlowContext(flow_id="f1", current_step="start")
        result = engine.match("15 Haziran 2026", flow_ctx=ctx)
        self.assertIsNotNone(result)
        self.assertEqual(result.rule.name, "CatchAll")

    def test_wildcard_next_steps_fallback(self) -> None:
        entry = _make_rule(
            name="TarihSor",
            trigger_patterns=["tarih"],
            response_template="Tarihiniz nedir?",
            flow_id="f2",
            step_key="tarih_sor",
            next_steps={"*": "fiyat_goster"},
        )
        fiyat = _make_rule(
            name="Fiyat",
            trigger_patterns=["*"],
            response_template="İzel: 20.000₺",
            flow_id="f2",
            step_key="fiyat_goster",
            required_step="tarih_sor",
            next_steps={"*": "randevu"},
        )
        engine = RuleEngine([entry, fiyat])
        ctx = FlowContext(flow_id="f2", current_step="tarih_sor")
        result = engine.match("23 Ağustos", flow_ctx=ctx)
        self.assertIsNotNone(result)
        self.assertEqual(result.rule.name, "Fiyat")
        self.assertIn("20.000", result.rendered_answer)

    def test_specific_choice_takes_priority_over_wildcard(self) -> None:
        parent = _make_rule(
            name="KınaSor",
            trigger_patterns=["kına"],
            response_template="Düğün ile birlikte mi?",
            flow_id="f3",
            step_key="kina_sor",
            next_steps={"evet": "kina_dugun", "hayır": "kina_tek", "*": "kina_tek"},
        )
        combo = _make_rule(
            name="KınaDüğün",
            trigger_patterns=["*"],
            response_template="Kına+Düğün: 22.000₺",
            flow_id="f3",
            step_key="kina_dugun",
            required_step="kina_sor",
        )
        tek = _make_rule(
            name="KınaTek",
            trigger_patterns=["*"],
            response_template="Kına tek: 13.000₺",
            flow_id="f3",
            step_key="kina_tek",
            required_step="kina_sor",
        )
        engine = RuleEngine([parent, combo, tek])
        ctx = FlowContext(flow_id="f3", current_step="kina_sor")

        result_evet = engine.match("evet", flow_ctx=ctx)
        self.assertEqual(result_evet.rule.name, "KınaDüğün")

        result_hayir = engine.match("hayır", flow_ctx=ctx)
        self.assertEqual(result_hayir.rule.name, "KınaTek")

        result_random = engine.match("bilmiyorum", flow_ctx=ctx)
        self.assertEqual(result_random.rule.name, "KınaTek")


class TestSelectionsTracking(unittest.TestCase):
    """Verify that user choices are recorded in FlowContext.selections."""

    def test_selections_recorded_on_choice(self) -> None:
        entry = _make_rule(
            name="Start",
            trigger_patterns=["merhaba"],
            response_template="A veya B?",
            flow_id="sel",
            step_key="start",
            next_steps={"A": "step_a"},
        )
        step_a = _make_rule(
            name="StepA",
            trigger_patterns=["*"],
            response_template="Tarih?",
            flow_id="sel",
            step_key="step_a",
            required_step="start",
            next_steps={"*": "done"},
        )
        done = _make_rule(
            name="Done",
            trigger_patterns=["*"],
            response_template="Tamam.",
            flow_id="sel",
            step_key="done",
            required_step="step_a",
        )
        engine = RuleEngine([entry, step_a, done])

        r1 = engine.match("merhaba")
        self.assertEqual(r1.rule.name, "Start")
        ctx1 = r1.next_flow_context
        self.assertIsNotNone(ctx1)

        r2 = engine.match("A", flow_ctx=ctx1)
        self.assertEqual(r2.rule.name, "StepA")
        ctx2 = r2.next_flow_context
        self.assertIn("start", ctx2.selections)
        self.assertEqual(ctx2.selections["start"], "A")

        r3 = engine.match("15 Haziran", flow_ctx=ctx2)
        self.assertEqual(r3.rule.name, "Done")
        self.assertIsNone(r3.next_flow_context)


class TestMakeupHouseScenario(unittest.TestCase):
    """End-to-end test simulating the real makeup house flow."""

    def _build_makeup_flow(self):
        karsilama = _make_rule(
            name="Karşılama",
            trigger_patterns=["merhaba", "selam", "bilgi", "fiyat", "makyaj"],
            response_template=(
                "İzellik Makeup House'a hoş geldiniz!\n"
                "1) Düğün Saç Makyaj\n2) Kına Saç Makyaj\n3) Nişan Saç Makyaj"
            ),
            flow_id="hizmet_akisi",
            step_key="start",
            next_steps={
                "düğün": "tarih_sor_dugun",
                "1": "tarih_sor_dugun",
                "kına": "tarih_sor_kina",
                "2": "tarih_sor_kina",
                "nişan": "tarih_sor_nisan",
                "3": "tarih_sor_nisan",
            },
            priority=10,
        )
        tarih_dugun = _make_rule(
            name="TarihSorDüğün",
            trigger_patterns=["düğün", "1"],
            response_template="Düğün tarihiniz nedir?",
            flow_id="hizmet_akisi",
            step_key="tarih_sor_dugun",
            required_step="start",
            next_steps={"*": "fiyat_dugun"},
        )
        tarih_kina = _make_rule(
            name="TarihSorKına",
            trigger_patterns=["kına", "2"],
            response_template="Kına tarihiniz nedir? Düğün ile birlikte mi?",
            flow_id="hizmet_akisi",
            step_key="tarih_sor_kina",
            required_step="start",
            next_steps={"evet": "fiyat_kina_dugun", "hayır": "fiyat_kina", "*": "fiyat_kina"},
        )
        tarih_nisan = _make_rule(
            name="TarihSorNişan",
            trigger_patterns=["nişan", "3"],
            response_template="Nişan tarihiniz nedir?",
            flow_id="hizmet_akisi",
            step_key="tarih_sor_nisan",
            required_step="start",
            next_steps={"*": "fiyat_nisan"},
        )
        fiyat_dugun = _make_rule(
            name="FiyatDüğün",
            trigger_patterns=["*"],
            response_template="İzel: 20.000₺ | Merve: 13.000₺ | Dicle: 13.000₺",
            flow_id="hizmet_akisi",
            step_key="fiyat_dugun",
            required_step="tarih_sor_dugun",
            next_steps={"*": "randevu"},
        )
        fiyat_nisan = _make_rule(
            name="FiyatNişan",
            trigger_patterns=["*"],
            response_template="İzel: 15.000₺ | Merve: 10.000₺",
            flow_id="hizmet_akisi",
            step_key="fiyat_nisan",
            required_step="tarih_sor_nisan",
        )
        fiyat_kina = _make_rule(
            name="FiyatKına",
            trigger_patterns=["*"],
            response_template="İzel: 20.000₺ | Merve: 13.000₺",
            flow_id="hizmet_akisi",
            step_key="fiyat_kina",
            required_step="tarih_sor_kina",
        )
        fiyat_kina_dugun = _make_rule(
            name="FiyatKınaDüğün",
            trigger_patterns=["*"],
            response_template="İzel: 40.000₺ | Merve: 22.000₺",
            flow_id="hizmet_akisi",
            step_key="fiyat_kina_dugun",
            required_step="tarih_sor_kina",
        )
        randevu = _make_rule(
            name="Randevu",
            trigger_patterns=["*"],
            response_template="Randevunuz oluşturuldu.",
            flow_id="hizmet_akisi",
            step_key="randevu",
            required_step="fiyat_dugun",
        )
        nedime = _make_rule(
            name="NedimeFiyat",
            trigger_patterns=["nedime", "ek kişi", "yanımdaki"],
            response_template="Nedime: 5.000₺",
        )
        istanbul = _make_rule(
            name="İstanbul",
            trigger_patterns=["istanbul"],
            response_template="İstanbul: 0540 272 3434",
        )
        return [
            karsilama, tarih_dugun, tarih_kina, tarih_nisan,
            fiyat_dugun, fiyat_nisan, fiyat_kina, fiyat_kina_dugun,
            randevu, nedime, istanbul,
        ]

    def test_full_dugun_flow(self) -> None:
        """Merhaba → düğün → tarih → fiyat → artist → randevu."""
        engine = RuleEngine(self._build_makeup_flow())

        r1 = engine.match("Merhaba bilgi almak istiyorum")
        self.assertEqual(r1.rule.name, "Karşılama")
        ctx = r1.next_flow_context
        self.assertEqual(ctx.current_step, "start")

        r2 = engine.match("düğün saç makyaj", flow_ctx=ctx)
        self.assertEqual(r2.rule.name, "TarihSorDüğün")
        ctx = r2.next_flow_context
        self.assertEqual(ctx.current_step, "tarih_sor_dugun")
        self.assertEqual(ctx.selections.get("start"), "düğün saç makyaj")

        r3 = engine.match("15 Haziran 2026", flow_ctx=ctx)
        self.assertEqual(r3.rule.name, "FiyatDüğün")
        self.assertIn("20.000", r3.rendered_answer)
        ctx = r3.next_flow_context
        self.assertEqual(ctx.selections.get("tarih_sor_dugun"), "15 Haziran 2026")

        r4 = engine.match("Merve ile devam edelim", flow_ctx=ctx)
        self.assertEqual(r4.rule.name, "Randevu")
        self.assertIsNone(r4.next_flow_context)

    def test_nisan_flow_terminal(self) -> None:
        """Nişan akışı: merhaba → nişan → tarih → fiyat (akış biter)."""
        engine = RuleEngine(self._build_makeup_flow())

        r1 = engine.match("fiyat bilgisi")
        ctx = r1.next_flow_context

        r2 = engine.match("nişan", flow_ctx=ctx)
        self.assertEqual(r2.rule.name, "TarihSorNişan")
        ctx = r2.next_flow_context

        r3 = engine.match("20 Temmuz", flow_ctx=ctx)
        self.assertEqual(r3.rule.name, "FiyatNişan")
        self.assertIn("15.000", r3.rendered_answer)
        self.assertIsNone(r3.next_flow_context)

    def test_kina_with_dugun_combo(self) -> None:
        """Kına + düğün combo: kına → evet → combo fiyat."""
        engine = RuleEngine(self._build_makeup_flow())

        r1 = engine.match("merhaba")
        ctx = r1.next_flow_context

        r2 = engine.match("kına", flow_ctx=ctx)
        self.assertEqual(r2.rule.name, "TarihSorKına")
        ctx = r2.next_flow_context

        r3 = engine.match("evet düğün ile birlikte", flow_ctx=ctx)
        self.assertEqual(r3.rule.name, "FiyatKınaDüğün")
        self.assertIn("40.000", r3.rendered_answer)

    def test_standalone_works_inside_flow(self) -> None:
        """Akış ortasında 'nedime fiyatı' sorusu standalone rule'dan cevaplanır."""
        engine = RuleEngine(self._build_makeup_flow())

        r1 = engine.match("merhaba")
        ctx = r1.next_flow_context

        r2 = engine.match("nedime fiyatı ne kadar", flow_ctx=ctx)
        self.assertEqual(r2.rule.name, "NedimeFiyat")
        self.assertIn("5.000", r2.rendered_answer)
        self.assertIsNone(r2.next_flow_context)

    def test_standalone_without_flow(self) -> None:
        """Flow olmadan Istanbul yönlendirme kuralı çalışır."""
        engine = RuleEngine(self._build_makeup_flow())
        result = engine.match("istanbul şubesi var mı")
        self.assertEqual(result.rule.name, "İstanbul")

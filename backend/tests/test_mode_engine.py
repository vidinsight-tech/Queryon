"""Tests for the pure-function mode engine."""
import pytest
from backend.orchestrator.mode_engine import (
    SKIP_SENTINEL,
    all_fields_handled,
    build_mode_context,
    compute_mode_context,
    field_is_visible,
    get_next_field,
    get_next_optional_field,
    is_complete,
)

FIELDS = [
    {"key": "name", "label": "Ad", "question": "Adınız nedir?", "required": True},
    {"key": "phone", "label": "Telefon", "question": "Telefon numaranız?", "required": True},
    {"key": "notes", "label": "Notlar", "question": "Notlarınız?", "required": False},
]

FIELDS_ALL_REQUIRED = [
    {"key": "name", "label": "Ad", "question": "Adınız nedir?", "required": True},
    {"key": "phone", "label": "Telefon", "question": "Telefon numaranız?", "required": True},
]


class TestIsComplete:
    def test_empty_collected_not_complete(self):
        assert is_complete(FIELDS, {}) is False

    def test_partial_not_complete(self):
        assert is_complete(FIELDS, {"name": "Ali"}) is False

    def test_all_required_complete(self):
        assert is_complete(FIELDS, {"name": "Ali", "phone": "555"}) is True

    def test_optional_missing_still_complete(self):
        assert is_complete(FIELDS, {"name": "Ali", "phone": "555"}) is True

    def test_empty_fields_always_complete(self):
        assert is_complete([], {}) is True


class TestAllFieldsHandled:
    def test_optional_not_handled(self):
        assert all_fields_handled(FIELDS, {"name": "Ali", "phone": "555"}) is False

    def test_optional_skipped(self):
        assert all_fields_handled(FIELDS, {"name": "Ali", "phone": "555", "notes": SKIP_SENTINEL}) is True

    def test_optional_filled(self):
        assert all_fields_handled(FIELDS, {"name": "Ali", "phone": "555", "notes": "ek bilgi"}) is True

    def test_all_required_only(self):
        assert all_fields_handled(FIELDS_ALL_REQUIRED, {"name": "Ali", "phone": "555"}) is True


class TestGetNextField:
    def test_returns_first_missing_required(self):
        nxt = get_next_field(FIELDS, {})
        assert nxt is not None
        assert nxt["key"] == "name"

    def test_skips_already_collected(self):
        nxt = get_next_field(FIELDS, {"name": "Ali"})
        assert nxt is not None
        assert nxt["key"] == "phone"

    def test_returns_none_when_all_required_collected(self):
        nxt = get_next_field(FIELDS, {"name": "Ali", "phone": "555"})
        assert nxt is None


class TestGetNextOptionalField:
    def test_returns_first_optional(self):
        nxt = get_next_optional_field(FIELDS, {"name": "Ali", "phone": "555"})
        assert nxt is not None
        assert nxt["key"] == "notes"

    def test_returns_none_when_filled(self):
        nxt = get_next_optional_field(FIELDS, {"name": "Ali", "phone": "555", "notes": "merhaba"})
        assert nxt is None

    def test_returns_none_when_skipped(self):
        nxt = get_next_optional_field(FIELDS, {"name": "Ali", "phone": "555", "notes": SKIP_SENTINEL})
        assert nxt is None


class TestBuildModeContext:
    def test_saved_state(self):
        ctx = build_mode_context("appointment", FIELDS, {}, confirmed=True, saved=True)
        assert "Kaydedildi" in ctx

    def test_confirmed_not_saved(self):
        ctx = build_mode_context("appointment", FIELDS, {"name": "Ali", "phone": "555", "notes": SKIP_SENTINEL}, confirmed=True, saved=False)
        assert "onaylandı" in ctx.lower() or "kaydediliyor" in ctx.lower()

    def test_all_required_filled_asks_optional(self):
        """When required fields are done but optional remains, ask the optional field."""
        ctx = build_mode_context("appointment", FIELDS, {"name": "Ali", "phone": "555"}, confirmed=False, saved=False)
        assert "Notlarınız?" in ctx
        assert "Opsiyonel" in ctx

    def test_all_fields_handled_asks_confirmation(self):
        """When all fields (required+optional) are handled, show summary."""
        ctx = build_mode_context("appointment", FIELDS, {"name": "Ali", "phone": "555", "notes": SKIP_SENTINEL}, confirmed=False, saved=False)
        assert "onaylıyor musunuz" in ctx.lower() or "doğru mu" in ctx.lower()
        assert "Ali" in ctx

    def test_skipped_optional_not_in_summary(self):
        """Skipped optional fields should not appear in the summary."""
        ctx = build_mode_context("appointment", FIELDS, {"name": "Ali", "phone": "555", "notes": SKIP_SENTINEL}, confirmed=False, saved=False)
        assert SKIP_SENTINEL not in ctx
        assert "Notlar" not in ctx

    def test_filled_optional_in_summary(self):
        """Filled optional fields should appear in the summary."""
        ctx = build_mode_context("appointment", FIELDS, {"name": "Ali", "phone": "555", "notes": "Alerjim var"}, confirmed=False, saved=False)
        assert "Alerjim var" in ctx

    def test_no_optional_fields_shows_confirmation_after_required(self):
        """When there are no optional fields, go directly to confirmation after required."""
        ctx = build_mode_context("appointment", FIELDS_ALL_REQUIRED, {"name": "Ali", "phone": "555"}, confirmed=False, saved=False)
        assert "onaylıyor musunuz" in ctx.lower() or "doğru mu" in ctx.lower()

    def test_next_field_question(self):
        ctx = build_mode_context("appointment", FIELDS, {}, confirmed=False, saved=False)
        assert "Adınız nedir?" in ctx

    def test_markers_present(self):
        ctx = build_mode_context("appointment", FIELDS, {}, confirmed=False, saved=False)
        assert "--- [MODE CONTEXT] ---" in ctx
        assert "--- [/MODE CONTEXT] ---" in ctx


class TestComputeModeContext:
    def test_no_fields_configured_returns_none(self):
        cfg = {"appointment_fields": [], "order_mode_enabled": False, "order_fields": []}
        mode, ctx = compute_mode_context(cfg, {})
        assert mode is None
        assert ctx is None

    def test_appointment_not_activated_when_no_state(self):
        cfg = {
            "appointment_fields": FIELDS,
            "order_mode_enabled": False,
            "order_fields": [],
        }
        mode, ctx = compute_mode_context(cfg, {})
        assert mode is None

    def test_appointment_activated_when_stored(self):
        cfg = {
            "appointment_fields": FIELDS,
            "order_mode_enabled": False,
            "order_fields": [],
        }
        mode, ctx = compute_mode_context(cfg, {"active_mode": "appointment"})
        assert mode == "appointment"
        assert ctx is not None

    def test_appointment_not_reactivated_when_saved(self):
        cfg = {
            "appointment_fields": FIELDS,
            "order_mode_enabled": False,
            "order_fields": [],
        }
        flow = {"active_mode": "appointment", "appointment": {"name": "Ali", "saved": True}}
        mode, ctx = compute_mode_context(cfg, flow)
        assert mode is None

    def test_order_mode(self):
        cfg = {
            "appointment_fields": [],
            "order_mode_enabled": True,
            "order_fields": FIELDS,
        }
        mode, ctx = compute_mode_context(cfg, {"active_mode": "order"})
        assert mode == "order"
        assert ctx is not None

    def test_order_not_activated_when_disabled(self):
        cfg = {
            "appointment_fields": [],
            "order_mode_enabled": False,
            "order_fields": FIELDS,
        }
        mode, ctx = compute_mode_context(cfg, {"active_mode": "order"})
        assert mode is None


# ── show_if / conditional field fixtures ──────────────────────────────────────

# Scenario: wedding makeup booking
# - name (required, always visible)
# - location: Studio / Away / Home  (required, always visible, with options)
# - city (required, only visible when location == "Şehir Dışı")
# - notes (optional, always visible)
FIELDS_CONDITIONAL = [
    {"key": "name", "label": "Ad", "question": "Adınız nedir?", "required": True},
    {
        "key": "location",
        "label": "Hazırlık Yeri",
        "question": "Hazırlık nerede yapılacak?",
        "required": True,
        "options": ["Stüdyo", "Şehir Dışı", "Ev"],
    },
    {
        "key": "city",
        "label": "Şehir",
        "question": "Hangi şehirde?",
        "required": True,
        "show_if": {"field": "location", "value": ["Şehir Dışı"]},
    },
    {"key": "notes", "label": "Notlar", "question": "Notlarınız?", "required": False},
]


class TestFieldIsVisible:
    def test_no_show_if_always_visible(self):
        assert field_is_visible(FIELDS_CONDITIONAL[0], {}) is True

    def test_conditional_invisible_when_dep_not_collected(self):
        city_field = FIELDS_CONDITIONAL[2]
        assert field_is_visible(city_field, {}) is False
        assert field_is_visible(city_field, {"name": "Ali"}) is False

    def test_conditional_invisible_when_dep_is_wrong_value(self):
        city_field = FIELDS_CONDITIONAL[2]
        assert field_is_visible(city_field, {"location": "Stüdyo"}) is False
        assert field_is_visible(city_field, {"location": "Ev"}) is False

    def test_conditional_visible_when_dep_matches(self):
        city_field = FIELDS_CONDITIONAL[2]
        assert field_is_visible(city_field, {"location": "Şehir Dışı"}) is True

    def test_conditional_string_value_normalised(self):
        """show_if.value as bare string (not list) should still work."""
        field = {
            "key": "city",
            "label": "Şehir",
            "required": True,
            "show_if": {"field": "location", "value": "Şehir Dışı"},
        }
        assert field_is_visible(field, {"location": "Şehir Dışı"}) is True
        assert field_is_visible(field, {"location": "Stüdyo"}) is False

    def test_dep_skip_sentinel_treated_as_not_collected(self):
        city_field = FIELDS_CONDITIONAL[2]
        assert field_is_visible(city_field, {"location": SKIP_SENTINEL}) is False


class TestIsCompleteConditional:
    def test_city_not_required_when_invisible(self):
        # location = Stüdyo → city never asked → collection is complete
        assert is_complete(FIELDS_CONDITIONAL, {"name": "Ali", "location": "Stüdyo"}) is True

    def test_city_required_when_visible(self):
        # location = Şehir Dışı → city becomes required
        assert is_complete(FIELDS_CONDITIONAL, {"name": "Ali", "location": "Şehir Dışı"}) is False

    def test_complete_with_city_filled(self):
        collected = {"name": "Ali", "location": "Şehir Dışı", "city": "İstanbul"}
        assert is_complete(FIELDS_CONDITIONAL, collected) is True

    def test_empty_collected_not_complete(self):
        assert is_complete(FIELDS_CONDITIONAL, {}) is False


class TestGetNextFieldConditional:
    def test_city_skipped_when_invisible(self):
        # After name + location=Stüdyo, city is invisible → no more required fields
        nxt = get_next_field(FIELDS_CONDITIONAL, {"name": "Ali", "location": "Stüdyo"})
        assert nxt is None

    def test_city_returned_when_visible(self):
        # After name + location=Şehir Dışı, city should be next
        nxt = get_next_field(FIELDS_CONDITIONAL, {"name": "Ali", "location": "Şehir Dışı"})
        assert nxt is not None
        assert nxt["key"] == "city"

    def test_location_before_city(self):
        # location itself must be collected first
        nxt = get_next_field(FIELDS_CONDITIONAL, {"name": "Ali"})
        assert nxt is not None
        assert nxt["key"] == "location"


class TestAllFieldsHandledConditional:
    def test_invisible_city_not_counted(self):
        # With location=Stüdyo, city is invisible — only name, location, notes matter
        assert all_fields_handled(FIELDS_CONDITIONAL, {"name": "Ali", "location": "Stüdyo"}) is False
        assert all_fields_handled(
            FIELDS_CONDITIONAL,
            {"name": "Ali", "location": "Stüdyo", "notes": SKIP_SENTINEL},
        ) is True

    def test_visible_city_must_be_handled(self):
        # With location=Şehir Dışı, city is visible and must be filled
        assert all_fields_handled(
            FIELDS_CONDITIONAL,
            {"name": "Ali", "location": "Şehir Dışı", "notes": SKIP_SENTINEL},
        ) is False
        assert all_fields_handled(
            FIELDS_CONDITIONAL,
            {"name": "Ali", "location": "Şehir Dışı", "city": "İstanbul", "notes": SKIP_SENTINEL},
        ) is True


class TestBuildModeContextConditional:
    def test_city_question_shown_when_visible(self):
        ctx = build_mode_context(
            "appointment",
            FIELDS_CONDITIONAL,
            {"name": "Ali", "location": "Şehir Dışı"},
            confirmed=False,
            saved=False,
        )
        assert "Hangi şehirde?" in ctx

    def test_city_not_in_remaining_when_invisible(self):
        ctx = build_mode_context(
            "appointment",
            FIELDS_CONDITIONAL,
            {"name": "Ali", "location": "Stüdyo"},
            confirmed=False,
            saved=False,
        )
        # No required field remains — should ask for notes (optional) or show summary
        assert "Hangi şehirde?" not in ctx

    def test_conditional_hint_in_remaining_list(self):
        # When city is a remaining visible required field, its show_if hint should appear
        ctx = build_mode_context(
            "appointment",
            FIELDS_CONDITIONAL,
            {"name": "Ali", "location": "Şehir Dışı"},
            confirmed=False,
            saved=False,
        )
        # The remaining-required line should mention the condition
        assert "Şehir" in ctx

    def test_summary_excludes_invisible_city(self):
        # If somehow city was collected but is now invisible, it should not appear in summary
        ctx = build_mode_context(
            "appointment",
            FIELDS_CONDITIONAL,
            {
                "name": "Ali",
                "location": "Stüdyo",
                "city": "İstanbul",  # invisible — location changed to Stüdyo
                "notes": SKIP_SENTINEL,
            },
            confirmed=False,
            saved=False,
        )
        # Summary should NOT contain İstanbul because city is invisible
        assert "İstanbul" not in ctx

    def test_summary_includes_visible_city(self):
        ctx = build_mode_context(
            "appointment",
            FIELDS_CONDITIONAL,
            {
                "name": "Ali",
                "location": "Şehir Dışı",
                "city": "İstanbul",
                "notes": SKIP_SENTINEL,
            },
            confirmed=False,
            saved=False,
        )
        assert "İstanbul" in ctx

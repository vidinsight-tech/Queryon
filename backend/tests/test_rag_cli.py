"""
RAG CLI menü ve I/O testleri.

Çalıştırma:
  python -m pytest backend/tests/test_rag_cli.py -v
  python -m unittest backend.tests.test_rag_cli -v
"""
from __future__ import annotations

import unittest

from backend.scripts.rag_cli import (
    MAIN_ITEMS,
    _reset_io,
    _set_io,
    _show_menu,
)


class TestRagCliMenu(unittest.TestCase):
    def tearDown(self) -> None:
        _reset_io()

    def test_show_menu_returns_user_choice(self) -> None:
        """Menü gösterilir ve kullanıcı girişi döner."""
        choices = ["3", "0", "99"]
        it = iter(choices)
        _set_io(input_fn=lambda p: next(it, "0"), print_fn=lambda s: None)

        r = _show_menu("Test Menü", ["1) A", "2) B", "0) Çıkış"])
        self.assertEqual(r, "3")

        r = _show_menu("Alt Menü", ["0) Geri"])
        self.assertEqual(r, "0")

        r = _show_menu("Son", [])
        self.assertEqual(r, "99")

    def test_show_menu_displays_title_and_items(self) -> None:
        """Menü çıktısında başlık ve seçenekler görünür."""
        out: list[str] = []
        _set_io(input_fn=lambda p: "0", print_fn=out.append)
        _show_menu("Queryon RAG CLI", MAIN_ITEMS)
        text = "\n".join(out)
        self.assertIn("Queryon RAG CLI", text)
        self.assertIn("LLM Yönetimi", text)
        self.assertIn("RAG Sohbet", text)
        self.assertIn("0) Çıkış", text)

    def test_show_menu_has_box_style(self) -> None:
        """Menü kutu karakterleri ile çizilir."""
        out: list[str] = []
        _set_io(input_fn=lambda p: "0", print_fn=out.append)
        _show_menu("Başlık", ["1) Seçenek", "0) Geri"])
        text = "\n".join(out)
        self.assertIn("╭", text)
        self.assertIn("╮", text)
        self.assertIn("╰", text)
        self.assertIn("╯", text)
        self.assertIn("Başlık", text)
        self.assertIn("1) Seçenek", text)


if __name__ == "__main__":
    unittest.main()

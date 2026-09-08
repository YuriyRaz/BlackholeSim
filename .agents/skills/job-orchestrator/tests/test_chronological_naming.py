from __future__ import annotations

import re
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT / "scripts"))

from orchestrator_core import (  # noqa: E402
    chronological_run_id,
    slugify,
)


class SlugifyTest(unittest.TestCase):
    def test_normal_text(self) -> None:
        self.assertEqual(slugify("Investigate the Auth System"), "investigate-the-auth-system")

    def test_special_characters(self) -> None:
        self.assertEqual(slugify("Fix login bug!!"), "fix-login-bug")

    def test_colons_and_slashes(self) -> None:
        self.assertEqual(slugify("API: add /users endpoint"), "api-add-users-endpoint")

    def test_empty_string(self) -> None:
        self.assertEqual(slugify(""), "run")

    def test_whitespace_only(self) -> None:
        self.assertEqual(slugify("   "), "run")

    def test_only_special_chars(self) -> None:
        self.assertEqual(slugify("!@#$%"), "run")

    def test_long_string_truncated(self) -> None:
        result = slugify("a" * 100)
        self.assertEqual(len(result), 50)
        self.assertEqual(result, "a" * 50)

    def test_leading_trailing_hyphens_trimmed(self) -> None:
        self.assertEqual(slugify("--hello--"), "hello")

    def test_consecutive_special_chars(self) -> None:
        self.assertEqual(slugify("hello   world"), "hello-world")

    def test_already_slugified(self) -> None:
        self.assertEqual(slugify("already-a-slug"), "already-a-slug")

    def test_mixed_case(self) -> None:
        self.assertEqual(slugify("Hello World"), "hello-world")

    def test_numbers_preserved(self) -> None:
        self.assertEqual(slugify("task 123 done"), "task-123-done")

    def test_underscores_replaced(self) -> None:
        self.assertEqual(slugify("some_thing"), "some-thing")

    def test_unicode_characters_replaced(self) -> None:
        self.assertEqual(slugify("Café 東京"), "caf")


class ChronologicalRunIdTest(unittest.TestCase):
    def test_format(self) -> None:
        result = chronological_run_id("Investigate the Auth System")
        # Should match: YYYY-MM-DDTHHMMSSZ-<slug>
        self.assertTrue(
            re.match(r"\d{4}-\d{2}-\d{2}T\d{6}Z-[a-z0-9-]+", result),
            f"Format mismatch: {result}",
        )

    def test_with_name_override(self) -> None:
        result = chronological_run_id("some goal", name="my-custom-name")
        self.assertTrue(result.endswith("-my-custom-name"), f"Name override failed: {result}")

    def test_explicit_empty_name_uses_run_fallback(self) -> None:
        with patch(
            "orchestrator_core.utc_now",
            return_value="2026-07-29T12:34:56.000000Z",
        ):
            result = chronological_run_id("goal-must-not-be-used", name="")

        self.assertEqual(result, "2026-07-29T123456Z-run")

    def test_with_empty_goal(self) -> None:
        result = chronological_run_id("")
        self.assertTrue(
            re.match(r"\d{4}-\d{2}-\d{2}T\d{6}Z-run", result),
            f"Empty goal fallback failed: {result}",
        )

    def test_sortability(self) -> None:
        with patch(
            "orchestrator_core.utc_now",
            side_effect=[
                "2026-07-20T14:30:12.000000Z",
                "2026-07-21T09:00:00.000000Z",
            ],
        ):
            earlier = chronological_run_id("same goal")
            later = chronological_run_id("same goal")

        self.assertEqual(earlier, "2026-07-20T143012Z-same-goal")
        self.assertEqual(later, "2026-07-21T090000Z-same-goal")
        self.assertLess(earlier, later)

    def test_run_id_matches_folder_name(self) -> None:
        # The run_id IS the folder name, so it must be filesystem-safe
        result = chronological_run_id("Fix the auth bug!")
        # No special chars that are illegal in Windows/Unix paths
        illegal = '<>:"/\\|?*'
        for char in illegal:
            self.assertNotIn(char, result, f"Illegal char {char!r} in run ID: {result}")


if __name__ == "__main__":
    unittest.main()

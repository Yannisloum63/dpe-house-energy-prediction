"""Vérifier les réponses paginées sans accès réseau."""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import extract_dpe as script


class PaginationTests(unittest.TestCase):
    def fetch(self, pages, max_rows=0):
        session = MagicMock()
        payloads = [{"schema": [{"key": c} for c in script.COLUMNS]}] + pages
        responses = []
        for payload in payloads:
            response = MagicMock()
            response.json.return_value = payload
            responses.append(response)
        session.get.side_effect = responses
        session.__enter__.return_value = session
        with patch.object(script.requests, "Session", return_value=session):
            return script.fetch_all("test", max_rows=max_rows)

    def pages(self, total=3):
        return [
            {"total": total, "results": [{"numero_dpe": "1"}],
             "next": script.API_URL + "?after=1"},
            {"results": [{"numero_dpe": "2"}],
             "next": script.API_URL + "?after=2"},
            {"results": [{"numero_dpe": "3"}]},
        ]

    def test_total_only_on_first_page(self):
        data = self.fetch(self.pages())
        self.assertEqual(data.numero_dpe.tolist(), ["1", "2", "3"])
        self.assertEqual(data.attrs["source_total"], 3)

    def test_limited_download_without_later_total(self):
        data = self.fetch(self.pages(), max_rows=2)
        self.assertEqual(len(data), 2)
        self.assertEqual(data.attrs["source_total"], 3)

    def test_changed_total_still_rejected(self):
        pages = self.pages()
        pages[1]["total"] = 4
        with self.assertRaisesRegex(ValueError, "volume source"):
            self.fetch(pages)

    def test_missing_or_invalid_first_total_rejected(self):
        for value in [None, -1, "3", True]:
            with self.subTest(total=value), self.assertRaisesRegex(ValueError, "total absent ou invalide"):
                self.fetch(self.pages(total=value))
        pages = self.pages()
        del pages[0]["total"]
        with self.assertRaisesRegex(ValueError, "total absent ou invalide"):
            self.fetch(pages)

    def test_incomplete_download_still_rejected(self):
        with self.assertRaisesRegex(ValueError, "incomplète"):
            self.fetch(self.pages(total=4))

    def test_empty_dataset(self):
        data = self.fetch([{"total": 0, "results": []}])
        self.assertTrue(data.empty)
        self.assertEqual(data.attrs["source_total"], 0)


if __name__ == "__main__":
    unittest.main()

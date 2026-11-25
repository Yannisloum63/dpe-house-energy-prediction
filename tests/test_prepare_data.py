"""Contrôles de préparation, de regroupement et de séparation."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import prepare_data as prep
from extract_dpe import FEATURE_COLUMNS


def sample():
    rows = []
    for label in "ABCDEFG":
        for building in range(20):
            for diagnosis in range(2):
                row = dict.fromkeys(FEATURE_COLUMNS, "inconnue")
                row.update(numero_dpe=f"{label}{building:02}_{diagnosis}",
                           id_rnb=f"R{label}{building}", numero_dpe_remplace=pd.NA,
                           etiquette_dpe=label, conso_5_usages_par_m2_ep=200.0,
                           surface_habitable_logement=90.0, hauteur_sous_plafond=2.5,
                           nombre_niveau_logement=2.0, isolation_toiture=1.0)
                rows.append(row)
    return pd.DataFrame(rows)


class PreparationTests(unittest.TestCase):
    def test_mask_without_deleting_or_changing_targets(self):
        raw = sample()
        raw.loc[0, "hauteur_sous_plafond"] = 282
        raw.loc[1, "nombre_niveau_logement"] = 184
        raw.loc[2, "surface_habitable_logement"] = 3771
        raw.loc[3, prep.TARGET_REG] = 2128.2
        before = raw.copy(deep=True)
        clean, changes = prep.prepare_inputs(raw, FEATURE_COLUMNS)
        self.assertEqual(len(clean), len(raw))
        self.assertTrue(pd.isna(clean.loc[0, "hauteur_sous_plafond"]))
        self.assertTrue(pd.isna(clean.loc[1, "nombre_niveau_logement"]))
        self.assertEqual(clean.loc[2, "surface_habitable_logement"], 3771)
        self.assertEqual(len(changes), 2)
        pd.testing.assert_frame_equal(raw, before)
        pd.testing.assert_frame_equal(clean[[prep.TARGET_REG, prep.TARGET_CLF]], raw[[prep.TARGET_REG, prep.TARGET_CLF]])

    def test_missing_and_invalid_values(self):
        raw = sample()
        raw.loc[0, "hauteur_sous_plafond"] = np.nan
        raw.loc[1, "hauteur_sous_plafond"] = np.inf
        raw.loc[2, "nombre_niveau_logement"] = 1.5
        raw.loc[3, "isolation_toiture"] = 2
        clean, changes = prep.prepare_inputs(raw, FEATURE_COLUMNS)
        self.assertEqual(len(changes), 3)
        self.assertTrue(clean.loc[0:1, "hauteur_sous_plafond"].isna().all())
        self.assertTrue(pd.isna(clean.loc[2, "nombre_niveau_logement"]))
        self.assertTrue(pd.isna(clean.loc[3, "isolation_toiture"]))

    def test_transitive_links_and_unknown_buildings(self):
        raw = pd.DataFrame({"numero_dpe": ["a", "b", "c", "d", "e", "f"],
                            "id_rnb": ["R1", "R1", None, None, None, None],
                            "numero_dpe_remplace": [None, "c", None, None, "old", "old"]})
        groups = prep.building_groups(raw)
        self.assertEqual(groups[0], groups[2])
        self.assertNotEqual(groups[3], groups[2])
        self.assertNotEqual(groups[3], groups[4])
        self.assertEqual(groups[4], groups[5])

    def test_reproducible_after_row_shuffle(self):
        raw = sample()
        first = prep.make_assignments(raw)
        second = prep.make_assignments(raw.sample(frac=1, random_state=9))
        pd.testing.assert_frame_equal(first, second)
        self.assertEqual(first.groupby("group_id").split.nunique().max(), 1)
        self.assertEqual(len(first), len(raw))

    def test_bad_assignments_rejected(self):
        raw = sample()
        assignments = prep.make_assignments(raw)
        with self.assertRaisesRegex(ValueError, "exactement"):
            prep.validate_assignments(raw, assignments.iloc[:-1])
        broken = assignments.copy()
        broken.loc[0, "split"] = "test" if broken.loc[0, "split"] != "test" else "train"
        with self.assertRaisesRegex(ValueError, "traverse"):
            prep.validate_assignments(raw, broken)

    def test_no_target_as_input(self):
        features = FEATURE_COLUMNS.copy()
        features[0] = prep.TARGET_REG
        with self.assertRaisesRegex(ValueError, "Cible"):
            prep.prepare_inputs(sample(), features)

    def test_published_loader_requires_explicit_masking(self):
        root = Path(__file__).resolve().parents[1]
        def response(url, **kwargs):
            result = MagicMock()
            result.content = (root / url.removeprefix("https://example.test/")).read_bytes()
            return result
        with patch("requests.get", side_effect=response):
            raw, splits, features, changes, report = prep.load_shared_data("https://example.test")
            self.assertTrue(changes.empty)
            self.assertFalse(report["masking_applied"])
            joined = pd.concat(splits.values()).set_index("numero_dpe").sort_index()
            pd.testing.assert_frame_equal(joined[features], raw.set_index("numero_dpe").sort_index()[features])
            _, masked_splits, _, changes, report = prep.load_shared_data("https://example.test", apply_mask=True)
            self.assertEqual(len(changes), 24)
            self.assertTrue(report["masking_applied"])
            self.assertEqual(sum(len(d) for d in masked_splits.values()), 80000)


if __name__ == "__main__":
    unittest.main()

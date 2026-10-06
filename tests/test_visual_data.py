from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from visual_data import build_response, export_response_csv


class BuildResponseTests(unittest.TestCase):
    def test_numpy_arrays_are_copied_and_safe(self):
        grid = np.array([100.0, 1000.0, 10000.0])
        source = np.array([1.0, 2.0, 3.0])
        correction = {
            "grid_freqs": grid,
            "source_fr": source,
            "target_fr": np.array([2.0, 4.0, 6.0]),
            "peq_resp": np.array([0.5, 1.0, 1.5]),
        }

        response = build_response(correction)

        np.testing.assert_array_equal(response.freqs, grid)
        np.testing.assert_array_equal(response.source, source)
        np.testing.assert_array_equal(response.simulated, [1.5, 3.0, 4.5])
        np.testing.assert_array_equal(grid, [100.0, 1000.0, 10000.0])
        np.testing.assert_array_equal(source, [1.0, 2.0, 3.0])
        with self.assertRaises(ValueError):
            response.source[0] = 20.0

    def test_all_zero_measured_source_is_available(self):
        response = build_response({
            "grid_freqs": [100.0, 1000.0],
            "source_fr": np.zeros(2),
            "target_fr": np.array([1.0, 2.0]),
            "peq_resp": np.zeros(2),
        })

        self.assertTrue(response.source_available)
        np.testing.assert_array_equal(response.source, [0.0, 0.0])

    def test_fir_simulation_is_recalculated_and_ignores_stale_cache(self):
        response = build_response({
            "grid_freqs": np.array([100.0, 1000.0]),
            "source_fr": np.array([10.0, 10.0]),
            "target_fr": np.array([14.0, 15.0]),
            "peq_resp": np.array([1.0, 2.0]),
            "combined_resp": np.array([3.0, 4.0]),
            "simulated_curve": np.array([999.0, 999.0]),
            "use_fir": True,
        })

        self.assertTrue(response.use_fir)
        np.testing.assert_array_equal(response.filter_response, [3.0, 4.0])
        np.testing.assert_array_equal(response.simulated, [13.0, 14.0])

    def test_raw_target_restores_recorded_alignment_offset(self):
        correction = {
            "grid_freqs": [100.0, 1000.0],
            "source_fr": [0.0, 0.0],
            "target_fr": [1.25, -0.75],
            "level_offset_db": 2.5,
            "peq_resp": [0.0, 0.0],
        }

        aligned = build_response(correction)
        raw = build_response(correction, raw_target=True)

        np.testing.assert_allclose(aligned.target, [1.25, -0.75])
        np.testing.assert_allclose(raw.target, [3.75, 1.75])

    def test_residual_is_target_minus_simulation(self):
        response = build_response({
            "grid_freqs": [100.0, 1000.0],
            "source_fr": [1.0, 2.0],
            "target_fr": [4.0, 7.0],
            "peq_resp": [0.5, 1.5],
        })

        np.testing.assert_allclose(response.simulated, [1.5, 3.5])
        np.testing.assert_allclose(response.residual, [2.5, 3.5])
        np.testing.assert_allclose(response.before_residual, [3.0, 5.0])

    def test_grid_sorts_filters_invalid_values_and_keeps_first_duplicate(self):
        response = build_response({
            "grid_freqs": np.array([100.0, 50.0, 100.0, np.nan, 30000.0, 25.0]),
            "source_fr": np.array([10.0, 20.0, 30.0, 40.0, 50.0, 60.0]),
            "target_fr": np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0]),
            "peq_resp": np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6]),
        })

        np.testing.assert_array_equal(response.freqs, [25.0, 50.0, 100.0])
        # Sorted indices are [5, 1, 0]; the second 100 Hz entry is discarded.
        np.testing.assert_array_equal(response.source, [60.0, 20.0, 10.0])
        np.testing.assert_array_equal(response.target, [6.0, 2.0, 1.0])
        np.testing.assert_allclose(response.filter_response, [0.6, 0.2, 0.1])

    def test_metrics_keep_absent_values_distinct_from_zero(self):
        zero = build_response({
            "grid_freqs": [100.0],
            "source_fr": [0.0],
            "target_fr": [0.0],
            "peq_resp": [0.0],
            "peq_rmse": 0.0,
            "combined_rmse": 0,
            "fir_n_taps": 0,
        })
        absent = build_response({
            "grid_freqs": [100.0],
            "source_fr": [0.0],
            "target_fr": [0.0],
            "peq_resp": [0.0],
        })

        self.assertEqual(zero.iir_rmse, 0.0)
        self.assertEqual(zero.combined_rmse, 0.0)
        self.assertIsNone(zero.fir_taps)
        self.assertIsNone(absent.iir_rmse)
        self.assertIsNone(absent.combined_rmse)
        self.assertIsNone(absent.fir_taps)


class ExportTests(unittest.TestCase):
    def test_csv_exports_every_valid_grid_point_and_blanks_missing_measurement(self):
        correction = {
            "grid_freqs": np.array([200.0, 20.0, 100.0]),
            "source_fr": np.array([2.0, 0.0, np.nan]),
            "target_fr": np.array([3.0, 1.0, np.nan]),
            "peq_resp": np.zeros(3),
        }
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "response.csv"
            export_response_csv(output, correction)
            with output.open(encoding="utf-8-sig", newline="") as stream:
                rows = list(csv.reader(stream))

        self.assertEqual(len(rows), 4)  # header plus the full three-point grid
        self.assertEqual([row[0] for row in rows[1:]], ["20", "100", "200"])
        # The 100 Hz measurement is absent, while that frequency stays in the export.
        self.assertEqual(rows[2][1:4], ["", "", ""])
        self.assertEqual(rows[2][0], "100")


class CoreCalculationTests(unittest.TestCase):
    def test_calculate_correction_returns_aligned_measurements_on_full_grid(self):
        import cosplay as cp

        frequencies = (20.0, 1000.0, 20000.0)
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "source.csv"
            target_path = Path(directory) / "target.csv"
            source_path.write_text("".join(f"{freq},{0.0}\n" for freq in frequencies), encoding="utf-8")
            target_path.write_text("".join(f"{freq},{7.0}\n" for freq in frequencies), encoding="utf-8")
            with patch.object(cp, "localized_print"):
                result = cp.calculate_correction(source_path, target_path, fs=48000.0)

        self.assertEqual(len(result["grid_freqs"]), 512)
        self.assertAlmostEqual(result["level_offset_db"], 7.0, places=5)
        np.testing.assert_allclose(result["source_fr"], 0.0, atol=1e-9)
        np.testing.assert_allclose(result["target_fr"], 0.0, atol=1e-5)
        np.testing.assert_allclose(result["delta_aligned"], 0.0, atol=1e-5)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest
import time
from types import SimpleNamespace

import numpy as np

from sound_stage import FrequencyResponsePlot
from visual_data import build_response
from cosplay_gui import UI_STRINGS


class RecordingCanvas:
    """Small Canvas stand-in for retained-item geometry regression checks."""

    def __init__(self):
        self.items = {}
        self.next_id = 1

    def _create(self, kind, coords, options):
        item_id = self.next_id
        self.next_id += 1
        self.items[item_id] = {
            "kind": kind,
            "coords": tuple(coords),
            "options": dict(options),
            "tags": options.get("tags", ()),
        }
        return item_id

    def create_line(self, *coords, **options):
        return self._create("line", coords, options)

    def create_polygon(self, *coords, **options):
        return self._create("polygon", coords, options)

    def create_oval(self, *coords, **options):
        return self._create("oval", coords, options)

    def create_rectangle(self, *coords, **options):
        return self._create("rectangle", coords, options)

    def create_text(self, *coords, **options):
        return self._create("text", coords, options)

    def coords(self, item_id, *coords):
        if item_id in self.items:
            self.items[item_id]["coords"] = tuple(coords)

    def itemconfigure(self, item_id, **options):
        if item_id in self.items:
            self.items[item_id]["options"].update(options)

    def delete(self, item):
        if isinstance(item, int):
            self.items.pop(item, None)
            return
        for item_id, value in tuple(self.items.items()):
            if item == value["tags"] or item in value["tags"]:
                self.items.pop(item_id, None)


def sample_correction():
    freqs = np.geomspace(20.0, 20000.0, 512)
    source = 3.0 * np.sin(np.log(freqs))
    target = source + 2.0 * np.cos(np.log(freqs) * 1.2)
    filter_response = 1.5 * np.exp(-0.5 * (np.log(freqs / 1200.0) / 0.6) ** 2)
    bands = [
        {"filter_type": kind, "frequency": center, "gain": gain, "Q": 0.9}
        for kind, center, gain in (
            ("Lowshelf", 70.0, 2.0),
            ("Peaking", 220.0, -1.0),
            ("Peaking", 800.0, 1.0),
            ("Peaking", 1800.0, -2.0),
            ("Peaking", 4200.0, 2.5),
            ("Peaking", 7000.0, -1.5),
            ("Peaking", 9500.0, 1.0),
            ("Peaking", 12000.0, -1.0),
            ("Peaking", 15000.0, 1.2),
            ("Highshelf", 18000.0, -2.0),
        )
    ]
    return {
        "grid_freqs": freqs,
        "source_fr": source,
        "target_fr": target,
        "peq_resp": filter_response,
        "combined_resp": filter_response * 1.1,
        "peq": bands,
        "samplerate": 48000,
    }


class SoundStageGeometryTests(unittest.TestCase):
    def setUp(self):
        self.correction = sample_correction()
        self.plot = object.__new__(FrequencyResponsePlot)
        plot = self.plot
        plot.mode = "eq"
        plot._quality = "auto"
        plot._motion_enabled = True
        plot._transition = None
        plot._empty = False
        plot._selected_band = 4
        plot._node_items = {}
        plot._ribbon_items = {}
        plot._ribbon_rule_items = {}
        plot._lens_items = {}
        plot._coords = {}
        plot._residual_item = None
        plot._resid_strip_item = None
        plot._band_response_cache = {}
        plot._range_locked = True
        plot._locked_ranges = {}
        plot._base_range = (-20.0, 20.0)
        plot._layout = (1060, 500, 48, 18, 12, 54, 994, 414)
        plot.result_data = self.correction
        plot.response = build_response(self.correction)
        plot._display_data = plot._arrays_for_display(plot.response)
        plot._frame_data = plot._display_data
        plot.frame_stats = {"frame_ms": 0.0, "points": 0}
        plot.view_style = "membrane"
        plot.canvas = RecordingCanvas()
        plot._destroyed = False
        plot._animation_job = None
        plot._slow_frame = False
        plot.fonts = {"mono9": ("Menlo", 9), "ui11": ("Arial", 11)}
        plot._t_fn = None

    def test_log_axis_is_exact_and_clamped_series_stay_inside_plot(self):
        plot = self.plot
        g = plot._layout
        self.assertAlmostEqual(plot._x(20.0, g), 48.0)
        self.assertAlmostEqual(plot._x(20000.0, g), 1042.0)
        expected = 48 + 994 * np.log10(1000.0 / 20.0) / np.log10(20000.0 / 20.0)
        self.assertAlmostEqual(plot._x(1000.0, g), expected)
        plot._base_range = (-0.5, 0.5)
        points = plot._line_coords(
            plot._display_data["freqs"],
            plot._display_data["simulated"],
            np.arange(512),
            g,
        )
        self.assertTrue(all(g[4] <= points[i] <= g[4] + g[7] for i in range(1, len(points), 2)))
        self.assertTrue(plot._range_overflow())

    def test_shelf_filter_lens_uses_normalized_filter_type(self):
        plot = self.plot
        low = plot._individual_band_curve(0)
        high = plot._individual_band_curve(9)
        self.assertIsNotNone(low)
        self.assertIsNotNone(high)
        self.assertGreater(float(np.ptp(low)), 0.1)
        self.assertGreater(float(np.ptp(high)), 0.1)

    def test_locked_range_discloses_clipped_values(self):
        plot = self.plot
        plot._locked_ranges["eq"] = (-1.0, 1.0)
        plot._draw_grid(plot._layout)
        labels = [item["options"].get("text") for item in plot.canvas.items.values()]
        self.assertIn("Outside locked range · unlock to fit", labels)

    def test_retained_items_remain_bounded_and_static_render_stays_idle(self):
        plot = self.plot
        plot._draw_response(plot._layout)
        initial = len(plot.canvas.items)
        counts = []
        for _ in range(130):
            plot._draw_response(plot._layout, update=True)
            counts.append(len(plot.canvas.items))
        self.assertEqual(max(counts), min(counts))
        self.assertEqual(counts[-1], initial)
        self.assertIsNone(plot._animation_job)
        self.assertIsNone(plot._transition)
        self.assertEqual(len(plot._node_items), 10)
        self.assertTrue(plot._ribbon_items)
        budgets = {}
        for quality in ("low", "auto", "high"):
            plot._quality = quality
            budgets[quality] = len(plot._sample_indices(plot._display_data["freqs"], plot._layout[6]))
        self.assertLessEqual(budgets["low"], 96)
        self.assertLessEqual(budgets["auto"], 192)
        self.assertEqual(budgets["high"], 512)
        plot._quality = "auto"
        plot._transition = (0.0, 0.4, {}, {})
        plot._slow_frame = True
        self.assertEqual(len(plot._sample_indices(plot._display_data["freqs"], plot._layout[6])), 64)
        plot._transition = None
        plot._slow_frame = False

    def test_fifty_mode_quality_view_and_geometry_rebuilds_do_not_accumulate_items(self):
        plot = self.plot
        counts = {}
        for i in range(50):
            plot.mode = "comp" if i % 2 else "eq"
            plot.view_style = "flat" if i % 2 else "membrane"
            plot._quality = ("auto", "low", "high")[i % 3]
            plot.response = build_response(self.correction, mode=plot.mode)
            plot._display_data = plot._arrays_for_display(plot.response)
            plot._band_response_cache.clear()
            plot._layout = plot._geometry(920 if i % 2 else 1060, 240 if i % 2 else 500)
            plot.canvas.delete("curve")
            plot._coords = {}
            plot._node_items = {}
            plot._ribbon_items = {}
            plot._ribbon_rule_items = {}
            plot._lens_items = {}
            plot._residual_item = None
            plot._resid_strip_item = None
            plot._draw_response(plot._layout, update=True)
            counts.setdefault((plot.view_style, plot._quality), []).append(len(plot.canvas.items))
        for same_state_counts in counts.values():
            self.assertEqual(max(same_state_counts), min(same_state_counts))
        self.assertEqual(plot._animation_job, None)

    def test_filter_only_response_is_not_mislabeled_as_measurement(self):
        correction = sample_correction()
        correction.pop("source_fr")
        correction.pop("target_fr")
        response = build_response(correction)
        plot = self.plot
        plot.response = response
        plot.result_data = correction
        plot._display_data = plot._arrays_for_display(response)
        self.assertFalse(plot._display_data["source_available"])
        self.assertFalse(plot._display_data["target_available"])
        self.assertEqual(len(plot._display_data["simulated"]), 512)
        plot._draw_response(plot._layout)
        self.assertIn("sim-line", [item["options"].get("tags")[-1] for item in plot.canvas.items.values() if item["kind"] == "line"])

    def test_filter_only_hover_omits_unmeasured_source_and_target(self):
        correction = sample_correction()
        correction.pop("source_fr")
        correction.pop("target_fr")
        plot = self.plot
        plot.result_data = correction
        plot.response = build_response(correction)
        plot._display_data = plot._arrays_for_display(plot.response)
        plot._hover_freq = 997.25
        plot._draw_interaction(plot._layout)
        texts = [item["options"].get("text", "") for item in plot.canvas.items.values()
                 if item["kind"] == "text"]
        self.assertEqual(len(texts), 1)
        self.assertIn("SIM", texts[0])
        self.assertNotIn("SRC", texts[0])
        self.assertNotIn("TGT", texts[0])

    def test_clipped_nodes_and_click_hit_testing_share_position(self):
        plot = self.plot
        plot._base_range = (-0.5, 0.5)
        g = plot._layout
        plot._draw_band_nodes(g)
        for i, (outer, _inner) in plot._node_items.items():
            x, y, radius = plot._band_node_position(
                i, float(plot._display_data["bands"][i]["frequency"]), g)
            coords = plot.canvas.items[outer]["coords"]
            self.assertAlmostEqual(coords[0], x-radius)
            self.assertAlmostEqual(coords[1], y-radius)
            self.assertGreaterEqual(coords[1]+1e-6, g[4])
            self.assertLessEqual(coords[3]-1e-6, g[4]+g[7])
            selected = []
            plot.set_selected_band = selected.append
            plot.on_band_selected = selected.append
            plot._on_click(SimpleNamespace(x=x, y=y))
            self.assertEqual(selected[:1], [i])

    def test_membrane_polygons_reverse_complete_points_and_stay_ordered(self):
        plot = self.plot
        plot._draw_response(plot._layout)
        polygons = [item for item in plot.canvas.items.values()
                    if item["kind"] == "polygon" and item["options"].get("tags") == ("curve", "ribbon")]
        self.assertEqual(len(polygons), 3)
        for item in polygons:
            coords = item["coords"]
            half = len(coords) // 2
            self.assertEqual(half % 2, 0)
            front_x = coords[0:half:2]
            back_x = coords[half::2]
            self.assertTrue(all(a <= b for a, b in zip(front_x, front_x[1:])))
            self.assertTrue(all(a >= b for a, b in zip(back_x, back_x[1:])))
            self.assertAlmostEqual(front_x[0], back_x[-1])
            self.assertAlmostEqual(front_x[-1], back_x[0])

    def test_resampling_transition_supports_different_grid_sizes(self):
        old_freqs = np.geomspace(20.0, 20000.0, 257)
        new_freqs = np.geomspace(30.0, 18000.0, 401)
        old_values = 4.0 * np.log10(old_freqs / 100.0)
        old = {"freqs": old_freqs, "source": old_values, "target": old_values + 2,
               "simulated": old_values + 1, "residual": np.ones(257),
               "before_residual": np.zeros(257), "filter": np.zeros(257)}
        target = {"freqs": new_freqs, "source": np.zeros(401), "target": np.zeros(401),
                  "simulated": np.zeros(401), "residual": np.zeros(401),
                  "before_residual": np.zeros(401), "filter": np.zeros(401)}
        frame = FrequencyResponsePlot._resample_frame(old, target)
        self.assertEqual(len(frame["simulated"]), len(new_freqs))
        expected = np.interp(np.log(new_freqs), np.log(old_freqs), old_values + 1)
        np.testing.assert_allclose(frame["simulated"], expected)
        equal_sized_grid = np.geomspace(50.0, 12000.0, 257)
        same_count = FrequencyResponsePlot._resample_frame(
            old,
            {"freqs": equal_sized_grid, "source": np.zeros(257), "target": np.zeros(257),
             "simulated": np.zeros(257), "residual": np.zeros(257),
             "before_residual": np.zeros(257), "filter": np.zeros(257)},
        )
        np.testing.assert_allclose(
            same_count["simulated"],
            np.interp(np.log(equal_sized_grid), np.log(old_freqs), old_values + 1),
        )

    def test_rapid_grid_changes_start_from_the_last_visible_frame(self):
        plot = self.plot
        plot._schedule_redraw = lambda structural=False: None
        plot._ensure_animation = lambda: None
        plot._t_fn = lambda key: key
        plot._suppress_morph_once = False
        plot._animation_deadline = None
        plot._last_animation_tick = None
        plot._frame_data = dict(plot._display_data)
        plot._frame_data["simulated"] = np.full(512, 3.25)

        first = sample_correction()
        first["grid_freqs"] = np.geomspace(25.0, 18000.0, 333)
        plot.set_data(first)
        self.assertEqual(len(plot._transition[2]["freqs"]), 333)
        np.testing.assert_allclose(plot._transition[2]["simulated"], 3.25)

        second = sample_correction()
        second["grid_freqs"] = np.geomspace(40.0, 16000.0, 181)
        plot.set_data(second)
        self.assertEqual(len(plot._transition[2]["freqs"]), 181)
        self.assertEqual(len(plot._transition[3]["freqs"]), 181)
        self.assertEqual(plot._transition[0] > 0, True)

    def test_resize_and_mode_switch_keep_the_current_grid_and_frame_coherent(self):
        plot = self.plot
        plot._schedule_redraw = lambda structural=False: None
        plot._ensure_animation = lambda: None
        plot._update_mode_label = lambda: None
        plot._t_fn = lambda key: key
        plot._suppress_morph_once = False
        first = sample_correction()
        first["grid_freqs"] = np.geomspace(35.0, 17000.0, 287)
        plot.set_data(first)
        resized = plot._geometry(920, 330)
        plot._layout = resized
        plot._draw_response(resized, update=True)
        self.assertEqual(len(plot._frame_data["freqs"]), 287)

        second = sample_correction()
        second["grid_freqs"] = np.geomspace(45.0, 15000.0, 193)
        plot.set_data(second)
        self.assertEqual(len(plot._transition[2]["freqs"]), 193)
        plot._draw_response(resized, update=True)
        np.testing.assert_array_equal(plot._frame_data["freqs"], plot._display_data["freqs"])

        plot.set_mode("comp")
        self.assertIsNone(plot._transition)
        self.assertEqual(plot.response.mode, "comp")
        np.testing.assert_array_equal(plot._frame_data["freqs"], plot._display_data["freqs"])
        self.assertEqual(len(plot._line_coords(plot._frame_data["freqs"],
                                               plot._frame_data["simulated"],
                                               np.arange(193), resized)), 386)

    def test_nodes_and_hover_readout_follow_the_interpolated_frame(self):
        plot = self.plot
        plot._ensure_animation = lambda: None
        target = dict(plot._display_data)
        before = dict(target)
        before["simulated"] = np.full_like(target["simulated"], -4.0)
        target["simulated"] = np.full_like(target["simulated"], 8.0)
        before["source"] = np.zeros_like(target["source"])
        target["source"] = np.full_like(target["source"], 6.0)
        plot._display_data = target
        plot._transition = (time.monotonic() - .21, .42, before, target)
        plot._draw_response(plot._layout)
        np.testing.assert_allclose(plot._frame_data["simulated"], 2.0, atol=.1)
        freq = float(plot._display_data["bands"][4]["frequency"])
        _x, y, radius = plot._band_node_position(4, freq, plot._layout)
        expected_y = plot._clip_y(plot._y(2.0, plot._layout), plot._layout)
        expected_y = max(plot._layout[4]+radius,
                         min(plot._layout[4]+plot._layout[7]-radius, expected_y))
        self.assertAlmostEqual(y, expected_y, delta=.02)
        plot._hover_freq = 1000.0
        plot._draw_interaction(plot._layout)
        texts = [item["options"].get("text", "") for item in plot.canvas.items.values()
                 if item["kind"] == "text" and "SIM" in item["options"].get("text", "")]
        self.assertTrue(texts)
        self.assertIn("SIM +2.00", texts[-1])

    def test_control_labels_use_translation_keys_and_reflect_state(self):
        plot = self.plot
        labels = {}
        class LabelStub:
            def __init__(self, key):
                self.key = key
            def configure(self, **kwargs):
                labels[self.key] = kwargs["text"]
        plot.btn_view = LabelStub("view")
        plot.btn_lock = LabelStub("lock")
        plot.btn_toggle_mode = LabelStub("mode")
        control_keys = ("plot_control_membrane", "plot_control_flat", "plot_control_locked",
                        "plot_control_auto", "plot_control_response", "plot_control_compensation")
        for language in ("zh", "en", "ja"):
            strings = UI_STRINGS[language]
            self.assertTrue(all(key in strings for key in control_keys))
            plot._t_fn = strings.__getitem__
            plot.view_style = "membrane"
            plot._range_locked = True
            plot.mode = "eq"
            plot._sync_controls()
            self.assertEqual(labels["view"], strings["plot_control_membrane"] + "  ✓")
            self.assertEqual(labels["lock"], strings["plot_control_locked"])
            self.assertEqual(labels["mode"], strings["plot_control_response"] + "  /  " +
                             strings["plot_control_compensation"] + "  ↗")
            plot.view_style = "flat"
            plot._range_locked = False
            plot.mode = "comp"
            plot._sync_controls()
            self.assertEqual(labels["view"], strings["plot_control_flat"] + "  ✓")
            self.assertEqual(labels["lock"], strings["plot_control_auto"])
            self.assertEqual(labels["mode"], strings["plot_control_compensation"] + "  /  " +
                             strings["plot_control_response"] + "  ↗")


if __name__ == "__main__":
    unittest.main()

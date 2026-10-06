from __future__ import annotations

import tempfile
import os
import sys
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

import cosplay as cp
import cosplay_gui as gui


@unittest.skipIf(
    sys.platform == "darwin" and not os.environ.get("EQ_COSPLAY_RUN_TK_TESTS"),
    "Tk's Aqua initializer aborts this non-GUI macOS runner; opt in from a GUI session.",
)
class GuiIntegrationContracts(unittest.TestCase):
    """Exercise UI state transitions without audio, DSP, network, or bootstrap."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.original_stdout = gui.sys.stdout
        self.original_stderr = gui.sys.stderr
        self.original_language = cp.LANG
        self.patches = [
            patch.object(cp, "make_log_path", side_effect=lambda _name: Path(self.tmp.name) / "session.log"),
            patch.object(cp, "get_platform_info", return_value=("Linux", "amd64")),
            patch.object(cp, "get_default_audio_backend", return_value=("ALSA", "Mock Output")),
            patch.object(gui, "_configure_macos_window", return_value=False),
            patch.object(gui.CosplayApp, "_apply_window_icon", return_value=None),
            patch.object(gui.CosplayApp, "_init_output_default", return_value=None),
            patch.object(gui.CosplayApp, "_bootstrap", return_value=None),
        ]
        for item in self.patches:
            item.start()
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            for item in reversed(self.patches):
                item.stop()
            self.tmp.cleanup()
            self.skipTest(f"Tk display unavailable: {exc}")
        self.root.withdraw()
        self.app = gui.CosplayApp(self.root)
        self.app.plot_view.set_motion_enabled(False)
        self._pump()

    def tearDown(self):
        app = getattr(self, "app", None)
        if app is not None:
            writer = getattr(app, "_io_writer", None)
            if writer is not None:
                writer.close()
        root = getattr(self, "root", None)
        if root is not None:
            try:
                root.destroy()
            except tk.TclError:
                pass
        gui.sys.stdout = self.original_stdout
        gui.sys.stderr = self.original_stderr
        cp.LANG = self.original_language
        for item in reversed(self.patches):
            item.stop()
        self.tmp.cleanup()

    def _pump(self, rounds=3):
        if self.root is None:
            return
        for _ in range(rounds):
            try:
                self.root.update_idletasks()
                self.root.update()
            except tk.TclError:
                break

    def _correction(self):
        return {
            "grid_freqs": np.array([20.0, 100.0, 1000.0, 10000.0, 20000.0]),
            "source_fr": np.array([0.0, 1.0, 2.0, 1.0, 0.0]),
            "target_fr": np.array([1.0, 2.0, 3.0, 2.0, 1.0]),
            "peq_resp": np.array([0.5, 0.5, 0.5, 0.5, 0.5]),
            "combined_resp": np.array([0.8, 0.8, 0.8, 0.8, 0.8]),
            "simulated_curve": np.full(5, -999.0),
            "fir_ir": np.ones(9),
            "fir_n_taps": 9,
            "peq_rmse": 0.4,
            "combined_rmse": 0.2,
            "use_fir": False,
            "peq": [{"filter_type": "Peaking", "frequency": 1000.0, "gain": 0.5, "Q": 1.0}],
        }

    def _complete_fit(self):
        self.app._on_calc_done({
            "revision": self.app._selection_revision,
            "fs": int(self.app.var_sr.get()),
            "correction": self._correction(),
        }, None)
        self._pump()

    def test_fit_fir_selection_rate_drawers_inspector_language_and_destroy(self):
        app = self.app
        app.source_entry = {"display_name": "Reference", "relative_path": "tests/reference.csv"}
        app.target_entry = {"display_name": "Target", "relative_path": "tests/target.csv"}
        app.db_ready = True
        app._selection_changed()
        self._complete_fit()

        self.assertIsNotNone(app.correction)
        self.assertEqual(str(app.btn_calc.cget("state")), "normal")
        self.assertEqual(str(app.btn_deploy.cget("state")), "normal")
        self.assertEqual(str(app.btn_toggle_fir.cget("state")), "normal")
        self.assertIsNone(app.engine_proc)  # FIR toggle must stay local when stopped.

        app._on_toggle_fir()
        self._pump()
        self.assertTrue(app.correction["use_fir"])
        np.testing.assert_allclose(app.plot_view.response.simulated,
                                   app.correction["source_fr"] + app.correction["combined_resp"])
        self.assertIsNone(app.engine_proc)
        app._on_toggle_fir()
        self._pump()
        self.assertFalse(app.correction["use_fir"])

        old_revision = app._selection_revision
        app._on_source_selected({"display_name": "Changed reference"})
        self.assertEqual(app._selection_revision, old_revision + 1)
        self.assertIsNone(app.correction)
        self.assertEqual(str(app.btn_deploy.cget("state")), "disabled")

        self._complete_fit()
        app.var_sr.set("96000" if cp.DEFAULT_SAMPLE_RATE != 96000 else "44100")
        app._on_sample_rate_change()
        self._pump()
        self.assertEqual(str(app.btn_deploy.cget("state")), "disabled")
        self.assertEqual(app.phase_label.cget("text"), app._t("stage_sr"))

        for drawer in ("library", "peq", "logs"):
            app._toggle_drawer(drawer)
            self._pump()
            self.assertEqual(app._drawer, drawer)
        app._toggle_drawer("logs")
        self.assertIsNone(app._drawer)

        app._show_exact_data()
        self._pump()
        self.assertIsNotNone(app.data_inspector.window)
        self.assertTrue(app.data_inspector.window.winfo_exists())
        for language in ("en", "ja", "zh"):
            app.var_lang.set(language)
            app._on_lang_change()
            self._pump()
            self.assertEqual(cp.LANG, language)

        # The fixture tears down with direct destroy; _quit_app/_on_stop are never invoked.
        root = self.root
        root.destroy()
        self.root = None

    def test_late_fit_cannot_replace_a_new_selection(self):
        app = self.app
        old_revision = app._selection_revision
        app._on_source_selected({"display_name": "New source", "relative_path": "new.csv"})
        app._on_calc_done({"revision": old_revision, "fs": int(app.var_sr.get()),
                           "correction": self._correction()}, None)
        self.assertIsNone(app.correction)
        self.assertEqual(str(app.btn_deploy.cget("state")), "disabled")
        self.assertNotEqual(app._status_key, "gui_status_calc")

    def test_audio_deploy_uses_captured_inputs_and_holds_user_controls(self):
        from unittest.mock import Mock
        app = self.app
        source = {"display_name": "Reference", "relative_path": "reference.csv"}
        target = {"display_name": "Target", "relative_path": "target.csv"}
        app.source_box.set_entry(source)
        app.target_box.set_entry(target)
        app.db_ready = True
        self._complete_fit()
        captured = []
        process = Mock()
        process.poll.return_value = None
        path = Path(self.tmp.name) / "mock.yml"
        with patch.object(app, "_run_bg", side_effect=lambda worker, done: captured.append((worker, done))), \
             patch.object(cp, "build_config_path", return_value=path) as config_path, \
             patch.object(cp, "generate_camilladsp_config") as generate, \
             patch.object(cp, "run_camilladsp", return_value=(process, None)), \
             patch.object(app, "_refresh_presets"):
            app._on_deploy()
            self.assertTrue(app.busy)
            self.assertFalse(app.source_box._enabled)
            self.assertEqual(str(app.cmb_sr.cget("state")), "disabled")
            # A programmatic selection race must not mislabel the captured sound
            # as the currently previewed correction. No audio process is started.
            app._on_source_selected({"display_name": "Changed", "relative_path": "changed.csv"})
            result = captured[0][0]()
            captured[0][1](result, None)
            config_path.assert_called_once_with(source, target)
            self.assertEqual(len(generate.call_args.kwargs["peq_list"]), 1)
        self.assertFalse(app.busy)
        self.assertTrue(app.source_box._enabled)
        self.assertFalse(app._display_is_applied)
        self.assertEqual(app.phase_label.cget("text"), app._t("stage_review"))
        app.engine_proc = None

    def test_small_native_layout_keeps_stage_and_controls_visible(self):
        app = self.app
        self.root.deiconify()
        self.root.geometry("960x720")
        app.var_lang.set("en")
        app._on_lang_change()
        app._toggle_settings()
        app._toggle_drawer("peq")
        self._pump(8)
        self.assertGreater(app.plot_view.canvas.winfo_height(), 100)
        self.assertGreater(app.plot_view.canvas.winfo_width(), 800)
        height = self.root.winfo_height()
        for widget in (app.footer, app.control_bar, app.settings_bar, app.bottom_row):
            self.assertTrue(widget.winfo_ismapped())
            self.assertLessEqual(widget.winfo_y() + widget.winfo_height(), height)
        self._complete_fit()
        self._pump()
        canvas = app.plot_view.canvas
        # Small plots retain units and scale text without cutting the bottom or
        # colliding with the residual strip's separate scale.
        labels = [canvas.bbox(item) for item in canvas.find_withtag("static")
                  if canvas.type(item) == "text"]
        for bounds in labels:
            self.assertGreaterEqual(bounds[0], 0)
            self.assertGreaterEqual(bounds[1], 0)
            self.assertLessEqual(bounds[2], canvas.winfo_width())
            self.assertLessEqual(bounds[3], canvas.winfo_height())
        for index, first in enumerate(labels):
            for second in labels[index + 1:]:
                overlap_width = min(first[2], second[2]) - max(first[0], second[0])
                overlap_height = min(first[3], second[3]) - max(first[1], second[1])
                self.assertFalse(overlap_width > 0 and overlap_height > 0,
                                 f"Scale labels overlap: {first}, {second}")

    def test_failed_engine_launch_never_applies_preview(self):
        app = self.app
        app.source_box.set_entry({"display_name": "Source"})
        app.target_box.set_entry({"display_name": "Target"})
        self._complete_fit()
        captured = []
        with patch.object(app, "_run_bg", side_effect=lambda worker, done: captured.append((worker, done))), \
             patch.object(cp, "build_config_path", return_value=Path(self.tmp.name) / "mock.yml"), \
             patch.object(cp, "generate_camilladsp_config"), \
             patch.object(cp, "run_camilladsp", return_value=(None, None)), \
             patch.object(gui.messagebox, "showerror"):
            app._on_deploy()
            with self.assertRaises(RuntimeError) as failed:
                captured[0][0]()
            captured[0][1](None, failed.exception)
        self.assertFalse(app.busy)
        self.assertFalse(app._display_is_applied)
        self.assertIsNone(app.engine_proc)
        self.assertEqual(app._status_key, "gui_status_deploy_fail")

    def test_original_target_control_requires_measurement(self):
        app = self.app
        self._complete_fit()
        app.data_inspector.show(app.correction)
        missing = {"grid_freqs": np.array([20., 1000., 20000.]),
                   "peq_resp": np.zeros(3), "level_offset_db": 2.0}
        app.data_inspector.set_data(missing)
        self.assertEqual(str(app.data_inspector.raw_check.cget("state")), "disabled")
        missing["target_fr"] = np.ones(3)
        app.data_inspector.set_data(missing)
        self.assertEqual(str(app.data_inspector.raw_check.cget("state")), "normal")

    def test_plot_controls_translate_and_fit_at_minimum_window_size(self):
        app = self.app
        self.root.deiconify()
        self.root.geometry("960x720")
        self._complete_fit()
        app.plot_view.set_mode("comp")
        app.data_inspector.show(app.correction, "comp")
        for language, response, membrane, locked, automatic in (
            ("zh", "响应", "曲面", "范围锁定", "自动范围"),
            ("en", "Response", "Membrane", "Range locked", "Auto range"),
            ("ja", "周波数応答", "曲面", "範囲固定", "自動範囲"),
        ):
            with self.subTest(language=language):
                app.var_lang.set(language)
                app._on_lang_change()
                app.plot_view.set_scale_locked(True)
                self._pump(5)
                self.assertIn(response, app.plot_view.btn_toggle_mode.cget("text"))
                self.assertIn(membrane, app.plot_view.btn_view.cget("text"))
                self.assertIn(locked, app.plot_view.btn_lock.cget("text"))
                self.assertEqual(app.data_inspector.mode, "comp")
                self.assertEqual(app.data_inspector.view_mode.get(),
                                 {"zh": "补偿", "en": "Compensation", "ja": "補正"}[language])
                for widget in (app.plot_view.btn_toggle_mode, app.plot_view.btn_view,
                               app.plot_view.btn_lock, app.btn_calc, app.btn_deploy,
                               app.btn_settings, app.cmb_lang):
                    self.assertTrue(widget.winfo_ismapped())
                    self.assertGreaterEqual(widget.winfo_rootx(), self.root.winfo_rootx())
                    self.assertLessEqual(widget.winfo_rootx() + widget.winfo_width(),
                                         self.root.winfo_rootx() + self.root.winfo_width())
                    self.assertGreaterEqual(widget.winfo_width(), widget.winfo_reqwidth())
                app.plot_view.set_scale_locked(False)
                self.assertIn(automatic, app.plot_view.btn_lock.cget("text"))
                app.cmb_quality.current(2)
                app._on_render_quality_change()
                self.assertEqual(app._render_quality.get(), "low")
                self.assertEqual(app.plot_view._quality, "low")


if __name__ == "__main__":
    unittest.main()

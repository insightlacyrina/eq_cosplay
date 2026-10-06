# Industrial sound correction workspace

The Python GUI renders response data as a vector membrane or a flat chart. All
surface depth, emblems, icons and preset previews use Tk Canvas primitives; no
new bitmap artwork or rendering dependencies are required. The material effect
is a stylized vector surface, not operating-system blur or optical refraction.

The visual system uses neutral graphite surfaces, cool white typography and
restrained semantic response colors. A 24 px outer margin, 12 px section gaps
and 8 px control rhythm align the workspace. The main action has a neutral
light surface; persistent drawer tabs use subtle borders rather than sharing
that emphasis. UI text uses system sans-serif fonts with CJK fallback, while
numerical tables and response axes use a separate monospace family.

## Module boundaries

- `cosplay.py`: fitting, alignment, IIR/FIR responses and audio deployment.
- `visual_data.py`: pure response normalization with read-only arrays; target-minus-simulation
  residuals, original/aligned target levels, exact log-frequency readouts and CSV.
- `sound_stage.py`: drawing and input only. It consumes that shared model and
  reports a selected PEQ band through a callback; it cannot change audio routing.
- `preset_gallery.py`: lazy background parsing of saved filters and companion
  FIR files, bounded preview cache, and explicit load/delete callbacks.
- `ui_controls.py` / `vector_icons.py` / `theme.py`: picker, controls, vector
  shapes and common design tokens.
- `data_inspector.py`: complete response grid, measurement basis and CSV export.
- `cosplay_gui.py`: coordinates selections, revisions, settings and audio state.
  A generated or newly selected response is explicitly distinguished from the
  configuration that is actually playing. Inputs are held while a fit/deploy is
  pending, and late fit results are checked against selection and sample rate.

## Operation

Fit a source and target, then choose **membrane / flat** for presentation and
**response / compensation** for the quantity plotted. Range lock holds the dB
scale across comparisons; unlock it to fit a new range. Hover reads the original
calculation grid with logarithmic interpolation. Click a PEQ node to open its
parameters and isolate its computed filter contribution.

Settings expose automatic/high/low drawing quality and a motion toggle. The
bottom controls reveal saved presets, filter parameters or diagnostics. Exact
data opens a nonmodal table with original/aligned target levels and CSV export;
export includes the full valid calculation grid, independent of drawing quality.
An absent measurement or saved metric is shown as unavailable rather than zero.
The simulated response is a calculated prediction, not a microphone measurement
or a promise of perceptual equivalence.

## Performance contract

Static grid and retained response geometry are separated. Animations use elapsed
time, only run during transitions, and update bounded vector geometry. Resize
and pointer events are coalesced; automatic quality reduces point count when
the drawing path exceeds its budget. A closed gallery does not calculate
previews. A single worker computes visible preset responses; results cross a
queue before any Tk updates, and file state keys invalidate a 64-entry cache.
Logs are processed in bounded batches and the display history is capped.

Native Tk GUI tests on macOS must run with access to WindowServer. In a sandbox
without that access, Aqua can abort before Python can catch an exception. Run
the numeric tests normally; opt into native tests from a desktop terminal:

```sh
EQ_COSPLAY_RUN_TK_TESTS=1 .venv/bin/python -m unittest discover -s tests -v
```

Local timing is evidence about the tested machine, not a guarantee for every
display, operating system or computer. Validate native drawing and frame pacing
on the intended hardware before claiming a universal frame-rate target.

The revised native macOS Tk check performed five IIR/FIR round trips and one
resize, recording 233 animated frames with at most 192 sampled points. Python
drawing work measured 0.95 ms median / 2.86 ms p95, while callback intervals
measured 18.96 / 30.95 ms. Work duration and presented frame pacing are separate
quantities; this run does not establish sustained 60 fps. Curve items remained
at eleven, settled canvas items remained 53 to 53, and the animation timer
cleared. Audio launch and routing tests use mocked engines; hardware playback
and packaged-app validation remain separate checks.

## Rendering regressions

Membrane perimeters reverse complete `(x, y)` pairs, rather than reversing the
flat coordinate stream. Narrow, low-contrast surfaces preserve curve visibility.
Interrupted transitions start from the last displayed frame and resample onto
the next logarithmic frequency grid. Curves, PEQ nodes, filter lenses and hover
readouts consume the same interpolated frame. Missing series and structural
rebuilds invalidate retained items; automatic detail changes keep the material
present throughout motion. All plot controls and status annotations support
Chinese, English and Japanese. Native minimum-window checks verify that scale
text stays inside the canvas without overlapping, including open settings and
the parameter drawer.

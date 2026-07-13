# EQ Cosplay

**Make one pair of headphones sound like another** — using frequency-response data from [AutoEq](https://github.com/jaakkopasanen/AutoEq), a fixed **10-band parametric EQ**, optional **minimum-phase FIR** residual correction, and real-time playback through [CamillaDSP](https://github.com/HEnquist/camilladsp).

**Languages / 语言:** [English](README.md) · [中文说明](README.zh-CN.md)

> Short blurb for GitHub **About**:  
> Headphone “cosplay” EQ: fit Source→Target FR from AutoEq, export 10-band IIR PEQ + optional min-phase FIR, deploy via CamillaDSP. GUI & CLI (en/zh/ja).

---

## Get the code (important)

**We strongly recommend using `git clone` instead of downloading the ZIP from GitHub.**

| Method | Why |
|--------|-----|
| **`git clone` (recommended)** | Keeps executable bits (`+x`) on launch scripts; easier updates via `git pull`; fewer “permission denied” / Gatekeeper surprises |
| **Download ZIP** | Often strips executable permissions; on macOS may add quarantine attributes; updates require re-downloading |

```bash
git clone https://github.com/insightlacyrina/eq_cosplay.git
cd eq_cosplay
```

If you already used a ZIP on macOS/Linux, fix permissions once:

```bash
chmod +x start.command start_cli.command cosplay_gui.py cosplay.py
# macOS only, if Gatekeeper blocks launch:
xattr -dr com.apple.quarantine .
```

---

## Overview

| You wear (Source) | You want (Target) | Tool output |
|-------------------|-------------------|-------------|
| e.g. Sony WH-1000XM4 | e.g. AKG Q701 | IIR PEQ (± FIR) so Source ≈ Target on-axis FR |

**Pipeline**

1. Resolve models in the AutoEq results index (fuzzy search, multi-lab providers).
2. Download FR CSVs (with mirror fallbacks; optional offline CSVs).
3. Build `Target − Source` on a log-spaced grid, with midband level alignment and smoothing.
4. Fit a **fixed 10-band IIR** (Lowshelf + 8× Peaking + Highshelf).
5. If critical bands still differ strongly → design a **min-phase FIR** residual for CamillaDSP convolution.
6. Optionally deploy CamillaDSP: virtual cable → filters → real headphones.

PEQ values can be copied into Equalizer APO, Wavelet, etc. **Full residual accuracy** (when FIR is enabled) requires CamillaDSP + the generated WAV impulse responses.

---

## Features

- **AutoEq integration** — live `INDEX.md`, fuzzy matching, provider selection (oratory1990, Rtings, …)
- **10-band IIR fit** — residual-driven placement, joint optimize of gain / fc / Q, perceptual weights, soft regularization for less “surgical” Q
- **FIR residual stage** — replaces aggressive multi-band IIR “precision” mode; CamillaDSP `Conv` + mono float WAVs
- **Pre-amp modes** — safe / moderate / custom / none (from combined response peak)
- **CamillaDSP deploy** — YAML under `presets/`, FIR WAVs beside config, **single-instance** engine (stops existing `camilladsp` only when needed, then notifies)
- **GUI + CLI** — responsive Tkinter UI or terminal workflow
- **i18n** — English / 中文 / 日本語
- **Clean tree** — `presets/` for configs, `logs/` for all runtime logs

---

## Requirements

- Python **3.10+**
- **numpy**, **scipy**
- **Tkinter** for the GUI (e.g. Homebrew: `python-tk@3.x`)
- Optional for full system EQ:
  - [CamillaDSP](https://github.com/HEnquist/camilladsp) (can be downloaded by the app)
  - Virtual audio device: **BlackHole 2ch** (macOS), **VB-Audio Cable** (Windows), loopback / virtual sink (Linux)

---

## Quick start

### Launchers

| Platform | GUI | Terminal |
|----------|-----|----------|
| **Windows** | double-click `start.bat` | `start_cli.bat` or `start.bat --cli` |
| **macOS** | double-click `start.command` | `start_cli.command` / `start.command --cli` |
| **Linux** | `bash start.command` | `bash start.command --cli` |

```bash
# After git clone (recommended)
cd eq_cosplay

# macOS / Linux
./start.command          # GUI (default)
./start.command --cli    # terminal UI

# Windows (cmd / Explorer)
start.bat                # GUI
start_cli.bat            # terminal UI
```

First run creates `.venv`, installs dependencies, and starts the app.

**Windows notes:** `start.command` is a bash script and will **not** start the GUI on Windows — use **`start.bat`**. The launcher resolves `py -3` / `python` / `python3`, creates `.venv\Scripts\…`, and checks Tkinter. If Tk is missing, reinstall Python from [python.org](https://www.python.org/downloads/) with **“tcl/tk and IDLE”** enabled.

`start.command` (macOS) also runs a **new-Mac preflight**: restores `+x`, clears `com.apple.quarantine` when possible, warns if the project lives under Desktop/Documents/Downloads, and keeps the Terminal window open on failure so error text is readable.

### macOS first-run checklist (new machine)

1. Prefer **`git clone`** over downloading a ZIP (keeps executable bits).  
2. Prefer a path **outside** Desktop / Documents / Downloads (e.g. `~/Developer/eq_cosplay`) so Terminal folder-access prompts are less painful.  
3. If double-click is blocked by Gatekeeper:
   ```bash
   cd /path/to/eq_cosplay
   chmod +x start.command start_cli.command
   xattr -dr com.apple.quarantine .
   open start.command
   ```
4. When Terminal asks for Desktop/Documents/Downloads access → **Allow**.  
5. First time CamillaDSP runs (unsigned binary): **System Settings → Privacy & Security → Open Anyway**, or:
   ```bash
   xattr -dr com.apple.quarantine ./camilladsp
   ```
6. GUI needs Tk: `brew install python-tk` (or `python-tk@3.12` matching your Python).  
7. Full system EQ needs a virtual cable (e.g. BlackHole 2ch) and a real playback device name.

### Manual

```bash
git clone https://github.com/insightlacyrina/eq_cosplay.git
cd eq_cosplay
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt    # or: pip install numpy scipy
python cosplay_gui.py              # GUI
# python cosplay.py                # CLI
```

### Typical session

1. Select sample rate (e.g. 48000 Hz).  
2. Enter **source** (what you wear) and **target** (what to cosplay).  
3. Review delta summary and the 10-band PEQ table.  
4. Choose pre-amp mode.  
5. Deploy CamillaDSP (FIR WAVs are written automatically when needed).  
6. Set OS output to the **virtual capture** device; CamillaDSP plays to your **real** headphones.

---

## Repository layout

```text
eq_cosplay/
├── cosplay.py           # Core: AutoEq, PEQ/FIR, CamillaDSP YAML & process control
├── cosplay_gui.py       # Tkinter frontend
├── start.command        # macOS/Linux bootstrap + GUI
├── start_cli.command    # macOS/Linux CLI
├── start.bat            # Windows bootstrap + GUI
├── start_cli.bat        # Windows CLI
├── requirements.txt     # Python dependencies
├── README.md            # English docs
├── README.zh-CN.md      # Chinese docs
├── presets/             # Saved YAML + FIR WAVs (generated; usually gitignored content)
├── logs/                # Session & engine logs (gitignored)
├── offline_csvs/        # Optional offline AutoEq-style CSVs
└── LICENSE
```

Do **not** commit the CamillaDSP binary or machine-local presets/logs unless you intentionally want to.

---

## Correction model (brief)

1. Log grid interpolation of source/target FR (≈20 Hz–20 kHz).  
2. Midband **level alignment** (200–2000 Hz) + fractional-octave **smoothing** for IIR.  
3. Optimize fixed **10-band IIR** against the smoothed, aligned delta.  
4. Gate **FIR residual** on critical-band stats and/or IIR residual RMSE.  
5. Combined response ≈ aligned delta; pre-amp from combined peak gain.

Cross-lab pairs (e.g. oratory → Rtings) can still leave high-frequency residual; FIR helps when the difference is representable as a magnitude curve.

---

## CamillaDSP (FIR path)

Conceptual chain:

```text
Preamp → FIR Conv (L/R WAV) → 10× Biquad PEQ
```

At most **one** `camilladsp` process is kept. Starting a new session stops any previous instance and prints a short notice **only if** something was stopped.

| OS | Capture (virtual) | Playback |
|----|-------------------|----------|
| macOS | BlackHole 2ch | Real headphones/speakers |
| Windows | VB-Audio Cable | Real output |
| Linux | ALSA/PipeWire virtual | Real output |

Do not use the same virtual device for both capture and playback.

---

## Credits

- [AutoEq](https://github.com/jaakkopasanen/AutoEq) — measurement corpus and community results  
- [CamillaDSP](https://github.com/HEnquist/camilladsp) — realtime routing and filtering  
- RBJ Audio EQ Cookbook — biquad coefficient forms  

EQ Cosplay is an independent project and is not affiliated with AutoEq or CamillaDSP upstream.

---

## Disclaimer

EQ cannot fully reproduce another headphone’s timbre, staging, or nonlinear behavior. Measurement labs differ in compensation and absolute level; alignment reduces but does not remove that bias. Use adequate pre-amp and protect your hearing.

---

## License

This repository’s own source (Python scripts, launchers, docs) is under the **MIT License**. See [LICENSE](LICENSE).

Third-party components keep their own licenses:

- AutoEq measurement data: follow AutoEq / measurer terms when redistributing CSVs.  
- CamillaDSP: GPL-3.0 **or** MPL-2.0 (see upstream). Prefer **downloading at runtime**; do not commit the binary unless you accept distributing under a compatible policy.

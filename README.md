# EQ Cosplay (Swift Native Edition)

**Make one headphone sound like another** — An Apple native rewrite using **Swift 5.9+ / SwiftUI / CoreAudio / Accelerate DSP** based on the [AutoEq](https://github.com/jaakkopasanen/AutoEq) database and [CamillaDSP](https://github.com/HEnquist/camilladsp).

**Languages:** [English](README.md) · [中文说明](README.zh-CN.md)

---

## 🌟 Key Highlights

- **100% Apple Native**: Zero Python runtime or Tkinter dependencies. Compiled to native Mach-O binary with instant launch and minimal memory footprint.
- **Hardware-Accelerated DSP**:
  - Leverages Apple's `Accelerate (vDSP)` framework for real cepstrum minimum-phase reconstruction (**8192-tap FIR residual**).
  - High-performance Levenberg-Marquardt non-linear optimizer fitting **10-band IIR PEQ (1 Lowshelf + 8 Peaking + 1 Highshelf)** in milliseconds.
  - Native 32-bit Float mono WAV generator for CamillaDSP `Conv`.
- **EchoCR Visual Identity**: Sleek dark panel styling (`#12161d` panels, `#5eead4` teal primary, `#d4a24a` gold accents, `#34d399` emerald).
- **Interactive Log-Frequency Canvas**: 20 Hz – 20,000 Hz vector rendering with hover crosshair and real-time frequency & dB readout.
- **MenuBar Extra**: Status bar item keeps the CamillaDSP engine active when the main window is closed, offering instant preset switching and engine controls.
- **Seamless Ecosystem Compatibility**: Automatically recognizes and loads existing presets from the desktop `eq_cosplay/presets` directory.

---

## 🚀 Quick Start

### 1. Launch the Desktop App
```bash
open "dist/EQ Cosplay.app"
```

### 2. Run the Interactive CLI
```bash
./dist/eq-cosplay-cli
# or via SwiftPM:
swift run eq-cosplay-cli
```

### 3. Run Automated Tests
```bash
swift run eq-cosplay-tests
```
Executes 24 automated unit tests covering Biquad equations, LogGrid, optimizer convergence, FFT invertibility, minimum-phase causality, WAV writing, and CamillaDSP YAML generation.

### 4. Build & Package App
```bash
./build_app.sh
```

---

## 🎧 Audio Routing Setup

1. **Install Virtual Device**:
   ```bash
   brew install blackhole-2ch
   ```
2. **macOS Sound Settings**: Set system output to **BlackHole 2ch**.
3. **Deploy**: In EQ Cosplay, select your physical output device and click **Deploy to CamillaDSP**.

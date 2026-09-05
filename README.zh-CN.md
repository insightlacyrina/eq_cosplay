# EQ Cosplay (Swift 原生重构版)

**让一副耳机“扮演”另一副耳机的听感** — 基于 [AutoEq](https://github.com/jaakkopasanen/AutoEq) 频响数据库，利用 Apple 官方原生技术栈（**Swift 5.9+ / SwiftUI / CoreAudio / Accelerate DSP**）重构实现的现代化 macOS 耳机频响仿真与均衡校正系统。

**语言:** [中文说明](README.zh-CN.md) · [English](README.md)

---

## 🌟 重构亮点与特性

1. **纯粹的 Apple 原生体验**：
   - 告别 Python 环境与 Tkinter 依赖，编译为原生 macOS Mach-O 机器码，启动毫秒级响应，极低内存占用。
   - 完美适配 macOS Sonoma、Sequoia 及以上系统与 Apple Silicon (M1/M2/M3/M4/M5) 硬件架构。

2. **硬件级 Accelerate DSP 运算**：
   - 使用 Apple 原生 `Accelerate (vDSP)` 执行超高精度实倒谱（Real Cepstrum）变换，极速合成 **8192-tap 最小相位 FIR 残差冲激响应**。
   - 内置阻尼高斯-牛顿 / Levenberg-Marquardt 非线性最小二乘优化算法，联合优化 **10 段 IIR PEQ（1 Lowshelf + 8 Peaking + 1 Highshelf）**，收敛耗时仅需数十毫秒。
   - 32-bit Float 单声道 WAV 文件格式写入器，原生对接 CamillaDSP `Conv` 滤波器。

3. **EchoCR 声骸台视觉设计**：
   - 深度复刻 EchoCR 深色面板美学（面板 `#12161d`、高亮金 `#d4a24a`、薄荷青 `#5eead4`、翡翠绿 `#34d399`、柔红 `#f87171`）。
   - 高清对数频率坐标 Canvas 矢量绘图引擎，支持 20 Hz – 20,000 Hz 平滑曲线渲染，具备鼠标悬停十字准星与动态频点/分贝指示浮标。

4. **双模运行与菜单栏常驻**：
   - **独立桌面窗口**：直观的搜索选择、实时频响对比曲线、10 段均衡参数表、实时日志控制台。
   - **macOS 状态栏常驻 (MenuBarExtra)**：关闭主窗口后在屏幕右上角继续运行，指示引擎状态，支持一键切换本地已存方案、停止引擎与退出。
   - **终端命令行工具 (CLI)**：配套提供原汁原味的 `eq-cosplay-cli` 交互式终端工具。

5. **无缝兼容原有生态**：
   - 自动扫描并加载原 Python 项目 `/Users/zhuyongfei/Desktop/eq_cosplay/presets` 下的已有调音预设，无缝迁移。
   - 自动识别系统内置扬声器、耳机孔、USB DAC、蓝牙耳机及 BlackHole 2ch 虚拟声卡。

---

## 🚀 快速开始

### 1. 运行桌面 App
在当前目录已打包生成独立 App：
```bash
open "dist/EQ Cosplay.app"
```
或者在 Finder 中双击 `dist/EQ Cosplay.app`。

### 2. 运行终端命令行工具
```bash
./dist/eq-cosplay-cli
# 或通过 SwiftPM 源码运行：
swift run eq-cosplay-cli
```

### 3. 运行自动化测试套件
```bash
swift run eq-cosplay-tests
```
包含 Biquad 滤波器精度、对数频网格、优化拟合收敛、FFT 可逆性、FIR 最小相位因果性、WAV 写入与 YAML 生成等 24 项全量自动化测试。

### 4. 重新打包 .app
```bash
./build_app.sh
```
脚本会自动执行 Release 优化编译，提取图标生成 `.icns`，组装 `dist/EQ Cosplay.app` 并完成本地签名。

---

## 📂 项目结构

```
eq_cosplay_swift/
├── Package.swift                     # SwiftPM 工程清单
├── build_app.sh                      # 原生 .app 打包与签名脚本
├── dist/
│   ├── EQ Cosplay.app                # 编译打包好的 macOS 独立 App
│   └── eq-cosplay-cli                # 原生 CLI 独立二进制
├── assets/                           # 图标与字体资源
│   ├── icons/
│   └── fonts/
├── Sources/
│   ├── EQCosplayCore/                # 核心功能库
│   │   ├── DSP/                      # RBJ 滤波器、对数网格、LM 优化器、Accelerate FIR、WAV 写入
│   │   ├── AutoEq/                   # AutoEq 索引拉取、Markdown 解析、模糊匹配、CSV 下载与缓存
│   │   ├── Audio/                    # CoreAudio 设备枚举、BlackHole 检测
│   │   ├── Engine/                   # CamillaDSP YAML 生成、进程管道监控、预设管理
│   │   ├── Localization/             # 中/英/日动态国际化词库
│   │   └── Models/                   # 领域实体与 EchoCRTheme 视觉规范
│   ├── EQCosplayApp/                 # 原生 SwiftUI 界面与菜单栏
│   │   ├── AppState.swift            # 核心响应式状态机
│   │   ├── EQCosplayApp.swift        # 主程序入口与 MenuBarExtra
│   │   └── Views/                    # 频响 Canvas、耳机选择器、PEQ 参数表、日志台
│   └── EQCosplayCLI/                 # 原生终端命令行入口
└── Tests/
    └── EQCosplayTests/               # 全量自动化测试套件
```

---

## 🎧 音频路由配置（与 CamillaDSP）

1. **虚拟声卡**：推荐安装 [BlackHole 2ch](https://github.com/ExistentialAudio/BlackHole)：
   ```bash
   brew install blackhole-2ch
   ```
2. **系统设置**：在 macOS **系统设置 → 声音 → 输出** 中，将输出选择为 **BlackHole 2ch**。
3. **播放声音**：在 EQ Cosplay 中点击 **“应用并启动 CamillaDSP”**，系统声音将经由 CamillaDSP 实时进行 10 段 IIR + 最小相位 FIR 残差校正，并输出到您真实的物理耳机上。

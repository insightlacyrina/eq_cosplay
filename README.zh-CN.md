# EQ Cosplay

**让一副耳机“扮演”另一副耳机的听感** — 基于 [AutoEq](https://github.com/jaakkopasanen/AutoEq) 频响数据，生成固定 **10 段参数均衡（IIR PEQ）**，必要时叠加 **最小相位 FIR 残差**，并通过 [CamillaDSP](https://github.com/HEnquist/camilladsp) 实时播放。

**Languages / 语言:** [English](README.md) · [中文说明](README.zh-CN.md)

> GitHub **About** 可用短描述：  
> 耳机 Cosplay EQ：基于 AutoEq 做 Source→Target 频响校正，输出 10 段 IIR PEQ + 可选最小相位 FIR，支持 CamillaDSP 部署。GUI / CLI（中英日）。

---

## 获取代码（重要）

**强烈建议使用 `git clone`，不要优先使用 GitHub 网页的 “Download ZIP”。**

| 方式 | 说明 |
|------|------|
| **`git clone`（推荐）** | 保留启动脚本的可执行权限（`+x`）；可用 `git pull` 更新；更少“无权限 / 无法打开”问题 |
| **下载 ZIP** | 常丢失可执行位；在 macOS 上还可能带上隔离属性（quarantine）；更新只能重新下包 |

```bash
git clone https://github.com/insightlacyrina/eq_cosplay.git
cd eq_cosplay
```

若已经用 ZIP 解压到 macOS / Linux，可先修复一次：

```bash
chmod +x start.command start_cli.command cosplay_gui.py cosplay.py
# 仅 macOS：若 Gatekeeper 拦截启动
xattr -dr com.apple.quarantine .
```

---

## 能做什么

| 当前佩戴（Source） | 想要的听感（Target） | 输出 |
|--------------------|----------------------|------|
| 例如 Sony WH-1000XM4 | 例如 AKG Q701 | IIR PEQ（± FIR），使 Source 频响接近 Target |

**处理流程**

1. 在 AutoEq 结果索引中匹配型号（模糊搜索、多实验室数据源）。  
2. 下载频响 CSV（含镜像回退；可选离线 CSV）。  
3. 在对数频率网格上计算 `Target − Source`，做中频电平对齐与平滑。  
4. 拟合固定 **10 段 IIR**（Lowshelf + 8× Peaking + Highshelf）。  
5. 关键频段差异仍大时 → 设计 **最小相位 FIR 残差**，供 CamillaDSP 卷积。  
6. 可选部署 CamillaDSP：虚拟声卡 → 滤波器 → 真实耳机。

PEQ 参数可填入 Equalizer APO、Wavelet 等。**启用 FIR 时的完整残差精度**需要 CamillaDSP 与生成的 WAV 冲激响应。

---

## 功能特性

- **对接 AutoEq** — 在线 `INDEX.md`、模糊匹配、多数据源（oratory1990、Rtings 等）  
- **10 段 IIR 拟合** — 残差驱动布点，联合优化 gain / fc / Q，感知加权与软约束  
- **FIR 残差级** — 不再用“堆很多段 IIR”当精确模式；CamillaDSP `Conv` + 单声道 float WAV  
- **前级增益** — 安全 / 折中 / 自定义 / 不调整（依据联合响应峰值）  
- **CamillaDSP 部署** — 方案在 `presets/`，FIR WAV 与配置同目录，**单实例**引擎（仅在真正停掉旧进程时提示）  
- **GUI + CLI** — Tkinter 界面或终端流程  
- **多语言** — 英语 / 中文 / 日语  
- **目录清晰** — `presets/` 存方案，`logs/` 存日志  

---

## 运行环境

- Python **3.10+**  
- **numpy**、**scipy**  
- GUI 需要 **Tkinter**（Homebrew 示例：`python-tk@3.x`）  
- 完整系统 EQ 可选：  
  - [CamillaDSP](https://github.com/HEnquist/camilladsp)（程序内可下载）  
  - 虚拟声卡：**BlackHole 2ch**（macOS）、**VB-Audio Cable**（Windows）、loopback / 虚拟 sink（Linux）  

---

## 快速开始

### 启动方式

| 平台 | GUI | 终端 |
|------|-----|------|
| **Windows** | 双击 `start.bat` | `start_cli.bat` 或 `start.bat --cli` |
| **macOS** | 双击 `start.command` | `start_cli.command` / `start.command --cli` |
| **Linux** | `bash start.command` | `bash start.command --cli` |

```bash
# 推荐：先 git clone
cd eq_cosplay

# macOS / Linux
./start.command          # GUI（默认）
./start.command --cli    # 终端

# Windows（cmd / 资源管理器）
start.bat                # GUI
start_cli.bat            # 终端
```

首次运行会创建 `.venv`、安装依赖并启动程序。

**Windows 说明：** `start.command` 是 bash 脚本，**不能**在 Windows 上启动 GUI，请用 **`start.bat`**。启动器会尝试 `py -3` / `python` / `python3`，并创建 `.venv\Scripts\…`。若缺少 Tk，请用 [python.org](https://www.python.org/downloads/) 安装包重装，勾选 **“tcl/tk and IDLE”** 与 **Add to PATH**。

macOS 的 `start.command` 还包含**新机预检**：恢复 `+x`、尽量清除 quarantine、项目在桌面/文稿/下载时提示、失败时窗口不立刻关闭。

### macOS 新机清单

1. 优先 **`git clone`**，少用 ZIP。  
2. 尽量不要把项目放在桌面 / 文稿 / 下载（可用如 `~/Developer/eq_cosplay`），减少“终端要访问文件夹”弹窗。  
3. 若双击被 Gatekeeper 拦截：
   ```bash
   cd /path/to/eq_cosplay
   chmod +x start.command start_cli.command
   xattr -dr com.apple.quarantine .
   open start.command
   ```
4. 终端询问访问桌面等目录时 → 选 **允许**。  
5. 首次运行未签名的 CamillaDSP：系统设置 → 隐私与安全性 → **仍要打开**，或：
   ```bash
   xattr -dr com.apple.quarantine ./camilladsp
   ```
6. GUI 需要 Tk：`brew install python-tk`（或与 Python 版本匹配的 `python-tk@3.12` 等）。  
7. 完整系统 EQ 需要虚拟线（如 BlackHole 2ch）以及真实播放设备名。  

### 手动安装

```bash
git clone https://github.com/insightlacyrina/eq_cosplay.git
cd eq_cosplay
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python cosplay_gui.py              # GUI
# python cosplay.py                # CLI
```

### 典型使用流程

1. 选择采样率（如 48000 Hz）。  
2. 输入 **Source**（当前耳机）与 **Target**（想 Cosplay 的型号）。  
3. 查看差值概览与 10 段 PEQ 表。  
4. 选择前级增益模式。  
5. 部署 CamillaDSP（需要 FIR 时会自动写 WAV）。  
6. 系统输出设为**虚拟采集设备**；CamillaDSP 播放到**真实耳机**。  

GUI 中若启用了 FIR，可在绿色 FIR 提示下方使用 **「停止 FIR」** 全宽按钮：关闭 FIR、按仅 IIR 重写配置并重启引擎。

---

## 目录结构

```text
eq_cosplay/
├── cosplay.py           # 核心：AutoEq、PEQ/FIR、CamillaDSP
├── cosplay_gui.py       # Tkinter 界面
├── start.command        # macOS/Linux 启动 + GUI
├── start_cli.command    # macOS/Linux 终端
├── start.bat            # Windows 启动 + GUI
├── start_cli.bat        # Windows 终端
├── requirements.txt     # Python 依赖
├── README.md            # 英文说明
├── README.zh-CN.md      # 中文说明（本文件）
├── presets/             # 已保存 YAML + FIR WAV（一般被 gitignore）
├── logs/                # 会话与引擎日志（gitignore）
├── offline_csvs/        # 可选离线测量 CSV
└── LICENSE
```

请勿提交 CamillaDSP 二进制或本机 `presets/`、`logs/`（除非你有意为之）。

---

## 校正模型（简要）

1. Source/Target 频响插值到对数网格（约 20 Hz–20 kHz）。  
2. 中频段（200–2000 Hz）**电平对齐** + 分数倍频程**平滑**（供 IIR）。  
3. 对平滑后的对齐差值拟合固定 **10 段 IIR**。  
4. 按关键频段统计和/或 IIR 残差 RMSE 决定是否做 **FIR 残差**。  
5. 联合响应 ≈ 对齐后的差值；前级取自联合响应峰值。  

跨实验室组合（如 oratory → Rtings）高频仍可能有残差；在幅度差可表示时，FIR 会有帮助。

---

## CamillaDSP（含 FIR 时）

示意链路：

```text
前级增益 → FIR 卷积（左/右 WAV）→ 10 段 Biquad PEQ
```

同时只保留 **一个** `camilladsp` 进程。启动新会话会停掉旧实例，**仅在确实停掉了进程时**打印提示。

| 系统 | 采集（虚拟） | 播放 |
|------|--------------|------|
| macOS | BlackHole 2ch | 真实耳机/音箱 |
| Windows | VB-Audio Cable | 真实输出 |
| Linux | ALSA/PipeWire 虚拟设备 | 真实输出 |

不要把采集与播放都设成同一个虚拟设备。

---

## 致谢

- [AutoEq](https://github.com/jaakkopasanen/AutoEq) — 测量与社区结果  
- [CamillaDSP](https://github.com/HEnquist/camilladsp) — 实时路由与滤波  
- RBJ Audio EQ Cookbook — 双二阶系数  

本项目为独立工具，与 AutoEq、CamillaDSP 上游无隶属关系。

---

## 免责声明

均衡无法完整复现另一副耳机的音色、定位与非线性失真。不同实验室补偿与绝对电平不同；对齐能减轻但不能消除差异。请合理设置前级，注意听力健康。

---

## 许可证

本仓库自有源码（Python 脚本、启动器、文档）采用 **MIT License**，见 [LICENSE](LICENSE)。

第三方组件仍遵循其原许可：

- AutoEq 测量数据：再分发 CSV 时请遵守 AutoEq / 原测量者条款。  
- CamillaDSP：GPL-3.0 **或** MPL-2.0（见上游）。建议**运行时下载**，不要把二进制提交进本仓库（除非你清楚兼容策略）。  

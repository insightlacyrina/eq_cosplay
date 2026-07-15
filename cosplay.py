import csv
import difflib
import json
import math
import os
import re
import sys
import tempfile
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
import subprocess
import threading
import locale
import platform
import tarfile
import zipfile
import shutil

import numpy as np
from scipy import optimize
from scipy.io import wavfile as scipy_wavfile

# --- 配置常量 ---
GITHUB_RAW_INDEX_URL = "https://raw.githubusercontent.com/jaakkopasanen/AutoEq/master/results/INDEX.md"

MIRROR_PREFIXES = [
    "",                                    # 官方 GitHub（优先尝试）
    "https://ghproxy.net/",
    "https://ghp.ci/",
    "https://mirror.ghproxy.com/",
    "https://raw.kkgithub.com/",           # 保留作为备选
]

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
OFFLINE_CSV_DIR = Path("./offline_csvs")
# 生成的 CamillaDSP YAML 方案集中存放目录
SAVED_PRESETS_DIR = Path("./presets")
# 运行日志目录（CamillaDSP / GUI / CLI 会话日志）
LOGS_DIR = Path("./logs")
SUPPORTED_SAMPLE_RATES = {
    '1': 44100,
    '2': 48000,
    '3': 88200,
    '4': 96000,
    '5': 192000,
}
DEFAULT_SAMPLE_RATE = 48000
# 耳机数据库（CLI / GUI 共用；启动时由 load_autoeq_database 填充）
AUTOEQ_DATABASE: dict = {}

def get_system_language() -> str:
    """获取系统语言环境，支持多种环境变量和 locale 返回值。"""
    def normalize_locale_code(raw: str) -> str | None:
        raw = raw.strip().lower()
        if raw.startswith('zh'):
            return 'zh'
        if raw.startswith('ja'):
            return 'ja'
        if raw.startswith('en'):
            return 'en'
        match = re.match(r'^([a-z]{2})', raw)
        if match:
            return match.group(1)
        return None

    candidates = [
        os.environ.get('LANGUAGE'),
        os.environ.get('LC_ALL'),
        os.environ.get('LC_MESSAGES'),
        os.environ.get('LC_CTYPE'),
        os.environ.get('LANG'),
    ]

    for value in candidates:
        if not value:
            continue
        lang_code = normalize_locale_code(value)
        if lang_code in ('zh', 'ja', 'en'):
            return lang_code

    try:
        locale_name = locale.getlocale()[0]
    except Exception:
        locale_name = None
    if locale_name:
        locale_name = normalize_locale_code(locale_name)
        if locale_name in ('zh', 'ja', 'en'):
            return locale_name

    # Python 3.15 将移除 getdefaultlocale；仅作为旧环境回退
    try:
        get_default = getattr(locale, 'getdefaultlocale', None)
        if get_default is not None:
            default_locale = get_default()[0]
            if default_locale:
                locale_name = normalize_locale_code(default_locale)
                if locale_name in ('zh', 'ja', 'en'):
                    return locale_name
    except Exception:
        pass

    # macOS：终端 LANG 常为 en_US，但系统 UI 可能是中文/日文
    try:
        if platform.system() == 'Darwin':
            result = subprocess.run(
                ['defaults', 'read', '-g', 'AppleLanguages'],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout:
                match = re.search(r'[\s(]"([a-z]{2})[-_]', result.stdout.lower())
                if match and match.group(1) in ('zh', 'ja', 'en'):
                    return match.group(1)
    except Exception:
        pass

    return 'en'

LANG = get_system_language()
MESSAGES = {
    "en": {
        "retry_request": "[WARN] Request failed ({exc}), retrying in {wait_time:.1f}s ({attempt}/{retries})...",
        "parse_index_empty": "[WARN] No valid entries were parsed from AutoEq INDEX.md.",
        "loading_database": "[..] Connecting to AutoEq GitHub to load the latest database...",
        "database_loaded": "[OK] Loaded {count} headphone entries.",
        "database_failed": "[WARN] Failed to load INDEX.md from AutoEq GitHub: {error}",
        "using_fallback_db": "[INFO] Using local fallback database.",
        "db_not_loaded": "[ERR] AutoEq database is not loaded.",
        "searching_headphone": "\n[..] Searching for the best match for '{user_input}' ({prompt_type})...",
        "no_match_found": "[ERR] No matching headphone found. Check spelling or try a fuller model name.",
        "match_success": "[OK] Match found -- {prompt_type}: {display_name}",
        "no_csv_in_dir": "[WARN] No .csv files found in directory {directory}.",
        "cannot_access_dir": "[WARN] Unable to access AutoEq directory {path}: {error}",
        "downloading_file": "[..] Downloading: {filename} ...",
        "download_failed": "[WARN] File download failed: {error}",
        "download_failed_label": "download failed",
        "offline_csv_missing": "[WARN] Local fallback CSV not found: {path}. Place the file under offline_csvs.",
        "network_exit": "[ERR] Network error or download failure. The program will exit.",
        "no_relative_path": "[WARN] Headphone '{display_name}' does not have a relative path.",
        "using_local_csv": "[INFO] Using local offline CSV: {path}",
        "calculating_peq": "\n[..] Calculating frequency response delta and fitting 10-band PEQ...",
        "peq_complete": "[OK] 10-band IIR PEQ completed, RMSE: {rmse:.3f} dB",
        "peq_standard_mode": "[INFO] Using fixed 10-band IIR PEQ (Lowshelf + 8×Peaking + Highshelf).",
        "fir_precision_mode": "[INFO] Large FR difference in critical band(s): {regions}. Adding minimum-phase FIR residual correction.",
        "fir_skipped_mode": "[INFO] Critical bands within tolerance — FIR residual stage skipped (IIR only).",
        "fir_complete": "[OK] FIR residual designed ({taps} taps), residual RMSE: {rmse:.3f} dB, combined RMSE: {combined:.3f} dB",
        "fir_saved": "[OK] FIR impulse responses saved:\n     L: {left}\n     R: {right}",
        "fir_triggered_banner": "\n========== FIR CONVOLUTION ENABLED ==========\n"
            "[FIR] Critical-band FR mismatch is large — precision stage uses minimum-phase FIR\n"
            "      convolution (not extra IIR peaking bands).\n"
            "[FIR] 10-band IIR above = portable tonal shape for other EQ apps.\n"
            "[FIR] Full residual accuracy requires CamillaDSP Conv + the WAV impulse files.\n"
            "============================================",
        "fir_camilladsp_deploy_notice": "\n========== CamillaDSP + FIR DEPLOY ==========\n"
            "[CamillaDSP] This preset chains: Preamp → FIR Conv (L/R) → 10-band IIR PEQ.\n"
            "[CamillaDSP] FIR WAVs must stay next to the YAML (paths are absolute in config).\n"
            "[CamillaDSP] Do not delete *_fir_left.wav / *_fir_right.wav or convolution will fail.\n"
            "[CamillaDSP] Latency ≈ FIR length / sample rate (8192 taps @ 48 kHz ≈ 170 ms worst-case\n"
            "             processing block; engine uses partitioned conv when available).\n"
            "[CamillaDSP] Route system output to the virtual device (e.g. BlackHole), then play audio.\n"
            "============================================",
        "fir_camilladsp_running_notice": "[CamillaDSP/FIR] Engine running with FIR convolution active.\n"
            "     Keep both the YAML and its companion FIR WAV files on disk.",
        "deploy_iir_only_notice": "[CamillaDSP] IIR-only preset (no FIR). Critical-band residual was within tolerance.",
        "deploy_skipped_with_fir": "[WARN] FIR residual was designed for this pair, but CamillaDSP was not deployed.\n"
            "       The PEQ table alone is only the 10-band IIR envelope — fine detail needs FIR Conv.\n"
            "       Re-run and choose deploy (y) to write WAV + YAML and start CamillaDSP.",
        "deploy_prompt_with_fir": "\nFIR residual is ready. Deploy CamillaDSP with FIR convolution? (y/n): ",
        "installing_blackhole": "[..] Installing BlackHole 2ch virtual audio device...",
        "homebrew_missing": "[ERR] Homebrew is not installed. Please install Homebrew first.",
        "blackhole_installed": "[OK] BlackHole 2ch is installed.",
        "blackhole_install_failed": "[WARN] BlackHole installation failed: {error}",
        "blackhole_install_error": "[ERR] Error installing BlackHole: {error}",
        "blackhole_not_installed": "[INFO] BlackHole 2ch is not installed.",
        "camilladsp_not_installed": "[INFO] CamillaDSP is not installed.",
        "camilladsp_download_fail_continue": "[WARN] CamillaDSP download failed; cannot continue deployment.",
        "download_camilladsp": "[..] Downloading CamillaDSP engine from GitHub...",
        "camilladsp_asset_not_found": "[ERR] Could not find a compatible CamillaDSP asset for your platform.",
        "camilladsp_download_error": "[ERR] Error downloading CamillaDSP: {error}",
        "camilladsp_download_success": "[OK] CamillaDSP downloaded and configured successfully.",
        "config_generated": "[OK] CamillaDSP configuration file generated: {path}",
        "starting_camilladsp": "[..] Starting CamillaDSP...",
        "camilladsp_failed": "[ERR] CamillaDSP failed to start: {error}",
        "camilladsp_started": "[OK] CamillaDSP has started successfully.",
        "camilladsp_executable_missing": "[ERR] CamillaDSP executable not found in the downloaded archive.",
        "camilladsp_installed": "[OK] CamillaDSP is already installed.",
        "log_prefix": "[CamillaDSP]",
        "exit_prompt": "\nEnter 'q' and press Enter to shut down the engine.",
        "camilladsp_monitor_prompt": "\nPress 'q' then Enter to stop CamillaDSP and exit.",
        "camilladsp_stopped": "[OK] CamillaDSP has been stopped.",
        "camilladsp_previous_stopped": "[INFO] Stopped {count} existing CamillaDSP process(es) so only one instance runs at a time.",
        "auto_deploy_complete": "[OK] Full auto deployment complete.",
        "usage_instructions": "[TIP] Set system audio output to 'BlackHole 2ch' and keep the engine running until you are ready to stop.",
        "output_device_set": "[OK] Output device set to: {device}",
        "prepare_config": "[..] Preparing the CamillaDSP configuration file:",
        "physical_source_label": "base",
        "target_cosplay_label": "target",
        "csv_label": "CSV",
        "peq_table_band": "Band",
        "peq_table_type": "Type",
        "peq_table_frequency": "Frequency (Hz)",
        "peq_table_gain": "Gain (dB)",
        "peq_table_q": "Q",
        "welcome": "EQ Cosplay  --  Terminal Tool (Core Calculation)",
        "welcome_sep": "",
        "sample_rate_prompt": "\nSelect target sample rate:\n  [1] 44100 Hz\n  [2] 48000 Hz  (default)\n  [3] 88200 Hz\n  [4] 96000 Hz\n  [5] 192000 Hz\nChoice [1-5]: ",
        "invalid_selection": "[WARN] Invalid selection, using default {default} Hz.",
        "platform_detected": "[INFO] Platform: {platform_name} ({architecture})",
        "virtual_device_missing_windows": "[WARN] VB-Audio Virtual Cable not detected. Download from https://vb-audio.com/Cable/ then press Enter.",
        "virtual_device_missing_linux": "[WARN] No virtual audio device detected. Install ALSA loopback / PipeWire virtual sink, then press Enter.",
        "press_enter_to_continue": "Press Enter to continue...",
        "goodbye": "Goodbye.",
        "step1_prompt": "\nStep 1  Current headphone model (or 'q' to quit): ",
        "step2_prompt": "\nStep 2  Target headphone to cosplay (or 'q' to quit): ",
        "debug_prompt": "\nEnable debug mode for CamillaDSP? (y/n, default n): ",
        "yaml_dump_header": "\nYAML CONFIG DUMP",
        "debug_enabled": "[INFO] Debug mode enabled. Dumping YAML and launching CamillaDSP with verbose logs.",
        "audio_device_list_header": "\nAUDIO DEVICE LIST",
        "deploy_prompt": "\nDeploy full CamillaDSP environment? (y/n): ",
        "install_blackhole_prompt": "Install BlackHole 2ch automatically? (y/n): ",
        "output_device_prompt": "\nPlayback (output) device name\n  Press Enter for default: {default_name}\n> ",
        "output_device_macos_note": "[TIP] macOS: use the real CoreAudio playback device name (system_profiler SPAudioDataType). Do not use BlackHole 2ch here -- that is the capture device.",
        "full_auto_deploy": "[..] Starting CamillaDSP automatic deployment...",
        "process_exited": "[WARN] CamillaDSP process has exited.",
        "cannot_generate_peq": "[WARN] Cannot generate PEQ: missing source or target CSV. Check network or model name.",
        "partial_blackhole_failure": "[WARN] BlackHole installation failed; setup may not work properly.",
        "user_cancelled_blackhole": "[WARN] BlackHole installation cancelled.",
        "user_cancelled_deploy": "[WARN] CamillaDSP deployment cancelled.",
        "use_default_device": "{default_name}",
        "plugin_note": "[TIP] Enter the parameters above into your equalizer software (e.g. Equalizer APO, Wavelet).",
        "unknown_error": "[ERR] An unexpected error occurred: {error}",
        "peq_table_title": "Recommended PEQ  (parametric EQ)",
        "delta_summary_heading": "Delta curve overview  (Target - Source)",
        "delta_peak": "  Peak boost:            +{peak:.2f} dB",
        "delta_valley": "  Maximum attenuation:   {valley:.2f} dB",
        "delta_mean": "  Mean difference:       {mean:.2f} dB",
        "section_separator": "",
        "provider_list_header": "\nMultiple providers found for this headphone:",
        "provider_menu_default_note": "Press Enter to choose the first provider.",
        "provider_choice_prompt": "Provider number: ",
        "provider_invalid_selection": "[WARN] Invalid selection; defaulting to the first provider.",
        "delta_clipping_warning": "[WARN] Peak boost detected. Pre-amp adjustment is required to prevent clipping.",
        "preamp_selection_prompt": "\nSelect pre-amp mode:",
        "preamp_option_safe": "  [1] Safe      -({peak:.2f} + 0.2) dB  absolute clipping prevention",
        "preamp_option_moderate": "  [2] Moderate  -({peak:.2f} / 2.0) dB  balanced dynamics",
        "preamp_option_custom": "  [3] Custom    enter your own value (e.g. -4.5)",
        "preamp_custom_input_prompt": "Pre-amp value in dB (negative = attenuation): ",
        "preamp_invalid_input": "[ERR] Invalid input. Please enter a valid number.",
        "preamp_applied": "[OK] Applied pre-amp: {preamp:.2f} dB",
        "no_preamp_needed": "[INFO] No pre-amp adjustment needed (peak <= 0 dB).",
        "main_program_started": "[OK] Main program started.",
        "csv_url_not_found": "[WARN] No usable CSV URL for '{display_name}'. Try another model or place a file under offline_csvs.",
        "csv_download_failed_retry": "[WARN] Failed to download CSV for '{display_name}'. Try another model or use offline_csvs.",
        "capture_device_as_playback": "[WARN] '{user_input}' is a virtual capture device and cannot be used for playback. Falling back to '{default_name}'.",
        "camilladsp_exited_early": "process exited immediately with code {code}. Check capture/playback device names and sample rate.",
        "camilladsp_process_not_started": "process did not start",
        "camilladsp_log_window_title": "CamillaDSP Log -- EQ Cosplay",
        "camilladsp_log_window_opened": "[OK] CamillaDSP log window opened.\n     Log file: {path}",
        "camilladsp_log_window_failed": "[WARN] Could not open a separate log window ({error}). Streaming logs here instead.",
        "camilladsp_log_file_hint": "[INFO] CamillaDSP log file: {path}",
        "camilladsp_engine_running": "[OK] EQ engine is running.\n     Main window: control  |  Separate window: CamillaDSP logs",
        "camilladsp_log_end_marker": "===== CamillaDSP stopped =====",
        "deploy_skipped": "[INFO] Skipped CamillaDSP deployment. You can still use the PEQ values above in other EQ software.",
        "default_playback_headphones": "External Headphones",
        "default_playback_speakers": "Speakers",
        "default_playback_linux": "default",
        "provider_single_source": "[INFO] Only one measurement source for this headphone: {provider}",
        "saved_presets_prompt": "\nFound {count} saved preset(s) on this machine.\nLoad a saved CamillaDSP preset now? (y/n, default n): ",
        "saved_presets_header": "Saved presets",
        "saved_presets_choice_prompt": "Enter preset number (or Enter to cancel): ",
        "saved_presets_invalid": "[WARN] Invalid selection. Skipping saved presets.",
        "saved_presets_cancelled": "[INFO] Skipped saved presets. Starting a new cosplay calculation.",
        "saved_presets_selected": "[OK] Selected preset: {name}",
        "saved_presets_empty": "[INFO] No saved presets yet. New YAML files will be stored under {path}.",
        "saved_presets_dir": "[INFO] Preset folder: {path}",
        "saved_presets_saved": "[OK] Configuration saved to: {path}",
        "saved_presets_launch": "[..] Launching CamillaDSP with saved preset...",
        "saved_presets_missing_file": "[ERR] Preset file not found: {path}",
        # --- GUI ---
        "gui_window_title": "EQ Cosplay",
        "gui_language": "Language",
        "gui_presets": "Saved presets",
        "gui_refresh": "Refresh",
        "gui_load_start": "Load & start",
        "gui_cosplay": "Cosplay",
        "gui_sample_rate": "Sample rate (Hz)",
        "gui_source": "Current headphones (Source)",
        "gui_target": "Target headphones",
        "gui_playback": "Playback device",
        "gui_output_resolved": "[INFO] Playback device resolved: '{user}' → '{device}'\n",
        "gui_preamp": "Pre-amp",
        "gui_preamp_safe": "Safe  −(peak+0.2) dB",
        "gui_preamp_moderate": "Moderate  −(peak/2) dB",
        "gui_preamp_custom": "Custom",
        "gui_preamp_none": "None (0 dB)",
        "gui_custom_db": "Custom dB",
        "gui_debug": "CamillaDSP debug log",
        "gui_calc": "Calculate",
        "gui_deploy": "Deploy & start CamillaDSP",
        "gui_stop": "Stop engine",
        "gui_peq": "Recommended PEQ",
        "gui_log": "Log",
        "gui_tip": "Tip: 10-band IIR is portable; full residual accuracy needs CamillaDSP FIR convolution when enabled.",
        "gui_tip_header": "Info",
        "gui_platform": "Platform",
        "gui_capture": "Capture",
        "gui_logs_dir": "Log folder",
        "gui_status_loading": "Loading database…",
        "gui_status_ready": "Ready · {count} models",
        "gui_status_db_fail": "Database load failed",
        "gui_status_busy_wait": "Please wait for the current task to finish.",
        "gui_status_calc": "Calculating…",
        "gui_status_calc_fail": "Calculation failed",
        "gui_status_calc_done": "Done · ready to deploy",
        "gui_status_deploy": "Deploying…",
        "gui_status_deploy_fail": "Deploy failed",
        "gui_status_engine_fail": "Engine failed to start",
        "gui_status_running": "Engine running",
        "gui_status_stopped": "Engine stopped",
        "gui_status_exited": "Engine exited",
        "gui_status_preset": "Starting preset…",
        "gui_status_download": "Downloading CamillaDSP…",
        "gui_fir_on": "FIR on · {taps} taps · combined RMSE {rmse}",
        "gui_fir_off": "IIR only · RMSE {rmse} (FIR not triggered)",
        "gui_fir_paused": "IIR only · FIR available (disabled) · IIR RMSE {rmse}",
        "gui_stop_fir": "Stop FIR",
        "gui_enable_fir": "Enable FIR",
        "gui_status_stop_fir": "Disabling FIR & restarting…",
        "gui_status_enable_fir": "Enabling FIR & restarting…",
        "gui_fir_stopped_log": "[INFO] FIR disabled. Restarting CamillaDSP with IIR-only chain.\n",
        "gui_fir_enabled_log": "[INFO] FIR re-enabled. Restarting CamillaDSP with FIR convolution chain.\n",
        "gui_msg_stop_fir_need": "FIR is not active for this session.",
        "gui_msg_enable_fir_need": "No FIR residual is available to enable.",
        "gui_metrics": "Response peak {peak:+.2f} dB  |  Level offset {offset:+.2f} dB",
        "gui_db_ok": "[OK] Database ready: {count} entries.\n",
        "gui_calc_ok": "[OK] Calculation finished. You can deploy CamillaDSP.\n",
        "gui_session_log": "[INFO] Session log: {path}\n",
        "gui_logs_info": "[INFO] Log folder: {path}\n",
        "gui_config_ok": "[OK] Config: {path}\n",
        "gui_engine_exit": "[WARN] CamillaDSP exited (code={code}).\n",
        "gui_engine_stopped": "[OK] CamillaDSP stopped.\n",
        "gui_msg_db_fail": "Failed to load AutoEq database:\n{error}",
        "gui_msg_db_not_ready": "Database is not ready yet.",
        "gui_msg_fill_models": "Please enter source and target headphone models.",
        "gui_msg_not_found": "No match for: {name}",
        "gui_msg_calc_fail": "Calculation failed:\n{error}",
        "gui_msg_need_calc": "Please calculate first.",
        "gui_msg_engine_running": "Engine is already running. Stop it first.",
        "gui_msg_bh_ask": "BlackHole 2ch not detected. Try to install?",
        "gui_msg_bh_fail": "BlackHole install failed or incomplete.",
        "gui_msg_bh_later": "You can install the virtual audio device later.",
        "gui_msg_virt_other": "Please ensure a virtual cable is installed (Windows: VB-Cable / Linux: loopback).",
        "gui_msg_cdsp_ask": "CamillaDSP not found. Download now?",
        "gui_msg_cdsp_fail": "CamillaDSP download failed.",
        "gui_msg_deploy_fail": "Deploy failed:\n{error}",
        "gui_msg_start_fail": "CamillaDSP failed to start. Check the log.",
        "gui_msg_pick_preset": "Select a saved preset first.",
        "gui_msg_ok": "OK",
        "gui_msg_cancel": "Cancel",
        "gui_provider_model": "Model",
        "gui_provider_source": "Provider",
        "gui_col_band": "#",
        "gui_col_type": "Type",
        "gui_col_freq": "Hz",
        "gui_col_gain": "dB",
        "gui_col_q": "Q",
    },
    "zh": {
        "retry_request": "[WARN] 请求失败 ({exc})，{wait_time:.1f} 秒后重试 ({attempt}/{retries})...",
        "parse_index_empty": "[WARN] 未从 AutoEq INDEX.md 中解析到有效条目。",
        "loading_database": "[..] 正在连接 AutoEq GitHub 获取最新数据库...",
        "database_loaded": "[OK] 已成功加载 {count} 个耳机条目。",
        "database_failed": "[WARN] 无法从 AutoEq GitHub 加载 INDEX.md：{error}",
        "using_fallback_db": "[INFO] 使用本地备用数据库进行匹配。",
        "db_not_loaded": "[ERR] 数据库尚未加载。",
        "searching_headphone": "\n[..] 正在寻找与 '{user_input}' 最匹配的【{prompt_type}】耳机...",
        "no_match_found": "[ERR] 数据库中没有找到相关耳机，请检查拼写或换一个更完整的型号。",
        "match_success": "[OK] 匹配成功 -- 【{prompt_type}】: {display_name}",
        "no_csv_in_dir": "[WARN] 在目录 {directory} 中未找到任何 .csv 文件。",
        "cannot_access_dir": "[WARN] 无法访问 AutoEq 目录 {path}：{error}",
        "downloading_file": "[..] 正在下载: {filename} ...",
        "download_failed": "[WARN] 下载文件失败：{error}",
        "download_failed_label": "下载失败",
        "offline_csv_missing": "[WARN] 本地离线 CSV 未找到：{path}。请将文件放入 offline_csvs 目录。",
        "network_exit": "[ERR] 网络连接失败或下载错误，程序将退出。",
        "no_relative_path": "[WARN] 耳机 '{display_name}' 没有关联的路径信息。",
        "using_local_csv": "[INFO] 使用本地离线 CSV: {path}",
        "calculating_peq": "\n[..] 正在计算频响差值并拟合 10 段 IIR PEQ...",
        "peq_complete": "[OK] 10 段 IIR PEQ 完成，拟合 RMSE: {rmse:.3f} dB",
        "peq_standard_mode": "[INFO] 固定使用 10 段 IIR PEQ（Lowshelf + 8×Peaking + Highshelf）。",
        "fir_precision_mode": "[INFO] 关键频段差异较大：{regions}。将叠加最小相位 FIR 残差校正。",
        "fir_skipped_mode": "[INFO] 关键频段差异可控 — 跳过 FIR 残差级（仅 IIR）。",
        "fir_complete": "[OK] FIR 残差已设计（{taps} taps），残差 RMSE: {rmse:.3f} dB，联合 RMSE: {combined:.3f} dB",
        "fir_saved": "[OK] FIR 冲激响应已保存：\n     L: {left}\n     R: {right}",
        "fir_triggered_banner": "\n========== 已启用 FIR 卷积精确校正 ==========\n"
            "[FIR] 关键频段差异较大 — 精确级改用「最小相位 FIR 卷积」补残差，\n"
            "      不再增加 IIR peaking 段数。\n"
            "[FIR] 上方 10 段 IIR 表可填入其他均衡器，负责主体音色包络。\n"
            "[FIR] 完整残差精度需 CamillaDSP 的 Conv + 配套 WAV 冲激文件。\n"
            "============================================",
        "fir_camilladsp_deploy_notice": "\n========== CamillaDSP + FIR 部署提示 ==========\n"
            "[CamillaDSP] 本方案链路：前级增益 → FIR 卷积（左/右）→ 10 段 IIR PEQ。\n"
            "[CamillaDSP] FIR 的 WAV 与 YAML 同目录；配置内为绝对路径，请勿只拷走 yml。\n"
            "[CamillaDSP] 请保留 *_fir_left.wav / *_fir_right.wav，删除后卷积会加载失败。\n"
            "[CamillaDSP] 延迟与 FIR 长度/采样率相关（8192 taps @ 48 kHz 量级约百毫秒级）。\n"
            "[CamillaDSP] 请将系统输出切到虚拟声卡（如 BlackHole），再播放音频。\n"
            "============================================",
        "fir_camilladsp_running_notice": "[CamillaDSP/FIR] 引擎已在 FIR 卷积模式下运行。\n"
            "     请保持 YAML 与配套 FIR WAV 同时存在于磁盘。",
        "deploy_iir_only_notice": "[CamillaDSP] 当前为纯 IIR 方案（未启用 FIR）。关键频段残差在容差内。",
        "deploy_skipped_with_fir": "[WARN] 本配对已设计 FIR 残差，但未部署 CamillaDSP。\n"
            "       上方 PEQ 表仅为 10 段 IIR 包络；精细校正依赖 FIR 卷积。\n"
            "       若需完整精度，请重新选择部署 (y) 以写出 WAV+YAML 并启动引擎。",
        "deploy_prompt_with_fir": "\n已准备 FIR 残差。是否部署带 FIR 卷积的 CamillaDSP？(y/n): ",
        "installing_blackhole": "[..] 正在安装 BlackHole 2ch 虚拟音频设备...",
        "homebrew_missing": "[ERR] 未安装 Homebrew，请先安装 Homebrew。",
        "blackhole_installed": "[OK] BlackHole 2ch 已安装。",
        "blackhole_install_failed": "[WARN] BlackHole 安装失败: {error}",
        "blackhole_install_error": "[ERR] 安装 BlackHole 时发生错误: {error}",
        "blackhole_not_installed": "[INFO] 检测到 BlackHole 2ch 未安装。",
        "camilladsp_not_installed": "[INFO] 检测到 CamillaDSP 未安装。",
        "camilladsp_download_fail_continue": "[WARN] CamillaDSP 下载失败，无法继续部署。",
        "download_camilladsp": "[..] 正在从 GitHub 下载 CamillaDSP 引擎...",
        "camilladsp_asset_not_found": "[ERR] 未找到适用于当前平台的 CamillaDSP 版本。",
        "camilladsp_download_error": "[ERR] 下载 CamillaDSP 时发生错误: {error}",
        "camilladsp_download_success": "[OK] CamillaDSP 下载并配置成功。",
        "config_generated": "[OK] CamillaDSP 配置文件已生成: {path}",
        "starting_camilladsp": "[..] 正在启动 CamillaDSP...",
        "camilladsp_failed": "[ERR] CamillaDSP 启动失败: {error}",
        "camilladsp_started": "[OK] CamillaDSP 已成功启动。",
        "camilladsp_executable_missing": "[ERR] 未在下载的归档中找到 CamillaDSP 可执行文件。",
        "camilladsp_installed": "[OK] CamillaDSP 已安装。",
        "log_prefix": "[CamillaDSP]",
        "exit_prompt": "\n输入 q 并回车以退出引擎。",
        "camilladsp_monitor_prompt": "\n按 q 然后回车停止 CamillaDSP 并退出。",
        "camilladsp_stopped": "[OK] CamillaDSP 已停止。",
        "camilladsp_previous_stopped": "[INFO] 已停止 {count} 个正在运行的 CamillaDSP 进程，保证同一时间仅有一个实例。",
        "auto_deploy_complete": "[OK] 全自动部署完成。",
        "usage_instructions": "[TIP] 请将系统音频输出切换到 BlackHole 2ch，并在使用完毕后停止引擎。",
        "output_device_set": "[OK] 输出设备设置为: {device}",
        "prepare_config": "[..] 准备生成 CamillaDSP 配置文件:",
        "physical_source_label": "base",
        "target_cosplay_label": "target",
        "csv_label": "CSV",
        "peq_table_band": "频段",
        "peq_table_type": "类型",
        "peq_table_frequency": "频率 (Hz)",
        "peq_table_gain": "增益 (dB)",
        "peq_table_q": "Q",
        "welcome": "EQ Cosplay  --  终端工具 (Core Calculation)",
        "welcome_sep": "",
        "sample_rate_prompt": "\n请选择目标采样率：\n  [1] 44100 Hz\n  [2] 48000 Hz  （默认）\n  [3] 88200 Hz\n  [4] 96000 Hz\n  [5] 192000 Hz\n请输入选择 [1-5]：",
        "invalid_selection": "[WARN] 选择无效，已使用默认 {default} Hz。",
        "platform_detected": "[INFO] 当前系统：{platform_name} ({architecture})",
        "virtual_device_missing_windows": "[WARN] 未检测到 VB-Audio Virtual Cable。请访问 https://vb-audio.com/Cable/ 安装后按 Enter 继续。",
        "virtual_device_missing_linux": "[WARN] 未检测到虚拟音频设备。请安装 ALSA loopback / PipeWire 虚拟输出后按 Enter 继续。",
        "press_enter_to_continue": "按 Enter 继续...",
        "goodbye": "再见。",
        "step1_prompt": "\n第一步  当前佩戴的耳机型号（输入 q 退出）: ",
        "step2_prompt": "\n第二步  想 Cosplay 的耳机型号（输入 q 退出）: ",
        "debug_prompt": "\n是否开启 Debug 调试模式？(y/n，默认 n): ",
        "yaml_dump_header": "\nYAML 配置转储",
        "debug_enabled": "[INFO] Debug 模式已开启。将打印 YAML 并以详细日志启动 CamillaDSP。",
        "audio_device_list_header": "\n音频设备列表",
        "deploy_prompt": "\n是否部署完整的 CamillaDSP 环境？(y/n): ",
        "install_blackhole_prompt": "是否自动安装 BlackHole 2ch？(y/n): ",
        "output_device_prompt": "\n播放（输出）设备名称\n  直接回车使用默认: {default_name}\n> ",
        "output_device_macos_note": "[TIP] macOS：请使用真实的 CoreAudio 播放设备名（system_profiler SPAudioDataType）。不要填 BlackHole 2ch，那是采集设备。",
        "full_auto_deploy": "[..] 开始部署 CamillaDSP 全自动环境...",
        "process_exited": "[WARN] CamillaDSP 进程已退出。",
        "cannot_generate_peq": "[WARN] 无法生成 PEQ：缺少源或目标 CSV。请检查网络或耳机型号。",
        "partial_blackhole_failure": "[WARN] BlackHole 安装失败，继续但可能无法正常工作。",
        "user_cancelled_blackhole": "[WARN] 用户取消安装 BlackHole。",
        "user_cancelled_deploy": "[WARN] 用户取消 CamillaDSP 部署。",
        "use_default_device": "{default_name}",
        "plugin_note": "[TIP] 请将上述参数填入均衡器软件（如 Equalizer APO、Wavelet 等）。",
        "unknown_error": "[ERR] 发生未知错误: {error}",
        "peq_table_title": "推荐 PEQ 设置  (参数均衡器)",
        "delta_summary_heading": "Delta 曲线概览  (Target - Source)",
        "delta_peak": "  最大提升:     +{peak:.2f} dB",
        "delta_valley": "  最大衰减:     {valley:.2f} dB",
        "delta_mean": "  平均差异:     {mean:.2f} dB",
        "section_separator": "",
        "provider_list_header": "\n检测到该耳机有多个提供者：",
        "provider_menu_default_note": "直接回车则默认选择第 1 个。",
        "provider_choice_prompt": "请输入提供者序号: ",
        "provider_invalid_selection": "[WARN] 选择无效，默认选择第 1 个。",
        "delta_clipping_warning": "[WARN] 检测到峰值提升，需要调整前级增益以防止削波。",
        "preamp_selection_prompt": "\n选择前级增益模式：",
        "preamp_option_safe": "  [1] 绝对安全  -({peak:.2f} + 0.2) dB  确保零削波",
        "preamp_option_moderate": "  [2] 折中动态  -({peak:.2f} / 2.0) dB  保留更多整体音量",
        "preamp_option_custom": "  [3] 自定义    手动输入浮点数值（如 -4.5）",
        "preamp_custom_input_prompt": "前级增益 (dB，负数表示衰减): ",
        "preamp_invalid_input": "[ERR] 输入无效，请输入有效的数字。",
        "preamp_applied": "[OK] 已应用前级增益：{preamp:.2f} dB",
        "no_preamp_needed": "[INFO] 无需前级增益调整（峰值 <= 0 dB）。",
        "main_program_started": "[OK] 主程序已启动。",
        "csv_url_not_found": "[WARN] 未能为耳机 '{display_name}' 找到可用 CSV。请尝试其他型号或放入 offline_csvs。",
        "csv_download_failed_retry": "[WARN] 下载耳机 '{display_name}' 的 CSV 失败。请尝试其他型号或使用 offline_csvs。",
        "capture_device_as_playback": "[WARN] '{user_input}' 是虚拟采集设备，不能用作播放输出。已改用 '{default_name}'。",
        "camilladsp_exited_early": "进程立即退出，退出码 {code}。请检查采集/播放设备名称与采样率。",
        "camilladsp_process_not_started": "进程未能启动",
        "camilladsp_log_window_title": "CamillaDSP 日志 -- EQ Cosplay",
        "camilladsp_log_window_opened": "[OK] 已打开 CamillaDSP 日志窗口。\n     日志文件：{path}",
        "camilladsp_log_window_failed": "[WARN] 无法打开独立日志窗口（{error}）。将在本窗口流式输出日志。",
        "camilladsp_log_file_hint": "[INFO] CamillaDSP 日志文件：{path}",
        "camilladsp_engine_running": "[OK] EQ 引擎运行中。\n     主窗口：控制  |  独立窗口：CamillaDSP 日志",
        "camilladsp_log_end_marker": "===== CamillaDSP 已停止 =====",
        "deploy_skipped": "[INFO] 已跳过 CamillaDSP 部署。仍可将上方 PEQ 参数用于其他均衡器软件。",
        "default_playback_headphones": "外置耳机",
        "default_playback_speakers": "扬声器",
        "default_playback_linux": "default",
        "provider_single_source": "[INFO] 该耳机仅有一个数据来源：{provider}",
        "saved_presets_prompt": "\n本机已保存 {count} 套方案。\n是否直接启用已保存的 CamillaDSP 方案？(y/n，默认 n): ",
        "saved_presets_header": "已保存的方案",
        "saved_presets_choice_prompt": "请输入方案序号（直接回车取消）: ",
        "saved_presets_invalid": "[WARN] 选择无效，已跳过已保存方案。",
        "saved_presets_cancelled": "[INFO] 已跳过保存方案，开始新的 cosplay 计算。",
        "saved_presets_selected": "[OK] 已选择方案: {name}",
        "saved_presets_empty": "[INFO] 暂无已保存方案。新生成的 YAML 将保存在 {path}。",
        "saved_presets_dir": "[INFO] 方案目录: {path}",
        "saved_presets_saved": "[OK] 配置已保存到: {path}",
        "saved_presets_launch": "[..] 正在用已保存方案启动 CamillaDSP...",
        "saved_presets_missing_file": "[ERR] 方案文件不存在: {path}",
        # --- GUI ---
        "gui_window_title": "EQ Cosplay",
        "gui_language": "界面语言",
        "gui_presets": "已保存方案",
        "gui_refresh": "刷新",
        "gui_load_start": "加载并启动",
        "gui_cosplay": "Cosplay",
        "gui_sample_rate": "采样率 (Hz)",
        "gui_source": "当前耳机 (Source)",
        "gui_target": "目标耳机 (Target)",
        "gui_playback": "播放设备",
        "gui_output_resolved": "[INFO] 播放设备已解析: '{user}' → '{device}'\n",
        "gui_preamp": "前级增益 (Pre-amp)",
        "gui_preamp_safe": "安全  −(peak+0.2) dB",
        "gui_preamp_moderate": "折中  −(peak/2) dB",
        "gui_preamp_custom": "自定义",
        "gui_preamp_none": "不调整 (0 dB)",
        "gui_custom_db": "自定义 dB",
        "gui_debug": "CamillaDSP Debug 日志",
        "gui_calc": "计算校正",
        "gui_deploy": "部署并启动 CamillaDSP",
        "gui_stop": "停止引擎",
        "gui_peq": "推荐 PEQ",
        "gui_log": "日志",
        "gui_tip": "提示：10 段 IIR 可填入其他均衡器；启用 FIR 时完整残差精度需 CamillaDSP 卷积。",
        "gui_tip_header": "提示与环境",
        "gui_platform": "平台",
        "gui_capture": "捕获",
        "gui_logs_dir": "日志目录",
        "gui_status_loading": "加载数据库…",
        "gui_status_ready": "就绪 · {count} 型号",
        "gui_status_db_fail": "数据库加载失败",
        "gui_status_busy_wait": "请等待当前任务完成。",
        "gui_status_calc": "计算中…",
        "gui_status_calc_fail": "计算失败",
        "gui_status_calc_done": "计算完成 · 可部署",
        "gui_status_deploy": "部署中…",
        "gui_status_deploy_fail": "部署失败",
        "gui_status_engine_fail": "引擎启动失败",
        "gui_status_running": "引擎运行中",
        "gui_status_stopped": "引擎已停止",
        "gui_status_exited": "引擎已退出",
        "gui_status_preset": "启动预设…",
        "gui_status_download": "下载 CamillaDSP…",
        "gui_fir_on": "FIR 已启用 · {taps} taps · 联合 RMSE {rmse}",
        "gui_fir_off": "仅 IIR · RMSE {rmse}（未触发 FIR）",
        "gui_fir_paused": "仅 IIR · FIR 可重新开启 · IIR RMSE {rmse}",
        "gui_stop_fir": "停止 FIR",
        "gui_enable_fir": "开启 FIR",
        "gui_status_stop_fir": "正在关闭 FIR 并重新启动…",
        "gui_status_enable_fir": "正在开启 FIR 并重新启动…",
        "gui_fir_stopped_log": "[INFO] 已关闭 FIR。正在以仅 IIR 链路重启 CamillaDSP。\n",
        "gui_fir_enabled_log": "[INFO] 已重新开启 FIR。正在以 FIR 卷积链路重启 CamillaDSP。\n",
        "gui_msg_stop_fir_need": "当前会话未启用 FIR。",
        "gui_msg_enable_fir_need": "当前没有可开启的 FIR 残差。",
        "gui_metrics": "响应峰值 {peak:+.2f} dB  |  电平对齐偏移 {offset:+.2f} dB",
        "gui_db_ok": "[OK] 数据库就绪，共 {count} 个条目。\n",
        "gui_calc_ok": "[OK] 计算完成。可点击「部署并启动 CamillaDSP」。\n",
        "gui_session_log": "[INFO] 会话日志: {path}\n",
        "gui_logs_info": "[INFO] 日志目录: {path}\n",
        "gui_config_ok": "[OK] 配置: {path}\n",
        "gui_engine_exit": "[WARN] CamillaDSP 已退出 (code={code}).\n",
        "gui_engine_stopped": "[OK] 已停止 CamillaDSP。\n",
        "gui_msg_db_fail": "加载 AutoEq 数据库失败:\n{error}",
        "gui_msg_db_not_ready": "数据库尚未加载完成。",
        "gui_msg_fill_models": "请填写当前耳机与目标耳机。",
        "gui_msg_not_found": "未找到耳机: {name}",
        "gui_msg_calc_fail": "计算失败:\n{error}",
        "gui_msg_need_calc": "请先完成计算。",
        "gui_msg_engine_running": "引擎已在运行，请先停止。",
        "gui_msg_bh_ask": "未检测到 BlackHole 2ch，是否尝试安装？",
        "gui_msg_bh_fail": "BlackHole 安装失败或未完成。",
        "gui_msg_bh_later": "可稍后手动安装虚拟声卡。",
        "gui_msg_virt_other": "请确认已安装虚拟音频线（Windows: VB-Cable / Linux: loopback）。",
        "gui_msg_cdsp_ask": "未找到 CamillaDSP，是否立即下载？",
        "gui_msg_cdsp_fail": "CamillaDSP 下载失败。",
        "gui_msg_deploy_fail": "部署失败:\n{error}",
        "gui_msg_start_fail": "CamillaDSP 未能启动，请查看日志。",
        "gui_msg_pick_preset": "请选择已保存的方案。",
        "gui_msg_ok": "确定",
        "gui_msg_cancel": "取消",
        "gui_provider_model": "型号",
        "gui_provider_source": "数据来源",
        "gui_col_band": "#",
        "gui_col_type": "类型",
        "gui_col_freq": "Hz",
        "gui_col_gain": "dB",
        "gui_col_q": "Q",
    },
    "ja": {
        "retry_request": "[WARN] リクエスト失敗 ({exc})。{wait_time:.1f}秒後に再試行 ({attempt}/{retries})...",
        "parse_index_empty": "[WARN] AutoEq INDEX.md から有効なエントリを解析できませんでした。",
        "loading_database": "[..] AutoEq GitHub に接続して最新データベースを読み込んでいます...",
        "database_loaded": "[OK] {count} 件のヘッドホンエントリを読み込みました。",
        "database_failed": "[WARN] AutoEq GitHub から INDEX.md を読み込めませんでした: {error}",
        "using_fallback_db": "[INFO] ローカルのフォールバックデータベースを使用しています。",
        "db_not_loaded": "[ERR] AutoEq データベースが読み込まれていません。",
        "searching_headphone": "\n[..] '{user_input}' に最も近い {prompt_type} を検索しています...",
        "no_match_found": "[ERR] 一致するヘッドホンが見つかりません。スペルまたはより完全なモデル名を確認してください。",
        "match_success": "[OK] マッチ完了 -- {prompt_type}: {display_name}",
        "no_csv_in_dir": "[WARN] ディレクトリ {directory} に .csv ファイルが見つかりません。",
        "cannot_access_dir": "[WARN] AutoEq ディレクトリ {path} にアクセスできません: {error}",
        "downloading_file": "[..] ダウンロード中: {filename} ...",
        "download_failed": "[WARN] ファイルのダウンロードに失敗しました: {error}",
        "download_failed_label": "ダウンロード失敗",
        "offline_csv_missing": "[WARN] オフライン CSV が見つかりません: {path}。offline_csvs に配置してください。",
        "network_exit": "[ERR] ネットワークエラーまたはダウンロード失敗。プログラムを終了します。",
        "no_relative_path": "[WARN] ヘッドホン '{display_name}' に相対パスがありません。",
        "using_local_csv": "[INFO] ローカルオフライン CSV を使用: {path}",
        "calculating_peq": "\n[..] 周波数特性差を計算し、10 バンド IIR PEQ をフィッティングしています...",
        "peq_complete": "[OK] 10 バンド IIR PEQ 完了。RMSE: {rmse:.3f} dB",
        "peq_standard_mode": "[INFO] 固定 10 バンド IIR PEQ（Lowshelf + 8×Peaking + Highshelf）を使用します。",
        "fir_precision_mode": "[INFO] 重要帯域で大きな差を検出: {regions}。最小位相 FIR 残差補正を追加します。",
        "fir_skipped_mode": "[INFO] 重要帯域は許容内 — FIR 残差段をスキップ（IIR のみ）。",
        "fir_complete": "[OK] FIR 残差を設計（{taps} taps）。残差 RMSE: {rmse:.3f} dB、合成 RMSE: {combined:.3f} dB",
        "fir_saved": "[OK] FIR インパルス応答を保存:\n     L: {left}\n     R: {right}",
        "fir_triggered_banner": "\n========== FIR 畳み込みが有効 ==========\n"
            "[FIR] 重要帯域の差が大きいため、精密段は追加 IIR ではなく\n"
            "      最小位相 FIR 畳み込みで残差を補正します。\n"
            "[FIR] 上記 10 バンド IIR は他 EQ 向けの音色の骨格です。\n"
            "[FIR] 残差までの精度には CamillaDSP の Conv と WAV が必要です。\n"
            "============================================",
        "fir_camilladsp_deploy_notice": "\n========== CamillaDSP + FIR デプロイ ==========\n"
            "[CamillaDSP] チェーン: Preamp → FIR Conv (L/R) → 10-band IIR PEQ。\n"
            "[CamillaDSP] FIR WAV は YAML と同じ場所に必要（設定は絶対パス）。\n"
            "[CamillaDSP] *_fir_left.wav / *_fir_right.wav を削除しないでください。\n"
            "[CamillaDSP] 遅延は FIR 長/サンプリング周波数に依存します。\n"
            "[CamillaDSP] システム出力を仮想デバイスへ向けて再生してください。\n"
            "============================================",
        "fir_camilladsp_running_notice": "[CamillaDSP/FIR] FIR 畳み込みモードでエンジン稼働中。\n"
            "     YAML と FIR WAV をディスク上に保持してください。",
        "deploy_iir_only_notice": "[CamillaDSP] IIR のみのプリセット（FIR なし）。重要帯域は許容内です。",
        "deploy_skipped_with_fir": "[WARN] FIR 残差は設計済みですが CamillaDSP は未デプロイです。\n"
            "       表示中の PEQ は 10 バンド IIR のみ。細部は FIR が必要です。\n"
            "       完全精度には再実行してデプロイ (y) を選んでください。",
        "deploy_prompt_with_fir": "\nFIR 残差の準備ができました。FIR 畳み込み付きで CamillaDSP をデプロイしますか？(y/n): ",
        "installing_blackhole": "[..] BlackHole 2ch をインストールしています...",
        "homebrew_missing": "[ERR] Homebrew がインストールされていません。",
        "blackhole_installed": "[OK] BlackHole 2ch はインストール済みです。",
        "blackhole_install_failed": "[WARN] BlackHole のインストールに失敗しました: {error}",
        "blackhole_install_error": "[ERR] BlackHole のインストール中にエラー: {error}",
        "blackhole_not_installed": "[INFO] BlackHole 2ch がインストールされていません。",
        "camilladsp_not_installed": "[INFO] CamillaDSP がインストールされていません。",
        "camilladsp_download_fail_continue": "[WARN] CamillaDSP のダウンロードに失敗。デプロイを続行できません。",
        "download_camilladsp": "[..] GitHub から CamillaDSP をダウンロードしています...",
        "camilladsp_asset_not_found": "[ERR] 現在のプラットフォーム用 CamillaDSP アセットが見つかりません。",
        "camilladsp_download_error": "[ERR] CamillaDSP のダウンロード中にエラー: {error}",
        "camilladsp_download_success": "[OK] CamillaDSP のダウンロードと構成に成功しました。",
        "config_generated": "[OK] CamillaDSP 設定ファイルを生成しました: {path}",
        "starting_camilladsp": "[..] CamillaDSP を起動しています...",
        "camilladsp_failed": "[ERR] CamillaDSP の起動に失敗しました: {error}",
        "camilladsp_started": "[OK] CamillaDSP が正常に起動しました。",
        "camilladsp_executable_missing": "[ERR] アーカイブ内に CamillaDSP 実行ファイルが見つかりません。",
        "camilladsp_installed": "[OK] CamillaDSP は既にインストールされています。",
        "log_prefix": "[CamillaDSP]",
        "exit_prompt": "\n終了するには 'q' を入力して Enter を押してください。",
        "camilladsp_monitor_prompt": "\n停止するには q を入力して Enter を押してください。",
        "camilladsp_stopped": "[OK] CamillaDSP を停止しました。",
        "camilladsp_previous_stopped": "[INFO] 稼働中の CamillaDSP を {count} 件停止しました（同時に 1 インスタンスのみ）。",
        "auto_deploy_complete": "[OK] 自動デプロイが完了しました。",
        "usage_instructions": "[TIP] システム出力を BlackHole 2ch に設定し、完了したらエンジンを停止してください。",
        "output_device_set": "[OK] 出力デバイス: {device}",
        "prepare_config": "[..] CamillaDSP 設定ファイルを作成しています:",
        "physical_source_label": "base",
        "target_cosplay_label": "target",
        "csv_label": "CSV",
        "peq_table_band": "バンド",
        "peq_table_type": "タイプ",
        "peq_table_frequency": "周波数 (Hz)",
        "peq_table_gain": "ゲイン (dB)",
        "peq_table_q": "Q",
        "welcome": "EQ Cosplay  --  ターミナルツール (Core Calculation)",
        "welcome_sep": "",
        "sample_rate_prompt": "\nターゲットサンプリングレート:\n  [1] 44100 Hz\n  [2] 48000 Hz  (デフォルト)\n  [3] 88200 Hz\n  [4] 96000 Hz\n  [5] 192000 Hz\n選択 [1-5]: ",
        "invalid_selection": "[WARN] 無効な選択です。デフォルト {default} Hz を使用します。",
        "platform_detected": "[INFO] プラットフォーム: {platform_name} ({architecture})",
        "virtual_device_missing_windows": "[WARN] VB-Audio Virtual Cable が検出されません。https://vb-audio.com/Cable/ から導入後 Enter。",
        "virtual_device_missing_linux": "[WARN] 仮想オーディオデバイスが検出されません。導入後 Enter を押してください。",
        "press_enter_to_continue": "Enter を押して続行...",
        "goodbye": "さようなら。",
        "step1_prompt": "\nステップ1  現在のヘッドホンモデル（終了: q）: ",
        "step2_prompt": "\nステップ2  Cosplay したいモデル（終了: q）: ",
        "debug_prompt": "\nデバッグモードを有効にしますか？(y/n、デフォルト n): ",
        "yaml_dump_header": "\nYAML 設定ダンプ",
        "debug_enabled": "[INFO] デバッグモード有効。YAML を表示し詳細ログで起動します。",
        "audio_device_list_header": "\nオーディオデバイス一覧",
        "deploy_prompt": "\nCamillaDSP 環境をデプロイしますか？(y/n): ",
        "install_blackhole_prompt": "BlackHole 2ch を自動インストールしますか？(y/n): ",
        "output_device_prompt": "\n再生（出力）デバイス名\n  Enter でデフォルト: {default_name}\n> ",
        "output_device_macos_note": "[TIP] macOS: 実際の CoreAudio 再生デバイス名を使用（system_profiler SPAudioDataType）。BlackHole 2ch はキャプチャ用です。",
        "full_auto_deploy": "[..] CamillaDSP の自動デプロイを開始します...",
        "process_exited": "[WARN] CamillaDSP プロセスが終了しました。",
        "cannot_generate_peq": "[WARN] PEQ を生成できません。CSV またはネットワークを確認してください。",
        "partial_blackhole_failure": "[WARN] BlackHole のインストールに失敗。動作しない可能性があります。",
        "user_cancelled_blackhole": "[WARN] BlackHole のインストールをキャンセルしました。",
        "user_cancelled_deploy": "[WARN] CamillaDSP のデプロイをキャンセルしました。",
        "use_default_device": "{default_name}",
        "plugin_note": "[TIP] 上記パラメータをイコライザー（Equalizer APO / Wavelet 等）に入力してください。",
        "unknown_error": "[ERR] 不明なエラー: {error}",
        "peq_table_title": "推奨 PEQ 設定  (パラメトリック EQ)",
        "delta_summary_heading": "Delta カーブ概要  (Target - Source)",
        "delta_peak": "  最大ブースト:   +{peak:.2f} dB",
        "delta_valley": "  最大減衰:       {valley:.2f} dB",
        "delta_mean": "  平均差:         {mean:.2f} dB",
        "section_separator": "",
        "provider_list_header": "\n複数のプロバイダーが見つかりました:",
        "provider_menu_default_note": "Enter で最初のプロバイダーを選択します。",
        "provider_choice_prompt": "プロバイダー番号: ",
        "provider_invalid_selection": "[WARN] 無効な選択です。最初のプロバイダーを使用します。",
        "delta_clipping_warning": "[WARN] ピークブースト検出。クリッピング防止のためプリアンプ調整が必要です。",
        "preamp_selection_prompt": "\nプリアンプモード:",
        "preamp_option_safe": "  [1] セーフ      -({peak:.2f} + 0.2) dB",
        "preamp_option_moderate": "  [2] モデレート  -({peak:.2f} / 2.0) dB",
        "preamp_option_custom": "  [3] カスタム    独自の値（例: -4.5）",
        "preamp_custom_input_prompt": "プリアンプ値 dB（減衰は負数）: ",
        "preamp_invalid_input": "[ERR] 無効な入力です。数値を入力してください。",
        "preamp_applied": "[OK] プリアンプを適用: {preamp:.2f} dB",
        "no_preamp_needed": "[INFO] プリアンプ調整は不要です（ピーク <= 0 dB）。",
        "main_program_started": "[OK] メインプログラムを起動しました。",
        "csv_url_not_found": "[WARN] '{display_name}' の CSV URL が見つかりません。別モデルまたは offline_csvs を使用してください。",
        "csv_download_failed_retry": "[WARN] '{display_name}' の CSV ダウンロードに失敗しました。",
        "capture_device_as_playback": "[WARN] '{user_input}' はキャプチャ用です。デフォルト '{default_name}' に切り替えます。",
        "camilladsp_exited_early": "プロセスがすぐに終了（コード {code}）。デバイス名とサンプリングレートを確認してください。",
        "camilladsp_process_not_started": "プロセスを開始できませんでした",
        "camilladsp_log_window_title": "CamillaDSP ログ -- EQ Cosplay",
        "camilladsp_log_window_opened": "[OK] ログウィンドウを開きました。\n     ログファイル: {path}",
        "camilladsp_log_window_failed": "[WARN] ログウィンドウを開けません（{error}）。この画面に表示します。",
        "camilladsp_log_file_hint": "[INFO] CamillaDSP ログファイル: {path}",
        "camilladsp_engine_running": "[OK] EQ エンジン稼働中。\n     メイン: 操作  |  別ウィンドウ: ログ",
        "camilladsp_log_end_marker": "===== CamillaDSP を停止しました =====",
        "deploy_skipped": "[INFO] デプロイをスキップしました。上記 PEQ は他の EQ でも利用できます。",
        "default_playback_headphones": "外部ヘッドフォン",
        "default_playback_speakers": "スピーカー",
        "default_playback_linux": "default",
        "provider_single_source": "[INFO] このヘッドホンの測定ソースは 1 件のみです: {provider}",
        "saved_presets_prompt": "\nこのマシンに保存済みプリセットが {count} 件あります。\n保存済み CamillaDSP プリセットを今すぐ読み込みますか？(y/n、デフォルト n): ",
        "saved_presets_header": "保存済みプリセット",
        "saved_presets_choice_prompt": "プリセット番号を入力（Enter でキャンセル）: ",
        "saved_presets_invalid": "[WARN] 無効な選択です。保存済みプリセットをスキップします。",
        "saved_presets_cancelled": "[INFO] 保存済みプリセットをスキップし、新規 cosplay 計算を開始します。",
        "saved_presets_selected": "[OK] 選択したプリセット: {name}",
        "saved_presets_empty": "[INFO] 保存済みプリセットはまだありません。新規 YAML は {path} に保存されます。",
        "saved_presets_dir": "[INFO] プリセットフォルダ: {path}",
        "saved_presets_saved": "[OK] 設定を保存しました: {path}",
        "saved_presets_launch": "[..] 保存済みプリセットで CamillaDSP を起動しています...",
        "saved_presets_missing_file": "[ERR] プリセットファイルが見つかりません: {path}",
        # --- GUI ---
        "gui_window_title": "EQ Cosplay",
        "gui_language": "言語",
        "gui_presets": "保存済みプリセット",
        "gui_refresh": "更新",
        "gui_load_start": "読込して起動",
        "gui_cosplay": "Cosplay",
        "gui_sample_rate": "サンプリング周波数 (Hz)",
        "gui_source": "現在のヘッドホン (Source)",
        "gui_target": "ターゲットヘッドホン",
        "gui_playback": "再生デバイス",
        "gui_output_resolved": "[INFO] 再生デバイスを解決: '{user}' → '{device}'\n",
        "gui_preamp": "プリアンプ",
        "gui_preamp_safe": "セーフ  −(peak+0.2) dB",
        "gui_preamp_moderate": "モデレート  −(peak/2) dB",
        "gui_preamp_custom": "カスタム",
        "gui_preamp_none": "なし (0 dB)",
        "gui_custom_db": "カスタム dB",
        "gui_debug": "CamillaDSP デバッグログ",
        "gui_calc": "計算",
        "gui_deploy": "デプロイして CamillaDSP 起動",
        "gui_stop": "エンジン停止",
        "gui_peq": "推奨 PEQ",
        "gui_log": "ログ",
        "gui_tip": "ヒント: 10 バンド IIR は他 EQ でも利用可。FIR 有効時の残差精度には CamillaDSP 畳み込みが必要です。",
        "gui_tip_header": "情報",
        "gui_platform": "プラットフォーム",
        "gui_capture": "キャプチャ",
        "gui_logs_dir": "ログフォルダ",
        "gui_status_loading": "データベース読込中…",
        "gui_status_ready": "準備完了 · {count} 機種",
        "gui_status_db_fail": "DB 読込失敗",
        "gui_status_busy_wait": "現在の処理が終わるまでお待ちください。",
        "gui_status_calc": "計算中…",
        "gui_status_calc_fail": "計算失敗",
        "gui_status_calc_done": "完了 · デプロイ可能",
        "gui_status_deploy": "デプロイ中…",
        "gui_status_deploy_fail": "デプロイ失敗",
        "gui_status_engine_fail": "エンジン起動失敗",
        "gui_status_running": "エンジン稼働中",
        "gui_status_stopped": "エンジン停止",
        "gui_status_exited": "エンジン終了",
        "gui_status_preset": "プリセット起動中…",
        "gui_status_download": "CamillaDSP をダウンロード中…",
        "gui_fir_on": "FIR 有効 · {taps} taps · 合成 RMSE {rmse}",
        "gui_fir_off": "IIR のみ · RMSE {rmse}（FIR 未使用）",
        "gui_fir_paused": "IIR のみ · FIR 再有効化可 · IIR RMSE {rmse}",
        "gui_stop_fir": "FIR 停止",
        "gui_enable_fir": "FIR 有効化",
        "gui_status_stop_fir": "FIR を無効化して再起動中…",
        "gui_status_enable_fir": "FIR を有効化して再起動中…",
        "gui_fir_stopped_log": "[INFO] FIR を無効化しました。IIR のみで CamillaDSP を再起動します。\n",
        "gui_fir_enabled_log": "[INFO] FIR を再有効化しました。FIR 畳み込みで CamillaDSP を再起動します。\n",
        "gui_msg_stop_fir_need": "このセッションでは FIR は有効ではありません。",
        "gui_msg_enable_fir_need": "有効化できる FIR 残差がありません。",
        "gui_metrics": "応答ピーク {peak:+.2f} dB  |  レベルオフ {offset:+.2f} dB",
        "gui_db_ok": "[OK] データベース準備完了: {count} 件。\n",
        "gui_calc_ok": "[OK] 計算完了。CamillaDSP をデプロイできます。\n",
        "gui_session_log": "[INFO] セッションログ: {path}\n",
        "gui_logs_info": "[INFO] ログフォルダ: {path}\n",
        "gui_config_ok": "[OK] 設定: {path}\n",
        "gui_engine_exit": "[WARN] CamillaDSP 終了 (code={code}).\n",
        "gui_engine_stopped": "[OK] CamillaDSP を停止しました。\n",
        "gui_msg_db_fail": "AutoEq DB の読込に失敗:\n{error}",
        "gui_msg_db_not_ready": "データベースの準備がまだです。",
        "gui_msg_fill_models": "ソースとターゲットの機種を入力してください。",
        "gui_msg_not_found": "一致なし: {name}",
        "gui_msg_calc_fail": "計算失敗:\n{error}",
        "gui_msg_need_calc": "先に計算してください。",
        "gui_msg_engine_running": "エンジン稼働中です。先に停止してください。",
        "gui_msg_bh_ask": "BlackHole 2ch が見つかりません。インストールしますか？",
        "gui_msg_bh_fail": "BlackHole のインストールに失敗しました。",
        "gui_msg_bh_later": "仮想オーディオは後でインストールできます。",
        "gui_msg_virt_other": "仮想ケーブルを確認してください (Windows: VB-Cable / Linux: loopback)。",
        "gui_msg_cdsp_ask": "CamillaDSP がありません。ダウンロードしますか？",
        "gui_msg_cdsp_fail": "CamillaDSP のダウンロードに失敗しました。",
        "gui_msg_deploy_fail": "デプロイ失敗:\n{error}",
        "gui_msg_start_fail": "CamillaDSP を起動できません。ログを確認してください。",
        "gui_msg_pick_preset": "保存済みプリセットを選択してください。",
        "gui_msg_ok": "OK",
        "gui_msg_cancel": "キャンセル",
        "gui_provider_model": "モデル",
        "gui_provider_source": "提供元",
        "gui_col_band": "#",
        "gui_col_type": "タイプ",
        "gui_col_freq": "Hz",
        "gui_col_gain": "dB",
        "gui_col_q": "Q",
    },
}

# 备用数据库，当网络不可用时使用本地离线 CSV
FALLBACK_ENTRIES = {}
for name in [
    "Sennheiser HD800S",
    "Sennheiser HD650",
    "AKG K701",
    "Sony WH-1000XM4",
    "Sony MDR-Z1R",
    "Apple AirPods Max",
    "HIFIMAN Arya",
]:
    safe_name = re.sub(r"[^\w\-_.]", '_', name)
    local_csv_path = str(OFFLINE_CSV_DIR / f"{safe_name}.csv")
    FALLBACK_ENTRIES[name.lower()] = [
        {
            "display_name": name,
            "relative_path": local_csv_path,
            "provider": 'offline',
        }
    ]

def translate(message_id: str, **kwargs) -> str:
    template = MESSAGES.get(LANG, MESSAGES['en']).get(message_id, message_id)
    try:
        return template.format(**kwargs)
    except Exception:
        return template


def set_language(code: str) -> str:
    """切换界面语言（en / zh / ja），返回实际生效的代码。"""
    global LANG
    code = (code or "").strip().lower()
    if code.startswith("zh"):
        code = "zh"
    elif code.startswith("ja"):
        code = "ja"
    elif code.startswith("en"):
        code = "en"
    if code not in MESSAGES:
        code = "en"
    LANG = code
    return LANG


def available_languages() -> list[tuple[str, str]]:
    """返回 (code, 显示名) 列表。"""
    return [
        ("en", "English"),
        ("zh", "中文"),
        ("ja", "日本語"),
    ]


# UI 主题色（gum 边框 / 标题）
UI_ACCENT_COLOR = "#00d7ff"


def _color_enabled() -> bool:
    if os.environ.get('NO_COLOR') is not None:
        return False
    if os.environ.get('TERM') in (None, 'dumb'):
        return False
    try:
        return sys.stdout.isatty()
    except Exception:
        return False


def resolve_gum() -> str | None:
    """定位 gum 可执行文件。"""
    return shutil.which('gum')


def style_text(text: str) -> str:
    """为 [OK]/[WARN]/[ERR]/[INFO]/[TIP]/[..] 标签着色（无 emoji）。"""
    if not _color_enabled() or not text:
        return text
    # ANSI: bold + color for status tags only
    mapping = (
        ('[OK]', '\033[1;32m[OK]\033[0m'),
        ('[WARN]', '\033[1;33m[WARN]\033[0m'),
        ('[ERR]', '\033[1;31m[ERR]\033[0m'),
        ('[INFO]', '\033[1;36m[INFO]\033[0m'),
        ('[TIP]', '\033[1;34m[TIP]\033[0m'),
        ('[..]', '\033[2m[..]\033[0m'),
    )
    for plain, colored in mapping:
        if plain in text:
            text = text.replace(plain, colored)
    return text


def rule_line(char: str = '-', width: int = 56) -> str:
    return char * width


def _rows_to_csv(headers: list[str], rows: list[list[str]]) -> str:
    """将表头与行转为 CSV 文本供 gum table 使用。"""
    import csv
    import io

    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator='\n')
    writer.writerow(headers)
    for row in rows:
        writer.writerow([str(c) for c in row])
    return buf.getvalue()


def print_table_ascii(headers: list[str], rows: list[list[str]]) -> None:
    """无 gum 时的 ASCII 表格回退。"""
    column_widths = []
    for col_index in range(len(headers)):
        max_width = get_display_width(headers[col_index])
        for row in rows:
            if col_index < len(row):
                max_width = max(max_width, get_display_width(row[col_index]))
        column_widths.append(max_width)

    separator_width = sum(column_widths) + 3 * (len(column_widths) - 1)
    header_cells = [pad_text(headers[i], column_widths[i]) for i in range(len(headers))]
    print(' | '.join(header_cells))
    print('-' * max(separator_width, 20))
    for row in rows:
        cells = [
            pad_text(row[i] if i < len(row) else '', column_widths[i])
            for i in range(len(headers))
        ]
        print(' | '.join(cells))


def print_gum_table(headers: list[str], rows: list[list[str]]) -> bool:
    """用 gum table 静态打印表格，边框色 #00d7ff。成功返回 True。"""
    gum = resolve_gum()
    if not gum or not rows:
        return False
    csv_data = _rows_to_csv(headers, rows)
    cmd = [
        gum,
        'table',
        '--print',
        '--border', 'rounded',
        '--border.foreground', UI_ACCENT_COLOR,
        '--header.foreground', UI_ACCENT_COLOR,
        '--cell.foreground', '252',
    ]
    try:
        result = subprocess.run(
            cmd,
            input=csv_data,
            text=True,
            timeout=30,
            env={**os.environ, 'CLICOLOR_FORCE': '1'},
        )
        return result.returncode == 0
    except Exception:
        return False


def print_table(headers: list[str], rows: list[list[str]]) -> None:
    """优先 gum table（边框 #00d7ff），否则 ASCII 回退。"""
    if not print_gum_table(headers, rows):
        print_table_ascii(headers, rows)


def print_banner(title: str) -> None:
    """打印简洁横幅标题；优先 gum style 圆角边框 + 强调色 #00d7ff。"""
    gum = resolve_gum()
    if gum:
        try:
            result = subprocess.run(
                [
                    gum, 'style',
                    '--border', 'rounded',
                    '--border-foreground', UI_ACCENT_COLOR,
                    '--foreground', UI_ACCENT_COLOR,
                    '--align', 'center',
                    '--width', str(max(48, get_display_width(title) + 8)),
                    '--padding', '0 2',
                    title,
                ],
                text=True,
                timeout=10,
                env={**os.environ, 'CLICOLOR_FORCE': '1'},
            )
            if result.returncode == 0:
                return
        except Exception:
            pass

    width = max(56, get_display_width(title) + 4)
    top = '+' + '-' * (width - 2) + '+'
    pad = max(width - 2 - get_display_width(title), 0)
    left = pad // 2
    right = pad - left
    mid = '|' + ' ' * left + title + ' ' * right + '|'
    print(top)
    print(mid)
    print(top)


def print_section(title: str) -> None:
    """小节标题：优先 gum style（#00d7ff），否则分隔线。"""
    print()
    gum = resolve_gum()
    if gum:
        try:
            result = subprocess.run(
                [
                    gum, 'style',
                    '--foreground', UI_ACCENT_COLOR,
                    '--bold',
                    title,
                ],
                text=True,
                timeout=10,
                env={**os.environ, 'CLICOLOR_FORCE': '1'},
            )
            if result.returncode == 0:
                return
        except Exception:
            pass
    print(rule_line('='))
    if _color_enabled():
        print(f"\033[1m{title}\033[0m")
    else:
        print(title)
    print(rule_line('-'))


def prompt(message_id: str, **kwargs) -> str:
    return input(style_text(translate(message_id, **kwargs)))


def localized_print(message_id: str, **kwargs) -> None:
    text = translate(message_id, **kwargs)
    if message_id in ('welcome',):
        print_banner(text)
        return
    if message_id in (
        'peq_table_title',
        'delta_summary_heading',
        'yaml_dump_header',
        'audio_device_list_header',
        'prepare_config',
    ):
        print_section(text)
        return
    if message_id == 'section_separator' or message_id == 'welcome_sep':
        # 由 print_section / print_banner 负责分隔，避免重复空行
        return
    print(style_text(text))


def fetch_url(url: str, timeout: float = 15.0, retries: int = 3, backoff_factor: float = 0.5) -> bytes:
    """带有镜像加速回退机制的 URL 获取函数。"""
    
    # 1. 参数校验
    if retries < 1:
        raise ValueError("retries 必须大于等于 1")
    if timeout <= 0:
        raise ValueError("timeout 必须大于 0")
    if backoff_factor < 0:
        raise ValueError("backoff_factor 不能为负数")

    # 2. 安全性检查：防止 SSRF，仅允许 http 和 https
    parsed_url = urllib.parse.urlparse(url)
    if parsed_url.scheme not in ('http', 'https'):
        raise ValueError(f"不支持的 URL 协议: {parsed_url.scheme}. 仅支持 http 和 https.")

    last_exception: Exception | None = None

    for attempt in range(1, retries + 1):
        prefix_index = min(attempt - 1, len(MIRROR_PREFIXES) - 1)
        prefix = MIRROR_PREFIXES[prefix_index]
        candidate_url = f"{prefix}{url}" if prefix else url

        try:
            request = urllib.request.Request(candidate_url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                if 200 <= response.status < 300:
                    return response.read()
                else:
                    raise urllib.error.HTTPError(
                        url=response.url,
                        code=response.status,
                        msg=response.reason,
                        hdrs=response.headers,
                        fp=None
                    )

        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as exc:
            last_exception = exc
            should_retry = False

            if isinstance(exc, urllib.error.URLError):
                should_retry = True
            elif isinstance(exc, urllib.error.HTTPError):
                if exc.code >= 500 or exc.code == 429:
                    should_retry = True
            elif isinstance(exc, (TimeoutError, OSError)):
                should_retry = True

            if not should_retry:
                break
            if attempt >= retries:
                break

            wait_time = backoff_factor * (2 ** (attempt - 1))
            localized_print('retry_request', exc=exc, wait_time=wait_time, attempt=attempt, retries=retries)
            time.sleep(wait_time)

    if last_exception is not None:
        raise last_exception
    raise RuntimeError("未知错误：请求未成功且未捕获到异常")


def fetch_text_url(url: str, timeout: float = 15.0, retries: int = 3, backoff_factor: float = 0.5) -> str:
    """获取 URL 内容并解码为字符串"""
    return fetch_url(url, timeout=timeout, retries=retries, backoff_factor=backoff_factor).decode("utf-8", errors="replace")


# --- AutoEq 数据库相关 ---

def extract_provider_label(relative_path: str) -> str:
    """从 AutoEq 相对路径中推断提供者标签。"""
    if not relative_path:
        return 'default'
    normalized = relative_path.strip().replace('\\', '/').strip('/')
    if normalized.endswith('.csv'):
        normalized = normalized[:normalized.rfind('/')]
    segments = [seg for seg in normalized.split('/') if seg]
    if not segments:
        return 'default'
    if segments[0] == 'offline_csvs':
        return 'offline'
    return segments[0]


def make_safe_filename(value: str) -> str:
    value = re.sub(r'[^\w\-\. ]+', '_', value).strip().replace(' ', '_')
    return re.sub(r'__+', '_', value)


def build_config_filename(source_entry: dict, target_entry: dict) -> str:
    src_provider = source_entry.get('provider', 'default')
    tgt_provider = target_entry.get('provider', 'default')
    src_label = make_safe_filename(f"{source_entry['display_name']}_{src_provider}")
    tgt_label = make_safe_filename(f"{target_entry['display_name']}_{tgt_provider}")
    return f"cosplay_{src_label}_to_{tgt_label}.yml"


def get_presets_dir() -> Path:
    """返回方案目录路径，必要时创建。"""
    SAVED_PRESETS_DIR.mkdir(parents=True, exist_ok=True)
    return SAVED_PRESETS_DIR.resolve()


def get_logs_dir() -> Path:
    """返回日志目录（logs/），必要时创建，并迁移根目录历史 *.log。"""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    logs_dir = LOGS_DIR.resolve()
    # 一次性清理：项目根下散落的 camilladsp_*.log / eq_cosplay_*.log → logs/
    try:
        script_dir = Path(__file__).resolve().parent
        for pattern in ("camilladsp_*.log", "eq_cosplay_*.log", "cosplay_session_*.log"):
            for old in script_dir.glob(pattern):
                if not old.is_file():
                    continue
                dest = logs_dir / old.name
                if dest.exists():
                    dest = logs_dir / f"{old.stem}_migrated{old.suffix}"
                try:
                    old.replace(dest)
                except Exception:
                    try:
                        shutil.copy2(old, dest)
                        old.unlink(missing_ok=True)
                    except Exception:
                        pass
    except Exception:
        pass
    return logs_dir


def make_log_path(prefix: str = "session", ext: str = ".log") -> Path:
    """在 logs/ 下生成带时间戳与 PID 的日志路径。

    例: logs/camilladsp_20260713_153012_29406.log
    """
    logs_dir = get_logs_dir()
    stamp = time.strftime("%Y%m%d_%H%M%S")
    safe_prefix = re.sub(r"[^\w\-]+", "_", prefix).strip("_") or "session"
    if not ext.startswith("."):
        ext = f".{ext}"
    return logs_dir / f"{safe_prefix}_{stamp}_{os.getpid()}{ext}"


def build_config_path(source_entry: dict, target_entry: dict) -> Path:
    """生成写入 presets/ 的完整配置路径。"""
    return get_presets_dir() / build_config_filename(source_entry, target_entry)


def list_saved_presets() -> list[Path]:
    """列出本机已保存的 YAML 方案（presets/ + 项目根目录历史 cosplay_*.yml）。"""
    presets_dir = get_presets_dir()
    found: list[Path] = []
    seen_names: set[str] = set()

    for path in sorted(presets_dir.glob("*.yml")) + sorted(presets_dir.glob("*.yaml")):
        if path.is_file() and path.name not in seen_names:
            found.append(path)
            seen_names.add(path.name)

    # 兼容旧版写在项目根目录的 cosplay_*.yml
    script_dir = Path(__file__).resolve().parent
    for path in sorted(script_dir.glob("cosplay_*.yml")) + sorted(script_dir.glob("cosplay_*.yaml")):
        if path.is_file() and path.name not in seen_names:
            found.append(path)
            seen_names.add(path.name)

    # 按修改时间新→旧，便于优先选最近方案
    found.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return found


def format_preset_label(path: Path) -> str:
    """把 cosplay_A_to_B.yml 整理成可读标签。"""
    name = path.stem
    if name.startswith("cosplay_"):
        name = name[len("cosplay_"):]
    name = name.replace("_to_", "  ->  ").replace("_", " ")
    try:
        mtime = time.strftime("%Y-%m-%d %H:%M", time.localtime(path.stat().st_mtime))
    except Exception:
        mtime = "?"
    location = "presets/" if path.parent.resolve() == get_presets_dir() else "./"
    return f"{name}  [{location}{path.name}]  ({mtime})"


def prompt_select_saved_preset() -> Path | None:
    """交互选择已保存方案；取消或无效时返回 None。"""
    presets = list_saved_presets()
    if not presets:
        localized_print('saved_presets_empty', path=get_presets_dir())
        return None

    choice = prompt('saved_presets_prompt', count=len(presets)).strip().lower()
    if choice not in ('y', 'yes'):
        localized_print('saved_presets_cancelled')
        return None

    print_section(translate('saved_presets_header'))
    preset_headers = ['#', 'Preset', 'File', 'Modified']
    preset_rows = []
    for idx, p in enumerate(presets, start=1):
        name = p.stem
        if name.startswith('cosplay_'):
            name = name[len('cosplay_'):].replace('_to_', ' -> ').replace('_', ' ')
        try:
            mtime = time.strftime('%Y-%m-%d %H:%M', time.localtime(p.stat().st_mtime))
        except Exception:
            mtime = '?'
        loc = 'presets/' if p.parent.resolve() == get_presets_dir() else './'
        preset_rows.append([str(idx), name, f'{loc}{p.name}', mtime])
    print_table(preset_headers, preset_rows)
    localized_print('saved_presets_dir', path=get_presets_dir())

    raw = input(style_text(translate('saved_presets_choice_prompt'))).strip()
    if raw == '':
        localized_print('saved_presets_cancelled')
        return None
    if not raw.isdigit():
        localized_print('saved_presets_invalid')
        return None
    index = int(raw) - 1
    if not (0 <= index < len(presets)):
        localized_print('saved_presets_invalid')
        return None

    selected = presets[index]
    localized_print('saved_presets_selected', name=selected.name)
    return selected


def ensure_runtime_for_camilladsp(system_name: str) -> bool:
    """检查/安装虚拟声卡与 CamillaDSP，成功返回 True。"""
    if not is_blackhole_installed():
        localized_print('blackhole_not_installed')
        if system_name == 'Darwin':
            install_choice = prompt('install_blackhole_prompt').lower().strip()
            if install_choice == 'y':
                if not install_blackhole():
                    localized_print('partial_blackhole_failure')
            else:
                localized_print('user_cancelled_blackhole')
        elif system_name == 'Windows':
            localized_print('virtual_device_missing_windows')
            input(translate('press_enter_to_continue'))
        elif system_name == 'Linux':
            localized_print('virtual_device_missing_linux')
            input(translate('press_enter_to_continue'))
        else:
            input(translate('press_enter_to_continue'))
    else:
        localized_print('blackhole_installed')

    if not is_camilladsp_installed():
        localized_print('camilladsp_not_installed')
        if not download_camilladsp():
            localized_print('camilladsp_download_fail_continue')
            return False
    else:
        localized_print('camilladsp_installed')
    return True


def config_uses_fir_conv(config_path: Path) -> bool:
    """检测 YAML 是否包含 FIR Conv（fir_left / type: Conv）。"""
    try:
        text = Path(config_path).read_text(encoding='utf-8', errors='replace')
    except Exception:
        return False
    lower = text.lower()
    if 'fir_left' in lower or 'fir_right' in lower:
        return True
    # 宽松匹配：存在 Conv + Wav 卷积段
    return ('type: conv' in lower) and ('type: wav' in lower or 'filename:' in lower)


def companion_fir_wav_paths(config_path: Path) -> tuple[Path, Path]:
    """返回与 YAML 同 stem 的左右 FIR WAV 路径。"""
    stem = Path(config_path).with_suffix("")
    return Path(f"{stem}_fir_left.wav"), Path(f"{stem}_fir_right.wav")


def config_has_companion_fir_wavs(config_path: Path) -> bool:
    """磁盘上是否仍有可重新启用的 FIR 冲激文件。"""
    left, right = companion_fir_wav_paths(config_path)
    return left.is_file() and right.is_file() and left.stat().st_size > 0


def load_fir_ir_from_companion_wavs(
    config_path: Path,
) -> tuple[np.ndarray | None, int | None]:
    """从预设配套 WAV 加载 FIR 冲激（优先左声道）。

    返回 (ir, sample_rate)；失败时 (None, None)。
    """
    left, right = companion_fir_wav_paths(config_path)
    for path in (left, right):
        if not path.is_file():
            continue
        try:
            sr, data = scipy_wavfile.read(str(path))
            arr = np.asarray(data, dtype=np.float64).reshape(-1)
            if arr.size > 0:
                return arr, int(sr)
        except Exception:
            continue
    return None, None


def parse_camilladsp_config_for_regen(config_path: Path) -> dict | None:
    """从已有 CamillaDSP YAML 提取可再生成所需的基本字段。

    用于在无 correction 会话（例如刚加载预设）时仍可关闭/开启 FIR。
    """
    path = Path(config_path)
    try:
        text = path.read_text(encoding='utf-8')
    except Exception:
        return None

    def _first_group(pattern: str, default: str | None = None) -> str | None:
        m = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        return m.group(1).strip() if m else default

    try:
        samplerate = int(_first_group(r'^\s*samplerate:\s*(\d+)', '48000') or 48000)
    except Exception:
        samplerate = DEFAULT_SAMPLE_RATE

    backend_type = _first_group(
        r'capture:\s*\n(?:[ \t]+.+\n)*?[ \t]+type:\s*([^\n#]+)',
        'CoreAudio',
    ) or 'CoreAudio'
    capture_device = _first_group(
        r'capture:\s*\n(?:[ \t]+.+\n)*?[ \t]+device:\s*["\']?([^"\'\n]+)',
        'BlackHole 2ch',
    ) or 'BlackHole 2ch'
    playback_device = _first_group(
        r'playback:\s*\n(?:[ \t]+.+\n)*?[ \t]+device:\s*["\']?([^"\'\n]+)',
        '',
    ) or ''

    pre_amp = 0.0
    m_gain = re.search(
        r'preamp_gain:\s*\n(?:[ \t]+.+\n)*?[ \t]+gain:\s*([-+0-9.eE]+)',
        text,
    )
    if m_gain:
        try:
            pre_amp = float(m_gain.group(1))
        except Exception:
            pre_amp = 0.0

    peq: list[dict] = []
    # 匹配 peq_XX 段（跳过 fir_* / preamp）
    for m in re.finditer(
        r'^\s*(peq_\d+):\s*\n'
        r'(?:[ \t]+type:\s*Biquad\s*\n)?'
        r'(?:[ \t]+parameters:\s*\n)'
        r'(?:[ \t]+type:\s*(\w+)\s*\n)'
        r'(?:[ \t]+freq:\s*([-+0-9.eE]+)\s*\n)'
        r'(?:[ \t]+gain:\s*([-+0-9.eE]+)\s*\n)'
        r'(?:[ \t]+q:\s*([-+0-9.eE]+)\s*\n)',
        text,
        re.IGNORECASE | re.MULTILINE,
    ):
        try:
            peq.append(
                {
                    'filter_type': m.group(2),
                    'frequency': float(m.group(3)),
                    'gain': float(m.group(4)),
                    'Q': float(m.group(5)),
                }
            )
        except Exception:
            continue

    if not peq:
        return None

    return {
        'samplerate': samplerate,
        'backend_type': backend_type.strip(),
        'capture_device': capture_device.strip().strip('"').strip("'"),
        'playback_device': playback_device.strip().strip('"').strip("'"),
        'pre_amp': pre_amp,
        'peq': peq,
        'use_fir': config_uses_fir_conv(path),
        'has_companion_fir': config_has_companion_fir_wavs(path),
    }


def regenerate_config_fir_mode(
    config_path: Path,
    *,
    use_fir: bool,
    output_device: str | None = None,
    fir_ir: np.ndarray | None = None,
    samplerate: int | None = None,
) -> dict:
    """基于已有 YAML 重新生成：开启或关闭 FIR（保留 PEQ / 设备等）。

    返回用于 GUI 的摘要 dict：use_fir, samplerate, path, peq, fir_n_taps。
    """
    path = Path(config_path)
    basics = parse_camilladsp_config_for_regen(path)
    if not basics:
        raise RuntimeError(f'Cannot parse CamillaDSP config: {path}')

    peq = list(basics['peq'])
    out_dev = (output_device or basics['playback_device'] or '').strip()
    if not out_dev:
        raise RuntimeError('Playback device missing in config and UI')

    sr = int(samplerate or basics['samplerate'] or DEFAULT_SAMPLE_RATE)
    ir = fir_ir
    # 保留文件中已有 RMSE 等指标，避免开关 FIR 时被清成 0
    existing_metrics = load_config_metrics(path)
    mode_metrics = dict(existing_metrics)
    mode_metrics['use_fir'] = bool(use_fir)

    if use_fir:
        if ir is None or len(np.asarray(ir).reshape(-1)) == 0:
            ir, wav_sr = load_fir_ir_from_companion_wavs(path)
            if ir is None:
                raise RuntimeError(
                    f'No FIR residual available for re-enable (missing companion WAV next to {path.name})'
                )
            # 与磁盘 FIR 采样率对齐，避免扬声器路径下 44.1k/48k 不一致导致卷积异常
            if wav_sr:
                sr = int(wav_sr)
        taps = int(len(np.asarray(ir).reshape(-1)))
        mode_metrics['fir_n_taps'] = taps
        generate_camilladsp_config(
            peq,
            out_dev,
            path,
            pre_amp=float(basics['pre_amp']),
            samplerate=sr,
            backend_type=basics['backend_type'],
            capture_device=basics['capture_device'],
            fir_ir=ir,
            metrics=mode_metrics,
        )
    else:
        taps = int(existing_metrics.get('fir_n_taps') or 0)
        generate_camilladsp_config(
            peq,
            out_dev,
            path,
            pre_amp=float(basics['pre_amp']),
            samplerate=sr,
            backend_type=basics['backend_type'],
            capture_device=basics['capture_device'],
            fir_ir=None,
            metrics=mode_metrics,
        )

    metrics = load_config_metrics(path)
    return {
        'path': path,
        'use_fir': bool(use_fir),
        'samplerate': sr,
        'peq': peq,
        'fir_ir': ir if use_fir else fir_ir,
        'fir_n_taps': int(metrics.get('fir_n_taps') or taps or 0),
        'playback_device': out_dev,
        'metrics': metrics,
        'peq_rmse': metrics.get('peq_rmse'),
        'combined_rmse': metrics.get('combined_rmse'),
        'response_peak': metrics.get('response_peak'),
        'level_offset_db': metrics.get('level_offset_db'),
    }


def launch_camilladsp_session(config_path: Path, debug_mode: bool = False) -> bool:
    """启动 CamillaDSP 并阻塞直到用户输入 q。成功跑完返回 True。"""
    if not config_path.is_file():
        localized_print('saved_presets_missing_file', path=config_path)
        return False

    fir_active = config_uses_fir_conv(config_path)
    if fir_active:
        localized_print('fir_camilladsp_deploy_notice')

    if debug_mode:
        dump_yaml_config(config_path)
        dump_audio_device_list()

    localized_print('saved_presets_launch')
    camilladsp_process, camilladsp_log_path = run_camilladsp(config_path, debug=debug_mode)
    if camilladsp_process is None:
        localized_print(
            'camilladsp_failed',
            error=translate('camilladsp_process_not_started'),
        )
        return False

    localized_print('auto_deploy_complete')
    if fir_active:
        localized_print('fir_camilladsp_running_notice')
    localized_print('usage_instructions')
    localized_print('camilladsp_monitor_prompt')
    try:
        while True:
            stop_input = input()
            if stop_input.strip().lower() == 'q':
                break
    except KeyboardInterrupt:
        pass
    finally:
        terminate_camilladsp(camilladsp_process, camilladsp_log_path)
        localized_print('camilladsp_stopped')
    return True

def normalize_text(text: str) -> str:
    """Unicode 规范化 + 清理，用于耳机型号匹配"""
    if not text:
        return ""
    text = unicodedata.normalize('NFKC', str(text))
    return text.strip()


def parse_autoeq_index(raw_text: str) -> dict:
    """解析 AutoEq INDEX.md 文件"""
    entries = {}
    # 匹配 Markdown 链接格式: [Name](Path)
    matches = re.findall(r"\[([^\]]+?)\]\(([^)]+?)\)", raw_text, flags=re.DOTALL)

    for item in matches:
        if not isinstance(item, tuple) or len(item) != 2:
            continue

        display_name, raw_path = item
        if display_name is None or raw_path is None:
            continue

        display_name = normalize_text(str(display_name))
        raw_path = normalize_text(str(raw_path))

        if raw_path.startswith("./"):
            raw_path = raw_path[2:]

        decoded_path = urllib.parse.unquote(raw_path)
        quoted_path = urllib.parse.quote(decoded_path, safe="/")
        provider = extract_provider_label(decoded_path)
        key = display_name.lower()

        entries.setdefault(key, []).append(
            {
                "display_name": display_name,
                "relative_path": quoted_path,
                "provider": provider,
            }
        )

    if not entries:
        localized_print('parse_index_empty')

    return entries


def load_autoeq_database() -> dict:
    """加载 AutoEq 数据库，优先在线加载，失败则使用本地备用"""
    try:
        localized_print('loading_database')
        # 重试次数应覆盖所有镜像前缀，加1作为安全边际
        retries = len(MIRROR_PREFIXES) + 1
        raw_index = fetch_text_url(GITHUB_RAW_INDEX_URL, timeout=20.0, retries=retries, backoff_factor=1.0)
        entries = parse_autoeq_index(raw_index)
        if entries:
            localized_print('database_loaded', count=len(entries))
            return entries
    except Exception as exc:
        localized_print('database_failed', error=exc)

    localized_print('using_fallback_db')
    return FALLBACK_ENTRIES


def select_headphone_provider(entries: list[dict]) -> dict:
    """选择耳机频响来源：多源出菜单；单源打印提供者名称提示。"""
    if len(entries) == 1:
        item = entries[0]
        provider = item.get('provider') or extract_provider_label(item.get('relative_path', ''))
        localized_print(
            'provider_single_source',
            provider=provider,
            display_name=item.get('display_name', ''),
        )
        return item

    localized_print('provider_list_header')
    provider_headers = ['#', 'Model', 'Provider']
    provider_rows = []
    for idx, item in enumerate(entries, start=1):
        provider = item.get('provider') or extract_provider_label(item.get('relative_path', ''))
        provider_rows.append([str(idx), item['display_name'], provider])
    print_table(provider_headers, provider_rows)
    print(style_text(translate('provider_menu_default_note')))

    choice = input(style_text(translate('provider_choice_prompt'))).strip()
    if choice == '':
        return entries[0]

    if not choice.isdigit():
        localized_print('provider_invalid_selection')
        return entries[0]

    index = int(choice) - 1
    if 0 <= index < len(entries):
        return entries[index]

    localized_print('provider_invalid_selection')
    return entries[0]


def find_headphone(user_input: str, prompt_type: str = "目标") -> dict | None:
    """根据用户输入查找最匹配的耳机"""
    if not AUTOEQ_DATABASE:
        localized_print('db_not_loaded')
        return None

    localized_print('searching_headphone', user_input=user_input, prompt_type=prompt_type)
    lower_names = list(AUTOEQ_DATABASE.keys())
    
    # 使用 difflib 进行模糊匹配
    matches = difflib.get_close_matches(user_input.lower(), lower_names, n=1, cutoff=0.3)

    if not matches:
        localized_print('no_match_found')
        return None

    best_match = matches[0]
    items = AUTOEQ_DATABASE[best_match]
    selected_entry = select_headphone_provider(items)
    localized_print('match_success', prompt_type=prompt_type, display_name=selected_entry['display_name'])
    return selected_entry


# --- 文件下载与解析 ---

def find_best_csv_url(relative_path: str, display_name: str) -> str | None:
    """尽量从多个候选地址中找到可访问的 CSV 下载链接，避免 404/403 直接失败。"""
    if not relative_path:
        return None

    try:
        decoded_path = urllib.parse.unquote(relative_path)
        safe_path = urllib.parse.quote(decoded_path, safe="/")
        retries = len(MIRROR_PREFIXES) + 1

        # 1) 先尝试 GitHub Contents API（如果可用，能拿到更准确的文件记录）
        api_url = f"https://api.github.com/repos/jaakkopasanen/AutoEq/contents/results/{safe_path}"
        try:
            api_bytes = fetch_url(api_url, timeout=25.0, retries=retries, backoff_factor=1.0)
            api_payload = json.loads(api_bytes.decode("utf-8", errors="replace"))
            if isinstance(api_payload, list):
                for item in api_payload:
                    if not isinstance(item, dict):
                        continue
                    item_name = item.get("name", "")
                    if isinstance(item_name, str) and item_name.lower().endswith(".csv"):
                        download_url = item.get("download_url")
                        if isinstance(download_url, str) and download_url.startswith("http"):
                            return download_url
        except Exception:
            pass

        # 2) 失败后，回退到多种 raw URL 模式
        raw_candidates = [
            f"https://raw.githubusercontent.com/jaakkopasanen/AutoEq/master/results/{safe_path}",
            f"https://raw.kkgithub.com/jaakkopasanen/AutoEq/master/results/{safe_path}",
            f"https://raw.githubusercontent.com/jaakkopasanen/AutoEq/master/results/{decoded_path}",
            f"https://raw.kkgithub.com/jaakkopasanen/AutoEq/master/results/{decoded_path}",
        ]

        for candidate_url in raw_candidates:
            try:
                candidate_bytes = fetch_url(candidate_url, timeout=25.0, retries=retries, backoff_factor=1.0)
                if candidate_bytes and len(candidate_bytes) > 0:
                    return candidate_url
            except Exception:
                continue

        localized_print('no_csv_in_dir', directory=decoded_path)
        return None

    except Exception as exc:
        localized_print('cannot_access_dir', path=relative_path, error=exc)
        return None


def download_file(download_url: str, dest_path: Path) -> bool:
    """下载文件到指定路径。失败返回 False，允许上层友好处理。"""
    try:
        localized_print('downloading_file', filename=dest_path.name)
        retries = len(MIRROR_PREFIXES) + 1
        data = fetch_url(download_url, timeout=25.0, retries=retries, backoff_factor=1.0)
        dest_path.write_bytes(data)
        return True
    except Exception as exc:
        localized_print('download_failed', error=exc)
        return False


def download_headphone_csv(entry: dict, temp_dir: Path) -> Path | None:
    """
    综合函数：根据 entry 信息下载或读取 CSV 文件
    返回: CSV 文件路径，失败返回 None
    """
    relative_path = entry.get("relative_path")
    if not relative_path:
        localized_print('no_relative_path', display_name=entry['display_name'])
        return None

    normalized_rel = relative_path.replace('\\', '/')
    local_path = Path(normalized_rel)
    if local_path.is_file():
        localized_print('using_local_csv', path=local_path)
        return local_path

    if 'offline_csvs' in normalized_rel:
        localized_print('offline_csv_missing', path=local_path)
        return None

    csv_url = find_best_csv_url(relative_path, entry["display_name"])
    if not csv_url:
        localized_print('csv_url_not_found', display_name=entry['display_name'])
        return None

    safe_name = re.sub(r'[^\w\-_\.]', '_', entry["display_name"])
    dest_path = temp_dir / f"{safe_name}.csv"
    
    if download_file(csv_url, dest_path):
        return dest_path

    localized_print('csv_download_failed_retry', display_name=entry['display_name'])
    return None


def parse_csv_response(csv_path: Path) -> tuple[np.ndarray, np.ndarray]:
    """解析 AutoEq CSV 文件，返回频率和增益数组"""
    freqs = []
    mags = []

    with csv_path.open("r", encoding="utf-8", errors="replace") as csv_file:
        for raw_line in csv_file:
            line = raw_line.strip()
            # 跳过注释和空行
            if not line or line.startswith("#") or line.startswith("["):
                continue
            
            # 处理可能的制表符或逗号分隔
            line = line.replace("\t", ",")
            fields = re.split(r"[,;\s]+", line)
            
            if len(fields) < 2:
                continue
            
            try:
                f = float(fields[0])
                m = float(fields[1])
            except ValueError:
                continue
            
            freqs.append(f)
            mags.append(m)

    if len(freqs) < 3:
        raise ValueError(f"无法从 CSV 文件 {csv_path} 解析到有效频响数据。")

    freqs = np.array(freqs)
    mags = np.array(mags)
    
    # 确保按频率排序
    sort_idx = np.argsort(freqs)
    return freqs[sort_idx], mags[sort_idx]


# --- 核心计算逻辑 (PEQ Fit) ---

def make_log_freqs(num_points: int = 512) -> np.ndarray:
    """生成对数分布的频率点"""
    return np.logspace(np.log10(20.0), np.log10(20000.0), num_points)


def _biquad_coeffs(filter_type: str, f0: float, gain_db: float, Q: float, fs: float) -> tuple[float, float, float, float, float]:
    """RBJ Cookbook 双二阶系数，返回归一化后的 (b0, b1, b2, a1, a2)。"""
    A = 10.0 ** (gain_db / 40.0)
    w0 = 2.0 * np.pi * f0 / fs
    # 防止 Q 过小导致数值问题
    Q = max(float(Q), 1e-4)
    alpha = np.sin(w0) / (2.0 * Q)
    cos_w0 = np.cos(w0)

    if filter_type == "Peaking":
        b0 = 1.0 + alpha * A
        b1 = -2.0 * cos_w0
        b2 = 1.0 - alpha * A
        a0 = 1.0 + alpha / A
        a1 = -2.0 * cos_w0
        a2 = 1.0 - alpha / A
    elif filter_type == "Lowshelf":
        sqrtA = np.sqrt(A)
        b0 = A * ((A + 1.0) - (A - 1.0) * cos_w0 + 2.0 * sqrtA * alpha)
        b1 = 2.0 * A * ((A - 1.0) - (A + 1.0) * cos_w0)
        b2 = A * ((A + 1.0) - (A - 1.0) * cos_w0 - 2.0 * sqrtA * alpha)
        a0 = (A + 1.0) + (A - 1.0) * cos_w0 + 2.0 * sqrtA * alpha
        a1 = -2.0 * ((A - 1.0) + (A + 1.0) * cos_w0)
        a2 = (A + 1.0) + (A - 1.0) * cos_w0 - 2.0 * sqrtA * alpha
    elif filter_type == "Highshelf":
        sqrtA = np.sqrt(A)
        b0 = A * ((A + 1.0) + (A - 1.0) * cos_w0 + 2.0 * sqrtA * alpha)
        b1 = -2.0 * A * ((A - 1.0) + (A + 1.0) * cos_w0)
        b2 = A * ((A + 1.0) + (A - 1.0) * cos_w0 - 2.0 * sqrtA * alpha)
        a0 = (A + 1.0) - (A - 1.0) * cos_w0 + 2.0 * sqrtA * alpha
        a1 = 2.0 * ((A - 1.0) - (A + 1.0) * cos_w0)
        a2 = (A + 1.0) - (A - 1.0) * cos_w0 - 2.0 * sqrtA * alpha
    else:
        raise ValueError(f"未知滤波器类型: {filter_type}")

    inv_a0 = 1.0 / a0
    return b0 * inv_a0, b1 * inv_a0, b2 * inv_a0, a1 * inv_a0, a2 * inv_a0


def biquad_response(
    freqs: np.ndarray,
    filter_type: str,
    f0: float,
    gain_db: float,
    Q: float,
    fs: float = 48000.0,
    z: np.ndarray | None = None,
) -> np.ndarray:
    """
    计算双二阶滤波器的频率响应（复数）。
    参考 RBJ Audio EQ Cookbook。
    可传入预计算的 z = exp(j*2πf/fs) 以加速批量评估。
    """
    b0, b1, b2, a1, a2 = _biquad_coeffs(filter_type, f0, gain_db, Q, fs)
    if z is None:
        z = np.exp(1j * 2.0 * np.pi * freqs / fs)
    z_inv = 1.0 / z
    z_inv2 = z_inv * z_inv
    numerator = b0 + b1 * z_inv + b2 * z_inv2
    denominator = 1.0 + a1 * z_inv + a2 * z_inv2
    return numerator / denominator


# --- 专业级校正：10 段 IIR PEQ + 可选最小相位 FIR 残差 ---
#
# 架构：
# - IIR：固定 10 段（Lowshelf + 8×Peaking + Highshelf），负责宽带/听感包络
# - FIR：关键频段差异大时，用最小相位卷积补 IIR 残差（替代原 20 段 IIR 精确模式）
# - 预处理：参考带电平对齐 + 分数倍频程平滑（改善跨源偏移与测量毛刺）

PEQ_NUM_PEAKING = 8          # 固定 10 段（+2 shelf）
PEQ_NUM_PEAKING_STANDARD = PEQ_NUM_PEAKING  # 兼容旧引用
PEQ_GAIN_MIN = -10.0
PEQ_GAIN_MAX = 10.0
PEQ_Q_PEAK_MIN = 0.35
PEQ_Q_PEAK_MAX = 4.0         # 听感友好：避免原 Q=6 的过窄尖峰
PEQ_Q_SHELF_MIN = 0.5
PEQ_Q_SHELF_MAX = 1.4
PEQ_FC_MIN = 20.0
PEQ_FC_MAX = 20000.0
PEQ_MIN_OCTAVE_SEP = 0.38    # 略密于 0.45，提高 10 段覆盖能力
PEQ_MAX_LOW_PEAKING = 3      # 允许多 1 个低频 peaking

# 关键频段：差异大时启用 FIR 残差（不再升 IIR 段数）
PEQ_CRITICAL_BANDS: list[tuple[float, float, str]] = [
    (60.0, 150.0, "60-150Hz"),
    (200.0, 600.0, "200-600Hz"),
    (2000.0, 4000.0, "2-4kHz"),
    (5000.0, 10000.0, "5-10kHz"),
]
PEQ_CRITICAL_MAX_ABS_DB = 3.5
PEQ_CRITICAL_PTP_DB = 4.0
PEQ_CRITICAL_RMS_DB = 2.2

# 预处理 / FIR
PEQ_ALIGN_BAND = (200.0, 2000.0)   # 电平对齐参考带
PEQ_SMOOTH_OCTAVES = 1.0 / 6.0     # IIR 拟合用 1/6 oct 平滑
FIR_SMOOTH_OCTAVES = 1.0 / 12.0    # FIR 目标轻平滑
FIR_N_TAPS = 8192
FIR_GAIN_CLIP_DB = 18.0
FIR_RESIDUAL_TRIGGER_RMSE = 1.15   # IIR 后残差仍大则强制 FIR


def peq_response_db(
    freqs: np.ndarray,
    bands: list[dict],
    fs: float,
    z: np.ndarray | None = None,
) -> np.ndarray:
    """计算一组完整 PEQ 参数（含 gain）的总幅频响应 (dB)。"""
    if z is None:
        z = np.exp(1j * 2.0 * np.pi * freqs / fs)
    total_db = np.zeros_like(freqs, dtype=float)
    for band in bands:
        h = biquad_response(
            freqs,
            band["type"],
            float(band["frequency"]),
            float(band["gain"]),
            float(band["Q"]),
            fs=fs,
            z=z,
        )
        total_db += 20.0 * np.log10(np.abs(h) + 1e-12)
    return total_db


def apply_peq_chain(freqs: np.ndarray, bands: list[dict], gains: np.ndarray, fs: float) -> np.ndarray:
    """兼容旧接口：用外部 gains 覆盖 band 增益后返回复数响应。"""
    response = np.ones_like(freqs, dtype=np.complex128)
    for band, gain in zip(bands, gains):
        response *= biquad_response(freqs, band["type"], band["frequency"], float(gain), band["Q"], fs=fs)
    return response


def smooth_curve_logf(freqs: np.ndarray, curve: np.ndarray, octaves: float) -> np.ndarray:
    """在对数频率轴上做高斯平滑（分数倍频程）。"""
    if octaves <= 0 or len(freqs) < 3:
        return curve.copy()
    logf = np.log2(np.clip(freqs, 1e-6, None))
    # FWHM ≈ octaves → sigma ≈ FWHM / 2.355
    sigma = max(octaves / 2.355, 1e-6)
    out = np.empty_like(curve, dtype=float)
    for i, lf in enumerate(logf):
        w = np.exp(-0.5 * ((logf - lf) / sigma) ** 2)
        w_sum = float(np.sum(w))
        out[i] = float(np.dot(w, curve) / w_sum) if w_sum > 0 else float(curve[i])
    return out


def align_delta_level(
    freqs: np.ndarray,
    delta_db: np.ndarray,
    band: tuple[float, float] = PEQ_ALIGN_BAND,
) -> tuple[np.ndarray, float]:
    """用参考频带均值对齐差值，去掉跨测量源的整体电平偏置。"""
    f_lo, f_hi = band
    mask = (freqs >= f_lo) & (freqs <= f_hi)
    if not np.any(mask):
        mask = (freqs >= 100.0) & (freqs <= 5000.0)
    offset = float(np.mean(delta_db[mask])) if np.any(mask) else 0.0
    return delta_db - offset, offset


def perceptual_error_weights(
    freqs: np.ndarray,
    boost_regions: list[tuple[float, float]] | None = None,
) -> np.ndarray:
    """听感相关的频率权重：200 Hz–6 kHz 更高，1–4 kHz 再加强。

    权重均值归一化；boost_regions 仅作轻度偏置（不再 ×1.55 激进加权）。
    """
    logf = np.log10(np.clip(freqs, 20.0, 20000.0))
    broad = np.exp(-0.5 * ((logf - np.log10(1000.0)) / 0.85) ** 2)
    presence = np.exp(-0.5 * ((logf - np.log10(2500.0)) / 0.40) ** 2)
    bass = np.exp(-0.5 * ((logf - np.log10(100.0)) / 0.45) ** 2)
    treble = np.exp(-0.5 * ((logf - np.log10(7000.0)) / 0.45) ** 2)
    # 略降极高频权重，避免 10k+ 测量噪声拖垮 10 段预算
    air = np.exp(-0.5 * ((logf - np.log10(14000.0)) / 0.30) ** 2)
    w = 0.30 + 0.48 * broad + 0.22 * presence + 0.16 * bass + 0.10 * treble - 0.08 * air
    w = np.maximum(w, 0.12)

    if boost_regions:
        for f_lo, f_hi in boost_regions:
            mask = (freqs >= f_lo) & (freqs <= f_hi)
            w = np.where(mask, w * 1.20, w)

    return w / float(np.mean(w))


def analyze_critical_band_differences(
    freqs: np.ndarray,
    delta_db: np.ndarray,
) -> tuple[bool, list[dict]]:
    """分析关键频段差值，判断是否需要 FIR 残差校正。

    返回 (needs_fir, region_stats)。
    """
    stats: list[dict] = []
    needs = False
    for f_lo, f_hi, name in PEQ_CRITICAL_BANDS:
        mask = (freqs >= f_lo) & (freqs <= f_hi)
        if not np.any(mask):
            continue
        seg = delta_db[mask]
        max_abs = float(np.max(np.abs(seg)))
        ptp = float(np.ptp(seg))
        rms = float(np.sqrt(np.mean(seg ** 2)))
        large = (
            max_abs >= PEQ_CRITICAL_MAX_ABS_DB
            or ptp >= PEQ_CRITICAL_PTP_DB
            or rms >= PEQ_CRITICAL_RMS_DB
        )
        stats.append({
            "name": name,
            "f_lo": f_lo,
            "f_hi": f_hi,
            "max_abs": max_abs,
            "ptp": ptp,
            "rms": rms,
            "large": large,
        })
        if large:
            needs = True
    return needs, stats


def _estimate_q_from_bandwidth(
    freqs: np.ndarray,
    curve: np.ndarray,
    peak_idx: int,
    min_q: float = PEQ_Q_PEAK_MIN,
    max_q: float = PEQ_Q_PEAK_MAX,
) -> float:
    """根据残差局部 -3 dB 带宽估计 peaking Q。"""
    n = len(freqs)
    peak_idx = int(np.clip(peak_idx, 0, n - 1))
    f0 = float(freqs[peak_idx])
    peak_val = float(curve[peak_idx])
    if abs(peak_val) < 0.35:
        return 1.1

    thr = peak_val - 3.0 * np.sign(peak_val) if abs(peak_val) >= 3.0 else peak_val * 0.5

    def side_boundary(direction: int) -> float:
        i = peak_idx
        while 0 < i < n - 1:
            j = i + direction
            y0, y1 = float(curve[i]), float(curve[j])
            crossed = (peak_val > 0 and y1 <= thr) or (peak_val < 0 and y1 >= thr)
            if crossed:
                if abs(y1 - y0) < 1e-12:
                    return float(freqs[j])
                t = float(np.clip((thr - y0) / (y1 - y0), 0.0, 1.0))
                return float(freqs[i]) + t * (float(freqs[j]) - float(freqs[i]))
            i = j
        return float(freqs[0] if direction < 0 else freqs[-1])

    f_lo = side_boundary(-1)
    f_hi = side_boundary(+1)
    bw = max(f_hi - f_lo, f0 * 1e-3)
    q = f0 / bw
    # 10 段模式：略压初始 Q，避免优化从过窄尖峰起步
    q = float(np.clip(q, min_q, max_q))
    if q > 2.8:
        q = 2.8 + 0.45 * (q - 2.8)
    return float(np.clip(q, min_q, max_q))


def _octave_distance(f1: float, f2: float) -> float:
    return abs(math.log2(max(f1, 1e-6) / max(f2, 1e-6)))


def _find_residual_extrema(
    freqs: np.ndarray,
    residual: np.ndarray,
    n_peaks: int,
    existing_freqs: list[float] | None = None,
    min_octave_sep: float = PEQ_MIN_OCTAVE_SEP,
    max_low_peaking: int = PEQ_MAX_LOW_PEAKING,
    f_lo: float | None = None,
    f_hi: float | None = None,
    score_boost: float = 1.0,
    prefer_regions: list[tuple[float, float]] | None = None,
) -> list[tuple[int, float]]:
    """在残差上寻找 |r| 最大的若干局部极值，保证倍频程间隔。"""
    existing_freqs = list(existing_freqs or [])
    n = len(residual)
    candidates: list[tuple[float, int, float]] = []

    for i in range(1, n - 1):
        f = float(freqs[i])
        if f_lo is not None and f < f_lo:
            continue
        if f_hi is not None and f > f_hi:
            continue
        r = float(residual[i])
        is_max = residual[i] >= residual[i - 1] and residual[i] >= residual[i + 1]
        is_min = residual[i] <= residual[i - 1] and residual[i] <= residual[i + 1]
        if not (is_max or is_min):
            continue
        if abs(r) < 0.25:
            continue
        score = abs(r) * score_boost
        if f > 12000.0:
            score *= 0.45
        elif f > 10000.0:
            score *= 0.70
        elif f < 40.0:
            score *= 0.65
        if prefer_regions:
            for pr_lo, pr_hi in prefer_regions:
                if pr_lo <= f <= pr_hi:
                    score *= 1.28
                    break
        candidates.append((score, i, r))

    candidates.sort(key=lambda x: x[0], reverse=True)
    selected: list[tuple[int, float]] = []
    selected_freqs = list(existing_freqs)
    low_count = sum(1 for ef in selected_freqs if ef < 300.0)

    for _, idx, r in candidates:
        f = float(freqs[idx])
        if any(_octave_distance(f, ef) < min_octave_sep for ef in selected_freqs):
            continue
        if f < 300.0 and low_count >= max_low_peaking:
            continue
        selected.append((idx, r))
        selected_freqs.append(f)
        if f < 300.0:
            low_count += 1
        if len(selected) >= n_peaks:
            break

    if len(selected) < n_peaks:
        g_lo = f_lo if f_lo is not None else 80.0
        g_hi = f_hi if f_hi is not None else 10000.0
        g_lo = max(g_lo, 30.0)
        g_hi = min(g_hi, 12000.0)
        if g_hi > g_lo:
            grid = np.logspace(np.log10(g_lo), np.log10(g_hi), max(n_peaks * 4, 8))
            for f in grid:
                if any(_octave_distance(f, ef) < min_octave_sep for ef in selected_freqs):
                    continue
                if f < 300.0 and low_count >= max_low_peaking:
                    continue
                idx = int(np.argmin(np.abs(freqs - f)))
                selected.append((idx, float(residual[idx])))
                selected_freqs.append(float(freqs[idx]))
                if f < 300.0:
                    low_count += 1
                if len(selected) >= n_peaks:
                    break

    return selected[:n_peaks]


def initialize_peq_bands_from_delta(
    freqs: np.ndarray,
    delta_db: np.ndarray,
    n_peaking: int = PEQ_NUM_PEAKING,
    fs: float = 48000.0,
    critical_stats: list[dict] | None = None,
) -> list[dict]:
    """残差驱动的 10 段 PEQ 初始化（非固定栅格）。

    对关键大差异区仅做选峰偏好，不再做 20 段密布。
    """
    residual = delta_db.copy()
    min_sep = PEQ_MIN_OCTAVE_SEP
    max_low = PEQ_MAX_LOW_PEAKING

    low_mask = (freqs >= 20.0) & (freqs <= 120.0)
    low_gain = float(np.mean(residual[low_mask])) if np.any(low_mask) else 0.0
    low_gain = float(np.clip(low_gain, PEQ_GAIN_MIN, PEQ_GAIN_MAX))
    if np.any(low_mask) and abs(low_gain) > 0.2:
        w = np.abs(residual[low_mask]) + 0.1
        low_fc = float(np.exp(np.average(np.log(freqs[low_mask]), weights=w)))
    else:
        low_fc = 60.0
    low_fc = float(np.clip(low_fc, 25.0, 250.0))
    bands: list[dict] = [
        {"type": "Lowshelf", "frequency": low_fc, "gain": low_gain, "Q": 0.7},
    ]
    residual = residual - peq_response_db(freqs, bands, fs=fs)

    high_mask = (freqs >= 6000.0) & (freqs <= 14000.0)
    high_gain = float(np.mean(residual[high_mask])) if np.any(high_mask) else 0.0
    high_gain = float(np.clip(high_gain, PEQ_GAIN_MIN, PEQ_GAIN_MAX))
    if np.any(high_mask) and abs(high_gain) > 0.2:
        w = np.abs(residual[high_mask]) + 0.1
        high_fc = float(np.exp(np.average(np.log(freqs[high_mask]), weights=w)))
    else:
        high_fc = 9000.0
    high_fc = float(np.clip(high_fc, 4000.0, 14000.0))
    high_band = {"type": "Highshelf", "frequency": high_fc, "gain": high_gain, "Q": 0.7}
    residual_for_peaks = residual - peq_response_db(freqs, [high_band], fs=fs)

    prefer = [
        (float(s["f_lo"]), float(s["f_hi"]))
        for s in (critical_stats or [])
        if s.get("large")
    ]

    selected_pairs = _find_residual_extrema(
        freqs,
        residual_for_peaks,
        n_peaks=n_peaking,
        existing_freqs=[low_fc, high_fc],
        min_octave_sep=min_sep,
        max_low_peaking=max_low,
        prefer_regions=prefer or None,
    )

    peaking_bands: list[dict] = []
    for idx, r in selected_pairs[:n_peaking]:
        f0 = float(np.clip(float(freqs[idx]), 30.0, 14000.0))
        gain = float(np.clip(r, PEQ_GAIN_MIN, PEQ_GAIN_MAX))
        q = _estimate_q_from_bandwidth(freqs, residual_for_peaks, idx)
        peaking_bands.append({"type": "Peaking", "frequency": f0, "gain": gain, "Q": q})

    peaking_bands.sort(key=lambda b: b["frequency"])
    bands.extend(peaking_bands)
    bands.append(high_band)
    return bands


def default_peq_bands(n_peaking: int = PEQ_NUM_PEAKING) -> list[dict]:
    """均匀对数栅格起点（残差初始化失败时的回退）。"""
    peak_fcs = np.logspace(np.log10(50.0), np.log10(10000.0), n_peaking)
    bands = [{"type": "Lowshelf", "frequency": 50.0, "gain": 0.0, "Q": 0.7}]
    for fc in peak_fcs:
        bands.append({"type": "Peaking", "frequency": float(fc), "gain": 0.0, "Q": 1.1})
    bands.append({"type": "Highshelf", "frequency": 9000.0, "gain": 0.0, "Q": 0.7})
    return bands


def _pack_peq_params(bands: list[dict]) -> np.ndarray:
    """参数向量：[gain, log10(fc), log10(Q)] * N。"""
    vec = []
    for b in bands:
        vec.extend([
            float(b["gain"]),
            math.log10(max(float(b["frequency"]), 1.0)),
            math.log10(max(float(b["Q"]), 1e-3)),
        ])
    return np.asarray(vec, dtype=float)


def _unpack_peq_params(x: np.ndarray, template: list[dict]) -> list[dict]:
    bands = []
    for i, t in enumerate(template):
        g = float(x[3 * i])
        fc = 10.0 ** float(x[3 * i + 1])
        q = 10.0 ** float(x[3 * i + 2])
        bands.append({
            "type": t["type"],
            "frequency": fc,
            "gain": g,
            "Q": q,
        })
    return bands


def _peq_param_bounds(template: list[dict]) -> tuple[np.ndarray, np.ndarray]:
    """按滤波器类型给出 fc/Q/gain 边界。"""
    lo = []
    hi = []
    for t in template:
        ftype = t["type"]
        lo.extend([PEQ_GAIN_MIN])
        hi.extend([PEQ_GAIN_MAX])
        if ftype == "Lowshelf":
            lo.extend([math.log10(20.0), math.log10(PEQ_Q_SHELF_MIN)])
            hi.extend([math.log10(300.0), math.log10(PEQ_Q_SHELF_MAX)])
        elif ftype == "Highshelf":
            lo.extend([math.log10(4000.0), math.log10(PEQ_Q_SHELF_MIN)])
            hi.extend([math.log10(14000.0), math.log10(PEQ_Q_SHELF_MAX)])
        else:
            lo.extend([math.log10(25.0), math.log10(PEQ_Q_PEAK_MIN)])
            hi.extend([math.log10(14000.0), math.log10(PEQ_Q_PEAK_MAX)])
    return np.asarray(lo, dtype=float), np.asarray(hi, dtype=float)


def _enforce_peaking_separation(bands: list[dict], min_oct: float = PEQ_MIN_OCTAVE_SEP) -> list[dict]:
    """优化后若 peaking 过近，沿对数轴向两侧推开。"""
    idx = [i for i, b in enumerate(bands) if b["type"] == "Peaking"]
    if len(idx) < 2:
        return bands
    order = sorted(idx, key=lambda i: bands[i]["frequency"])
    fcs = [float(bands[i]["frequency"]) for i in order]
    for _ in range(8):
        moved = False
        for k in range(len(fcs) - 1):
            if _octave_distance(fcs[k], fcs[k + 1]) < min_oct:
                mid = math.sqrt(fcs[k] * fcs[k + 1])
                fcs[k] = mid / (2 ** (min_oct / 2))
                fcs[k + 1] = mid * (2 ** (min_oct / 2))
                fcs[k] = float(np.clip(fcs[k], 25.0, 14000.0))
                fcs[k + 1] = float(np.clip(fcs[k + 1], 25.0, 14000.0))
                moved = True
        if not moved:
            break
    for i, fc in zip(order, fcs):
        bands[i]["frequency"] = fc
    return bands


def optimize_peq_bands(
    freqs: np.ndarray,
    delta_db: np.ndarray,
    bands: list[dict],
    fs: float,
    max_nfev: int = 2000,
    boost_regions: list[tuple[float, float]] | None = None,
) -> tuple[list[dict], float]:
    """联合优化 10 段 gain / fc / Q。

    正则策略（听感 + 数值稳定）：
    - |g| 从 5 dB 起软惩罚，抑制无谓大幅
    - Q 从 2.4 起软惩罚，抑制尖刺
    - peaking 间隔惩罚
    - soft_l1 + 略大 f_scale：对毛刺更鲁棒，允许 1 dB 级拟合余量
    """
    weights = perceptual_error_weights(freqs, boost_regions=boost_regions)
    z = np.exp(1j * 2.0 * np.pi * freqs / fs)
    template = [{"type": b["type"]} for b in bands]
    x0 = _pack_peq_params(bands)
    lower, upper = _peq_param_bounds(template)
    x0 = np.clip(x0, lower + 1e-9, upper - 1e-9)
    min_sep = PEQ_MIN_OCTAVE_SEP

    def residual(x: np.ndarray) -> np.ndarray:
        cand = _unpack_peq_params(x, template)
        pred = peq_response_db(freqs, cand, fs=fs, z=z)
        err = (pred - delta_db) * weights
        pen: list[float] = []
        peak_fcs: list[float] = []
        for b in cand:
            g = abs(float(b["gain"]))
            pen.append(0.18 * max(0.0, g - 5.0) ** 1.35)
            pen.append(0.04 * g)  # 全程轻 L1，鼓励稀疏增益
            if b["type"] == "Peaking":
                q = float(b["Q"])
                pen.append(0.18 * max(0.0, q - 2.4) ** 1.2)
                pen.append(0.06 * max(0.0, q - 3.2))
                peak_fcs.append(float(b["frequency"]))
            elif b["type"] in ("Lowshelf", "Highshelf"):
                pen.append(0.06 * max(0.0, float(b["Q"]) - 1.0))
        peak_fcs.sort()
        for a, bfc in zip(peak_fcs, peak_fcs[1:]):
            sep = _octave_distance(a, bfc)
            pen.append(0.30 * max(0.0, min_sep - sep))
        if pen:
            err = np.concatenate([err, np.asarray(pen, dtype=float)])
        return err

    result = optimize.least_squares(
        residual,
        x0,
        bounds=(lower, upper),
        method="trf",
        loss="soft_l1",
        f_scale=2.5,
        max_nfev=max_nfev,
        xtol=1e-9,
        ftol=1e-9,
        gtol=1e-9,
        verbose=0,
    )

    fitted = _enforce_peaking_separation(_unpack_peq_params(result.x, template), min_oct=min_sep)
    x1 = np.clip(_pack_peq_params(fitted), lower + 1e-9, upper - 1e-9)
    result2 = optimize.least_squares(
        residual,
        x1,
        bounds=(lower, upper),
        method="trf",
        loss="soft_l1",
        f_scale=2.5,
        max_nfev=max(500, max_nfev // 3),
        verbose=0,
    )
    fitted = _enforce_peaking_separation(_unpack_peq_params(result2.x, template), min_oct=min_sep)

    pred = peq_response_db(freqs, fitted, fs=fs, z=z)
    rmse = float(np.sqrt(np.mean((pred - delta_db) ** 2)))
    return fitted, rmse


def _min_phase_from_magnitude(mag_lin: np.ndarray, n_fft: int) -> np.ndarray:
    """由单边线性幅度谱重建最小相位冲激响应（实倒谱法）。"""
    log_mag = np.log(np.maximum(mag_lin.astype(float), 1e-12))
    ceps = np.fft.irfft(log_mag, n=n_fft)
    window = np.zeros(n_fft, dtype=float)
    window[0] = 1.0
    if n_fft >= 2:
        window[1:(n_fft + 1) // 2] = 2.0
    if n_fft % 2 == 0:
        window[n_fft // 2] = 1.0
    H = np.exp(np.fft.rfft(ceps * window, n=n_fft))
    # 锁回目标幅度，保留最小相位角
    H = mag_lin * np.exp(1j * np.angle(H))
    return np.fft.irfft(H, n=n_fft)


def design_fir_from_mag_db(
    freqs: np.ndarray,
    mag_db: np.ndarray,
    fs: float,
    n_taps: int = FIR_N_TAPS,
    gain_clip_db: float = FIR_GAIN_CLIP_DB,
) -> np.ndarray:
    """将目标幅度曲线（dB）设计为最小相位 FIR。"""
    n_fft = int(2 ** math.ceil(math.log2(max(n_taps, 64))))
    f_bins = np.fft.rfftfreq(n_fft, d=1.0 / float(fs))
    # 端点外推：DC 用最低频，Nyquist 用最高有效频
    f_src = np.clip(freqs.astype(float), 1e-6, None)
    m_src = mag_db.astype(float)
    mag_i = np.interp(f_bins, f_src, m_src, left=m_src[0], right=m_src[-1])
    mag_i = np.clip(mag_i, -gain_clip_db, gain_clip_db)
    mag_lin = 10.0 ** (mag_i / 20.0)
    # DC / Nyquist 稳定化
    nyq = 0.5 * float(fs)
    if len(f_bins):
        ref20 = mag_lin[int(np.argmin(np.abs(f_bins - 20.0)))]
        mag_lin[f_bins < 15.0] = ref20
        hi = f_bins > 0.90 * nyq
        if np.any(hi):
            t = (f_bins[hi] - 0.90 * nyq) / max(0.10 * nyq, 1e-9)
            mag_lin[hi] *= np.clip(1.0 - 0.85 * t, 0.08, 1.0)

    ir = _min_phase_from_magnitude(mag_lin, n_fft)
    # 截断到 n_taps，并加短淡出避免截断咔哒
    if len(ir) > n_taps:
        ir = ir[:n_taps].copy()
    else:
        pad = np.zeros(n_taps, dtype=float)
        pad[: len(ir)] = ir
        ir = pad
    fade = min(64, n_taps // 8)
    if fade > 1:
        ir[-fade:] *= np.linspace(1.0, 0.0, fade)
    # 峰值归一：防止数值溢出；真正响度由 preamp 管
    peak = float(np.max(np.abs(ir)))
    if peak > 4.0:
        ir = ir * (4.0 / peak)
    return ir.astype(np.float64)


def fir_response_db(freqs: np.ndarray, ir: np.ndarray, fs: float) -> np.ndarray:
    """计算 FIR 在指定频率上的幅度响应 (dB)。"""
    n = int(2 ** math.ceil(math.log2(max(len(ir) * 2, 4096))))
    spectrum = np.fft.rfft(ir, n=n)
    f_bins = np.fft.rfftfreq(n, d=1.0 / float(fs))
    mag = np.abs(spectrum)
    mag_i = np.interp(freqs, f_bins, mag, left=mag[0], right=mag[-1])
    return 20.0 * np.log10(mag_i + 1e-12)


def write_fir_wav(path: Path, ir: np.ndarray, fs: float) -> None:
    """写入 mono float32 WAV（CamillaDSP Conv 可读）。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = np.asarray(ir, dtype=np.float32).reshape(-1, 1)
    # 轻限幅到 ±1 附近之外也允许（float wav 可 >1）；仍做软限
    peak = float(np.max(np.abs(data)))
    if peak > 0.99:
        data = data * (0.99 / peak)
    scipy_wavfile.write(str(path), int(fs), data.reshape(-1))


def _bands_from_peq_list(peq_list: list[dict]) -> list[dict]:
    return [
        {
            "type": b["filter_type"],
            "frequency": float(b["frequency"]),
            "gain": float(b["gain"]),
            "Q": float(b["Q"]),
        }
        for b in peq_list
    ]


def calculate_correction(
    source_csv_path: Path,
    target_csv_path: Path,
    fs: float = DEFAULT_SAMPLE_RATE,
) -> dict:
    """计算 Source→Target 校正：固定 10 段 IIR + 可选 FIR 残差。

    返回 dict：
      peq, peq_rmse, use_fir, fir_ir, fir_n_taps, fir_rmse, combined_rmse,
      response_peak, level_offset_db, needs_fir, critical_stats, grid_freqs, ...
    """
    localized_print('calculating_peq')

    source_freqs, source_mags = parse_csv_response(source_csv_path)
    target_freqs, target_mags = parse_csv_response(target_csv_path)

    grid_freqs = make_log_freqs(512)
    source_interp = np.interp(grid_freqs, source_freqs, source_mags)
    target_interp = np.interp(grid_freqs, target_freqs, target_mags)
    delta_raw = target_interp - source_interp

    # 1) 电平对齐 + 平滑（数学稳定 + 听感）
    delta_aligned, level_offset = align_delta_level(grid_freqs, delta_raw)
    delta_for_iir = smooth_curve_logf(grid_freqs, delta_aligned, PEQ_SMOOTH_OCTAVES)

    # 触发 FIR 用对齐后、中等平滑的曲线（避免噪声误触发）
    delta_for_gate = smooth_curve_logf(grid_freqs, delta_aligned, 1.0 / 8.0)
    needs_fir, critical_stats = analyze_critical_band_differences(grid_freqs, delta_for_gate)

    n_peaking = PEQ_NUM_PEAKING
    total_bands = n_peaking + 2
    localized_print('peq_standard_mode', bands=total_bands)

    prefer_regions = [
        (float(s["f_lo"]), float(s["f_hi"]))
        for s in critical_stats
        if s.get("large")
    ] or None

    fc_cap = min(PEQ_FC_MAX, 0.45 * float(fs))

    try:
        bands0 = initialize_peq_bands_from_delta(
            grid_freqs,
            delta_for_iir,
            n_peaking=n_peaking,
            fs=float(fs),
            critical_stats=critical_stats,
        )
    except Exception:
        bands0 = default_peq_bands(n_peaking=n_peaking)
        for b in bands0:
            b["gain"] = float(np.clip(
                np.interp(b["frequency"], grid_freqs, delta_for_iir),
                PEQ_GAIN_MIN,
                PEQ_GAIN_MAX,
            ))

    for b in bands0:
        b["frequency"] = float(np.clip(b["frequency"], PEQ_FC_MIN, fc_cap))

    fitted, peq_rmse_smooth = optimize_peq_bands(
        grid_freqs,
        delta_for_iir,
        bands0,
        fs=float(fs),
        max_nfev=2000,
        boost_regions=prefer_regions,
    )

    shelves_low = [b for b in fitted if b["type"] == "Lowshelf"]
    shelves_high = [b for b in fitted if b["type"] == "Highshelf"]
    peakings = sorted([b for b in fitted if b["type"] == "Peaking"], key=lambda b: b["frequency"])
    ordered = shelves_low + peakings + shelves_high

    peq_list: list[dict] = []
    for band in ordered:
        fc = float(np.clip(band["frequency"], PEQ_FC_MIN, fc_cap))
        q = float(band["Q"])
        if band["type"] == "Peaking":
            q = float(np.clip(q, PEQ_Q_PEAK_MIN, PEQ_Q_PEAK_MAX))
        else:
            q = float(np.clip(q, PEQ_Q_SHELF_MIN, PEQ_Q_SHELF_MAX))
        peq_list.append(
            {
                "filter_type": band["type"],
                "frequency": float(np.round(fc, 1)),
                "gain": float(np.round(float(band["gain"]), 2)),
                "Q": float(np.round(q, 2)),
            }
        )

    peq_bands = _bands_from_peq_list(peq_list)
    peq_resp = peq_response_db(grid_freqs, peq_bands, fs=float(fs))
    # 对「对齐后的原始差值」评估 IIR 残差（FIR 目标）
    residual_vs_aligned = delta_aligned - peq_resp
    peq_rmse = float(np.sqrt(np.mean((peq_resp - delta_aligned) ** 2)))
    localized_print('peq_complete', rmse=peq_rmse)

    # 2) FIR 残差：关键带触发，或 IIR 残差整体仍偏大
    if peq_rmse >= FIR_RESIDUAL_TRIGGER_RMSE:
        needs_fir = True

    fir_ir: np.ndarray | None = None
    fir_rmse = 0.0
    combined_rmse = peq_rmse
    combined_resp = peq_resp.copy()

    if needs_fir:
        large_names = [s["name"] for s in critical_stats if s.get("large")]
        detail = ", ".join(
            f"{s['name']}(max|{s['max_abs']:.1f}|dB)" for s in critical_stats if s.get("large")
        )
        localized_print(
            'fir_precision_mode',
            regions=detail or (", ".join(large_names) if large_names else f"IIR residual RMSE {peq_rmse:.2f} dB"),
        )
        # FIR 拟合对齐后残差，轻平滑抑制测量毛刺
        residual_target = smooth_curve_logf(grid_freqs, residual_vs_aligned, FIR_SMOOTH_OCTAVES)
        fir_ir = design_fir_from_mag_db(
            grid_freqs,
            residual_target,
            fs=float(fs),
            n_taps=FIR_N_TAPS,
        )
        fir_resp = fir_response_db(grid_freqs, fir_ir, fs=float(fs))
        fir_rmse = float(np.sqrt(np.mean((fir_resp - residual_vs_aligned) ** 2)))
        combined_resp = peq_resp + fir_resp
        combined_rmse = float(np.sqrt(np.mean((combined_resp - delta_aligned) ** 2)))
        localized_print(
            'fir_complete',
            taps=len(fir_ir),
            rmse=fir_rmse,
            combined=combined_rmse,
        )
        # 专用醒目提示：精确级已切换为 FIR 卷积
        localized_print('fir_triggered_banner')
    else:
        localized_print('fir_skipped_mode')

    response_peak = float(np.max(combined_resp))
    response_valley = float(np.min(combined_resp))

    return {
        "peq": peq_list,
        "peq_rmse": peq_rmse,
        "peq_rmse_smooth": peq_rmse_smooth,
        "use_fir": bool(fir_ir is not None),
        "fir_ir": fir_ir,
        "fir_n_taps": int(len(fir_ir)) if fir_ir is not None else 0,
        "fir_rmse": fir_rmse,
        "combined_rmse": combined_rmse,
        "response_peak": response_peak,
        "response_valley": response_valley,
        "level_offset_db": level_offset,
        "needs_fir": needs_fir,
        "critical_stats": critical_stats,
        "grid_freqs": grid_freqs,
        "delta_raw": delta_raw,
        "delta_aligned": delta_aligned,
        "combined_resp": combined_resp,
    }


def calculate_peq_parameters(
    source_csv_path: Path,
    target_csv_path: Path,
    fs: float = DEFAULT_SAMPLE_RATE,
) -> list[dict]:
    """兼容旧接口：仅返回 10 段 IIR PEQ 列表。"""
    result = calculate_correction(source_csv_path, target_csv_path, fs=fs)
    return result["peq"]


def get_platform_info() -> tuple[str, str]:
    """获取当前操作系统和架构信息。"""
    system_name = platform.system()
    machine_arch = platform.machine().lower()
    if machine_arch in ('amd64', 'x86_64'):
        machine_arch = 'amd64'
    elif machine_arch in ('arm64', 'aarch64'):
        machine_arch = 'arm64'
    return system_name, machine_arch


def select_samplerate() -> int:
    """让用户选择目标采样率，并返回实际值。"""
    default_rate = DEFAULT_SAMPLE_RATE
    user_input = input(translate('sample_rate_prompt')).strip()
    if user_input == '':
        return default_rate
    selected = SUPPORTED_SAMPLE_RATES.get(user_input)
    if selected is None:
        localized_print('invalid_selection', default=default_rate)
        return default_rate
    return selected


def get_default_audio_backend(system_name: str) -> tuple[str, str]:
    """根据操作系统返回 CamillaDSP 后端类型和默认虚拟音频输入设备名称。"""
    if system_name == 'Darwin':
        return 'CoreAudio', 'BlackHole 2ch'
    if system_name == 'Windows':
        return 'WASAPI', 'CABLE Output (VB-Audio Virtual Cable)'
    if system_name == 'Linux':
        return 'ALSA', 'Virtual Audio Device'
    return 'CoreAudio', 'BlackHole 2ch'


def get_camilladsp_asset_name(system_name: str, arch: str) -> str | None:
    """根据平台返回 CamillaDSP 发行包名称关键字。"""
    if system_name == 'Darwin':
        return f'macos-{arch}.tar.gz'
    if system_name == 'Windows':
        if arch == 'amd64':
            return 'windows-amd64.zip'
        return f'windows-{arch}.zip'
    if system_name == 'Linux':
        return f'linux-{arch}.tar.gz'
    return None


def extract_archive_to_script_dir(archive_path: Path) -> bool:
    """解压 CamillaDSP 发布包到脚本目录。"""
    script_dir = Path(__file__).resolve().parent
    try:
        if archive_path.suffix == '.zip':
            with zipfile.ZipFile(archive_path, 'r') as zip_ref:
                zip_ref.extractall(script_dir)
        else:
            with tarfile.open(archive_path, 'r:gz') as tar_ref:
                tar_ref.extractall(script_dir)
        return True
    except Exception:
        return False


def get_camilladsp_executable_name(system_name: str) -> str:
    return 'camilladsp.exe' if system_name == 'Windows' else 'camilladsp'


# --- 新增：系统工具函数 ---

def is_blackhole_installed() -> bool:
    """检测当前系统是否已安装所需的虚拟音频线。"""
    system_name, _ = get_platform_info()
    if system_name == 'Darwin':
        blackhole_driver_path = Path("/Library/Audio/Plug-Ins/HAL/BlackHole2ch.driver")
        if blackhole_driver_path.exists() and blackhole_driver_path.is_dir():
            return True
        try:
            result = subprocess.run(['brew', 'list', '--cask', 'blackhole-2ch'], capture_output=True, text=True)
            return result.returncode == 0
        except Exception:
            return False

    if system_name == 'Windows':
        powershell = shutil.which('powershell') or shutil.which('pwsh')
        if powershell:
            try:
                result = subprocess.run([
                    powershell,
                    '-NoProfile',
                    '-Command',
                    'Get-CimInstance Win32_SoundDevice | Select-Object -ExpandProperty Name'
                ], capture_output=True, text=True, timeout=15)
                if result.returncode == 0 and result.stdout:
                    return 'CABLE' in result.stdout or 'VB-Audio' in result.stdout
            except Exception:
                pass
        return False

    if system_name == 'Linux':
        for cmd in (['aplay', '-l'], ['arecord', '-l']):
            if shutil.which(cmd[0]):
                try:
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                    if result.returncode == 0 and result.stdout:
                        lower_output = result.stdout.lower()
                        if 'virtual' in lower_output or 'cable' in lower_output or 'vb-audio' in lower_output:
                            return True
                except Exception:
                    pass
        return False

    return False


def install_blackhole() -> bool:
    """仅在 macOS 上尝试自动安装 BlackHole，否则返回 False。"""
    system_name, _ = get_platform_info()
    if system_name != 'Darwin':
        return False

    try:
        localized_print('installing_blackhole')
        brew_path = shutil.which('brew')
        if not brew_path:
            localized_print('homebrew_missing')
            return False

        result = subprocess.run([brew_path, 'install', '--cask', 'blackhole-2ch'], capture_output=True, text=True)
        if result.returncode == 0:
            localized_print('blackhole_installed')
            return True
        localized_print('blackhole_install_failed', error=result.stderr.strip())
        return False
    except Exception as e:
        localized_print('blackhole_install_error', error=e)
        return False


_MACOS_VIRTUAL_AUDIO_KEYWORDS = (
    'blackhole',
    'background music',
    'loopback',
    'virtual',
    'multi-output',
    '多输出',
    'aggregate',
    '聚合',
)


def _parse_macos_audio_output_candidates(
    profiler_text: str,
) -> list[tuple[str, bool]]:
    """解析 system_profiler SPAudioDataType 输出。

    返回 (设备名, 是否为 Default Output Device) 列表；已排除虚拟声卡。
    """
    current_name: str | None = None
    candidates: list[tuple[str, bool]] = []

    for raw_line in profiler_text.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue
        stripped = line.strip()
        indent = len(line) - len(line.lstrip(' '))
        # 设备名行：缩进较浅并以 ':' 结尾
        if indent <= 8 and stripped.endswith(':') and not stripped.startswith('Devices'):
            name = stripped[:-1].strip()
            if name and name not in ('Audio', 'Devices'):
                current_name = name
            continue
        if current_name is None:
            continue
        lower = stripped.lower()
        name_lower = current_name.lower()
        if any(kw in name_lower for kw in _MACOS_VIRTUAL_AUDIO_KEYWORDS):
            continue
        if 'default output device: yes' in lower:
            candidates.append((current_name, True))
        elif lower.startswith('output channels:'):
            if (current_name, False) not in candidates and (current_name, True) not in candidates:
                candidates.append((current_name, False))
    return candidates


def list_macos_playback_devices() -> list[str]:
    """列出本机可用的非虚拟 CoreAudio 播放设备名（真实耳机/音箱等）。"""
    try:
        result = subprocess.run(
            ['system_profiler', 'SPAudioDataType'],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if result.returncode != 0 or not result.stdout:
            return []
        seen: list[str] = []
        for name, _ in _parse_macos_audio_output_candidates(result.stdout):
            if name not in seen:
                seen.append(name)
        return seen
    except Exception:
        return []


def detect_macos_default_playback_device() -> str | None:
    """从 system_profiler 推断当前默认物理播放设备名（排除 BlackHole 等虚拟设备）。"""
    try:
        result = subprocess.run(
            ['system_profiler', 'SPAudioDataType'],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if result.returncode != 0 or not result.stdout:
            return None

        candidates = _parse_macos_audio_output_candidates(result.stdout)

        # 优先：标记为 Default Output Device 且非虚拟
        for name, is_default in candidates:
            if is_default:
                return name
        # 其次：任意带输出的非虚拟设备（优先含 headphone/耳机/扬声器）
        preferred_keywords = ('headphone', '耳机', 'speaker', '扬声器', 'built-in')
        non_virtual = [name for name, _ in candidates]
        for name in non_virtual:
            if any(k in name.lower() for k in preferred_keywords):
                return name
        if non_virtual:
            return non_virtual[0]
    except Exception:
        pass
    return None


# 内置耳机插孔在各语言 macOS 下的 CoreAudio 显示名（互为别名）
_BUILTIN_HEADPHONE_ALIASES = frozenset({
    'external headphones',
    'headphones',
    '外置耳机',
    '外部ヘッドフォン',
    'ヘッドフォン',
})

# 内置扬声器在各语言下的常见展示名（互为别名；真实设备常为「MacBook Pro扬声器」等）
_BUILTIN_SPEAKER_ALIASES = frozenset({
    'speakers',
    'speaker',
    'built-in speakers',
    'built-in output',
    'macbook speakers',
    '扬声器',
    '内置扬声器',
    'スピーカー',
    '内蔵スピーカー',
})


def is_builtin_headphone_label(name: str) -> bool:
    """判断是否为系统内置耳机插孔的本地化名称。"""
    if not name:
        return False
    lowered = name.strip().lower()
    if lowered in {a.lower() for a in _BUILTIN_HEADPHONE_ALIASES}:
        return True
    # 宽松匹配：含 headphone / 耳机 / ヘッドフォン（排除「扬声器」误伤）
    if '扬声器' in name or 'speaker' in lowered:
        return False
    return (
        'headphone' in lowered
        or '耳机' in name
        or 'ヘッドフォン' in name
        or 'ヘッドホン' in name
    )


def is_builtin_speaker_label(name: str) -> bool:
    """判断是否为内置扬声器相关名称（含 MacBook Pro扬声器 等真实设备名）。"""
    if not name:
        return False
    lowered = name.strip().lower()
    if lowered in {a.lower() for a in _BUILTIN_SPEAKER_ALIASES}:
        return True
    return (
        'speaker' in lowered
        or '扬声器' in name
        or 'スピーカー' in name
    )


def localized_default_playback_label(kind: str = 'headphones') -> str:
    """按当前界面语言返回默认播放设备的展示名（不依赖系统探测结果的语言）。"""
    if kind == 'speakers':
        return translate('default_playback_speakers')
    if kind == 'linux':
        return translate('default_playback_linux')
    return translate('default_playback_headphones')


def display_name_for_playback_device(real_name: str) -> str:
    """将真实 CoreAudio 设备名转为当前界面语言的展示名。

    配置文件仍应使用 real_name；提示文案使用本函数结果，避免英文界面里出现「外置耳机」。
    """
    if is_builtin_headphone_label(real_name):
        return localized_default_playback_label('headphones')
    return real_name


def _match_playback_device_among(text: str, available: list[str]) -> str | None:
    """在可用设备列表中做精确 / 忽略大小写 / 子串匹配。"""
    if not text or not available:
        return None
    for name in available:
        if name == text:
            return name
    lower = text.lower()
    for name in available:
        if name.lower() == lower:
            return name
    # 子串：用户填「扬声器」应对上「MacBook Pro扬声器」
    for name in available:
        if lower in name.lower() or name.lower() in lower:
            return name
    return None


def resolve_playback_device_name(
    user_or_display: str,
    detected_real: str | None = None,
    available: list[str] | None = None,
) -> str:
    """把用户输入 / 展示名解析为应写入 CamillaDSP 配置的真实设备名。

    关键规则：
    - 绝不把「外置耳机」这类别名原样写进配置（设备未接入时不存在）；
    - 优先匹配本机当前可用的 CoreAudio 播放设备；
    - 耳机别名但未插入耳机时，回退到系统当前默认输出（如 MacBook Pro扬声器）。
    """
    system_name, _ = get_platform_info()
    text = (user_or_display or '').strip()

    if available is None and system_name == 'Darwin':
        available = list_macos_playback_devices()
    available = list(available or [])

    if detected_real is None and system_name == 'Darwin':
        detected_real = detect_macos_default_playback_device()

    # 1) 直接命中可用设备
    matched = _match_playback_device_among(text, available) if text else None
    if matched:
        return matched

    # 2) 耳机别名 → 可用耳机设备，否则当前默认（扬声器等）
    if text and is_builtin_headphone_label(text):
        for name in available:
            if is_builtin_headphone_label(name):
                return name
        if detected_real:
            return detected_real
        if available:
            return available[0]
        # 最后才用本地化展示名（可能仍失败，但避免 silently 丢输入）
        return localized_default_playback_label('headphones')

    # 3) 扬声器别名 → 可用扬声器设备 / 默认
    if text and is_builtin_speaker_label(text):
        for name in available:
            if is_builtin_speaker_label(name):
                return name
        if detected_real:
            return detected_real
        if available:
            return available[0]
        return localized_default_playback_label('speakers')

    # 4) 空输入 → 系统默认
    if not text:
        if detected_real:
            return detected_real
        if available:
            return available[0]
        return localized_default_playback_label('headphones')

    # 5) 用户填了未知名且不在列表中：优先系统默认，避免写死幽灵设备名
    if available and detected_real:
        return detected_real
    if detected_real:
        return detected_real
    if available:
        return available[0]
    return text


def set_config_playback_device(config_path: Path, output_device: str) -> bool:
    """就地更新 YAML 中 playback.device，不改动 capture 与其它字段。

    用于「加载预设」时套用 GUI 当前播放设备，避免旧预设仍写着已不存在的「外置耳机」。
    """
    path = Path(config_path)
    try:
        text = path.read_text(encoding='utf-8')
    except Exception:
        return False
    # 仅替换 playback 段下的 device 行（capture 在前，playback 在后）
    pattern = re.compile(
        r'(playback:\s*\n(?:[ \t]+[^\n]+\n)*?[ \t]+device:\s*)(?:"[^"]*"|\'[^\']*\'|[^\n]+)',
        re.MULTILINE,
    )
    new_text, n = pattern.subn(rf'\1"{output_device}"', text, count=1)
    if n == 0:
        return False
    try:
        path.write_text(new_text, encoding='utf-8')
        return True
    except Exception:
        return False


def get_output_device_name() -> str:
    """获取用户输入的实际播放（输出）设备名称。

    注意：capture 使用虚拟声卡（如 BlackHole），playback 必须是真实耳机/音箱。
    二者不能写成同一个设备，否则会出现无声或回环。

    提示中的默认名随界面语言变化；写入 CamillaDSP 时使用系统真实设备名。
    """
    system_name, _ = get_platform_info()
    detected_real: str | None = None
    available: list[str] = []

    if system_name == 'Darwin':
        available = list_macos_playback_devices()
        detected_real = detect_macos_default_playback_device()
        if detected_real:
            # 界面提示用真实名（如 MacBook Pro扬声器），避免误导成「外置耳机」
            display_default = detected_real
        else:
            display_default = localized_default_playback_label('speakers')
        localized_print('output_device_macos_note')
    elif system_name == 'Windows':
        display_default = localized_default_playback_label('speakers')
    elif system_name == 'Linux':
        display_default = localized_default_playback_label('linux')
    else:
        display_default = localized_default_playback_label('headphones')

    user_input = prompt('output_device_prompt', default_name=display_default).strip()

    capture_aliases = {
        'blackhole 2ch', 'blackhole', 'blackhole2ch',
        'cable output (vb-audio virtual cable)', 'cable output',
    }
    if user_input and (
        user_input.lower() in capture_aliases or user_input.lower().startswith('blackhole')
    ):
        localized_print(
            'capture_device_as_playback',
            user_input=user_input,
            default_name=display_default,
        )
        return resolve_playback_device_name(display_default, detected_real, available)

    if not user_input:
        return resolve_playback_device_name(display_default, detected_real, available)

    return resolve_playback_device_name(user_input, detected_real, available)


def is_camilladsp_installed() -> bool:
    """检测与当前 Python 脚本同目录下是否有 camilladsp 可执行文件"""
    system_name, _ = get_platform_info()
    script_dir = Path(__file__).resolve().parent
    camilla_path = script_dir / get_camilladsp_executable_name(system_name)
    if not camilla_path.exists():
        return False
    if system_name == 'Windows':
        return True
    return os.access(camilla_path, os.X_OK)


def download_camilladsp() -> bool:
    """从 GitHub 下载 CamillaDSP 引擎，支持 macOS/Windows/Linux 自动选择包。"""
    try:
        localized_print('download_camilladsp')
        system_name, machine_arch = get_platform_info()

        api_url = "https://api.github.com/repos/HEnquist/camilladsp/releases/latest"
        retries = len(MIRROR_PREFIXES) + 1
        release_data = json.loads(fetch_text_url(api_url, timeout=30.0, retries=retries, backoff_factor=1.0))

        target_asset_name = get_camilladsp_asset_name(system_name, machine_arch)
        if not target_asset_name:
            localized_print('camilladsp_asset_not_found')
            return False

        asset_url = None
        for asset in release_data.get('assets', []):
            if target_asset_name in asset.get('name', ''):
                asset_url = asset.get('browser_download_url')
                break

        if not asset_url:
            localized_print('camilladsp_asset_not_found')
            return False

        localized_print('downloading_file', filename=asset_url)
        retries = len(MIRROR_PREFIXES) + 1
        archive_data = fetch_url(asset_url, timeout=60.0, retries=retries, backoff_factor=1.0)

        suffix = '.zip' if asset_url.endswith('.zip') else '.tar.gz'
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
            tmp_file.write(archive_data)
            tmp_file_path = tmp_file.name

        try:
            archive_path = Path(tmp_file_path)
            if not extract_archive_to_script_dir(archive_path):
                localized_print('camilladsp_executable_missing')
                return False

            executable_name = get_camilladsp_executable_name(system_name)
            script_dir = Path(__file__).resolve().parent
            camilla_path = script_dir / executable_name

            if not camilla_path.exists():
                # 如果解压后没有直接生成可执行文件，则尝试从解压目录中查找
                found = list(script_dir.rglob(executable_name))
                if found:
                    camilla_path = found[0]
                else:
                    localized_print('camilladsp_executable_missing')
                    return False

            if system_name != 'Windows':
                camilla_path.chmod(0o755)
            # 新机摩擦：下载的未签名二进制常带 quarantine，尽量清除以便首次执行
            if system_name == 'Darwin':
                try:
                    subprocess.run(
                        ['xattr', '-dr', 'com.apple.quarantine', str(camilla_path)],
                        capture_output=True,
                        timeout=10,
                    )
                    # 同目录可能还有解压残留带标记
                    subprocess.run(
                        ['xattr', '-dr', 'com.apple.quarantine', str(script_dir / 'camilladsp')],
                        capture_output=True,
                        timeout=10,
                    )
                except Exception:
                    pass
            localized_print('camilladsp_download_success')
            return True
        finally:
            Path(tmp_file_path).unlink(missing_ok=True)
    except Exception as e:
        localized_print('camilladsp_download_error', error=e)
        return False


def metrics_from_correction(correction: dict | None) -> dict:
    """从 calculate_correction 结果提取可序列化指标（供写入预设）。

    peq_rmse / combined_rmse 始终保存「计算时的真实值」，不随 FIR 开/关被覆盖。
    若会话里曾把 combined_rmse 临时改成 IIR 显示值，优先使用 fir_combined_rmse 快照。
    """
    if not correction:
        return {}
    out: dict = {}

    def _f(key: str):
        val = correction.get(key)
        if val is None:
            return None
        try:
            return float(val)
        except Exception:
            return None

    peq_rmse = _f('peq_rmse')
    # 联合 RMSE：优先 FIR 快照，避免 IIR 模式写盘时污染
    combined = _f('fir_combined_rmse')
    if combined is None:
        combined = _f('combined_rmse')
    # 若 combined 被错误写成与 peq 相同，而快照里有更好的值已处理；
    # 若仅有 peq，combined 可等于 peq（未触发 FIR 时合理）
    fir_rmse = _f('fir_rmse')
    # 峰值：FIR 模式用联合峰；一并保存 IIR 峰便于切换
    fir_peak = _f('fir_response_peak')
    iir_peak = _f('iir_response_peak')
    peak = fir_peak if fir_peak is not None else _f('response_peak')
    valley = _f('fir_response_valley')
    if valley is None:
        valley = _f('response_valley')
    offset = _f('level_offset_db')

    if peq_rmse is not None:
        out['peq_rmse'] = peq_rmse
    if combined is not None:
        out['combined_rmse'] = combined
    if fir_rmse is not None:
        out['fir_rmse'] = fir_rmse
    if peak is not None:
        out['response_peak'] = peak  # 规范：联合/当前计算峰值
    if iir_peak is not None:
        out['iir_response_peak'] = iir_peak
    if fir_peak is not None:
        out['fir_response_peak'] = fir_peak
    if valley is not None:
        out['response_valley'] = valley
    if offset is not None:
        out['level_offset_db'] = offset

    if correction.get('fir_n_taps') is not None:
        try:
            out['fir_n_taps'] = int(correction['fir_n_taps'])
        except Exception:
            pass
    if 'use_fir' in correction:
        out['use_fir'] = bool(correction.get('use_fir'))
    return out


def write_config_metrics(config_path: Path, metrics: dict | None) -> None:
    """将指标写入 YAML 顶部注释行（# eq_cosplay_metrics: {...}）。"""
    if not metrics:
        return
    path = Path(config_path)
    try:
        text = path.read_text(encoding='utf-8')
    except Exception:
        return
    # 去掉旧 metrics 注释
    lines = [
        ln
        for ln in text.splitlines(keepends=True)
        if not ln.lstrip().startswith('# eq_cosplay_metrics:')
    ]
    payload = {
        k: metrics[k]
        for k in (
            'peq_rmse',
            'combined_rmse',
            'fir_rmse',
            'response_peak',
            'response_valley',
            'iir_response_peak',
            'fir_response_peak',
            'level_offset_db',
            'fir_n_taps',
            'use_fir',
        )
        if k in metrics and metrics[k] is not None
    }
    if not payload:
        return
    try:
        meta_line = '# eq_cosplay_metrics: ' + json.dumps(payload, ensure_ascii=False) + '\n'
    except Exception:
        return
    # 插在开头（CamillaDSP 忽略 # 注释）
    path.write_text(meta_line + ''.join(lines), encoding='utf-8')


def load_config_metrics(config_path: Path) -> dict:
    """读取预设 YAML 顶部的 eq_cosplay_metrics 注释。"""
    path = Path(config_path)
    try:
        with path.open('r', encoding='utf-8', errors='replace') as fh:
            for _ in range(30):
                line = fh.readline()
                if not line:
                    break
                stripped = line.strip()
                if stripped.startswith('# eq_cosplay_metrics:'):
                    raw = stripped.split(':', 1)[1].strip()
                    data = json.loads(raw)
                    return data if isinstance(data, dict) else {}
                # 跳过其它注释与空行；遇到正式 YAML 则停止
                if stripped and not stripped.startswith('#'):
                    break
    except Exception:
        pass
    return {}


def generate_camilladsp_config(
    peq_list: list[dict],
    output_device: str,
    config_path: Path,
    pre_amp: float = 0.0,
    samplerate: int = DEFAULT_SAMPLE_RATE,
    backend_type: str = 'CoreAudio',
    capture_device: str = 'BlackHole 2ch',
    fir_ir: np.ndarray | None = None,
    metrics: dict | None = None,
) -> None:
    """生成合规的 CamillaDSP YAML。

    可选 FIR：写入与 yml 同目录的 mono WAV，左右声道各一条 Conv 流水线，
    并在其后串联 10 段 IIR PEQ（与示例格式一致）。
    metrics：可选，写入顶部注释供 GUI 恢复 RMSE 等指标。
    """
    config_path = Path(config_path)
    config_path.parent.mkdir(parents=True, exist_ok=True)

    fir_left_path: Path | None = None
    fir_right_path: Path | None = None
    if fir_ir is not None and len(fir_ir) > 0:
        stem = config_path.with_suffix("")
        fir_left_path = Path(f"{stem}_fir_left.wav")
        fir_right_path = Path(f"{stem}_fir_right.wav")
        write_fir_wav(fir_left_path, fir_ir, float(samplerate))
        write_fir_wav(fir_right_path, fir_ir, float(samplerate))
        localized_print('fir_saved', left=fir_left_path, right=fir_right_path)

    # 保留旧文件中的 metrics（重新生成时若未传入则沿用）
    preserved = load_config_metrics(config_path) if config_path.is_file() else {}
    merged_metrics = dict(preserved)
    if metrics:
        for k, v in metrics.items():
            if v is None:
                continue
            # 保护：IIR 模式部署时不要把 combined_rmse 降级写成 peq_rmse
            if (
                k == 'combined_rmse'
                and 'combined_rmse' in preserved
                and 'peq_rmse' in metrics
            ):
                try:
                    incoming = float(v)
                    peq_v = float(metrics.get('peq_rmse'))
                    old = float(preserved['combined_rmse'])
                    if abs(incoming - peq_v) < 1e-9 and old + 1e-12 < peq_v:
                        # 旧联合 RMSE 更好（更小），保留
                        continue
                except Exception:
                    pass
            merged_metrics[k] = v
    if fir_ir is not None and len(fir_ir) > 0:
        merged_metrics['use_fir'] = True
        merged_metrics['fir_n_taps'] = int(len(fir_ir))
    elif metrics is not None and 'use_fir' in metrics:
        merged_metrics['use_fir'] = bool(metrics.get('use_fir'))
    else:
        # 本次明确生成 IIR-only 时标记，但不抹掉 peq_rmse / combined 历史
        if metrics is not None:
            merged_metrics['use_fir'] = False

    meta_header = ''
    if merged_metrics:
        try:
            slim = {
                k: merged_metrics[k]
                for k in (
                    'peq_rmse',
                    'combined_rmse',
                    'fir_rmse',
                    'response_peak',
                    'response_valley',
                    'iir_response_peak',
                    'fir_response_peak',
                    'level_offset_db',
                    'fir_n_taps',
                    'use_fir',
                )
                if k in merged_metrics and merged_metrics[k] is not None
            }
            if slim:
                meta_header = '# eq_cosplay_metrics: ' + json.dumps(slim, ensure_ascii=False) + '\n'
        except Exception:
            meta_header = ''

    yaml_content = f"""{meta_header}---
devices:
  samplerate: {samplerate}
  chunksize: 1024
  capture:
    type: {backend_type}
    channels: 2
    device: "{capture_device}"
  playback:
    type: {backend_type}
    channels: 2
    device: "{output_device}"

filters:
"""

    if pre_amp != 0.0:
        yaml_content += "  preamp_gain:\n"
        yaml_content += "    type: Gain\n"
        yaml_content += "    parameters:\n"
        yaml_content += f"      gain: {pre_amp}\n"
        yaml_content += "      inverted: false\n\n"

    if fir_left_path is not None and fir_right_path is not None:
        # 使用绝对路径，避免 CamillaDSP 工作目录导致找不到 WAV
        left_abs = fir_left_path.resolve().as_posix()
        right_abs = fir_right_path.resolve().as_posix()
        yaml_content += "  fir_left:\n"
        yaml_content += "    type: Conv\n"
        yaml_content += "    parameters:\n"
        yaml_content += "      type: Wav\n"
        yaml_content += f'      filename: "{left_abs}"\n'
        yaml_content += "      channel: 0\n\n"
        yaml_content += "  fir_right:\n"
        yaml_content += "    type: Conv\n"
        yaml_content += "    parameters:\n"
        yaml_content += "      type: Wav\n"
        yaml_content += f'      filename: "{right_abs}"\n'
        yaml_content += "      channel: 0\n\n"

    for i, band in enumerate(peq_list):
        filter_name = f"peq_{i+1:02d}"
        yaml_content += f"  {filter_name}:\n"
        yaml_content += "    type: Biquad\n"
        yaml_content += "    parameters:\n"
        yaml_content += f"      type: {band['filter_type']}\n"
        yaml_content += f"      freq: {band['frequency']}\n"
        yaml_content += f"      gain: {band['gain']}\n"
        yaml_content += f"      q: {band['Q']}\n"

    peq_names = [f"peq_{i+1:02d}" for i in range(len(peq_list))]

    yaml_content += "\npipeline:\n"
    if fir_left_path is not None:
        # 分声道：FIR →（可选 preamp）→ IIR PEQ
        for ch, fir_name in ((0, "fir_left"), (1, "fir_right")):
            yaml_content += "  - type: Filter\n"
            yaml_content += f"    channels: [{ch}]\n"
            yaml_content += "    names:\n"
            if pre_amp != 0.0:
                yaml_content += "      - preamp_gain\n"
            yaml_content += f"      - {fir_name}\n"
            for name in peq_names:
                yaml_content += f"      - {name}\n"
    else:
        yaml_content += "  - type: Filter\n"
        yaml_content += "    channels: [0, 1]\n"
        yaml_content += "    names:\n"
        if pre_amp != 0.0:
            yaml_content += "      - preamp_gain\n"
        for name in peq_names:
            yaml_content += f"      - {name}\n"

    with open(config_path, 'w', encoding='utf-8') as f:
        f.write(yaml_content)

    localized_print('config_generated', path=config_path)


def dump_yaml_config(config_path: Path) -> None:
    """打印生成的 YAML 配置以便调试"""
    localized_print('yaml_dump_header')
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            print(f.read(), end='', flush=True)
    except Exception as exc:
        localized_print('unknown_error', error=exc)


def dump_audio_device_list() -> None:
    """打印当前系统音频设备列表，便于调试路由问题。"""
    localized_print('audio_device_list_header')
    system_name, _ = get_platform_info()
    try:
        if system_name == 'Darwin':
            command = ['system_profiler', 'SPAudioDataType']
        elif system_name == 'Windows':
            powershell = shutil.which('powershell') or shutil.which('pwsh')
            if powershell:
                command = [powershell, '-NoProfile', '-Command', 'Get-CimInstance Win32_SoundDevice | Select-Object -ExpandProperty Name']
            else:
                command = ['cmd', '/c', 'echo', 'Unable to query audio devices without PowerShell']
        elif system_name == 'Linux':
            if shutil.which('aplay'):
                command = ['aplay', '-l']
            elif shutil.which('arecord'):
                command = ['arecord', '-l']
            else:
                command = ['bash', '-lc', 'echo "No ALSA query tool found"']
        else:
            command = ['echo', 'Unsupported audio device listing platform']

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=20,
            shell=False,
        )
        if result.stdout:
            print(result.stdout, flush=True)
        if result.stderr:
            print(result.stderr, flush=True)
    except Exception as exc:
        localized_print('unknown_error', error=exc)


def stream_camilladsp_output(process: subprocess.Popen) -> None:
    """后台读取 CamillaDSP 日志并实时打印到主终端（无法打开独立窗口时的回退方案）。"""
    prefix = translate('log_prefix')
    try:
        if process.stdout is None:
            return
        for line in process.stdout:
            if line:
                print(f"{prefix} {line.rstrip()}", flush=True)
    except Exception:
        pass


def _apple_script_escape(value: str) -> str:
    """转义 AppleScript 字符串中的反斜杠与双引号。"""
    return value.replace('\\', '\\\\').replace('"', '\\"')


def _shell_single_quote(value: str) -> str:
    """POSIX shell 单引号包裹（安全嵌入任意路径/标题）。"""
    return "'" + str(value).replace("'", "'\"'\"'") + "'"


def _write_log_viewer_script(log_path: Path, title: str) -> Path:
    """生成干净的日志查看脚本：不加载 shell 配置，避免 profile 噪声与参数误解析。

    历史问题：在 do script 里写 printf '\\e]0;TITLE\\a' 时，未加引号的 ';'
    会被 shell 当成命令分隔符，把标题拆成多条命令，误执行项目里的 camilladsp。
    """
    log_str = str(log_path.resolve())
    # 窗口标题保持简短；完整说明放正文
    short_title = 'CamillaDSP Log'
    # viewer 辅助脚本也放在 logs/ 下，避免污染项目根或系统临时目录散落
    script_path = get_logs_dir() / f"logview_{os.getpid()}.sh"
    # 脚本内全部用单引号变量赋值，避免空格/分号/破折号被解析
    content = f"""#!/bin/bash
# EQ Cosplay — CamillaDSP log viewer (no user profile)
# Generated; safe to delete after session.
set +e
clear 2>/dev/null || true
TITLE={_shell_single_quote(short_title)}
FULL_TITLE={_shell_single_quote(title)}
LOG={_shell_single_quote(log_str)}

# OSC 0: set window title — entire sequence must stay ONE argument
printf '\\033]0;%s\\007' "$TITLE"

echo "$FULL_TITLE"
echo "---"
echo "file: $LOG"
echo "tip:  this window only follows the log; CamillaDSP is managed by the main program"
echo "---"

# Wait briefly for the log file to appear
i=0
while [ ! -f "$LOG" ] && [ "$i" -lt 50 ]; do
  sleep 0.1
  i=$((i + 1))
done

if [ ! -f "$LOG" ]; then
  echo "[WARN] log file not found yet: $LOG"
fi

# Follow from the beginning so startup lines are visible
exec tail -n +1 -f "$LOG"
"""
    script_path.write_text(content, encoding='utf-8')
    script_path.chmod(0o755)
    return script_path


def open_camilladsp_log_window(log_path: Path) -> bool:
    """在独立终端窗口中 tail -f CamillaDSP 日志。成功返回 True。

    使用临时 viewer 脚本 + 无 profile 的 shell，避免：
    - 登录脚本噪声（如 openclaw/compdef）
    - OSC 标题串中 ';' 被拆成多条命令、误启动 camilladsp
    """
    system_name, _ = get_platform_info()
    title = translate('camilladsp_log_window_title')
    log_str = str(log_path.resolve())

    try:
        viewer = _write_log_viewer_script(log_path, title)

        if system_name == 'Darwin':
            # AppleScript quoted form 保证路径安全；bash --noprofile --norc 跳过用户配置
            helper_as = _apple_script_escape(str(viewer))
            script = (
                f'set helperPath to "{helper_as}"\n'
                'tell application "Terminal"\n'
                '    activate\n'
                '    do script "bash --noprofile --norc " & quoted form of helperPath\n'
                'end tell'
            )
            result = subprocess.run(
                ['osascript', '-e', script],
                capture_output=True,
                text=True,
                timeout=15,
            )
            return result.returncode == 0

        if system_name == 'Windows':
            # 干净 PowerShell，不加载 profile
            t = title.replace("'", "''")
            lp = log_str.replace("'", "''")
            ps_cmd = (
                f"$Host.UI.RawUI.WindowTitle = '{t}'; "
                f"Clear-Host; "
                f"Write-Host '{t}'; "
                f"Write-Host '---'; "
                f"Write-Host 'file: {lp}'; "
                f"Write-Host '---'; "
                f"Get-Content -LiteralPath '{lp}' -Wait -Tail 200"
            )
            creationflags = getattr(subprocess, 'CREATE_NEW_CONSOLE', 0x00000010)
            subprocess.Popen(
                ['powershell', '-NoProfile', '-NoExit', '-Command', ps_cmd],
                creationflags=creationflags,
            )
            return True

        if system_name == 'Linux':
            import shlex
            # 无 profile 启动 viewer 脚本
            run_cmd = f"bash --noprofile --norc {shlex.quote(str(viewer))}"
            launchers = [
                ['gnome-terminal', '--', 'bash', '--noprofile', '--norc', str(viewer)],
                ['konsole', '-e', 'bash', '--noprofile', '--norc', str(viewer)],
                ['xfce4-terminal', '-T', 'CamillaDSP Log', '-e', run_cmd],
                ['xterm', '-T', 'CamillaDSP Log', '-e', 'bash', '--noprofile', '--norc', str(viewer)],
                ['x-terminal-emulator', '-e', 'bash', '--noprofile', '--norc', str(viewer)],
            ]
            for cmd in launchers:
                if shutil.which(cmd[0]):
                    subprocess.Popen(cmd, start_new_session=True)
                    return True
            return False

        return False
    except Exception:
        return False


def append_camilladsp_log_marker(log_path: Path | None) -> None:
    """向日志文件写入停止标记，便于独立窗口用户看到结束状态。"""
    if log_path is None:
        return
    try:
        with open(log_path, 'a', encoding='utf-8') as fh:
            fh.write('\n' + translate('camilladsp_log_end_marker') + '\n')
            fh.flush()
    except Exception:
        pass


def list_camilladsp_pids() -> list[int]:
    """枚举系统中正在运行的 CamillaDSP 进程 PID（不含本 Python 进程）。"""
    system_name, _ = get_platform_info()
    pids: list[int] = []
    try:
        if system_name == "Windows":
            # tasklist CSV: "camilladsp.exe","1234",...
            result = subprocess.run(
                [
                    "tasklist",
                    "/FI",
                    "IMAGENAME eq camilladsp.exe",
                    "/FO",
                    "CSV",
                    "/NH",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            for line in (result.stdout or "").splitlines():
                line = line.strip()
                if not line or "camilladsp" not in line.lower():
                    continue
                # "camilladsp.exe","1234","Session Name","Session#","Mem Usage"
                parts = [p.strip().strip('"') for p in line.split(",")]
                if len(parts) >= 2 and parts[1].isdigit():
                    pids.append(int(parts[1]))
        else:
            # -x 精确匹配进程名 camilladsp
            result = subprocess.run(
                ["pgrep", "-x", "camilladsp"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            for tok in (result.stdout or "").split():
                if tok.isdigit():
                    pids.append(int(tok))
            # 兼容部分环境进程名带路径后缀或未注册为短名：用 pgrep -f 再筛一遍
            if not pids:
                result2 = subprocess.run(
                    ["pgrep", "-f", "[/\\\\]camilladsp(\\s|$)"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                for tok in (result2.stdout or "").split():
                    if tok.isdigit():
                        pids.append(int(tok))
    except Exception:
        pass
    # 去重、排除当前解释器
    me = os.getpid()
    return sorted({p for p in pids if p != me})


def stop_existing_camilladsp_instances(*, announce: bool = True) -> int:
    """启动前停止已有 CamillaDSP，保证同时仅一个实例。

    返回实际停止的进程数。仅当 count > 0 且 announce=True 时打印提示。
    """
    pids = list_camilladsp_pids()
    if not pids:
        return 0

    system_name, _ = get_platform_info()
    stopped = 0
    try:
        if system_name == "Windows":
            # 先按 PID 温和结束，再兜底 image name
            for pid in pids:
                r = subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                if r.returncode == 0:
                    stopped += 1
            # 残留同名进程
            left = list_camilladsp_pids()
            if left:
                subprocess.run(
                    ["taskkill", "/F", "/IM", "camilladsp.exe"],
                    capture_output=True,
                    timeout=15,
                )
                time.sleep(0.3)
                stopped = max(stopped, len(pids) - len(list_camilladsp_pids()))
        else:
            for pid in pids:
                try:
                    os.kill(pid, 15)  # SIGTERM
                except ProcessLookupError:
                    continue
                except Exception:
                    try:
                        os.kill(pid, 9)
                    except Exception:
                        continue
            # 等待退出
            deadline = time.time() + 2.0
            while time.time() < deadline:
                left = list_camilladsp_pids()
                if not left:
                    break
                time.sleep(0.1)
            left = list_camilladsp_pids()
            if left:
                for pid in left:
                    try:
                        os.kill(pid, 9)  # SIGKILL
                    except Exception:
                        pass
                subprocess.run(["pkill", "-9", "-x", "camilladsp"], capture_output=True, timeout=10)
                time.sleep(0.2)
            stopped = len(pids) - len(list_camilladsp_pids())
            if stopped <= 0 and pids:
                # 已全部消失但计数边界：至少算检测到并尝试停止过
                stopped = len(pids) if not list_camilladsp_pids() else max(1, len(pids) - len(list_camilladsp_pids()))
    except Exception:
        # 最后兜底
        try:
            if system_name == "Windows":
                subprocess.run(
                    ["taskkill", "/F", "/IM", "camilladsp.exe"],
                    capture_output=True,
                    timeout=15,
                )
            else:
                subprocess.run(["pkill", "-9", "-x", "camilladsp"], capture_output=True, timeout=10)
        except Exception:
            pass
        stopped = len(pids)

    if stopped > 0 and announce:
        localized_print("camilladsp_previous_stopped", count=stopped)
    return max(0, stopped)


def terminate_camilladsp(process: subprocess.Popen, log_path: Path | None = None) -> None:
    """终止本会话启动的 CamillaDSP，并清理残留实例（不提示）。"""
    append_camilladsp_log_marker(log_path)
    try:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except Exception:
                process.kill()
    except Exception:
        pass
    system_name, _ = get_platform_info()
    try:
        if system_name == "Windows" and getattr(process, "pid", None):
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                capture_output=True,
                timeout=15,
            )
    except Exception:
        pass
    # 清场其它残留，用户主动停止时不弹「已停止旧实例」提示
    stop_existing_camilladsp_instances(announce=False)
    log_fh = getattr(process, "_cosplay_log_fh", None)
    if log_fh is not None:
        try:
            log_fh.close()
        except Exception:
            pass


def run_camilladsp(config_path: Path, debug: bool = False) -> tuple[subprocess.Popen | None, Path | None]:
    """运行 CamillaDSP，日志写入文件并尽量在独立窗口展示。

    启动前检测并停止已有 CamillaDSP，保证同时仅一个实例。
    仅当确实停止了旧进程时才会提示。

    返回 (process, log_path)；启动失败时 process 为 None。
    """
    log_path: Path | None = None
    log_fh = None
    try:
        system_name, _ = get_platform_info()
        # 单实例：有旧进程才停止并提示，没有则静默
        stopped = stop_existing_camilladsp_instances(announce=True)
        time.sleep(0.4 if stopped > 0 else 0.05)

        script_dir = Path(__file__).resolve().parent
        executable_name = get_camilladsp_executable_name(system_name)
        # CamillaDSP 4.x: 配置文件是位置参数；-c/--check 表示“仅校验配置后退出”，不能用来指定配置文件
        command = [str(script_dir / executable_name)]
        if debug:
            command += ['-l', 'debug']
        else:
            command += ['-l', 'info']
        command.append(str(config_path.resolve()))

        # 日志统一写入 logs/，不再散落在项目根目录
        log_path = make_log_path("camilladsp")
        log_fh = open(log_path, 'w', encoding='utf-8', buffering=1)
        # 简洁日志头：避免特殊符号干扰 tail/终端显示
        log_fh.write(f"# EQ Cosplay / CamillaDSP log\n")
        log_fh.write(f"# started: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        log_fh.write(f"# config:  {config_path.resolve()}\n")
        log_fh.write(f"# level:   {'debug' if debug else 'info'}\n")
        log_fh.write("# ---\n")
        log_fh.flush()

        localized_print('starting_camilladsp')
        process = subprocess.Popen(
            command,
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        process._cosplay_log_fh = log_fh  # type: ignore[attr-defined]

        window_ok = open_camilladsp_log_window(log_path)
        if window_ok:
            localized_print('camilladsp_log_window_opened', path=log_path)
        else:
            localized_print('camilladsp_log_window_failed', error='no terminal launcher')
            localized_print('camilladsp_log_file_hint', path=log_path)
            # 独立窗口失败时回退：从文件尾部跟随输出到主终端
            def _tail_log_to_main(path: Path, proc: subprocess.Popen) -> None:
                prefix = translate('log_prefix')
                try:
                    with open(path, 'r', encoding='utf-8', errors='replace') as fh:
                        fh.seek(0, os.SEEK_END)
                        while proc.poll() is None:
                            line = fh.readline()
                            if line:
                                print(f"{prefix} {line.rstrip()}", flush=True)
                            else:
                                time.sleep(0.2)
                        # 进程结束后读完剩余
                        for line in fh:
                            print(f"{prefix} {line.rstrip()}", flush=True)
                except Exception:
                    pass

            threading.Thread(
                target=_tail_log_to_main,
                args=(log_path, process),
                daemon=True,
            ).start()

        # 给进程一点启动时间：若因设备名错误等立刻退出，不要误报“已成功启动”
        time.sleep(1.5)
        if process.poll() is not None:
            localized_print(
                'camilladsp_failed',
                error=translate('camilladsp_exited_early', code=process.returncode),
            )
            localized_print('camilladsp_log_file_hint', path=log_path)
            try:
                # 把日志尾部贴到主窗口，方便立刻排查
                tail = log_path.read_text(encoding='utf-8', errors='replace').splitlines()[-30:]
                for line in tail:
                    print(f"{translate('log_prefix')} {line}", flush=True)
            except Exception:
                pass
            try:
                log_fh.close()
            except Exception:
                pass
            return None, log_path

        localized_print('camilladsp_started')
        localized_print('camilladsp_engine_running')
        return process, log_path
    except Exception as exc:
        localized_print('camilladsp_failed', error=exc)
        if log_fh is not None:
            try:
                log_fh.close()
            except Exception:
                pass
        return None, log_path


# --- 显示函数 ---

def get_display_width(text: str) -> int:
    """计算终端显示宽度，支持 CJK 全角字符和组合符号。"""
    width = 0
    for ch in str(text):
        if unicodedata.category(ch) == 'Mn':
            continue
        if unicodedata.east_asian_width(ch) in ('F', 'W'):
            width += 2
        else:
            width += 1
    return width


def pad_text(text: str, width: int, align: str = 'left') -> str:
    """按终端显示宽度对字符串进行填充。"""
    text = str(text)
    current_width = get_display_width(text)
    padding = max(width - current_width, 0)
    if align == 'right':
        return ' ' * padding + text
    elif align == 'center':
        left = padding // 2
        right = padding - left
        return ' ' * left + text + ' ' * right
    return text + ' ' * padding


def print_peq_table(peq_list: list[dict]) -> None:
    """用 gum table（边框 #00d7ff）打印 PEQ 表格；无 gum 时 ASCII 回退。"""
    headers = [
        translate('peq_table_band'),
        translate('peq_table_type'),
        translate('peq_table_frequency'),
        translate('peq_table_gain'),
        translate('peq_table_q'),
    ]

    rows = []
    for idx, band in enumerate(peq_list, start=1):
        filter_type = band.get('filter_type', 'N/A')
        frequency = f"{band.get('frequency', 0.0):.1f}"
        gain_value = band.get('gain', 0.0)
        gain_str = f"{gain_value:.2f}"
        if abs(gain_value) > 6.0:
            gain_str = f"*{gain_value:.2f}"
        q_value = f"{band.get('Q', 0.0):.2f}"
        rows.append([str(idx), filter_type, frequency, gain_str, q_value])

    localized_print('peq_table_title')
    print_table(headers, rows)
    localized_print('plugin_note')


def print_delta_summary(source_csv_path: Path, target_csv_path: Path) -> None:
    """打印频响差值的简要统计（gum table）。"""
    source_freqs, source_mags = parse_csv_response(source_csv_path)
    target_freqs, target_mags = parse_csv_response(target_csv_path)
    grid_freqs = make_log_freqs(512)
    delta_db = np.interp(grid_freqs, target_freqs, target_mags) - np.interp(grid_freqs, source_freqs, source_mags)

    peak = float(np.max(delta_db))
    valley = float(np.min(delta_db))
    mean = float(np.mean(delta_db))

    localized_print('delta_summary_heading')
    metric_headers = ['Metric', 'Value']
    if LANG == 'zh':
        metric_rows = [
            ['最大提升', f'{peak:+.2f} dB'],
            ['最大衰减', f'{valley:+.2f} dB'],
            ['平均差异', f'{mean:+.2f} dB'],
        ]
    elif LANG == 'ja':
        metric_rows = [
            ['最大ブースト', f'{peak:+.2f} dB'],
            ['最大減衰', f'{valley:+.2f} dB'],
            ['平均差', f'{mean:+.2f} dB'],
        ]
    else:
        metric_rows = [
            ['Peak boost', f'{peak:+.2f} dB'],
            ['Max attenuation', f'{valley:+.2f} dB'],
            ['Mean difference', f'{mean:+.2f} dB'],
        ]
    print_table(metric_headers, metric_rows)


def select_preamp_gain(peak: float) -> float:
    """交互式选择前级增益以防止削波"""
    if peak <= 0:
        localized_print('no_preamp_needed')
        return 0.0
    
    localized_print('delta_clipping_warning')
    localized_print('preamp_selection_prompt')
    localized_print('preamp_option_safe', peak=peak)
    localized_print('preamp_option_moderate', peak=peak)
    localized_print('preamp_option_custom')
    
    while True:
        try:
            choice = input().strip()
            if choice == '1':
                preamp = -(peak + 0.2)
                localized_print('preamp_applied', preamp=preamp)
                return preamp
            elif choice == '2':
                preamp = -(peak / 2.0)
                localized_print('preamp_applied', preamp=preamp)
                return preamp
            elif choice == '3':
                while True:
                    try:
                        custom_input = input(translate('preamp_custom_input_prompt')).strip()
                        preamp = float(custom_input)
                        localized_print('preamp_applied', preamp=preamp)
                        return preamp
                    except ValueError:
                        localized_print('preamp_invalid_input')
            else:
                localized_print('preamp_invalid_input')
        except KeyboardInterrupt:
            print()
            localized_print('goodbye')
            sys.exit(0)


class _SessionLogTee:
    """将 stdout 同步写入终端与 logs/ 会话文件。"""

    def __init__(self, stream, log_path: Path):
        self._stream = stream
        self._path = Path(log_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(self._path, "a", encoding="utf-8", buffering=1)
        self._fh.write(
            f"# EQ Cosplay CLI session log\n"
            f"# started: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"# file: {self._path.resolve()}\n"
            f"# ---\n"
        )

    def write(self, data: str) -> int:
        try:
            self._stream.write(data)
        except Exception:
            pass
        try:
            self._fh.write(data)
        except Exception:
            pass
        return len(data) if data else 0

    def flush(self) -> None:
        try:
            self._stream.flush()
        except Exception:
            pass
        try:
            self._fh.flush()
        except Exception:
            pass

    def close(self) -> None:
        try:
            self._fh.close()
        except Exception:
            pass


# --- 主程序入口 ---

if __name__ == "__main__":
    # 日志目录 + CLI 会话文件（终端输出仍可见，同时落盘到 logs/）
    _logs_dir = get_logs_dir()
    _session_log = make_log_path("cli_session")
    _orig_stdout = sys.stdout
    sys.stdout = _SessionLogTee(_orig_stdout, _session_log)  # type: ignore[assignment]

    localized_print('main_program_started')
    localized_print('welcome')
    print(f"[INFO] Log directory: {_logs_dir}", flush=True)
    print(f"[INFO] Session log:   {_session_log}", flush=True)

    system_name, system_arch = get_platform_info()
    localized_print('platform_detected', platform_name=system_name, architecture=system_arch)
    backend_type, default_capture_device = get_default_audio_backend(system_name)

    # 启动时：若本机有已保存 YAML，优先询问是否直接启用
    try:
        get_presets_dir()  # 确保 presets/ 存在
        saved_preset = prompt_select_saved_preset()
        if saved_preset is not None:
            debug_choice = prompt('debug_prompt').lower().strip()
            debug_mode = debug_choice == 'y'
            if debug_mode:
                localized_print('debug_enabled')
            localized_print('full_auto_deploy')
            if ensure_runtime_for_camilladsp(system_name):
                if launch_camilladsp_session(saved_preset, debug_mode=debug_mode):
                    localized_print('goodbye')
                    sys.exit(0)
            # 启动失败则继续进入新建流程
    except KeyboardInterrupt:
        localized_print('goodbye')
        sys.exit(0)
    except EOFError:
        print()
        localized_print('goodbye')
        sys.exit(0)

    # 1. 加载数据库（新建 cosplay 才需要）
    AUTOEQ_DATABASE = load_autoeq_database()
    selected_samplerate = select_samplerate()

    while True:
        try:
            source_input = prompt('step1_prompt')
            if source_input.lower() == 'q':
                localized_print('goodbye')
                sys.exit(0)

            source_entry = find_headphone(source_input, "base")
            if not source_entry:
                continue

            target_input = prompt('step2_prompt')
            if target_input.lower() == 'q':
                localized_print('goodbye')
                sys.exit(0)

            target_entry = find_headphone(target_input, "target")
            if not target_entry:
                continue

            # 2. 创建临时目录用于存储下载的 CSV
            temp_dir = Path(tempfile.mkdtemp(prefix="autoeq_calc_"))

            # 3. 下载 CSV 文件
            source_csv_path = download_headphone_csv(source_entry, temp_dir)
            target_csv_path = download_headphone_csv(target_entry, temp_dir)

            localized_print('prepare_config')
            print_table(
                ['Role', 'Name', 'CSV'],
                [
                    [
                        translate('physical_source_label'),
                        source_entry['display_name'],
                        source_csv_path.name if source_csv_path else translate('download_failed_label'),
                    ],
                    [
                        translate('target_cosplay_label'),
                        target_entry['display_name'],
                        target_csv_path.name if target_csv_path else translate('download_failed_label'),
                    ],
                ],
            )

            if source_csv_path and target_csv_path:
                # 4. 分析差值
                print_delta_summary(source_csv_path, target_csv_path)

                # 5. 计算校正：固定 10 段 IIR + 可选 FIR 残差
                correction = calculate_correction(
                    source_csv_path,
                    target_csv_path,
                    fs=selected_samplerate,
                )
                peq_parameters = correction["peq"]

                # 6. 前级增益：基于联合响应峰值（IIR±FIR），而非裸 delta
                peak = float(correction.get("response_peak", 0.0))
                pre_amp = select_preamp_gain(peak)

                # 7. 打印 IIR 结果（FIR 细节在部署时写入 WAV）
                print_peq_table(peq_parameters)
                use_fir = bool(correction.get("use_fir") and correction.get("fir_ir") is not None)

                # 8. 调试模式询问
                debug_choice = prompt('debug_prompt').lower().strip()
                debug_mode = debug_choice == 'y'
                if debug_mode:
                    localized_print('debug_enabled')

                # 9. 询问用户是否要生成 CamillaDSP 配置
                #    若已触发 FIR，使用专用部署确认文案
                if use_fir:
                    deploy_choice = prompt('deploy_prompt_with_fir').lower().strip()
                else:
                    deploy_choice = prompt('deploy_prompt').lower().strip()
                if deploy_choice == 'y':
                    localized_print('full_auto_deploy')
                    if not ensure_runtime_for_camilladsp(system_name):
                        continue

                    output_device = get_output_device_name()
                    localized_print('output_device_set', device=output_device)

                    # 生成并集中保存到 presets/（附带 RMSE 等指标注释）
                    config_path = build_config_path(source_entry, target_entry)
                    generate_camilladsp_config(
                        peq_parameters,
                        output_device,
                        config_path,
                        pre_amp,
                        samplerate=selected_samplerate,
                        backend_type=backend_type,
                        capture_device=default_capture_device,
                        fir_ir=correction.get("fir_ir") if use_fir else None,
                        metrics=metrics_from_correction(correction),
                    )
                    if not use_fir:
                        localized_print('deploy_iir_only_notice')
                    localized_print('saved_presets_saved', path=config_path)

                    if launch_camilladsp_session(config_path, debug_mode=debug_mode):
                        localized_print('goodbye')
                        sys.exit(0)
                else:
                    if use_fir:
                        localized_print('deploy_skipped_with_fir')
                    else:
                        localized_print('deploy_skipped')

            else:
                localized_print('cannot_generate_peq')

        except KeyboardInterrupt:
            localized_print('goodbye')
            sys.exit(0)
        except EOFError:
            print()
            localized_print('goodbye')
            sys.exit(0)
        except Exception as e:
            localized_print('unknown_error', error=e)
            import traceback
            traceback.print_exc()

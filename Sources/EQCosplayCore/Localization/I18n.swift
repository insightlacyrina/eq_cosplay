import Foundation

public enum Language: String, CaseIterable, Identifiable, Sendable {
    case zh = "zh"
    case en = "en"
    case ja = "ja"

    public var id: String { rawValue }
    public var label: String {
        switch self {
        case .zh: return "简体中文"
        case .en: return "English"
        case .ja: return "日本語"
        }
    }
}

public final class I18n: @unchecked Sendable {
    public static let shared = I18n()

    public var currentLanguage: Language {
        didSet {
            UserDefaults.standard.set(currentLanguage.rawValue, forKey: "EQCosplayLanguage")
        }
    }

    private init() {
        if let saved = UserDefaults.standard.string(forKey: "EQCosplayLanguage"),
           let lang = Language(rawValue: saved) {
            self.currentLanguage = lang
            return
        }

        // Auto-detect system language
        let preferred = Locale.preferredLanguages.first?.lowercased() ?? "en"
        if preferred.starts(with: "zh") {
            self.currentLanguage = .zh
        } else if preferred.starts(with: "ja") {
            self.currentLanguage = .ja
        } else {
            self.currentLanguage = .en
        }
    }

    public func t(_ key: String) -> String {
        let dict = Self.translations[currentLanguage] ?? Self.translations[.en]!
        return dict[key] ?? Self.translations[.en]?[key] ?? key
    }

    public func t(_ key: String, args: [String: Any]) -> String {
        var str = t(key)
        for (k, v) in args {
            str = str.replacingOccurrences(of: "{\(k)}", with: "\(v)")
        }
        return str
    }

    private static let translations: [Language: [String: String]] = [
        .zh: [
            "app_title": "EQ Cosplay",
            "app_subtitle": "让一副耳机扮演另一副耳机的听感",
            "source_headphone": "当前佩戴耳机 (Source)",
            "target_headphone": "想要模仿耳机 (Target)",
            "search_placeholder": "输入耳机品牌或型号 (如 WH-1000XM4, Q701)...",
            "search_hint": "支持多关键词模糊搜索，数据来自 AutoEq 官方库",
            "provider_label": "测量数据源: {provider}",
            "calculate_button": "拟合校正曲线",
            "deploy_button": "应用并启动 CamillaDSP",
            "stop_button": "停止引擎",
            "save_preset_button": "保存预设",
            "calculating": "正在下载频响并拟合 10 段 PEQ 与 FIR 残差...",
            "status_idle": "就绪 / 引擎未启动",
            "status_running": "CamillaDSP 正在运行: {preset}",
            "status_calculating": "计算中...",
            "plot_source": "当前耳机 (Source)",
            "plot_target": "目标耳机 (Target)",
            "plot_simulated": "模拟后 (Simulated)",
            "plot_delta": "差值曲线 (Delta)",
            "plot_empty_hint": "选择耳机后点击「拟合校正曲线」生成频响",
            "peq_table_title": "10 段参数均衡 (IIR PEQ)",
            "peq_empty_hint": "尚未生成均衡器参数",
            "col_index": "序号",
            "col_type": "类型",
            "col_freq": "中心频率 (Hz)",
            "col_gain": "增益 (dB)",
            "col_q": "Q值 (Q)",
            "metrics_title": "校正指标",
            "rmse_peq": "10段 IIR 均方根误差 (RMSE): {val} dB",
            "rmse_combined": "叠加 FIR 联合误差: {val} dB",
            "peak_gain": "最大联合响应峰值: {val} dB",
            "fir_status": "FIR 状态",
            "fir_active": "启用最小相位 FIR 残差卷积 ({taps} Taps)",
            "fir_inactive": "未启用 (IIR 已满足容差)",
            "fir_stop": "停止 FIR",
            "fir_enable": "开启 FIR",
            "preamp_label": "前级增益防削波",
            "preamp_safe": "安全模式 (-(峰值+0.2) dB)",
            "preamp_moderate": "折中模式 (-峰值/2 dB)",
            "preamp_custom": "自定义",
            "preamp_none": "不调整 (0 dB)",
            "sample_rate": "采样率",
            "output_device": "物理输出声卡",
            "presets_library": "本地方案库",
            "no_presets": "暂无已保存预设",
            "load_preset": "载入方案",
            "delete_preset": "删除",
            "log_console": "运行日志",
            "clear_log": "清空日志",
            "menubar_show": "显示主窗口",
            "menubar_hide": "隐藏主窗口",
            "menubar_refresh": "刷新预设",
            "menubar_stop": "停止 CamillaDSP",
            "menubar_quit": "退出 EQ Cosplay",
            "blackhole_warning": "未检测到 BlackHole 2ch 虚拟音频驱动，CamillaDSP 系统捕获需要虚拟声卡支持。",
            "install_blackhole": "一键安装驱动",
            "installing_blackhole": "正在安装驱动...",
            "camilla_not_found": "未找到 CamillaDSP 可执行程序，请将其放置在应用目录或 PATH 中。"
        ],
        .en: [
            "app_title": "EQ Cosplay",
            "app_subtitle": "Make one headphone sound like another",
            "source_headphone": "Physical Headphone (Source)",
            "target_headphone": "Desired Sound (Target)",
            "search_placeholder": "Type model name (e.g. WH-1000XM4, Q701)...",
            "search_hint": "Fuzzy search with multiple keywords, powered by AutoEq",
            "provider_label": "Measurement: {provider}",
            "calculate_button": "Fit Correction Curves",
            "deploy_button": "Deploy to CamillaDSP",
            "stop_button": "Stop Engine",
            "save_preset_button": "Save Preset",
            "calculating": "Downloading FR & fitting 10-band PEQ + FIR...",
            "status_idle": "Idle / Engine stopped",
            "status_running": "CamillaDSP running: {preset}",
            "status_calculating": "Calculating...",
            "plot_source": "Source Curve",
            "plot_target": "Target Curve",
            "plot_simulated": "Simulated Result",
            "plot_delta": "Delta Curve",
            "plot_empty_hint": "Select headphones and click 'Fit Correction Curves' to generate frequency response",
            "peq_table_title": "10-Band Parametric EQ (IIR)",
            "peq_empty_hint": "No equalizer parameters generated yet",
            "col_index": "#",
            "col_type": "Type",
            "col_freq": "Freq (Hz)",
            "col_gain": "Gain (dB)",
            "col_q": "Q (Q)",
            "metrics_title": "Correction Metrics",
            "rmse_peq": "10-band IIR RMSE: {val} dB",
            "rmse_combined": "Combined + FIR RMSE: {val} dB",
            "peak_gain": "Response Peak: {val} dB",
            "fir_status": "FIR Residual",
            "fir_active": "Minimum-phase FIR Conv Active ({taps} Taps)",
            "fir_inactive": "Inactive (IIR meets tolerance)",
            "fir_stop": "Stop FIR",
            "fir_enable": "Enable FIR",
            "preamp_label": "Preamp Gain (Anti-clipping)",
            "preamp_safe": "Safe (-(peak+0.2) dB)",
            "preamp_moderate": "Moderate (-peak/2 dB)",
            "preamp_custom": "Custom",
            "preamp_none": "None (0 dB)",
            "sample_rate": "Sample Rate",
            "output_device": "Audio Output Device",
            "presets_library": "Presets Library",
            "no_presets": "No saved presets found",
            "load_preset": "Load Preset",
            "delete_preset": "Delete",
            "log_console": "Live Logs",
            "clear_log": "Clear",
            "menubar_show": "Show Window",
            "menubar_hide": "Hide Window",
            "menubar_refresh": "Refresh Presets",
            "menubar_stop": "Stop CamillaDSP",
            "menubar_quit": "Quit EQ Cosplay",
            "blackhole_warning": "BlackHole 2ch was not found. System-wide routing requires a virtual audio device.",
            "install_blackhole": "Install Driver",
            "installing_blackhole": "Installing...",
            "camilla_not_found": "CamillaDSP binary not found. Place it in the app directory or install via PATH."
        ],
        .ja: [
            "app_title": "EQ Cosplay",
            "app_subtitle": "ヘッドホンの音色を別のモデルへとコスプレさせる",
            "source_headphone": "使用中ヘッドホン (Source)",
            "target_headphone": "目標ヘッドホン (Target)",
            "search_placeholder": "型番を入力 (例: WH-1000XM4, Q701)...",
            "search_hint": "AutoEq データベースによる高精度あいまい検索",
            "provider_label": "測定データ源: {provider}",
            "calculate_button": "補正曲線を計算",
            "deploy_button": "CamillaDSP を起動・適用",
            "stop_button": "エンジン停止",
            "save_preset_button": "プリセット保存",
            "calculating": "周波数応答を取得して10バンドPEQとFIR残差を最適化中...",
            "status_idle": "待機中 / 停止",
            "status_running": "CamillaDSP 実行中: {preset}",
            "status_calculating": "計算中...",
            "plot_source": "使用中カーブ",
            "plot_target": "目標カーブ",
            "plot_simulated": "補正後シミュレーション",
            "plot_delta": "差分カーブ",
            "plot_empty_hint": "ヘッドホンを選択し「補正曲線を計算」をクリックして周波数応答を生成",
            "peq_table_title": "10バンド パラメトリックEQ (IIR)",
            "peq_empty_hint": "イコライザーパラメータはまだ生成されていません",
            "col_index": "No",
            "col_type": "タイプ",
            "col_freq": "中心周波数 (Hz)",
            "col_gain": "ゲイン (dB)",
            "col_q": "Q値 (Q)",
            "metrics_title": "補正指標",
            "rmse_peq": "10バンド IIR RMSE: {val} dB",
            "rmse_combined": "FIR合成後 RMSE: {val} dB",
            "peak_gain": "最大応答ピーク: {val} dB",
            "fir_status": "FIR 残差",
            "fir_active": "最小位相 FIR 畳み込み有効 ({taps} Taps)",
            "fir_inactive": "未適用 (IIR のみで許容範囲内)",
            "fir_stop": "FIR 停止",
            "fir_enable": "FIR 有効化",
            "preamp_label": "プリアンプゲイン (クリッピング防止)",
            "preamp_safe": "安全 (-(ピーク+0.2) dB)",
            "preamp_moderate": "中庸 (-ピーク/2 dB)",
            "preamp_custom": "カスタム",
            "preamp_none": "なし (0 dB)",
            "sample_rate": "サンプリング周波数",
            "output_device": "オーディオ出力デバイス",
            "presets_library": "保存済みプリセット",
            "no_presets": "保存されたプリセットはありません",
            "load_preset": "読み込み",
            "delete_preset": "削除",
            "log_console": "動作ログ",
            "clear_log": "クリア",
            "menubar_show": "メインウィンドウを表示",
            "menubar_hide": "メインウィンドウを隠す",
            "menubar_refresh": "プリセットを再読み込み",
            "menubar_stop": "CamillaDSP を停止",
            "menubar_quit": "EQ Cosplay を終了",
            "blackhole_warning": "BlackHole 2ch が検出されませんでした。システム全体のEQには仮想オーディオデバイスが必要です。",
            "install_blackhole": "ドライバを導入",
            "installing_blackhole": "導入処理中...",
            "camilla_not_found": "CamillaDSP の実行ファイルが見つかりません。"
        ]
    ]
}

#!/bin/bash
# EQ Cosplay launcher — bootstrap venv, preflight macOS friction, then GUI/CLI.
set -u

# 获取当前脚本所在的绝对路径，并进入该目录
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT" || {
  echo "[ERR] Cannot cd to project directory: $ROOT"
  echo "Press Enter to close."
  read -r _
  exit 1
}

# 简易多语言启动提示（与 cosplay.py 的 en/zh/ja 对齐，无 emoji）
LANG_CODE="$(printf '%s' "${LC_ALL:-${LC_MESSAGES:-${LANG:-en}}}" | cut -c1-2 | tr '[:upper:]' '[:lower:]')"
case "$LANG_CODE" in
  zh)
    MSG_BOOT="[EQ Cosplay] 正在启动..."
    MSG_PREFLIGHT="[EQ Cosplay] 新机/首次运行预检..."
    MSG_CHMOD="[OK] 已恢复启动脚本可执行权限 (+x)。"
    MSG_QUAR_CLEAR="[OK] 已清除 macOS 隔离标记 (quarantine)，避免 Gatekeeper 误拦。"
    MSG_QUAR_HINT="[WARN] 仍检测到隔离相关属性。若提示「无法验证开发者」：
     系统设置 → 隐私与安全性 → 仍要打开
     或终端执行: xattr -dr com.apple.quarantine \"$ROOT\""
    MSG_PATH_WARN="[WARN] 项目位于桌面/文稿/下载目录。
     首次运行时 macOS 可能询问「终端是否允许访问该文件夹」——请点「允许」。
     更省事：把整个文件夹移到例如 ~/Developer/eq_cosplay 后再打开。"
    MSG_PY_MISS="[ERR] 未找到 python3。
     macOS: 安装 Xcode 命令行工具: xcode-select --install
     或安装 Homebrew Python: https://brew.sh"
    MSG_VENV="[EQ Cosplay] 首次运行：正在创建隔离虚拟环境..."
    MSG_VENV_OK="[OK] 虚拟环境就绪。"
    MSG_VENV_FAIL="[ERR] 创建虚拟环境失败。请确认已安装 python3 与 pip。"
    MSG_DEPS="[..] 正在检查核心依赖..."
    MSG_DEPS_FAIL="[ERR] 安装 Python 依赖失败（numpy/scipy）。请检查网络后重试。"
    MSG_START="[OK] 启动图形界面"
    MSG_START_CLI="[OK] 启动终端界面"
    MSG_END="[EQ Cosplay] 进程已结束。"
    MSG_PIP_NOTICE="[notice] 检测到 pip 有新版本可用: %s -> %s"
    MSG_PIP_PROMPT="是否现在更新 pip？(y/n，默认 n): "
    MSG_PIP_UPDATING="[..] 正在更新 pip..."
    MSG_PIP_OK="[OK] pip 已更新到最新版本。"
    MSG_PIP_FAIL="[WARN] pip 更新失败，将继续使用当前版本。"
    MSG_PIP_SKIP="[INFO] 已跳过 pip 更新。"
    MSG_PIP_CURRENT="[INFO] pip 已是最新版本 (%s)。"
    MSG_TK="[ERR] 无法导入 Tkinter。macOS 请执行: brew install python-tk
     然后将回退到终端界面。"
    MSG_CAMILLA_NOTE="[INFO] 首次部署 CamillaDSP 时，未签名二进制可能被拦截：
     系统设置 → 隐私与安全性 → 仍要打开
     或: xattr -dr com.apple.quarantine ./camilladsp"
    MSG_PRESS_ENTER="按 Enter 关闭此窗口..."
    ;;
  ja)
    MSG_BOOT="[EQ Cosplay] 起動しています..."
    MSG_PREFLIGHT="[EQ Cosplay] 初回/新規 Mac 向け事前チェック..."
    MSG_CHMOD="[OK] 起動スクリプトに実行権限 (+x) を付与しました。"
    MSG_QUAR_CLEAR="[OK] macOS の隔離属性 (quarantine) を削除しました。"
    MSG_QUAR_HINT="[WARN] 隔離属性が残っている可能性があります。
     システム設定 → プライバシーとセキュリティ → このまま開く
     または: xattr -dr com.apple.quarantine \"$ROOT\""
    MSG_PATH_WARN="[WARN] プロジェクトがデスクトップ/書類/ダウンロードにあります。
     初回は「ターミナルがフォルダにアクセス」と聞かれることがあります → 許可してください。
     推奨: ~/Developer/eq_cosplay などへ移動。"
    MSG_PY_MISS="[ERR] python3 が見つかりません。xcode-select --install または Homebrew を確認してください。"
    MSG_VENV="[EQ Cosplay] 初回実行: 仮想環境を作成しています..."
    MSG_VENV_OK="[OK] 仮想環境の準備ができました。"
    MSG_VENV_FAIL="[ERR] 仮想環境の作成に失敗しました。"
    MSG_DEPS="[..] コア依存関係を確認しています..."
    MSG_DEPS_FAIL="[ERR] 依存関係のインストールに失敗しました。"
    MSG_START="[OK] GUI を起動します"
    MSG_START_CLI="[OK] ターミナル UI を起動します"
    MSG_END="[EQ Cosplay] プロセスが終了しました。"
    MSG_PIP_NOTICE="[notice] 新しい pip が利用可能です: %s -> %s"
    MSG_PIP_PROMPT="今すぐ pip を更新しますか？(y/n、デフォルト n): "
    MSG_PIP_UPDATING="[..] pip を更新しています..."
    MSG_PIP_OK="[OK] pip を最新版に更新しました。"
    MSG_PIP_FAIL="[WARN] pip の更新に失敗しました。現在のバージョンで続行します。"
    MSG_PIP_SKIP="[INFO] pip の更新をスキップしました。"
    MSG_PIP_CURRENT="[INFO] pip は最新です (%s)。"
    MSG_TK="[ERR] Tkinter を import できません。brew install python-tk を試してください。"
    MSG_CAMILLA_NOTE="[INFO] CamillaDSP 初回実行時は未署名バイナリがブロックされることがあります。
     システム設定 → プライバシーとセキュリティ → このまま開く"
    MSG_PRESS_ENTER="終了するには Enter を押してください..."
    ;;
  *)
    MSG_BOOT="[EQ Cosplay] Starting..."
    MSG_PREFLIGHT="[EQ Cosplay] First-run / new-Mac preflight..."
    MSG_CHMOD="[OK] Restored executable bits (+x) on launch scripts."
    MSG_QUAR_CLEAR="[OK] Cleared macOS quarantine attributes (reduces Gatekeeper blocks)."
    MSG_QUAR_HINT="[WARN] Quarantine-related attributes may still be present.
     System Settings → Privacy & Security → Open Anyway
     Or run: xattr -dr com.apple.quarantine \"$ROOT\""
    MSG_PATH_WARN="[WARN] Project is under Desktop/Documents/Downloads.
     macOS may ask Terminal for folder access — click Allow.
     Easier: move the folder to e.g. ~/Developer/eq_cosplay."
    MSG_PY_MISS="[ERR] python3 not found. Install Xcode CLT (xcode-select --install) or Homebrew Python."
    MSG_VENV="[EQ Cosplay] First run: creating virtual environment..."
    MSG_VENV_OK="[OK] Virtual environment ready."
    MSG_VENV_FAIL="[ERR] Failed to create virtual environment."
    MSG_DEPS="[..] Checking core dependencies..."
    MSG_DEPS_FAIL="[ERR] Failed to install Python deps (numpy/scipy). Check network and retry."
    MSG_START="[OK] Launching GUI"
    MSG_START_CLI="[OK] Launching terminal UI"
    MSG_END="[EQ Cosplay] Process finished."
    MSG_PIP_NOTICE="[notice] A new release of pip is available: %s -> %s"
    MSG_PIP_PROMPT="Update pip now? (y/n, default n): "
    MSG_PIP_UPDATING="[..] Updating pip..."
    MSG_PIP_OK="[OK] pip has been updated."
    MSG_PIP_FAIL="[WARN] pip update failed; continuing with the current version."
    MSG_PIP_SKIP="[INFO] Skipped pip update."
    MSG_PIP_CURRENT="[INFO] pip is up to date (%s)."
    MSG_TK="[ERR] Tkinter is not available. Try: brew install python-tk
     Falling back to terminal UI."
    MSG_CAMILLA_NOTE="[INFO] First CamillaDSP run may be blocked (unsigned binary):
     System Settings → Privacy & Security → Open Anyway
     Or: xattr -dr com.apple.quarantine ./camilladsp"
    MSG_PRESS_ENTER="Press Enter to close this window..."
    ;;
esac

# 失败时窗口不立刻消失（双击 .command 时尤其重要）
pause_and_exit() {
  local code="${1:-1}"
  echo ""
  echo "$MSG_PRESS_ENTER"
  # 无 TTY 时 read 可能失败，忽略
  read -r _ 2>/dev/null || true
  exit "$code"
}

# 参数：--cli 强制终端版；默认 GUI；--skip-preflight 跳过预检（调试用）
USE_CLI=0
SKIP_PREFLIGHT=0
for arg in "$@"; do
  case "$arg" in
    --cli|-c) USE_CLI=1 ;;
    --skip-preflight) SKIP_PREFLIGHT=1 ;;
  esac
done

echo "$MSG_BOOT"

# ---------------------------------------------------------------------------
# 预检：减少新 Mac 摩擦（可执行位 / quarantine / 受保护路径 / python3）
# ---------------------------------------------------------------------------
if [ "$SKIP_PREFLIGHT" != "1" ]; then
  echo "$MSG_PREFLIGHT"

  # 1) 可执行位（ZIP 下载常丢失）
  NEED_CHMOD=0
  for f in start.command start_cli.command cosplay_gui.py cosplay.py; do
    if [ -f "$f" ] && [ ! -x "$f" ]; then
      NEED_CHMOD=1
      break
    fi
  done
  chmod +x start.command start_cli.command cosplay_gui.py cosplay.py 2>/dev/null || true
  if [ -f camilladsp ]; then
    chmod +x camilladsp 2>/dev/null || true
  fi
  if [ -f camilladsp.exe ]; then
    chmod +x camilladsp.exe 2>/dev/null || true
  fi
  if [ "$NEED_CHMOD" = "1" ]; then
    echo "$MSG_CHMOD"
  fi

  # 2) macOS：清除 quarantine（用户目录下通常无需 sudo）
  if [ "$(uname -s)" = "Darwin" ]; then
    HAD_QUAR=0
    if command -v xattr >/dev/null 2>&1; then
      if xattr -r -p com.apple.quarantine "$ROOT" >/dev/null 2>&1; then
        HAD_QUAR=1
      fi
      # 也扫常见文件（xattr -r 对大目录可能慢，项目很小可接受）
      xattr -dr com.apple.quarantine "$ROOT" 2>/dev/null || true
      if [ "$HAD_QUAR" = "1" ]; then
        echo "$MSG_QUAR_CLEAR"
      fi
      # 仍有 quarantine 则提示（权限不足等）
      if xattr -r -p com.apple.quarantine "$ROOT" >/dev/null 2>&1; then
        echo "$MSG_QUAR_HINT"
      fi
    fi

    # 3) 受保护目录提示
    case "$ROOT" in
      "$HOME/Desktop"*|"$HOME/Documents"*|"$HOME/Downloads"*|*/Desktop/*|*/Documents/*|*/Downloads/*)
        echo "$MSG_PATH_WARN"
        ;;
    esac

    # 4) CamillaDSP 首次拦截说明（仅提示一次感：文件存在时）
    if [ -f camilladsp ] || [ -f camilladsp.exe ]; then
      echo "$MSG_CAMILLA_NOTE"
    fi
  fi

  # 5) python3 必须可用
  if ! command -v python3 >/dev/null 2>&1; then
    echo "$MSG_PY_MISS"
    pause_and_exit 1
  fi
fi

# ---------------------------------------------------------------------------
# venv + deps
# ---------------------------------------------------------------------------
if [ ! -d ".venv" ]; then
  echo "$MSG_VENV"
  if ! python3 -m venv .venv; then
    echo "$MSG_VENV_FAIL"
    pause_and_exit 1
  fi
  echo "$MSG_VENV_OK"
fi

# shellcheck source=/dev/null
if ! source .venv/bin/activate; then
  echo "$MSG_VENV_FAIL"
  pause_and_exit 1
fi

# --- pip 版本检查 ---
PIP_VERSIONS="$(python3 - <<'PY'
import json
import urllib.request

try:
    import pip
    current = getattr(pip, "__version__", None) or ""
except Exception:
    current = ""

latest = ""
try:
    req = urllib.request.Request(
        "https://pypi.org/pypi/pip/json",
        headers={"User-Agent": "eq-cosplay-start/1.0"},
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        data = json.loads(resp.read().decode("utf-8", errors="replace"))
    latest = (data.get("info") or {}).get("version") or ""
except Exception:
    latest = ""

print(current)
print(latest)
PY
)"

PIP_CURRENT="$(printf '%s\n' "$PIP_VERSIONS" | sed -n '1p')"
PIP_LATEST="$(printf '%s\n' "$PIP_VERSIONS" | sed -n '2p')"

if [ -n "$PIP_CURRENT" ] && [ -n "$PIP_LATEST" ] && [ "$PIP_CURRENT" != "$PIP_LATEST" ]; then
  # shellcheck disable=SC2059
  printf "${MSG_PIP_NOTICE}\n" "$PIP_CURRENT" "$PIP_LATEST"
  if [ -t 0 ] && [ "$USE_CLI" = "1" ]; then
    printf "%s" "$MSG_PIP_PROMPT"
    read -r PIP_ANS || PIP_ANS=""
    case "$(printf '%s' "$PIP_ANS" | tr '[:upper:]' '[:lower:]')" in
      y|yes)
        echo "$MSG_PIP_UPDATING"
        if python3 -m pip install --upgrade pip --disable-pip-version-check -q; then
          echo "$MSG_PIP_OK"
        else
          echo "$MSG_PIP_FAIL"
        fi
        ;;
      *)
        echo "$MSG_PIP_SKIP"
        ;;
    esac
  else
    echo "$MSG_PIP_SKIP"
  fi
elif [ -n "$PIP_CURRENT" ]; then
  # shellcheck disable=SC2059
  printf "${MSG_PIP_CURRENT}\n" "$PIP_CURRENT"
fi

echo "$MSG_DEPS"
if ! python3 -m pip install -q --disable-pip-version-check -r requirements.txt 2>/dev/null; then
  if ! python3 -m pip install -q --disable-pip-version-check numpy scipy; then
    echo "$MSG_DEPS_FAIL"
    pause_and_exit 1
  fi
fi

# ---------------------------------------------------------------------------
# Launch
# ---------------------------------------------------------------------------
EXIT_CODE=0
if [ "$USE_CLI" = "1" ]; then
  if ! command -v gum >/dev/null 2>&1; then
    if command -v brew >/dev/null 2>&1; then
      brew install gum >/dev/null 2>&1 || true
    fi
  fi
  echo "$MSG_START_CLI"
  python3 cosplay.py || EXIT_CODE=$?
else
  if ! python3 -c "import tkinter" 2>/dev/null; then
    if command -v brew >/dev/null 2>&1; then
      PY_MAJOR_MINOR="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || true)"
      if [ -n "$PY_MAJOR_MINOR" ]; then
        brew install "python-tk@${PY_MAJOR_MINOR}" >/dev/null 2>&1 || true
      fi
      brew install python-tk >/dev/null 2>&1 || true
    fi
  fi
  if ! python3 -c "import tkinter" 2>/dev/null; then
    echo "$MSG_TK"
    echo "$MSG_START_CLI"
    python3 cosplay.py || EXIT_CODE=$?
  else
    echo "$MSG_START"
    python3 cosplay_gui.py || EXIT_CODE=$?
  fi
fi

echo "$MSG_END"
if [ "$EXIT_CODE" != "0" ]; then
  pause_and_exit "$EXIT_CODE"
fi
exit 0

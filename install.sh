#!/usr/bin/env bash
# install.sh — 安装 knowwind-wx 采集工具（含 wechat-decrypt）
# 用法：curl -fsSL https://raw.githubusercontent.com/vincent4j/knowwind-wx/main/install.sh | sh

set -e

# ── 常量 ──────────────────────────────────────────────────────────────────────
REPO_URL="https://github.com/vincent4j/knowwind-wx"
INSTALL_DIR="$HOME/.knowwind/wx"
DECRYPT_DIR="$INSTALL_DIR/vendor/wechat-decrypt"
VENV_DIR="$INSTALL_DIR/.venv"
VENV_PY="$VENV_DIR/bin/python3"
VENV_PIP="$VENV_DIR/bin/pip"
BIN_PATH="/usr/local/bin/knowwind-wx"
DECRYPT_BIN="/usr/local/bin/knowwind-wx-decrypt"

OS="$(uname -s)"
# ── 输出工具 ──────────────────────────────────────────────────────────────────
ok()   { echo "  ✅ $1"; }
info() { echo "  →  $1"; }
warn() { echo "  ⚠️  $1"; }
fail() { echo "  ❌ $1"; }
hr()   { echo "─────────────────────────────────────────"; }

echo ""
hr
echo "  knowwind-wx 安装程序"
hr
echo ""

# ══════════════════════════════════════════════════════════════════════════════
# Phase 1: 预检查（发现问题立即报告，全部检查完再退出）
# ══════════════════════════════════════════════════════════════════════════════
echo "▶ 预检查环境..."
echo ""
PREFLIGHT_ERRORS=0

# Python 3.10+
if ! command -v python3 &>/dev/null; then
  fail "未找到 python3 — 请先安装 Python 3.10+"
  PREFLIGHT_ERRORS=$((PREFLIGHT_ERRORS + 1))
else
  PY_OK=$(python3 -c "import sys; print(sys.version_info >= (3,10))")
  if [ "$PY_OK" = "True" ]; then
    ok "Python $(python3 --version | cut -d' ' -f2)"
  else
    fail "Python 版本过低（需要 3.10+），当前: $(python3 --version)"
    PREFLIGHT_ERRORS=$((PREFLIGHT_ERRORS + 1))
  fi
fi

# git
if ! command -v git &>/dev/null; then
  fail "未找到 git — 请安装 Xcode Command Line Tools: xcode-select --install"
  PREFLIGHT_ERRORS=$((PREFLIGHT_ERRORS + 1))
else
  ok "git $(git --version | awk '{print $3}')"
fi

# WeChat.app（仅 macOS）
if [ "$OS" = "Darwin" ]; then
  if [ -d "/Applications/WeChat.app" ]; then
    ok "微信客户端 已安装"
  else
    fail "未找到 /Applications/WeChat.app — 请先从 App Store 安装微信"
    PREFLIGHT_ERRORS=$((PREFLIGHT_ERRORS + 1))
  fi
fi

if [ "$PREFLIGHT_ERRORS" -gt 0 ]; then
  echo ""
  fail "发现 ${PREFLIGHT_ERRORS} 个问题，请解决后重新运行安装程序。"
  exit 1
fi

# ── 检查已有安装状态（只报告，不退出）────────────────────────────────────────
echo ""
echo "▶ 检查已有安装..."
echo ""

# knowwind-wx
if [ -d "$INSTALL_DIR/.git" ]; then
  _COMMIT=$(git -C "$INSTALL_DIR" log -1 --format="%h" 2>/dev/null || echo "?")
  warn "knowwind-wx 已安装（${_COMMIT}）→ 将升级到最新版"
else
  info "knowwind-wx 未安装 → 将全新安装"
fi

# wechat-decrypt
if [ -d "$DECRYPT_DIR/.git" ]; then
  _COMMIT=$(git -C "$DECRYPT_DIR" log -1 --format="%h" 2>/dev/null || echo "?")
  warn "wechat-decrypt 已安装（${_COMMIT}）→ 将升级到最新版"
else
  info "wechat-decrypt 未安装 → 将全新安装"
fi

# wechat-decrypt 运行状态
if curl -sf --max-time 2 "http://localhost:5678/api/info" >/dev/null 2>&1; then
  DECRYPT_WAS_RUNNING=1
  warn "wechat-decrypt 服务正在运行（:5678）→ 安装完成后将重启"
else
  DECRYPT_WAS_RUNNING=0
  info "wechat-decrypt 服务未运行"
fi

echo ""

# ══════════════════════════════════════════════════════════════════════════════
# Phase 2: 安装 knowwind-wx
# ══════════════════════════════════════════════════════════════════════════════
echo "▶ 安装 knowwind-wx..."
echo ""
mkdir -p "$(dirname "$INSTALL_DIR")"

if [ -d "$INSTALL_DIR/.git" ]; then
  info "更新仓库..."
  git -C "$INSTALL_DIR" pull --quiet
  git -C "$INSTALL_DIR" submodule update --init --quiet
else
  info "克隆仓库到 $INSTALL_DIR..."
  git clone --quiet --recursive "$REPO_URL" "$INSTALL_DIR"
fi

if [ ! -f "$VENV_PY" ]; then
  info "创建Python 虚拟环境..."
  python3 -m venv "$VENV_DIR"
fi
info "安装 Python 依赖..."
"$VENV_PIP" install --quiet --upgrade pip
"$VENV_PIP" install --quiet httpx python-dotenv
if [ -f "$DECRYPT_DIR/requirements.txt" ]; then
  "$VENV_PIP" install --quiet -r "$DECRYPT_DIR/requirements.txt"
fi
ok "knowwind-wx 就绪"
echo ""

# ══════════════════════════════════════════════════════════════════════════════
# Phase 4: macOS 专项配置
# ══════════════════════════════════════════════════════════════════════════════
SKIP_KEY_EXTRACT=0

if [ "$OS" = "Darwin" ]; then
  echo "▶ macOS 配置..."
  echo ""

  # ad-hoc 重签名（允许内存读取，每次微信大版本更新后需重做）
  echo "  需要对微信做 ad-hoc 重签名，以允许本地工具读取解密密钥。"
  echo "  此操作仅影响本机应用签名，不修改微信程序本身。"
  echo ""
  info "运行 codesign（需要 sudo）..."
  sudo codesign --force --deep --sign - /Applications/WeChat.app
  ok "重签名完成（微信大版本升级后需重新运行安装程序）"
  echo ""

  # 提取微信密钥（需要微信正在运行）
  echo "▶ 提取微信密钥..."
  echo ""

  if ! pgrep -x WeChat >/dev/null 2>&1; then
    # 检测是否交互模式（curl | sh 时 stdin 不是 tty）
    if [ -t 0 ]; then
      echo "  微信当前未运行，请先打开微信客户端。"
      echo ""
      printf "  打开微信后按回车继续..."
      read -r _
      echo ""
    else
      warn "非交互模式：微信未运行，跳过密钥提取。"
      warn "安装完成后请手动运行: knowwind-wx-decrypt"
      SKIP_KEY_EXTRACT=1
    fi
  fi

  if [ "$SKIP_KEY_EXTRACT" = "0" ]; then
    if [ ! -f "$DECRYPT_DIR/find_all_keys_macos" ]; then
      warn "未找到 find_all_keys_macos，跳过密钥提取。请手动运行: knowwind-wx-decrypt"
      SKIP_KEY_EXTRACT=1
    else
      chmod +x "$DECRYPT_DIR/find_all_keys_macos"
      info "提取密钥（需要 sudo）..."
      if (cd "$DECRYPT_DIR" && sudo ./find_all_keys_macos); then
        ok "密钥提取完成"
      else
        warn "密钥提取失败，稍后可运行 knowwind-wx-decrypt 重试"
        SKIP_KEY_EXTRACT=1
      fi
    fi
    echo ""
  fi
fi

# ══════════════════════════════════════════════════════════════════════════════
# Phase 5: 创建命令行工具
# ══════════════════════════════════════════════════════════════════════════════
echo "▶ 创建命令行工具..."
echo ""

_install_bin() {
  local src="$1" dst="$2"
  if [ -w "/usr/local/bin" ]; then
    cp "$src" "$dst" && chmod +x "$dst"
  else
    sudo cp "$src" "$dst" && sudo chmod +x "$dst"
  fi
}

# knowwind-wx 主命令
cat > /tmp/_kw_entry <<EOF
#!/usr/bin/env bash
exec "${VENV_PY}" "${INSTALL_DIR}/knowwind-wx" "\$@"
EOF
_install_bin /tmp/_kw_entry "$BIN_PATH"
rm /tmp/_kw_entry
ok "命令已创建: knowwind-wx"

# knowwind-wx-decrypt 启动助手（每次开机 / 微信更新后运行）
cat > /tmp/_kw_decrypt <<EOF
#!/usr/bin/env bash
# knowwind-wx-decrypt — 启动 wechat-decrypt 本地服务
# 使用场景：重启电脑后、微信更新后需要重新运行一次
DECRYPT_DIR="${DECRYPT_DIR}"

echo ""
echo "=== 启动 wechat-decrypt 服务 ==="
echo ""

# 检查微信是否在运行
if ! pgrep -x WeChat >/dev/null 2>&1; then
  echo "❌ 请先打开微信，然后重新运行此命令"
  exit 1
fi

# 停止旧进程
OLD_PID=\$(lsof -ti:5678 2>/dev/null || true)
if [ -n "\$OLD_PID" ]; then
  echo "→ 停止旧服务 (PID: \$OLD_PID)..."
  kill "\$OLD_PID" 2>/dev/null || true
  sleep 1
fi

# 提取密钥
echo "→ 提取微信密钥（需要 sudo）..."
chmod +x "\$DECRYPT_DIR/find_all_keys_macos"
(cd "\$DECRYPT_DIR" && sudo ./find_all_keys_macos) || { echo "❌ 密钥提取失败"; exit 1; }

# 启动服务
echo "→ 启动服务..."
(cd "\$DECRYPT_DIR" && "${VENV_PY}" main.py >/dev/null 2>&1 &)
sleep 2

if curl -sf --max-time 3 http://localhost:5678/api/info >/dev/null 2>&1; then
  echo "✅ wechat-decrypt 服务已启动（127.0.0.1:5678）"
else
  echo "⚠️  服务可能仍在启动中，请稍候运行: knowwind-wx status"
fi
echo ""
EOF
_install_bin /tmp/_kw_decrypt "$DECRYPT_BIN"
rm /tmp/_kw_decrypt
ok "命令已创建: knowwind-wx-decrypt"
echo ""

# ══════════════════════════════════════════════════════════════════════════════
# Phase 6: 启动 wechat-decrypt 服务
# ══════════════════════════════════════════════════════════════════════════════
if [ "$OS" = "Darwin" ] && [ "$SKIP_KEY_EXTRACT" = "0" ]; then
  echo "▶ 启动 wechat-decrypt 服务..."
  echo ""

  # 停止旧进程
  OLD_PID=$(lsof -ti:5678 2>/dev/null || true)
  if [ -n "$OLD_PID" ]; then
    info "停止旧服务..."
    kill "$OLD_PID" 2>/dev/null || true
    sleep 1
  fi

  info "启动服务..."
  (cd "$DECRYPT_DIR" && "$VENV_PY" main.py >/dev/null 2>&1 &)
  sleep 2

  if curl -sf --max-time 3 "http://localhost:5678/api/info" >/dev/null 2>&1; then
    ok "wechat-decrypt 服务已启动（127.0.0.1:5678）"
  else
    warn "服务未响应，稍后可运行 knowwind-wx-decrypt 重试"
  fi
  echo ""
fi

# ══════════════════════════════════════════════════════════════════════════════
# 完成
# ══════════════════════════════════════════════════════════════════════════════
hr
echo "  ✅ 安装完成！"
hr
echo ""
echo "下一步："
echo ""
echo "  1. 在 KnowWind 「平台管理 → 微信」页面获取绑定码"
echo "  2. 运行绑定命令："
echo ""
echo "       knowwind-wx bind --code <绑定码> --server <服务器地址>"
echo ""
echo "  3. 启动采集服务："
echo ""
echo "       knowwind-wx run"
echo ""
if [ "$OS" = "Darwin" ]; then
  echo "  ⚠️  重启电脑或微信更新后，需要重新运行："
  echo ""
  echo "       knowwind-wx-decrypt"
  echo ""
fi

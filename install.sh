#!/usr/bin/env bash
set -euo pipefail

# agent-migrate installer
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/CodeMath/oh-my-migrate/main/install.sh | bash
#   curl -fsSL https://raw.githubusercontent.com/CodeMath/oh-my-migrate/main/install.sh | bash -s -- --codex

REPO="CodeMath/oh-my-migrate"
BRANCH="main"
RAW="https://raw.githubusercontent.com/${REPO}/${BRANCH}"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info()  { echo -e "${BLUE}[info]${NC} $*"; }
ok()    { echo -e "${GREEN}[ok]${NC} $*"; }
warn()  { echo -e "${YELLOW}[warn]${NC} $*"; }

INSTALL_CODEX=false
for arg in "$@"; do
  case "$arg" in
    --codex) INSTALL_CODEX=true ;;
  esac
done

# ── Step 1: Install agent-migrate CLI ──
info "Installing agent-migrate CLI..."
if command -v uv &>/dev/null; then
  uv pip install "git+https://github.com/${REPO}.git" 2>/dev/null || \
  uv pip install "git+https://github.com/${REPO}.git" --system 2>/dev/null
  ok "Installed via uv"
elif command -v pip &>/dev/null; then
  pip install "git+https://github.com/${REPO}.git" 2>/dev/null || \
  pip install --user "git+https://github.com/${REPO}.git" 2>/dev/null
  ok "Installed via pip"
elif command -v pip3 &>/dev/null; then
  pip3 install "git+https://github.com/${REPO}.git" 2>/dev/null || \
  pip3 install --user "git+https://github.com/${REPO}.git" 2>/dev/null
  ok "Installed via pip3"
else
  warn "No pip/uv found. Install manually: pip install git+https://github.com/${REPO}.git"
fi

# ── Step 2: Install Claude Code Skill ──
info "Installing Claude Code skill..."
SKILL_DIR="${HOME}/.claude/skills/agent-migrate"
mkdir -p "${SKILL_DIR}"
curl -fsSL "${RAW}/.claude/skills/agent-migrate/SKILL.md" -o "${SKILL_DIR}/SKILL.md"
ok "Skill installed → ${SKILL_DIR}/SKILL.md"

# ── Step 3: (Optional) Install Codex instruction ──
if [ "$INSTALL_CODEX" = true ]; then
  info "Installing Codex instruction..."
  CODEX_DIR="${HOME}/.codex"
  mkdir -p "${CODEX_DIR}"
  curl -fsSL "${RAW}/codex-instruction.md" -o "${CODEX_DIR}/agent-migrate-instruction.md"
  ok "Codex instruction → ${CODEX_DIR}/agent-migrate-instruction.md"
fi

# ── Step 4: Per-project skill (optional) ──
if [ -d ".claude" ] || [ -f "pyproject.toml" ]; then
  info "Detected project directory. Installing project-level skill..."
  mkdir -p ".claude/skills/agent-migrate"
  curl -fsSL "${RAW}/.claude/skills/agent-migrate/SKILL.md" -o ".claude/skills/agent-migrate/SKILL.md"
  ok "Project skill → .claude/skills/agent-migrate/SKILL.md"
fi

echo ""
ok "agent-migrate installed successfully!"
echo ""
echo "  Quick start:"
echo "    agent-migrate auto --json     # detect drift + plan"
echo "    agent-migrate rls --json      # check RLS policies"
echo ""
echo "  Claude Code will auto-trigger on: migrate, 마이그레이션, RLS, schema drift"
if [ "$INSTALL_CODEX" = true ]; then
  echo "  Codex instruction: ~/.codex/agent-migrate-instruction.md"
fi

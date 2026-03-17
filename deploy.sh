#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# 360 Feedback Django — One-command deploy
# Run from project root: ./deploy.sh
#
# What it does:
#   1. Checks ansible is installed
#   2. Runs the Ansible playbook against the server
# ─────────────────────────────────────────────────────────────────────────────

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Ansible requires UTF-8 locale on some systems
export LANG="${LANG:-en_US.UTF-8}"
export LC_ALL="${LC_ALL:-en_US.UTF-8}"

echo "🚀 Deploying 360 Feedback Django to server..."
echo ""

ANSIBLE_PLAYBOOK="ansible-playbook"
if ! command -v ansible-playbook &>/dev/null; then
  if [[ -x "$SCRIPT_DIR/.venv-deploy/bin/ansible-playbook" ]]; then
    ANSIBLE_PLAYBOOK="$SCRIPT_DIR/.venv-deploy/bin/ansible-playbook"
  else
    echo "❌ ansible-playbook not found. Install one of:"
    echo "   sudo apt install ansible"
    echo "   python3 -m venv .venv-deploy && .venv-deploy/bin/pip install ansible"
    exit 1
  fi
fi

# Run playbook
"$ANSIBLE_PLAYBOOK" \
  -i "$SCRIPT_DIR/ansible/inventory.ini" \
  "$SCRIPT_DIR/ansible/playbook.yml" \
  "$@"

echo ""
echo "✅ Deploy complete!"
echo "   App: http://164.52.215.113:5173/"

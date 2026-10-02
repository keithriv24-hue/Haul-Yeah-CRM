#!/usr/bin/env bash
# Practical secret scanner for the Haul Yeah CRM (Problem #1).
# Greps git-TRACKED files for credentials that must never be committed.
# Exits non-zero when something is found so it can gate a commit/CI step.
#
#   bash scripts/scan_secrets.sh
#
set -uo pipefail
cd "$(git rev-parse --show-toplevel)" || exit 2

fail=0
report() { echo "POSSIBLE SECRET [$1]:"; echo "$2"; echo; fail=1; }

# Only scan tracked files, and never scan lockfiles / example env templates.
tracked() { git ls-files -- "$@" ':!:*.lock' ':!:*yarn.lock' ':!:*package-lock.json' ':!:**/env.test.example'; }

# 1) bcrypt password hashes committed into source
hits=$(git grep -nI -e '\$2[aby]\$[0-9][0-9]\$' -- $(tracked '*.py' '*.js' '*.jsx' '*.ts' '*.tsx' '*.json' '*.md') 2>/dev/null)
[ -n "$hits" ] && report "bcrypt hash" "$hits"

# 2) tracked .env files (real env must stay out of git)
envs=$(git ls-files -- '*.env' '**/.env' '.env' 2>/dev/null | grep -v -E '\.example$' || true)
[ -n "$envs" ] && report "tracked .env file" "$envs"

# 3) long-lived provider tokens / keys in source
hits=$(git grep -nIE '(sk_live_[0-9A-Za-z]{10,}|\bpat[A-Za-z0-9]{14}\.[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{30,}|xox[baprs]-[0-9A-Za-z-]{10,})' \
  -- $(tracked '*.py' '*.js' '*.jsx' '*.ts' '*.tsx') 2>/dev/null)
[ -n "$hits" ] && report "provider token/key" "$hits"

# 4) obvious hardcoded password assignments (allow os.environ / process.env lookups)
hits=$(git grep -nIE '(password|passwd|secret|api_?key)[[:space:]]*[:=][[:space:]]*["'"'"'][^"'"'"']{6,}' \
  -- $(tracked '*.py' '*.js' '*.jsx' '*.ts' '*.tsx') 2>/dev/null \
  | grep -vE 'environ|process\.env|getenv|os\.environ|REACT_APP_|placeholder|example|detail=|message=|HTTPException|raise ' || true)
[ -n "$hits" ] && report "hardcoded password/secret literal" "$hits"

if [ "$fail" -ne 0 ]; then
  echo "scan_secrets: findings above — move them to environment variables / secrets."
  exit 1
fi
echo "scan_secrets: clean (no tracked secrets found)."

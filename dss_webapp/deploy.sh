#!/usr/bin/env bash
# Deploy the app to a DSS project as a webapp.
#
# Prereqs:
#   1. Frontend built (make build — or run `cd frontend && npm run build`)
#   2. Code env `<ENV_NAME>` exists on the target DSS instance (Python 3.11+)
#   3. `dku` CLI authenticated to the right profile
#
# The DSS project and webapp are created automatically if they don't exist.
# When the webapp is created, its generated ID is written back to app.env.
#
# Reads LIB_NS, APP_PREFIX, ENV_NAME, VITE_APP_NAME from the environment (set
# by the Makefile from app.env). Can also be called directly:
#
#   LIB_NS=my_app APP_PREFIX=MY_APP ENV_NAME=my-env \
#     VITE_APP_NAME="My App" \
#     ./dss_webapp/deploy.sh PROJECT_KEY [WEBAPP_ID] [DKU_PROFILE]

set -euo pipefail

PROJECT="${1:?Usage: deploy.sh PROJECT_KEY [WEBAPP_ID] [DKU_PROFILE]}"
WEBAPP_ID="${2:-}"
PROFILE="${3:-}"

REPO="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND_SRC="$REPO/backend"
FRONTEND_DIST="$REPO/frontend/dist"

# dku is expected to be installed globally and on PATH (authenticate with `dku auth`).
if ! command -v dku >/dev/null 2>&1; then
    echo "✗ dku CLI not found on PATH."
    echo "  Install the Dataiku CLI globally and authenticate with: dku auth"
    exit 1
fi

# Fallback defaults so the script works when called without the Makefile.
LIB_NS="${LIB_NS:-}"
APP_PREFIX="${APP_PREFIX:-}"
ENV_NAME="${ENV_NAME:-}"
VITE_APP_NAME="${VITE_APP_NAME:-}"

# Display name used when creating the project or webapp (falls back to project key).
APP_DISPLAY_NAME="${VITE_APP_NAME:-$PROJECT}"
ENABLE_WIZARD="${ENABLE_WIZARD:-0}"
ENABLE_CHARTS="${ENABLE_CHARTS:-0}"
ENABLE_FLOW="${ENABLE_FLOW:-0}"
ENABLE_DOCUMENTS="${ENABLE_DOCUMENTS:-0}"
ENABLE_CHATBOT="${ENABLE_CHATBOT:-0}"
ENABLE_DESCRIBE="${ENABLE_DESCRIBE:-0}"

# ── Pre-flight ─────────────────────────────────────────────────────────────
if [ -n "$PROFILE" ]; then
    echo "→ Switching dku profile to $PROFILE"
    dku auth switch "$PROFILE"
fi

if [ ! -d "$FRONTEND_DIST" ]; then
    echo "✗ No frontend build found at $FRONTEND_DIST"
    echo "  Run: make build   (or: cd frontend && npm run build)"
    exit 1
fi

# ── Ensure code env has the packages the enabled blocks need ──────────────────
# Adds only what's missing — never removes packages the operator added manually.
# Rebuilds the env (blocking) only when the spec changes, so normal deploys
# that touch only code are not slowed by an env rebuild.
echo "→ Ensuring code env $ENV_NAME has required packages"

REQUIRED="fastapi>=0.100.0
uvicorn[standard]>=0.20.0
uvicorn-worker
gunicorn"
[ "$ENABLE_CHATBOT"   = "1" ] && REQUIRED="$REQUIRED
langchain-core>=0.3.0
sse-starlette>=1.6.0"
[ "$ENABLE_DOCUMENTS" = "1" ] && REQUIRED="$REQUIRED
python-multipart>=0.0.7"
[ "$ENABLE_DESCRIBE"  = "1" ] && REQUIRED="$REQUIRED
pymupdf>=1.24.0"

if ! _current_json="$(dku code-env get "$ENV_NAME" -o json 2>/dev/null)"; then
    echo "  Code env '$ENV_NAME' not found — creating it with required packages"
    # dku code-env create installs DSS core packages (python-dateutil, requests…)
    # by default — the dataiku webapp kernel needs them at startup.
    printf '%s\n' "$REQUIRED" | dku code-env create "$ENV_NAME" -r -
    echo "  ✓ code env created and built"
else
    _merged="$(mktemp -t codeenv_pkgs.XXXXXX)"
    _status="$(CURRENT_JSON="$_current_json" REQUIRED="$REQUIRED" MERGED="$_merged" python3 <<'PY'
import json, os, re

def base(line):
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    return re.split(r"[\s<>=!~;\[]", line, maxsplit=1)[0].lower().replace("_", "-")

current  = (json.loads(os.environ["CURRENT_JSON"]).get("specPackageList") or "")
have     = {base(l) for l in current.splitlines()} - {None}
existing = [l for l in current.splitlines() if l.strip()]
missing  = [l for l in os.environ["REQUIRED"].splitlines()
            if l.strip() and base(l) not in have]

with open(os.environ["MERGED"], "w") as f:
    f.write("\n".join(existing + missing) + "\n")
print("CHANGED" if missing else "UNCHANGED")
PY
)"
    if [ "$_status" = "CHANGED" ]; then
        echo "  Adding missing packages and rebuilding (this may take a few minutes)…"
        dku code-env set-packages "$ENV_NAME" -p "@$_merged"
        echo "  ✓ code env updated"
    else
        echo "  ✓ code env already has all required packages"
    fi
    rm -f "$_merged"
fi

# ── Ensure project exists (idempotent) ────────────────────────────────────────
echo "→ Ensuring project $PROJECT exists"
dku project create "$PROJECT" -n "$APP_DISPLAY_NAME" --if-not-exists >/dev/null

# ── Ensure webapp exists (create on first deploy when WEBAPP_ID is empty) ─────
if [ -z "$WEBAPP_ID" ]; then
    echo "→ No WEBAPP_ID set — creating a new STANDARD webapp '$APP_DISPLAY_NAME'"
    # dku prints status messages (including the new id) to stderr, not stdout.
    create_out="$(dku webapp create "$APP_DISPLAY_NAME" -P "$PROJECT" -t STANDARD 2>&1)"
    WEBAPP_ID="$(printf '%s' "$create_out" | sed -n 's/.*id=\([A-Za-z0-9_-]*\).*/\1/p' | head -1)"
    [ -n "$WEBAPP_ID" ] || { echo "✗ Could not parse new webapp id from:"; echo "$create_out"; exit 1; }
    echo "  ✓ Created webapp id=$WEBAPP_ID"
    # Persist so the next deploy reuses it (portable Python, works on macOS + Linux).
    if [ -f "$REPO/app.env" ]; then
        python3 - "$REPO/app.env" "$WEBAPP_ID" <<'PY'
import re, sys
path, new_id = sys.argv[1], sys.argv[2]
content = open(path).read()
content = re.sub(r'^WEBAPP_ID=.*', f'WEBAPP_ID={new_id}', content, flags=re.MULTILINE)
open(path, 'w').write(content)
PY
        echo "  ✓ Recorded WEBAPP_ID=$WEBAPP_ID in app.env"
    fi
fi

# ── Helper: recursively upload a local directory to the project library ────
upload_dir() {
    local src="$1"
    local lib_root="$2"
    local total=0

    dku library mkdir "python/$lib_root" -P "$PROJECT" >/dev/null 2>&1 || true

    # Create directory structure first
    while IFS= read -r -d '' d; do
        rel="${d#"$src"}"
        rel="${rel#/}"
        [ -z "$rel" ] && continue
        case "$rel" in
            *__pycache__* | .*) continue ;;
        esac
        dku library mkdir "python/$lib_root/$rel" -P "$PROJECT" >/dev/null 2>&1 || true
    done < <(find "$src" -type d -print0)

    # Upload files
    while IFS= read -r -d '' f; do
        rel="${f#"$src/"}"
        case "$rel" in
            *__pycache__* | *.pyc | .*) continue ;;
        esac
        dku library write "python/$lib_root/$rel" -c "@$f" -P "$PROJECT" >/dev/null
        total=$((total + 1))
        printf '\r  %d files' "$total"
    done < <(find "$src" -type f -print0)

    printf '\r  %d files uploaded\n' "$total"
}

# ── 1. Ensure package root __init__.py exists ──────────────────────────────
echo "→ Ensuring python/$LIB_NS/ package root"
dku library mkdir "python/$LIB_NS" -P "$PROJECT" >/dev/null 2>&1 || true
tmp_init="$(mktemp -t deploy_init.XXXXXX.py)"
: > "$tmp_init"
dku library write "python/$LIB_NS/__init__.py" -c "@$tmp_init" -P "$PROJECT" >/dev/null
rm -f "$tmp_init"

# ── 2. Push backend ────────────────────────────────────────────────────────
echo "→ Uploading backend → python/$LIB_NS/backend/"
upload_dir "$BACKEND_SRC" "$LIB_NS/backend"

# ── 3. Push frontend dist ─────────────────────────────────────────────────
echo "→ Uploading frontend dist → python/$LIB_NS/frontend_dist/"
upload_dir "$FRONTEND_DIST" "$LIB_NS/frontend_dist"

# ── 4. Update webapp definition ───────────────────────────────────────────
echo "→ Patching webapp definition..."
WEBAPP_DIR="$(dirname "$0")"
tmp_current="$(mktemp -t webapp_current.XXXXXX.json)"
tmp_updated="$(mktemp -t webapp_updated.XXXXXX.json)"
trap 'rm -f "$tmp_current" "$tmp_updated"' EXIT

dku webapp get-definition "$WEBAPP_ID" -P "$PROJECT" > "$tmp_current"

# Generate the webapp python entry from LIB_NS + APP_PREFIX so the inline
# code always matches what was deployed, even after a rename.
GENERATED_BACKEND_PY="import importlib, os
os.environ['APP_PREFIX'] = '${APP_PREFIX}'
os.environ['${APP_PREFIX}_DSS_MODE'] = '1'
os.environ.setdefault('${APP_PREFIX}_CORS_ORIGINS', '*')
os.environ['LIB_NS'] = '${LIB_NS}'
os.environ['ENABLE_WIZARD'] = '${ENABLE_WIZARD}'
os.environ['ENABLE_CHARTS'] = '${ENABLE_CHARTS}'
os.environ['ENABLE_FLOW'] = '${ENABLE_FLOW}'
os.environ['ENABLE_DOCUMENTS'] = '${ENABLE_DOCUMENTS}'
os.environ['ENABLE_CHATBOT'] = '${ENABLE_CHATBOT}'
os.environ['ENABLE_DESCRIBE'] = '${ENABLE_DESCRIBE}'
importlib.import_module('${LIB_NS}.backend.app').configure(app)
"

WEBAPP_DIR="$WEBAPP_DIR" CURRENT="$tmp_current" UPDATED="$tmp_updated" \
GENERATED_BACKEND_PY="$GENERATED_BACKEND_PY" ENV_NAME="$ENV_NAME" \
python3 <<'PY'
import json, os

with open(os.environ["CURRENT"]) as f:
    defn = json.load(f)

webapp_dir = os.environ["WEBAPP_DIR"]
params = defn.setdefault("params", {})
params["html"]   = open(f"{webapp_dir}/html.html").read()
params["css"]    = open(f"{webapp_dir}/css.css").read()
params["js"]     = open(f"{webapp_dir}/js.js").read()
params["python"] = os.environ["GENERATED_BACKEND_PY"]

params["backendEnabled"]   = True
params["backendFramework"] = "FASTAPI"
params["autoStartBackend"] = True
params["libraries"] = sorted(set(params.get("libraries", []) + ["jquery", "dataiku"]))
params["envSelection"] = {
    "envMode": "EXPLICIT_ENV",
    "envName": os.environ["ENV_NAME"],
}

with open(os.environ["UPDATED"], "w") as f:
    json.dump(defn, f)
PY

dku webapp set-definition "$WEBAPP_ID" -d "@$tmp_updated" -P "$PROJECT" >/dev/null
echo "  ✓ webapp definition updated"

# ── 5. Restart webapp backend ─────────────────────────────────────────────
# `dku webapp start` now blocks until the backend is confirmed up or has
# crashed. On a failed boot it prints the crash reason and log tail, then
# exits non-zero — no polling loop or separate log fetch needed.

echo "→ Restarting webapp backend..."
dku webapp stop "$WEBAPP_ID" -P "$PROJECT" >/dev/null 2>&1 || true

if ! dku webapp start "$WEBAPP_ID" -P "$PROJECT"; then
    echo "Fix the error above, then re-run: make deploy"
    exit 1
fi

echo ""
echo "✓ Deployed $LIB_NS to project=$PROJECT webapp=$WEBAPP_ID"
echo "  Code env: $ENV_NAME"
echo "  Backend is running.  Tail logs anytime with:"
echo "    dku webapp logs $WEBAPP_ID -P $PROJECT"

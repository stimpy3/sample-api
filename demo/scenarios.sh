#!/usr/bin/env bash
# Demo scenarios for the contract gate.
#
#   ./demo/scenarios.sh list
#   ./demo/scenarios.sh run 2
#   ./demo/scenarios.sh reset
#
# Each scenario creates a branch, makes one change, regenerates the spec and
# commits. Push the branch (or point Jenkins at it) to see the pipeline react.
#
# The point of having seven rather than two: a gate that only ever says no is
# indistinguishable from a broken build. Scenarios 1, 6 and 7 are green, and
# they are the ones that show this is a policy rather than a wall.

set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"
PY="${PY:-.venv/Scripts/python.exe}"
[ -x "$PY" ] || PY="python"

regen() { "$PY" scripts/export_openapi.py --output openapi.yaml >/dev/null 2>&1; }

require_clean_tree() {
  # These scenarios end in `git add -A`, which would sweep up any unrelated
  # edits sitting in the working tree and commit them onto a throwaway demo
  # branch. Then `reset` deletes that branch and the work is gone. Refuse
  # rather than let that happen — it has already happened once.
  if [ -n "$(git status --porcelain)" ]; then
    echo
    echo "  Working tree is not clean:"
    git status --short | sed 's/^/    /'
    echo
    echo "  These scenarios commit everything with 'git add -A'. Commit or stash"
    echo "  first, or your changes end up on a demo branch that gets deleted."
    echo
    exit 1
  fi
}

start() {
  require_clean_tree
  git checkout -q main
  git branch -D "demo/$1" 2>/dev/null || true
  git checkout -q -b "demo/$1"
}

finish() {
  git add -A
  git commit -q -m "$1"
  echo
  echo "  branch : demo/$(git rev-parse --abbrev-ref HEAD | sed 's|demo/||')"
  echo "  expect : $2"
  echo
  echo "  push it:  git push -u origin $(git rev-parse --abbrev-ref HEAD)"
}

case "${1:-list}" in

list)
  cat <<'EOF'

  1  safe-add          Add an optional field           GREEN, deploys
  2  breaking-rename   Rename email -> email_address   RED  (breaking)
  3  stale-spec        Change code, skip regenerating  RED  (freshness)
  4  runtime-drift     Violate the spec at runtime     RED  (conformance only)
  5  reusable          Tool against an unrelated spec  proves reusability
  6  retire-endpoint   Remove a sunset endpoint        GREEN, no waiver
  7  waived-demotion   Demote a field, with a waiver   GREEN, waiver shown

  run:  ./demo/scenarios.sh run <n>

EOF
  ;;

run)
  case "${2:?which scenario}" in

  1)
    start safe-add
    sed -i 's|    created_at: datetime = Field(description="When the user record was created.")|    nickname: str \| None = Field(default=None, description="Optional short name.")\n    created_at: datetime = Field(description="When the user record was created.")|' app/models.py
    regen
    finish "Add optional nickname field" "GREEN - additive changes are not blocked"
    ;;

  2)
    start breaking-rename
    sed -i 's/\bemail\b: str = Field(description="Contact email address."/email_address: str = Field(description="Contact email address."/' app/models.py
    sed -i 's/email=email/email_address=email/; s/name=name, email=/name=name, email_address=/' app/store.py
    regen
    finish "Rename email to email_address" "RED - breaking, and staging keeps serving the old build"
    ;;

  3)
    # The whole point: the code changes and the spec does not. Do NOT regen.
    start stale-spec
    sed -i 's|    name: str = Field(description="Display name.", examples=\["Sohan"\])|    full_name: str = Field(description="Display name.", examples=["Sohan"])|' app/models.py
    sed -i 's/name=name/full_name=name/g' app/store.py
    finish "Rename name to full_name without regenerating the spec" "RED - freshness; the other two checks would pass on a stale contract"
    ;;

  4)
    # Spec untouched, implementation drifts away from it. oasdiff sees nothing
    # to compare; only a live request finds this. This is the scenario that
    # justifies having both checks.
    start runtime-drift
    python - <<'PYEOF'
import pathlib
p = pathlib.Path("app/routers/users.py")
src = p.read_text(encoding="utf-8")
src = src.replace(
    "def list_users() -> list[User]:\n    return store.list_users()",
    "def list_users() -> list[User]:\n"
    "    # Deliberate drift: the spec says created_at is a date-time string,\n"
    "    # and this returns null for it. The spec file is unchanged, so the\n"
    "    # breaking check has nothing to compare and passes.\n"
    "    from fastapi.responses import JSONResponse\n"
    "    return JSONResponse([\n"
    "        {'id': u.id, 'name': u.name, 'email': u.email, 'created_at': None}\n"
    "        for u in store.list_users()\n"
    "    ])",
)
p.write_text(src, encoding="utf-8")
PYEOF
    regen
    finish "Return null for a non-nullable field" "RED - conformance fails while breaking PASSES"
    ;;

  5)
    echo
    echo "  Reusability: the published tool against a repo that shares no code with it."
    echo
    TMP="$(mktemp -d)"
    cp "$ROOT/../api-guard/tests/fixtures/specs/base.yaml" "$TMP/old.yaml" 2>/dev/null || {
      echo "  (needs the api-guard repo alongside this one)"; exit 1; }
    cp "$ROOT/../api-guard/tests/fixtures/specs/breaking-property-removed.yaml" "$TMP/new.yaml"
    printf 'spec:\n  path: new.yaml\n  base: ./old.yaml\n' > "$TMP/api-guard.yaml"
    echo "  folder contains: $(ls "$TMP" | tr '\n' ' ')"
    echo "  no git repo, no Python, no project."
    echo
    docker run --rm -v "$TMP:/work" -w /work sohanbhadalkar/api-guard:1 check --config api-guard.yaml || true
    ;;

  6)
    start retire-endpoint
    python - <<'PYEOF'
import pathlib
p = pathlib.Path("app/routers/users.py")
src = p.read_text(encoding="utf-8")
start = src.index("@router.get(\n    \"/search\"")
end = src.index("@router.get(\n    \"/{user_id}\"")
p.write_text(src[:start] + src[end:], encoding="utf-8")
PYEOF
    regen
    finish "Remove /users/search after its sunset date" "GREEN - the promise was kept, no waiver needed"
    ;;

  7)
    start waived-demotion
    sed -i 's|    email: str = Field(description="Contact email address.", examples=\["sohan@example.com"\])|    phone: str = Field(description="Contact phone number.", examples=["+91..."])\n    email: str \| None = Field(default=None, description="Deprecated: use phone.")|' app/models.py
    regen
    echo
    echo "  Run the gate now to get the fingerprint, then add it to waivers.yaml:"
    echo "    docker run --rm -v \"\$PWD:/work\" -w /work sohanbhadalkar/api-guard:1 \\"
    echo "      check --config api-guard.yaml --generated-spec openapi.yaml"
    echo
    git add -A
    git commit -q -m "Add phone, demote email to optional"
    echo "  branch : demo/waived-demotion"
    echo "  expect : RED until a waiver is added, then GREEN with the waiver listed"
    ;;

  *) echo "unknown scenario: $2"; exit 1 ;;
  esac
  ;;

reset)
  git checkout -q main
  for b in $(git branch --list 'demo/*' | tr -d ' *'); do git branch -D "$b"; done
  echo "  back on main, demo branches removed"
  ;;

*) echo "usage: $0 {list|run <n>|reset}"; exit 1 ;;
esac

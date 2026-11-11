#!/usr/bin/env bash
# Copy the artifact reference schemas from citeck-ai into this skill and record the source commit.
# Never edit references/schemas by hand: change them in citeck-ai and run this script again.
# Usage: sync_schemas.sh /path/to/citeck-ai
set -euo pipefail
src_repo="${1:?path to the citeck-ai repository}"
here="$(cd "$(dirname "$0")/.." && pwd)"
src="$src_repo/src/main/resources/schemas"
[ -d "$src" ] || { echo "No schemas directory: $src" >&2; exit 1; }
commit="$(git -C "$src_repo" rev-parse --short HEAD)"
dirty="$(git -C "$src_repo" status --porcelain -- src/main/resources/schemas | wc -l | tr -d ' ')"
rm -rf "$here/references/schemas"
cp -R "$src" "$here/references/schemas"
{
  echo "# Source of references/schemas"
  echo
  echo "Copied from citeck-ai \`src/main/resources/schemas/\` at commit \`$commit\` on $(date -u +%Y-%m-%d)."
  [ "$dirty" = "0" ] || echo "WARNING: the source had $dirty uncommitted change(s) in the schemas directory."
  echo "Do not edit these files here: change citeck-ai and run scripts/sync_schemas.sh again."
} > "$here/references/schemas/SOURCE.md"
echo "schemas copied from citeck-ai $commit"

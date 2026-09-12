#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REF="${1:-}"
if [[ -z "$REF" ]]; then
  REF="$(curl -fsSL https://api.github.com/repos/NousResearch/hermes-agent/releases/latest | jq -r .tag_name)"
fi
[[ "$REF" =~ ^v[0-9]{4}\.[0-9]+\.[0-9]+([.-][0-9]+)?$ ]] || { echo "Unexpected upstream tag: $REF" >&2; exit 1; }

VERSION="${REF#v}"
BUILD="$ROOT/build"
DIST="$ROOT/dist"
rm -rf "$BUILD" "$DIST"
mkdir -p "$BUILD/runtime-export" "$BUILD/staging/app" "$DIST"

docker buildx build --platform linux/arm64 \
  --build-arg "HERMES_REF=$REF" \
  --file "$ROOT/scripts/Dockerfile.runtime" \
  --cache-from type=gha,scope=hermes-runtime-arm64 \
  --cache-to type=gha,scope=hermes-runtime-arm64,mode=max \
  --progress plain \
  --output "type=local,dest=$BUILD/runtime-export" "$ROOT"

test -s "$BUILD/runtime-export/runtime.tar"
gzip -1 -c "$BUILD/runtime-export/runtime.tar" > "$BUILD/staging/app/runtime.tgz"
cp -a "$ROOT/package/app/wrapper" "$ROOT/package/app/server" "$ROOT/package/app/web" "$ROOT/package/app/ui" "$BUILD/staging/app/"
tar -C "$BUILD/staging/app" -czf "$BUILD/app.tgz" .
APP_MD5="$(md5sum "$BUILD/app.tgz" | awk '{print $1}')"

cp -a "$ROOT/package/cmd" "$ROOT/package/config" "$ROOT/package/wizard" "$ROOT/package/i18n" "$BUILD/staging/"
cp "$ROOT/package/ICON.PNG" "$ROOT/package/ICON_256.PNG" "$BUILD/staging/"
cp "$BUILD/app.tgz" "$BUILD/staging/app.tgz"
sed -e "s/__FPK_VERSION__/${VERSION}-1/g" -e "s/__APP_MD5__/${APP_MD5}/g" "$ROOT/package/manifest.template" > "$BUILD/staging/manifest"

FPK="$DIST/trim.hermes_${VERSION}-1_arm64.fpk"
tar -C "$BUILD/staging" -czf "$FPK" manifest app.tgz cmd config wizard i18n ICON.PNG ICON_256.PNG
sha256sum "$FPK" > "$FPK.sha256"
tar -tzf "$FPK" >/dev/null
tar -xOf "$FPK" manifest | grep -q "checksum=\"$APP_MD5\""
printf '%s\n' "$REF" > "$DIST/upstream-ref.txt"
echo "Built $FPK"

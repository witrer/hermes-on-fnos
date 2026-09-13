#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REF="${1:-}"
if [[ -z "$REF" ]]; then
  REF="$(curl -fsSL https://api.github.com/repos/NousResearch/hermes-agent/releases/latest | jq -r .tag_name)"
fi
[[ "$REF" =~ ^v[0-9]{4}\.[0-9]+\.[0-9]+([.-][0-9]+)?$ ]] || { echo "Unexpected upstream tag: $REF" >&2; exit 1; }

VERSION="${REF#v}"
PACKAGE_REVISION="${PACKAGE_REVISION:-2}"
BUILD="$ROOT/build"
DIST="$ROOT/dist"
rm -rf "$BUILD" "$DIST"
mkdir -p "$BUILD/runtime-export" "$BUILD/package/app" "$DIST"

IMAGE_TAG="hermes-fnos-runtime:${VERSION//[^0-9A-Za-z_.-]/-}"

docker buildx build --platform linux/arm64 \
  --build-arg "HERMES_REF=$REF" \
  --file "$ROOT/scripts/Dockerfile.runtime" \
  --cache-from type=gha,scope=hermes-runtime-arm64 \
  --cache-to type=gha,scope=hermes-runtime-arm64,mode=max \
  --progress plain \
  --load --tag "$IMAGE_TAG" "$ROOT"

container_id="$(docker create --platform linux/arm64 "$IMAGE_TAG")"
cleanup_container() { docker rm -f "$container_id" >/dev/null 2>&1 || true; }
trap cleanup_container EXIT
docker cp "$container_id:/out/runtime.tar" "$BUILD/runtime-export/runtime.tar"
test -s "$BUILD/runtime-export/runtime.tar"
gzip -1 -c "$BUILD/runtime-export/runtime.tar" > "$BUILD/package/app/runtime.tgz"
cleanup_container
trap - EXIT
cp -a "$ROOT/package/app/wrapper" "$ROOT/package/app/server" "$ROOT/package/app/web" "$ROOT/package/app/ui" "$BUILD/package/app/"
cp -a "$ROOT/package/cmd" "$ROOT/package/config" "$ROOT/package/wizard" "$ROOT/package/i18n" "$BUILD/package/"
cp "$ROOT/package/ICON.PNG" "$ROOT/package/ICON_256.PNG" "$BUILD/package/"
sed -e "s/__FPK_VERSION__/${VERSION}-${PACKAGE_REVISION}/g" "$ROOT/package/manifest.template" > "$BUILD/package/manifest"

FNPACK_VERSION="${FNPACK_VERSION:-1.2.3}"
FNPACK_BIN="$BUILD/fnpack"
curl -fsSL "https://static2.fnnas.com/fnpack/fnpack-${FNPACK_VERSION}-linux-amd64" -o "$FNPACK_BIN"
chmod +x "$FNPACK_BIN"
(cd "$DIST" && "$FNPACK_BIN" build --directory "$BUILD/package")

FPK="$DIST/trim.hermes_${VERSION}-${PACKAGE_REVISION}_arm64.fpk"
mv "$DIST/trim.hermes.fpk" "$FPK"
sha256sum "$FPK" > "$FPK.sha256"
tar -tzf "$FPK" >/dev/null
APP_MD5="$(tar -xOf "$FPK" app.tgz | md5sum | awk '{print $1}')"
tar -xOf "$FPK" manifest | grep -q "checksum=\"$APP_MD5\""
printf '%s\n' "$REF" > "$DIST/upstream-ref.txt"
echo "Built $FPK"

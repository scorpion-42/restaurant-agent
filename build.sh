#!/usr/bin/env bash
#
# build.sh — package the FastAPI app as an AWS Lambda deployment zip.
#
#   Target runtime : AWS Lambda, Python 3.12, arm64 (Linux aarch64)
#   Output         : deployment.zip at the project root
#   Lambda handler : app.lambda_handler.handler
#
# Runtime dependencies are resolved for Linux aarch64 — NOT this macOS host —
# so native extensions (e.g. pydantic-core) ship as manylinux wheels.

set -euo pipefail

# Always run from the project root, regardless of the caller's working dir.
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

BUILD_DIR="build"
ZIP_FILE="deployment.zip"
PY_VERSION="3.12"
TARGET_PLATFORM="aarch64-manylinux2014"

[[ -f app/lambda_handler.py ]] || {
  echo "error: app/lambda_handler.py not found — run from a valid project root" >&2
  exit 1
}

echo "==> Cleaning previous build artifacts (${BUILD_DIR}/, ${ZIP_FILE})"
rm -rf "$BUILD_DIR" "$ZIP_FILE"
mkdir -p "$BUILD_DIR"

echo "==> Exporting runtime dependencies from uv.lock (dev group excluded)"
REQ_FILE="$(mktemp)"
trap 'rm -f "$REQ_FILE"' EXIT
uv export \
  --frozen \
  --no-dev \
  --no-emit-project \
  --no-hashes \
  --format requirements-txt \
  --quiet \
  -o "$REQ_FILE"

echo "==> Installing dependencies for Linux ${TARGET_PLATFORM} / Python ${PY_VERSION}"
uv pip install \
  -r "$REQ_FILE" \
  --target "$BUILD_DIR" \
  --python-platform "$TARGET_PLATFORM" \
  --python-version "$PY_VERSION" \
  --only-binary :all:

echo "==> Copying application code into ${BUILD_DIR}/app"
cp -R app "$BUILD_DIR/app"

echo "==> Copying static frontend into ${BUILD_DIR}/static"
cp -R static "$BUILD_DIR/static"

echo "==> Copying menu images into ${BUILD_DIR}/images"
cp -R images "$BUILD_DIR/images"

echo "==> Stripping build noise (__pycache__, *.pyc, .DS_Store, dist-info RECORD)"
find "$BUILD_DIR" -type d -name "__pycache__" -prune -exec rm -rf {} +
find "$BUILD_DIR" -type f -name "*.pyc" -delete
find "$BUILD_DIR" -type f -name ".DS_Store" -delete
find "$BUILD_DIR" -type f -path "*.dist-info/RECORD" -delete

echo "==> Zipping contents of ${BUILD_DIR}/ into ${ZIP_FILE}"
( cd "$BUILD_DIR" && zip -r -q -X "../${ZIP_FILE}" . )

echo "==> Build complete: ${ZIP_FILE} ($(du -h "$ZIP_FILE" | cut -f1))"

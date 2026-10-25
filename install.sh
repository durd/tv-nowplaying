#!/usr/bin/env bash
# Install the app on the TV from a computer: the alternative to the integration's "App" update entity.
# Usage: ./install.sh <webhook id> [--build]
#   <webhook id>  the id shown when adding TV Now Playing in Home Assistant (or nowplaying.webhookId in
#                 local.properties)
#   --build       build the app here (JDK 17 and the Android SDK) instead of downloading the latest release
# Which TV: TV_HOST, else tv.host in local.properties, else the Philips TV found over mDNS.
set -euo pipefail
cd "$(dirname "$0")"
PKG=io.github.durd.nowplaying
LISTENER=$PKG/$PKG.NowPlayingListener
RELEASE=https://github.com/durd/tv-nowplaying/releases/latest/download/tv-nowplaying.apk

ID="" BUILD=""
for arg in "$@"; do
  case "$arg" in
    --build) BUILD=1 ;;
    -*) echo "unknown option: $arg" >&2; exit 2 ;;
    *) ID=$arg ;;
  esac
done
[ -n "$ID" ] || ID=$(sed -n 's/^nowplaying.webhookId=//p' local.properties 2>/dev/null || true)
if [ -z "$ID" ]; then
  echo "usage: ./install.sh <webhook id> [--build]   (the id shown when adding TV Now Playing in Home Assistant)" >&2
  exit 2
fi

# Python ADB client in its own venv, made on first run and kept up to date with requirements.txt.
[ -x tools/venv/bin/python ] || python3 -m venv tools/venv
tools/venv/bin/pip install -q -r tools/requirements.txt
tv() { tools/venv/bin/python -I tools/tv.py "$@"; }

mkdir -p build
APK=build/tv-nowplaying.apk
if [ -n "$BUILD" ]; then
  export JAVA_HOME="${JAVA_HOME:-/opt/homebrew/opt/openjdk@17}"
  export ANDROID_HOME="${ANDROID_HOME:-/opt/homebrew/share/android-commandlinetools}"
  grep -qs '^sdk.dir=' local.properties || echo "sdk.dir=$ANDROID_HOME" >> local.properties
  ./gradlew assembleRelease -q --console=plain
  cp app/build/outputs/apk/release/app-release.apk "$APK"
else
  curl -fsSL -o "$APK" "$RELEASE"
fi

OUT=$(tv --install "$APK" 2>&1) || true
if [[ "$OUT" == *INSTALL_FAILED_UPDATE_INCOMPATIBLE* ]]; then
  # Signed with another key (a release over a local build, or the other way round): replace it.
  echo "replacing an app signed with another key"
  tv "pm uninstall $PKG" >/dev/null
  OUT=$(tv --install "$APK" 2>&1) || true
fi
echo "$OUT"
[[ "$OUT" == *Success* ]] || exit 1

# What an install doesn't carry over: DUMP, notification access (which also starts the app), the webhook id.
tv "pm grant $PKG android.permission.DUMP; cmd notification allow_listener $LISTENER"
tv "am broadcast --include-stopped-packages -n $PKG/.ConfigReceiver --es webhook_id $ID" >/dev/null
# A fresh install takes a moment to be bound.
for _ in 1 2 3 4 5; do
  if tv 'dumpsys notification | grep -A3 "Live notification listeners"' | grep -qF "$PKG"; then
    echo "installed and configured; it reports to Home Assistant within seconds"; exit 0
  fi
  sleep 2
done
echo "ERROR: the app is installed but its notification access did not take" >&2; exit 1

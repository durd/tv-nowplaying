#!/usr/bin/env bash
# Build the app, install it on the TV and grant what it needs: notification access (Android TV has no UI
# for that) and android.permission.DUMP (to read `dumpsys media_session` and `dumpsys tv_input`).
# Usage: ./install.sh      (which TV: TV_HOST, else tv.host in local.properties, else the one found over mDNS)
set -euo pipefail
cd "$(dirname "$0")"
PKG=io.github.durd.nowplaying
LISTENER=$PKG/$PKG.NowPlayingListener

# Python ADB client in its own venv, made on first run and kept up to date with requirements.txt.
[ -x tools/venv/bin/python ] || python3 -m venv tools/venv
tools/venv/bin/pip install -q -r tools/requirements.txt
tv() { tools/venv/bin/python -I tools/tv.py "$@"; }

export JAVA_HOME="${JAVA_HOME:-/opt/homebrew/opt/openjdk@17}"
export ANDROID_HOME="${ANDROID_HOME:-/opt/homebrew/share/android-commandlinetools}"
[ -f local.properties ] || echo "sdk.dir=$ANDROID_HOME" > local.properties
# The webhook id is the only secret: anyone on the LAN who knows it can set what the TV is playing.
# Kept out of git; it is the id the TV Now Playing integration was set up with in Home Assistant.
if ! grep -q '^nowplaying.webhookId=.' local.properties; then
  echo "ERROR: set nowplaying.webhookId in local.properties to the webhook id shown when adding" >&2
  echo "the TV Now Playing integration in Home Assistant (see README.md)." >&2
  exit 1
fi
./gradlew assembleRelease -q --console=plain

tv --install app/build/outputs/apk/release/app-release.apk
# Regranting access rebinds the listener, which also restarts it on the new build.
tv "pm grant $PKG android.permission.DUMP; cmd notification disallow_listener $LISTENER; cmd notification allow_listener $LISTENER"
# A fresh install takes a moment to be bound.
for _ in 1 2 3 4 5; do
  if tv 'dumpsys notification | grep -A3 "Live notification listeners"' | grep -qF "$PKG"; then
    echo "notification access granted"; exit 0
  fi
  sleep 2
done
echo "ERROR: listener not enabled" >&2; exit 1

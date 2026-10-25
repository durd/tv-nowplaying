# AGENTS.md

Guidance for AI coding agents (Claude Code, Codex, etc.) and contributors working in this repository.

## What this is

Two parts that ship together (see README.md for what they do and why):

- `app/`: a headless Android TV app (plain Java, no Kotlin, no AndroidX) that reads media sessions and
  the HDMI input through `dumpsys` and posts changes to a Home Assistant webhook.
- `custom_components/tv_nowplaying/`: a Home Assistant integration (config flow, `media_player` and
  `update` platforms) that receives those reports and installs the app through the Android Debug Bridge
  integration.
- `tools/tv.py`, `./tv`, `install.sh`: ADB over TCP from a computer, via Python `adb_shell` (never the
  `adb` binary: its own key makes the TV ask "Allow USB debugging?" again).

Built for and tested on one TV, a Philips 65OLED706 (Android TV 11). Keep that framing: no claims of
support for other sets that haven't been tested.

## The contract between the two parts

The app POSTs JSON to `/api/webhook/<id>`: `state` (playing, buffering, paused, idle, on, off), `app`,
`app_name`, `title`, `artist`, `position` (seconds), `position_updated_at` (ISO 8601, UTC), `version`. Fields
may be null. Change both sides together, and keep the integration tolerant of reports from older app versions.

The app's settings arrive as a broadcast to `ConfigReceiver` (`--es webhook_id`, `--es ha_url`), guarded by
`android.permission.DUMP` so only ADB's shell can send it. Never log the webhook id.

## Build and test

- App: JDK 17 and the Android SDK. `./gradlew assembleRelease`. The version comes from
  `custom_components/tv_nowplaying/manifest.json` (versionCode = major*10000 + minor*100 + patch); bump it
  there only.
- Signing: release builds use the `RELEASE_*` environment (CI) or `release.signing=<properties file>` in
  the gitignored `local.properties`; otherwise the debug key. A debug-signed and a release-signed app can't
  update each other: both install paths uninstall and reinstall when that happens.
- On a TV: `./install.sh <webhook id> --build` builds, installs and configures it. `./tv '<command>'` runs a
  shell command; the app logs under the tag `NowPlaying` (`./tv 'logcat -d -s NowPlaying'`). The TV's
  logcat buffer rotates within minutes: use Home Assistant's history for timelines.
- Integration: there are no unit tests yet. Check with `python3 -m py_compile` and on a real Home Assistant
  (copy `custom_components/tv_nowplaying/` into its config, restart, add the integration). The `update`
  entity needs `app/tv-nowplaying.apk` inside the integration directory (gitignored; CI puts it there).
- Test changes against a real TV and real apps before claiming they work: what Android exposes differs by
  app (SmartTube never marks its session active, Netflix gives no title, DRM blocks screenshots).

## Releases

Push a tag `vX.Y.Z` matching `manifest.json`. `.github/workflows/release.yml` builds and signs the app and
publishes `tv-nowplaying.apk`, `tv_nowplaying.zip` (the integration with the APK in `app/`, which HACS
installs: `hacs.json` has `zip_release`) and `SHA256SUMS`. The signing key never goes in the repo.

## Conventions

- Match the surrounding code: comments explain why, not what. The app uses plain Java and the Android SDK
  only, no libraries. The integration follows current Home Assistant patterns (config entries,
  `OptionsFlowWithReload`, `DATA_COMPONENT`) and adds no requirements.
- This repo is public. Before every commit, check that it contains no personal details: host names, IP
  addresses (use 192.0.2.x in examples), device serials, webhook ids, keys, or what anyone watched.
- Commit messages: a short subject line, then the why.

# TV Now Playing

What a Philips Android TV is playing, in Home Assistant: playing, paused or idle, the app, the title
and channel (where the app tells Android), the position, and which HDMI source is on screen.

This is a **workaround for one TV**, a Philips 65OLED706 (2021/22, Android TV 11). Its Home Assistant
integration can control the TV but never says whether anything is playing: the TV's own API has no
playback state. It may well work on other Philips Android TVs of that era, and parts of it on other
Android TVs, but nothing else has been tested. Issues and pull requests are welcome; no promises.

It has two parts:

- **An app on the TV** (`app/`), with no UI, that reads the TV's media sessions and HDMI input and posts
  any change to a Home Assistant webhook.
- **A Home Assistant integration** (`custom_components/tv_nowplaying/`) that receives those reports and
  makes one media player of them. Power, volume, inputs and play/pause go on to the TV's own integration
  (Philips TV). Artwork comes from the Android Debug Bridge integration's screenshot or, while Plex
  plays, the Plex client's poster. The integration also installs and updates the app on the TV.

## What it reports

| On screen | State | Title | Artist / details |
|---|---|---|---|
| SmartTube (YouTube) | playing / paused | video title | channel |
| Netflix | playing / paused | — (Netflix doesn't say) | — |
| Plex, with the Plex client entity set | playing / paused | episode or movie title | series, season, episode, poster |
| An HDMI source | `on` | input, e.g. `HDMI 1` | the device's HDMI-CEC name as the app name |
| Home screen, menus | idle | | |
| Standby | off | | |

A set-top box on HDMI never tells the TV its channel, so an HDMI source is only ever `on`. Other apps
work as far as they publish a media session; what they put in it varies.

## Setup

### Before you start

1. **Turn on USB debugging on the TV.** Android TV settings → Device Preferences → About: select *Build*
   seven times to unlock Developer options. Then Device Preferences → Developer options → *USB
   debugging* on. On the 65OLED706 this also opens ADB over the network (port 5555).
2. **Set up the TV in Home Assistant** with these integrations (Settings → Devices & services):
   - **Philips TV**: the TV's own integration, for power, volume, inputs and play/pause.
   - **Android Debug Bridge**: for installing the app, and for screenshots as artwork. When it first
     connects, the TV asks *Allow USB debugging?*: tick *Always allow from this computer* and accept.
   - **Plex** (optional): for posters and episode details while Plex plays.
3. **Install [HACS](https://hacs.xyz/)** if you don't have it.

### A. Set up from Home Assistant (recommended)

1. In HACS, open the menu (⋮) → **Custom repositories**. Add `https://github.com/durd/tv-nowplaying`
   with type **Integration**.
2. Search HACS for **TV Now Playing**, **Download** it, and **restart Home Assistant**.
3. Settings → Devices & services → **Add integration** → **TV Now Playing**:
   - **Name**: what the TV is called, e.g. *Living Room TV*. The media player is named after it.
   - **Webhook id**: leave the random one.
   - **TV media player to control**: the Philips TV entity.
   - **Android Debug Bridge entity**: the TV's ADB entity. Needed for step 4.
   - **Artwork from** (optional): the same ADB entity, for screenshots as artwork.
   - **Plex client on this TV** (optional): the Plex entity for the Plex app on this TV.
4. **Turn the TV on**, open the new device's **App** update entity and press **Install**. It takes about
   15 seconds and finishes when the app's first report arrives.

That's it: the media player shows what the TV is playing within a few seconds of any change.

### B. Set up the app from a computer

Instead of step 4 above, for example without the Android Debug Bridge integration:

1. Do steps 1–3 of A. Copy the **webhook id** (later: TV Now Playing → *Configure* shows it).
2. On a computer with Python 3 on the same network:
   ```sh
   git clone https://github.com/durd/tv-nowplaying.git
   cd tv-nowplaying
   ./install.sh <webhook id>
   ```
   It downloads the latest release, installs it over ADB, grants what the app needs and gives it the
   webhook id. The TV is found over mDNS; with more than one TV, or to use a host name, set `TV_HOST` (or
   `tv.host=` in `local.properties`).
3. The first time, the TV asks *Allow USB debugging?* for this computer: tick *Always allow* and accept.

`./install.sh <webhook id> --build` builds the app instead (needs JDK 17 and the Android SDK; by default
Homebrew's `openjdk@17` and `android-commandlinetools`, else set `JAVA_HOME` and `ANDROID_HOME`).

## Updating

1. Update **TV Now Playing** in HACS and restart Home Assistant.
2. The **App** update entity then offers the new app version: press **Install** (TV on).

From a computer, run `./install.sh <webhook id>` again.

## Troubleshooting

- **"The TV must be on"**: installing needs the TV on and the Android Debug Bridge entity connected.
- **"Installed but has not reported"**: check the app's log, `./tv 'logcat -d -s NowPlaying'` from the
  cloned repo. `no webhook id yet` means the id didn't arrive: install again. If Home Assistant isn't
  found over mDNS, give its address (it must be the address the TV can reach directly, not a reverse
  proxy):
  ```sh
  ./tv 'am broadcast -n io.github.durd.nowplaying/.ConfigReceiver --es ha_url http://192.0.2.10:8123'
  ```
- **A build of your own and a release**: they are signed with different keys, so the TV won't update one
  with the other. Both install paths replace the app when that happens and set it up again.
- **No artwork with Netflix**: Netflix blocks screenshots.
- **The App entity says "not reported"**: the app hasn't reported its version yet (or is an older build
  that didn't); press Install.

## How it works

- The app runs as a notification listener, which Android binds at boot and keeps bound. It doesn't read
  notifications.
- It reads every media session from `dumpsys media_session`. Android's own API for other apps' sessions
  (`getActiveSessions`) only lists sessions an app marks active, and SmartTube never does. That needs
  `android.permission.DUMP`, granted over ADB. The same dump access gives `dumpsys tv_input` (the input on
  screen) and `dumpsys window displays` (the app in front). HDMI-CEC itself is closed to apps (SELinux); a
  CEC device's name comes from Android's TV input framework instead.
- It checks every 5 s while the screen is on, and right after any audio player starts or stops, and sends
  only when the state, app or title changes or the position jumps. Screen off sends `off`.
- It finds Home Assistant over mDNS (`_home-assistant._tcp`) and posts to the address and port Home
  Assistant advertises, at `/api/webhook/<id>`. The webhook only accepts requests from the local network.
- Its settings (the webhook id, optionally Home Assistant's URL) arrive over ADB as a broadcast to
  `ConfigReceiver`, which only accepts senders holding DUMP: ADB's shell, not other apps.
- The integration installs the app through the Android Debug Bridge integration's `adb_command` service.
  Each release bundles the app with the integration, so they always match.

## Security

- **ADB stays on.** Anyone on your network whose key the TV has accepted gets a shell on it, including
  Home Assistant (through the Android Debug Bridge integration) and, with setup B, `tools/adbkey/` on your
  computer: keep that private (it is gitignored and only readable by you).
- **DUMP** lets the app read Android's system diagnostics. It only ever sends the fields above, and only
  to your Home Assistant.
- **The webhook id** is the only thing that stands between the local network and setting what the TV
  reports. Treat it like a password.

## Remove

In Home Assistant, delete the TV Now Playing integration and remove it in HACS. On the TV, uninstall the
app (with setup B: `./tv 'pm uninstall io.github.durd.nowplaying'`), which also removes its permissions.

## Also here: waking a DALI Sound Hub

[`hub-wake/`](hub-wake/) is a separate workaround for the same TV: a Raspberry Pi service that turns a
DALI Sound Hub on over HDMI-CEC when the TV turns on, because after standby the hub stops answering the
TV properly and the TV gives up on it. It has nothing to do with the app or the integration. See
[hub-wake/README.md](hub-wake/README.md).

## Licence

MIT, see [LICENSE](LICENSE).

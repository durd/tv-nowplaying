# TV Now Playing

What a Philips Android TV is playing, in Home Assistant: playing, paused or idle, the app, the title
and channel (where the app tells Android), the position, and which HDMI source is on screen.

This is a **workaround for one TV**, a Philips 65OLED706 (2021/22, Android TV 11). Its Home Assistant
integration can control the TV but never says whether anything is playing: the TV's own API has no
playback state. It may well work on other Philips Android TVs of that era, and parts of it on other
Android TVs, but nothing else has been tested. Issues and pull requests are welcome; no promises.

It has two parts:

- **An Android app on the TV** (`app/`), with no UI, that reads the TV's media sessions and HDMI input
  and posts any change to a Home Assistant webhook.
- **A Home Assistant integration** (`custom_components/tv_nowplaying/`) that receives those reports and
  makes one media player out of them, passing power, volume, inputs and play/pause on to the TV's own
  integration (Philips TV) and taking artwork from another entity, such as the Android Debug Bridge
  integration's screenshot or, while Plex plays, the Plex client's poster.

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

## How it works

- The app runs as a notification listener, which Android binds at boot and keeps bound. It doesn't
  read notifications.
- It reads every media session from `dumpsys media_session`. Android's own API for other apps' sessions
  (`getActiveSessions`) only lists sessions an app marks active, and SmartTube never does. That needs
  `android.permission.DUMP`, granted over ADB. The same dump access gives `dumpsys tv_input` (the input
  on screen) and `dumpsys window displays` (the app in front). HDMI-CEC itself is closed to apps
  (SELinux); a CEC device's name comes from Android's TV input framework instead.
- It checks every 5 s while the screen is on, and right after any audio player starts or stops, and
  sends only when the state, app or title changes or the position jumps. Screen off sends `off`.
- It finds Home Assistant over mDNS (`_home-assistant._tcp`) and posts to the address and port Home
  Assistant advertises, at `/api/webhook/<id>`. The webhook only accepts requests from the local network.

## Install

### 1. Home Assistant integration

In HACS, add this repository as a custom repository (type *Integration*), download **TV Now Playing**
and restart Home Assistant. Then add the integration (Settings → Devices & services → Add):

- **Webhook id**: prefilled with a new random id. Copy it; the app is built with it.
- **TV media player to control**: the Philips TV integration's entity. The TV reads off when it does.
- **Artwork from** (optional): e.g. the Android Debug Bridge integration's entity, whose screenshot of
  the screen becomes the artwork. Netflix blocks screenshots, so it has none.
- **Plex client on this TV** (optional): the Plex integration's entity for the Plex app on this TV.

### 2. The app

Needs JDK 17, the Android SDK and Python 3 on the computer that builds it (by default Homebrew's
`openjdk@17` and `android-commandlinetools`; set `JAVA_HOME` and `ANDROID_HOME` otherwise), and ADB
over the network turned on on the TV (Settings → Developer options → USB debugging).

```sh
echo "nowplaying.webhookId=<the webhook id>" >> local.properties
./install.sh
```

`install.sh` builds the app, installs it over ADB and grants DUMP and notification access. The TV is
found over mDNS (`_philipstv_s_rpc._tcp`); with more than one, or to use a name, set `TV_HOST` or
`tv.host=` in `local.properties`. ADB goes through `tools/tv.py` (Python, `adb_shell`, in a venv made on
first run), with its own key in `tools/adbkey/`: the first connection makes the TV ask "Allow USB
debugging?" once.

`local.properties` is gitignored. Optional there: `nowplaying.haUrl=http://host:port` to skip finding
Home Assistant over mDNS.

`./tv '<command>'` runs a command on the TV, e.g. the app's log: `./tv 'logcat -d -s NowPlaying'`.

## Security

- **ADB stays on.** Anyone on your network whose key the TV has accepted gets a shell on it. The key in
  `tools/adbkey/` is such a key: keep it private (it is gitignored and only readable by you).
- **DUMP** lets the app read Android's system diagnostics. It only ever sends the fields above, and only
  to your Home Assistant.
- **The webhook id** is the only thing that stands between the local network and setting what the TV
  reports. Treat it like a password.

## Remove

On the TV: `pm uninstall io.github.durd.nowplaying` removes the app and its grants (`pm revoke
io.github.durd.nowplaying android.permission.DUMP` drops only DUMP). In Home Assistant, delete the integration
and remove it in HACS.

## Licence

MIT, see [LICENSE](LICENSE).

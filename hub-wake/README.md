# hub-wake

Turns a DALI Sound Hub on over HDMI-CEC when the TV turns on, from a Raspberry Pi on one of the TV's
HDMI inputs. A separate workaround for the same TV as the rest of this repo, a Philips 65OLED706, with a
DALI Sound Hub and its HDMI module on the TV's eARC input. Nothing else has been tested.

## The problem

The hub turned on with the TV at first, then stopped. The TV's HDMI-CEC log shows why:

- When the hub goes to standby (with the TV, or from its own remote), it drops HDMI hot-plug and from
  then on answers *Give Physical Address* with `f.f.f.f`: no valid address. It still answers on CEC.
- When the TV wakes, it asks the hub for its address, gets `f.f.f.f` five times and gives up on it, so it
  never sends *System Audio Mode Request*, the message that would turn the hub on.
- The TV can't be made to send it anyway: Android 11 has no `cmd hdmi_control`, and apps and ADB's shell
  can't reach CEC.

The hub does still accept a *Power On* key from another device. After that it reports its address
again, and the TV sets up eARC and system audio by itself.

## What it does

`hub-wake` runs on the Pi as a service. It registers the Pi as a CEC playback device (named after its
host name), listens to the bus, and when the TV announces itself after waking up (`Report Physical
Address 0.0.0.0` and `Request Active Source`, sent to all devices), it asks the hub for its address. If
the address isn't valid, it sends *User Control Pressed: Power On Function*, the key that only turns
devices on, never off, and checks again, up to three times. With the 65OLED706 and the Sound Hub, the
hub turns on a second or two after the TV.

It only reacts to the TV waking up, so turning the hub off with its own remote while the TV is on still
works. It never claims to be the active source, so the TV doesn't switch to the Pi's input.

`ensure-cec-init` keeps `hdmi_ignore_cec_init=1` in the Pi's `config.txt`, so the Pi's firmware doesn't
wake the TV or switch it to the Pi's input when the Pi boots. moOde, which this was set up on, manages
`config.txt` and may rewrite it, so the line is checked at boot, whenever `config.txt` changes, and at
shutdown, and put back if it's gone. The first change keeps a copy as `config.txt.hub-wake.bak`.

| File | Installed to | Does |
|---|---|---|
| `hub-wake` | `/usr/local/bin/` | Listens for the TV and wakes the hub |
| `hub-wake.service` | `/etc/systemd/system/` | Runs it at boot, restarts it if it stops |
| `ensure-cec-init` | `/usr/local/bin/` | Adds `hdmi_ignore_cec_init=1` to `config.txt` if missing |
| `ensure-cec-init.service` | `/etc/systemd/system/` | Runs the check at boot |
| `ensure-cec-init.path` | `/etc/systemd/system/` | Runs the check whenever `config.txt` changes |
| `ensure-cec-init-shutdown.service` | `/etc/systemd/system/` | Runs the check at shutdown, before the boot partition is unmounted |

## What you need

- A Raspberry Pi with HDMI-CEC on a free TV input. Set up on a Pi 4 running moOde (Debian 13, kernel
  6.18), which uses its micro-HDMI port 0 (next to USB-C) as `/dev/cec0`. Its audio can go elsewhere, as
  here through a DAC HAT to the hub's own inputs.
- `cec-ctl` (Debian package `v4l-utils`).
- The boot partition at `/boot/firmware`. On older Raspberry Pi OS it is `/boot`: change the path in
  `ensure-cec-init` and the two `ensure-cec-init` units.

Check that the Pi can reach the hub before installing anything. With the hub off:

```sh
cec-ctl -d0 --playback --osd-name test
cec-ctl -d0 -t5 --give-physical-addr          # f.f.f.f: the hub is in its broken state
cec-ctl -d0 -t5 --user-control-pressed ui-cmd=power-on-function
cec-ctl -d0 -t5 --user-control-released
```

The hub should turn on, and asking again should give its real address (e.g. `2.0.0.0`).

## Install

From a clone of this repo, with `pi@<host>` for the Pi:

```sh
cd hub-wake
scp hub-wake ensure-cec-init *.service *.path pi@<host>:/tmp/
ssh pi@<host> 'cd /tmp &&
  sudo install -m 755 hub-wake ensure-cec-init /usr/local/bin/ &&
  sudo install -m 644 hub-wake.service ensure-cec-init.service ensure-cec-init.path \
    ensure-cec-init-shutdown.service /etc/systemd/system/ &&
  sudo systemctl daemon-reload &&
  sudo systemctl enable --now hub-wake ensure-cec-init ensure-cec-init.path ensure-cec-init-shutdown'
```

`hdmi_ignore_cec_init` takes effect at the Pi's next reboot.

Test it: put the TV in standby, wait ten seconds, turn it on. The log shows what happened:

```sh
journalctl -u hub-wake
```

```
TV announced itself, checking hub
hub not on, sending Power On (attempt 1)
hub is on
```

## Remove

```sh
sudo systemctl disable --now hub-wake ensure-cec-init ensure-cec-init.path ensure-cec-init-shutdown
sudo rm /usr/local/bin/hub-wake /usr/local/bin/ensure-cec-init \
  /etc/systemd/system/hub-wake.service /etc/systemd/system/ensure-cec-init.service \
  /etc/systemd/system/ensure-cec-init.path /etc/systemd/system/ensure-cec-init-shutdown.service
sudo systemctl daemon-reload
```

`hdmi_ignore_cec_init=1` stays in `config.txt` until you remove it, or restore `config.txt.hub-wake.bak`.

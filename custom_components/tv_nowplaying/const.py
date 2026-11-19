"""Constants for TV Now Playing."""

DOMAIN = "tv_nowplaying"

# Entity that carries out commands: power, volume, inputs, play/pause (the TV's own integration).
CONF_CONTROL_ENTITY = "control_entity"
# Optional entity whose picture is used as artwork (e.g. the Android Debug Bridge integration's
# screenshot).
CONF_ARTWORK_ENTITY = "artwork_entity"
# Optional Android Debug Bridge integration entity for this TV, used to install the app.
CONF_ADB_ENTITY = "adb_entity"
# Optional Plex client entity for this TV: its poster and episode details while Plex is playing.
CONF_PLEX_ENTITY = "plex_entity"
# Offer volume only as up/down steps, not as a level: a sound bar on HDMI ARC/CEC keeps its own volume,
# so a level set through the TV lands a step or two off and then jumps back when the bar reports in.
CONF_VOLUME_STEPS_ONLY = "volume_steps_only"

PLEX_APP = "com.plexapp.android"
APP_PACKAGE = "io.github.durd.nowplaying"
APP_LISTENER = f"{APP_PACKAGE}/{APP_PACKAGE}.NowPlayingListener"


def signal(entry_id: str) -> str:
    """Dispatcher signal for webhook reports to one config entry's entity."""
    return f"{DOMAIN}_{entry_id}"

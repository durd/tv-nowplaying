"""Constants for TV Now Playing."""

DOMAIN = "tv_nowplaying"

# Entity that carries out commands: power, volume, inputs, play/pause (the TV's own integration).
CONF_CONTROL_ENTITY = "control_entity"
# Optional entity whose picture is used as artwork (e.g. the Android Debug Bridge integration's
# screenshot).
CONF_ARTWORK_ENTITY = "artwork_entity"
# Optional Plex client entity for this TV: its poster and episode details while Plex is playing.
CONF_PLEX_ENTITY = "plex_entity"

PLEX_APP = "com.plexapp.android"


def signal(entry_id: str) -> str:
    """Dispatcher signal for webhook reports to one config entry's entity."""
    return f"{DOMAIN}_{entry_id}"

"""The TV as one media player: what is on from the app's reports, commands to the TV's own integration."""

from __future__ import annotations

from datetime import datetime
import hashlib
from typing import Any

from homeassistant.components.media_player import (
    ATTR_INPUT_SOURCE,
    ATTR_INPUT_SOURCE_LIST,
    ATTR_MEDIA_DURATION,
    ATTR_MEDIA_EPISODE,
    ATTR_MEDIA_SEASON,
    ATTR_MEDIA_SERIES_TITLE,
    ATTR_MEDIA_TITLE,
    ATTR_MEDIA_VOLUME_LEVEL,
    ATTR_MEDIA_VOLUME_MUTED,
    DATA_COMPONENT,
    DOMAIN as MEDIA_PLAYER_DOMAIN,
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID, ATTR_ENTITY_PICTURE, ATTR_SUPPORTED_FEATURES, STATE_OFF
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, State, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

from .const import CONF_ARTWORK_ENTITY, CONF_CONTROL_ENTITY, CONF_PLEX_ENTITY, DOMAIN, PLEX_APP, signal

STATES = {
    "playing": MediaPlayerState.PLAYING,
    "buffering": MediaPlayerState.BUFFERING,
    "paused": MediaPlayerState.PAUSED,
    "idle": MediaPlayerState.IDLE,
    "on": MediaPlayerState.ON,  # an HDMI source on screen: nothing else is known about it
    "off": MediaPlayerState.OFF,
}

# What this entity can pass on to the control entity; the rest of its features are left out.
FORWARDED = (
    MediaPlayerEntityFeature.TURN_ON
    | MediaPlayerEntityFeature.TURN_OFF
    | MediaPlayerEntityFeature.VOLUME_SET
    | MediaPlayerEntityFeature.VOLUME_STEP
    | MediaPlayerEntityFeature.VOLUME_MUTE
    | MediaPlayerEntityFeature.PLAY
    | MediaPlayerEntityFeature.PAUSE
    | MediaPlayerEntityFeature.STOP
    | MediaPlayerEntityFeature.NEXT_TRACK
    | MediaPlayerEntityFeature.PREVIOUS_TRACK
    | MediaPlayerEntityFeature.SELECT_SOURCE
)

# Last report attributes kept across a restart (what the app sends, under this entity's names).
RESTORED = {"app": "app_id", "app_name": "app_name", "title": "media_title", "artist": "media_artist"}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([TvNowPlaying(entry)])


class TvNowPlaying(MediaPlayerEntity, RestoreEntity):
    """One TV, combining the app's reports with the TV's own integration."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_device_class = MediaPlayerDeviceClass.TV
    _attr_should_poll = False

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry
        self._control: str = entry.options[CONF_CONTROL_ENTITY]
        self._artwork: str | None = entry.options.get(CONF_ARTWORK_ENTITY)
        self._plex: str | None = entry.options.get(CONF_PLEX_ENTITY)
        self._report: dict[str, Any] = {}
        self._attr_unique_id = entry.entry_id
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)}, name=entry.title)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) is not None and last.state in STATES:
            # A stale "playing" from before a restart: the control entity's "off" still overrides it.
            self._report = {"state": last.state} | {k: last.attributes.get(a) for k, a in RESTORED.items()}
        self.async_on_remove(async_dispatcher_connect(self.hass, signal(self._entry.entry_id), self._on_report))
        watched = [e for e in (self._control, self._artwork, self._plex) if e]
        self.async_on_remove(async_track_state_change_event(self.hass, watched, self._on_change))

    @callback
    def _on_report(self, report: dict[str, Any]) -> None:
        self._report = report
        self.async_write_ha_state()

    @callback
    def _on_change(self, event: Event[EventStateChangedData]) -> None:
        self.async_write_ha_state()

    # Sources -------------------------------------------------------------------------------------

    def _state_of(self, entity_id: str | None) -> State | None:
        return self.hass.states.get(entity_id) if entity_id else None

    def _control_attr(self, name: str) -> Any:
        state = self._state_of(self._control)
        return state.attributes.get(name) if state else None

    def _plex_state(self) -> State | None:
        """The Plex client's state while Plex is what plays on the TV, else None."""
        if self._report.get("app") != PLEX_APP:
            return None
        state = self._state_of(self._plex)
        if state and state.state in (MediaPlayerState.PLAYING, MediaPlayerState.PAUSED):
            return state
        return None

    def _artwork_state(self) -> State | None:
        """The entity whose picture is the artwork: Plex while it plays, else the artwork entity."""
        if self.state in (None, MediaPlayerState.OFF):
            return None
        for state in (self._plex_state(), self._state_of(self._artwork)):
            if state and state.attributes.get(ATTR_ENTITY_PICTURE):
                return state
        return None

    # State ---------------------------------------------------------------------------------------

    @property
    def available(self) -> bool:
        return self._state_of(self._control) is not None or bool(self._report)

    @property
    def state(self) -> MediaPlayerState | None:
        control = self._state_of(self._control)
        if control and control.state == STATE_OFF:
            return MediaPlayerState.OFF
        if (reported := STATES.get(self._report.get("state"))) is not None:
            return reported
        if control and control.state in STATES:
            return STATES[control.state]
        return None

    @property
    def app_id(self) -> str | None:
        return self._report.get("app")

    @property
    def app_name(self) -> str | None:
        return self._report.get("app_name")

    @property
    def media_title(self) -> str | None:
        if plex := self._plex_state():
            return plex.attributes.get(ATTR_MEDIA_TITLE)
        return self._report.get("title")

    @property
    def media_artist(self) -> str | None:
        return None if self._plex_state() else self._report.get("artist")

    @property
    def media_series_title(self) -> str | None:
        plex = self._plex_state()
        return plex.attributes.get(ATTR_MEDIA_SERIES_TITLE) if plex else None

    @property
    def media_season(self) -> str | None:
        plex = self._plex_state()
        return plex.attributes.get(ATTR_MEDIA_SEASON) if plex else None

    @property
    def media_episode(self) -> str | None:
        plex = self._plex_state()
        return plex.attributes.get(ATTR_MEDIA_EPISODE) if plex else None

    @property
    def media_duration(self) -> int | None:
        plex = self._plex_state()
        return plex.attributes.get(ATTR_MEDIA_DURATION) if plex else None

    @property
    def media_position(self) -> float | None:
        if self.state not in (MediaPlayerState.PLAYING, MediaPlayerState.BUFFERING, MediaPlayerState.PAUSED):
            return None
        return self._report.get("position")

    @property
    def media_position_updated_at(self) -> datetime | None:
        if self.media_position is None or not (at := self._report.get("position_updated_at")):
            return None
        return dt_util.parse_datetime(at)

    @property
    def source(self) -> str | None:
        # An HDMI source on screen is reported as "on" with its input as the title ("HDMI 1").
        if self._report.get("state") == "on":
            return self._report.get("title")
        return self._control_attr(ATTR_INPUT_SOURCE)

    @property
    def source_list(self) -> list[str] | None:
        return self._control_attr(ATTR_INPUT_SOURCE_LIST)

    @property
    def volume_level(self) -> float | None:
        return self._control_attr(ATTR_MEDIA_VOLUME_LEVEL)

    @property
    def is_volume_muted(self) -> bool | None:
        return self._control_attr(ATTR_MEDIA_VOLUME_MUTED)

    @property
    def supported_features(self) -> MediaPlayerEntityFeature:
        return MediaPlayerEntityFeature(self._control_attr(ATTR_SUPPORTED_FEATURES) or 0) & FORWARDED

    # Artwork -------------------------------------------------------------------------------------

    @property
    def media_image_hash(self) -> str | None:
        # The source entity's picture URL changes with its image (a cache-busting parameter), so its
        # hash tells browsers when to fetch again.
        if (state := self._artwork_state()) is None:
            return None
        return hashlib.sha256(state.attributes[ATTR_ENTITY_PICTURE].encode()).hexdigest()[:16]

    async def async_get_media_image(self) -> tuple[bytes | None, str | None]:
        """Fetched server-side from the source entity, so no tokenised URL is handed out."""
        state = self._artwork_state()
        entity = self.hass.data[DATA_COMPONENT].get_entity(state.entity_id) if state else None
        if entity is None:
            return None, None
        return await entity.async_get_media_image()

    # Commands, passed on to the control entity ---------------------------------------------------

    async def _forward(self, service: str, **data: Any) -> None:
        await self.hass.services.async_call(
            MEDIA_PLAYER_DOMAIN, service, {ATTR_ENTITY_ID: self._control, **data}, blocking=True, context=self._context
        )

    async def async_turn_on(self) -> None:
        await self._forward("turn_on")

    async def async_turn_off(self) -> None:
        await self._forward("turn_off")

    async def async_volume_up(self) -> None:
        await self._forward("volume_up")

    async def async_volume_down(self) -> None:
        await self._forward("volume_down")

    async def async_set_volume_level(self, volume: float) -> None:
        await self._forward("volume_set", volume_level=volume)

    async def async_mute_volume(self, mute: bool) -> None:
        await self._forward("volume_mute", is_volume_muted=mute)

    async def async_media_play(self) -> None:
        await self._forward("media_play")

    async def async_media_pause(self) -> None:
        await self._forward("media_pause")

    async def async_media_stop(self) -> None:
        await self._forward("media_stop")

    async def async_media_next_track(self) -> None:
        await self._forward("media_next_track")

    async def async_media_previous_track(self) -> None:
        await self._forward("media_previous_track")

    async def async_select_source(self, source: str) -> None:
        await self._forward("select_source", source=source)

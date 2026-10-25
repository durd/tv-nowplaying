"""TV Now Playing: what an Android TV is playing, pushed by the tv-nowplaying app on the TV."""

from __future__ import annotations

import logging

from aiohttp import web

from homeassistant.components import webhook
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_WEBHOOK_ID, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import DOMAIN, signal

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.MEDIA_PLAYER, Platform.UPDATE]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Receive the TV's reports on the entry's webhook and set up its media player."""

    async def handle(hass: HomeAssistant, webhook_id: str, request: web.Request) -> web.Response | None:
        try:
            report = await request.json()
        except ValueError:
            return web.Response(status=400)
        if not isinstance(report, dict) or "state" not in report:
            return web.Response(status=400)
        _LOGGER.debug("Report: %s", report)
        async_dispatcher_send(hass, signal(entry.entry_id), report)
        return None

    # The TV posts from the LAN; local_only keeps the webhook unreachable through Nabu Casa or a proxy.
    webhook.async_register(
        hass, DOMAIN, entry.title, entry.data[CONF_WEBHOOK_ID], handle, local_only=True, allowed_methods=["POST"]
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Stop listening and remove the media player."""
    webhook.async_unregister(hass, entry.data[CONF_WEBHOOK_ID])
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

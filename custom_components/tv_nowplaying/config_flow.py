"""Config flow for TV Now Playing."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components import webhook
from homeassistant.components.media_player import DOMAIN as MEDIA_PLAYER_DOMAIN
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlowWithReload
from homeassistant.const import CONF_NAME, CONF_WEBHOOK_ID
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.selector import EntitySelector, EntitySelectorConfig

from .const import CONF_ARTWORK_ENTITY, CONF_CONTROL_ENTITY, CONF_PLEX_ENTITY, DOMAIN

MEDIA_PLAYER = EntitySelector(EntitySelectorConfig(domain=MEDIA_PLAYER_DOMAIN))


def _first(hass: HomeAssistant, platform: str) -> str | None:
    """The first media player of an integration, as a suggestion (Philips TV, ADB, Plex)."""
    for entry in er.async_get(hass).entities.values():
        if entry.domain == MEDIA_PLAYER_DOMAIN and entry.platform == platform and not entry.disabled:
            return entry.entity_id
    return None


def _entities_schema(hass: HomeAssistant, current: dict[str, Any]) -> dict:
    """Entity fields, suggested from the current settings or else from what is installed."""

    def suggest(key: str, platform: str) -> dict:
        value = current.get(key) if current else _first(hass, platform)
        return {"suggested_value": value} if value else {}

    return {
        vol.Required(CONF_CONTROL_ENTITY, description=suggest(CONF_CONTROL_ENTITY, "philips_js")): MEDIA_PLAYER,
        vol.Optional(CONF_ARTWORK_ENTITY, description=suggest(CONF_ARTWORK_ENTITY, "androidtv")): MEDIA_PLAYER,
        vol.Optional(CONF_PLEX_ENTITY, description=suggest(CONF_PLEX_ENTITY, "plex")): MEDIA_PLAYER,
    }


class TvNowPlayingConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add a TV: its name, the webhook id the app on it posts to, and the entities it works with."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_WEBHOOK_ID])
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=user_input[CONF_NAME],
                data={CONF_WEBHOOK_ID: user_input[CONF_WEBHOOK_ID]},
                options={k: v for k, v in user_input.items() if k not in (CONF_NAME, CONF_WEBHOOK_ID)},
            )
        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default="TV"): str,
                # Prefilled with a new random id; paste the app's id instead to keep an existing install.
                vol.Required(CONF_WEBHOOK_ID, default=webhook.async_generate_id()): str,
                **_entities_schema(self.hass, {}),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> TvNowPlayingOptionsFlow:
        return TvNowPlayingOptionsFlow()


class TvNowPlayingOptionsFlow(OptionsFlowWithReload):
    """Change the entities; the webhook id is shown for reference (it is what the app is built with)."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(_entities_schema(self.hass, dict(self.config_entry.options))),
            description_placeholders={"webhook_id": self.config_entry.data[CONF_WEBHOOK_ID]},
        )

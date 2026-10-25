"""Installs the app bundled with this integration on the TV, through the Android Debug Bridge integration."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
from pathlib import Path
from typing import Any

from homeassistant.components.update import UpdateEntity, UpdateEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID, CONF_WEBHOOK_ID, STATE_OFF, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.loader import async_get_integration

from .const import APP_LISTENER, APP_PACKAGE, CONF_ADB_ENTITY, DOMAIN, signal

_LOGGER = logging.getLogger(__name__)

# Bundled into the release zip by CI, next to this file (never committed).
APK = Path(__file__).parent / "app" / "tv-nowplaying.apk"
REMOTE = "/data/local/tmp/tv-nowplaying.apk"
# Raw bytes per ADB shell command, as in tools/tv.py: some TVs' adbd corrupt larger transfers.
CHUNK = 48 * 1024
# How long to wait for the freshly installed app's first report.
REPORT_TIMEOUT = 60
# Shown until the app reports its version (never installed, or a build from before it did).
UNKNOWN = "not reported"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    if entry.options.get(CONF_ADB_ENTITY):
        version = (await async_get_integration(hass, DOMAIN)).version
        async_add_entities([TvAppUpdate(entry, str(version))])


class TvAppUpdate(UpdateEntity, RestoreEntity):
    """The app on the TV: the version it reports against the one bundled here, and installing it."""

    _attr_has_entity_name = True
    _attr_translation_key = "app"
    _attr_supported_features = UpdateEntityFeature.INSTALL
    _attr_should_poll = False

    def __init__(self, entry: ConfigEntry, bundled: str) -> None:
        self._entry = entry
        self._adb: str = entry.options[CONF_ADB_ENTITY]
        self._attr_unique_id = f"{entry.entry_id}_app"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)})
        self._attr_latest_version = bundled
        self._attr_installed_version = UNKNOWN
        self._reported = asyncio.Event()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) and last.attributes.get("installed_version"):
            self._attr_installed_version = last.attributes["installed_version"]
        self.async_on_remove(async_dispatcher_connect(self.hass, signal(self._entry.entry_id), self._on_report))

    @callback
    def _on_report(self, report: dict[str, Any]) -> None:
        if (version := report.get("version")) and version != self._attr_installed_version:
            self._attr_installed_version = version
            self.async_write_ha_state()
        if version == self._attr_latest_version:
            self._reported.set()

    async def _shell(self, command: str) -> str:
        """Run a shell command on the TV through the ADB integration; its output, or '' for none."""
        response = await self.hass.services.async_call(
            "androidtv", "adb_command", {ATTR_ENTITY_ID: self._adb, "command": command},
            blocking=True, return_response=True,
        )
        return ((response or {}).get(self._adb) or {}).get("adb_response") or ""

    async def async_install(self, version: str | None, backup: bool, **kwargs: Any) -> None:
        if not APK.exists():
            raise HomeAssistantError("This copy of the integration has no app bundled; install a release through HACS")
        adb = self.hass.states.get(self._adb)
        if adb is None or adb.state in (STATE_UNAVAILABLE, STATE_UNKNOWN, STATE_OFF):
            raise HomeAssistantError(f"The TV must be on, and {self._adb} connected, to install the app")
        data = await self.hass.async_add_executor_job(APK.read_bytes)

        # Copy the APK over in base64 chunks and check it arrived whole.
        await self._shell(f"rm -f {REMOTE} {REMOTE}.b64")
        for i in range(0, len(data), CHUNK):
            await self._shell(f"echo -n {base64.b64encode(data[i:i + CHUNK]).decode()} >> {REMOTE}.b64")
        copied = await self._shell(f"base64 -d {REMOTE}.b64 > {REMOTE} && rm -f {REMOTE}.b64 && md5sum {REMOTE}")
        if copied.split()[:1] != [hashlib.md5(data).hexdigest()]:
            await self._shell(f"rm -f {REMOTE} {REMOTE}.b64")
            raise HomeAssistantError("The app did not reach the TV intact; try again")

        installed = await self._shell(f"pm install -r {REMOTE}")
        if "INSTALL_FAILED_UPDATE_INCOMPATIBLE" in installed:
            # Signed with another key (a build of your own): it has to go before this one can be installed.
            _LOGGER.info("Replacing an app signed with another key: %s", installed)
            await self._shell(f"pm uninstall {APP_PACKAGE}")
            installed = await self._shell(f"pm install -r {REMOTE}")
        await self._shell(f"rm -f {REMOTE}")
        if "Success" not in installed:
            raise HomeAssistantError(f"Installing the app failed: {installed or 'no answer from the TV'}")

        # What an install doesn't carry over: DUMP, notification access (which also starts it), the webhook id.
        self._reported.clear()
        await self._shell(f"pm grant {APP_PACKAGE} android.permission.DUMP; cmd notification allow_listener {APP_LISTENER}")
        await self._shell(
            f"am broadcast --include-stopped-packages -n {APP_PACKAGE}/.ConfigReceiver"
            f" --es webhook_id {self._entry.data[CONF_WEBHOOK_ID]}"
        )
        # Its first report proves all of it: installed, permitted, configured and reaching Home Assistant.
        try:
            async with asyncio.timeout(REPORT_TIMEOUT):
                await self._reported.wait()
        except TimeoutError as err:
            raise HomeAssistantError(
                f"The app was installed but has not reported within {REPORT_TIMEOUT} s; check its log on the TV"
            ) from err

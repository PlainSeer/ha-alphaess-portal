"""AlphaESS portal force-discharge control."""
import json
from pathlib import Path
from homeassistant.helpers import config_validation as cv, entity_registry as er
from homeassistant.config_entries import SOURCE_IMPORT
from homeassistant.const import Platform
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from .client import PortalClient
from .const import DOMAIN
from .coordinator import PortalCoordinator

PLATFORMS = [Platform.SWITCH, Platform.NUMBER, Platform.BUTTON]
CONFIG_SCHEMA = cv.empty_config_schema(DOMAIN)

async def async_setup(hass, config):
    # One-time import of the earlier local experiment. New users use the UI.
    if DOMAIN in config and not hass.config_entries.async_entries(DOMAIN):
        path = Path(hass.config.path('alphaess_portal.json'))
        def read_legacy():
            return json.loads(path.read_text()) if path.exists() else None
        legacy = await hass.async_add_executor_job(read_legacy)
        if legacy:
            hass.async_create_task(hass.config_entries.flow.async_init(DOMAIN, context={'source': SOURCE_IMPORT}, data=legacy))
    return True

async def async_setup_entry(hass, entry):
    client = PortalClient(async_get_clientsession(hass), entry.data['username'], entry.data['password'], entry.data['serial'])
    coordinator = PortalCoordinator(hass, entry, client)
    # Local setting controls remain usable during a network outage.
    # A failed first status read leaves only the dispatch switch unavailable.
    await coordinator.async_refresh()
    registry = er.async_get(hass)
    for entity in list(registry.entities.values()):
        if entity.config_entry_id == entry.entry_id and entity.platform == DOMAIN and entity.domain == 'sensor':
            registry.async_remove(entity.entity_id)
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True

async def async_reload_entry(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(hass, entry):
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

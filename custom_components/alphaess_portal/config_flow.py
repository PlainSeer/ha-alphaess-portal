"""Set up an owner's portal account through Home Assistant."""
import voluptuous as vol
from aiohttp import ClientError
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import selector
from .client import PortalClient, PortalAuthError
from .const import DEFAULTS, DOMAIN

LOGIN_SCHEMA = vol.Schema({
    vol.Required('username'): str,
    vol.Required('password'): selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)),
    vol.Required('serial'): str,
})

def options_schema(options):
    return vol.Schema({
        vol.Required('power_w', default=options.get('power_w', 5000)): vol.All(vol.Coerce(int), vol.Range(min=100, max=30000)),
        vol.Required('charge_power_w', default=options.get('charge_power_w', 2000)): vol.All(vol.Coerce(int), vol.Range(min=100, max=7000)),
        vol.Required('charge_target_soc', default=options.get('charge_target_soc', 100)): vol.All(vol.Coerce(int), vol.Range(min=5, max=100)),
        vol.Required('charge_duration_minutes', default=options.get('charge_duration_minutes', 5)): vol.All(vol.Coerce(int), vol.Range(min=1, max=180)),
        vol.Required('target_soc', default=options.get('target_soc', 5)): vol.All(vol.Coerce(int), vol.Range(min=5, max=100)),
        vol.Required('active_poll_seconds', default=options.get('active_poll_seconds', DEFAULTS['active_poll_seconds'])): vol.All(vol.Coerce(int), vol.Range(min=15, max=300)),
        vol.Required('idle_poll_seconds', default=options.get('idle_poll_seconds', DEFAULTS['idle_poll_seconds'])): vol.All(vol.Coerce(int), vol.Range(min=60, max=3600)),
        vol.Required('duration_minutes', default=options.get('duration_minutes', 5)): vol.All(vol.Coerce(int), vol.Range(min=1, max=180)),
    })

class PortalConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def validate(self, data):
        client = PortalClient(async_get_clientsession(self.hass), data['username'], data['password'], data['serial'])
        await client.status()

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            data = {**user_input, 'username': user_input['username'].strip(), 'serial': user_input['serial'].strip()}
            await self.async_set_unique_id(data['serial'])
            self._abort_if_unique_id_configured()
            try:
                await self.validate(data)
            except PortalAuthError:
                errors['base'] = 'invalid_auth'
            except (RuntimeError, ClientError, TimeoutError):
                errors['base'] = 'cannot_connect'
            else:
                return self.async_create_entry(title=f"AlphaESS Portal {data['serial']}", data=data, options=DEFAULTS.copy())
        return self.async_show_form(step_id='user', data_schema=LOGIN_SCHEMA, errors=errors)

    async def async_step_import(self, user_input):
        data = {key: user_input[key] for key in ['username', 'password', 'serial']}
        await self.async_set_unique_id(data['serial'])
        self._abort_if_unique_id_configured()
        try:
            await self.validate(data)
        except (RuntimeError, ClientError, TimeoutError):
            return self.async_abort(reason='cannot_connect')
        options = {**DEFAULTS, **{key: user_input[key] for key in DEFAULTS if key in user_input}}
        options['target_soc'] = max(5, options['target_soc'])
        return self.async_create_entry(title=f"AlphaESS Portal {data['serial']}", data=data, options=options)

    async def async_step_reauth(self, entry_data):
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        errors = {}
        entry = self._get_reauth_entry()
        if user_input:
            data = {**entry.data, **user_input}
            try:
                await self.validate(data)
            except PortalAuthError:
                errors['base'] = 'invalid_auth'
            except (RuntimeError, ClientError, TimeoutError):
                errors['base'] = 'cannot_connect'
            else:
                return self.async_update_reload_and_abort(entry, data_updates=user_input)
        return self.async_show_form(step_id='reauth_confirm', data_schema=vol.Schema({vol.Required('username', default=entry.data['username']): str, vol.Required('password'): selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD))}), errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return PortalOptionsFlow()

class PortalOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        return self.async_show_form(step_id='init', data_schema=options_schema(self.config_entry.options))

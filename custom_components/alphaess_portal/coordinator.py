"""Poll dispatch status quickly when active and slowly when idle."""
import logging
from datetime import timedelta, datetime, timezone
from time import monotonic
from aiohttp import ClientError, ClientConnectorError
import socket
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from .client import PortalAuthError
from .const import DEFAULTS

class PortalCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry, client):
        self.entry, self.client = entry, client
        self._fast_until = 0
        self._failures = 0
        self.last_error = None
        self.last_checked = None
        super().__init__(hass, logging.getLogger(__name__), name='AlphaESS Portal', config_entry=entry, update_interval=timedelta(seconds=self.setting('idle_poll_seconds')))

    def setting(self, key):
        return self.entry.options.get(key, DEFAULTS[key])

    def command_sent(self):
        # Keep checking briefly after commands while the portal catches up.
        self._fast_until = monotonic() + max(60, self.setting('active_poll_seconds') * 2)
        self.update_interval = timedelta(seconds=self.setting('active_poll_seconds'))

    async def _async_update_data(self):
        try:
            data = await self.client.status()
        except PortalAuthError as exc:
            raise ConfigEntryAuthFailed('Portal authentication failed') from exc
        except (RuntimeError, ClientError, TimeoutError) as exc:
            self._failures += 1
            delay = min(900, 60 * 2 ** min(self._failures - 1, 4))
            delay = max(delay, self.update_interval.total_seconds(), getattr(exc, 'retry_after', 0))
            self.update_interval = timedelta(seconds=delay)
            if isinstance(exc, TimeoutError):
                detail = 'Portal request timed out'
            elif isinstance(exc, ClientConnectorError):
                cause = exc.os_error
                dns = isinstance(cause, socket.gaierror) or 'DNS' in type(exc).__name__ or 'DNS' in str(cause)
                detail = 'DNS lookup failed' if dns else 'Portal network connection failed'
            elif isinstance(exc, ClientError):
                detail = f'Portal network error ({type(exc).__name__})'
            else:
                detail = str(exc)
            self.last_error = detail
            raise UpdateFailed(f'{detail}; retrying status in {int(delay)} seconds') from exc
        self._failures = 0
        self.last_error = None
        self.last_checked = datetime.now(timezone.utc).isoformat()
        source = ((data.get('power') or {}).get('dispatch') or {}).get('source')
        active = source in ('IMMEDIATE_DISCHARGE', 'IMMEDIATE_CHARGE') or monotonic() < self._fast_until
        seconds = self.setting('active_poll_seconds' if active else 'idle_poll_seconds')
        self.update_interval = timedelta(seconds=seconds)
        return data

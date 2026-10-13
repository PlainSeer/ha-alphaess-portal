"""The same login and charge-control requests as the AlphaESS portal."""
import asyncio
import base64
import hashlib
import math
from time import monotonic
from datetime import datetime, timezone
from urllib.parse import urlparse
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding

class PortalAuthError(RuntimeError):
    """The owner account needs to sign in again."""

class PortalRateLimitError(RuntimeError):
    """The server asked us to slow down."""
    def __init__(self, retry_after=60):
        super().__init__('AlphaESS portal rate limited the request')
        self.retry_after = retry_after

class PortalClient:
    def __init__(self, session, username, password, serial):
        self.session, self.username, self.password, self.serial = session, username.strip(), password, serial
        self._lock = asyncio.Lock()
        self._retry_at = 0
        self.endpoint = None
        self.token = None
        self.site_id = None
        self.headers = {'Client-End': 'Web', 'Client-Name': 'Portal', 'Tenant': 'alphaess', 'Accept-Language': 'en-US'}

    async def _json(self, method, url, **kwargs):
        if monotonic() < self._retry_at:
            raise PortalRateLimitError(math.ceil(self._retry_at - monotonic()))
        async with self.session.request(method, url, headers=self.headers, timeout=25, **kwargs) as response:
            if response.status in (401, 403):
                raise PortalAuthError('Portal authentication rejected')
            if response.status == 429:
                try: retry_after = max(60, int(response.headers.get('Retry-After', 60)))
                except (TypeError, ValueError): retry_after = 60
                self._retry_at = monotonic() + retry_after
                raise PortalRateLimitError(retry_after)
            if response.status >= 400:
                # Do not include raw responses or credentials in HA logs.
                raise RuntimeError(f'AlphaESS portal request failed (HTTP {response.status})')
            if response.status == 204:
                return None
            return await response.json()

    async def login(self):
        self.headers.pop('Authorization', None)
        route = await self._json('GET', 'https://platform.alphaess.com/api/users-center/users/region', params={'usernameOrEmail': self.username})
        self.endpoint = route['endPoint'].rstrip('/')
        url = urlparse(self.endpoint)
        if url.scheme != 'https' or not url.hostname.endswith('.alphaess.com'):
            raise RuntimeError('Unexpected AlphaESS region endpoint')
        padder = padding.PKCS7(128).padder()
        raw = padder.update(self.password.encode()) + padder.finalize()
        encryptor = Cipher(algorithms.AES(hashlib.sha256(self.username.encode()).digest()), modes.CBC(hashlib.md5(self.username.encode()).digest())).encryptor()
        encrypted = base64.b64encode(encryptor.update(raw) + encryptor.finalize()).decode()
        try:
            data = await self._json('POST', self.endpoint + '/users-center/sessions', json={'type': 'password', 'email': self.username, 'password': encrypted})
        except PortalRateLimitError:
            raise
        except RuntimeError as exc:
            raise PortalAuthError('Portal login rejected') from exc
        if 'accessToken' not in data:
            raise PortalAuthError('Portal login rejected')
        self.token = data
        self.expires = datetime.now(timezone.utc).timestamp() + data['expiresIn'] - 60
        self.headers['Authorization'] = 'Bearer ' + data['accessToken']

    async def request(self, method, path, **kwargs):
        async with self._lock:
            return await self._request(method, path, **kwargs)

    async def _request(self, method, path, **kwargs):
        if not self.token:
            await self.login()
        elif datetime.now(timezone.utc).timestamp() >= self.expires:
            try:
                data = await self._json('POST', self.endpoint + '/users-center/sessions/refresh', json={'refreshToken': self.token['refreshToken']})
                self.token = data
                self.expires = datetime.now(timezone.utc).timestamp() + data['expiresIn'] - 60
                self.headers['Authorization'] = 'Bearer ' + data['accessToken']
            except PortalRateLimitError:
                raise
            except RuntimeError:
                await self.login()
        return await self._json(method, self.endpoint + path, **kwargs)

    async def find_site(self):
        sites = await self.request('GET', '/internal/v1/sites')
        for site in sites:
            devices = await self.request('GET', f"/internal/v1/sites/{site['id']}/devices")
            if any(device.get('sysSn') == self.serial for device in devices.get('ess', [])):
                self.site_id = site['id']
                return
        raise RuntimeError('Configured inverter not found in this portal account')

    async def status(self):
        if self.site_id is None:
            await self.find_site()
        return await self.request('GET', f'/internal/v1/sites/{self.site_id}/real-status')

    async def discharge(self, power=5000, target_soc=5, duration=5):
        if self.site_id is None:
            await self.find_site()
        return await self.request('POST', f'/internal/v1/sites/{self.site_id}/charge-control', json={'strategy': 'Discharge', 'power': power, 'targetSoc': target_soc, 'duration': duration})

    async def charge(self, power=2000, target_soc=100, duration=5):
        # Experimental portal strategy; not yet confirmed by an AlphaESS charge test.
        if self.site_id is None:
            await self.find_site()
        return await self.request('POST', f'/internal/v1/sites/{self.site_id}/charge-control', json={'strategy': 'Charge', 'power': power, 'targetSoc': target_soc, 'duration': duration})

    async def stop(self):
        if self.site_id is None:
            await self.find_site()
        return await self.request('POST', f'/internal/v1/sites/{self.site_id}/charge-control', json={'strategy': 'Standby'})

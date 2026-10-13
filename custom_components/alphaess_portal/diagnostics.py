"""Fetch read-only portal data only when HA diagnostics are requested."""
from datetime import datetime, timezone

from aiohttp import ClientError

from .client import PortalAuthError, PortalRateLimitError


_PRIVATE_KEYS = {
    "username", "usernameoremail", "email", "password", "accessToken",
    "refreshToken", "authorization", "appsecret", "appid", "token",
    "syssn", "serial", "serialnumber", "siteid", "userid", "customerid",
    "address", "latitude", "longitude", "phone", "telephone", "ssid",
    "registerkey", "ip", "ipaddress", "mac", "name", "contactname",
}
_PRIVATE_KEYS = {key.lower() for key in _PRIVATE_KEYS}


def _redact(value, secrets):
    """Keep operational fields; exclude credentials and identifying data."""
    if isinstance(value, dict):
        return {
            key: "**REDACTED**"
            if str(key).lower().replace("_", "").replace("-", "") in _PRIVATE_KEYS
            else _redact(item, secrets)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item, secrets) for item in value]
    if isinstance(value, str):
        for secret in secrets:
            value = value.replace(secret, "**REDACTED**")
    return value


async def async_get_config_entry_diagnostics(hass, entry):
    """Use existing authentication for fixed GETs; never issue ESS writes."""
    client = entry.runtime_data.client
    if client.site_id is None:
        await client.find_site()  # Existing GET-only site/device discovery.

    result = {"captured_at": datetime.now(timezone.utc).isoformat()}
    requests = (
        ("settings", f"/internal/v1/sites/{client.site_id}/setting", {}),
        ("soc_settings", f"/internal/v1/sites/{client.site_id}/soc-setting", {}),
        ("capabilities", "/internal/v1/capabilities",
         {"params": {"siteId": client.site_id, "components": "software"}}),
    )
    for name, path, kwargs in requests:
        try:
            result[name] = {"data": await client.request("GET", path, **kwargs)}
        except PortalAuthError:
            result[name] = {"error": "authentication_failed"}
            break
        except PortalRateLimitError as exc:
            result[name] = {"error": "rate_limited", "retry_after": exc.retry_after}
            break
        except (RuntimeError, ClientError, TimeoutError, ValueError):
            # Do not expose response bodies, headers or credentials in errors.
            result[name] = {"error": "read_failed"}

    # Authentication may have refreshed during the reads; redact current tokens.
    secrets = {
        value for value in (
            client.username, client.password, client.serial, client.site_id,
            *((client.token or {}).get(key) for key in ("accessToken", "refreshToken")),
        ) if isinstance(value, str) and value
    }
    return _redact(result, sorted(secrets, key=len, reverse=True))

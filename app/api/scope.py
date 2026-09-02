from collections.abc import Mapping

from app.agent.context import TrustedScope

TENANT_HEADER = "X-Tenant-Id"
PROPERTY_HEADER = "X-Property-Id"
RUN_ID_HEADER = "X-Run-Id"


def trusted_scope_from_headers(headers: Mapping[str, str]) -> TrustedScope:
    """Build TrustedScope from demo request headers.

    This is scope propagation for the HTTP demo, not authentication.
    Values come only from X-Tenant-Id and X-Property-Id. The user
    message and request body are never read here. Missing or blank
    headers stay empty so scoped tools fail closed.
    """

    return TrustedScope(
        tenant_id=_header_value(headers, TENANT_HEADER),
        property_id=_header_value(headers, PROPERTY_HEADER),
    )


def _header_value(headers: Mapping[str, str], name: str) -> str | None:
    raw = headers.get(name)
    if raw is None:
        return None
    value = raw.strip()
    return value or None

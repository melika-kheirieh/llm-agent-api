from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.agent.context import TrustedScope
from app.agent.tools import ToolResult

ALLOWED_POLICY_ACTIONS = frozenset(
    {"dispatch_vendor", "schedule_inspection", "escalate_to_human", "monitor"}
)
ALLOWED_EMERGENCY_LEVELS = frozenset({"low", "medium", "high", "critical"})
ALLOWED_ISSUE_TYPES = frozenset({"plumbing", "hvac", "electrical", "roofing"})


@dataclass(frozen=True)
class MaintenancePolicyRequest:
    """Typed arguments for maintenance_policy_lookup. Scope is not in arguments."""

    issue_type: str | None = None

    @classmethod
    def from_arguments(cls, arguments: dict) -> "MaintenancePolicyRequest":
        value = arguments.get("issue_type")
        if not isinstance(value, str) or not value.strip():
            return cls(issue_type=None)
        issue = value.strip().lower()
        if issue not in ALLOWED_ISSUE_TYPES:
            return cls(issue_type=None)
        return cls(issue_type=issue)


@dataclass(frozen=True)
class MaintenancePolicyRecord:
    tenant_id: str
    property_id: str
    issue_type: str
    emergency_level: str
    allowed_action: str
    response_sla: str
    requires_human_escalation: bool
    policy_version: str
    effective_at: str
    expires_at: str

    def as_data(self, *, as_of: str) -> dict:
        return {
            "tenant_id": self.tenant_id,
            "property_id": self.property_id,
            "issue_type": self.issue_type,
            "emergency_level": self.emergency_level,
            "allowed_action": self.allowed_action,
            "response_sla": self.response_sla,
            "requires_human_escalation": self.requires_human_escalation,
            "policy_version": self.policy_version,
            "effective_at": self.effective_at,
            "expires_at": self.expires_at,
            "as_of": as_of,
        }


@dataclass(frozen=True)
class MaintenancePolicyObservation:
    tenant_id: str
    property_id: str
    issue_type: str
    emergency_level: str
    allowed_action: str
    response_sla: str
    requires_human_escalation: bool
    policy_version: str
    effective_at: datetime
    expires_at: datetime
    as_of: datetime

    @classmethod
    def from_data(cls, data: dict) -> "MaintenancePolicyObservation | None":
        if not isinstance(data, dict):
            return None
        tenant_id = _required_text(data.get("tenant_id"))
        property_id = _required_text(data.get("property_id"))
        issue_type = _required_text(data.get("issue_type"))
        emergency_level = _required_text(data.get("emergency_level"))
        allowed_action = _required_text(data.get("allowed_action"))
        response_sla = _required_text(data.get("response_sla"))
        policy_version = _required_text(data.get("policy_version"))
        if None in (
            tenant_id,
            property_id,
            issue_type,
            emergency_level,
            allowed_action,
            response_sla,
            policy_version,
        ):
            return None
        if not isinstance(data.get("requires_human_escalation"), bool):
            return None
        effective_at = _parse_datetime(data.get("effective_at"))
        expires_at = _parse_datetime(data.get("expires_at"))
        as_of = _parse_datetime(data.get("as_of"))
        if None in (effective_at, expires_at, as_of):
            return None
        return cls(
            tenant_id=tenant_id,
            property_id=property_id,
            issue_type=issue_type,
            emergency_level=emergency_level,
            allowed_action=allowed_action,
            response_sla=response_sla,
            requires_human_escalation=data["requires_human_escalation"],
            policy_version=policy_version,
            effective_at=effective_at,
            expires_at=expires_at,
            as_of=as_of,
        )

    def is_valid_for(
        self,
        request: MaintenancePolicyRequest,
        trusted_scope: TrustedScope,
    ) -> bool:
        if request.issue_type is None:
            return False
        if self.issue_type != request.issue_type:
            return False
        if not trusted_scope.tenant_id or not trusted_scope.property_id:
            return False
        if self.tenant_id != trusted_scope.tenant_id:
            return False
        if self.property_id != trusted_scope.property_id:
            return False
        if self.emergency_level not in ALLOWED_EMERGENCY_LEVELS:
            return False
        if self.allowed_action not in ALLOWED_POLICY_ACTIONS:
            return False
        if self.effective_at > self.as_of:
            return False
        if self.expires_at <= self.as_of:
            return False
        return True


def _required_text(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed


class MaintenancePolicyStore(Protocol):
    async def get(
        self,
        issue_type: str,
        *,
        trusted_scope: TrustedScope,
    ) -> ToolResult: ...


class MaintenancePolicyLookupTool:
    name = "maintenance_policy_lookup"

    def __init__(self, store: MaintenancePolicyStore | None = None):
        if store is None:
            from app.tools.catalog import default_policy_store

            store = default_policy_store()
        self.store = store

    async def execute(
        self,
        arguments: dict,
        *,
        trusted_scope: TrustedScope,
    ) -> ToolResult:
        request = MaintenancePolicyRequest.from_arguments(arguments)
        if request.issue_type is None:
            return ToolResult(
                success=False,
                data={"error": "missing_issue_type"},
                retryable=False,
            )
        return await self.store.get(
            request.issue_type,
            trusted_scope=trusted_scope,
        )

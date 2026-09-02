from dataclasses import dataclass
from typing import Protocol

from app.agent.context import TrustedScope
from app.agent.tools import ToolResult

ALLOWED_WORK_ORDER_STATUSES = frozenset({"open", "in_progress", "closed", "on_hold"})


@dataclass(frozen=True)
class WorkOrderLookupRequest:
    """Typed arguments for work_order_lookup. Parsed from the router's dict.

    tenant_id and property_id are never accepted here.
    """

    work_order_id: str | None = None

    @classmethod
    def from_arguments(cls, arguments: dict) -> "WorkOrderLookupRequest":
        value = arguments.get("work_order_id")
        if not isinstance(value, str) or not value.strip():
            return cls(work_order_id=None)
        return cls(work_order_id=value.strip())


@dataclass(frozen=True)
class WorkOrderRecord:
    """Persisted work-order row. Lookups are scoped by TrustedScope, not this type."""

    work_order_id: str
    tenant_id: str
    property_id: str
    status: str
    issue_type: str
    reported_at: str
    notes: str | None = None
    vendor: str | None = None

    def as_data(self) -> dict:
        payload = {
            "work_order_id": self.work_order_id,
            "tenant_id": self.tenant_id,
            "property_id": self.property_id,
            "status": self.status,
            "issue_type": self.issue_type,
            "reported_at": self.reported_at,
        }
        if self.notes is not None:
            payload["notes"] = self.notes
        if self.vendor is not None:
            payload["vendor"] = self.vendor
        return payload


WorkOrderResult = WorkOrderRecord


@dataclass(frozen=True)
class WorkOrderObservation:
    """Parsed tool payload used by verification and answer formatting."""

    work_order_id: str
    tenant_id: str
    property_id: str
    status: str
    issue_type: str
    reported_at: str

    @classmethod
    def from_data(cls, data: dict) -> "WorkOrderObservation | None":
        if not isinstance(data, dict):
            return None
        work_order_id = _required_text(data.get("work_order_id"))
        tenant_id = _required_text(data.get("tenant_id"))
        property_id = _required_text(data.get("property_id"))
        status = _required_text(data.get("status"))
        issue_type = _required_text(data.get("issue_type"))
        reported_at = _required_text(data.get("reported_at"))
        if None in (
            work_order_id,
            tenant_id,
            property_id,
            status,
            issue_type,
            reported_at,
        ):
            return None
        return cls(
            work_order_id=work_order_id,
            tenant_id=tenant_id,
            property_id=property_id,
            status=status,
            issue_type=issue_type,
            reported_at=reported_at,
        )

    def is_valid_for(
        self,
        request: WorkOrderLookupRequest,
        trusted_scope: TrustedScope,
    ) -> bool:
        if request.work_order_id is None:
            return False
        if self.work_order_id != request.work_order_id:
            return False
        if self.status not in ALLOWED_WORK_ORDER_STATUSES:
            return False
        if not trusted_scope.tenant_id or not trusted_scope.property_id:
            return False
        if self.tenant_id != trusted_scope.tenant_id:
            return False
        if self.property_id != trusted_scope.property_id:
            return False
        return True


def _required_text(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


class WorkOrderStore(Protocol):
    async def get(
        self,
        work_order_id: str,
        *,
        trusted_scope: TrustedScope,
    ) -> ToolResult: ...


class WorkOrderLookupTool:
    name = "work_order_lookup"

    def __init__(self, store: WorkOrderStore | None = None):
        if store is None:
            from app.tools.catalog import default_work_order_store

            store = default_work_order_store()
        self.store = store

    async def execute(
        self,
        arguments: dict,
        *,
        trusted_scope: TrustedScope,
    ) -> ToolResult:
        request = WorkOrderLookupRequest.from_arguments(arguments)
        if request.work_order_id is None:
            return ToolResult(
                success=False,
                data={"error": "missing_work_order_id"},
                retryable=False,
            )
        return await self.store.get(
            request.work_order_id,
            trusted_scope=trusted_scope,
        )

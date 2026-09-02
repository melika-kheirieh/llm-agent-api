from datetime import datetime
from typing import Protocol

from app.agent.context import TrustedScope
from app.agent.tools import ToolResult
from app.tools.maintenance_policy import MaintenancePolicyRecord
from app.tools.work_order import WorkOrderRecord


class WorkOrderStore(Protocol):
    async def get(
        self,
        work_order_id: str,
        *,
        trusted_scope: TrustedScope,
    ) -> ToolResult: ...


class MaintenancePolicyStore(Protocol):
    async def get(
        self,
        issue_type: str,
        *,
        trusted_scope: TrustedScope,
    ) -> ToolResult: ...


def _missing_scope_result() -> ToolResult:
    return ToolResult(
        success=False,
        data={"error": "missing_scope"},
        retryable=False,
    )


class InMemoryWorkOrderStore:
    """Deterministic in-process work-order source. No network, no SQLite."""

    def __init__(self, records: tuple[WorkOrderRecord, ...] | list[WorkOrderRecord]):
        self._by_id = {record.work_order_id: record for record in records}

    async def get(
        self,
        work_order_id: str,
        *,
        trusted_scope: TrustedScope,
    ) -> ToolResult:
        if not trusted_scope.tenant_id or not trusted_scope.property_id:
            return _missing_scope_result()
        record = self._by_id.get(work_order_id)
        if record is None:
            return ToolResult(
                success=False,
                data={"error": "not_found"},
                retryable=False,
            )
        if record.tenant_id != trusted_scope.tenant_id:
            return ToolResult(
                success=False,
                data={"error": "cross_tenant"},
                retryable=False,
            )
        if record.property_id != trusted_scope.property_id:
            return ToolResult(
                success=False,
                data={"error": "wrong_property"},
                retryable=False,
            )
        return ToolResult(success=True, data=record.as_data())


class InMemoryPolicyStore:
    """Deterministic in-process policy source. Stamps as_of from a frozen clock."""

    def __init__(
        self,
        records: tuple[MaintenancePolicyRecord, ...] | list[MaintenancePolicyRecord],
        *,
        now: datetime,
    ):
        self._now = now
        self._by_key = {
            (record.tenant_id, record.property_id, record.issue_type): record
            for record in records
        }

    async def get(
        self,
        issue_type: str,
        *,
        trusted_scope: TrustedScope,
    ) -> ToolResult:
        if not trusted_scope.tenant_id or not trusted_scope.property_id:
            return _missing_scope_result()
        record = self._by_key.get(
            (trusted_scope.tenant_id, trusted_scope.property_id, issue_type)
        )
        if record is None:
            foreign = self._foreign_policy(issue_type, trusted_scope)
            if foreign is not None:
                error = (
                    "cross_tenant"
                    if foreign.tenant_id != trusted_scope.tenant_id
                    else "wrong_property"
                )
                return ToolResult(
                    success=False,
                    data={"error": error},
                    retryable=False,
                )
            return ToolResult(
                success=False,
                data={"error": "missing_policy"},
                retryable=False,
            )
        return ToolResult(
            success=True,
            data=record.as_data(as_of=self._now.isoformat()),
        )

    def _foreign_policy(
        self,
        issue_type: str,
        trusted_scope: TrustedScope,
    ) -> MaintenancePolicyRecord | None:
        """Detect out-of-scope hits without returning their payload."""
        for record in self._by_key.values():
            if record.issue_type != issue_type:
                continue
            if record.tenant_id != trusted_scope.tenant_id:
                return record
            if record.property_id != trusted_scope.property_id:
                return record
        return None

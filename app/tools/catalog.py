from datetime import datetime, timezone

from app.agent.context import TrustedScope
from app.agent.tools import AgentTool
from app.tools.maintenance_policy import (
    MaintenancePolicyLookupTool,
    MaintenancePolicyRecord,
)
from app.tools.store import InMemoryPolicyStore, InMemoryWorkOrderStore
from app.tools.work_order import WorkOrderLookupTool, WorkOrderRecord

FROZEN_NOW = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)
DEFAULT_SCOPE = TrustedScope(tenant_id="tenant-a", property_id="prop-1")
OTHER_TENANT_SCOPE = TrustedScope(tenant_id="tenant-b", property_id="prop-2")
WRONG_PROPERTY_SCOPE = TrustedScope(tenant_id="tenant-a", property_id="prop-9")

WORK_ORDERS = (
    WorkOrderRecord(
        work_order_id="WO-123",
        tenant_id="tenant-a",
        property_id="prop-1",
        status="open",
        issue_type="plumbing",
        reported_at="2026-01-15T10:00:00+00:00",
        notes="Leak under kitchen sink",
        vendor="PipeCo",
    ),
    WorkOrderRecord(
        work_order_id="WO-456",
        tenant_id="tenant-a",
        property_id="prop-9",
        status="open",
        issue_type="electrical",
        reported_at="2026-02-01T08:00:00+00:00",
    ),
    WorkOrderRecord(
        work_order_id="WO-999",
        tenant_id="tenant-b",
        property_id="prop-2",
        status="in_progress",
        issue_type="hvac",
        reported_at="2026-03-10T14:30:00+00:00",
        vendor="CoolAir",
    ),
)

POLICIES = (
    MaintenancePolicyRecord(
        tenant_id="tenant-a",
        property_id="prop-1",
        issue_type="plumbing",
        emergency_level="high",
        allowed_action="dispatch_vendor",
        response_sla="4h",
        requires_human_escalation=False,
        policy_version="2024.1",
        effective_at="2024-01-01T00:00:00+00:00",
        expires_at="2027-12-31T00:00:00+00:00",
    ),
    MaintenancePolicyRecord(
        tenant_id="tenant-a",
        property_id="prop-1",
        issue_type="hvac",
        emergency_level="medium",
        allowed_action="schedule_inspection",
        response_sla="24h",
        requires_human_escalation=False,
        policy_version="2023.4",
        effective_at="2023-01-01T00:00:00+00:00",
        expires_at="2025-06-01T00:00:00+00:00",
    ),
    MaintenancePolicyRecord(
        tenant_id="tenant-b",
        property_id="prop-2",
        issue_type="plumbing",
        emergency_level="low",
        allowed_action="monitor",
        response_sla="72h",
        requires_human_escalation=True,
        policy_version="2024.9",
        effective_at="2024-01-01T00:00:00+00:00",
        expires_at="2027-12-31T00:00:00+00:00",
    ),
    MaintenancePolicyRecord(
        tenant_id="tenant-a",
        property_id="prop-9",
        issue_type="electrical",
        emergency_level="high",
        allowed_action="escalate_to_human",
        response_sla="1h",
        requires_human_escalation=True,
        policy_version="2025.1",
        effective_at="2025-01-01T00:00:00+00:00",
        expires_at="2028-01-01T00:00:00+00:00",
    ),
)


def default_work_order_store() -> InMemoryWorkOrderStore:
    return InMemoryWorkOrderStore(WORK_ORDERS)


def default_policy_store() -> InMemoryPolicyStore:
    return InMemoryPolicyStore(POLICIES, now=FROZEN_NOW)


def build_default_tools() -> dict[str, AgentTool]:
    work_orders = default_work_order_store()
    policies = default_policy_store()
    work_order_tool = WorkOrderLookupTool(work_orders)
    policy_tool = MaintenancePolicyLookupTool(policies)
    return {
        work_order_tool.name: work_order_tool,
        policy_tool.name: policy_tool,
    }


def scoped_work_order_data(
    work_order_id: str = "WO-123",
    *,
    status: str = "open",
    issue_type: str = "plumbing",
    tenant_id: str = DEFAULT_SCOPE.tenant_id,
    property_id: str = DEFAULT_SCOPE.property_id,
    reported_at: str = "2026-01-15T10:00:00+00:00",
) -> dict:
    """Success payload that passes domain verification for DEFAULT_SCOPE."""
    return WorkOrderRecord(
        work_order_id=work_order_id,
        tenant_id=tenant_id or "tenant-a",
        property_id=property_id or "prop-1",
        status=status,
        issue_type=issue_type,
        reported_at=reported_at,
    ).as_data()

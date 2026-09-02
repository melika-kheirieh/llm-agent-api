from dataclasses import dataclass

from app.agent.tools import ToolResult

ALLOWED_WORK_ORDER_STATUSES = frozenset({"open", "in_progress", "closed", "on_hold"})


@dataclass(frozen=True)
class WorkOrderLookupRequest:
    """Typed arguments for work_order_lookup. Parsed from the router's dict."""

    work_order_id: str | None = None

    @classmethod
    def from_arguments(cls, arguments: dict) -> "WorkOrderLookupRequest":
        value = arguments.get("work_order_id")
        if not isinstance(value, str) or not value.strip():
            return cls(work_order_id=None)
        return cls(work_order_id=value.strip())


@dataclass(frozen=True)
class WorkOrderResult:
    """Typed success payload produced by work_order_lookup."""

    work_order_id: str
    status: str
    issue_type: str

    def as_data(self) -> dict[str, str]:
        return {
            "work_order_id": self.work_order_id,
            "status": self.status,
            "issue_type": self.issue_type,
        }


@dataclass(frozen=True)
class WorkOrderObservation:
    """Parsed tool payload used by verification and answer formatting.

    Returns None from from_data when required fields are missing or not strings.
    Domain checks (allowed status, requested-id match) live on is_valid_for.
    """

    work_order_id: str
    status: str
    issue_type: str | None = None

    @classmethod
    def from_data(cls, data: dict) -> "WorkOrderObservation | None":
        if not isinstance(data, dict):
            return None

        work_order_id = data.get("work_order_id")
        status = data.get("status")
        if not isinstance(work_order_id, str) or not work_order_id.strip():
            return None
        if not isinstance(status, str) or not status.strip():
            return None

        raw_issue = data.get("issue_type")
        issue_type = raw_issue.strip() if isinstance(raw_issue, str) and raw_issue.strip() else None
        return cls(
            work_order_id=work_order_id.strip(),
            status=status.strip(),
            issue_type=issue_type,
        )

    def is_valid_for(self, request: WorkOrderLookupRequest) -> bool:
        if request.work_order_id is None:
            return False
        if self.work_order_id != request.work_order_id:
            return False
        if self.status not in ALLOWED_WORK_ORDER_STATUSES:
            return False
        return True


class WorkOrderLookupTool:
    name = "work_order_lookup"

    async def execute(self, arguments: dict) -> ToolResult:
        request = WorkOrderLookupRequest.from_arguments(arguments)
        if request.work_order_id is None:
            return ToolResult(success=False, data={"error": "missing_work_order_id"})

        result = WorkOrderResult(
            work_order_id=request.work_order_id,
            status="open",
            issue_type="plumbing",
        )
        return ToolResult(success=True, data=result.as_data())

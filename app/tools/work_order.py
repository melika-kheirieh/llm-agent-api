from dataclasses import dataclass

from app.agent.tools import ToolResult


@dataclass(frozen=True)
class WorkOrder:
    work_order_id: str
    status: str
    issue_type: str


class WorkOrderLookupTool:
    name = "work_order_lookup"

    async def execute(self, arguments: dict) -> ToolResult:
        work_order_id = arguments.get("work_order_id")
        if not work_order_id:
            return ToolResult(success=False, data={"error": "missing_work_order_id"})

        return ToolResult(
            success=True,
            data={
                "work_order_id": work_order_id,
                "status": "open",
                "issue_type": "plumbing",
            },
        )

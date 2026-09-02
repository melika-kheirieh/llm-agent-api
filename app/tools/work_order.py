from dataclasses import dataclass


@dataclass(frozen=True)
class WorkOrder:
    work_order_id: str
    status: str
    issue_type: str


class WorkOrderLookupTool:
    name = "work_order_lookup"

    def execute(self, arguments: dict) -> dict:
        work_order_id = arguments.get("work_order_id")
        if not work_order_id:
            return {"success": False, "error": "missing_work_order_id"}

        return {
            "success": True,
            "data": {
                "work_order_id": work_order_id,
                "status": "open",
                "issue_type": "plumbing",
            },
        }

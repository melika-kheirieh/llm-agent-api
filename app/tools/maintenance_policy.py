from app.agent.tools import ToolResult


class MaintenancePolicyTool:
    name = "maintenance_policy_lookup"

    async def execute(self, arguments: dict) -> ToolResult:
        issue_type = arguments.get("issue_type")
        if not issue_type:
            return ToolResult(success=False, data={"error": "missing_issue_type"})

        return ToolResult(
            success=True,
            data={
                "issue_type": issue_type,
                "priority": "normal",
                "escalation_required": False,
            },
        )

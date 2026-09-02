class MaintenancePolicyTool:
    name = "maintenance_policy_lookup"

    def execute(self, arguments: dict) -> dict:
        issue_type = arguments.get("issue_type")
        if not issue_type:
            return {"success": False, "error": "missing_issue_type"}

        return {
            "success": True,
            "data": {
                "issue_type": issue_type,
                "priority": "normal",
                "escalation_required": False,
            },
        }

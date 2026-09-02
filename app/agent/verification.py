from app.agent.tools import ToolResult


class ToolVerifier:
    def verify(self, result: ToolResult) -> bool:
        return result.success and bool(result.data)

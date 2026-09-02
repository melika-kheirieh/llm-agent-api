from app.agent.tools import ToolResult
from app.tools.work_order import WorkOrderLookupRequest, WorkOrderObservation


class ToolVerifier:
    """Domain gate for work_order_lookup results.

    A successful tool envelope is not enough: required fields, requested-id
    match, and an allowed status must all hold. Retryable tool failures stay
    unverified so RecoveryPolicy can retry them.
    """

    def verify(self, result: ToolResult, arguments: dict | None = None) -> bool:
        if not result.success:
            return False

        observation = WorkOrderObservation.from_data(result.data)
        if observation is None:
            return False

        request = WorkOrderLookupRequest.from_arguments(arguments or {})
        return observation.is_valid_for(request)

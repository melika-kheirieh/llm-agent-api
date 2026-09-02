from app.agent.context import TrustedScope
from app.agent.tools import ToolResult
from app.tools.maintenance_policy import (
    MaintenancePolicyObservation,
    MaintenancePolicyRequest,
)
from app.tools.work_order import WorkOrderLookupRequest, WorkOrderObservation

_WORK_ORDER = "work_order_lookup"
_POLICY = "maintenance_policy_lookup"


class ToolVerifier:
    """Domain gates per registered tool. Unknown tools never verify.

    Retryable tool failures stay unverified so RecoveryPolicy can retry them.
    """

    def verify(
        self,
        result: ToolResult,
        arguments: dict | None = None,
        *,
        tool_name: str | None = None,
        trusted_scope: TrustedScope | None = None,
    ) -> bool:
        if not result.success:
            return False
        scope = trusted_scope or TrustedScope()
        args = arguments or {}
        if tool_name == _WORK_ORDER:
            return _verify_work_order(result, args, scope)
        if tool_name == _POLICY:
            return _verify_policy(result, args, scope)
        return False


def _verify_work_order(
    result: ToolResult,
    arguments: dict,
    trusted_scope: TrustedScope,
) -> bool:
    observation = WorkOrderObservation.from_data(result.data)
    if observation is None:
        return False
    request = WorkOrderLookupRequest.from_arguments(arguments)
    return observation.is_valid_for(request, trusted_scope)


def _verify_policy(
    result: ToolResult,
    arguments: dict,
    trusted_scope: TrustedScope,
) -> bool:
    observation = MaintenancePolicyObservation.from_data(result.data)
    if observation is None:
        return False
    request = MaintenancePolicyRequest.from_arguments(arguments)
    return observation.is_valid_for(request, trusted_scope)

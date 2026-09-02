from app.evaluation.metrics import EvaluationResult


def test_success_case_passes():
    result = EvaluationResult(
        case_name="successful_execution",
        expected_status="completed",
        actual_status="completed",
    )

    assert result.passed


def test_escalation_case_passes():
    result = EvaluationResult(
        case_name="needs_review",
        expected_status="needs_human_review",
        actual_status="needs_human_review",
    )

    assert result.passed

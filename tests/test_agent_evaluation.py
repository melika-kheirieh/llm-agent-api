from app.evaluation.agent_cases import DEFAULT_CASES


def test_default_agent_evaluation_cases_exist():
    assert len(DEFAULT_CASES) >= 2
    assert {case.expected_status for case in DEFAULT_CASES} == {
        "completed",
        "needs_human_review",
    }

from app.agent.context import ContextItem, ContextPolicy


def test_context_policy_filters_empty_items():
    policy = ContextPolicy()

    result = policy.select(
        [
            ContextItem(key="valid", value="data", source="tool"),
            ContextItem(key="empty", value=None, source="history"),
        ]
    )

    assert len(result) == 1
    assert result[0].key == "valid"

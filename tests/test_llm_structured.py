import asyncio

import pytest
from pydantic import BaseModel, ConfigDict

from app.agent.contracts import AgentAction
from app.agent.llm_router import decision_from_routing_output
from app.agent.schemas import RoutingOutput
from app.infra.errors import FailureClass, ModelError
from app.llm.async_base import AsyncLLMClient
from app.llm.structured import generate_structured_from, parse_structured_output


class _SampleSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    count: int = 0


def test_parse_structured_output_success():
    parsed = parse_structured_output(
        '{"name": "wo", "count": 2}',
        _SampleSchema,
    )

    assert parsed.name == "wo"
    assert parsed.count == 2


def test_parse_structured_output_accepts_fenced_json():
    parsed = parse_structured_output(
        '```json\n{"action": "direct"}\n```',
        RoutingOutput,
    )

    assert parsed.action == AgentAction.DIRECT


def test_parse_malformed_text_is_model_error():
    with pytest.raises(ModelError, match="Malformed structured output") as exc:
        parse_structured_output("not json", RoutingOutput)

    assert exc.value.failure_class == FailureClass.MODEL_ERROR


def test_parse_schema_validation_failure_is_model_error():
    with pytest.raises(ModelError, match="Malformed structured output"):
        parse_structured_output(
            '{"action": "direct", "unexpected": true}',
            RoutingOutput,
        )


def test_parse_invalid_action_is_model_error():
    with pytest.raises(ModelError, match="Malformed structured output"):
        parse_structured_output('{"action": "plan"}', RoutingOutput)


class _TextOnlyLLM:
    async def generate(self, prompt: str) -> str:
        return '{"name": "from-generate"}'


class _StructuredLLM:
    def __init__(self, payload: dict):
        self.payload = payload
        self.structured_prompts: list[str] = []

    async def generate(self, prompt: str) -> str:
        raise AssertionError("generate should not run when generate_structured exists")

    async def generate_structured(self, prompt: str, schema):
        self.structured_prompts.append(prompt)
        return schema.model_validate(self.payload)


def test_generate_structured_from_uses_provider_method():
    llm = _StructuredLLM({"name": "typed"})
    parsed = asyncio.run(
        generate_structured_from(llm, "prompt", _SampleSchema)
    )

    assert parsed.name == "typed"
    assert llm.structured_prompts == ["prompt"]


def test_generate_structured_from_falls_back_to_generate():
    parsed = asyncio.run(
        generate_structured_from(_TextOnlyLLM(), "prompt", _SampleSchema)
    )

    assert parsed.name == "from-generate"


class _EchoClient(AsyncLLMClient):
    async def generate(self, prompt: str) -> str:
        return '{"name": "echo"}'


def test_default_generate_structured_parses_generate_text():
    parsed = asyncio.run(_EchoClient().generate_structured("prompt", _SampleSchema))

    assert parsed.name == "echo"


def test_router_receives_validated_typed_decision():
    parsed = RoutingOutput(action=AgentAction.DIRECT)
    decision = decision_from_routing_output(parsed)

    assert decision.action == AgentAction.DIRECT
    assert decision.tool_name is None

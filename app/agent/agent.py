from __future__ import annotations

from .schemas import Analysis
from app.llm.base import LLMClient


class Agent:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    def analyze(self, message: str) -> Analysis:
        return Analysis(language="auto", tone="neutral", task_type="qa")

    def respond(self, message: str, analysis: Analysis) -> str:
        prompt = f"Answer clearly.\n\nUser: {message}"
        return self.llm.generate(prompt).strip()

    def run(self, message: str) -> str:
        analysis = self.analyze(message)
        # hook: maybe_use_tool(message, analysis)
        return self.respond(message, analysis)

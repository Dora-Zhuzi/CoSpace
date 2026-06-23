"""LLM 服务（OpenAI 兼容接口）。

设了 llm_api_key 时走真实模型；为空时 `enabled=False`，由各业务服务走本地降级实现，
保证零配置也能端到端演示完整流程。
"""
import json
import re

from app.core.config import settings


class LLM:
    def __init__(self):
        self.enabled = bool(settings.llm_api_key)
        self.model = settings.llm_model
        self._client = None

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(
                api_key=settings.llm_api_key, base_url=settings.llm_base_url
            )
        return self._client

    def chat(self, prompt: str, system: str | None = None) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return self.chat_messages(messages)

    def chat_messages(self, messages: list[dict]) -> str:
        """多轮对话：messages 为 OpenAI 格式 [{role, content}, ...]。"""
        resp = self._get_client().chat.completions.create(
            model=self.model, messages=messages
        )
        return resp.choices[0].message.content or ""


_llm: LLM | None = None


def get_llm() -> LLM:
    global _llm
    if _llm is None:
        _llm = LLM()
    return _llm


def parse_json(content: str):
    """从 LLM 返回中提取 JSON，兼容 markdown 代码块。"""
    content = (content or "").strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", content)
    if match:
        content = match.group(1).strip()
    return json.loads(content)

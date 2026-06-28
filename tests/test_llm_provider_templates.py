from __future__ import annotations

import json
import unittest
from unittest.mock import patch


class FakeHTTPResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self) -> "FakeHTTPResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class LLMProviderTemplatesTest(unittest.TestCase):
    def test_qwen_provider_posts_openai_compatible_chat_request(self) -> None:
        from src.llm.openai_compatible import OpenAICompatibleClient

        captured: dict[str, object] = {}

        def fake_urlopen(request: object, timeout: int) -> FakeHTTPResponse:
            captured["url"] = request.full_url
            captured["timeout"] = timeout
            captured["headers"] = dict(request.header_items())
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return FakeHTTPResponse(
                {
                    "choices": [{"message": {"content": '{"ok": true}'}}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
                }
            )

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            response = OpenAICompatibleClient(
                provider="qwen",
                api_key="test-key",
                timeout_seconds=7,
                max_retries=0,
            ).chat_json("system", "user")

        self.assertEqual(
            captured["url"],
            "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
        )
        self.assertEqual(captured["timeout"], 7)
        self.assertEqual(captured["body"]["model"], "qwen-plus")
        self.assertEqual(
            captured["body"]["messages"],
            [
                {"role": "system", "content": "system"},
                {"role": "user", "content": "user"},
            ],
        )
        self.assertEqual(captured["headers"]["Authorization"], "Bearer test-key")
        self.assertEqual(response.payload, {"ok": True})
        self.assertEqual(response.usage["total_tokens"], 3)

    def test_provider_aliases_resolve_to_chinese_llm_templates(self) -> None:
        from src.llm.openai_compatible import provider_template

        self.assertEqual(provider_template("dashscope").provider, "qwen")
        self.assertEqual(
            provider_template("kimi").api_url,
            "https://api.moonshot.cn/v1/chat/completions",
        )
        self.assertEqual(
            provider_template("glm").api_url,
            "https://open.bigmodel.cn/api/paas/v4/chat/completions",
        )


if __name__ == "__main__":
    unittest.main()

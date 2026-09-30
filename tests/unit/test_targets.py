"""Unit tests for target model adapters (OpenAI/LiteLLM, Ollama, and Mock)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.targets.base import GenerationResult
from app.targets.ollama_client import OllamaTarget
from app.targets.openai_client import OpenAILiteLLMTarget


@pytest.mark.asyncio
async def test_openai_target_generate():
    """Verify OpenAILiteLLMTarget generates responses via LiteLLM."""
    target = OpenAILiteLLMTarget(
        name="GPT-4o Test",
        model_identifier="gpt-4o",
        api_key="sk-test-key",
    )

    fake_response = MagicMock()
    fake_choice = MagicMock()
    fake_choice.message.content = "Mocked GPT-4o response"
    fake_choice.finish_reason = "stop"
    fake_response.choices = [fake_choice]
    fake_response.usage.prompt_tokens = 10
    fake_response.usage.completion_tokens = 20
    fake_response.usage.total_tokens = 30

    with patch("litellm.acompletion", new_callable=AsyncMock) as mock_acompletion:
        mock_acompletion.return_value = fake_response

        res = await target.generate("Hello model")
        assert isinstance(res, GenerationResult)
        assert res.text == "Mocked GPT-4o response"
        assert res.tokens_used == 30
        assert res.prompt_tokens == 10
        assert res.completion_tokens == 20


@pytest.mark.asyncio
async def test_ollama_target_generate():
    """Verify OllamaTarget queries local Ollama HTTP endpoint."""
    target = OllamaTarget(
        name="Llama-3 Local",
        model_identifier="llama3:latest",
        endpoint_url="http://localhost:11434",
    )

    fake_payload = {
        "message": {"content": "Mocked Llama 3 output"},
        "prompt_eval_count": 8,
        "eval_count": 16,
    }

    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.json.return_value = fake_payload

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = fake_resp

        res = await target.generate("Test prompt")
        assert res.text == "Mocked Llama 3 output"
        assert res.tokens_used == 24
        assert res.prompt_tokens == 8
        assert res.completion_tokens == 16

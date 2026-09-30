"""Target model factory for instantiating model adapters from database configurations."""

from typing import Any
from app.core.security import fernet_manager
from app.db.models.target_model import TargetModelConfig
from app.targets.base import TargetModel
from app.targets.mock_client import MockTargetModel
from app.targets.ollama_client import OllamaTarget
from app.targets.openai_client import OpenAILiteLLMTarget


class TargetModelFactory:
    """Factory to create TargetModel instances from database configs or dictionary specs."""

    @staticmethod
    def create_from_config(config: TargetModelConfig) -> TargetModel:
        """Instantiate TargetModel from a SQLAlchemy TargetModelConfig model."""
        decrypted_key = fernet_manager.decrypt(config.encrypted_api_key) if config.encrypted_api_key else None
        provider = config.provider.lower().strip()

        if provider in ("mock", "test"):
            return MockTargetModel(
                name=config.name,
                model_identifier=config.model_identifier,
                is_whitebox=config.is_whitebox,
            )

        if provider == "ollama":
            return OllamaTarget(
                name=config.name,
                model_identifier=config.model_identifier,
                endpoint_url=config.endpoint_url,
                default_temperature=config.default_temperature,
                default_max_tokens=config.default_max_tokens,
                is_whitebox=config.is_whitebox,
            )

        # Default: LiteLLM unified provider (OpenAI, Anthropic, Mistral, Azure, etc.)
        return OpenAILiteLLMTarget(
            name=config.name,
            model_identifier=config.model_identifier,
            api_key=decrypted_key,
            endpoint_url=config.endpoint_url,
            default_temperature=config.default_temperature,
            default_max_tokens=config.default_max_tokens,
            extra_kwargs=config.metadata_json or {},
        )

    @staticmethod
    def create_mock(
        name: str = "Mock Safety Target",
        model_identifier: str = "mock-model",
        jailbreak_trigger: str = "JAILBREAK_SUCCESS",
    ) -> TargetModel:
        """Helper to create a mock target for tests."""
        return MockTargetModel(
            name=name,
            model_identifier=model_identifier,
            jailbreak_trigger=jailbreak_trigger,
        )


target_model_factory = TargetModelFactory()

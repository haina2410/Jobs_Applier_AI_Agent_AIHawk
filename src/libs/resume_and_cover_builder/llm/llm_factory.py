"""Factory for creating LLM instances based on config.py settings."""
import config as cfg
from langchain_core.messages import BaseMessage
from langchain_core.messages.ai import AIMessage


class MockModel:
    """Mock LLM provider for testing without calling real APIs."""
    def invoke(self, prompt) -> BaseMessage:
        return AIMessage(
            content="[Mock response] This is a placeholder response for testing purposes.",
            response_metadata={
                "model_name": "mock",
                "system_fingerprint": "",
                "finish_reason": "stop",
                "logprobs": None,
            },
            id="mock-id",
            usage_metadata={
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
            },
        )


def create_llm(openai_api_key):
    """Create an LLM instance based on LLM_MODEL_TYPE in config.py.
    Returns a ChatOpenAI-compatible model (real or mock)."""
    if cfg.LLM_MODEL_TYPE == "mock":
        return MockModel()

    from langchain_openai import ChatOpenAI
    kwargs = dict(model_name=cfg.LLM_MODEL, openai_api_key=openai_api_key, temperature=0.4)
    if cfg.LLM_API_URL:
        kwargs["openai_api_base"] = cfg.LLM_API_URL
    return ChatOpenAI(**kwargs)


def create_embeddings(openai_api_key):
    """Create an embeddings instance. Returns None for mock mode."""
    if cfg.LLM_MODEL_TYPE == "mock":
        return None

    from langchain_openai import OpenAIEmbeddings
    kwargs = dict(openai_api_key=openai_api_key)
    if cfg.LLM_API_URL:
        kwargs["openai_api_base"] = cfg.LLM_API_URL
    return OpenAIEmbeddings(**kwargs)

"""Multi-Provider LLM Configuration with Fallback Support

Provider routing uses the canonical model strings for CrewAI/LiteLLM:
  - Gemini models: gemini/<model-id>
  - OpenAI models: openai/<model-id>  (or just the model ID for direct OpenAI)
  - OpenAI-compatible proxies (MiniMax, DeepSeek): openai/<model-id> with custom base_url

ThinkingEffort maps reasoning tier to temperature — lower temperature = more focused.
"""
import os

from crewai import LLM
from dotenv import load_dotenv

load_dotenv()


class ThinkingEffort:
    """Thinking effort levels mapped to temperature."""
    LOW = 0.9
    MEDIUM = 0.5
    HIGH = 0.25
    XHIGH = 0.1


class LLMProvider:
    """Central LLM provider configuration — single LLM instances without FallbackLLM wrapper.

    Used by crew_agents.py for direct agent LLM assignment.
    For tiered primary/fallback model selection, use llm_config.build_model_matrix().
    """

    @staticmethod
    def get_orchestration_llm(fallback: bool = False) -> LLM:
        """Get Orchestration Tier LLM with High/XHigh thinking effort."""
        if not fallback:
            # Primary: Google Gemini 3.1 Pro Preview
            return LLM(
                model="gemini/gemini-3.1-pro-preview",
                api_key=os.getenv("GOOGLE_API_KEY"),
                temperature=ThinkingEffort.HIGH,
                max_tokens=8192,
            )
        else:
            # Fallback: OpenAI GPT-5.2-Codex with XHigh thinking
            return LLM(
                model="openai/gpt-5.2-codex",
                api_key=os.getenv("OPENAI_API_KEY"),
                temperature=ThinkingEffort.XHIGH,
                max_tokens=16384,
            )

    @staticmethod
    def get_l1_llm(fallback: bool = False) -> LLM:
        """Get L1 Agent LLM with Medium thinking effort."""
        if not fallback:
            # Primary: OpenAI GPT-5.2-Codex
            return LLM(
                model="openai/gpt-5.2-codex",
                api_key=os.getenv("OPENAI_API_KEY"),
                temperature=ThinkingEffort.MEDIUM,
                max_tokens=8192,
            )
        else:
            # Fallback: MiniMax m2.5 via OpenAI-compatible proxy
            # Must use openai/ prefix + base_url for OpenAI-compatible endpoints
            base_url = os.getenv("MINIMAX_BASE_URL", "https://api.minimax.chat/v1")
            return LLM(
                model="openai/minimax-m2.5",
                api_key=os.getenv("MINIMAX_API_KEY"),
                base_url=base_url.rstrip("/"),
                temperature=ThinkingEffort.MEDIUM,
                max_tokens=8192,
            )

    @staticmethod
    def get_l2_llm(fallback: bool = False) -> LLM:
        """Get L2 Agent LLM with Low thinking effort."""
        if not fallback:
            # Primary: MiniMax m2.5 via OpenAI-compatible proxy
            base_url = os.getenv("MINIMAX_BASE_URL", "https://api.minimax.chat/v1")
            return LLM(
                model="openai/minimax-m2.5",
                api_key=os.getenv("MINIMAX_API_KEY"),
                base_url=base_url.rstrip("/"),
                temperature=ThinkingEffort.LOW,
                max_tokens=4096,
            )
        else:
            # Fallback: DeepSeek v3.2 via OpenAI-compatible proxy
            base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
            return LLM(
                model="openai/deepseek-v3.2",
                api_key=os.getenv("DEEPSEEK_API_KEY"),
                base_url=base_url.rstrip("/"),
                temperature=ThinkingEffort.LOW,
                max_tokens=4096,
            )

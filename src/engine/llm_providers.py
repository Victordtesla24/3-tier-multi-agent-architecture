"""Multi-Provider LLM Configuration with Fallback Support"""
from crewai import LLM
from typing import Optional
import os
from dotenv import load_dotenv

load_dotenv()


class ThinkingEffort:
    """Thinking effort levels mapped to temperature"""
    LOW = 0.9
    MEDIUM = 0.5 
    HIGH = 0.3
    XHIGH = 0.1


class LLMProvider:
    """Central LLM provider configuration with fallback support"""

    @staticmethod
    def get_orchestration_llm(fallback: bool = False) -> LLM:
        """Get Orchestration AI Model with High thinking effort"""
        if not fallback:
            # Primary: Google Gemini 3.1 Pro Preview
            return LLM(
                model="gemini/gemini-3.1-pro-preview",
                api_key=os.getenv("GOOGLE_API_KEY"),
                temperature=ThinkingEffort.HIGH,
                max_tokens=8192
            )
        else:
            # Fallback: OpenAI GPT-5.2-Codex with xHigh thinking
            return LLM(
                model="openai/gpt-5.2-codex",
                api_key=os.getenv("OPENAI_API_KEY"),
                temperature=ThinkingEffort.XHIGH,
                max_tokens=16384
            )

    @staticmethod
    def get_l1_llm(fallback: bool = False) -> LLM:
        """Get L1 Agent LLM with Medium thinking effort"""
        if not fallback:
            # Primary: OpenAI GPT-5.2-Codex
            return LLM(
                model="openai/gpt-5.2-codex",
                api_key=os.getenv("OPENAI_API_KEY"),
                temperature=ThinkingEffort.MEDIUM,
                max_tokens=8192
            )
        else:
            # Fallback: MiniMax m2.5
            return LLM(
                model="minimax/minimax-m2.5",
                api_key=os.getenv("MINIMAX_API_KEY"),
                temperature=ThinkingEffort.MEDIUM,
                max_tokens=8192
            )

    @staticmethod
    def get_l2_llm(fallback: bool = False) -> LLM:
        """Get L2 Agent LLM with Low thinking effort"""
        if not fallback:
            # Primary: MiniMax m2.5
            return LLM(
                model="minimax/minimax-m2.5",
                api_key=os.getenv("MINIMAX_API_KEY"),
                temperature=ThinkingEffort.LOW,
                max_tokens=4096
            )
        else:
            # Fallback: DeepSeek v3.2
            return LLM(
                model="deepseek/deepseek-v3.2",
                api_key=os.getenv("DEEPSEEK_API_KEY"),
                temperature=ThinkingEffort.LOW,
                max_tokens=4096
            )

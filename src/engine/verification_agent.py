from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from engine.verification_primitives import (
    contains_banned_markers,
    extract_python_blocks,
    has_empty_implementations,
)


@dataclass(frozen=True)
class VerificationReport:
    success: bool
    banned_markers: List[str]
    syntax_errors: List[str]
    empty_implementations: int

    @property
    def errors(self) -> List[str]:
        messages: List[str] = []
        if self.banned_markers:
            markers = ", ".join(self.banned_markers)
            messages.append(
                f"Verification failed: detected banned lexical markers: {markers}"
            )
        for err in self.syntax_errors:
            messages.append(f"Verification failed: AST SyntaxError in generated code - {err}")
        if self.empty_implementations:
            messages.append(
                "Verification failed: AST detected empty implementation (pass)."
            )
        return messages

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "banned_markers": list(self.banned_markers),
            "syntax_errors": list(self.syntax_errors),
            "empty_implementations": self.empty_implementations,
        }


class VerificationAgent:
    """
    Dedicated verification agent that coordinates the individual verification
    primitives and decides overall acceptance for a pipeline run.
    """

    def evaluate(self, final_output: str) -> VerificationReport:
        output = final_output or ""

        banned_hits = contains_banned_markers(output)
        syntax_errors: List[str] = []
        empty_impl_count = 0

        for block in extract_python_blocks(output):
            has_empty, parse_error = has_empty_implementations(block)
            if parse_error is not None:
                syntax_errors.append(str(parse_error))
            if has_empty:
                empty_impl_count += 1

        success = not banned_hits and not syntax_errors and empty_impl_count == 0
        return VerificationReport(
            success=success,
            banned_markers=list(banned_hits),
            syntax_errors=syntax_errors,
            empty_implementations=empty_impl_count,
        )


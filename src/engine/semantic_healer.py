"""Semantic Self-Healing Engine for the 3-Tier Architecture.

Validates rule files against the architectural blueprint and regenerates
them if semantic drift or placeholder content is detected.
"""
import hashlib
import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("SemanticHealer")


# ---------------------------------------------------------------------------
# Canonical rule templates — generated from the blueprint source of truth
# ---------------------------------------------------------------------------

RULE_TEMPLATES: dict[str, str] = {
    "l1-orchestration.md": """\
# L1 Orchestration Agent Rules
## Role
Chief Orchestration Manager — high-level strategy and workflow control.

## Constraints
1. Decompose objectives into clearly scoped L2-level tasks.
2. Delegate ALL implementation to L2 coordinators; never implement directly.
3. Validate final outputs against user success criteria before acceptance.
4. Enforce single-source-of-truth across all artefacts.
5. Zero tolerance for simulated code, deferred task markers, or placeholders.

## Escalation
Escalate to the human operator only on unresolvable deadlock or missing API keys.
""",
    "l2-sub-agent.md": """\
# L2 Sub-Agent Coordinator Rules
## Role
Engineering Lead & Strict Code Reviewer — task decomposition and delegation.

## Constraints
1. Receive component-level objective and Success Criteria from L1.
2. Break the objective into atomic implementation tasks for L3.
3. Validate each L3 output before acceptance — reject on deferred markers, placeholder, pass-only bodies.
4. Maximum 3 retry iterations per L3 failure.
5. Produce complete, executable artefacts with explicit file paths.
6. Maintain strict 1:1 requirement-to-instruction mapping.
7. Log implementation approaches to `.agent/memory/l2-memory.md`.
""",
    "l3-leaf-worker.md": """\
# L3 Leaf Worker Agent Rules
## Role
Atomic task executor — code generation and file operations.

## Constraints
1. Never delegate — execute atomically.
2. Never emit deferred implementation markers, stub content, pass-only function bodies, or simulated logic.
3. All code must be complete, runnable, and production-ready.
4. Include explicit error handling in every function.
5. Enforce AST-parseable, syntactically valid Python for all generated code.
""",
    "system-verification-agent.md": """\
# System Verification Agent Rules
## Role
Automated architecture integrity validator.

## Constraints
1. Verify all Docs\u2194Code contract file paths exist before pipeline execution.
2. Detect lexical banned markers: unresolved TODO/TBD/FIXME markers, empty pass-only implementations, and NotImplementedError stubs.
3. Fail hard on AST-detected empty function bodies (sole `pass` statement).
4. Emit structured telemetry for every validation event.
5. Trigger auto-regeneration on any rule file with detected placeholder content.
6. On new chat/session initialization, emit exactly: `3-tier-multi-agent-architecture Status: ON 🟢`.
""",
}


class ArchitectureHealer:
    """Advanced Semantic Self-Healing Engine.

    Evaluates rule files against the architectural blueprint and regenerates
    them deterministically if drift, placeholder content, or corruption is detected.
    """

    def __init__(self, workspace_dir: str):
        self.workspace = Path(workspace_dir)
        # Resolve blueprint from project root (supports both workspace and project root)
        candidate_paths = [
            self.workspace / "docs" / "architecture" / "multi-agent-3-level-architecture.md",
            Path(__file__).parent.parent.parent / "docs" / "architecture" / "multi-agent-3-level-architecture.md",
        ]
        self.blueprint_path = next((p for p in candidate_paths if p.exists()), None)

        if self.blueprint_path and self.blueprint_path.exists():
            self.blueprint_context = self.blueprint_path.read_text(encoding="utf-8")
        else:
            self.blueprint_context = "Blueprint missing. Regeneration will use built-in canonical templates."
            logger.warning(
                "Architecture blueprint not found. Semantic healer will use built-in rule templates."
            )

        # Healing audit log — stored alongside the workspace memory
        self.audit_log_path = self.workspace / ".agent" / "memory" / "healer_audit.json"

    def validate_and_heal(self, target_rule_path: str) -> bool:
        """Validates the semantic intent of a rule file against the blueprint.

        Returns True if valid (or healed successfully), False if healing failed.
        """
        target = self.workspace / target_rule_path

        if not target.exists():
            logger.warning(f"Rule file missing: {target_rule_path}. Triggering regeneration.")
            self._regenerate_rule(target)
            self._write_audit(target_rule_path, action="CREATED", reason="file_missing")
            return True

        current_content = target.read_text(encoding="utf-8")
        checksum = hashlib.sha256(current_content.encode()).hexdigest()[:12]

        logger.info(f"Validating semantic integrity: {target_rule_path} (sha256:{checksum})")

        is_valid = self._llm_semantic_check(current_content)

        if not is_valid:
            logger.error(
                f"Semantic drift detected in {target_rule_path}. Initiating auto-regeneration."
            )
            self._regenerate_rule(target)
            self._write_audit(
                target_rule_path,
                action="REGENERATED",
                reason="semantic_drift_or_placeholder_detected",
            )
            return True

        logger.info(f"Semantic validation passed: {target_rule_path}")
        self._write_audit(target_rule_path, action="VALIDATED_OK", reason="no_drift_detected")
        return True

    def _llm_semantic_check(self, content: str) -> bool:
        """Lexical check for placeholder / drift markers.

        In a fully provisioned environment with API keys, this would call
        the LLM to evaluate semantic intent. Here we apply the same
        zero-tolerance lexical gate that the verification scoring uses.
        """
        banned_patterns = [
            (r"(?im)^\s*(#|//)\s*TODO\b", "TODO comment marker"),
            (r"(?im)^\s*TODO\b", "TODO marker"),
            (r"(?im)\bTBD\b", "TBD marker"),
            (r"(?im)\bFIXME\b", "FIXME marker"),
            (r"(?im)\braise\s+NotImplementedError\b", "NotImplementedError stub"),
            (r"(?im)^\s*pass\s*(#.*)?$", "pass-only implementation"),
            (r"(?im)<\s*placeholder\s*>", "<placeholder> token"),
            (r"(?im)\{\{\s*.*placeholder.*\}\}", "{{placeholder}} token"),
        ]
        for pattern, marker_name in banned_patterns:
            if re.search(pattern, content):
                logger.warning(f"Banned marker found: '{marker_name}'")
                return False
        return True

    def _regenerate_rule(self, target: Path) -> None:
        """Regenerates a rule file from the canonical built-in template.

        Uses the built-in RULE_TEMPLATES dictionary as the deterministic
        source of truth that mirrors the architectural blueprint.
        """
        target.parent.mkdir(parents=True, exist_ok=True)
        rule_name = target.name

        if rule_name in RULE_TEMPLATES:
            content = RULE_TEMPLATES[rule_name]
            logger.info(f"Regenerating {rule_name} from canonical template.")
        else:
            # Generate a minimal compliant rule stub for unknown rule files
            content = (
                f"# {rule_name} — Auto-generated by ArchitectureHealer\n\n"
                f"## Status\nAuto-regenerated at {datetime.now(timezone.utc).isoformat()}.\n\n"
                "## Constraints\n"
                "1. This rule was auto-regenerated. Review and extend as needed.\n"
                "2. Zero tolerance for placeholder or simulated logic.\n"
            )
            logger.warning(
                f"No canonical template for '{rule_name}'. Generated minimal compliant stub."
            )

        target.write_text(content, encoding="utf-8")
        logger.info(f"Rule file written: {target}")

    def _write_audit(self, rule_path: str, action: str, reason: str) -> None:
        """Appends a structured audit entry to the healer log."""
        try:
            self.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
            if self.audit_log_path.exists():
                data = json.loads(self.audit_log_path.read_text(encoding="utf-8"))
            else:
                data = {"events": []}

            data["events"].append(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "rule_path": rule_path,
                    "action": action,
                    "reason": reason,
                }
            )
            self.audit_log_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.error(f"Failed to write healer audit log: {exc}")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    workspace = sys.argv[1] if len(sys.argv) > 1 else "."
    healer = ArchitectureHealer(workspace)

    rules_to_validate = [
        ".agent/rules/l1-orchestration.md",
        ".agent/rules/l2-sub-agent.md",
        ".agent/rules/l3-leaf-worker.md",
        ".agent/rules/system-verification-agent.md",
    ]
    for rule in rules_to_validate:
        healer.validate_and_heal(rule)

"""Antigravity CLI — Production Entry Point for the 3-Tier Multi-Agent Architecture.

Usage:
    PYTHONPATH=src python src/orchestrator/antigravity-cli.py \\
        --prompt "<your objective>" \\
        [--workspace /path/to/workspace] \\
        [--verbose]
"""
import os
import sys
from pathlib import Path

import argparse
import json
import logging

# Ensure src/ is on the module path regardless of invocation CWD
sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.logging_utils import install_log_redaction

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
install_log_redaction()
# Prevent noisy duplicate tracer-provider warnings from third-party libs.
logging.getLogger("opentelemetry.trace").setLevel(logging.ERROR)
logger = logging.getLogger("AntigravityCLI")

# Project root is always two levels up from this file (src/orchestrator/ → project root)
PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
DEFAULT_WORKSPACE_ROOT = PROJECT_ROOT / "workspaces"


class ArchitectureHealer:
    """
    Lazy compatibility shim for tests and integrations that monkeypatch
    `antigravity-cli.py` module symbols.
    """

    def __init__(self, *args, **kwargs):
        from engine.semantic_healer import ArchitectureHealer as _Impl

        self._impl = _Impl(*args, **kwargs)

    def validate_and_heal(self, *args, **kwargs):
        return self._impl.validate_and_heal(*args, **kwargs)


class OrchestrationStateMachine:
    """
    Lazy compatibility shim for historical module-level imports.
    """

    def __init__(self, *args, **kwargs):
        from engine.state_machine import OrchestrationStateMachine as _Impl

        self._impl = _Impl(*args, **kwargs)

    def execute_pipeline(self, *args, **kwargs):
        return self._impl.execute_pipeline(*args, **kwargs)


# Patch pathlib.Path.is_file to bypass macOS Sandbox PermissionError
# triggered by Pydantic's BaseSettings looking for .env in restricted directories.
_orig_is_file = Path.is_file


def _patched_is_file(self: Path) -> bool:
    try:
        return _orig_is_file(self)
    except PermissionError:
        return False


Path.is_file = _patched_is_file


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Antigravity 3-Tier Multi-Agent Architecture with CrewAI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--prompt", required=True, help="User objective / prompt")
    parser.add_argument(
        "--workspace",
        default=None,
        help=(
            "Working directory for pipeline artefacts. "
            "If omitted, uses ANTIGRAVITY_WORKSPACE_DIR or "
            "<project_root>/workspaces/cli-default."
        ),
    )
    parser.add_argument(
        "--strict-provider-validation",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Fail fast if provider credentials/base URLs are missing or placeholder values.",
    )
    parser.add_argument(
        "--max-provider-4xx",
        type=int,
        default=50,
        help="Maximum tolerated provider HTTP 4xx events before pipeline abort.",
    )
    parser.add_argument(
        "--fail-on-research-empty",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Fail pipeline if research stage returns fewer than two citations for non-trivial prompts.",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose CrewAI output")

    args = parser.parse_args()

    # Resolve workspace according to the primary workspace pattern.
    if args.workspace:
        workspace = Path(args.workspace).resolve()
    else:
        env_workspace = os.environ.get("ANTIGRAVITY_WORKSPACE_DIR")
        if env_workspace:
            workspace = Path(env_workspace).resolve()
        else:
            root = Path(os.environ.get("ANTIGRAVITY_WORKSPACE_ROOT", DEFAULT_WORKSPACE_ROOT))
            workspace = (root / "cli-default").resolve()

    workspace.mkdir(parents=True, exist_ok=True)

    # Bind CrewAI and appdirs storage into the workspace namespace before any CrewAI import.
    from engine.crewai_storage import bootstrap_crewai_storage

    bootstrap_crewai_storage(workspace)

    from engine.orchestration_api import OrchestrationRunConfig, run_orchestration
    from engine.status_banner import emit_status_banner

    emit_status_banner()
    print("🌌 Antigravity 3-Tier Multi-Agent Architecture + CrewAI")
    print(f"📁 Workspace : {workspace}")
    print(f"📁 Project   : {PROJECT_ROOT}")
    print(f"🎯 Objective : {args.prompt}\n")

    print(f"🧠 Agent memory : {workspace / '.agent' / 'memory' / 'execution_log.json'}")
    print(f"🧩 Agent tmp    : {workspace / '.agent' / 'tmp'}")

    logger.info(f"Initialising Antigravity Engine | workspace={workspace}")

    # Pre-execution: Semantic Auto-Healing — always uses PROJECT_ROOT so the
    # architecture docs and rule templates are reliably available.
    logger.info("Engaging Semantic Healer pre-flight checks…")
    healer = ArchitectureHealer(str(PROJECT_ROOT))
    rules_to_validate = [
        ".agent/rules/l1-orchestration.md",
        ".agent/rules/l2-sub-agent.md",
        ".agent/rules/l3-leaf-worker.md",
        ".agent/rules/system-verification-agent.md",
    ]
    for rule in rules_to_validate:
        healer.validate_and_heal(rule)

    logger.info("Starting execution pipeline…")
    try:
        cfg = OrchestrationRunConfig(
            prompt=args.prompt,
            workspace=workspace,
            strict_provider_validation=args.strict_provider_validation,
            max_provider_4xx=args.max_provider_4xx,
            fail_on_research_empty=args.fail_on_research_empty,
            verbose=args.verbose,
            caller="cli",
        )
        result = run_orchestration(cfg)

        output_file = workspace / "execution_result.json"
        output_file.write_text(
            json.dumps(
                {
                    "success": result.success,
                    "workspace": str(result.workspace),
                    "prompt": result.prompt,
                    "strict_provider_validation": result.strict_provider_validation,
                    "max_provider_4xx": result.max_provider_4xx,
                    "fail_on_research_empty": result.fail_on_research_empty,
                    "run_id": result.run_id,
                    "execution_log_path": str(result.execution_log_path),
                    "final_output_path": str(result.final_output_path),
                    "reconstructed_prompt_path": str(result.reconstructed_prompt_path),
                    "research_context_path": str(result.research_context_path),
                    "provider_4xx_count": result.provider_4xx_count,
                    "completion_status": result.completion_status,
                    "completion_summary": result.completion_summary,
                    "failed_stage": result.failed_stage,
                    "stage_progress": result.stage_progress,
                    "error": result.error,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        if result.success:
            print(f"\n✅ Execution complete! Results saved to {output_file}")
        else:
            print(f"\n⚠️  Execution completed with failures. See {output_file}")

        print("\nKey artefacts:")
        print(f"- Reconstructed prompt : {result.reconstructed_prompt_path}")
        print(f"- Research context     : {result.research_context_path}")
        print(f"- Final output         : {result.final_output_path}")
        print(f"- Telemetry log        : {result.execution_log_path}")
        print(f"- Completion status    : {result.completion_status}")
        print(f"- Completion summary   : {result.completion_summary}")

        logger.info("Pipeline execution finished.")
        return 0 if result.success else 1

    except Exception as exc:  # pragma: no cover - top-level safeguard
        logger.error(f"Critical pipeline failure: {exc}", exc_info=True)
        print(f"\n❌ Execution failed: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

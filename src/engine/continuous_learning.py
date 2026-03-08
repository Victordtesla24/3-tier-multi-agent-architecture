from __future__ import annotations

import json
import statistics
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List


def _load_execution_log(log_path: Path) -> Dict[str, Any]:
    if not log_path.exists():
        return {"executions": []}
    try:
        return json.loads(log_path.read_text(encoding="utf-8"))
    except Exception:
        return {"executions": []}


def _normalize_pipeline_runs(executions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Normalize historical and current execution-log shapes into pipeline runs."""
    runs: List[Dict[str, Any]] = []
    for item in executions:
        if not isinstance(item, dict):
            continue

        if item.get("event") == "PIPELINE_COMPLETE":
            details = item.get("details")
            if isinstance(details, dict):
                normalized = dict(details)
                normalized.setdefault("timestamp", item.get("timestamp"))
                normalized.setdefault("run_id", item.get("run_id"))
                normalized.setdefault("state", item.get("state"))
                runs.append(normalized)
            continue

        if any(key in item for key in ("success", "stage_progress", "failed_stage", "completion_status")):
            normalized = dict(item)
            details = normalized.get("details")
            if isinstance(details, dict):
                for key, value in details.items():
                    normalized.setdefault(key, value)
            runs.append(normalized)

    return runs


def _extract_failure_modes(executions: List[Dict[str, Any]]) -> Counter:
    """Count failure modes by (stage, error_type) across all executions."""
    failures: Counter = Counter()
    for item in executions:
        success = item.get("success")
        completion_status = item.get("completion_status")
        failed_stage = item.get("failed_stage")
        is_failure = (
            success is False
            or completion_status in {"partial", "blocked"}
            or failed_stage is not None
        )
        if is_failure:
            stage = str(failed_stage or item.get("state") or completion_status or "unknown")
            error_type = str(
                item.get("error_type")
                or item.get("error")
                or completion_status
                or "unclassified"
            )[:80]
            failures[(stage, error_type)] += 1
    return failures


def _compute_stage_latencies(executions: List[Dict[str, Any]]) -> Dict[str, List[float]]:
    """Extract per-stage durations from executions that include timing data."""
    latencies: Dict[str, List[float]] = {}
    for item in executions:
        stage_progress = item.get("stage_progress", {})
        if isinstance(stage_progress, dict):
            for stage_name, stage_data in stage_progress.items():
                if isinstance(stage_data, dict) and "duration_s" in stage_data:
                    raw_duration = stage_data["duration_s"]
                    if raw_duration is None:
                        continue
                    duration = float(raw_duration)
                    latencies.setdefault(stage_name, []).append(duration)
    return latencies


def _compute_task_graph_metrics(executions: List[Dict[str, Any]]) -> Dict[str, float]:
    """Aggregate additive task-graph telemetry from normalized pipeline runs."""
    if not executions:
        return {
            "avg_task_count": 0.0,
            "avg_parallel_batch_count": 0.0,
            "avg_worker_retry_count": 0.0,
            "avg_task_failure_count": 0.0,
            "task_graph_runs": 0.0,
            "legacy_fallback_runs": 0.0,
        }

    task_counts: List[float] = []
    batch_counts: List[float] = []
    retry_counts: List[float] = []
    failure_counts: List[float] = []
    task_graph_runs = 0
    legacy_fallback_runs = 0

    for item in executions:
        execution_mode = str(item.get("execution_mode") or "")
        if execution_mode == "task_graph":
            task_graph_runs += 1
        elif execution_mode == "legacy_hierarchical":
            legacy_fallback_runs += 1

        task_counts.append(float(item.get("task_count", 0) or 0))
        batch_counts.append(float(item.get("parallel_batch_count", 0) or 0))
        retry_counts.append(float(item.get("worker_retry_count", 0) or 0))
        failure_counts.append(float(item.get("task_failure_count", 0) or 0))

    divisor = len(executions)
    return {
        "avg_task_count": sum(task_counts) / divisor,
        "avg_parallel_batch_count": sum(batch_counts) / divisor,
        "avg_worker_retry_count": sum(retry_counts) / divisor,
        "avg_task_failure_count": sum(failure_counts) / divisor,
        "task_graph_runs": float(task_graph_runs),
        "legacy_fallback_runs": float(legacy_fallback_runs),
    }


def _generate_recommendations(
    failure_modes: Counter,
    latencies: Dict[str, List[float]],
    total_runs: int,
    task_graph_metrics: Dict[str, float],
) -> List[str]:
    """Generate concrete parameter-adjustment recommendations."""
    recommendations: List[str] = []

    if total_runs == 0:
        recommendations.append("- No executions recorded. Run the pipeline to generate baseline data.")
        return recommendations

    total_failures = sum(failure_modes.values())
    failure_rate = total_failures / max(total_runs, 1)

    if failure_rate > 0.5:
        recommendations.append(
            f"- CRITICAL: {failure_rate:.0%} failure rate across {total_runs} runs. "
            "Review provider credentials and model availability before next execution."
        )

    for (stage, error_type), count in failure_modes.most_common(5):
        pct = count / max(total_runs, 1)
        if "timeout" in error_type.lower() or "timed out" in error_type.lower():
            recommendations.append(
                f"- Stage '{stage}' timed out in {pct:.0%} of runs. "
                "Consider increasing `timeout` in `build_llm()` from 90s to 120s."
            )
        elif "429" in error_type or "rate" in error_type.lower():
            recommendations.append(
                f"- Stage '{stage}' hit rate limits in {pct:.0%} of runs. "
                "Consider increasing backoff base delay or adding a token-bucket rate limiter."
            )
        elif "soft-failure" in error_type.lower() or "cannot fulfill" in error_type.lower():
            recommendations.append(
                f"- Stage '{stage}' returned soft-failure responses in {pct:.0%} of runs. "
                "Review prompt specificity or switch the primary model for this tier."
            )
        elif count >= 3:
            recommendations.append(
                f"- Stage '{stage}' failed {count} times with '{error_type}'. "
                "Investigate root cause and consider adding a targeted pre-check."
            )

    for stage_name, durations in latencies.items():
        if len(durations) >= 3:
            median_s = statistics.median(durations)
            p90_s = sorted(durations)[int(len(durations) * 0.9)]
            if p90_s > 60:
                recommendations.append(
                    f"- Stage '{stage_name}' P90 latency is {p90_s:.1f}s (median {median_s:.1f}s). "
                    "Consider a lower-effort model for this tier or reducing max_reasoning_attempts."
                )

    if task_graph_metrics["legacy_fallback_runs"] > 0:
        fallback_rate = task_graph_metrics["legacy_fallback_runs"] / max(total_runs, 1)
        if fallback_rate >= 0.25:
            recommendations.append(
                f"- Task-graph execution fell back to legacy mode in {fallback_rate:.0%} of runs. "
                "Review planner prompt quality and plan validation failures before widening rollout."
            )

    if task_graph_metrics["avg_worker_retry_count"] >= 1:
        recommendations.append(
            f"- Workers are retrying {task_graph_metrics['avg_worker_retry_count']:.1f} time(s) per run on average. "
            "Tighten task descriptions or strengthen evaluator feedback specificity."
        )

    if not recommendations:
        recommendations.append(
            f"- Pipeline is healthy: {total_runs} runs with {failure_rate:.0%} failure rate. "
            "No parameter adjustments recommended at this time."
        )

    return recommendations


def generate_improvement_proposal(workspace: Path) -> str:
    """Build a structured WHAT/WHY/HOW improvement proposal with failure analysis."""
    workspace = workspace.resolve()
    log_path = workspace / ".agent" / "memory" / "execution_log.json"
    payload = _load_execution_log(log_path)
    raw_executions = payload.get("executions", [])
    if not isinstance(raw_executions, list):
        raw_executions = []
    executions = _normalize_pipeline_runs(raw_executions)

    total_runs = len(executions)
    failure_modes = _extract_failure_modes(executions)
    latencies = _compute_stage_latencies(executions)
    task_graph_metrics = _compute_task_graph_metrics(executions)
    recommendations = _generate_recommendations(
        failure_modes,
        latencies,
        total_runs,
        task_graph_metrics,
    )

    what_lines = [
        f"- Analyzed {total_runs} recorded pipeline execution(s) in this workspace.",
    ]
    if failure_modes:
        what_lines.append(f"- Detected {sum(failure_modes.values())} total failures across {len(failure_modes)} distinct failure modes.")
        for (stage, error_type), count in failure_modes.most_common(5):
            what_lines.append(f"  - [{stage}] {error_type}: {count} occurrence(s)")
    else:
        what_lines.append("- No failures detected in recorded executions.")

    if latencies:
        what_lines.append("- Stage latency summary:")
        for stage_name, durations in sorted(latencies.items()):
            median_s = statistics.median(durations) if durations else 0
            what_lines.append(f"  - {stage_name}: median {median_s:.1f}s across {len(durations)} samples")
    if total_runs:
        what_lines.append(
            "- Task-graph telemetry summary: "
            f"avg tasks/run {task_graph_metrics['avg_task_count']:.1f}, "
            f"avg batches/run {task_graph_metrics['avg_parallel_batch_count']:.1f}, "
            f"avg worker retries/run {task_graph_metrics['avg_worker_retry_count']:.1f}."
        )
        if task_graph_metrics["legacy_fallback_runs"]:
            what_lines.append(
                f"- Legacy fallback runs detected: {int(task_graph_metrics['legacy_fallback_runs'])}."
            )

    why_lines = [
        "- Failure-mode clustering reveals recurring bottlenecks that can be addressed "
        "through targeted parameter tuning rather than architectural changes.",
        "- Stage latency distributions identify tiers where model effort or timeout "
        "adjustments would reduce wall-clock time without sacrificing output quality.",
    ]

    proposal = [
        "# Continuous Improvement Proposal",
        "",
        "## WHAT \u2014 Observed Patterns",
        *what_lines,
        "",
        "## WHY \u2014 Root Cause Analysis",
        *why_lines,
        "",
        "## HOW \u2014 Concrete Recommendations",
        *recommendations,
        "",
    ]
    return "\n".join(proposal)


_EXPECTED_APPROVAL_TOKEN = "AG-APPLY-IMPROVEMENT"


def apply_architecture_upgrade(
    workspace: Path,
    proposal_markdown: str,
    *,
    approval_token: str,
) -> Path | None:
    """Gated application of an architecture improvement proposal.

    The proposal is only persisted if the caller provides the expected approval
    token. This keeps the engine deterministic while allowing the host surface
    (CLI, MCP, or UI) to control when upgrades are accepted.
    """
    if not approval_token or approval_token != _EXPECTED_APPROVAL_TOKEN:
        return None

    workspace = workspace.resolve()
    target = workspace / ".agent" / "memory" / "improvement-notes.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(proposal_markdown, encoding="utf-8")
    return target

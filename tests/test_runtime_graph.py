from __future__ import annotations

import asyncio
import threading
import time
from unittest.mock import patch

import pytest

from engine.crew_orchestrator import CrewAIThreeTierOrchestrator
from engine.project_root_tools import ProjectRootFileReadTool
from engine.runtime_graph import (
    DAGTaskExecutor,
    OrchestrationPlan,
    PlanningFailureError,
    ReflexiveTaskWorker,
    SemanticTaskPlanner,
    TaskGraphExecutionError,
    TaskGraphExecutionSummary,
    TaskStatus,
    WorkerTask,
)
from engine.workflow_primitives import sanitize_user_input


@pytest.fixture(autouse=True)
def mock_env():
    with patch.dict(
        "os.environ",
        {
            "GOOGLE_API_KEY": "dummy_google_key",
            "OPENAI_API_KEY": "dummy_openai_key",
            "OLLAMA_BASE_URL": "http://127.0.0.1:11434",
        },
    ):
        yield


def test_orchestration_plan_rejects_missing_dependency():
    with pytest.raises(ValueError, match="is missing from the plan"):
        OrchestrationPlan(
            original_query="broken",
            tasks=[
                WorkerTask(
                    task_id="task_b",
                    description="depends on missing task",
                    dependencies=["task_a"],
                )
            ],
        )


def test_orchestration_plan_rejects_circular_dependency():
    with pytest.raises(ValueError, match="Circular dependency"):
        OrchestrationPlan(
            original_query="cycle",
            tasks=[
                WorkerTask(
                    task_id="task_a",
                    description="A",
                    dependencies=["task_b"],
                ),
                WorkerTask(
                    task_id="task_b",
                    description="B",
                    dependencies=["task_a"],
                ),
            ],
        )


def test_semantic_task_planner_fast_path_weather():
    planner = SemanticTaskPlanner(llm_planner=lambda _prompt: "")
    plan = planner.create_plan(
        source_prompt="Fetch weather for Melbourne and save to weather.md",
        research_context="unused",
    )

    assert plan.original_query == "Fetch weather for Melbourne and save to weather.md"
    assert [task.task_id for task in plan.tasks] == ["fetch_weather", "save_weather"]
    assert plan.tasks[1].dependencies == ["fetch_weather"]


def test_semantic_task_planner_fast_path_prompt_rewrite():
    planner = SemanticTaskPlanner(llm_planner=lambda _prompt: "")
    plan = planner.create_plan(
        source_prompt=(
            "Rewrite this request into a production-grade prompt: "
            "Draft a concise customer onboarding email for a B2B SaaS product."
        ),
        research_context="unused",
    )

    assert plan.tasks[0].task_id == "rewrite_prompt"
    assert "production-grade prompt" in plan.tasks[0].description
    assert "Do not return a prompt-engineering framework" in plan.tasks[0].description
    assert (
        plan.global_context["input_data"]
        == "Draft a concise customer onboarding email for a B2B SaaS product."
    )


def test_semantic_task_planner_fast_path_prompt_rewrite_from_wrapped_prompt():
    planner = SemanticTaskPlanner(llm_planner=lambda _prompt: "")
    plan = planner.create_plan(
        source_prompt="""```markdown
# Prompt Wrapper

## Input Data
`<input_data>`
Rewrite this request into a production-grade prompt: Draft a concise customer onboarding email for a B2B SaaS product.
`</input_data>`
```""",
        research_context="unused",
    )

    assert plan.tasks[0].task_id == "rewrite_prompt"
    assert plan.global_context["input_data"] == (
        "Draft a concise customer onboarding email for a B2B SaaS product."
    )


def test_sanitize_user_input_extracts_markdown_input_data_block():
    raw_prompt = """```markdown
# Prompt Wrapper

## Input Data
```
Rewrite this request into a production-grade prompt: Draft a concise customer onboarding email for a B2B SaaS product.
```
```"""

    assert sanitize_user_input(raw_prompt) == (
        "Rewrite this request into a production-grade prompt: "
        "Draft a concise customer onboarding email for a B2B SaaS product."
    )


def test_sanitize_user_input_extracts_backticked_input_data_tags():
    raw_prompt = """## Input Data
`<input_data>`
Rewrite this request into a production-grade prompt: Draft a concise customer onboarding email for a B2B SaaS product.
`</input_data>`
"""

    assert sanitize_user_input(raw_prompt) == (
        "Rewrite this request into a production-grade prompt: "
        "Draft a concise customer onboarding email for a B2B SaaS product."
    )


def test_semantic_task_planner_cleans_json_fences():
    planner = SemanticTaskPlanner(
        llm_planner=lambda _prompt: """```json
{
  "original_query": "ship feature",
  "tasks": [
    {
      "task_id": "analyse",
      "description": "Analyse repository state",
      "dependencies": [],
      "required_tools": ["project_root_file_read"]
    }
  ]
}
```"""
    )
    plan = planner.create_plan(
        source_prompt="ship feature",
        research_context="## Summary\n- ok\n",
    )

    assert plan.original_query == "ship feature"
    assert plan.tasks[0].task_id == "analyse"


def test_semantic_task_planner_rejects_malformed_json():
    planner = SemanticTaskPlanner(llm_planner=lambda _prompt: "not json")

    with pytest.raises(PlanningFailureError, match="JSON object"):
        planner.create_plan(source_prompt="ship feature", research_context="unused")


def test_project_root_tool_reads_reports_and_benchmarks(tmp_path):
    report_path = tmp_path / "docs" / "reports" / "summary.md"
    benchmark_path = tmp_path / "docs" / "benchmarks" / "latest_results.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    benchmark_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("report-ok", encoding="utf-8")
    benchmark_path.write_text("benchmark-ok", encoding="utf-8")

    reader = ProjectRootFileReadTool(project_root=str(tmp_path))

    assert reader._run("docs/reports/summary.md") == "report-ok"
    assert reader._run("docs/benchmarks/latest_results.md") == "benchmark-ok"


def test_dag_executor_runs_parallel_batches():
    plan = OrchestrationPlan(
        original_query="parallel",
        tasks=[
            WorkerTask(task_id="task_a", description="A"),
            WorkerTask(task_id="task_b", description="B"),
            WorkerTask(
                task_id="task_c",
                description="C",
                dependencies=["task_a", "task_b"],
            ),
        ],
    )
    events: list[tuple[str, dict[str, object]]] = []

    async def dispatcher(task: WorkerTask, _context: dict[str, object]) -> WorkerTask:
        await asyncio.sleep(0.01)
        task.status = TaskStatus.COMPLETED
        task.result = f"result::{task.task_id}"
        task.attempt_count = 1
        return task

    summary = DAGTaskExecutor(
        worker_dispatcher=dispatcher,
        event_sink=lambda event_type, details: events.append((event_type, details)),
    ).execute_plan_sync(plan)

    assert summary.parallel_batch_count == 2
    assert summary.started_execution is True
    assert summary.global_context["task_task_c_result"] == "result::task_c"
    batch_events = [details for event, details in events if event == "TASK_GRAPH_BATCH_STARTED"]
    assert batch_events[0]["task_ids"] == ["task_a", "task_b"]
    assert batch_events[1]["task_ids"] == ["task_c"]


def test_dag_executor_caps_parallel_batches():
    plan = OrchestrationPlan(
        original_query="parallel-capped",
        tasks=[
            WorkerTask(task_id="task_a", description="A"),
            WorkerTask(task_id="task_b", description="B"),
            WorkerTask(task_id="task_c", description="C"),
            WorkerTask(task_id="task_d", description="D"),
            WorkerTask(task_id="task_e", description="E"),
        ],
    )
    events: list[tuple[str, dict[str, object]]] = []

    async def dispatcher(task: WorkerTask, _context: dict[str, object]) -> WorkerTask:
        await asyncio.sleep(0.01)
        task.status = TaskStatus.COMPLETED
        task.result = f"result::{task.task_id}"
        task.attempt_count = 1
        return task

    summary = DAGTaskExecutor(
        worker_dispatcher=dispatcher,
        event_sink=lambda event_type, details: events.append((event_type, details)),
        max_parallel_tasks=3,
    ).execute_plan_sync(plan)

    assert summary.parallel_batch_count == 2
    batch_events = [details for event, details in events if event == "TASK_GRAPH_BATCH_STARTED"]
    assert batch_events[0]["task_ids"] == ["task_a", "task_b", "task_c"]
    assert batch_events[1]["task_ids"] == ["task_d", "task_e"]


def test_dag_executor_enforces_timeout():
    """Verify that a hanging worker task is bounded by task_timeout_seconds and yields TaskStatus.FAILED."""
    plan = OrchestrationPlan(
        original_query="timeout test",
        tasks=[
            WorkerTask(task_id="slow_task", description="Simulated infinite hang"),
        ],
    )

    async def hanging_dispatcher(task: WorkerTask, _context: dict[str, object]) -> WorkerTask:
        await asyncio.sleep(9999)
        task.status = TaskStatus.COMPLETED
        task.result = "should never reach"
        return task

    with pytest.raises(TaskGraphExecutionError) as exc_info:
        DAGTaskExecutor(
            worker_dispatcher=hanging_dispatcher,
            task_timeout_seconds=0.05,
        ).execute_plan_sync(plan)

    assert exc_info.value.started_execution is True
    assert "failed after" in str(exc_info.value)


def test_dag_executor_rejects_deadlock_before_work_starts():
    invalid_plan = OrchestrationPlan.model_construct(
        plan_id="deadlock-plan",
        original_query="deadlock",
        tasks=[
            WorkerTask.model_construct(
                task_id="task_a",
                description="A",
                dependencies=["missing"],
                required_tools=[],
                status=TaskStatus.PENDING,
                result=None,
                error_log=None,
                attempt_count=0,
            )
        ],
        global_context={},
    )

    async def dispatcher(task: WorkerTask, _context: dict[str, object]) -> WorkerTask:
        task.status = TaskStatus.COMPLETED
        task.result = "unused"
        return task

    with pytest.raises(TaskGraphExecutionError) as exc_info:
        DAGTaskExecutor(worker_dispatcher=dispatcher).execute_plan_sync(invalid_plan)

    assert exc_info.value.started_execution is False


def test_reflexive_worker_retries_until_pass():
    attempts: list[int] = []

    def execution_runner(task: WorkerTask, context: dict[str, object]) -> str:
        attempts.append(task.attempt_count)
        return f"candidate::{task.attempt_count}::{context.get('qa_feedback')}"

    def evaluation_runner(task: WorkerTask, _candidate_output: str, _context: dict[str, object]) -> str:
        return "PASS" if task.attempt_count >= 2 else "FAIL: be more specific"

    task = WorkerTask(task_id="task_a", description="A")
    result = asyncio.run(
        ReflexiveTaskWorker(
            execution_runner=execution_runner,
            evaluation_runner=evaluation_runner,
        ).execute_task(task, {})
    )

    assert result.status == TaskStatus.COMPLETED
    assert result.attempt_count == 2
    assert attempts == [1, 2]


def test_reflexive_worker_marks_failure_after_retry_exhaustion():
    task = WorkerTask(task_id="task_a", description="A")
    result = asyncio.run(
        ReflexiveTaskWorker(
            execution_runner=lambda _task, _context: "candidate",
            evaluation_runner=lambda _task, _candidate_output, _context: "FAIL: still wrong",
            max_retries=2,
        ).execute_task(task, {})
    )

    assert result.status == TaskStatus.FAILED
    assert result.attempt_count == 2
    assert "failed QA" in str(result.error_log)


def test_level2_evaluation_semaphore_limits_concurrency():
    orchestrator = CrewAIThreeTierOrchestrator.__new__(CrewAIThreeTierOrchestrator)
    orchestrator._level2_evaluator_semaphore = asyncio.Semaphore(2)

    lock = threading.Lock()
    active = 0
    max_active = 0

    def fake_eval(*, task: WorkerTask, candidate_output: str, task_context: dict[str, object]) -> str:
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.03)
        with lock:
            active -= 1
        return f"PASS::{task.task_id}::{candidate_output}::{task_context!r}"

    orchestrator._evaluate_task_graph_worker_output = fake_eval

    async def run() -> list[str]:
        return await asyncio.gather(
            *[
                orchestrator._evaluate_task_graph_worker_output_bounded(
                    task=WorkerTask(task_id=f"task_{index}", description=f"Task {index}"),
                    candidate_output="candidate",
                    task_context={},
                )
                for index in range(5)
            ]
        )

    results = asyncio.run(run())

    assert len(results) == 5
    assert max_active == 2


def test_execute_prefers_task_graph_path_and_writes_final_output(tmp_path, monkeypatch):
    monkeypatch.setattr("engine.crew_orchestrator._MODULE_PROJECT_ROOT", tmp_path)
    orchestrator = CrewAIThreeTierOrchestrator(workspace_dir=str(tmp_path), verbose=False)
    plan = OrchestrationPlan(
        plan_id="plan-123",
        original_query="ship feature",
        tasks=[WorkerTask(task_id="task_a", description="A")],
    )
    completed_task = WorkerTask(
        task_id="task_a",
        description="A",
        status=TaskStatus.COMPLETED,
        result="task result",
        attempt_count=1,
    )
    summary = TaskGraphExecutionSummary(
        plan_id=plan.plan_id,
        completed_tasks=[completed_task],
        parallel_batch_count=1,
        worker_retry_count=0,
        task_failure_count=0,
        started_execution=True,
    )

    monkeypatch.setattr(orchestrator, "_plan_execution_graph", lambda **_kwargs: plan)
    monkeypatch.setattr(orchestrator, "_execute_task_graph", lambda **_kwargs: summary)
    monkeypatch.setattr(
        orchestrator,
        "_synthesise_task_graph_output",
        lambda **_kwargs: "task graph result",
    )
    monkeypatch.setattr(
        orchestrator,
        "_execute_hierarchical_legacy",
        lambda **_kwargs: pytest.fail("legacy path should not be used"),
    )

    result = orchestrator.execute("reconstructed prompt", "research context", "ctx")

    assert result == "task graph result"
    assert (tmp_path / ".agent" / "tmp" / "final_output.md").read_text(encoding="utf-8") == "task graph result"


def test_task_graph_worker_normalizes_generic_read_tools_and_reroutes_off_ollama(
    tmp_path, monkeypatch
):
    monkeypatch.setattr("engine.crew_orchestrator._MODULE_PROJECT_ROOT", tmp_path)
    orchestrator = CrewAIThreeTierOrchestrator(workspace_dir=str(tmp_path), verbose=False)
    worker_tools = orchestrator._build_worker_tools()
    task = WorkerTask(
        task_id="collect_architecture_inputs",
        description="Load docs/architecture/* and docs/reports/* sources.",
        required_tools=["filesystem_read"],
    )

    selected_tools = orchestrator._select_worker_tools_for_task(
        task=task,
        worker_tools=worker_tools,
    )
    selected_names = [tool.name for tool in selected_tools]
    execution_tier = orchestrator._select_task_graph_worker_tier(
        worker_tools=selected_tools,
    )

    assert selected_names == ["project_root_file_read", "workspace_file_read"]
    assert not str(getattr(execution_tier.primary, "model", "")).startswith("ollama/")


def test_task_graph_worker_keeps_l3_tier_for_toolless_tasks(tmp_path, monkeypatch):
    monkeypatch.setattr("engine.crew_orchestrator._MODULE_PROJECT_ROOT", tmp_path)
    orchestrator = CrewAIThreeTierOrchestrator(workspace_dir=str(tmp_path), verbose=False)

    execution_tier = orchestrator._select_task_graph_worker_tier(worker_tools=[])

    assert execution_tier is orchestrator.models.level3


def test_task_graph_worker_uses_minimal_default_tools_when_required_tools_missing(
    tmp_path, monkeypatch
):
    monkeypatch.setattr("engine.crew_orchestrator._MODULE_PROJECT_ROOT", tmp_path)
    orchestrator = CrewAIThreeTierOrchestrator(workspace_dir=str(tmp_path), verbose=False)
    worker_tools = orchestrator._build_worker_tools()
    task = WorkerTask(
        task_id="tooling_fallback",
        description="Run with omitted required_tools.",
        required_tools=[],
    )

    selected_tools = orchestrator._select_worker_tools_for_task(
        task=task,
        worker_tools=worker_tools,
    )
    selected_names = [tool.name for tool in selected_tools]

    assert selected_names == [
        "workspace_file_read",
        "workspace_file_write",
        "complete_task",
    ]


def test_execute_falls_back_to_legacy_when_planning_fails(tmp_path, monkeypatch):
    events: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr("engine.crew_orchestrator._MODULE_PROJECT_ROOT", tmp_path)
    orchestrator = CrewAIThreeTierOrchestrator(
        workspace_dir=str(tmp_path),
        verbose=False,
        telemetry_hook=lambda event_type, details: events.append((event_type, details)),
    )

    monkeypatch.setattr(
        orchestrator,
        "_plan_execution_graph",
        lambda **_kwargs: (_ for _ in ()).throw(PlanningFailureError("planner failed")),
    )

    def legacy(**_kwargs: object) -> str:
        orchestrator._emit_telemetry(
            "EXECUTION_MODE_SELECTED",
            {"execution_mode": "legacy_hierarchical"},
        )
        return "legacy result"

    monkeypatch.setattr(orchestrator, "_execute_hierarchical_legacy", legacy)

    result = orchestrator.execute("reconstructed prompt", "research context", "ctx")

    assert result == "legacy result"
    assert any(event == "EXECUTION_MODE_FALLBACK" for event, _details in events)
    assert any(
        event == "EXECUTION_MODE_SELECTED"
        and details.get("execution_mode") == "legacy_hierarchical"
        for event, details in events
    )


def test_execute_short_circuits_direct_clarification(tmp_path, monkeypatch):
    events: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr("engine.crew_orchestrator._MODULE_PROJECT_ROOT", tmp_path)
    orchestrator = CrewAIThreeTierOrchestrator(
        workspace_dir=str(tmp_path),
        verbose=False,
        telemetry_hook=lambda event_type, details: events.append((event_type, details)),
    )

    monkeypatch.setattr(
        orchestrator,
        "_plan_execution_graph",
        lambda **_kwargs: pytest.fail("task graph should not be planned"),
    )
    monkeypatch.setattr(
        orchestrator,
        "_execute_hierarchical_legacy",
        lambda **_kwargs: pytest.fail("legacy path should not be used"),
    )

    reconstructed_prompt = (
        "- What is the complete and exact <input_data> content to reconstruct into the "
        "production-grade system prompt?"
    )
    research_context = (
        "## Summary\n"
        "- Missing required task inputs.\n\n"
        "## Citations[]\n"
        "- None\n\n"
        "## MissingConfig[]\n"
        "- The exact <input_data> content to reconstruct.\n\n"
        "## RiskNotes[]\n"
        "- Proceeding would fabricate requirements.\n"
    )

    result = orchestrator.execute(reconstructed_prompt, research_context, "ctx")

    assert result == reconstructed_prompt
    assert (tmp_path / ".agent" / "tmp" / "final_output.md").read_text(
        encoding="utf-8"
    ) == reconstructed_prompt
    assert any(
        event == "EXECUTION_MODE_SELECTED"
        and details.get("execution_mode") == "direct_clarification"
        for event, details in events
    )

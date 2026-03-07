from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from engine.crew_orchestrator import CrewAIThreeTierOrchestrator
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


@pytest.fixture(autouse=True)
def mock_env():
    with patch.dict(
        "os.environ",
        {
            "GOOGLE_API_KEY": "dummy_google_key",
            "OPENAI_API_KEY": "dummy_openai_key",
            "MINIMAX_API_KEY": "dummy_minimax_key",
            "DEEPSEEK_API_KEY": "dummy_deepseek_key",
            "MINIMAX_BASE_URL": "https://dummy.minimax.api",
            "DEEPSEEK_BASE_URL": "https://dummy.deepseek.api",
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


def test_execute_prefers_task_graph_path_and_writes_final_output(tmp_path, monkeypatch):
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


def test_execute_falls_back_to_legacy_when_planning_fails(tmp_path, monkeypatch):
    events: list[tuple[str, dict[str, object]]] = []
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

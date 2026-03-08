from __future__ import annotations

import asyncio
import inspect
import json
import re
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Awaitable, Callable

from pydantic import BaseModel, Field, field_validator, model_validator


class AgentRole(str, Enum):
    ROUTER = "router"
    ORCHESTRATOR = "orchestrator"
    WORKER = "worker"
    EVALUATOR = "evaluator"


class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class MessagePayload(BaseModel):
    """Strict envelope for inter-agent messaging inside the hardened runtime."""

    message_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    sender: AgentRole
    receiver: AgentRole
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkerTask(BaseModel):
    """Discrete executable unit within the internal task graph."""

    task_id: str
    description: str
    dependencies: list[str] = Field(default_factory=list)
    required_tools: list[str] = Field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    result: str | None = None
    error_log: str | None = None
    attempt_count: int = 0


class OrchestrationPlan(BaseModel):
    """Validated internal task plan used by the DAG executor."""

    plan_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    original_query: str
    tasks: list[WorkerTask]
    global_context: dict[str, Any] = Field(default_factory=dict)

    @field_validator("tasks")
    @classmethod
    def _validate_tasks(cls, tasks: list[WorkerTask]) -> list[WorkerTask]:
        if not tasks:
            raise ValueError("OrchestrationPlan requires at least one task.")

        seen: set[str] = set()
        duplicates: list[str] = []
        for task in tasks:
            if task.task_id in seen:
                duplicates.append(task.task_id)
            seen.add(task.task_id)

        if duplicates:
            duplicate_list = ", ".join(sorted(set(duplicates)))
            raise ValueError(f"Duplicate task IDs detected: {duplicate_list}.")

        for task in tasks:
            for dependency in task.dependencies:
                if dependency not in seen:
                    raise ValueError(
                        f"Dependency '{dependency}' referenced by task '{task.task_id}' "
                        "is missing from the plan."
                    )
        return tasks

    @model_validator(mode="after")
    def _validate_acyclic(self) -> "OrchestrationPlan":
        graph = {task.task_id: list(task.dependencies) for task in self.tasks}
        visited: set[str] = set()
        path: set[str] = set()

        def visit(node: str) -> None:
            if node in path:
                raise ValueError(
                    f"Circular dependency detected involving task '{node}'."
                )
            if node in visited:
                return
            visited.add(node)
            path.add(node)
            for dependency in graph.get(node, []):
                visit(dependency)
            path.remove(node)

        for task_id in graph:
            visit(task_id)
        return self


class TaskGraphExecutionSummary(BaseModel):
    plan_id: str
    execution_mode: str = "task_graph"
    completed_tasks: list[WorkerTask]
    global_context: dict[str, Any] = Field(default_factory=dict)
    parallel_batch_count: int = 0
    worker_retry_count: int = 0
    task_failure_count: int = 0
    started_execution: bool = False


class PlanningFailureError(RuntimeError):
    """Raised when a semantic execution plan cannot be produced or validated."""


class TaskGraphExecutionError(RuntimeError):
    """Raised when the DAG executor cannot complete the current task graph."""

    def __init__(self, message: str, *, started_execution: bool):
        super().__init__(message)
        self.started_execution = started_execution


def extract_json_payload(raw: str) -> str:
    """Return the first JSON object found in a planner response."""

    cleaned = raw.strip().replace("```json", "").replace("```", "").strip()
    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if match is None:
        raise PlanningFailureError("Planner response did not contain a JSON object.")
    return match.group(0)


class SemanticTaskPlanner:
    """Construct dependency-validated task graphs from prompt and research context."""

    def __init__(self, llm_planner: Callable[[str], str]):
        self._llm_planner = llm_planner

    def _apply_fast_path(self, source_prompt: str) -> OrchestrationPlan | None:
        """
        Dynamically route recognized prompt patterns to pre-compiled plans bypassing LLM reasoning overhead.
        Extensible registry iterates over strict corporate intents to yield deterministically bounded task graphs.
        """
        prompt = " ".join(source_prompt.split()).strip()

        # Extensible intent registry mapping optimized regex payload to completely compiled Task Graphs
        intent_registry: list[dict[str, Any]] = [
            {
                "pattern": re.compile(r"^fetch weather for (?P<city>[a-zA-Z\s]+) and save to (?P<file>[\w.\-/]+)$", flags=re.IGNORECASE),
                "plan_builder": lambda match: OrchestrationPlan(
                    original_query=prompt,
                    tasks=[
                        WorkerTask(
                            task_id="fetch_weather",
                            description=f"Fetch the latest weather for {match.group('city').strip()}.",
                            required_tools=["weather_api"],
                        ),
                        WorkerTask(
                            task_id="save_weather",
                            description=f"Save the weather report to {match.group('file').strip()}.",
                            dependencies=["fetch_weather"],
                            required_tools=["workspace_file_write"],
                        ),
                    ],
                )
            }
            # System developers may seamlessly append deployment, build, and CI hooks directly into the array here
        ]

        for intent in intent_registry:
            match = intent["pattern"].match(prompt)
            if match is not None:
                try:
                    return intent["plan_builder"](match)
                except Exception:
                    # In extreme failure modes, gracefully degrade back to the core LLM execution planner
                    return None

        return None

    def create_plan(
        self,
        *,
        source_prompt: str,
        research_context: str,
        context_block: str | None = None,
    ) -> OrchestrationPlan:
        fast_path = self._apply_fast_path(source_prompt)
        if fast_path is not None:
            return fast_path

        planner_prompt = (
            "Build an internal execution plan for the Antigravity runtime.\n\n"
            "Return JSON only using this exact schema:\n"
            "{\n"
            '  "original_query": "string",\n'
            '  "tasks": [\n'
            "    {\n"
            '      "task_id": "snake_case_id",\n'
            '      "description": "atomic outcome",\n'
            '      "dependencies": ["task_id"],\n'
            '      "required_tools": ["tool_name"]\n'
            "    }\n"
            "  ]\n"
            "}\n\n"
            "Rules:\n"
            "- Create between 1 and 6 tasks.\n"
            "- Prefer parallelizable tasks where dependencies are not required.\n"
            "- Use only explicit dependencies.\n"
            "- Each task must be atomic and execution-ready.\n"
            "- Do not emit markdown fences or commentary.\n\n"
            f"Source Prompt:\n{source_prompt}\n\n"
            f"Research Context:\n{research_context}\n\n"
            f"Runtime Context:\n{context_block or 'No additional runtime context.'}\n"
        )

        raw_response = self._llm_planner(planner_prompt)
        try:
            payload = json.loads(extract_json_payload(raw_response))
        except json.JSONDecodeError as exc:
            raise PlanningFailureError(
                f"Planner returned malformed JSON: {exc}"
            ) from exc

        if "original_query" not in payload:
            payload["original_query"] = source_prompt

        try:
            return OrchestrationPlan.model_validate(payload)
        except Exception as exc:  # pragma: no cover - exercised via tests
            raise PlanningFailureError(str(exc)) from exc


ExecutionRunner = Callable[[WorkerTask, dict[str, Any]], Awaitable[str] | str]
EvaluationRunner = Callable[[WorkerTask, str, dict[str, Any]], Awaitable[str] | str]
TaskEventSink = Callable[[str, dict[str, Any]], None]


async def _resolve(value: Awaitable[str] | str) -> str:
    if inspect.isawaitable(value):
        return str(await value)
    return str(value)


async def _invoke_runner(
    runner: Callable[..., Awaitable[str] | str],
    *args: Any,
) -> str:
    if inspect.iscoroutinefunction(runner):
        return await _resolve(runner(*args))
    result = await asyncio.to_thread(runner, *args)
    return await _resolve(result)


class ReflexiveTaskWorker:
    """Execute and validate atomic tasks with bounded self-correction."""

    def __init__(
        self,
        *,
        execution_runner: ExecutionRunner,
        evaluation_runner: EvaluationRunner,
        max_retries: int = 3,
    ):
        self.execution_runner = execution_runner
        self.evaluation_runner = evaluation_runner
        self.max_retries = max_retries

    async def execute_task(
        self,
        task: WorkerTask,
        context: dict[str, Any],
    ) -> WorkerTask:
        import random

        current_result = ""
        qa_feedback = ""
        base_backoff_seconds = 2.0

        while task.attempt_count < self.max_retries:
            task.attempt_count += 1
            attempt_context = dict(context)
            attempt_context["previous_result"] = current_result
            attempt_context["qa_feedback"] = qa_feedback

            try:
                current_result = (
                    await _invoke_runner(self.execution_runner, task, attempt_context)
                ).strip()
                evaluation = (
                    await _invoke_runner(
                        self.evaluation_runner,
                        task,
                        current_result,
                        attempt_context,
                    )
                ).strip()

                if evaluation.upper().startswith("PASS"):
                    task.result = current_result
                    task.status = TaskStatus.COMPLETED
                    task.error_log = None
                    return task

                qa_feedback = evaluation
                task.error_log = (
                    f"Attempt {task.attempt_count} failed QA: {qa_feedback}"
                )
            except Exception as exc:
                task.error_log = (
                    f"Attempt {task.attempt_count} exception: "
                    f"{type(exc).__name__}: {exc}"
                )
                qa_feedback = task.error_log

            # Apply decoupled asynchronous exponential backoff + jitter prior to engaging internal retry
            if task.attempt_count < self.max_retries:
                # Add fractional randomized jitter between 0.1 to 1.5 seconds to strictly offset rate synchronization
                jitter = random.uniform(0.1, 1.5)
                backoff_time = (base_backoff_seconds ** task.attempt_count) + jitter
                await asyncio.sleep(backoff_time)

        task.status = TaskStatus.FAILED
        return task


class DAGTaskExecutor:
    """Execute an OrchestrationPlan in dependency-respecting parallel batches."""

    def __init__(
        self,
        *,
        worker_dispatcher: Callable[[WorkerTask, dict[str, Any]], Awaitable[WorkerTask]],
        event_sink: TaskEventSink | None = None,
        task_timeout_seconds: float = 300.0,
        max_parallel_tasks: int | None = None,
    ):
        self.worker_dispatcher = worker_dispatcher
        self.event_sink = event_sink
        self.task_timeout_seconds = task_timeout_seconds
        self.max_parallel_tasks = max_parallel_tasks

    def _emit(self, event_type: str, details: dict[str, Any]) -> None:
        if self.event_sink is None:
            return
        try:
            self.event_sink(event_type, details)
        except Exception:
            return

    async def execute_plan(
        self,
        plan: OrchestrationPlan,
        *,
        initial_context: dict[str, Any] | None = None,
    ) -> TaskGraphExecutionSummary:
        pending = {
            task.task_id: task.model_copy(deep=True)
            for task in plan.tasks
        }
        completed: dict[str, WorkerTask] = {}
        global_context = dict(plan.global_context)
        global_context.update(initial_context or {})
        global_context.setdefault("plan_id", plan.plan_id)

        batch_count = 0
        retry_count = 0
        task_failure_count = 0
        started_execution = False

        while pending:
            ready = [
                task
                for task in pending.values()
                if all(
                    dependency in completed
                    and completed[dependency].status == TaskStatus.COMPLETED
                    for dependency in task.dependencies
                )
            ]

            if not ready:
                raise TaskGraphExecutionError(
                    "Deadlock detected: pending tasks remain but none are runnable.",
                    started_execution=started_execution,
                )

            chunk_size = self.max_parallel_tasks or len(ready)
            if chunk_size <= 0:
                chunk_size = len(ready)

            for index in range(0, len(ready), chunk_size):
                ready_chunk = ready[index : index + chunk_size]
                batch_count += 1
                started_execution = True
                for task in ready_chunk:
                    pending.pop(task.task_id, None)
                    task.status = TaskStatus.IN_PROGRESS

                self._emit(
                    "TASK_GRAPH_BATCH_STARTED",
                    {
                        "plan_id": plan.plan_id,
                        "batch_index": batch_count,
                        "task_ids": [task.task_id for task in ready_chunk],
                    },
                )

                async def _run_with_timeout(ds_task: WorkerTask, ds_context: dict[str, Any]) -> WorkerTask:
                    try:
                        return await asyncio.wait_for(
                            self.worker_dispatcher(ds_task, ds_context),
                            timeout=self.task_timeout_seconds,
                        )
                    except asyncio.TimeoutError:
                        ds_task.status = TaskStatus.FAILED
                        ds_task.error_log = (
                            f"Task exceeded {self.task_timeout_seconds}s timeout boundary."
                        )
                        ds_task.attempt_count += 1
                        return ds_task

                results = await asyncio.gather(
                    *[
                        _run_with_timeout(
                            task,
                            {
                                "global": dict(global_context),
                                "dependency_results": {
                                    dependency: completed[dependency].result
                                    for dependency in task.dependencies
                                },
                            },
                        )
                        for task in ready_chunk
                    ],
                    return_exceptions=True,
                )

                for task, result in zip(ready_chunk, results):
                    if isinstance(result, BaseException):
                        task_failure_count += 1
                        raise TaskGraphExecutionError(
                            f"Task '{task.task_id}' raised an unhandled exception: {result}",
                            started_execution=started_execution,
                        ) from result

                    worker_result: WorkerTask = result
                    retry_count += max(worker_result.attempt_count - 1, 0)
                    completed[worker_result.task_id] = worker_result
                    if worker_result.result is not None:
                        global_context[f"task_{worker_result.task_id}_result"] = worker_result.result

                    self._emit(
                        "TASK_EXECUTION_RESULT",
                        {
                            "plan_id": plan.plan_id,
                            "task_id": worker_result.task_id,
                            "status": worker_result.status.value,
                            "attempt_count": worker_result.attempt_count,
                            "error_log": worker_result.error_log,
                        },
                    )

                    if worker_result.status != TaskStatus.COMPLETED:
                        task_failure_count += 1
                        raise TaskGraphExecutionError(
                            f"Task '{worker_result.task_id}' failed after {worker_result.attempt_count} attempt(s).",
                            started_execution=started_execution,
                        )

                self._emit(
                    "TASK_GRAPH_BATCH_COMPLETED",
                    {
                        "plan_id": plan.plan_id,
                        "batch_index": batch_count,
                        "task_ids": [task.task_id for task in ready_chunk],
                        "completed_task_count": len(completed),
                    },
                )

        return TaskGraphExecutionSummary(
            plan_id=plan.plan_id,
            completed_tasks=[completed[task.task_id] for task in plan.tasks],
            global_context=global_context,
            parallel_batch_count=batch_count,
            worker_retry_count=retry_count,
            task_failure_count=task_failure_count,
            started_execution=started_execution,
        )

    def execute_plan_sync(
        self,
        plan: OrchestrationPlan,
        *,
        initial_context: dict[str, Any] | None = None,
    ) -> TaskGraphExecutionSummary:
        """Run the DAG executor synchronously, safely handling pre-existing event loops.

        Uses asyncio.run() when no loop is running. Falls back to a dedicated
        thread when called from within an active event loop (e.g., Jupyter,
        async web servers, MCP handlers).
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is None:
            return asyncio.run(
                self.execute_plan(plan, initial_context=initial_context)
            )

        import concurrent.futures

        def _run_in_thread() -> TaskGraphExecutionSummary:
            return asyncio.run(
                self.execute_plan(plan, initial_context=initial_context)
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_run_in_thread)
            return future.result()

"""Scheduler runtime for V3.2 Phase 2.

Provides controlled delayed, recurring, and interval task scheduling.
Single-process, interpretable semantics only.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from app.v3.contracts.agent_message_contracts import AgentMessage, AgentMessageType
from app.v3.contracts.event_contracts import EventType, V3Event
from app.v3.contracts.execution_contracts import ExecutionNode
from app.v3.contracts.scheduler_contracts import ScheduledTask, TaskPriority, TaskStatus, TaskType
from app.v3.contracts.skill_contracts import SkillInput
from app.v3.events.event_bus import EventBus
from app.v3.events.event_store import EventStore
from app.v3.runtime.skill_executor import SkillExecutor


class SchedulerRuntime:
    """Controlled scheduler for delayed, recurring, and interval tasks.

    Single-process, single-threaded, interpretable scheduling semantics.
    Not distributed. Not multi-node. Not leader-election based.
    """

    def __init__(
        self,
        skill_executor: SkillExecutor,
        run_id: str,
        event_bus: EventBus | None = None,
        event_store: EventStore | None = None,
        execution_nodes: list[ExecutionNode] | None = None,
        messages: list[AgentMessage] | None = None,
    ) -> None:
        self.skill_executor = skill_executor
        self.run_id = run_id
        self.event_bus = event_bus
        self.event_store = event_store
        self.execution_nodes = execution_nodes
        self.messages = messages

        self._tasks: list[ScheduledTask] = []
        self._running = False

    @property
    def tasks(self) -> list[ScheduledTask]:
        return list(self._tasks)

    def get_task(self, task_id: str) -> ScheduledTask | None:
        for task in self._tasks:
            if task.task_id == task_id:
                return task
        return None

    def list_tasks_by_status(self, status: TaskStatus) -> list[ScheduledTask]:
        return [t for t in self._tasks if t.status == status]

    def list_tasks_by_type(self, task_type: TaskType) -> list[ScheduledTask]:
        return [t for t in self._tasks if t.task_type == task_type]

    def schedule_delayed(
        self,
        *,
        target_skill_name: str,
        payload: dict[str, Any] | None = None,
        reason: str = "",
        delay_seconds: float = 0.0,
        priority: TaskPriority = TaskPriority.NORMAL,
        metadata: dict[str, Any] | None = None,
    ) -> ScheduledTask:
        schedule_at = datetime.now(UTC) + timedelta(seconds=delay_seconds)
        task = ScheduledTask(
            run_id=self.run_id,
            task_type=TaskType.DELAYED,
            priority=priority,
            status=TaskStatus.SCHEDULED,
            target_skill_name=target_skill_name,
            payload=payload or {},
            reason=reason,
            schedule_at=schedule_at,
            metadata=metadata or {},
        )
        self._tasks.append(task)
        return task

    def schedule_recurring(
        self,
        *,
        target_skill_name: str,
        payload: dict[str, Any] | None = None,
        reason: str = "",
        interval_seconds: float,
        max_repeats: int | None = None,
        priority: TaskPriority = TaskPriority.NORMAL,
        metadata: dict[str, Any] | None = None,
    ) -> ScheduledTask:
        task = ScheduledTask(
            run_id=self.run_id,
            task_type=TaskType.RECURRING,
            priority=priority,
            status=TaskStatus.SCHEDULED,
            target_skill_name=target_skill_name,
            payload=payload or {},
            reason=reason,
            interval_seconds=interval_seconds,
            max_repeats=max_repeats,
            metadata=metadata or {},
        )
        self._tasks.append(task)
        return task

    def schedule_interval(
        self,
        *,
        target_skill_name: str,
        payload: dict[str, Any] | None = None,
        reason: str = "",
        interval_seconds: float,
        max_repeats: int | None = None,
        priority: TaskPriority = TaskPriority.NORMAL,
        metadata: dict[str, Any] | None = None,
    ) -> ScheduledTask:
        task = ScheduledTask(
            run_id=self.run_id,
            task_type=TaskType.INTERVAL,
            priority=priority,
            status=TaskStatus.SCHEDULED,
            target_skill_name=target_skill_name,
            payload=payload or {},
            reason=reason,
            interval_seconds=interval_seconds,
            max_repeats=max_repeats,
            metadata=metadata or {},
        )
        self._tasks.append(task)
        return task

    def cancel_task(self, task_id: str) -> bool:
        task = self.get_task(task_id)
        if task is None:
            return False
        if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
            return False
        task.status = TaskStatus.CANCELLED
        task.cancelled_at = datetime.now(UTC)
        return True

    async def tick(self) -> list[ScheduledTask]:
        """Process all due tasks. Returns list of tasks that were executed."""
        executed: list[ScheduledTask] = []
        due_tasks = [t for t in self._tasks if t.is_due and t.status in (TaskStatus.PENDING, TaskStatus.SCHEDULED)]
        due_tasks.sort(key=lambda t: {"high": 0, "normal": 1, "low": 2}[t.priority.value])

        for task in due_tasks:
            result = await self._execute_task(task)
            if result is not None:
                executed.append(task)

        return executed

    async def run_loop(self, tick_interval: float = 1.0, max_ticks: int | None = None) -> list[ScheduledTask]:
        """Run the scheduler loop until no more tasks are pending/scheduled.

        Args:
            tick_interval: Seconds between ticks.
            max_ticks: Maximum number of ticks to run (safety limit).
        """
        self._running = True
        all_executed: list[ScheduledTask] = []
        tick_count = 0

        while self._running:
            if max_ticks is not None and tick_count >= max_ticks:
                break

            pending = self.list_tasks_by_status(TaskStatus.PENDING)
            scheduled = self.list_tasks_by_status(TaskStatus.SCHEDULED)
            if not pending and not scheduled:
                break

            executed = await self.tick()
            all_executed.extend(executed)
            tick_count += 1

            if tick_interval > 0:
                await _sleep(tick_interval)

        self._running = False
        return all_executed

    def stop(self) -> None:
        self._running = False

    async def _execute_task(self, task: ScheduledTask) -> dict[str, Any] | None:
        if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
            return None

        task.status = TaskStatus.RUNNING
        task.started_at = datetime.now(UTC)

        await self._publish_event(
            V3Event(
                run_id=self.run_id,
                event_type=EventType.SKILL_STARTED.value,
                source=f"scheduler:{task.task_type.value}",
                trigger_depth=0,
                payload={
                    "scheduler_task_id": task.task_id,
                    "task_type": task.task_type.value,
                    "reason": task.reason,
                    "input_payload": task.payload,
                },
            )
        )

        try:
            output = await self.skill_executor.execute(
                task.target_skill_name,
                SkillInput(
                    run_id=self.run_id,
                    payload=task.payload,
                    context={
                        "scheduler_task_id": task.task_id,
                        "task_type": task.task_type.value,
                        "reason": task.reason,
                    },
                ),
            )

            task.completed_at = datetime.now(UTC)

            if output.success:
                task.status = TaskStatus.COMPLETED
                task.current_repeat += 1

                if task.can_repeat and task.interval_seconds is not None:
                    task.status = TaskStatus.SCHEDULED
                    task.schedule_at = datetime.now(UTC) + timedelta(seconds=task.interval_seconds)
                    task.started_at = None
                    task.completed_at = None
            else:
                task.status = TaskStatus.FAILED
                task.last_error = output.error

            await self._publish_event(
                V3Event(
                    run_id=self.run_id,
                    event_type=(
                        EventType.SKILL_FINISHED.value
                        if output.success
                        else EventType.SKILL_FAILED.value
                    ),
                    source=f"scheduler:{task.task_type.value}",
                    trigger_depth=0,
                    payload={
                        "scheduler_task_id": task.task_id,
                        "task_type": task.task_type.value,
                        "summary": output.summary,
                        "error": output.error,
                        "data": output.data,
                    },
                )
            )

            if self.execution_nodes is not None:
                self.execution_nodes.append(
                    ExecutionNode(
                        node_id=f"scheduler:{task.task_id}",
                        kind="trigger",
                        skill_name=task.target_skill_name,
                        status="done" if output.success else "failed",
                        source_event_type=EventType.SKILL_STARTED.value,
                        summary=output.summary,
                        output_data={
                            **output.data,
                            "scheduler_task_id": task.task_id,
                            "task_type": task.task_type.value,
                        },
                    )
                )

            return output.model_dump(mode="json")

        except Exception as e:
            task.status = TaskStatus.FAILED
            task.completed_at = datetime.now(UTC)
            task.last_error = str(e)
            return None

    async def _publish_event(self, event: V3Event) -> None:
        if self.event_store is not None:
            self.event_store.append(event)
        if self.event_bus is not None:
            await self.event_bus.publish(event)


async def _sleep(seconds: float) -> None:
    import asyncio
    await asyncio.sleep(seconds)

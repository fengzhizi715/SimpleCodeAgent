"""Snapshot system for V3.2 Phase 2.

Provides basic snapshots for replay and debugging:
- Workspace snapshot metadata
- Execution state snapshot
- Event checkpoint marker

Does NOT provide:
- Full filesystem snapshot restoration
- Arbitrary point-in-time state recovery
- Deterministic resume
"""

from __future__ import annotations

from typing import Any

from app.v3.contracts.snapshot_contracts import (
    EventCheckpoint,
    ExecutionStateSnapshot,
    Snapshot,
    SnapshotType,
    WorkspaceSnapshotMetadata,
)
from app.v3.events.event_store import EventStore


class SnapshotManager:
    """Manage snapshots for replay and debugging."""

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self._snapshots: list[Snapshot] = []

    @property
    def snapshots(self) -> list[Snapshot]:
        return list(self._snapshots)

    def get_snapshot(self, snapshot_id: str) -> Snapshot | None:
        for snap in self._snapshots:
            if snap.snapshot_id == snapshot_id:
                return snap
        return None

    def list_by_type(self, snapshot_type: SnapshotType) -> list[Snapshot]:
        return [s for s in self._snapshots if s.snapshot_type == snapshot_type]

    def capture_workspace(
        self,
        *,
        workspace_metadata: WorkspaceSnapshotMetadata | None = None,
        label: str = "",
        description: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> Snapshot:
        snap = Snapshot(
            run_id=self.run_id,
            snapshot_type=SnapshotType.WORKSPACE,
            label=label,
            description=description,
            workspace_metadata=workspace_metadata.model_dump(mode="json") if workspace_metadata else {},
            metadata=metadata or {},
        )
        self._snapshots.append(snap)
        return snap

    def capture_execution_state(
        self,
        *,
        completed_nodes: list[str] | None = None,
        failed_nodes: list[str] | None = None,
        pending_nodes: list[str] | None = None,
        shared_state_keys: list[str] | None = None,
        trigger_count: int = 0,
        event_count: int = 0,
        label: str = "",
        description: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> Snapshot:
        state = ExecutionStateSnapshot(
            run_id=self.run_id,
            completed_nodes=completed_nodes or [],
            failed_nodes=failed_nodes or [],
            pending_nodes=pending_nodes or [],
            shared_state_keys=shared_state_keys or [],
            trigger_count=trigger_count,
            event_count=event_count,
        )
        snap = Snapshot(
            run_id=self.run_id,
            snapshot_type=SnapshotType.EXECUTION_STATE,
            label=label,
            description=description,
            execution_state=state.model_dump(mode="json"),
            metadata=metadata or {},
        )
        self._snapshots.append(snap)
        return snap

    def capture_event_checkpoint(
        self,
        *,
        event_store: EventStore,
        label: str = "",
        description: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> Snapshot:
        events = event_store.list_by_run_id(self.run_id)
        chain_ids: set[str] = set()
        last_event = events[-1] if events else None

        for event in events:
            cid = event.execution_chain_id or event.event_id
            chain_ids.add(cid)

        checkpoint = EventCheckpoint(
            run_id=self.run_id,
            event_count=len(events),
            last_event_id=last_event.event_id if last_event else None,
            last_event_type=last_event.event_type if last_event else None,
            chain_ids=sorted(chain_ids),
        )

        snap = Snapshot(
            run_id=self.run_id,
            snapshot_type=SnapshotType.EVENT_CHECKPOINT,
            label=label,
            description=description,
            event_checkpoint=checkpoint.model_dump(mode="json"),
            metadata=metadata or {},
        )
        self._snapshots.append(snap)
        return snap

    def capture_all(
        self,
        *,
        event_store: EventStore,
        completed_nodes: list[str] | None = None,
        failed_nodes: list[str] | None = None,
        pending_nodes: list[str] | None = None,
        shared_state_keys: list[str] | None = None,
        trigger_count: int = 0,
        workspace_metadata: WorkspaceSnapshotMetadata | None = None,
        label: str = "",
        description: str = "",
    ) -> list[Snapshot]:
        """Capture all three snapshot types at once."""
        snaps: list[Snapshot] = []
        snaps.append(
            self.capture_workspace(
                workspace_metadata=workspace_metadata,
                label=label,
                description=f"Workspace snapshot: {description}",
            )
        )
        snaps.append(
            self.capture_execution_state(
                completed_nodes=completed_nodes,
                failed_nodes=failed_nodes,
                pending_nodes=pending_nodes,
                shared_state_keys=shared_state_keys,
                trigger_count=trigger_count,
                event_count=event_store.count_by_run_id(self.run_id),
                label=label,
                description=f"Execution state snapshot: {description}",
            )
        )
        snaps.append(
            self.capture_event_checkpoint(
                event_store=event_store,
                label=label,
                description=f"Event checkpoint: {description}",
            )
        )
        return snaps

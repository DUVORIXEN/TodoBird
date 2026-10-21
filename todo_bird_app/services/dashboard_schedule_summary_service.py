"""
Dashboard schedule summary service.

Pure-data bridge from WBS rollups and WBS CPM summaries into dashboard project
snapshot metrics. No UI logic and no DB writes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from todo_bird_app.services.gantt_wbs_adapter import GanttWBSAdapter
from todo_bird_app.services.wbs_service import WBSService


@dataclass(frozen=True)
class DashboardProjectScheduleSummary:
    project_id: int
    project_name: str
    summary_start: Optional[datetime]
    summary_finish: Optional[datetime]
    summary_span_minutes: Optional[int]
    critical_work_count: int
    summary_contains_critical_count: int
    at_risk_summary_count: int
    scheduled_summary_count: int
    leaf_work_count: int


class DashboardScheduleSummaryService:
    """Read-only dashboard summary projection over existing WBS/Gantt authorities."""

    @classmethod
    def project_summary(
        cls,
        db_manager,
        project_id: int,
        project_name: str = "",
    ) -> DashboardProjectScheduleSummary:
        snapshot = WBSService.build_project_hierarchy(
            db_manager,
            project_id=project_id,
        )
        rows = GanttWBSAdapter.build_project_rows(
            snapshot,
            db_manager,
        )

        starts = [
            row.cpm_earliest_start or row.planned_start
            for row in rows
            if (row.cpm_earliest_start or row.planned_start) is not None
        ]
        finishes = [
            row.cpm_earliest_finish or row.planned_finish
            for row in rows
            if (row.cpm_earliest_finish or row.planned_finish) is not None
        ]
        summary_rows = [row for row in rows if row.is_summary]
        leaf_rows = [row for row in rows if not row.is_summary]

        start = min(starts) if starts else None
        finish = max(finishes) if finishes else None
        span = (
            max(0, int((finish - start).total_seconds() // 60))
            if start is not None and finish is not None
            else None
        )

        at_risk_count = len([
            row
            for row in summary_rows
            if row.cpm_analysis_status in {"blocked", "incomplete", "not_analyzed"}
        ])

        return DashboardProjectScheduleSummary(
            project_id=int(project_id),
            project_name=str(project_name or ""),
            summary_start=start,
            summary_finish=finish,
            summary_span_minutes=span,
            critical_work_count=len([
                row
                for row in leaf_rows
                if row.cpm_is_critical
            ]),
            summary_contains_critical_count=len([
                row
                for row in summary_rows
                if row.cpm_is_critical
            ]),
            at_risk_summary_count=at_risk_count,
            scheduled_summary_count=len([
                row
                for row in summary_rows
                if row.cpm_schedulable
            ]),
            leaf_work_count=len(leaf_rows),
        )

    @staticmethod
    def _date_label(value: datetime) -> str:
        text = value.strftime("%d %b")
        return text[1:] if text.startswith("0") else text

    @classmethod
    def format_snapshot_suffix(
        cls,
        summary: DashboardProjectScheduleSummary,
    ) -> str:
        parts = []
        if summary.summary_start is not None and summary.summary_finish is not None:
            parts.append(
                f"{cls._date_label(summary.summary_start)}-{cls._date_label(summary.summary_finish)}"
            )
        if summary.critical_work_count:
            parts.append(f"{summary.critical_work_count} critical")
        if summary.at_risk_summary_count:
            parts.append(f"{summary.at_risk_summary_count} WBS at risk")
        return " • ".join(parts)

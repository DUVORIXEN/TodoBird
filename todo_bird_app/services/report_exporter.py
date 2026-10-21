import csv
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any

from PySide6.QtGui import QTextDocument, QPageLayout, QPageSize
from PySide6.QtPrintSupport import QPrinter

logger = logging.getLogger(__name__)

class ReportExporterService:
    """
    100% Offline Report Exporter for TODO BIRD.
    Generates CSV task data dumps and styled PDF executive summary reports.
    """
    @staticmethod
    def export_tasks_to_csv(db_manager, file_path: str) -> bool:
        try:
            tasks = db_manager.get_all_tasks()
            fieldnames = [
                "id", "title", "status", "priority", "category", "project_id",
                "planned_date", "planned_start_time", "planned_end_time",
                "estimated_duration", "actual_duration", "progress",
                "delay_minutes", "delay_percentage", "delay_reason", "created_at"
            ]

            with open(file_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
                writer.writeheader()
                for task in tasks:
                    writer.writerow(task)
            logger.info(f"Successfully exported {len(tasks)} tasks to CSV: {file_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to export CSV report: {e}")
            return False

    @staticmethod
    def export_analytics_to_pdf(db_manager, file_path: str) -> bool:
        try:
            tasks = db_manager.get_all_tasks()
            total_tasks = len(tasks)
            completed_tasks = sum(1 for t in tasks if t.get("status") == "Completed")
            inbox_tasks = sum(1 for t in tasks if t.get("status") == "Inbox")
            delayed_tasks = sum(1 for t in tasks if t.get("delay_minutes", 0) > 0)
            avg_delay = (sum(t.get("delay_minutes", 0) for t in tasks) / total_tasks) if total_tasks > 0 else 0

            completion_rate = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0.0

            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <style>
                    body {{
                        font-family: 'Helvetica', 'Arial', sans-serif;
                        color: #1E1E2E;
                        margin: 20px;
                    }}
                    h1 {{
                        color: #111827;
                        border-bottom: 2px solid #E95420;
                        padding-bottom: 8px;
                    }}
                    .metric-box {{
                        display: inline-block;
                        background: #F3F4F6;
                        border-radius: 8px;
                        padding: 12px 18px;
                        margin-right: 12px;
                        margin-bottom: 16px;
                    }}
                    .metric-title {{
                        font-size: 11px;
                        color: #6B7280;
                        text-transform: uppercase;
                    }}
                    .metric-value {{
                        font-size: 20px;
                        font-weight: bold;
                        color: #111827;
                    }}
                    table {{
                        width: 100%;
                        border-collapse: collapse;
                        margin-top: 16px;
                    }}
                    th, td {{
                        border: 1px solid #E5E7EB;
                        padding: 8px 12px;
                        text-align: left;
                        font-size: 12px;
                    }}
                    th {{
                        background-color: #F9FAFB;
                        font-weight: bold;
                    }}
                    tr:nth-child(even) {{
                        background-color: #F9FAFB;
                    }}
                    .footer {{
                        margin-top: 30px;
                        font-size: 10px;
                        color: #9CA3AF;
                        text-align: center;
                    }}
                </style>
            </head>
            <body>
                <h1>🐦 TODO BIRD — Executive Productivity Report</h1>
                <p>Generated offline on local system.</p>

                <div>
                    <div class="metric-box">
                        <div class="metric-title">Total Tasks</div>
                        <div class="metric-value">{total_tasks}</div>
                    </div>
                    <div class="metric-box">
                        <div class="metric-title">Completed</div>
                        <div class="metric-value">{completed_tasks} ({completion_rate:.1f}%)</div>
                    </div>
                    <div class="metric-box">
                        <div class="metric-title">Inbox Pending</div>
                        <div class="metric-value">{inbox_tasks}</div>
                    </div>
                    <div class="metric-box">
                        <div class="metric-title">Avg Delay (min)</div>
                        <div class="metric-value">{avg_delay:.1f}m</div>
                    </div>
                </div>

                <h2>Task Performance Overview</h2>
                <table>
                    <thead>
                        <tr>
                            <th>ID</th>
                            <th>Title</th>
                            <th>Status</th>
                            <th>Priority</th>
                            <th>Planned Date</th>
                            <th>Planned Time</th>
                            <th>Delay (m)</th>
                        </tr>
                    </thead>
                    <tbody>
            """

            for t in tasks[:30]:  # Top 30 tasks for clean single/double page layout
                html_content += f"""
                    <tr>
                        <td>#{t.get('id')}</td>
                        <td><b>{t.get('title')}</b></td>
                        <td>{t.get('status')}</td>
                        <td>{t.get('priority')}</td>
                        <td>{t.get('planned_date') or 'N/A'}</td>
                        <td>{t.get('planned_start_time') or 'N/A'} - {t.get('planned_end_time') or 'N/A'}</td>
                        <td>{t.get('delay_minutes', 0)}m</td>
                    </tr>
                """

            html_content += """
                    </tbody>
                </table>

                <div class="footer">
                    TODO BIRD • 100% Offline Intelligent Task Planner & Gantt Companion
                </div>
            </body>
            </html>
            """

            doc = QTextDocument()
            doc.setHtml(html_content)

            printer = QPrinter(QPrinter.HighResolution)
            printer.setOutputFormat(QPrinter.PdfFormat)
            printer.setOutputFileName(file_path)
            doc.print_(printer)

            logger.info(f"Successfully generated PDF report at: {file_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to export PDF report: {e}")
            return False

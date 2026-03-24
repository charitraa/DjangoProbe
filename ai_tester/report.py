import json
from pathlib import Path
from datetime import datetime
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box
from ai_tester.models import TestResult

console = Console()


class ReportGenerator:
    """
    Generates test reports from TestResult objects.

    Outputs:
      - Terminal: beautiful rich-formatted report
      - JSON:     machine-readable export (--output report.json)
      - PDF:      printable export (--output report.pdf)

    Usage:
        report = ReportGenerator(results, output_path="report.json")
        report.print()
    """

    def __init__(
        self,
        results:     list[TestResult],
        output_path: str | None = None,
        repo_path:   str | None = None,
    ):
        self.results     = results
        self.output_path = output_path
        self.repo_path   = repo_path
        self.generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Compute stats once
        self.total   = len(results)
        self.passed  = sum(1 for r in results if r.status == "PASSED")
        self.failed  = sum(1 for r in results if r.status == "FAILED")
        self.errors  = sum(1 for r in results if r.status == "ERROR")
        self.skipped = sum(1 for r in results if r.status == "SKIPPED")

    #  PUBLIC — main entry
    def print(self) -> None:
        """Print report to terminal and export if output_path set."""

        self._print_terminal()

        if self.output_path:
            self._export(self.output_path)

    #  TERMINAL REPORT
    def _print_terminal(self) -> None:
        """Print beautiful terminal report using Rich."""

        # Header
        project_name = (
            Path(self.repo_path).name
            if self.repo_path
            else "Django Project"
        )

        console.print()
        console.print(Panel(
            f"[bold cyan]DjangoProbe Test Report[/bold cyan]\n"
            f"[dim]{project_name}[/dim]\n"
            f"[dim]Generated: {self.generated_at}[/dim]",
            border_style = "cyan",
        ))

        #Summary Table
        console.print()
        console.print("[bold]  Results Summary[/bold]")

        summary = Table(box=box.ROUNDED, show_header=False)
        summary.add_column("Metric", style="dim")
        summary.add_column("Count",  justify="right")

        summary.add_row("Total Tests",   str(self.total))
        summary.add_row(
            "[green]Passed ✅[/green]",
            f"[green]{self.passed}[/green]"
        )
        summary.add_row(
            "[red]Failed ❌[/red]",
            f"[red]{self.failed}[/red]"
        )
        summary.add_row(
            "[yellow]Errors ⚠[/yellow]",
            f"[yellow]{self.errors}[/yellow]"
        )
        if self.skipped:
            summary.add_row(
                "[dim]Skipped ↷[/dim]",
                f"[dim]{self.skipped}[/dim]"
            )

        console.print(summary)

        # Pass Rate Bar
        if self.total > 0:
            pass_rate = (self.passed / self.total) * 100
            self._print_progress_bar(pass_rate)

        # Failed / Error Details
        bad_results = [
            r for r in self.results
            if r.status in ("FAILED", "ERROR")
        ]

        if bad_results:
            console.print()
            console.print("[bold]  Failed & Error Tests[/bold]")

            fail_table = Table(
                box         = box.ROUNDED,
                show_header = True,
                header_style = "bold",
            )
            fail_table.add_column("Test",   style="cyan",   max_width=40)
            fail_table.add_column("Status", justify="center")
            fail_table.add_column("Error",  style="dim",    max_width=50)

            for r in bad_results:
                status_str = (
                    "[red]FAILED[/red]"
                    if r.status == "FAILED"
                    else "[yellow]ERROR[/yellow]"
                )
                error_msg = (r.error_message or "")[:80]

                fail_table.add_row(
                    r.endpoint.url_pattern,
                    status_str,
                    error_msg,
                )

            console.print(fail_table)

        #All Passed message
        elif self.total > 0 and self.failed == 0 and self.errors == 0:
            console.print()
            console.print(
                "  [bold green]🎉 All tests passed![/bold green]"
            )

        #No results ─
        elif self.total == 0:
            console.print()
            console.print(
                "  [yellow]⚠ No test results to display[/yellow]\n"
                "  [dim]Check that test files were generated correctly[/dim]"
            )

        # Export hint
        console.print()
        console.print(
            "  [dim]Tip: use --output report.json or "
            "--output report.pdf to export[/dim]"
        )
        console.print()

    def _print_progress_bar(self, percent: float) -> None:
        """Print a visual pass rate progress bar."""

        width    = 40
        filled   = int(width * percent / 100)
        empty    = width - filled
        bar      = "█" * filled + "░" * empty
        color    = "green" if percent >= 80 else "yellow" if percent >= 50 else "red"

        console.print(
            f"\n  Pass Rate: [{color}]{bar}[/{color}] "
            f"[bold]{percent:.1f}%[/bold]"
        )

    #  EXPORT
    def _export(self, output_path: str) -> None:
        """Export report to JSON or PDF based on file extension."""

        path = Path(output_path)

        if path.suffix.lower() == ".json":
            self._export_json(path)
        elif path.suffix.lower() == ".pdf":
            self._export_pdf(path)
        else:
            console.print(
                f"[yellow]⚠ Unknown export format: {path.suffix}[/yellow]\n"
                "  Supported: .json, .pdf"
            )

    def _export_json(self, path: Path) -> None:
        """Export results to JSON file."""

        data = {
            "generated_at": self.generated_at,
            "summary": {
                "total":   self.total,
                "passed":  self.passed,
                "failed":  self.failed,
                "errors":  self.errors,
                "skipped": self.skipped,
                "pass_rate": round(
                    (self.passed / self.total * 100) if self.total else 0,
                    2
                ),
            },
            "results": [
                {
                    "url":          r.endpoint.url_pattern,
                    "app":          r.endpoint.app_name,
                    "view":         r.endpoint.view_name,
                    "status":       r.status,
                    "error":        r.error_message,
                    "ai_explanation": r.ai_explanation,
                }
                for r in self.results
            ]
        }

        path.write_text(
            json.dumps(data, indent=2),
            encoding="utf-8"
        )
        console.print(
            f"  [green]✓ JSON report saved:[/green] {path}"
        )

    def _export_pdf(self, path: Path) -> None:
        """Export results to PDF file."""

        try:
            from reportlab.lib.pagesizes  import A4
            from reportlab.lib.styles     import getSampleStyleSheet
            from reportlab.lib            import colors
            from reportlab.platypus       import (
                SimpleDocTemplate, Paragraph,
                Table, TableStyle, Spacer,
            )

        except ImportError:
            console.print(
                "[yellow]⚠ reportlab not installed — "
                "cannot export PDF[/yellow]\n"
                "  Run: pip install reportlab"
            )
            return

        doc    = SimpleDocTemplate(str(path), pagesize=A4)
        styles = getSampleStyleSheet()
        story  = []

        # Title
        story.append(Paragraph(
            "DjangoProbe Test Report",
            styles["Title"]
        ))
        story.append(Paragraph(
            f"Generated: {self.generated_at}",
            styles["Normal"]
        ))
        story.append(Spacer(1, 20))

        # Summary table
        story.append(Paragraph("Summary", styles["Heading2"]))
        summary_data = [
            ["Metric",  "Count"],
            ["Total",   str(self.total)],
            ["Passed",  str(self.passed)],
            ["Failed",  str(self.failed)],
            ["Errors",  str(self.errors)],
        ]
        summary_table = Table(summary_data)
        summary_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
            ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
            ("GRID",       (0, 0), (-1, -1), 0.5, colors.black),
            ("BACKGROUND", (0, 2), (-1, 2), colors.lightgreen),
            ("BACKGROUND", (0, 3), (-1, 4), colors.lightcoral),
        ]))
        story.append(summary_table)
        story.append(Spacer(1, 20))

        # Failed tests
        bad = [r for r in self.results if r.status in ("FAILED", "ERROR")]
        if bad:
            story.append(Paragraph("Failed Tests", styles["Heading2"]))
            fail_data = [["URL", "Status", "Error"]]
            for r in bad:
                fail_data.append([
                    r.endpoint.url_pattern[:40],
                    r.status,
                    (r.error_message or "")[:60],
                ])
            fail_table = Table(fail_data, colWidths=[180, 60, 250])
            fail_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
                ("GRID",       (0, 0), (-1, -1), 0.5, colors.black),
                ("FONTSIZE",   (0, 0), (-1, -1), 8),
            ]))
            story.append(fail_table)

        doc.build(story)
        console.print(f"  [green]✓ PDF report saved:[/green] {path}")
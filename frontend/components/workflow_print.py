"""Printable workflow report.

The DS can print (or save as PDF) the complete workflow of one document or of
every document in the current list: document details, Director reviews, each
workstream with every person's work record, remarks and the full history.

Built as HTML for a QTextDocument, so it prints the same on any printer and
needs nothing beyond PySide6.
"""

from __future__ import annotations

import html
import os
from datetime import datetime
from typing import Callable, Iterable, List, Optional

from PySide6.QtCore import QMarginsF
from PySide6.QtGui import QPageLayout, QPageSize, QTextDocument
from PySide6.QtWidgets import QFileDialog, QMessageBox, QWidget

try:
    from PySide6.QtPrintSupport import QPrintDialog, QPrinter, QPrintPreviewDialog
    HAS_PRINT = True
except ImportError:  # pragma: no cover - QtPrintSupport ships with PySide6
    HAS_PRINT = False


_CSS = """
body { font-family: 'Segoe UI', Arial, sans-serif; font-size: 9pt; color: #0F172A; }
h1 { font-size: 15pt; margin: 0 0 2px 0; }
h2 { font-size: 11pt; margin: 14px 0 4px 0; color: #1E293B; border-bottom: 1px solid #CBD5E1; }
h3 { font-size: 10pt; margin: 8px 0 3px 0; color: #334155; }
.sub { color: #64748B; font-size: 8pt; }
table { border-collapse: collapse; width: 100%; }
th { background: #F1F5F9; text-align: left; padding: 3px 5px; font-size: 8pt; border: 1px solid #CBD5E1; }
td { padding: 3px 5px; vertical-align: top; border: 1px solid #E2E8F0; font-size: 8.5pt; }
td.k { width: 26%; color: #475569; background: #F8FAFC; }
.note { background: #F5F3FF; padding: 4px 6px; }
.muted { color: #94A3B8; font-style: italic; }
"""


def _e(value) -> str:
    text = "" if value is None else str(value)
    return html.escape(text).replace("\n", "<br/>")


def _dt(value) -> str:
    if not value:
        return "—"
    text = str(value).replace("T", " ")
    return text[:16]


def _d(value) -> str:
    return str(value)[:10] if value else "—"


def _label(value) -> str:
    return str(value or "").replace("_", " ").title() or "—"


def document_workflow_html(doc) -> str:
    """The body (no <html> wrapper) of one document's workflow report."""
    parts: List[str] = []
    ref = getattr(doc, "reference", None) or doc.reference_no or f"#{doc.id}"
    parts.append(f"<h1>{_e(ref)} — {_e(doc.subject or doc.title)}</h1>")
    parts.append(
        f"<div class='sub'>Workflow report printed {datetime.now().strftime('%Y-%m-%d %H:%M')}</div>"
    )

    # ---- details ----
    parts.append("<h2>Document</h2><table>")
    rows = [
        ("Reference", ref),
        ("Title / Subject", doc.subject or doc.title),
        ("Source / Sender", " / ".join(v for v in (doc.source, doc.sender_name) if v) or "—"),
        ("Sender reference", doc.sender_reference or "—"),
        ("Ingestion mode", _label(doc.mode)),
        ("Priority", _label(doc.priority)),
        ("Received", _d(doc.received_date)),
        ("Deadline", _d(doc.deadline)),
        ("Registered", _dt(doc.registered_at)),
        ("Lifecycle", doc.lifecycle_label or _label(doc.lifecycle)),
    ]
    if doc.closed_at:
        rows.append(("Closed", f"{_dt(doc.closed_at)}  {doc.closure_remark or ''}"))
    for k, v in rows:
        parts.append(f"<tr><td class='k'>{_e(k)}</td><td>{_e(v)}</td></tr>")
    parts.append("</table>")

    # ---- director reviews ----
    parts.append("<h2>Director Review</h2>")
    if doc.director_reviews:
        parts.append("<table><tr><th>#</th><th>Director</th><th>Written</th><th>Remark</th></tr>")
        for r in doc.director_reviews:
            written = _dt(r.created_at)
            if getattr(r, "edited_at", None):
                written += f"<br/><span class='sub'>edited {_dt(r.edited_at)}</span>"
            parts.append(
                f"<tr><td>{r.review_no}</td><td>{_e(r.director_name or 'Director')}</td>"
                f"<td>{written}</td><td>{_e(r.remark_text)}</td></tr>"
            )
        parts.append("</table>")
    else:
        prior = [
            e for e in (doc.history or [])
            if e.event_type == "PRIOR_DIRECTOR_REVIEW_CONFIRMED"
        ]
        if prior:
            parts.append(
                f"<p class='note'>Director's instruction already written on the document "
                f"(confirmed by the DS {_dt(prior[-1].created_at)}): {_e(prior[-1].details or '')}</p>"
            )
        else:
            parts.append("<p class='muted'>No Director review recorded.</p>")

    # ---- workstreams ----
    parts.append("<h2>Workstreams</h2>")
    branches = list(doc.branches or [])
    if not branches:
        parts.append("<p class='muted'>Not routed yet.</p>")
    for b in branches:
        who = b.department_name or b.target_user_name or ""
        parts.append(
            f"<h3>{_e(b.label or _label(b.branch_type))}"
            f"{(' — ' + _e(who)) if who and who != b.label else ''}</h3>"
        )
        parts.append("<table>")
        parts.append(
            f"<tr><td class='k'>Stage</td><td>{_e(b.stage_label or _label(b.stage))}"
            f"{'' if b.is_active else ' (closed)'}</td></tr>"
        )
        parts.append(
            f"<tr><td class='k'>Opened / closed</td><td>{_dt(b.opened_at)} / {_dt(b.closed_at)}</td></tr>"
        )
        parts.append(f"<tr><td class='k'>Deadline</td><td>{_d(b.deadline)}</td></tr>")
        if b.round_no and b.round_no > 1:
            parts.append(f"<tr><td class='k'>Round</td><td>{b.round_no}</td></tr>")
        if b.instructions:
            parts.append(f"<tr><td class='k'>Instructions</td><td>{_e(b.instructions)}</td></tr>")
        parts.append("</table>")
        if b.work_items:
            parts.append(
                "<table><tr><th>Person</th><th>Stage</th><th>Assigned</th><th>Deadline</th>"
                "<th>Progress / result</th></tr>"
            )
            for w in b.work_items:
                progress_lines = []
                for p in (w.progress_updates or []):
                    progress_lines.append(
                        f"{_dt(p.created_at)} {_e(p.author_name or '')}: {_e(p.description)}"
                    )
                for rv in (w.reviews or []):
                    progress_lines.append(
                        f"{_dt(rv.created_at)} review by {_e(rv.reviewer_name or '')}: "
                        f"{_e(_label(rv.outcome))}{(' - ' + _e(rv.note)) if rv.note else ''}"
                    )
                if not progress_lines and w.latest_progress_text:
                    progress_lines.append(_e(w.latest_progress_text))
                parts.append(
                    f"<tr><td>{_e(w.assignee_name or '—')}"
                    f"{('<br/><span class=sub>' + _e(w.instructions) + '</span>') if w.instructions else ''}</td>"
                    f"<td>{_e(w.stage_label or _label(w.stage))}</td>"
                    f"<td>{_dt(w.assigned_at)}<br/><span class='sub'>by {_e(w.assigner_name or '—')}</span></td>"
                    f"<td>{_d(w.deadline)}</td>"
                    f"<td>{'<br/>'.join(progress_lines) or '<span class=muted>—</span>'}</td></tr>"
                )
            parts.append("</table>")

    # ---- remarks ----
    remarks = [
        r for r in (doc.remarks or [])
        if r.provenance not in ("DIRECTOR_REVIEW", "DIRECTOR_REVIEW_EDIT")
    ]
    if remarks:
        parts.append("<h2>Remarks</h2><table><tr><th>When</th><th>By</th><th>Workstream</th><th>Remark</th></tr>")
        for r in remarks:
            parts.append(
                f"<tr><td>{_dt(r.created_at)}</td><td>{_e(r.author_name or '')}"
                f" <span class='sub'>({_e(_label(r.remark_type))})</span></td>"
                f"<td>{_e(r.branch_label or 'Document')}</td><td>{_e(r.remark_text)}</td></tr>"
            )
        parts.append("</table>")

    # ---- history ----
    parts.append("<h2>Workflow History</h2>")
    history = list(doc.history or [])
    if history:
        parts.append("<table><tr><th>When</th><th>Who</th><th>Workstream</th><th>What happened</th></tr>")
        for e in history:
            who = _e(e.actor_name or "System")
            if e.actor_context_type:
                who += f" <span class='sub'>({_e(e.actor_context_type)})</span>"
            detail = f"<br/><span class='sub'>{_e(e.details)}</span>" if e.details else ""
            parts.append(
                f"<tr><td>{_dt(e.created_at)}</td><td>{who}</td>"
                f"<td>{_e(e.branch_label or '—')}</td><td>{_e(e.summary or e.event_type)}{detail}</td></tr>"
            )
        parts.append("</table>")
    else:
        parts.append("<p class='muted'>No history recorded.</p>")

    return "\n".join(parts)


_TABLE = "<table width='100%' cellspacing='0' cellpadding='3'>"


def workflows_html(docs: Iterable) -> str:
    bodies = []
    for i, doc in enumerate(docs):
        style = " style='page-break-before: always;'" if i else ""
        # QTextDocument ignores CSS table widths: give every table the
        # full page width as an attribute.
        body = document_workflow_html(doc).replace("<table>", _TABLE)
        bodies.append(f"<div{style}>{body}</div>")
    return (
        f"<html><head><meta charset='utf-8'><style>{_CSS}</style></head>"
        f"<body>{''.join(bodies)}</body></html>"
    )


def _text_document(docs: List) -> QTextDocument:
    text_doc = QTextDocument()
    text_doc.setDefaultStyleSheet(_CSS)
    text_doc.setHtml(workflows_html(docs))
    return text_doc


def _new_printer() -> "QPrinter":
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setPageLayout(
        QPageLayout(
            QPageSize(QPageSize.PageSizeId.A4),
            QPageLayout.Orientation.Portrait,
            QMarginsF(12, 12, 12, 12),
            QPageLayout.Unit.Millimeter,
        )
    )
    return printer


def print_workflows(
    parent: Optional[QWidget],
    docs: List,
    loader: Optional[Callable[[object], object]] = None,
) -> None:
    """Ask Print or Save as PDF, then produce the workflow report.

    *loader* turns a list entry into a full document (with workstreams and
    history); by default the entry is used as it is.
    """
    docs = [d for d in docs if d is not None]
    if not docs:
        QMessageBox.information(parent, "Print Workflow", "There is no document to print.")
        return
    if not HAS_PRINT:
        QMessageBox.warning(parent, "Print Workflow", "Printing is not available on this computer.")
        return

    box = QMessageBox(parent)
    box.setWindowTitle("Print Workflow")
    count = len(docs)
    box.setText(
        f"Print the complete workflow of {'this document' if count == 1 else f'{count} documents'}?"
    )
    box.setInformativeText(
        "Includes document details, Director review, every workstream with each person's "
        "work, remarks and the full history."
        + ("\nEach document starts on a new page." if count > 1 else "")
    )
    preview_btn = box.addButton("Print…", QMessageBox.ButtonRole.AcceptRole)
    pdf_btn = box.addButton("Save as PDF…", QMessageBox.ButtonRole.ActionRole)
    box.addButton(QMessageBox.StandardButton.Cancel)
    box.exec()
    clicked = box.clickedButton()
    if clicked not in (preview_btn, pdf_btn):
        return

    pdf_path = ""
    if clicked is pdf_btn:
        first = docs[0]
        default_name = (
            f"{(getattr(first, 'reference', '') or 'workflow').replace('/', '-')}_workflow.pdf"
            if count == 1 else f"CDTRS_workflows_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
        )
        pdf_path, _ = QFileDialog.getSaveFileName(
            parent, "Save Workflow as PDF",
            os.path.join(os.path.expanduser("~"), "Documents", default_name),
            "PDF files (*.pdf)",
        )
        if not pdf_path:
            return
        if not pdf_path.lower().endswith(".pdf"):
            pdf_path += ".pdf"

    # Load the full documents (workstreams, history) only now.
    full_docs = []
    failed = []
    for d in docs:
        try:
            full_docs.append(loader(d) if loader else d)
        except Exception:
            failed.append(getattr(d, "reference", None) or str(getattr(d, "id", "")))
    full_docs = [d for d in full_docs if d is not None]
    if not full_docs:
        QMessageBox.warning(parent, "Print Workflow", "Could not load the documents to print.")
        return

    text_doc = _text_document(full_docs)
    printer = _new_printer()

    if pdf_path:
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(pdf_path)
        text_doc.print_(printer)
        QMessageBox.information(parent, "Print Workflow", f"Saved:\n{pdf_path}")
    else:
        preview = QPrintPreviewDialog(printer, parent)
        preview.setWindowTitle("Print Workflow")
        preview.resize(1000, 800)
        preview.paintRequested.connect(lambda p: text_doc.print_(p))
        preview.exec()

    if failed:
        QMessageBox.warning(
            parent, "Print Workflow",
            "These documents could not be loaded and were left out:\n" + ", ".join(failed),
        )

"""Shared vocabulary for MacEff corpus doctors.

MacEff has several corpora that describe themselves — the knowledge graph, the
policy corpus and its indices, the learnings index — and each drifts from what
it describes in its own way. A **doctor** is the instrument that reports that
drift for one corpus.

Doctors stay **specialists**. A single checker over every corpus would be
shallow everywhere or become a dumping ground, because each corpus needs domain
knowledge the others cannot carry: graph topology, manifest registration and
index referential integrity are different problems.

But specialists reporting in private vocabularies are unreadable together. An
agent cannot tell that "orphan", "dangling entry", "unregistered policy" and
"stale index" are the same finding wearing four different words. So the
*vocabulary* is shared even though the *checks* are not, and it lives here so
no doctor owns it. Whichever doctor ships first extracts this rather than
keeping it — discovery order is not ownership.

The medical register is used only where it clarifies. A term that adds ceremony
without meaning does not belong here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

__all__ = ["Severity", "Finding", "Chart", "Diagnosis", "format_diagnosis"]


class Severity:
    """How a finding should be read, not how loudly it should be printed.

    ``ACUTE``   something is wrong NOW and will mislead a reader who trusts it.
                A registry that claims a type which does not exist, an index
                that reports coverage it does not have. These produce confident
                wrong answers, which is worse than no answer.

    ``CHRONIC`` accumulating degradation. Nothing breaks today; the corpus
                becomes less trustworthy every cycle. Orphaned artifacts are
                the canonical case — each one is survivable and the trend is
                not.

    ``NOTE``    an observation with no implied action. Present so a reader can
                see what was examined, because a doctor that prints only
                problems cannot be distinguished from one that failed to run.
    """

    ACUTE = "acute"
    CHRONIC = "chronic"
    NOTE = "note"

    ORDER = {ACUTE: 0, CHRONIC: 1, NOTE: 2}
    ICON = {ACUTE: "🔴", CHRONIC: "🟡", NOTE: "·"}


@dataclass
class Finding:
    """One observation about a corpus.

    ``remedy`` is required rather than optional. A finding an agent cannot act
    on is noise, and noise trains agents to skim the whole report — which is
    the failure mode that makes a checker worse than no checker, because an
    ignored report still looks like coverage.

    ``referral`` names another corpus when the remedy lives outside this
    doctor's domain. Specialists refer rather than reaching across.
    """

    check: str
    severity: str
    subject: str
    detail: str
    remedy: str
    referral: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "check": self.check,
            "severity": self.severity,
            "subject": self.subject,
            "detail": self.detail,
            "remedy": self.remedy,
        }
        if self.referral:
            d["referral"] = self.referral
        return d


@dataclass
class Chart:
    """Baseline measurements taken during an examination.

    Recorded even when nothing is wrong. A doctor that reports only findings
    gives a reader no way to tell a healthy corpus from an examination that
    silently covered nothing — the distinction this whole family of tools
    exists to make.
    """

    corpus: str
    vitals: Dict[str, Any] = field(default_factory=dict)
    scope: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {"corpus": self.corpus, "vitals": self.vitals, "scope": self.scope}


@dataclass
class Diagnosis:
    """The full result of one examination."""

    chart: Chart
    findings: List[Finding] = field(default_factory=list)

    def sorted_findings(self) -> List[Finding]:
        return sorted(self.findings,
                      key=lambda f: (Severity.ORDER.get(f.severity, 9), f.check, f.subject))

    def counts(self) -> Dict[str, int]:
        out = {Severity.ACUTE: 0, Severity.CHRONIC: 0, Severity.NOTE: 0}
        for f in self.findings:
            out[f.severity] = out.get(f.severity, 0) + 1
        return out

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chart": self.chart.to_dict(),
            "counts": self.counts(),
            "findings": [f.to_dict() for f in self.sorted_findings()],
        }


def format_diagnosis(dx: Diagnosis) -> str:
    """Render an examination for a human or an agent reading a terminal.

    The chart prints first and always. What was examined is context for every
    finding below it, and its absence is what lets a clean report be confused
    with an examination that never looked.
    """
    lines: List[str] = []
    lines.append(f"🩺 {dx.chart.corpus}")
    if dx.chart.scope:
        lines.append(f"   examined: {', '.join(dx.chart.scope)}")
    if dx.chart.vitals:
        vit = "  ".join(f"{k}={v}" for k, v in dx.chart.vitals.items())
        lines.append(f"   chart:    {vit}")
    lines.append("")

    findings = dx.sorted_findings()
    if not findings:
        lines.append("   ✅ no findings")
        lines.append("   (a clean result is only meaningful alongside the chart above —")
        lines.append("    it says these checks ran and found nothing, not that nothing is wrong.)")
        return "\n".join(lines)

    counts = dx.counts()
    lines.append(f"   {counts.get(Severity.ACUTE, 0)} acute · "
                 f"{counts.get(Severity.CHRONIC, 0)} chronic · "
                 f"{counts.get(Severity.NOTE, 0)} note")
    lines.append("")

    current = None
    for f in findings:
        if f.check != current:
            current = f.check
            lines.append(f"  {f.check}")
        icon = Severity.ICON.get(f.severity, "·")
        lines.append(f"   {icon} {f.subject}")
        if f.detail:
            lines.append(f"      {f.detail}")
        lines.append(f"      → {f.remedy}")
        if f.referral:
            lines.append(f"      ↪ referral: {f.referral}")
    return "\n".join(lines)

"""
The exchange rate between metered tokens and the account's weekly percent, fitted at ticks.

The account's counters are whole percents. At about a point an hour, hourly differences carry
plus or minus one of rounding noise on a signal of about one. A crossing of the counter from
k to k+1 is different: the account's cumulative points at that moment equal k+1 exactly, and
the moment is bracketed by the last sample at k and the first at k+1. Regressing the cumulative
points on the cumulative weighted tokens at the crossings uses every sample's information
instead of differencing it away.

Method:

- A tick is one crossing. The counter's samples are walked in order; a drop starts a new
  segment (a weekly reset). A rise of more than one point between two samples puts several
  crossings in one bracket that cannot be told apart, so those are dropped and counted.
- A bracket wider than ``NARROW_S`` (30 minutes) is low quality: its weight falls as
  ``(NARROW_S / width) ** 2``. One wider than ``MAX_BRACKET_S`` is dropped. Both are counted
  in the notes.
- Within a segment the first tick is the origin. Each later tick is a row: y is the points
  since the origin (the level difference), x is the cumulative weighted tokens per model
  between the two bracket midpoints. An event's tokens are spread evenly over its
  ``first_ts`` to ``last_ts`` when both are known, so the cumulative curve is interpolated.
- The model is ``y = scale * sum(prior_m * x_m) + sum(delta_m * x_m) + drift * hours``. The
  ``delta_m`` are ridge-shrunk towards zero (``RIDGE``, relative to each column's own scale),
  so a model with little data keeps the prior ratio. ``drift`` is points per hour the metered
  tokens do not explain, other agents' spend among it. A model's effective rate is
  ``scale * prior_m + delta_m`` points per weighted token.
- Intervals are 5th to 95th percentiles of a bootstrap (fixed seed) that resamples runs of
  neighbouring ticks, not single ticks: rows share their origin and the unmetered noise
  accumulates along them, so single-tick resampling would give intervals far too tight.
- The cache-read weight is a parameter. Both ``CACHE_READ_WEIGHTS`` are fitted and both
  residuals are reported; nothing here chooses one.
- A ``weekly_scoped`` counter, when it has crossings, gives its pool's rate from those alone
  (``points = rate * pool tokens + drift * hours``), as a cross-check on the joint fit. It is a
  different counter, so the numbers are comparable only in their ratios.

Nothing here writes. It is read-only analysis over ``budget_sampled`` and ``usage_metered`` events.
"""

import json
import math
import random
import sys
import textwrap
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from macf import usage_meter
from macf.agent_events_log import read_events

NARROW_S = 1800.0
MAX_BRACKET_S = 6 * 3600.0
MIN_ROWS = 3
MIN_METERED_FRACTION = 0.5  # of the rows, those with metered tokens in them
RIDGE = 0.3
BOOTSTRAPS = 300
CACHE_READ_WEIGHTS = (0.1, 0.0)
HOUR = 3600.0
PRIORS_FILE = "usage_priors.json"

#: Relative cost of a weighted token, by model-id prefix. These are PRIORS, starting points to be
#: confirmed against the counters, not facts about the account's pricing. The fit's per-model
#: deviations show where the data disagrees. A JSON file of the same shape at
#: ``{agent home}/.maceff/usage_priors.json`` overrides entries when present.
MODEL_PRIORS: Dict[str, float] = {
    "claude-opus": 5.0,
    "claude-sonnet": 1.0,
    "claude-haiku": 0.33,
    "claude-fable": 5.0,
}


@dataclass(frozen=True, kw_only=True)
class Tick:
    series: str  # "weekly_all" or the scoped pool's name
    level: int  # the counter after the crossing
    t_lo: float
    t_hi: float
    segment: int
    weight: float
    quality: str  # "ok" or "wide"

    @property
    def t_mid(self) -> float:
        return (self.t_lo + self.t_hi) / 2

    @property
    def width(self) -> float:
        return self.t_hi - self.t_lo


@dataclass(frozen=True, kw_only=True)
class Crossings:
    series: str
    ticks: Tuple[Tick, ...]
    segments: int
    dropped_wide: int
    dropped_multi: int


@dataclass(frozen=True, kw_only=True)
class Estimate:
    value: float
    low: float
    high: float


@dataclass(frozen=True, kw_only=True)
class TickFit:
    cache_read_weight: float
    scale: Estimate  # points per prior-weighted token
    rates: Dict[str, Estimate]  # model id to effective points per weighted token
    drift: Estimate  # points per hour the metered tokens do not explain
    blended_rate: float  # fitted metered points over weighted tokens, comparable to the provisional rate
    ticks: int  # rows in the regression
    rms_residual: float  # points, weighted
    notes: Tuple[str, ...]


@dataclass(frozen=True, kw_only=True)
class ScopedFit:
    pool: str
    cache_read_weight: float
    rate: Estimate  # scoped-counter points per weighted token of the pool's models
    drift: Estimate
    joint_rate: Optional[float]  # the joint fit's token-weighted rate for the same models
    ticks: int
    rms_residual: float


@dataclass(frozen=True, kw_only=True)
class TickReport:
    window_h: float
    crossings: Crossings
    fits: Dict[float, TickFit]  # by cache-read weight; none is chosen
    scoped: Tuple[ScopedFit, ...]
    scoped_crossings: Tuple[Crossings, ...]
    refusal: Optional[str]  # why there is no fit, when there is none


@dataclass(frozen=True, kw_only=True)
class _Row:
    y: float
    hours: float
    x: Dict[str, float]  # weighted tokens per model since the segment's origin
    weight: float


@dataclass(frozen=True, kw_only=True)
class _Flow:
    model: str
    t0: float
    t1: float
    rows: Dict[str, int]

    def tokens(self, cr: float) -> float:
        return usage_meter.weighted(self.rows, cr)


# ── priors ───────────────────────────────────────────────────────────────────

def load_priors(path: Optional[Path] = None) -> Dict[str, float]:
    """The defaults, overridden by the agent home's ``.maceff/usage_priors.json`` when it exists."""
    priors = dict(MODEL_PRIORS)
    if path is None:
        from macf.utils.paths import find_agent_home
        path = find_agent_home() / ".maceff" / PRIORS_FILE
    if not path.exists():
        return priors
    try:
        data = json.loads(path.read_text())
        if not isinstance(data, dict):
            raise ValueError("expected an object of prefix to ratio")
        priors.update({str(k): float(v) for k, v in data.items()})
    except (OSError, ValueError, TypeError) as e:
        print(f"⚠️ MACF: usage ticks: unreadable {path} ({e}); using the default model priors", file=sys.stderr)
        return dict(MODEL_PRIORS)
    return priors


def prior_ratio(model: str, priors: Dict[str, float], warned: set) -> float:
    """The relative cost of ``model``: its longest matching prefix, else 1 with a warning."""
    best = max((p for p in priors if model.startswith(p)), key=len, default=None)
    if best is not None:
        return priors[best]
    if model not in warned:
        warned.add(model)
        print(f"⚠️ MACF: usage ticks: no prior ratio for model {model!r}; using 1", file=sys.stderr)
    return 1.0


# ── ticks ────────────────────────────────────────────────────────────────────

def extract_ticks(points: Sequence[Dict[str, float]], series: str) -> Crossings:
    """Crossings of a counter from its samples, oldest first, each ``{t, pct}``."""
    ticks: List[Tick] = []
    segment = dropped_wide = dropped_multi = 0
    for a, b in zip(points, points[1:]):
        pa, pb = round(a["pct"]), round(b["pct"])
        if pb < pa:
            segment += 1  # a weekly reset
            continue
        if pb == pa:
            continue
        width = b["t"] - a["t"]
        if pb - pa > 1:
            dropped_multi += pb - pa
            continue
        if width > MAX_BRACKET_S:
            dropped_wide += 1
            continue
        wide = width > NARROW_S
        ticks.append(Tick(series=series, level=pb, t_lo=a["t"], t_hi=b["t"], segment=segment,
                          weight=(NARROW_S / width) ** 2 if wide else 1.0, quality="wide" if wide else "ok"))
    return Crossings(series=series, ticks=tuple(ticks), segments=len({t.segment for t in ticks}),
                     dropped_wide=dropped_wide, dropped_multi=dropped_multi)


def _series(samples: List[dict], kind: str, scope: Optional[str]) -> List[Dict[str, float]]:
    out = []
    for s in samples:
        lim = next((l for l in s["limits"] if l.get("kind") == kind and (scope is None or l.get("scope") == scope)),
                   None)
        if lim is not None and lim.get("percent") is not None:
            out.append({"t": s["t"], "pct": float(lim["percent"])})
    return out


# ── cumulative tokens ────────────────────────────────────────────────────────

def _stamp(value: object, what: str, bad: List[str]) -> Optional[float]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        bad.append(f"{what} {value!r}")
        return None


def _flows(since: float) -> List[_Flow]:
    """Each metered model row as a flow over its calls' time span."""
    flows: List[_Flow] = []
    bad: List[str] = []
    for ev in read_events(reverse=True, scope="all", only=usage_meter.EVENT, since=since - HOUR):
        d = ev.get("data") or {}
        t1 = _stamp(d.get("last_ts"), "last_ts", bad)
        t0 = _stamp(d.get("first_ts"), "first_ts", bad)
        t1 = t1 if t1 is not None else float(ev.get("timestamp", 0))
        t0 = t0 if t0 is not None and t0 <= t1 else t1
        for model, row in (d.get("by_model") or {}).items():
            flows.append(_Flow(model=model, t0=t0, t1=t1, rows=row))
    if bad:
        print(f"⚠️ MACF: usage ticks: {len(bad)} unreadable timestamps (first {bad[0]}); "
              "those events are placed at the time they were logged", file=sys.stderr)
    return flows


def _cumulative(flows: List[Tuple[_Flow, float]], t: float) -> Dict[str, float]:
    """Weighted tokens per model up to ``t``, each flow spread evenly over its span. ``flows`` pairs
    each with its weighted tokens."""
    out: Dict[str, float] = {}
    for f, w in flows:
        if f.t1 <= t:
            frac = 1.0
        elif f.t0 >= t:
            continue
        else:
            frac = (t - f.t0) / (f.t1 - f.t0)
        out[f.model] = out.get(f.model, 0.0) + frac * w
    return out


def _rows(ticks: Sequence[Tick], flows: List[_Flow], cr: float) -> List[_Row]:
    rows: List[_Row] = []
    weighted = [(f, f.tokens(cr)) for f in flows]
    origin: Dict[int, Tuple[Tick, Dict[str, float]]] = {}
    for tk in ticks:
        cum = _cumulative(weighted, tk.t_mid)
        if tk.segment not in origin:
            origin[tk.segment] = (tk, cum)
            continue
        o, ocum = origin[tk.segment]
        x = {m: cum.get(m, 0.0) - ocum.get(m, 0.0) for m in cum}
        rows.append(_Row(y=float(tk.level - o.level), hours=(tk.t_mid - o.t_mid) / HOUR, x=x, weight=tk.weight))
    return rows


# ── the solver ───────────────────────────────────────────────────────────────

def _solve(a: List[List[float]], b: List[float]) -> Optional[List[float]]:
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(m[r][c]))
        if abs(m[p][c]) < 1e-12:
            return None
        m[c], m[p] = m[p], m[c]
        for r in range(n):
            if r != c:
                f = m[r][c] / m[c][c]
                for k in range(c, n + 1):
                    m[r][k] -= f * m[c][k]
    return [m[i][n] / m[i][i] for i in range(n)]


@dataclass(frozen=True, kw_only=True)
class _Moments:
    """Per-row contributions to the normal equations, so a bootstrap sums rows instead of rebuilding."""
    a: List[List[List[float]]]  # per row, w * x_i * x_j
    b: List[List[float]]  # per row, w * x_i * y


def _moments(cols: List[List[float]], y: List[float], w: List[float]) -> _Moments:
    k = len(cols)
    return _Moments(a=[[[w[r] * cols[i][r] * cols[j][r] for j in range(k)] for i in range(k)] for r in range(len(y))],
                    b=[[w[r] * cols[i][r] * y[r] for i in range(k)] for r in range(len(y))])


def _wls(mom: _Moments, idx: Sequence[int], ridge: List[bool]) -> Optional[List[float]]:
    """Weighted least squares over the rows ``idx`` (repeats allowed), on unit-scaled columns with a
    ridge on the flagged ones; coefficients in the original units."""
    k = len(ridge)
    a = [[sum(mom.a[r][i][j] for r in idx) for j in range(k)] for i in range(k)]
    b = [sum(mom.b[r][i] for r in idx) for i in range(k)]
    norms = [math.sqrt(a[i][i]) if a[i][i] > 0 else 1.0 for i in range(k)]
    z = [[a[i][j] / (norms[i] * norms[j]) for j in range(k)] for i in range(k)]
    for i in range(k):
        z[i][i] += (RIDGE if ridge[i] else 0.0) + 1e-9
    sol = _solve(z, [b[i] / norms[i] for i in range(k)])
    return None if sol is None else [s / n for s, n in zip(sol, norms)]


def _resample(n: int, rng: random.Random) -> List[int]:
    """Row indices of a circular block bootstrap sample: runs of about the square root of ``n``."""
    block = max(3, int(math.sqrt(n)))
    out: List[int] = []
    while len(out) < n:
        start = rng.randrange(n)
        out.extend((start + i) % n for i in range(block))
    return out[:n]


def _percentiles(vals: List[float], point: float) -> Estimate:
    if not vals:
        return Estimate(value=point, low=point, high=point)
    o = sorted(vals)
    lo, hi = o[int(0.05 * len(o))], o[min(len(o) - 1, int(0.95 * len(o)))]
    return Estimate(value=point, low=min(lo, point), high=max(hi, point))


def _design(rows: List[_Row], models: List[str], ratios: Dict[str, float]) -> Tuple[List[List[float]], List[bool]]:
    cols = [[sum(ratios[m] * r.x.get(m, 0.0) for m in models) for r in rows]]
    ridge = [False]
    for m in models:
        cols.append([r.x.get(m, 0.0) for r in rows])
        ridge.append(True)
    cols.append([r.hours for r in rows])
    ridge.append(False)
    return cols, ridge


def _rms(rows: List[_Row], pred: List[float]) -> float:
    tw = sum(r.weight for r in rows)
    return math.sqrt(sum(r.weight * (r.y - p) ** 2 for r, p in zip(rows, pred)) / tw) if tw > 0 else 0.0


def _joint_pred(rows: List[_Row], models: List[str], ratios: Dict[str, float], c: List[float]) -> List[float]:
    return [c[0] * sum(ratios[m] * r.x.get(m, 0.0) for m in models)
            + sum(c[1 + i] * r.x.get(m, 0.0) for i, m in enumerate(models)) + c[-1] * r.hours for r in rows]


def _enough_metered(rows: List[_Row]) -> bool:
    """A fit needs ``MIN_ROWS`` rows with metered tokens, and at least ``MIN_METERED_FRACTION`` of all rows."""
    metered = sum(1 for r in rows if sum(r.x.values()) > 0)
    return metered >= MIN_ROWS and metered >= MIN_METERED_FRACTION * len(rows)


def fit_joint(ticks: Sequence[Tick], flows: List[_Flow], cr: float, priors: Dict[str, float],
              notes: Sequence[str] = ()) -> Optional[TickFit]:
    """The joint fit on one counter's ticks, or None with too few usable rows."""
    rows = _rows(ticks, flows, cr)
    models = sorted({m for r in rows for m, v in r.x.items() if v > 0})
    if len(rows) < MIN_ROWS or not models or not _enough_metered(rows):
        return None
    warned: set = set()
    ratios = {m: prior_ratio(m, priors, warned) for m in models}
    cols, ridge = _design(rows, models, ratios)
    mom = _moments(cols, [r.y for r in rows], [r.weight for r in rows])
    c = _wls(mom, range(len(rows)), ridge)
    if c is None:
        return None
    rng = random.Random(0)
    boots: List[List[float]] = []
    for _ in range(BOOTSTRAPS):
        bc = _wls(mom, _resample(len(rows), rng), ridge)
        if bc is not None:
            boots.append(bc)

    def rate(i: int, coefs: List[float]) -> float:
        return coefs[0] * ratios[models[i]] + coefs[1 + i]

    fnotes = list(notes)
    scale = _percentiles([b[0] for b in boots], c[0])
    if scale.high - scale.low <= 1e-9 * abs(scale.value):
        fnotes.append("the interval has no width: too little data to say how sure the rates are")
    if c[0] <= 0:
        fnotes.append("the scale is not positive: the data does not support a rate")
    total_x = {m: sum(r.x.get(m, 0.0) for r in rows) for m in models}
    tot = sum(total_x.values())
    fitted = sum(rate(i, c) * total_x[m] for i, m in enumerate(models))
    return TickFit(
        cache_read_weight=cr,
        scale=scale,
        rates={m: _percentiles([rate(i, b) for b in boots], rate(i, c)) for i, m in enumerate(models)},
        drift=_percentiles([b[-1] for b in boots], c[-1]),
        blended_rate=fitted / tot if tot > 0 else 0.0,
        ticks=len(rows), rms_residual=_rms(rows, _joint_pred(rows, models, ratios, c)), notes=tuple(fnotes))


def fit_scoped(cross: Crossings, flows: List[_Flow], cr: float, joint: Optional[TickFit]) -> Optional[ScopedFit]:
    """One scoped pool's rate from its own crossings: ``points = rate * pool tokens + drift * hours``."""
    pool = cross.series
    mine = [f for f in flows if pool.lower() in f.model.lower()]
    rows = _rows(cross.ticks, mine, cr)
    if len(rows) < MIN_ROWS or not _enough_metered(rows):
        return None

    cols = [[sum(r.x.values()) for r in rows], [r.hours for r in rows]]
    mom = _moments(cols, [r.y for r in rows], [r.weight for r in rows])
    c = _wls(mom, range(len(rows)), [False, False])
    if c is None:
        return None
    rng = random.Random(0)
    boots = [bc for bc in (_wls(mom, _resample(len(rows), rng), [False, False]) for _ in range(BOOTSTRAPS)) if bc]
    pred = [c[0] * sum(r.x.values()) + c[1] * r.hours for r in rows]
    joint_rate = None
    if joint is not None:
        tok = {m: sum(r.x.get(m, 0.0) for r in rows) for m in joint.rates}
        used = sum(v for m, v in tok.items() if pool.lower() in m.lower())
        if used > 0:
            joint_rate = sum(joint.rates[m].value * v for m, v in tok.items() if pool.lower() in m.lower()) / used
    return ScopedFit(pool=pool, cache_read_weight=cr, rate=_percentiles([b[0] for b in boots], c[0]),
                     drift=_percentiles([b[1] for b in boots], c[1]), joint_rate=joint_rate,
                     ticks=len(rows), rms_residual=_rms(rows, pred))


# ── the report ───────────────────────────────────────────────────────────────

def _notes(cross: Crossings) -> List[str]:
    wide = sum(1 for t in cross.ticks if t.quality == "wide")
    notes = []
    if wide:
        notes.append(f"{wide} crossings with a bracket over 30m, downweighted")
    if cross.dropped_wide:
        notes.append(f"{cross.dropped_wide} crossings dropped, bracket over 6h")
    if cross.dropped_multi:
        notes.append(f"{cross.dropped_multi} crossings dropped, several levels in one gap")
    return notes


def analyse(window_h: float = 48.0, now: Optional[float] = None, priors: Optional[Dict[str, float]] = None) -> TickReport:
    """Crossings and fits over the last ``window_h`` hours. Reads only that window."""
    from macf import budget
    now = now or time.time()
    since = now - window_h * HOUR
    priors = priors if priors is not None else load_priors()
    samples = budget.samples(since=since, now=now)
    cross = extract_ticks(_series(samples, "weekly_all", None), "weekly_all")
    pools = sorted({l.get("scope") for s in samples for l in s["limits"]
                    if l.get("kind") == "weekly_scoped" and l.get("scope")})
    scoped_cross = tuple(extract_ticks(_series(samples, "weekly_scoped", p), p) for p in pools)
    flows = _flows(since)
    fits: Dict[float, TickFit] = {}
    for cr in CACHE_READ_WEIGHTS:
        f = fit_joint(cross.ticks, flows, cr, priors)
        if f is not None:
            fits[cr] = f
    scoped = tuple(s for s in (fit_scoped(c, flows, CACHE_READ_WEIGHTS[0], fits.get(CACHE_READ_WEIGHTS[0]))
                               for c in scoped_cross) if s is not None)
    refusal = None
    if not fits:
        rows = _rows(cross.ticks, flows, CACHE_READ_WEIGHTS[0])
        metered = sum(1 for r in rows if sum(r.x.values()) > 0)
        refusal = (f"{len(cross.ticks)} crossings in the last {window_h:g}h; need at least {MIN_ROWS + 1} in a "
                   "segment with metered tokens between them")
        if rows and metered < len(rows):
            refusal += (f"; {metered} of {len(rows)} rows have metered tokens, and a fit needs {MIN_ROWS} and "
                        f"{MIN_METERED_FRACTION:.0%}")
    return TickReport(window_h=window_h, crossings=cross, fits=fits, scoped=scoped, scoped_crossings=scoped_cross,
                      refusal=refusal)


# ── view ─────────────────────────────────────────────────────────────────────

def _clock(t: float) -> str:
    return datetime.fromtimestamp(t).strftime("%m-%d %H:%M")


def _est(e: Estimate) -> str:
    return f"{e.value:.3g}  ({e.low:.2g} to {e.high:.2g})"


def format_report(rep: TickReport, show: int = 12) -> str:
    c = rep.crossings
    out = [f"ticks, last {rep.window_h:g}h",
           f"weekly_all: {len(c.ticks)} crossings, {c.segments} segment{'s' if c.segments != 1 else ''}"]
    out += [f"  {n}" for n in _notes(c)]
    for t in c.ticks[-show:]:
        out.append(f"  {t.level:>3} {_clock(t.t_mid)} +-{t.width / 120:.0f}m{' wide' if t.quality == 'wide' else ''}")
    if len(c.ticks) > show:
        out.append(f"  ... {len(c.ticks) - show} earlier")
    if rep.refusal:
        out += ["", f"no fit: {rep.refusal}",
                f"provisional {usage_meter.POINTS_PER_WEIGHTED_TOKEN:.3g} points/token"]
    for cr, f in rep.fits.items():
        out += ["", f"cache read x{cr:g}: {f.ticks} rows",
                f"  rms residual {f.rms_residual:.2f} points"]
        out += [textwrap.fill(n, 58, initial_indent="  note: ", subsequent_indent="    ") for n in f.notes]
        out += [f"  scale  {_est(f.scale)}",
                "  per weighted token, 90%:"]
        out += [f"   {m.removeprefix('claude-')[:14]:<14} {_est(e)}" for m, e in f.rates.items()]
        out += [f"  drift  {_est(f.drift)} pt/h",
                f"  blended {f.blended_rate:.3g}  (provisional {usage_meter.POINTS_PER_WEIGHTED_TOKEN:.3g})"]
    for s in rep.scoped:
        out += ["", f"scoped {s.pool}: {s.ticks} rows, x{s.cache_read_weight:g}",
                f"  rate   {_est(s.rate)}",
                f"  drift  {_est(s.drift)} pt/h",
                f"  rms residual {s.rms_residual:.2f}"]
        if s.joint_rate is not None:
            out.append(f"  joint rate, same models {s.joint_rate:.3g}")
    for sc in rep.scoped_crossings:
        if not any(s.pool == sc.series for s in rep.scoped):
            out += ["", f"scoped {sc.series}: {len(sc.ticks)} crossings, too few to fit"]
    out.append("")
    out.append("priors are defaults to be confirmed, not facts")
    return "\n".join(out)


def run_ticks(since_spec: str = "48h") -> str:
    from macf.cli import _parse_since
    now = time.time()
    return format_report(analyse((now - _parse_since(since_spec)) / HOUR, now))

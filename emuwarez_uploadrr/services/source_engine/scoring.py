"""Combines evidence into per-candidate scores and picks a winner.

Never returns "unknown" (spec section 17-19): every one of the 9 candidates
always gets a raw_score and a normalized_score, and the highest raw_score
wins regardless of how close the race is — closeness is communicated via
`margin`/`certainty`, not by withholding a winner.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .constants import CANDIDATES, certainty_label
from .evidence import Evidence

# A small structural floor so every candidate survives softmax normalization
# with a non-zero (if tiny) percentage — spec section 18: the floor is not
# evidence, just enough to keep every candidate visible in the ranking.
_FLOOR = -60.0
# Softmax temperature: higher = flatter (closer) distribution. Chosen so a
# ~20-point raw-score gap between two candidates lands around a clearly
# "high" confidence gap rather than a barely-visible one.
_TEMPERATURE = 18.0


@dataclass
class CandidateScore:
    label: str
    positive_score: float
    negative_score: float
    raw_score: float
    normalized_score: float
    ranking_position: int


@dataclass
class ScoringResult:
    ranking: list[CandidateScore]
    winner: CandidateScore
    runner_up: CandidateScore
    margin_pp: float
    margin_raw: float
    certainty: str
    evidence_strength: float


def score_candidates(evidence: list[Evidence]) -> ScoringResult:
    positive = {c: 0.0 for c in CANDIDATES}
    negative = {c: 0.0 for c in CANDIDATES}
    for ev in evidence:
        for cand, val in ev.effective().items():
            if val >= 0:
                positive[cand] += val
            else:
                negative[cand] += val

    raw = {c: max(positive[c] + negative[c], _FLOOR) for c in CANDIDATES}

    # Softmax normalization: negative raw scores are fine (that's the point —
    # a weak/contradictory candidate should still get *some* share), and the
    # result always sums to ~100%.
    scaled = {c: raw[c] / _TEMPERATURE for c in CANDIDATES}
    m = max(scaled.values())
    exp = {c: math.exp(v - m) for c, v in scaled.items()}
    total = sum(exp.values()) or 1.0
    normalized = {c: exp[c] / total for c in CANDIDATES}

    ordered = sorted(CANDIDATES, key=lambda c: raw[c], reverse=True)
    ranking = [
        CandidateScore(
            label=c, positive_score=positive[c], negative_score=negative[c],
            raw_score=raw[c], normalized_score=normalized[c], ranking_position=i + 1,
        )
        for i, c in enumerate(ordered)
    ]

    winner, runner_up = ranking[0], ranking[1]
    margin_pp = (winner.normalized_score - runner_up.normalized_score) * 100.0
    margin_raw = winner.raw_score - runner_up.raw_score
    certainty = certainty_label(margin_pp)

    # A rough "how much evidence did we actually have" signal — more entries
    # with higher reliability/strength = more confidence in the whole result,
    # independent of how close the race between candidates ended up being.
    total_weight = sum(
        {"weak": 0.35, "medium": 0.7, "strong": 1.0, "very_strong": 1.35}.get(e.strength, 0.7) * e.reliability
        for e in evidence
    )
    evidence_strength = max(0.0, min(1.0, total_weight / 12.0))

    return ScoringResult(
        ranking=ranking, winner=winner, runner_up=runner_up,
        margin_pp=margin_pp, margin_raw=margin_raw,
        certainty=certainty, evidence_strength=evidence_strength,
    )


def top_contributors(evidence: list[Evidence], candidate: str, *, n: int = 3, against: str | None = None) -> list[Evidence]:
    """The evidence entries that most favor `candidate` — or, if `against` is
    given, that most favor `candidate` over `against` (used for the
    winner-vs-runner-up explanation)."""
    def key(e: Evidence) -> float:
        eff = e.effective()
        if against:
            return eff.get(candidate, 0.0) - eff.get(against, 0.0)
        return eff.get(candidate, 0.0)

    ranked = sorted(evidence, key=key, reverse=True)
    return [e for e in ranked if key(e) > 0.5][:n]


def build_explanation(evidence: list[Evidence], result: ScoringResult) -> dict:
    winner_label = result.winner.label
    runner_label = result.runner_up.label

    winner_reasons = top_contributors(evidence, winner_label, n=3)
    comparative_reasons = top_contributors(evidence, winner_label, against=runner_label, n=2)

    if winner_reasons:
        winner_text = (
            f"{winner_label} obtiene la puntuación más alta porque " +
            "; ".join(e.explanation.rstrip(".") for e in winner_reasons) + "."
        )
    else:
        winner_text = (
            f"{winner_label} queda primero por descarte: ningún candidato acumula evidencia fuerte, "
            "y es el que menos contradicciones estructurales presenta."
        )

    if comparative_reasons:
        vs_text = (
            f"Supera a {runner_label} principalmente porque " +
            "; ".join(e.explanation.rstrip(".") for e in comparative_reasons) + "."
        )
    else:
        vs_text = (
            f"El margen sobre {runner_label} es pequeño ({result.margin_pp:.1f} puntos): "
            "la evidencia disponible no distingue con claridad entre ambos."
        )

    return {"winner": winner_text, "winner_vs_runner_up": vs_text}


def find_contradictions(evidence: list[Evidence], result: ScoringResult) -> list[str]:
    """Evidence that pointed strongly at a DIFFERENT candidate than the
    winner — surfaced so the UI can show "yes, but note that..."."""
    out: list[str] = []
    winner = result.winner.label
    for e in evidence:
        eff = e.effective()
        best_other = max((c for c in CANDIDATES if c != winner), key=lambda c: eff.get(c, 0.0), default=None)
        if best_other and eff.get(best_other, 0.0) - eff.get(winner, 0.0) > 8.0:
            out.append(f"{e.explanation} (favorece más a {best_other} que a {winner})")
    return out

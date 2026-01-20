"""
Data models for hybrid search results and retriever scores.
"""

from dataclasses import dataclass, field, asdict
from typing import Literal


@dataclass
class RetrieverScore:
    """Score from a single retriever with explanation."""
    retriever: str
    rank: int  # 1-indexed rank (0 = not found)
    raw_score: float  # Original score (BM25 or cosine)
    rrf_contribution: float  # 1/(k + rank) contribution
    matched_text: str = ""  # What matched (keyword, question text, etc.)


@dataclass
class ExplainedRecommendation:
    """A recommendation with full explanation metadata."""
    policy_name: str
    rrf_score: float
    confidence_tier: Literal["CRITICAL", "HIGH", "MEDIUM"]
    retriever_contributions: dict[str, RetrieverScore] = field(default_factory=dict)
    keywords_matched: list[tuple[str, float]] = field(default_factory=list)
    questions_matched: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "policy_name": self.policy_name,
            "rrf_score": round(self.rrf_score, 4),
            "confidence_tier": self.confidence_tier,
            "retriever_contributions": {
                k: asdict(v) for k, v in self.retriever_contributions.items()
            },
            "keywords_matched": self.keywords_matched,
            "questions_matched": self.questions_matched,
        }

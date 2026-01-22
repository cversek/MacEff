"""
Data models for hybrid search results and retriever scores.
"""

from dataclasses import dataclass, field, asdict
from typing import Literal


@dataclass
class MatchedKeyword:
    """A keyword extracted from the query with boost score."""
    keyword: str
    boost: float  # 1.0 = normal, 2.0 = ALL_CAPS boosted

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "keyword": self.keyword,
            "boost": round(self.boost, 2),
        }


@dataclass
class MatchedQuestion:
    """A CEP question that matched the query with section targeting info."""
    question_text: str
    section_number: int
    section_header: str
    policy_name: str
    distance: float  # LanceDB distance (lower = better match)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "question_text": self.question_text,
            "section_number": self.section_number,
            "section_header": self.section_header,
            "policy_name": self.policy_name,
            "distance": round(self.distance, 4),
        }


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
    score: float
    confidence_tier: Literal["CRITICAL", "HIGH", "MEDIUM"]
    retriever_contributions: dict[str, RetrieverScore] = field(default_factory=dict)
    keywords_matched: list[tuple[str, float]] = field(default_factory=list)
    matched_questions: list[MatchedQuestion] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "policy_name": self.policy_name,
            "score": round(self.score, 4),
            "confidence_tier": self.confidence_tier,
            "retriever_contributions": {
                k: asdict(v) for k, v in self.retriever_contributions.items()
            },
            "keywords_matched": self.keywords_matched,
            "matched_questions": [mq.to_dict() for mq in self.matched_questions],
        }

#!/usr/bin/env python3
"""
policy-recommend.py - Hybrid search with LanceDB backend

Migrated from sqlite-vec to LanceDB for ARM64 compatibility and native hybrid search.

Usage (from UserPromptSubmit hook):
    echo '{"prompt": "How do I manage TODOs?"}' | python policy-recommend.py

Output:
    {"additionalContext": "...", "explanations": [...]}

Target: <100ms execution time
"""

import json
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Literal, Optional

from ..hybrid_search.lancedb_search import LanceDBPolicySearch
from .paths import find_agent_home


def get_policy_db_path() -> Path:
    """Get path to policy index using portable path resolution."""
    agent_home = find_agent_home()
    return agent_home / ".maceff" / "policy_index.lance"


# Configuration
DB_PATH: Optional[Path] = None


def _get_db_path() -> Path:
    """Lazy accessor for DB_PATH with portable resolution."""
    global DB_PATH
    if DB_PATH is None:
        DB_PATH = get_policy_db_path()
    return DB_PATH


EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# Thresholds for tiered output
CRITICAL_THRESHOLD = 0.70  # Similarity score for CRITICAL tier
HIGH_THRESHOLD = 0.55      # Similarity score for HIGH tier
LOW_THRESHOLD = 0.30       # Minimum for any suggestion

MAX_RESULTS = 5
MIN_QUERY_LENGTH = 10

# Lazy-loaded searcher
_searcher: Optional[LanceDBPolicySearch] = None


def get_searcher() -> LanceDBPolicySearch:
    """Lazy load the LanceDB searcher."""
    global _searcher
    if _searcher is None:
        db_path = _get_db_path()
        _searcher = LanceDBPolicySearch(db_path, model_name=EMBEDDING_MODEL)
    return _searcher


@dataclass
class RetrieverScore:
    """Score from a single retriever with explanation."""
    retriever: str
    rank: int  # 1-indexed rank (0 = not found)
    raw_score: float  # Similarity score
    rrf_contribution: float  # 1/(k + rank) contribution
    matched_text: str = ""  # What matched


@dataclass
class ExplainedRecommendation:
    """A policy recommendation with full explanation metadata."""
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


def extract_keywords(prompt: str) -> list[tuple[str, float]]:
    """Extract meaningful keywords from prompt with ALL_CAPS boosting."""
    stop_words = {
        'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
        'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
        'should', 'may', 'might', 'must', 'can', 'this', 'that', 'these',
        'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they', 'what', 'which',
        'who', 'whom', 'how', 'when', 'where', 'why', 'if', 'then', 'else',
        'for', 'of', 'to', 'from', 'in', 'on', 'at', 'by', 'with', 'about',
        'into', 'through', 'during', 'before', 'after', 'above', 'below',
        'and', 'or', 'but', 'not', 'so', 'as', 'than', 'too', 'very', 'just',
        'also', 'now', 'here', 'there', 'all', 'any', 'both', 'each', 'more',
        'most', 'other', 'some', 'such', 'no', 'nor', 'only', 'own', 'same',
        'tell', 'me', 'please', 'help', 'need', 'want', 'know', 'think',
    }

    caps_words = re.findall(r'\b[A-Z]{2,}\b', prompt)
    regular_words = re.findall(r'\b[a-zA-Z]{3,}\b', prompt.lower())

    keywords = []
    seen = set()

    for w in caps_words:
        w_lower = w.lower()
        if w_lower not in seen and w_lower not in stop_words:
            seen.add(w_lower)
            keywords.append((w_lower, 3.0))

    for w in regular_words:
        if w not in seen and w not in stop_words:
            seen.add(w)
            keywords.append((w, 1.0))

    return keywords[:10]


def search_with_lancedb(query: str, limit: int = 5) -> list[ExplainedRecommendation]:
    """
    Search using LanceDB native hybrid search.

    Replaces 4-retriever RRF fusion with LanceDB's built-in capabilities.
    """
    searcher = get_searcher()
    keywords = extract_keywords(query)

    # Use LanceDB hybrid search (vector + FTS)
    result = searcher.hybrid_search(query, limit=limit)

    recommendations = []
    for idx, r in enumerate(result['results'], start=1):
        similarity = r['similarity']

        # Determine confidence tier based on similarity
        if similarity >= CRITICAL_THRESHOLD:
            tier = "CRITICAL"
        elif similarity >= HIGH_THRESHOLD:
            tier = "HIGH"
        else:
            tier = "MEDIUM"

        # Create retriever score for explanation
        retriever_score = RetrieverScore(
            retriever="lancedb_hybrid",
            rank=idx,
            raw_score=similarity,
            rrf_contribution=r.get('rrf_score', 0),
            matched_text=f"similarity: {similarity:.2f}"
        )

        rec = ExplainedRecommendation(
            policy_name=r['policy_name'],
            rrf_score=r.get('rrf_score', similarity),  # Use similarity as proxy
            confidence_tier=tier,
            retriever_contributions={"lancedb_hybrid": retriever_score},
            keywords_matched=keywords[:5],
            questions_matched=[],  # LanceDB doesn't expose matched questions directly
        )
        recommendations.append(rec)

    return recommendations


def format_output(recommendations: list[ExplainedRecommendation]) -> str:
    """Format recommendations as ranked list for hook injection.

    Visual markers:
    🥇🥈🥉 = Top 3 ranks
    🎯 = CRITICAL tier (high confidence)
    📜 = HIGH tier
    📋 = MEDIUM tier
    """
    if not recommendations:
        return ""

    rank_emoji = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
    tier_emoji = {"CRITICAL": "🎯", "HIGH": "📜", "MEDIUM": "📋"}

    lines = ["📚 Policy Recommendations (LanceDB Hybrid Search):"]

    for i, rec in enumerate(recommendations[:5]):
        rank = rank_emoji[i] if i < len(rank_emoji) else f"#{i+1}"
        tier = tier_emoji.get(rec.confidence_tier, "📋")

        # Main line: rank + tier + name + score
        lines.append(f"{rank} {tier} {rec.policy_name.upper()} ({rec.rrf_score:.3f})")

    # CLI hint for top result
    if recommendations:
        lines.append(f"  → macf_tools policy navigate {recommendations[0].policy_name}")

    return "\n".join(lines)


def format_verbose_output(explanations: list[dict], query: str = "") -> str:
    """Format explanations with full retriever breakdown for --explain mode."""
    if not explanations:
        return "No recommendations found."

    rank_emoji = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
    tier_emoji = {"CRITICAL": "🎯", "HIGH": "📜", "MEDIUM": "📋"}

    lines = []
    if query:
        lines.append(f'Policy Recommendations for: "{query}"')
        lines.append("=" * 60)

    for i, rec in enumerate(explanations):
        rank = rank_emoji[i] if i < len(rank_emoji) else f"#{i+1}"
        tier = tier_emoji.get(rec.get('confidence_tier', 'MEDIUM'), '📋')
        name = rec.get('policy_name', 'unknown').upper()
        score = rec.get('rrf_score', 0)

        lines.append(f"\n{rank} {tier} {name} (Score: {score:.4f})")

        # Show retriever contributions
        contributions = rec.get('retriever_contributions', {})
        if contributions:
            lines.append("   Retrievers:")
            for ret_name, ret_data in contributions.items():
                ret_rank = ret_data.get('rank', 0)
                matched = ret_data.get('matched_text', '')[:40]
                lines.append(f"     {ret_name}: rank {ret_rank} - {matched}")

    if explanations:
        lines.append("\n" + "=" * 60)
        lines.append(f"💡 macf_tools policy navigate {explanations[0].get('policy_name', 'unknown')}")

    return "\n".join(lines)


def get_recommendations(prompt: str) -> tuple[str, list[dict]]:
    """
    Get hybrid recommendations with explanations.

    Returns (formatted_output, explanations_list).
    """
    keywords = extract_keywords(prompt)
    if not keywords:
        return "", []

    db_path = _get_db_path()
    if not db_path.exists():
        print(
            f"⚠️ MACF: Policy index not found at {db_path}\n"
            f"   Run: macf_tools policy build_index",
            file=sys.stderr
        )
        return "", []

    try:
        recommendations = search_with_lancedb(prompt, limit=MAX_RESULTS)

        # Note: LanceDB returns distance scores (lower = better), not similarity
        # RRF ranking already handles relevance, so we don't filter by raw score
        if not recommendations:
            return "", []

        # Format output
        formatted = format_output(recommendations)
        explanations = [r.to_dict() for r in recommendations]

        return formatted, explanations

    except Exception as e:
        print(f"⚠️ MACF: Search error: {e}", file=sys.stderr)
        return "", []


def get_policy_recommendation(
    prompt: str,
    db_path: Optional[Path] = None,
    limit: int = MAX_RESULTS,
    explain: bool = False
) -> dict:
    """
    Public API for policy recommendations.

    Args:
        prompt: User query text
        db_path: Optional override for index path
        limit: Maximum results
        explain: Include verbose explanations

    Returns:
        Dict with additionalContext and optional explanations
    """
    global DB_PATH
    if db_path:
        DB_PATH = db_path

    formatted, explanations = get_recommendations(prompt)

    output = {
        "additionalContext": formatted,
    }

    if explain and explanations:
        output["explanations"] = explanations

    return output


def main():
    """Main entry point - read stdin, query policies, output JSON."""
    try:
        stdin_data = sys.stdin.read()
        if not stdin_data.strip():
            print(json.dumps({"continue": True}))
            return

        input_json = json.loads(stdin_data)
        prompt = input_json.get("prompt", "")

        if len(prompt) < MIN_QUERY_LENGTH:
            print(json.dumps({"continue": True}))
            return

        formatted, explanations = get_recommendations(prompt)

        if not formatted:
            print(json.dumps({"continue": True}))
            return

        output = {
            "continue": True,
            "additionalContext": formatted,
        }

        # Include explanations for debugging/learning
        if explanations:
            output["explanations"] = explanations

        print(json.dumps(output))

    except json.JSONDecodeError:
        print(json.dumps({"continue": True}))
    except Exception:
        print(json.dumps({"continue": True}))


if __name__ == "__main__":
    main()

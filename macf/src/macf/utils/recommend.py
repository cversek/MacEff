#!/usr/bin/env python3
"""
policy-recommend.py - Hybrid search with RRF scoring and explainability

Phase 3 (MISSION): Reciprocal Rank Fusion combining 4 retrievers:
1. FTS5 BM25 on policies_fts
2. FTS5 BM25 on questions_fts
3. Cosine similarity on policy_embeddings
4. Cosine similarity on question_embeddings

Each recommendation carries ExplainedRecommendation metadata showing
WHY it matched - enabling learning and debugging.

Usage (from UserPromptSubmit hook):
    echo '{"prompt": "How do I manage TODOs?"}' | python policy-recommend.py

Output:
    {"additionalContext": "...", "explanations": [...]}

Target: <100ms execution time (embedding lookup ~15ms)
"""

import json
import re
import sqlite3
import struct
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Literal, Optional

import sqlite_vec
from sentence_transformers import SentenceTransformer

from .paths import find_agent_home


def get_policy_db_path() -> Path:
    """Get path to policy_index.db using portable path resolution."""
    agent_home = find_agent_home()
    return agent_home / ".maceff" / "policy_index.db"


# Configuration (lazy - computed on first use)
DB_PATH: Optional[Path] = None


def _get_db_path() -> Path:
    """Lazy accessor for DB_PATH with portable resolution."""
    global DB_PATH
    if DB_PATH is None:
        DB_PATH = get_policy_db_path()
    return DB_PATH
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384

# RRF constant (standard value from literature)
RRF_K = 60

# Thresholds for tiered output
CRITICAL_THRESHOLD = 0.025  # RRF score for CRITICAL tier
HIGH_THRESHOLD = 0.015      # RRF score for HIGH tier
LOW_THRESHOLD = 0.008       # Minimum for any suggestion

MAX_RESULTS = 5
MIN_QUERY_LENGTH = 10

# Lazy-loaded model
_model: Optional[SentenceTransformer] = None


def get_model() -> SentenceTransformer:
    """Lazy load the embedding model."""
    global _model
    if _model is None:
        _model = SentenceTransformer(EMBEDDING_MODEL)
    return _model


def serialize_f32(vector: list[float]) -> bytes:
    """Serialize a float32 vector for sqlite-vec query."""
    return struct.pack(f'{len(vector)}f', *vector)


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


def build_fts_query(keywords: list[tuple[str, float]]) -> str:
    """Build FTS5 query string with weighted keywords."""
    query_parts = []
    for word, weight in keywords:
        if weight > 1:
            query_parts.extend([word] * int(weight))
        else:
            query_parts.append(word)
    return " OR ".join(query_parts)


def normalize_bm25(bm25_score: float) -> float:
    """Normalize BM25 score to 0-1 range."""
    if bm25_score >= 0:
        return 0.0
    return min(1.0, max(0.0, -bm25_score / 20))


# =============================================================================
# RETRIEVER 1: FTS5 on policies_fts
# =============================================================================

def search_policies_fts(keywords: list[tuple[str, float]], conn: sqlite3.Connection) -> dict[str, RetrieverScore]:
    """Retriever 1: FTS5 BM25 search on policies."""
    results = {}
    if not keywords:
        return results

    try:
        cursor = conn.cursor()
        fts_query = build_fts_query(keywords)

        cursor.execute("""
            SELECT policy_name, bm25(policies_fts) as score
            FROM policies_fts
            WHERE policies_fts MATCH ?
            ORDER BY score
            LIMIT 20
        """, (fts_query,))

        for rank, row in enumerate(cursor.fetchall(), start=1):
            policy_name = row[0]
            raw_score = row[1]
            rrf_contrib = 1.0 / (RRF_K + rank)

            results[policy_name] = RetrieverScore(
                retriever="policies_fts",
                rank=rank,
                raw_score=normalize_bm25(raw_score),
                rrf_contribution=rrf_contrib,
                matched_text=fts_query[:50]
            )

    except sqlite3.Error:
        pass

    return results


# =============================================================================
# RETRIEVER 2: FTS5 on questions_fts
# =============================================================================

def search_questions_fts(keywords: list[tuple[str, float]], conn: sqlite3.Connection) -> tuple[dict[str, RetrieverScore], dict[str, list[str]]]:
    """Retriever 2: FTS5 BM25 search on CNG questions.

    Returns (policy_scores, matched_questions_by_policy).
    """
    results = {}
    matched_questions: dict[str, list[str]] = {}

    if not keywords:
        return results, matched_questions

    try:
        cursor = conn.cursor()
        fts_query = build_fts_query(keywords)

        cursor.execute("""
            SELECT policy_name, question_text, section_number, bm25(questions_fts) as score
            FROM questions_fts
            WHERE questions_fts MATCH ?
            ORDER BY score
            LIMIT 30
        """, (fts_query,))

        # Group by policy, use best question rank
        policy_ranks: dict[str, tuple[int, float, str]] = {}  # policy -> (rank, score, question)

        for rank, row in enumerate(cursor.fetchall(), start=1):
            policy_name = row[0]
            question_text = row[1]
            section_num = row[2]
            raw_score = row[3]

            # Track matched questions
            if policy_name not in matched_questions:
                matched_questions[policy_name] = []
            matched_questions[policy_name].append(f"{question_text} (§{section_num})")

            # Use first (best) rank for each policy
            if policy_name not in policy_ranks:
                policy_ranks[policy_name] = (rank, raw_score, question_text)

        # Convert to RetrieverScores
        for policy_name, (rank, raw_score, question) in policy_ranks.items():
            rrf_contrib = 1.0 / (RRF_K + rank)
            results[policy_name] = RetrieverScore(
                retriever="questions_fts",
                rank=rank,
                raw_score=normalize_bm25(raw_score),
                rrf_contribution=rrf_contrib,
                matched_text=question[:80]
            )

    except sqlite3.Error:
        pass

    return results, matched_questions


# =============================================================================
# RETRIEVER 3: Semantic search on policy_embeddings
# =============================================================================

def search_policies_semantic(query_embedding: bytes, conn: sqlite3.Connection) -> dict[str, RetrieverScore]:
    """Retriever 3: Semantic search on policy embeddings."""
    results = {}

    try:
        cursor = conn.cursor()

        # sqlite-vec KNN query with k= constraint
        cursor.execute("""
            SELECT
                pe.rowid,
                pem.policy_name,
                pe.distance
            FROM policy_embeddings pe
            JOIN policy_embedding_map pem ON pe.rowid = pem.rowid
            WHERE pe.embedding MATCH ? AND k = 20
            ORDER BY pe.distance
        """, (query_embedding,))

        for rank, row in enumerate(cursor.fetchall(), start=1):
            policy_name = row[1]
            distance = row[2]
            # Convert distance to similarity (cosine distance -> similarity)
            similarity = max(0, 1 - distance)
            rrf_contrib = 1.0 / (RRF_K + rank)

            results[policy_name] = RetrieverScore(
                retriever="policy_embeddings",
                rank=rank,
                raw_score=round(similarity, 3),
                rrf_contribution=rrf_contrib,
                matched_text=f"semantic similarity: {similarity:.2f}"
            )

    except sqlite3.Error:
        pass

    return results


# =============================================================================
# RETRIEVER 4: Semantic search on question_embeddings
# =============================================================================

def search_questions_semantic(query_embedding: bytes, conn: sqlite3.Connection) -> tuple[dict[str, RetrieverScore], dict[str, list[str]]]:
    """Retriever 4: Semantic search on question embeddings.

    Returns (policy_scores, matched_questions_by_policy).
    """
    results = {}
    matched_questions: dict[str, list[str]] = {}

    try:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                qe.rowid,
                qem.policy_name,
                qem.question_id,
                qe.distance
            FROM question_embeddings qe
            JOIN question_embedding_map qem ON qe.rowid = qem.rowid
            WHERE qe.embedding MATCH ? AND k = 30
            ORDER BY qe.distance
        """, (query_embedding,))

        # Group by policy, use best question rank
        policy_ranks: dict[str, tuple[int, float]] = {}

        for rank, row in enumerate(cursor.fetchall(), start=1):
            policy_name = row[1]
            question_id = row[2]
            distance = row[3]
            similarity = max(0, 1 - distance)

            # Track for explanation
            if policy_name not in matched_questions:
                matched_questions[policy_name] = []
            matched_questions[policy_name].append(f"[semantic] {question_id}")

            if policy_name not in policy_ranks:
                policy_ranks[policy_name] = (rank, similarity)

        for policy_name, (rank, similarity) in policy_ranks.items():
            rrf_contrib = 1.0 / (RRF_K + rank)
            results[policy_name] = RetrieverScore(
                retriever="question_embeddings",
                rank=rank,
                raw_score=round(similarity, 3),
                rrf_contribution=rrf_contrib,
                matched_text=f"semantic similarity: {similarity:.2f}"
            )

    except sqlite3.Error:
        pass

    return results, matched_questions


# =============================================================================
# RRF FUSION
# =============================================================================

def fuse_with_rrf(
    policies_fts: dict[str, RetrieverScore],
    questions_fts: dict[str, RetrieverScore],
    policies_semantic: dict[str, RetrieverScore],
    questions_semantic: dict[str, RetrieverScore],
    keywords: list[tuple[str, float]],
    fts_questions: dict[str, list[str]],
    semantic_questions: dict[str, list[str]],
) -> list[ExplainedRecommendation]:
    """Fuse results from 4 retrievers using Reciprocal Rank Fusion.

    RRF_score(d) = Σ 1/(k + rank_i(d))

    Each policy gets contributions from retrievers that found it.
    """
    # Collect all policy names
    all_policies = set()
    all_policies.update(policies_fts.keys())
    all_policies.update(questions_fts.keys())
    all_policies.update(policies_semantic.keys())
    all_policies.update(questions_semantic.keys())

    recommendations = []

    for policy_name in all_policies:
        # Sum RRF contributions
        rrf_score = 0.0
        contributions = {}

        if policy_name in policies_fts:
            score = policies_fts[policy_name]
            rrf_score += score.rrf_contribution
            contributions["policies_fts"] = score

        if policy_name in questions_fts:
            score = questions_fts[policy_name]
            rrf_score += score.rrf_contribution
            contributions["questions_fts"] = score

        if policy_name in policies_semantic:
            score = policies_semantic[policy_name]
            rrf_score += score.rrf_contribution
            contributions["policy_embeddings"] = score

        if policy_name in questions_semantic:
            score = questions_semantic[policy_name]
            rrf_score += score.rrf_contribution
            contributions["question_embeddings"] = score

        # Determine confidence tier based on RRF score and retriever count
        num_retrievers = len(contributions)
        if rrf_score >= CRITICAL_THRESHOLD and num_retrievers >= 3:
            tier = "CRITICAL"
        elif rrf_score >= HIGH_THRESHOLD and num_retrievers >= 2:
            tier = "HIGH"
        else:
            tier = "MEDIUM"

        # Collect matched questions from both FTS and semantic
        questions_matched = []
        if policy_name in fts_questions:
            questions_matched.extend(fts_questions[policy_name][:3])
        if policy_name in semantic_questions:
            questions_matched.extend(semantic_questions[policy_name][:2])

        rec = ExplainedRecommendation(
            policy_name=policy_name,
            rrf_score=rrf_score,
            confidence_tier=tier,
            retriever_contributions=contributions,
            keywords_matched=keywords[:5],
            questions_matched=questions_matched[:5],
        )
        recommendations.append(rec)

    # Sort by RRF score descending
    recommendations.sort(key=lambda r: r.rrf_score, reverse=True)

    return recommendations[:MAX_RESULTS]


# =============================================================================
# OUTPUT FORMATTING
# =============================================================================

def format_recommendation(rec: ExplainedRecommendation, verbose: bool = False) -> str:
    """Format a single recommendation for display."""
    tier_emoji = {"CRITICAL": "🎯", "HIGH": "📜", "MEDIUM": "📋"}
    emoji = tier_emoji.get(rec.confidence_tier, "📋")

    lines = [f"{emoji} Policy Match: {rec.policy_name.upper()} ({rec.rrf_score:.3f})"]
    lines.append(f"  macf_tools policy navigate {rec.policy_name}")

    if verbose:
        # Show retriever breakdown
        for name, score in rec.retriever_contributions.items():
            lines.append(f"    {name}: rank {score.rank} (+{score.rrf_contribution:.4f})")

        # Show matched questions
        if rec.questions_matched:
            lines.append(f"    Questions: {rec.questions_matched[0][:60]}...")

    return "\n".join(lines)


def format_output(recommendations: list[ExplainedRecommendation]) -> str:
    """Format ALL recommendations as ranked list for hook injection.

    additionalContext is ephemeral (zero token cost, not persisted),
    so we show full ranked list to support learning, trust, and
    effective user-agent collaboration.

    Visual markers help users track relevance at a glance:
    🥇🥈🥉 = Top 3 ranks
    🎯 = CRITICAL tier (high confidence)
    📜 = HIGH tier
    📋 = MEDIUM tier
    ✦ = 4 retrievers agreed
    """
    if not recommendations:
        return ""

    rank_emoji = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
    tier_emoji = {"CRITICAL": "🎯", "HIGH": "📜", "MEDIUM": "📋"}

    lines = ["📚 Policy Recommendations (RRF Hybrid Search):"]

    for i, rec in enumerate(recommendations[:5]):  # Show top 5
        rank = rank_emoji[i] if i < len(rank_emoji) else f"#{i+1}"
        tier = tier_emoji.get(rec.confidence_tier, "📋")
        num_r = len(rec.retriever_contributions)
        consensus = "✦" if num_r == 4 else f"({num_r}R)"

        # Main line: rank + tier + name + score + consensus
        lines.append(f"{rank} {tier} {rec.policy_name.upper()} ({rec.rrf_score:.3f}) {consensus}")

        # Matched question (full - additionalContext is ephemeral, no token cost)
        if rec.questions_matched:
            q = rec.questions_matched[0]
            lines.append(f"    └─ {q}")

    # CLI hint for top result
    if recommendations:
        lines.append(f"  → macf_tools policy navigate {recommendations[0].policy_name}")

    return "\n".join(lines)


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

def get_recommendations(prompt: str) -> tuple[str, list[dict]]:
    """Get hybrid RRF recommendations with explanations.

    Returns (formatted_output, explanations_list).
    """
    keywords = extract_keywords(prompt)
    if not keywords:
        return "", []

    db_path = _get_db_path()
    if not db_path.exists():
        import sys
        print(
            f"⚠️ MACF: Policy index not found at {db_path}\n"
            f"   Run: macf_tools policy build_index",
            file=sys.stderr
        )
        return "", []

    try:
        # Connect and enable sqlite-vec
        conn = sqlite3.connect(str(db_path), timeout=0.5)
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)

        # Generate query embedding
        model = get_model()
        query_embedding = model.encode(prompt)
        query_bytes = serialize_f32(query_embedding.tolist())

        # Run all 4 retrievers
        policies_fts = search_policies_fts(keywords, conn)
        questions_fts, fts_questions = search_questions_fts(keywords, conn)
        policies_semantic = search_policies_semantic(query_bytes, conn)
        questions_semantic, semantic_questions = search_questions_semantic(query_bytes, conn)

        conn.close()

        # Fuse with RRF
        recommendations = fuse_with_rrf(
            policies_fts, questions_fts,
            policies_semantic, questions_semantic,
            keywords, fts_questions, semantic_questions
        )

        # Filter by minimum threshold
        recommendations = [r for r in recommendations if r.rrf_score >= LOW_THRESHOLD]

        if not recommendations:
            return "", []

        # Format output
        formatted = format_output(recommendations)
        explanations = [r.to_dict() for r in recommendations]

        return formatted, explanations

    except Exception:
        return "", []


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

        # Include explanations for debugging/learning (can be omitted in production)
        if explanations:
            output["explanations"] = explanations

        print(json.dumps(output))

    except json.JSONDecodeError:
        print(json.dumps({"continue": True}))
    except Exception:
        print(json.dumps({"continue": True}))


if __name__ == "__main__":
    main()

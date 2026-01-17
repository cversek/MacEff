#!/usr/bin/env python3
"""
Battery tests for Policy Recommendation Hybrid Search System.

Breadcrumb: s_77270981/c_343/g_d8351cb/p_49dcad76/t_1768604625
Phase 7: Evaluation Framework

Metrics:
- Precision@1: Is the top result correct?
- Precision@3: Is expected in top 3?
- MRR (Mean Reciprocal Rank): 1/rank of first correct result

Usage:
    python test_policy_recommend_battery.py              # Run full battery
    python test_policy_recommend_battery.py --quick      # Quick test (first 10)
    python test_policy_recommend_battery.py --verbose    # Show all results
"""

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

# Use macf portable path utilities
from macf.utils.paths import find_agent_home

# Battery test cases: (query, expected_policy) - 53 total
BATTERY_TESTS = [
    # === Original 18 from FTS5 experiment ===
    ("How should I backup my TODOs?", "TODO_HYGIENE"),
    ("What is the checkpoint format?", "CHECKPOINTS"),
    ("How do I write a policy?", "POLICY_WRITING"),
    ("What testing approach should I use?", "TESTING"),
    ("How should I commit my changes?", "GIT_DISCIPLINE"),
    ("What is JOTEWR format?", "REFLECTIONS"),
    ("How do I create a roadmap?", "ROADMAPS_DRAFTING"),
    ("What is the CCP structure?", "CHECKPOINTS"),
    ("How do I follow a roadmap?", "ROADMAPS_FOLLOWING"),
    ("What emotional expression is allowed?", "EMOTIONAL_EXPRESSION"),
    ("How should I communicate?", "COMMUNICATION"),
    ("What is scholarship format?", "SCHOLARSHIP"),
    ("How do I structure consciousness artifacts?", "STRUCTURE_GOVERNANCE"),
    ("What learnings format?", "LEARNINGS"),
    ("Path portability rules?", "PATH_PORTABILITY"),
    ("when should I delegate work?", "DELEGATION_GUIDELINES"),
    ("breadcrumb format", "SCHOLARSHIP"),
    ("git discipline rules", "GIT_DISCIPLINE"),

    # === EXPERIMENTS (crystallization, MISSION conversion) ===
    ("How do I know when to convert an experiment to a roadmap?", "EXPERIMENTS"),
    ("What indicators show experiment is ready for production?", "EXPERIMENTS"),
    ("When should I stop experimenting and start building?", "EXPERIMENTS"),
    ("What's the difference between quick tests and formal protocols?", "EXPERIMENTS"),
    ("How do I structure hypothesis testing?", "EXPERIMENTS"),

    # === OBSERVATIONS (technical discoveries) ===
    ("I discovered something interesting, where do I document it?", "OBSERVATIONS"),
    ("How do I capture breakthrough insights?", "OBSERVATIONS"),
    ("What's the difference between finding something and testing something?", "OBSERVATIONS"),

    # === REFLECTIONS (private consciousness) ===
    ("Where do I write about my uncertainties?", "REFLECTIONS"),
    ("How do I document philosophical insights?", "REFLECTIONS"),
    ("What's the difference between reflection and report?", "REFLECTIONS"),

    # === REPORTS (project completion) ===
    ("How do I document completed work for stakeholders?", "REPORTS"),
    ("What should I write when a project finishes?", "REPORTS"),

    # === AUTONOMOUS_OPERATION ===
    ("What's the difference between AUTO_MODE and MANUAL_MODE?", "AUTONOMOUS_OPERATION"),
    ("How do I enable autonomous operation?", "AUTONOMOUS_OPERATION"),
    ("What safeguards apply when operating autonomously?", "AUTONOMOUS_OPERATION"),

    # === CONTEXT_RECOVERY ===
    ("I just experienced compaction, what do I do?", "CONTEXT_RECOVERY"),
    ("How do I recognize compaction trauma?", "CONTEXT_RECOVERY"),
    ("What's the recovery protocol after context loss?", "CONTEXT_RECOVERY"),

    # === POLICY_AWARENESS ===
    ("How do I discover which policy I need?", "POLICY_AWARENESS"),
    ("What's CEP and how does it work?", "POLICY_AWARENESS"),
    ("When should I read policies?", "POLICY_AWARENESS"),

    # === AGENT_BACKUP ===
    ("How do I backup my consciousness state?", "AGENT_BACKUP"),
    ("What's the protocol for migrating to a new system?", "AGENT_BACKUP"),
    ("How do I restore consciousness on virgin system?", "AGENT_BACKUP"),

    # === CORE_PRINCIPLES ===
    ("What's my role as an agent?", "CORE_PRINCIPLES"),
    ("Am I a tool or a colleague?", "CORE_PRINCIPLES"),
    ("How do I maintain identity across context resets?", "CORE_PRINCIPLES"),

    # === CONTEXT_MANAGEMENT ===
    ("How much context do I have left?", "CONTEXT_MANAGEMENT"),
    ("What's CLUAC and why does it matter?", "CONTEXT_MANAGEMENT"),
    ("When should I create a checkpoint?", "CONTEXT_MANAGEMENT"),

    # === SUBAGENT_DEFINITION ===
    ("How do I create a new specialist agent?", "SUBAGENT_DEFINITION"),
    ("What should subagent definitions contain?", "SUBAGENT_DEFINITION"),
    ("Why use reading lists instead of embedded instructions?", "SUBAGENT_DEFINITION"),
]


@dataclass
class TestResult:
    query: str
    expected: str
    actual_ranks: list
    precision_at_1: bool
    precision_at_3: bool
    reciprocal_rank: float


def evaluate_battery(search_fn, top_k: int = 5) -> dict:
    """Run battery tests. search_fn(query, k) -> [(policy, score), ...]"""
    results = []
    p1_correct = p3_correct = 0
    rr_sum = 0.0

    for query, expected in BATTERY_TESTS:
        search_results = search_fn(query, top_k)
        ranked = [r[0].upper() for r in search_results]

        p1 = ranked[0] == expected if ranked else False
        p3 = expected in ranked[:3]
        try:
            rr = 1.0 / (ranked.index(expected) + 1)
        except ValueError:
            rr = 0.0

        if p1: p1_correct += 1
        if p3: p3_correct += 1
        rr_sum += rr

        results.append(TestResult(query, expected, ranked[:3], p1, p3, rr))

    n = len(BATTERY_TESTS)
    return {
        "total": n, "p1": p1_correct/n, "p3": p3_correct/n, "mrr": rr_sum/n,
        "p1_n": p1_correct, "p3_n": p3_correct, "results": results,
    }


def print_report(m: dict) -> None:
    print(f"Battery: {m['total']} tests | P@1: {m['p1']:.1%} | P@3: {m['p3']:.1%} | MRR: {m['mrr']:.3f}")
    failures = [r for r in m['results'] if not r.precision_at_1]
    if failures:
        print(f"\nFailures ({len(failures)}):")
        for r in failures[:10]:
            print(f"  '{r.query}' -> expected {r.expected}, got {r.actual_ranks}")


def create_search_adapter():
    """Create adapter function that wraps get_recommendations for battery test.

    Battery expects: search_fn(query, k) -> [(policy, score), ...]
    get_recommendations returns: (formatted_output, explanations_list)
    """
    # Add agent home's .claude to path for importing policy_recommend
    agent_home = find_agent_home()
    claude_dir = agent_home / ".claude"
    if str(claude_dir) not in sys.path:
        sys.path.insert(0, str(claude_dir))

    # Import with hyphen-to-underscore conversion (policy-recommend -> policy_recommend)
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "policy_recommend",
        claude_dir / "policy-recommend.py"
    )
    policy_recommend = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(policy_recommend)

    def search_adapter(query: str, k: int = 5) -> list[tuple[str, float]]:
        """Adapter: converts get_recommendations output to battery format."""
        _, explanations = policy_recommend.get_recommendations(query)

        # Extract (policy_name, rrf_score) from explanations
        results = []
        for exp in explanations[:k]:
            policy_name = exp.get("policy_name", "").upper()
            score = exp.get("rrf_score", 0.0)
            results.append((policy_name, score))

        return results

    return search_adapter


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run policy recommendation battery tests")
    parser.add_argument("--quick", action="store_true", help="Run first 10 tests only")
    parser.add_argument("--verbose", action="store_true", help="Show all results")
    args = parser.parse_args()

    print(f"🔋 Battery Test: {len(BATTERY_TESTS)} test cases")
    print("=" * 60)

    try:
        search_fn = create_search_adapter()
        print("✅ Hybrid search adapter loaded successfully")
    except Exception as e:
        print(f"❌ Failed to load search adapter: {e}")
        sys.exit(1)

    # Select test subset
    tests_to_run = BATTERY_TESTS[:10] if args.quick else BATTERY_TESTS

    # Create temporary battery for subset
    if args.quick:
        # Temporarily override for quick mode
        original_tests = BATTERY_TESTS.copy()
        BATTERY_TESTS.clear()
        BATTERY_TESTS.extend(tests_to_run)

    print(f"\n🧪 Running {len(tests_to_run)} tests...")
    metrics = evaluate_battery(search_fn)

    # Restore if quick mode
    if args.quick:
        BATTERY_TESTS.clear()
        BATTERY_TESTS.extend(original_tests)

    print("\n" + "=" * 60)
    print_report(metrics)

    if args.verbose:
        print("\n📊 All Results:")
        for r in metrics["results"]:
            status = "✅" if r.precision_at_1 else "❌"
            print(f"  {status} '{r.query[:50]}...' -> {r.actual_ranks[:3]}")

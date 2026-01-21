"""
LanceDB Policy Indexer - Production implementation.

Builds a LanceDB index from MacEff framework policies for hybrid search.
Integrates with existing PolicyExtractor for metadata extraction.

Breadcrumb: s_77270981/c_356/g_a76f3cd/p_0c1e0209/t_1768946800
"""

import time
from pathlib import Path
from typing import Optional

import lancedb
from sentence_transformers import SentenceTransformer

from .extractors.policy_extractor import PolicyExtractor


def build_lancedb_index(
    policies_dir: Path,
    output_path: Path,
    model_name: str = "all-MiniLM-L6-v2",
    manifest_path: Optional[Path] = None,
) -> dict:
    """
    Build a LanceDB index from policy markdown files.

    Args:
        policies_dir: Directory containing policy markdown files
        output_path: Path to LanceDB directory (will be created)
        model_name: SentenceTransformer model name
        manifest_path: Optional path to manifest.json for keywords

    Returns:
        Stats dict with timing and counts
    """
    start_time = time.time()

    # Load embedding model
    print(f"Loading embedding model: {model_name}")
    model_load_start = time.time()
    model = SentenceTransformer(model_name)
    model_load_time = time.time() - model_load_start
    print(f"Model loaded in {model_load_time:.2f}s")

    # Initialize extractor
    extractor = PolicyExtractor(manifest_path=manifest_path)

    # Find all policy markdown files
    policy_files = list(policies_dir.rglob("*.md"))
    policy_files = [f for f in policy_files if extractor.should_index(f)]
    print(f"Found {len(policy_files)} policy files")

    # Extract content and generate embeddings
    documents = []
    for pf in policy_files:
        content = pf.read_text()
        doc_data = extractor.extract_document(pf)

        # Generate embedding text (combines description, keywords, questions)
        text_for_embedding = extractor.generate_embedding_text(doc_data)

        documents.append({
            'policy_name': doc_data['policy_name'],
            'tier': doc_data['tier'],
            'category': doc_data['category'],
            'description': doc_data['description'],
            'file_path': doc_data['file_path'],
            'content': text_for_embedding,  # Used for both FTS and embedding
        })

    if not documents:
        raise ValueError(f"No policies found in {policies_dir}")

    # Generate embeddings in batch
    print("Generating embeddings...")
    embed_start = time.time()
    texts = [d['content'] for d in documents]
    embeddings = model.encode(texts, show_progress_bar=True)
    embed_time = time.time() - embed_start
    print(f"Embeddings generated in {embed_time:.2f}s")

    # Add embeddings to documents
    for i, doc in enumerate(documents):
        doc['embedding'] = embeddings[i].tolist()

    # Create LanceDB database and table
    print(f"Creating LanceDB index at {output_path}")
    db = lancedb.connect(str(output_path))

    # Drop existing table if present
    if "policies" in db.table_names():
        db.drop_table("policies")

    table = db.create_table("policies", documents)

    total_time = time.time() - start_time

    stats = {
        'documents_indexed': len(documents),
        'embedding_dimension': len(embeddings[0]),
        'model_load_time_ms': model_load_time * 1000,
        'embed_time_ms': embed_time * 1000,
        'total_time_ms': total_time * 1000,
        'index_path': str(output_path),
    }

    print(f"\n=== Index Build Complete ===")
    print(f"Documents: {stats['documents_indexed']}")
    print(f"Embedding dim: {stats['embedding_dimension']}")
    print(f"Total time: {stats['total_time_ms']:.0f}ms")

    return stats


if __name__ == "__main__":
    # Default paths for CLI usage
    from .utils.paths import find_agent_home

    agent_home = find_agent_home()
    policies_dir = agent_home / ".maceff" / "framework" / "policies"
    output_path = agent_home / ".maceff" / "policy_index.lance"
    manifest_path = policies_dir / "manifest.json"

    if not policies_dir.exists():
        print(f"Policies directory not found: {policies_dir}")
        exit(1)

    print(f"Policies dir: {policies_dir}")
    print(f"Output path: {output_path}")

    stats = build_lancedb_index(
        policies_dir,
        output_path,
        manifest_path=manifest_path if manifest_path.exists() else None
    )

    print(f"\nIndex ready at: {output_path}")

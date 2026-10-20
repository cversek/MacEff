"""H8's extractor: the policy recommender's machinery pointed at the knowledge web.

The recommender (macf.utils.recommend) indexes each policy as one row whose EMBEDDING text is a
summary: its name, a description paragraph, manifest keywords and the first five CEP questions.
Its questions go to a second table that labels sections but ranks nothing. This extractor fills
the same AbstractExtractor slots from snapshot nodes, so the shipping BaseIndexer and PolicySearch
run unmodified over the web:
  - extract_document takes a snapshot node id, not a path: it reads the snapshot, never the live
    file, so the corpus can't move under the arm;
  - every text is stripped first by a Step 5a tier (strict, or clean after the second audit): no
    label and no concept tokens;
  - the id travels in the 'policy_name' field, because that is the key PolicySearch reads back;
  - keywords are empty unless with_concepts is set, which fills the slot with the node's concepts
    the way the manifest fills it for a policy (H8_hybrid_kw, a deliberate fusion arm).

Two findings about the shipping code shape what this rebuilds:
its hybrid call always fails and falls back to vector search, and BaseIndexer.build_index
overwrites the extractor's 'content' (5000 characters of policy, meant for FTS) with the summary.
So 'content' here holds the summary, as it does in production, and 'body' holds what the
extractor meant 'content' to hold.
"""
import re
import sys

from lib import HERE  # noqa: F401  (puts the MacEff checkout on sys.path)
from step5a_text import TIERS

from macf.hybrid_search.base_indexer import BaseIndexer
from macf.hybrid_search.extractors.base import AbstractExtractor

META = re.compile(r"^\s*(#|\*\*[^*]+\*\*:|---|\||```|<!--|-->|\[[^\]]*\]:)")
QUESTION = re.compile(r"^\s*(?:[-*>]|\d+\.)?\s*(?:\*\*)?(.+?\?)(?:\*\*)?\s*$")


def description(text):
    """The first prose paragraph: PolicyExtractor takes the paragraph under Purpose, or the first
    after the title. Artifacts open with metadata lines and headings instead, so skip those and
    take the first paragraph of 40 characters or more, cut at 500 as the policy extractor cuts."""
    para = []
    for line in text.splitlines() + [""]:
        if not line.strip() or META.match(line):
            if len(" ".join(para)) >= 40:
                desc = " ".join(para)
                return desc if len(desc) <= 500 else desc[:497] + "..."
            para = []
            continue
        para.append(line.strip())
    return ""


def questions(text, cap=30):
    """Lines that are questions, the closest thing an artifact has to a CEP guide."""
    out, seen = [], set()
    for line in text.splitlines():
        m = QUESTION.match(line)
        if m and 15 <= len(m.group(1)) <= 300 and m.group(1) not in seen:
            seen.add(m.group(1))
            out.append(m.group(1))
            if len(out) >= cap:
                break
    return out


class KWExtractor(AbstractExtractor):
    def __init__(self, corpus, with_concepts=False, tier="strict"):
        self.corpus = corpus
        self.with_concepts = with_concepts
        self.strip = TIERS[tier]
        self._strict = {}

    @property
    def name(self):
        return "knowledge_web"

    def strict(self, nid):
        if nid not in self._strict:
            self._strict[nid] = self.strip(self.corpus.nodes[nid]["text"])
        return self._strict[nid]

    def get_fts_columns(self):
        return [("policy_name", "TEXT"), ("title", "TEXT"), ("keywords", "TEXT"), ("description", "TEXT"),
                ("body", "TEXT")]

    def extract_document(self, doc_path):
        nid = str(doc_path)
        v, text = self.corpus.nodes[nid], self.strict(nid)
        return {"policy_name": nid, "type": v["type"], "title": v["title"],
                "keywords": " ".join(v["concepts"]) if self.with_concepts else "",
                "description": description(text), "questions": "\n".join(questions(text)),
                "body": text[:5000]}

    def generate_embedding_text(self, doc_data):
        """PolicyExtractor.generate_embedding_text, with the node's type where it writes Policy."""
        keywords = doc_data["keywords"].split()
        parts = [f"{doc_data['type']}: {doc_data['title']}",
                 f"Description: {doc_data['description']}" if doc_data["description"] else "",
                 f"Keywords: {', '.join(keywords)}" if keywords else ""]
        qs = doc_data["questions"].split("\n")[:5] if doc_data["questions"] else []
        if qs:
            parts.append(f"Questions: {' '.join(qs)}")
        return " ".join(p for p in parts if p)

    def extract_questions(self, content, doc_id):
        return [{"question_id": f"{doc_id}_{i}", "policy_name": doc_id, "section_header": "",
                 "section_number": 0, "question_text": q} for i, q in enumerate(questions(content), 1)]

    def should_index(self, doc_path):
        return bool(self.strict(str(doc_path)).strip())


def build_index(corpus, with_concepts=False, tier="strict", db_uri="memory://"):
    """Embed every snapshot node through the shipping BaseIndexer into an in-memory 'documents'
    table, add a 'questions' table as PolicyIndexer does, and index both FTS columns."""
    ex = KWExtractor(corpus, with_concepts=with_concepts, tier=tier)
    indexer = BaseIndexer(extractor=ex)
    docs = []
    for nid in sorted(corpus.nodes):
        if ex.should_index(nid):
            d = ex.extract_document(nid)
            docs.append({**d, "content": ex.generate_embedding_text(d)})   # as BaseIndexer.build_index does
    stats = indexer.index_documents(docs, db_uri)
    db = stats["db"]
    qrows = [q for d in docs for q in ex.extract_questions(ex.strict(d["policy_name"]), d["policy_name"])]
    if qrows:
        emb = indexer.model.encode([q["question_text"] for q in qrows], show_progress_bar=False)
        for q, e in zip(qrows, emb):
            q["embedding"] = e.tolist()
        db.create_table("questions", qrows)
    table = stats["table"]
    table.create_fts_index("content", replace=True)
    table.create_fts_index("body", replace=True)
    print(f"indexed {len(docs)} documents and {len(qrows)} questions", file=sys.stderr)
    return db, ex, {"documents": len(docs), "questions": len(qrows), "model": indexer.embedding_model_name,
                    "embedding_seconds": round(stats["embedding_time"], 1)}

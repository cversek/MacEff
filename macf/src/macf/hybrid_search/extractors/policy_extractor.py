"""
Policy-specific extractor for MacEff framework policies.

Extracts:
- Policy metadata (tier, category, version)
- CEP Navigation Guide
- Description/purpose
- Keywords from manifest.json
- Questions from CEP guide
"""

import json
import re
from pathlib import Path
from typing import Any

from .base import AbstractExtractor


class PolicyExtractor(AbstractExtractor):
    """Extractor for MacEff policy documents."""

    def __init__(self, manifest_path: Path = None):
        """Initialize with optional manifest.json path."""
        self.manifest_path = manifest_path
        self._manifest_cache = None

    @property
    def name(self) -> str:
        return "policies"

    def get_fts_columns(self) -> list[tuple[str, str]]:
        """FTS5 columns for policy indexing."""
        return [
            ("policy_name", "TEXT"),
            ("tier", "TEXT"),
            ("category", "TEXT"),
            ("keywords", "TEXT"),
            ("description", "TEXT"),
            ("content", "TEXT"),
            ("cep_guide", "TEXT"),
            ("file_path", "TEXT"),
        ]

    def extract_document(self, doc_path: Path) -> dict[str, Any]:
        """Extract all policy fields from markdown file."""
        policy_name = doc_path.stem
        content = doc_path.read_text(encoding="utf-8")

        metadata = self._extract_metadata(content)
        cep_guide = self._extract_cep_navigation_guide(content)
        description = self._extract_description(content)
        keywords = self._extract_keywords_from_manifest(policy_name)

        return {
            "policy_name": policy_name,
            "tier": metadata["tier"],
            "category": metadata["category"],
            "keywords": " ".join(keywords),
            "description": description,
            "content": content[:5000],  # Limit content size for FTS
            "cep_guide": cep_guide,
            "file_path": str(doc_path),
        }

    def generate_embedding_text(self, doc_data: dict) -> str:
        """Create text representation for policy embedding.

        Combines policy name, description, keywords, and key questions
        into a single text for embedding generation.
        """
        policy_name = doc_data.get("policy_name", "")
        description = doc_data.get("description", "")
        keywords_str = doc_data.get("keywords", "")
        cep_guide = doc_data.get("cep_guide", "")

        keywords = keywords_str.split() if keywords_str else []

        parts = [
            f"Policy: {policy_name.replace('_', ' ')}",
            f"Description: {description}" if description else "",
            f"Keywords: {', '.join(keywords)}" if keywords else "",
        ]

        # Extract first few questions from CEP guide for semantic context
        questions = []
        for line in (cep_guide or "").split('\n'):
            if line.strip().startswith('- ') and line.strip().endswith('?'):
                questions.append(line.strip()[2:])
                if len(questions) >= 5:  # Limit to top 5 questions
                    break

        if questions:
            parts.append(f"Questions: {' '.join(questions)}")

        return ' '.join(p for p in parts if p)

    def extract_questions(self, content: str, doc_id: str) -> list[dict]:
        """Extract CNG questions from policy content.

        Returns structured questions for separate indexing.
        """
        cep_guide = self._extract_cep_navigation_guide(content)
        return self._extract_cng_questions(cep_guide, doc_id)

    def should_index(self, doc_path: Path) -> bool:
        """Index .md files except _* and README.md."""
        if doc_path.name.startswith("_") or doc_path.name == "README.md":
            return False
        return doc_path.suffix == ".md"

    # =========================================================================
    # Internal extraction methods (ported from reference implementation)
    # =========================================================================

    def _extract_metadata(self, content: str) -> dict:
        """Extract policy metadata from markdown content."""
        metadata = {
            "tier": "",
            "category": "",
            "version": "",
            "status": "",
        }

        patterns = {
            "tier": r"\*\*Tier\*\*:\s*(\w+)",
            "category": r"\*\*Category\*\*:\s*([^\n]+)",
            "version": r"\*\*Version\*\*:\s*([^\n]+)",
            "status": r"\*\*Status\*\*:\s*(\w+)",
        }

        for key, pattern in patterns.items():
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                metadata[key] = match.group(1).strip()

        return metadata

    def _extract_cep_navigation_guide(self, content: str) -> str:
        """Extract CEP Navigation Guide section from policy."""
        patterns = [
            r"## CEP Navigation Guide\s*\n(.*?)(?=\n===\s*CEP_NAV_BOUNDARY|(?=\n## [^C])|\Z)",
            r"## CEP Navigation Guide\s*\n(.*?)(?=\n---|\n## |\Z)",
        ]

        for pattern in patterns:
            match = re.search(pattern, content, re.DOTALL)
            if match:
                guide = match.group(1).strip()
                return guide

        return ""

    def _extract_description(self, content: str) -> str:
        """Extract policy description/purpose from first paragraph after title."""
        patterns = [
            r"## (?:Purpose|Policy Statement)\s*\n\n?([^\n#]+)",
            r"# [^\n]+\n\n([^\n#]+)",  # First paragraph after title
        ]

        for pattern in patterns:
            match = re.search(pattern, content)
            if match:
                desc = match.group(1).strip()
                # Truncate if too long
                if len(desc) > 500:
                    desc = desc[:497] + "..."
                return desc

        return ""

    def _extract_keywords_from_manifest(self, policy_name: str) -> list[str]:
        """Extract keywords from manifest.json discovery_index."""
        if not self.manifest_path or not self.manifest_path.exists():
            return []

        # Cache manifest to avoid repeated reads
        if self._manifest_cache is None:
            try:
                with open(self.manifest_path) as f:
                    self._manifest_cache = json.load(f)
            except (json.JSONDecodeError, IOError):
                self._manifest_cache = {}

        discovery_index = self._manifest_cache.get("discovery_index", {})
        keywords = []

        for keyword, policies in discovery_index.items():
            if policy_name in policies:
                keywords.append(keyword)

        return keywords

    def _extract_cng_questions(self, cep_guide: str, policy_name: str) -> list[dict]:
        """Parse CEP Navigation Guide into structured questions."""
        questions = []
        if not cep_guide:
            return questions

        current_section = ""
        section_num = ""
        question_id = 0

        for line in cep_guide.split('\n'):
            # Detect section headers in two formats:
            # Format 1: "**1 Recovery Type Classification**" (bold markers)
            # Format 2: "1 Understanding Learnings" (no bold markers)
            header_match = re.match(r'\*\*(\d+(?:\.\d+)?)\s+([^*]+)\*\*', line)
            if not header_match:
                # Try non-bold format
                header_match = re.match(r'^(\d+(?:\.\d+)?)\s+(.+)$', line)

            if header_match:
                section_num = header_match.group(1)
                current_section = header_match.group(2).strip()
                continue

            # Detect questions: "- What triggers each recovery type?"
            question_match = re.match(r'\s*-\s+(.+\?)\s*$', line)
            if question_match and current_section:
                question_id += 1
                questions.append({
                    "question_id": f"{policy_name}_{question_id}",
                    "policy_name": policy_name,
                    "section_header": current_section,
                    "section_number": section_num,
                    "question_text": question_match.group(1).strip()
                })

        return questions

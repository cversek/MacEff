"""Markdown-to-HTML presenter for consciousness artifacts.

Renders markdown files as styled HTML with a dark "homebrew" theme
and opens in the default browser. Graceful fallback when the `markdown`
library is not installed.

Usage::

    from macf.viz.markdown import MarkdownPresenter

    # From file path
    MarkdownPresenter("agent/private/reflections/jotewr.md").present()

    # From raw content
    MarkdownPresenter(content="# Hello\\n\\nWorld", title="Test").present()

    # Render to specific path
    path = MarkdownPresenter("notes.md").render("/tmp/notes.html")
"""
import hashlib
import os
import platform
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from string import Template
from typing import Optional


TEMPLATE_DIR = Path(__file__).parent / "templates"


def _convert_md_to_html(md_text: str) -> str:
    """Convert markdown to HTML, with graceful fallback."""
    try:
        import markdown
        return markdown.markdown(
            md_text,
            extensions=["extra", "codehilite", "toc"],
            extension_configs={
                "codehilite": {"css_class": "highlight", "guess_lang": False},
            },
        )
    except ImportError:
        # Fallback: escape HTML and wrap in <pre>
        escaped = (md_text
                   .replace("&", "&amp;")
                   .replace("<", "&lt;")
                   .replace(">", "&gt;"))
        return f"<pre>{escaped}</pre>"


def _extract_title(md_text: str, file_path: Optional[str] = None) -> str:
    """Extract title from first H1 heading or file name."""
    for line in md_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# ") and not stripped.startswith("##"):
            return stripped[2:].strip()
    if file_path:
        return Path(file_path).stem.replace("_", " ")
    return "Markdown Document"


def _open_in_browser(path: str) -> None:
    """Open a file in the default browser (cross-platform)."""
    system = platform.system()
    try:
        if system == "Darwin":
            subprocess.Popen(["open", path],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif system == "Linux":
            subprocess.Popen(["xdg-open", path],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            # Windows or unknown
            os.startfile(path)  # type: ignore[attr-defined]
    except (OSError, AttributeError) as e:
        print(f"⚠️ Could not open browser: {e}", file=sys.stderr)


class MarkdownPresenter:
    """Renders markdown to styled HTML and opens in browser.

    Args:
        source: File path to a markdown file, or None if using `content`.
        content: Raw markdown string (alternative to file path).
        title: Override title (default: extracted from first H1).
    """

    def __init__(
        self,
        source: Optional[str] = None,
        content: Optional[str] = None,
        title: Optional[str] = None,
    ):
        if source and not content:
            path = Path(source)
            if not path.exists():
                raise FileNotFoundError(f"Markdown file not found: {source}")
            self._md_text = path.read_text(errors="replace")
            self._source_path = str(path.resolve())
        elif content:
            self._md_text = content
            self._source_path = None
        else:
            raise ValueError("Provide either source (file path) or content (string)")

        self._title = title or _extract_title(self._md_text, self._source_path)

    def to_html(self) -> str:
        """Render markdown to complete styled HTML string."""
        template_path = TEMPLATE_DIR / "markdown_dark.html"
        try:
            template_text = template_path.read_text()
        except FileNotFoundError:
            print(f"⚠️ MACF: Template not found: {template_path}", file=sys.stderr)
            raise

        html_content = _convert_md_to_html(self._md_text)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        tmpl = Template(template_text)
        return tmpl.safe_substitute(
            title=self._title,
            content=html_content,
            timestamp=timestamp,
        )

    def render(self, output_path: str) -> Path:
        """Write styled HTML to a file. Returns the output path."""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_html())
        return path

    def present(self, output_path: Optional[str] = None) -> Path:
        """Render to temp file and open in default browser.

        Args:
            output_path: Override output path. Default: /tmp/macf_md_{hash}.html
        """
        if not output_path:
            # Deterministic filename from source path or content hash
            key = self._source_path or hashlib.md5(
                self._md_text[:200].encode()
            ).hexdigest()[:8]
            safe_name = Path(key).stem.replace(" ", "_")[:60]
            output_path = f"/tmp/macf_md_{safe_name}.html"

        path = self.render(output_path)
        print(f"📄 Rendered: {path}")
        print(f"   Open in browser: file://{path}")
        _open_in_browser(str(path))
        return path

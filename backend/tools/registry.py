"""Pluggable tool registry for the chatbot agent.

``make_tools(conversation_id)`` is called once per chat turn.  It returns
the set of LangChain tools the agent may invoke, closed over the conversation_id
where needed.

**Starter toolset (5 tools — 4 read-only + 1 mutating demo):**
- ``list_datasets``         — names + column counts for every dataset in the project.
- ``inspect_dataset``       — schema (column names + types) for one named dataset.
- ``sample_data``           — up to N rows from a dataset as a markdown table.
- ``search_knowledge_base`` — semantic search across all project knowledge banks.
- ``create_scratch_note``   — **mutating demo** (policy: prompt); exercises the
  tool-call approval flow.  Ask the agent "make a note: hello" to see it.

All tools use ``get_project()`` (dual-mode: local dev + in-DSS) so they work
without any mode-specific branching in the call site.

``sample_data`` reads rows the same way as ``backend/routes/example.py``:
``get_dataiku().Dataset(...).get_dataframe()`` — the runtime ``dataiku`` in DSS, or
the installed ``dataiku-internal-client`` against the remote instance locally.

**Adding domain tools:**
Drop a new ``@tool``-decorated function here and add it to ``_domain_tools()``.
Update ``DEFAULT_TOOL_POLICY`` in ``services/settings.py`` to set a default
allow/prompt policy.

**Documents-block integration:**
When ``ENABLE_DOCUMENTS=1``, ``_document_tools()`` is appended so the agent can
list and read uploaded files.  The gating is explicit so disabling Documents
also removes the tools — no stale references.
"""

from __future__ import annotations

from typing import Any

from langchain_core.tools import BaseTool, tool

from .. import config
from ..dss_client import get_dataiku, get_project

MAX_SAMPLE_ROWS = 50
MAX_KB_RESULTS = 5
MAX_KB_TOTAL = 6


def _format_table(columns: list[str], rows: list[list[Any]]) -> str:
    """Format columns + rows as a GitHub-flavoured markdown table."""
    if not columns:
        return "(no columns)"
    header = "| " + " | ".join(columns) + " |"
    sep    = "| " + " | ".join("---" for _ in columns) + " |"
    body   = [
        "| " + " | ".join("null" if c is None else str(c) for c in row) + " |"
        for row in rows
    ]
    return "\n".join([header, sep, *body])


def _domain_tools() -> list[BaseTool]:

    @tool("list_datasets")
    def list_datasets() -> str:
        """List every dataset in the DSS project with its name and column count (read-only).

        Call this first when the user hasn't specified which dataset to work with.
        """
        try:
            project = get_project()
            raw = project.list_datasets()
        except Exception as e:
            return f"Could not list datasets: {e}"
        if not raw:
            return "(no datasets in this project)"
        lines = ["| name | columns |", "| --- | ---: |"]
        for d in raw:
            name = d.get("name", str(d)) if isinstance(d, dict) else str(d)
            cols = len(d.get("schema", {}).get("columns", [])) if isinstance(d, dict) else "?"
            lines.append(f"| {name} | {cols} |")
        return "\n".join(lines)

    @tool("inspect_dataset")
    def inspect_dataset(dataset_name: str) -> str:
        """Return the full schema (column names and types) for a named dataset (read-only).

        Use this before sample_data or any analytical question to understand
        the column structure.

        Args:
            dataset_name: Exact dataset name as returned by list_datasets.
        """
        try:
            project = get_project()
            schema = project.get_dataset(dataset_name).get_schema()
        except Exception as e:
            return f"Could not get schema for '{dataset_name}': {e}"
        columns = schema.get("columns", [])
        if not columns:
            return f"Dataset '{dataset_name}' has no columns (or schema not available)."
        lines = [f"**{dataset_name}** — {len(columns)} column(s)\n",
                 "| column | type |", "| --- | --- |"]
        for c in columns:
            lines.append(f"| {c.get('name', '?')} | {c.get('type', '?')} |")
        return "\n".join(lines)

    @tool("sample_data")
    def sample_data(dataset_name: str, limit: int = 10) -> str:
        """Return up to ``limit`` rows from a dataset as a markdown table (read-only).

        Use this to check real values, spot data-quality issues, or understand
        ranges before asking analytical questions.

        Args:
            dataset_name: Exact dataset name as returned by list_datasets.
            limit: Number of rows to return (1–50, default 10).
        """
        n = max(1, min(MAX_SAMPLE_ROWS, int(limit)))
        try:
            df = get_dataiku().Dataset(dataset_name).get_dataframe(limit=n)
            return _format_table(list(df.columns), df.head(n).where(df.notna(), None).values.tolist())
        except Exception as e:
            return f"Could not sample '{dataset_name}': {e}"

    @tool("search_knowledge_base")
    def search_knowledge_base(query: str) -> str:
        """Search all knowledge banks in the DSS project for passages relevant to the query (read-only).

        Use when the user asks about domain rules, SOPs, reference documents,
        or any information that may have been uploaded to a knowledge bank.

        Args:
            query: Natural-language search phrase.
        """
        try:
            project = get_project()
            kb_ids = [kb["id"] for kb in project.list_knowledge_banks()]
        except Exception as e:
            return f"Could not reach DSS: {e}"
        if not kb_ids:
            return "No knowledge banks in this project."
        hits: list[tuple[float, str, str, str]] = []
        for kb_id in kb_ids:
            try:
                kb = project.get_knowledge_bank(kb_id)
                result = kb.search(query, max_documents=MAX_KB_RESULTS)
            except Exception:
                continue
            for d in getattr(result, "documents", None) or []:
                score = float(getattr(d, "score", 0.0) or 0.0)
                text  = str(getattr(d, "text", "") or "")
                kb_name = getattr(kb, "name", None) or kb_id
                source = "(unknown)"
                fr = getattr(d, "file_ref", None)
                if fr is not None:
                    source = str(getattr(fr, "path", None) or getattr(fr, "document_path", None) or source)
                hits.append((score, str(kb_name), source, text))
        if not hits:
            return f"No passages found for {query!r}."
        hits.sort(key=lambda h: h[0], reverse=True)
        blocks = []
        for score, kb_name, source, text in hits[:MAX_KB_TOTAL]:
            snippet = text.strip().replace("\n", " ")
            if len(snippet) > 600:
                snippet = snippet[:600] + "…"
            blocks.append(f"### {kb_name} — {source} (score={score:.3f})\n{snippet}")
        return "\n\n".join(blocks)

    @tool("create_scratch_note")
    def create_scratch_note(note: str) -> str:
        """Save a short scratch note to the DSS project.  **Mutating** — writes to
        DSS project variables.  Exists to demonstrate the tool-call approval flow.

        Args:
            note: Text to save (truncated to 1000 characters).
        """
        text = str(note).strip()[:1000]
        try:
            project = get_project()
            variables: dict[str, Any] = project.get_variables()
            variables.setdefault("standard", {})["scratch_note"] = text
            project.set_variables(variables)
        except Exception as e:
            return f"Could not save note: {e}"
        return f'Note saved: "{text}"'

    return [list_datasets, inspect_dataset, sample_data, search_knowledge_base, create_scratch_note]


def _document_tools() -> list[BaseTool]:
    """Document-block tools — appended only when ENABLE_DOCUMENTS=1."""
    from ..services import documents_service  # noqa: PLC0415

    @tool("list_documents")
    def list_documents() -> str:
        """List documents uploaded to this project with their descriptions (read-only)."""
        docs = documents_service.list_documents()
        if not docs:
            return "(no documents uploaded)"
        lines = []
        for d in docs:
            desc = d.description or "(no description)"
            lines.append(f"- {d.filename} ({d.mime_type}, {d.size_bytes} bytes): {desc}")
        return "\n".join(lines)

    @tool("read_document")
    def read_document(filename: str) -> Any:
        """Read the content of a document by filename (read-only).

        Returns multimodal content blocks (text or image) suitable for the LLM.

        Args:
            filename: The exact filename as returned by list_documents.
        """
        doc = documents_service.get_document_by_filename(filename)
        if doc is None:
            return [{"type": "text", "text": f"Document '{filename}' not found."}]
        return documents_service.read_document_blocks(doc.id)

    return [list_documents, read_document]


def make_tools(conversation_id: str) -> list[BaseTool]:  # noqa: ARG001
    """Return the agent's tool list for one chat turn.

    ``conversation_id`` is available for tools that need to scope state to the
    current conversation (none in the starter, but kept for extension).
    """
    tools: list[BaseTool] = list(_domain_tools())
    if config.ENABLE_DOCUMENTS:
        tools += _document_tools()
    return tools

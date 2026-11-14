#!/usr/bin/env python3
"""D3: `sem search --json` returns a wide snippet window.

The TTY path snips a match to one terminal line (~160 chars). JSON is consumed
by agents/tools, where a one-line snippet truncates the surrounding vocabulary
and the result can't actually be read from the tool. The JSON path widens the
window so a match carries real context; short snippets reflect short source
docs, not truncation.
"""
import importlib
import json

semanticscript = importlib.import_module("semanticscript")

_snippet = semanticscript._snippet
_tfidf_rank = semanticscript._tfidf_rank


def test_json_window_is_wider_than_tty_for_a_long_doc():
    long_text = ("integer overflow " + "context " * 200).strip()
    docs = [{"source": "diagnostic", "id": "SSX", "kind": "T1",
             "title": "Integer overflow", "ref": "x", "text": long_text}]
    tty = _tfidf_rank("integer overflow", docs, 20)[0]["snippet"]
    wide = _tfidf_rank("integer overflow", docs, 20, snippet_width=640)[0]["snippet"]
    assert len(tty) <= 170
    assert len(wide) > 400          # the wide window carries far more context
    assert len(wide) > len(tty)


def test_short_doc_is_not_padded():
    # a genuinely short doc stays short under either width — no fabricated context
    docs = [{"source": "diagnostic", "id": "SSY", "kind": "T1",
             "title": "tiny", "ref": "y", "text": "integer overflow only"}]
    wide = _tfidf_rank("integer overflow", docs, 20, snippet_width=640)[0]["snippet"]
    assert wide == "integer overflow only"


def test_spec_sections_are_not_capped():
    # DX-02: the language-guide sections are no longer truncated at 2000 chars, so a
    # long grammar/code section is available in full (the corpus had a [:2000] cap).
    secs = semanticscript._spec_sections()
    if not secs:               # frozen build without the guide — nothing to assert
        return
    assert any(len(s["text"]) > 2000 for s in secs), "expected an uncapped long section"


def test_full_text_source_returns_complete_block_with_newlines():
    # DX-02: a `spec` match returns the COMPLETE block verbatim (newlines/indentation
    # preserved), not a collapsed 640-char window — so grammar/code is usable.
    block = "Grammar\n```\nstmt ::= 'branch' cond\n     | 'return' value\n```\n" + "x " * 500
    docs = [{"source": "spec", "id": "Grammar", "kind": "spec",
             "title": "Grammar", "ref": "docs/LANGUAGE.md", "text": block}]
    # full-text source -> verbatim, newlines kept, not windowed/flattened
    full = _tfidf_rank("grammar branch", docs, 20, snippet_width=640,
                       full_text_sources=("spec",))[0]["snippet"]
    assert full == block
    assert "\n" in full
    # without the full-text source it would be a flattened window (the old behavior)
    windowed = _tfidf_rank("grammar branch", docs, 20, snippet_width=640)[0]["snippet"]
    assert "\n" not in windowed and len(windowed) < len(block)


def test_machine_readable_rank_can_include_complete_text_with_snippet():
    long_text = ("integer overflow\n" + "context " * 200).strip()
    docs = [{"source": "diagnostic", "id": "SSZ", "kind": "T1",
             "title": "Integer overflow", "ref": "z", "text": long_text}]
    row = _tfidf_rank(
        "integer overflow", docs, 20, snippet_width=160, include_full_text=True
    )[0]
    assert row["fullText"] == long_text
    assert len(row["fullText"]) > len(row["snippet"])
    assert "\n" in row["fullText"]


def test_json_search_includes_full_text_field(capsys):
    assert semanticscript.main([
        "search", "sqlite columnBlob lifetime", "--json", "--limit", "5"
    ]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["surface"] == "sem.search.v1"
    assert payload["matches"]
    assert all("fullText" in item for item in payload["matches"])
    assert all(item["fullText"] for item in payload["matches"])

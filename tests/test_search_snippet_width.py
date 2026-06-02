#!/usr/bin/env python3
"""D3: `sem search --json` returns a wide snippet window.

The TTY path snips a match to one terminal line (~160 chars). JSON is consumed
by agents/tools, where a one-line snippet truncates the surrounding vocabulary
and the result can't actually be read from the tool. The JSON path widens the
window so a match carries real context; short snippets reflect short source
docs, not truncation.
"""
import importlib

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

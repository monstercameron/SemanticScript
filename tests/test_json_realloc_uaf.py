#!/usr/bin/env python3
"""R-237/R-238: re-fetch a JSON node pointer after document_add_node before use.

document_add_node can realloc document->nodes, freeing the buffer a previously
taken SSJsonNode* points into. Two replace-existing paths read the old child
THROUGH that stale pointer before re-fetching:

  R-237 set_object_field_container (replace-existing-field path)
  R-238 replace_array_container    (replace-existing-index path)

Both now re-fetch via document_node_at(document, cursor) BEFORE reading
old_child, so the read and the subsequent invalidate_subtree use a live pointer.
Source-level guard (the realloc-during-add UAF read needs a heap checker to
observe; harness_json.c exercises these orderings under ASAN+UBSAN in CI, and
taskforge-web round-trips the real set/replace path). Here we assert the
re-fetch precedes the old_child read in each function body.
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "semanticscript", "runtime", "native_json",
                   "sem_json_runtime.c")


def _body(name, ret="int"):
    src = open(SRC, encoding="utf-8").read()
    # The function's closing brace is the only `}` at column 0 (nested blocks are
    # indented), so a non-greedy match to the first line-start `}` is the body.
    m = re.search(r"static %s %s\(.*?\n\}" % (ret, name), src, re.S)
    assert m, "%s not found" % name
    return m.group(0)


def test_r237_object_field_refetches_node_before_old_child_read():
    body = _body("set_object_field_container")
    refetch = body.index("object_node = document_node_at(document, cursor)")
    read = body.index("old_child = object_node->as.object_value.fields")
    assert refetch < read, "node must be re-fetched before the stale old_child read"


def test_r238_array_element_refetches_node_before_old_child_read():
    body = _body("replace_array_container")
    refetch = body.index("array_node = document_node_at(document, cursor)")
    read = body.index("old_child = array_node->as.array_value.items[index]")
    assert refetch < read, "node must be re-fetched before the stale old_child read"

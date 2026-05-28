#!/usr/bin/env python3
"""SemanticScript tool driver.

This is intentionally thin for 1.0: it discovers a project build tape and
delegates to the reference tools without inventing a second build engine.
"""

from __future__ import annotations

import argparse
import array
import copy
import errno
import functools
import hashlib
import importlib.util
import json
import os
import queue
import re
import secrets
import shlex
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.repo_version import read_repo_version
from shared.console_encoding import force_utf8_streams as _force_utf8_streams

VERSION = read_repo_version()
STARTER_PROJECT_VERSION = "0.0.1"
SYNTAX_PAYLOAD_VERSION = "sem.syntaxCutover.v1"
DOCS_PAYLOAD_VERSION = "sem.docs.v1"
DOCS_INDEX_PAYLOAD_VERSION = "sem.docsIndex.v1"
DOCS_SEARCH_PAYLOAD_VERSION = "sem.docsSearch.v1"
DOCS_INDEX_SCHEMA_VERSION = 1
DOCS_DEFAULT_EMBEDDING_DIMENSIONS = 384
DOCS_DEFAULT_EMBEDDING_PROVIDER = "sentence-transformers"
DOCS_DEFAULT_EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
DOCS_DEFAULT_ALLOW_MODEL_DOWNLOAD = False
DOCS_SEARCH_MAX_LIMIT = 50
SELF_PAYLOAD_VERSION = "sem.self.v1"
DEFAULT_RELEASE_REPOSITORY = "monstercameron/SemanticScript"
DEFAULT_RELEASE_PLATFORM = "windows-x64"
MCP_BOOTSTRAP_SKILLS = ("sem-start", "sem", "sem-agent", "sem-syntax")
MCP_BOOTSTRAP_EVAL_CODE = "\n".join((
    "error ConsoleWriteError",
    "errorCase ConsoleWriteError ConsoleWriteFailed Int32",
    'storage local immutable greetingText String "semantic tools ready"',
    "call greetingWriteCall console.writeLine",
    "argument greetingWriteCall text String greetingText",
    "run greetingWriteCall",
    "ignore void source greetingWriteCall",
    "bind error greetingWriteError ConsoleWriteError greetingWriteCall",
    "branch error source greetingWriteCall target greetingWriteFailed",
    "jump target greetingDone",
    "label greetingWriteFailed",
    "makeError greetingWriteFailure ConsoleWriteError.ConsoleWriteFailed greetingWriteError",
    "label greetingDone",
))
MCP_BOOTSTRAP_SKILLS_MCP_ARGS = {"names": list(MCP_BOOTSTRAP_SKILLS), "full": True}
MCP_BOOTSTRAP_TOOL_CALL = "skills_get " + json.dumps(MCP_BOOTSTRAP_SKILLS_MCP_ARGS, separators=(",", ":"))
MCP_BOOTSTRAP_AGENT_DOCS_CALL = 'agent_docs {"path":"."}'
MCP_BOOTSTRAP_DOCS_SEARCH = 'docs_search {"query":"<capability, API, type, syntax, or runtime need>","path":".","watch":true,"include_std":true}'
MCP_BOOTSTRAP_EVAL_CALL = "eval " + json.dumps({"code": MCP_BOOTSTRAP_EVAL_CODE}, separators=(",", ":"))
MCP_BOOTSTRAP_HELP = """MCP bootstrap:
  Start stdio server:
    sem.exe mcp
  MCP client config:
    {"command":"sem.exe","args":["mcp"],"cwd":"<project-root>"}
  Load project agent docs:
    """ + MCP_BOOTSTRAP_AGENT_DOCS_CALL + """
  Then load versioned skills:
    """ + MCP_BOOTSTRAP_TOOL_CALL + """
  Then inspect the project:
    help {"path":"."}
  Capability/API/type/syntax/runtime discovery:
    """ + MCP_BOOTSTRAP_DOCS_SEARCH + """
  Optional language smoke (writes one line and demonstrates explicit console failure handling):
    """ + MCP_BOOTSTRAP_EVAL_CALL + """
"""
MCP_HANDSHAKE_INSTRUCTIONS = """SemanticScript MCP server ready.

First load project-local AGENTS.md / CLAUDE.md instructions when present:
""" + MCP_BOOTSTRAP_AGENT_DOCS_CALL + """

Then load versioned skills:
""" + MCP_BOOTSTRAP_TOOL_CALL + """

`sem-start` resolves to the getting-started skill, and `sem-syntax` exposes the compact row/verb inventory. Then call:
help {"path":"."}

For standard-library/API/capability/type/syntax/runtime discovery before generating calls, use:
""" + MCP_BOOTSTRAP_DOCS_SEARCH + """

For exact usage rows after discovery, call docs_get for the selected operation, target, type, or enum.

To prove the language/runtime surface works before opening a project, optionally call this smoke snippet; it writes one line and shows the explicit error branch shape:
""" + MCP_BOOTSTRAP_EVAL_CALL + """
"""
SYNTAX_INVENTORY_PATH = ROOT.parent / "docs" / "reference" / "syntax-inventory.md"
CALL_DISPOSITION_VARIANTS = ("value", "ok", "error", "void")
STD_DOC_COMMENT_TAGS = (
    "rationale",
    "invariant",
    "warning",
    "memory",
    "concurrency",
    "timing",
    "failure",
    "security",
    "dependency",
    "observability",
    "test",
    "todo",
)
SQLITE_GENERATED_ID_RETURNING_GUIDANCE = {
    "title": "SQLite generated-id replacement: INSERT RETURNING",
    "summary": (
        "Do not recover generated ids through connection-global "
        "sqlite.lastInsertRowId or last_insert_rowid(). Prepare the INSERT as "
        "INSERT ... RETURNING id, step it to rowSqliteStepResult, read column 0 "
        "with sqlite.columnInt64, pass that named value into any activity-log "
        "INSERT, finalize the RETURNING statement before COMMIT, and rollback "
        "on any failure after BEGIN succeeds."
    ),
    "nativeSafe": True,
    "webServerSafe": True,
    "replacementTargets": [
        "sqlite.prepareStatement",
        "sqlite.bindText",
        "sqlite.stepStatement",
        "sqlite.columnInt64",
        "sqlite.finalizeStatement",
        "sqlite.beginImmediateTransaction",
        "sqlite.commitTransaction",
        "sqlite.rollbackTransaction",
    ],
    "searchTerms": [
        "sqlite insert returning generated id",
        "SQLite RETURNING row id",
        "activity log insert generated id",
        "SS3639 migration",
        "lastInsertRowId replacement",
        "last_insert_rowid replacement",
        "native webServer safe SQLite generated id",
    ],
    "sqlRows": [
        "storage module immutable insertEntitySql SqlText",
        "sql body insertEntitySql",
        "  INSERT INTO entity(name) VALUES (?1) RETURNING id",
        "storage module immutable insertActivityLogSql SqlText",
        "sql body insertActivityLogSql",
        "  INSERT INTO activity_log(entity_id, activity_type) VALUES (?1, ?2)",
    ],
    "rows": [
        "effect <callerOperation> readWrite database",
        "useCapability <callerOperation> sqliteDatabaseReadWriter",
        "call beginGeneratedIdTransactionCall sqlite.beginImmediateTransaction",
        "argument beginGeneratedIdTransactionCall database SqliteDatabase <database>",
        "run beginGeneratedIdTransactionCall",
        "bind ok beginGeneratedIdTransactionResult Int32 beginGeneratedIdTransactionCall",
        "bind error beginGeneratedIdTransactionError SqliteTransactionFailure beginGeneratedIdTransactionCall",
        "branch error source beginGeneratedIdTransactionCall target <beginFailedLabel>",
        "call prepareGeneratedInsertCall sqlite.prepareStatement",
        "argument prepareGeneratedInsertCall database SqliteDatabase <database>",
        "argument prepareGeneratedInsertCall sql SqlText insertEntitySql",
        "run prepareGeneratedInsertCall",
        "bind ok generatedInsertStatement SqliteStatement prepareGeneratedInsertCall",
        "bind error prepareGeneratedInsertError SqliteStatementPrepareFailure prepareGeneratedInsertCall",
        "branch error source prepareGeneratedInsertCall target <rollbackLabel>",
        "call bindGeneratedNameCall sqlite.bindText",
        "argument bindGeneratedNameCall statement SqliteStatement generatedInsertStatement",
        "argument bindGeneratedNameCall parameterIndex Int32 1",
        "argument bindGeneratedNameCall value SqliteText <entityName>",
        "run bindGeneratedNameCall",
        "bind ok bindGeneratedNameResult Int32 bindGeneratedNameCall",
        "bind error bindGeneratedNameError SqliteStatementBindFailure bindGeneratedNameCall",
        "branch error source bindGeneratedNameCall target <finalizeInsertThenRollbackLabel>",
        "call stepGeneratedInsertCall sqlite.stepStatement",
        "argument stepGeneratedInsertCall statement SqliteStatement generatedInsertStatement",
        "run stepGeneratedInsertCall",
        "bind ok generatedInsertStep SqliteStepResult stepGeneratedInsertCall",
        "bind error stepGeneratedInsertError SqliteStatementStepFailure stepGeneratedInsertCall",
        "branch error source stepGeneratedInsertCall target <finalizeInsertThenRollbackLabel>",
        "# require generatedInsertStep == rowSqliteStepResult before reading column 0",
        "storage local immutable generatedIdColumnIndex Int32 0",
        "call readGeneratedIdCall sqlite.columnInt64",
        "argument readGeneratedIdCall statement SqliteStatement generatedInsertStatement",
        "argument readGeneratedIdCall columnIndex Int32 generatedIdColumnIndex",
        "run readGeneratedIdCall",
        "bind value generatedEntityId Int64 readGeneratedIdCall",
        "call drainGeneratedInsertCall sqlite.stepStatement",
        "argument drainGeneratedInsertCall statement SqliteStatement generatedInsertStatement",
        "run drainGeneratedInsertCall",
        "bind ok generatedInsertDone SqliteStepResult drainGeneratedInsertCall",
        "bind error drainGeneratedInsertError SqliteStatementStepFailure drainGeneratedInsertCall",
        "branch error source drainGeneratedInsertCall target <finalizeInsertThenRollbackLabel>",
        "# require generatedInsertDone == doneSqliteStepResult before COMMIT",
        "call finalizeGeneratedInsertCall sqlite.finalizeStatement",
        "argument finalizeGeneratedInsertCall statement SqliteStatement generatedInsertStatement",
        "run finalizeGeneratedInsertCall",
        "ignore ok source finalizeGeneratedInsertCall type Int32",
        "bind error finalizeGeneratedInsertError SqliteStatementFinalizeFailure finalizeGeneratedInsertCall",
        "branch error source finalizeGeneratedInsertCall target <rollbackLabel>",
        "call prepareActivityLogCall sqlite.prepareStatement",
        "argument prepareActivityLogCall database SqliteDatabase <database>",
        "argument prepareActivityLogCall sql SqlText insertActivityLogSql",
        "run prepareActivityLogCall",
        "bind ok activityLogStatement SqliteStatement prepareActivityLogCall",
        "bind error prepareActivityLogError SqliteStatementPrepareFailure prepareActivityLogCall",
        "branch error source prepareActivityLogCall target <rollbackLabel>",
        "call bindActivityEntityCall sqlite.bindInt64",
        "argument bindActivityEntityCall statement SqliteStatement activityLogStatement",
        "argument bindActivityEntityCall parameterIndex Int32 1",
        "argument bindActivityEntityCall value Int64 generatedEntityId",
        "run bindActivityEntityCall",
        "bind ok bindActivityEntityResult Int32 bindActivityEntityCall",
        "bind error bindActivityEntityError SqliteStatementBindFailure bindActivityEntityCall",
        "branch error source bindActivityEntityCall target <finalizeActivityThenRollbackLabel>",
        "call stepActivityLogCall sqlite.stepStatement",
        "argument stepActivityLogCall statement SqliteStatement activityLogStatement",
        "run stepActivityLogCall",
        "bind ok activityLogStep SqliteStepResult stepActivityLogCall",
        "bind error stepActivityLogError SqliteStatementStepFailure stepActivityLogCall",
        "branch error source stepActivityLogCall target <finalizeActivityThenRollbackLabel>",
        "# require activityLogStep == doneSqliteStepResult for an activity-log INSERT without RETURNING",
        "call finalizeActivityLogCall sqlite.finalizeStatement",
        "argument finalizeActivityLogCall statement SqliteStatement activityLogStatement",
        "run finalizeActivityLogCall",
        "ignore ok source finalizeActivityLogCall type Int32",
        "bind error finalizeActivityLogError SqliteStatementFinalizeFailure finalizeActivityLogCall",
        "branch error source finalizeActivityLogCall target <rollbackLabel>",
        "call commitGeneratedIdTransactionCall sqlite.commitTransaction",
        "argument commitGeneratedIdTransactionCall database SqliteDatabase <database>",
        "run commitGeneratedIdTransactionCall",
        "bind ok commitGeneratedIdTransactionResult Int32 commitGeneratedIdTransactionCall",
        "bind error commitGeneratedIdTransactionError SqliteTransactionFailure commitGeneratedIdTransactionCall",
        "branch error source commitGeneratedIdTransactionCall target <commitFailedLabel>",
        "return value generatedEntityId",
        "label <rollbackLabel>",
        "call rollbackGeneratedIdTransactionCall sqlite.rollbackTransaction",
        "argument rollbackGeneratedIdTransactionCall database SqliteDatabase <database>",
        "run rollbackGeneratedIdTransactionCall",
        "ignore ok source rollbackGeneratedIdTransactionCall type Int32",
        "bind error rollbackGeneratedIdTransactionError SqliteTransactionFailure rollbackGeneratedIdTransactionCall",
        "branch error source rollbackGeneratedIdTransactionCall target <rollbackFailedLabel>",
        "return error <failureValue>",
    ],
    "lifetimeRules": [
        "columnInt64 returns an Int64 by value, so the generated id may be used after finalize.",
        "columnText, columnBlob, and columnName are borrowed from the same statement; consume or copy them before the next same-statement pointer column read, step, reset, finalize, or closeDatabase.",
        "A RETURNING statement remains active after the first row. Step it once more to doneSqliteStepResult, reset it, or finalize it before COMMIT.",
    ],
    "transactionRules": [
        "Use sqlite.beginImmediateTransaction when the generated row and activity-log row must commit atomically.",
        "After BEGIN succeeds, every prepare/bind/step/finalize failure path should finalize any acquired statement and then call sqlite.rollbackTransaction.",
        "Commit only after the RETURNING statement has been drained or finalized and the activity-log statement has reached doneSqliteStepResult.",
    ],
}
STD_DOC_STATIC_TARGETS = {
    "standard.gui": {
        "gui.applicationCreate": {
            "summary": "Create the GUI application handle before creating windows or controls.",
            "inputs": [{"name": "title", "type": "GuiText"}],
            "outputs": [{"type": "GuiApplication", "values": ["GuiApplication"]}],
            "effects": [{"action": "allocate", "path": "gui.application"}],
            "failureMode": {"kind": "null-sentinel", "text": "A null handle indicates GUI runtime, configuration, or allocation failure."},
        },
        "gui.windowCreate": {
            "summary": "Create a window handle for later attachment to the application.",
            "inputs": [
                {"name": "title", "type": "GuiText"},
                {"name": "width", "type": "GuiPixels"},
                {"name": "height", "type": "GuiPixels"},
                {"name": "layout", "type": "GuiWindowLayout"},
                {"name": "resizable", "type": "Int32"},
            ],
            "outputs": [{"type": "GuiWindow", "values": ["GuiWindow"]}],
            "effects": [{"action": "allocate", "path": "gui.window"}],
            "failureMode": {"kind": "null-sentinel", "text": "A null handle indicates GUI runtime, configuration, or allocation failure."},
        },
        "gui.textLabelCreate": {
            "summary": "Create a static text-label control handle.",
            "inputs": [{"name": "text", "type": "GuiText"}],
            "outputs": [{"type": "GuiTextLabel", "values": ["GuiTextLabel"]}],
            "effects": [{"action": "allocate", "path": "gui.control"}],
            "failureMode": {"kind": "null-sentinel", "text": "A null handle indicates GUI runtime, configuration, or allocation failure."},
        },
        "gui.textBoxCreate": {
            "summary": "Create a text-box control handle.",
            "inputs": [{"name": "placeholder", "type": "GuiText"}, {"name": "maxLength", "type": "Int32"}],
            "outputs": [{"type": "GuiTextBox", "values": ["GuiTextBox"]}],
            "effects": [{"action": "allocate", "path": "gui.control"}],
            "failureMode": {"kind": "null-sentinel", "text": "A null handle indicates GUI runtime, configuration, or allocation failure."},
        },
        "gui.buttonCreate": {
            "summary": "Create a button control handle.",
            "inputs": [{"name": "text", "type": "GuiText"}, {"name": "isDefault", "type": "Int32"}],
            "outputs": [{"type": "GuiButton", "values": ["GuiButton"]}],
            "effects": [{"action": "allocate", "path": "gui.control"}],
            "failureMode": {"kind": "null-sentinel", "text": "A null handle indicates GUI runtime, configuration, or allocation failure."},
        },
        "gui.listBoxCreate": {
            "summary": "Create a list-box control handle.",
            "inputs": [{"name": "selectionMode", "type": "GuiListBoxSelectionMode"}],
            "outputs": [{"type": "GuiListBox", "values": ["GuiListBox"]}],
            "effects": [{"action": "allocate", "path": "gui.control"}],
            "failureMode": {"kind": "null-sentinel", "text": "A null handle indicates GUI runtime, configuration, or allocation failure."},
        },
        "gui.windowAddControl": {
            "summary": "Attach a control handle to a window during GUI construction.",
            "inputs": [{"name": "window", "type": "GuiWindow"}, {"name": "control", "type": "GuiControl"}],
            "outputs": [{"type": "Int32", "values": ["Int32"]}],
            "effects": [{"action": "write", "path": "gui.window"}],
            "capabilities": ["guiWindowWriter"],
            "failureMode": {"kind": "status-code", "text": "Non-zero status reports a GUI runtime configuration failure."},
        },
        "gui.controlOnEvent": {
            "summary": "Register a GUI event handler operation for a control.",
            "inputs": [{"name": "control", "type": "GuiControl"}, {"name": "eventKind", "type": "GuiEventKind"}, {"name": "handler", "type": "GuiEventHandler"}],
            "outputs": [{"type": "Int32", "values": ["Int32"]}],
            "effects": [{"action": "write", "path": "gui.control.event"}],
            "capabilities": ["guiControlEventWriter"],
            "failureMode": {"kind": "status-code", "text": "Non-zero status reports handler registration failure."},
        },
        "gui.applicationSetMainWindow": {
            "summary": "Select the main window for the GUI application before applicationRun.",
            "inputs": [{"name": "application", "type": "GuiApplication"}, {"name": "window", "type": "GuiWindow"}],
            "outputs": [{"type": "Int32", "values": ["Int32"]}],
            "effects": [{"action": "write", "path": "gui.window"}],
            "failureMode": {"kind": "status-code", "text": "Non-zero status reports invalid application or window handles."},
        },
        "gui.applicationRun": {
            "summary": "Run the configured GUI application and return the GUI process status.",
            "inputs": [{"name": "application", "type": "GuiApplication"}],
            "outputs": [{"type": "ExitCode", "values": ["ExitCode"]}],
            "effects": [{"action": "write", "path": "gui.window"}],
            "failureMode": {"kind": "sentinel-value", "text": "Non-zero exit status reports runtime or handler failure; callers commonly return this ExitCode directly instead of branching."},
        },
        "gui.textBoxText": {
            "summary": "Read current text from a text box inside a GUI handler.",
            "inputs": [{"name": "session", "type": "GuiSession"}, {"name": "textBox", "type": "GuiTextBox"}],
            "outputs": [{"type": "GuiText", "values": ["GuiText"]}],
            "effects": [{"action": "read", "path": "gui.control.textBox.text"}],
            "capabilities": ["guiTextBoxReader"],
            "failureMode": {"kind": "null-sentinel", "text": "A null text pointer indicates an invalid session or text-box handle."},
        },
        "gui.textBoxSetText": {
            "summary": "Set current text on a text box inside a GUI handler.",
            "inputs": [{"name": "session", "type": "GuiSession"}, {"name": "textBox", "type": "GuiTextBox"}, {"name": "text", "type": "String"}],
            "outputs": [{"type": "Int32", "values": ["Int32"]}],
            "effects": [{"action": "write", "path": "gui.control.textBox.text"}],
            "capabilities": ["guiTextBoxWriter"],
            "failureMode": {"kind": "status-code", "text": "Non-zero status reports an invalid session or text-box handle."},
        },
        "gui.listBoxSelectedIndex": {
            "summary": "Read the selected list-box row index inside a GUI handler.",
            "inputs": [{"name": "session", "type": "GuiSession"}, {"name": "listBox", "type": "GuiListBox"}],
            "outputs": [{"type": "GuiSelectedIndex", "values": ["GuiSelectedIndex"]}],
            "effects": [{"action": "read", "path": "gui.control.listBox.selection"}],
            "capabilities": ["guiListBoxSelectionReader"],
            "failureMode": {"kind": "sentinel-value", "text": "guiInvalidSelectedIndex means no selected row; invalid handles are runtime errors."},
        },
        "gui.listBoxAppendItem": {
            "summary": "Append one visible item to a list box inside a GUI handler.",
            "inputs": [{"name": "session", "type": "GuiSession"}, {"name": "listBox", "type": "GuiListBox"}, {"name": "text", "type": "String"}],
            "outputs": [{"type": "Int32", "values": ["Int32"]}],
            "effects": [{"action": "write", "path": "gui.control.listBox.items"}],
            "capabilities": ["guiListBoxWriter"],
            "failureMode": {"kind": "status-code", "text": "Non-zero status reports an invalid session, list-box handle, or item text."},
        },
        "gui.listBoxClear": {
            "summary": "Remove all items from a list box inside a GUI handler.",
            "inputs": [{"name": "session", "type": "GuiSession"}, {"name": "listBox", "type": "GuiListBox"}],
            "outputs": [{"type": "Int32", "values": ["Int32"]}],
            "effects": [{"action": "write", "path": "gui.control.listBox.items"}],
            "capabilities": ["guiListBoxWriter"],
            "failureMode": {"kind": "status-code", "text": "Non-zero status reports an invalid session or list-box handle."},
        },
        "gui.textLabelSetText": {
            "summary": "Set text on a text label inside a GUI handler.",
            "inputs": [{"name": "session", "type": "GuiSession"}, {"name": "textLabel", "type": "GuiTextLabel"}, {"name": "text", "type": "GuiText"}],
            "outputs": [{"type": "Int32", "values": ["Int32"]}],
            "effects": [{"action": "write", "path": "gui.control.textLabel.text"}],
            "capabilities": ["guiTextLabelWriter"],
            "failureMode": {"kind": "status-code", "text": "Non-zero status reports an invalid session or label handle."},
        },
        "gui.windowClose": {
            "summary": "Request closing a GUI window inside a GUI handler.",
            "inputs": [{"name": "session", "type": "GuiSession"}, {"name": "window", "type": "GuiWindow"}],
            "outputs": [{"type": "Int32", "values": ["Int32"]}],
            "effects": [{"action": "write", "path": "gui.window"}],
            "capabilities": ["guiWindowWriter"],
            "failureMode": {"kind": "status-code", "text": "Non-zero status reports an invalid session or window handle."},
        },
        "gui.eventKeyCode": {"summary": "Reserved event-reader target for keyPressed events.", "inputs": [{"name": "event", "type": "GuiEvent"}], "outputs": [{"type": "Int32", "values": ["Int32"]}], "loweringStatus": "reserved"},
        "gui.eventSelectedIndex": {"summary": "Reserved event-reader target for selectionChanged events.", "inputs": [{"name": "event", "type": "GuiEvent"}], "outputs": [{"type": "GuiSelectedIndex", "values": ["GuiSelectedIndex"]}], "loweringStatus": "reserved"},
        "gui.eventWindowWidth": {"summary": "Reserved event-reader target for resized window width.", "inputs": [{"name": "event", "type": "GuiEvent"}], "outputs": [{"type": "GuiPixels", "values": ["GuiPixels"]}], "loweringStatus": "reserved"},
        "gui.eventWindowHeight": {"summary": "Reserved event-reader target for resized window height.", "inputs": [{"name": "event", "type": "GuiEvent"}], "outputs": [{"type": "GuiPixels", "values": ["GuiPixels"]}], "loweringStatus": "reserved"},
        "gui.eventCancelClose": {"summary": "Reserved event-writer target for closeRequested events.", "inputs": [{"name": "event", "type": "GuiEvent"}], "outputs": [{"type": "Int32", "values": ["Int32"]}], "loweringStatus": "reserved"},
    },
    "standard.json": {
        "json.createDocument": {
            "summary": "Parse JSON text into an owned JsonDocument; destroy it on every ownership path.",
            "inputs": [{"name": "jsonText", "type": "String"}, {"name": "capacityBytes", "type": "JsonCapacityBytes"}],
            "outputs": [{"type": "Result", "values": ["Result", "JsonDocument", "JsonAccessError"]}],
            "failureMode": {"kind": "result", "text": "JsonAccessError reports malformed input or capacity failure."},
            "cleanup": {"required": True, "strategy": "defer or explicitly call json.destroyDocument for the ok JsonDocument", "callTarget": "json.destroyDocument", "argumentName": "document", "argumentType": "JsonDocument", "resultType": "Int32"},
        },
        "json.createEmptyDocument": {
            "summary": "Create an owned mutable JsonDocument with object or array root kind.",
            "inputs": [{"name": "capacityBytes", "type": "JsonCapacityBytes"}, {"name": "rootKind", "type": "JsonValueKind"}],
            "outputs": [{"type": "Result", "values": ["Result", "JsonDocument", "JsonAccessError"]}],
            "failureMode": {"kind": "result", "text": "JsonAccessError reports capacity or root-kind failure."},
            "cleanup": {"required": True, "strategy": "defer or explicitly call json.destroyDocument for the ok JsonDocument", "callTarget": "json.destroyDocument", "argumentName": "document", "argumentType": "JsonDocument", "resultType": "Int32"},
        },
        "json.destroyDocument": {
            "summary": "Release an owned JsonDocument.",
            "inputs": [{"name": "document", "type": "JsonDocument"}],
            "outputs": [{"type": "Int32", "values": ["Int32"]}],
            "failureMode": {"kind": "none", "text": "Destroy is best-effort and should be used as cleanup."},
        },
        "json.documentRoot": {
            "summary": "Get the root cursor for a JsonDocument.",
            "inputs": [{"name": "document", "type": "JsonDocument"}],
            "outputs": [{"type": "JsonCursor", "values": ["JsonCursor"]}],
        },
        "json.objectFieldAt": {
            "summary": "Find a direct object field cursor under an object cursor.",
            "inputs": [{"name": "document", "type": "JsonDocument"}, {"name": "cursor", "type": "JsonCursor"}, {"name": "fieldName", "type": "String"}],
            "outputs": [{"type": "Result", "values": ["Result", "JsonCursor", "JsonAccessError"]}],
            "failureMode": {"kind": "result", "text": "JsonAccessError reports missing field, wrong kind, or malformed access."},
        },
        "json.cursorString": {
            "summary": "Read a string cursor into caller-owned scratch memory.",
            "inputs": [{"name": "document", "type": "JsonDocument"}, {"name": "cursor", "type": "JsonCursor"}, {"name": "scratch", "type": "OpaquePointer"}, {"name": "scratchCapacity", "type": "Int64"}],
            "outputs": [{"type": "Result", "values": ["Result", "String", "JsonAccessError"]}],
            "failureMode": {"kind": "result", "text": "JsonAccessError reports wrong type or scratch capacity failure."},
        },
        "json.cursorInt64": {
            "summary": "Read an integer cursor, returning missingDefault when the cursor is not an integer.",
            "inputs": [{"name": "document", "type": "JsonDocument"}, {"name": "cursor", "type": "JsonCursor"}, {"name": "missingDefault", "type": "Int64"}],
            "outputs": [{"type": "Int64", "values": ["Int64"]}],
            "failureMode": {"kind": "sentinel-value", "text": "missingDefault is returned when the cursor is missing or not an integer."},
        },
        "json.cursorArrayLength": {
            "summary": "Read an array cursor length.",
            "inputs": [{"name": "document", "type": "JsonDocument"}, {"name": "cursor", "type": "JsonCursor"}],
            "outputs": [{"type": "Result", "values": ["Result", "Int64", "JsonAccessError"]}],
            "failureMode": {"kind": "result", "text": "JsonAccessError reports wrong type or invalid cursor."},
        },
        "json.setObjectFieldString": {
            "summary": "Set a string field on an object cursor.",
            "inputs": [{"name": "document", "type": "JsonDocument"}, {"name": "cursor", "type": "JsonCursor"}, {"name": "fieldName", "type": "String"}, {"name": "value", "type": "String"}],
            "outputs": [{"type": "Result", "values": ["Result", "Int32", "JsonAccessError"]}],
            "failureMode": {"kind": "result", "text": "JsonAccessError reports wrong type, field limits, or capacity failure."},
        },
        "json.setObjectFieldInt64": {
            "summary": "Set an integer field on an object cursor.",
            "inputs": [{"name": "document", "type": "JsonDocument"}, {"name": "cursor", "type": "JsonCursor"}, {"name": "fieldName", "type": "String"}, {"name": "value", "type": "Int64"}],
            "outputs": [{"type": "Result", "values": ["Result", "Int32", "JsonAccessError"]}],
            "failureMode": {"kind": "result", "text": "JsonAccessError reports wrong type, field limits, or capacity failure."},
        },
        "json.setObjectFieldNull": {
            "summary": "Set a null field on an object cursor.",
            "inputs": [{"name": "document", "type": "JsonDocument"}, {"name": "cursor", "type": "JsonCursor"}, {"name": "fieldName", "type": "String"}],
            "outputs": [{"type": "Result", "values": ["Result", "Int32", "JsonAccessError"]}],
            "failureMode": {"kind": "result", "text": "JsonAccessError reports wrong type, field limits, or capacity failure."},
        },
        "json.serializeDocument": {
            "summary": "Serialize a JsonDocument into caller-owned scratch memory.",
            "inputs": [{"name": "document", "type": "JsonDocument"}, {"name": "scratch", "type": "OpaquePointer"}, {"name": "scratchCapacity", "type": "Int64"}],
            "outputs": [{"type": "Result", "values": ["Result", "JsonText", "JsonAccessError"]}],
            "failureMode": {"kind": "result", "text": "JsonAccessError reports scratch capacity or serialization failure."},
        },
        "json.stringify.String": {
            "summary": "Encode a string as JSON text using the high-level stringify alias.",
            "inputs": [{"name": "value", "type": "String"}],
            "outputs": [{"type": "Result", "values": ["Result", "JsonText", "JsonEncodeError"]}],
            "failureMode": {"kind": "result", "text": "JsonEncodeError reports output capacity or serialization failure."},
        },
        "json.parse.Int64": {
            "summary": "Parse a JSON integer literal using the high-level parse alias.",
            "inputs": [{"name": "jsonText", "type": "JsonText"}],
            "outputs": [{"type": "Result", "values": ["Result", "Int64", "JsonDecodeError"]}],
            "failureMode": {"kind": "result", "text": "JsonDecodeError reports malformed, truncated, or wrong-type input."},
        },
    },
    "standard.bcrypt": {
        "bcrypt.hashPassword": {
            "summary": "Hash a plaintext password into a caller-owned bcrypt hash buffer. Returns Int32 0 on success, negative on error (NOTE: opposite of verifyPassword, where 1 means match) — check for negative before trusting the buffer.",
            "inputs": [
                {"name": "plaintext", "type": "BcryptPlaintextPassword"},
                {"name": "cost", "type": "Int32"},
                {"name": "outBuffer", "type": "BcryptHashBuffer"},
                {"name": "outCapacity", "type": "Int32"},
            ],
            "outputs": [{"type": "Int32", "values": ["Int32"]}],
            "effects": [{"action": "read", "path": "memory.buffer"}, {"action": "write", "path": "memory.buffer"}, {"action": "read", "path": "system.random"}],
            "failureMode": {"kind": "status-code", "text": "Zero means success; negative status reports bad cost, undersized output, random-source failure, or hash failure."},
        },
        "bcrypt.verifyPassword": {
            "summary": "Verify a plaintext password against a trusted bcrypt hash. Returns Int32 1 on MATCH, 0 on mismatch, negative on error (inverted from the C 0==success idiom) — branch on negative before treating 0 as a mismatch, or auth ships silently broken.",
            "inputs": [{"name": "plaintext", "type": "BcryptPlaintextPassword"}, {"name": "expectedHash", "type": "BcryptPasswordHash"}],
            "outputs": [{"type": "Int32", "values": ["Int32"]}],
            "effects": [{"action": "read", "path": "memory.buffer"}],
            "failureMode": {"kind": "negative-status", "text": "1 means password match, 0 means mismatch, and negative status means malformed hash or runtime failure; branch on negative status before treating 0 as an authentication mismatch."},
        },
        "bcrypt.randomBytes": {
            "summary": "Fill a caller-owned buffer with platform CSPRNG bytes.",
            "inputs": [{"name": "outBuffer", "type": "BcryptRandomBuffer"}, {"name": "byteCount", "type": "Int32"}],
            "outputs": [{"type": "Int32", "values": ["Int32"]}],
            "effects": [{"action": "write", "path": "memory.buffer"}, {"action": "read", "path": "system.random"}],
            "failureMode": {"kind": "status-code", "text": "Zero means success; negative status reports invalid output buffer or CSPRNG failure."},
        },
        "bcrypt.base64UrlEncode": {
            "summary": "Base64url-encode caller-owned bytes into a caller-owned output buffer.",
            "inputs": [
                {"name": "inputBuffer", "type": "BcryptRandomBuffer"},
                {"name": "inputCount", "type": "Int32"},
                {"name": "outputBuffer", "type": "Base64UrlBuffer"},
                {"name": "outputCapacity", "type": "Int32"},
                {"name": "outputLengthOut", "type": "OpaquePointer"},
            ],
            "outputs": [{"type": "Int32", "values": ["Int32"]}],
            "effects": [{"action": "read", "path": "memory.buffer"}, {"action": "write", "path": "memory.buffer"}],
            "failureMode": {"kind": "status-code", "text": "Zero means success; negative status reports invalid pointers, capacity failure, or encoder failure."},
        },
        "bcrypt.hashPasswordResult": {
            "summary": "Result-shaped hashPassword wrapper. OK Bool true means the hash buffer was filled; Err Int32 carries the negative bcrypt status. Prefer this over raw hashPassword when caller control flow already uses `bind ok` / `bind error`.",
            "inputs": [
                {"name": "plaintext", "type": "BcryptPlaintextPassword"},
                {"name": "cost", "type": "Int32"},
                {"name": "outBuffer", "type": "BcryptHashBuffer"},
                {"name": "outCapacity", "type": "Int32"},
            ],
            "outputs": [{"type": "Result", "values": ["Result", "Bool", "Int32"]}],
            "effects": [{"action": "read", "path": "memory.buffer"}, {"action": "write", "path": "memory.buffer"}, {"action": "read", "path": "system.random"}],
            "failureMode": {"kind": "result", "text": "OK true means the output buffer contains a bcrypt hash; Err carries the negative SS_BCRYPT_ERR_* status."},
        },
        "bcrypt.hashSessionTokenResult": {
            "summary": "Result-shaped session-token-at-rest hash primitive. OK Bool true means the hash buffer contains a SessionTokenHash suitable for persistence; Err Int32 carries the negative bcrypt status. Store this value instead of the raw SessionToken.",
            "inputs": [
                {"name": "token", "type": "SessionToken"},
                {"name": "cost", "type": "Int32"},
                {"name": "outBuffer", "type": "BcryptHashBuffer"},
                {"name": "outCapacity", "type": "Int32"},
            ],
            "outputs": [{"type": "Result", "values": ["Result", "Bool", "Int32"]}],
            "effects": [{"action": "read", "path": "memory.buffer"}, {"action": "write", "path": "memory.buffer"}, {"action": "read", "path": "system.random"}],
            "failureMode": {"kind": "result", "text": "OK true means the output buffer contains a SessionTokenHash; Err carries the negative SS_BCRYPT_ERR_* status."},
        },
        "bcrypt.verifyPasswordResult": {
            "summary": "Result-shaped verifyPassword wrapper. OK Bool true means password match; OK Bool false means a clean mismatch; Err Int32 carries malformed-hash/config/runtime failure. Prefer this for authentication branches so mismatch and runtime failure are not conflated.",
            "inputs": [{"name": "plaintext", "type": "BcryptPlaintextPassword"}, {"name": "expectedHash", "type": "BcryptPasswordHash"}],
            "outputs": [{"type": "Result", "values": ["Result", "Bool", "Int32"]}],
            "effects": [{"action": "read", "path": "memory.buffer"}],
            "failureMode": {"kind": "result", "text": "OK Bool is the match decision; Err Int32 is a negative SS_BCRYPT_ERR_* status."},
        },
        "bcrypt.verifySessionTokenResult": {
            "summary": "Result-shaped session-token verifier. OK Bool true means the presented SessionToken matches the stored SessionTokenHash; OK Bool false is a clean mismatch; Err Int32 carries malformed-hash/config/runtime failure.",
            "inputs": [{"name": "token", "type": "SessionToken"}, {"name": "expectedHash", "type": "SessionTokenHash"}],
            "outputs": [{"type": "Result", "values": ["Result", "Bool", "Int32"]}],
            "effects": [{"action": "read", "path": "memory.buffer"}],
            "failureMode": {"kind": "result", "text": "OK Bool is the token-match decision; Err Int32 is a negative SS_BCRYPT_ERR_* status."},
        },
        "bcrypt.randomBytesResult": {
            "summary": "Result-shaped randomBytes wrapper. OK Bool true means the buffer was filled with platform CSPRNG bytes; Err Int32 carries the negative status.",
            "inputs": [{"name": "outBuffer", "type": "BcryptRandomBuffer"}, {"name": "byteCount", "type": "Int32"}],
            "outputs": [{"type": "Result", "values": ["Result", "Bool", "Int32"]}],
            "effects": [{"action": "write", "path": "memory.buffer"}, {"action": "read", "path": "system.random"}],
            "failureMode": {"kind": "result", "text": "OK true means random bytes were written; Err carries the negative SS_BCRYPT_ERR_* status."},
        },
        "bcrypt.base64UrlEncodeResult": {
            "summary": "Result-shaped base64UrlEncode wrapper. OK Bool true means outputBuffer and outputLengthOut were written; Err Int32 carries the negative status.",
            "inputs": [
                {"name": "inputBuffer", "type": "BcryptRandomBuffer"},
                {"name": "inputCount", "type": "Int32"},
                {"name": "outputBuffer", "type": "Base64UrlBuffer"},
                {"name": "outputCapacity", "type": "Int32"},
                {"name": "outputLengthOut", "type": "OpaquePointer"},
            ],
            "outputs": [{"type": "Result", "values": ["Result", "Bool", "Int32"]}],
            "effects": [{"action": "read", "path": "memory.buffer"}, {"action": "write", "path": "memory.buffer"}],
            "failureMode": {"kind": "result", "text": "OK true means encoding succeeded; Err carries the negative SS_BCRYPT_ERR_* status."},
        },
        "bcrypt.issueSessionToken": {
            "summary": "Native-linkable one-step session-token issuer. Fills caller-owned tokenBuffer with a fresh 43-character base64url SessionToken from 32 bytes of platform CSPRNG entropy.",
            "inputs": [
                {"name": "randomScratch", "type": "BcryptRandomBuffer"},
                {"name": "tokenBuffer", "type": "Base64UrlBuffer"},
                {"name": "tokenCapacity", "type": "Int32"},
                {"name": "tokenLengthOut", "type": "OpaquePointer"},
            ],
            "outputs": [{"type": "Int32", "values": ["Int32"]}],
            "effects": [{"action": "read", "path": "system.random"}, {"action": "write", "path": "memory.buffer"}, {"action": "read", "path": "memory.buffer"}],
            "failureMode": {"kind": "status-code", "text": "Zero means success; negative status reports invalid scratch/output pointers, insufficient token capacity, or CSPRNG failure. randomScratch must hold at least 32 bytes; tokenBuffer must hold at least 44 bytes."},
        },
        "bcrypt.issueCsrfToken": {
            "summary": "Native-linkable one-step CSRF-token issuer. Fills caller-owned tokenBuffer with a fresh 43-character base64url CsrfToken from 32 bytes of platform CSPRNG entropy.",
            "inputs": [
                {"name": "randomScratch", "type": "BcryptRandomBuffer"},
                {"name": "tokenBuffer", "type": "CsrfTokenBuffer"},
                {"name": "tokenCapacity", "type": "Int32"},
                {"name": "tokenLengthOut", "type": "OpaquePointer"},
            ],
            "outputs": [{"type": "Int32", "values": ["Int32"]}],
            "effects": [{"action": "read", "path": "system.random"}, {"action": "write", "path": "memory.buffer"}, {"action": "read", "path": "memory.buffer"}],
            "failureMode": {"kind": "status-code", "text": "Zero means success; negative status reports invalid scratch/output pointers, insufficient token capacity, or CSPRNG failure. randomScratch must hold at least 32 bytes; tokenBuffer must hold at least 44 bytes."},
        },
    },
    "standard.net": {
        "net.fetchText": {
            "summary": "Fetch an outbound HTTP URL as text using an explicit request policy.",
            "inputs": [{"name": "request", "type": "HttpGetRequest"}],
            "outputs": [{"type": "Result", "values": ["Result", "HttpTextResponse", "HttpClientErrorCode"]}],
            "effects": [{"action": "write", "path": "network.http.client"}, {"action": "allocate", "path": "heap"}],
            "capabilities": ["networkHttpClient"],
            "failureMode": {"kind": "result", "text": "HttpClientErrorCode reports DNS, connect, timeout, TLS, redirect, body-limit, or backend failures. HTTP non-2xx statuses are response data."},
            "cleanup": {"required": True, "strategy": "extract HttpTextResponse.body and call net.freeTextBody on every ok ownership path", "callTarget": "net.freeTextBody", "argumentName": "body", "argumentType": "HttpClientBodyText", "resultType": "Int32", "resultField": {"name": "body", "type": "HttpClientBodyText"}},
        },
        "net.fetchBytes": {
            "summary": "Prototype outbound HTTP bytes fetch target; exact binary length-safe source API is still partial.",
            "inputs": [{"name": "url", "type": "Url"}, {"name": "timeoutMillis", "type": "NetworkTimeoutMilliseconds"}, {"name": "maxBodyBytes", "type": "ResponseBodyLimitBytes"}],
            "outputs": [{"type": "Result", "values": ["Result", "HttpClientBodyBytes", "HttpClientErrorCode"]}],
            "effects": [{"action": "write", "path": "network.http.client"}, {"action": "allocate", "path": "heap"}],
            "capabilities": ["networkHttpClient"],
            "failureMode": {"kind": "result", "text": "HttpClientErrorCode reports DNS, connect, timeout, TLS, redirect, body-limit, or backend failures."},
            "loweringStatus": "partial",
        },
        "net.freeTextBody": {
            "summary": "Release a text body returned by net.fetchText.",
            "inputs": [{"name": "body", "type": "HttpClientBodyText"}],
            "outputs": [{"type": "Int32", "values": ["Int32"]}],
            "effects": [{"action": "free", "path": "heap"}],
            "failureMode": {"kind": "none", "text": "Cleanup is best-effort; pass only bodies returned by net.fetchText."},
        },
    },
    "standard.sqlite": {
        "sqlite.openDatabase": {
            "summary": "Open a SQLite database handle using the requested open mode. For webServer apps that should not open and close SQLite on every request, open once from webServerStartup, store the SqliteDatabase in module mutable or sharedState process storage, reuse that process-lifetime handle from handlers, and close it from webServerShutdown.",
            "inputs": [{"name": "path", "type": "String"}, {"name": "mode", "type": "SqliteOpenMode"}],
            "outputs": [{"type": "Result", "values": ["Result", "SqliteDatabase", "SqliteDatabaseOpenFailure"]}],
            "effects": [{"action": "readWrite", "path": "database"}],
            "capabilities": ["sqliteDatabaseReadWriter"],
            "failureMode": {"kind": "result", "text": "SqliteDatabaseOpenFailure carries the native status when the path, mode, or SQLite runtime rejects the open."},
            "cleanup": {"required": True, "strategy": "call sqlite.closeDatabase or defer it for every successfully opened database handle", "callTarget": "sqlite.closeDatabase", "argumentName": "database", "argumentType": "SqliteDatabase", "resultType": "Int32", "ignoreKind": "ok", "errorType": "SqliteDatabaseCloseFailure"},
            "agentWarnings": [
                "For webServer apps, the documented reuse pattern is webServerStartup -> sqlite.openDatabase -> set module/sharedState SqliteDatabase -> handlers reuse that handle -> webServerShutdown -> sqlite.closeDatabase. This is a process-lifetime single-handle pattern, not a connection pool; the current native HTTP adapter is blocking and single-threaded.",
                "Do not share one SqliteDatabase across future concurrent dispatch without an explicit guard/owner contract or a real pool. Keep per-request open/close when handler isolation matters more than open cost.",
            ],
        },
        "sqlite.closeDatabase": {
            "summary": "Close an open SQLite database handle.",
            "inputs": [{"name": "database", "type": "SqliteDatabase"}],
            "outputs": [{"type": "Result", "values": ["Result", "Int32", "SqliteDatabaseCloseFailure"]}],
            "effects": [{"action": "readWrite", "path": "database"}],
            "capabilities": ["sqliteDatabaseReadWriter"],
            "failureMode": {"kind": "result", "text": "SqliteDatabaseCloseFailure reports an unclosed statement or native close failure."},
        },
        "sqlite.errorMessage": {
            "summary": "Read SQLite's current database error message pointer.",
            "inputs": [{"name": "database", "type": "SqliteDatabase"}],
            "outputs": [{"type": "SqliteText", "values": ["SqliteText"]}],
            "effects": [{"action": "read", "path": "database"}],
            "capabilities": ["sqliteDatabaseReader"],
            "failureMode": {"kind": "none", "text": "The returned pointer is SQLite-owned and valid until SQLite changes the connection error state."},
        },
        "sqlite.lastInsertRowId": {
            "summary": "Compatibility-only reader for the connection-global row id from the most recent successful insert. New native and webServer code should use INSERT ... RETURNING id and read the returned column from the INSERT statement instead.",
            "inputs": [{"name": "database", "type": "SqliteDatabase"}],
            "outputs": [{"type": "SqliteRowId", "values": ["SqliteRowId"]}],
            "effects": [{"action": "read", "path": "database"}],
            "capabilities": ["sqliteDatabaseReader"],
            "failureMode": {"kind": "sentinel-value", "text": "The value is connection-global state. For generated ids, prefer INSERT ... RETURNING id so the id is returned by the write statement, bound to a named SemanticScript value, and passed explicitly into later statements such as activity-log inserts."},
            "agentWarnings": [
                "SS3639 flags sqlite.lastInsertRowId because it hides generated-id state on the connection. Use usage.migration.rows for the native/webServer-safe INSERT ... RETURNING id pattern.",
                "Do not generate new app code around sqlite.lastInsertRowId unless compatibility with an existing SQL shape is explicitly required.",
            ],
            "migration": SQLITE_GENERATED_ID_RETURNING_GUIDANCE,
        },
        "sqlite.changedRowCount": {
            "summary": "Read how many rows the most recent INSERT/UPDATE/DELETE on the connection changed. Use this to detect a SILENT no-op: an `UPDATE … WHERE id = ?` (or DELETE) that matches no row succeeds with a 0 changed-row count, so without checking this an agent reports success while nothing changed — e.g. toggling a task that does not exist.",
            "inputs": [{"name": "database", "type": "SqliteDatabase"}],
            "outputs": [{"type": "Int32", "values": ["Int32"]}],
            "effects": [{"action": "read", "path": "database"}],
            "capabilities": ["sqliteDatabaseReader"],
            "failureMode": {"kind": "status-count", "text": "A return of 0 after an UPDATE/DELETE means the WHERE clause matched nothing — branch on `changedRowCount == 0` to surface a not-found instead of a false success. Connection-global: read it immediately after the step on the same connection, before any other write."},
        },
        "sqlite.queryScalarInt64": {
            "summary": "Run one static no-parameter SQL read and return column 0 from the first row as Int64. Use this for COUNT(*) / EXISTS-style scalar reads instead of hand-writing prepare/step/column/finalize. Parameterized, multi-column, or multi-row reads still use sqlite.prepareStatement plus bind/step/column/finalize.",
            "inputs": [{"name": "database", "type": "SqliteDatabase"}, {"name": "sql", "type": "SqlText"}],
            "outputs": [{"type": "Result", "values": ["Result", "Int64", "SqliteQueryFailure"]}],
            "effects": [{"action": "read", "path": "database"}],
            "capabilities": ["sqliteDatabaseReader"],
            "failureMode": {"kind": "result", "text": "SqliteQueryFailure carries the native status for prepare, empty result, step, or finalize failure. SQL must be a single static SqlText statement with no bind placeholders."},
            "agentWarnings": [
                "sqlite.queryScalarInt64 owns prepare/step/column/finalize internally, so do not add a separate sqlite.finalizeStatement for it.",
                "This helper intentionally does not bind parameters. Use prepareStatement + bind* for untrusted values.",
            ],
        },
        "sqlite.enableWalMode": {
            "summary": "Enable SQLite WAL journaling on an open database handle without carrying a raw `PRAGMA journal_mode = WAL` SqlText constant in app source. Project builds can also opt in globally with `sqliteJournalMode PROJECT wal`, which applies this after each successful sqlite.openDatabase lowering.",
            "inputs": [{"name": "database", "type": "SqliteDatabase"}],
            "outputs": [{"type": "Result", "values": ["Result", "Int32", "SqliteJournalModeFailure"]}],
            "effects": [{"action": "readWrite", "path": "database"}],
            "capabilities": ["sqliteDatabaseReadWriter"],
            "failureMode": {"kind": "result", "text": "SqliteJournalModeFailure carries the native status when SQLite cannot apply WAL mode to the connection."},
            "agentWarnings": [
                "Prefer `sqliteJournalMode PROJECT wal` in build.sem when every opened database for the project should use WAL.",
                "Call sqlite.enableWalMode once during startup, immediately after sqlite.openDatabase, when only a specific handle should opt in.",
            ],
        },
        "sqlite.beginImmediateTransaction": {
            "summary": "Begin a SQLite IMMEDIATE transaction without carrying a raw `BEGIN IMMEDIATE` SqlText constant in app source.",
            "inputs": [{"name": "database", "type": "SqliteDatabase"}],
            "outputs": [{"type": "Result", "values": ["Result", "Int32", "SqliteTransactionFailure"]}],
            "effects": [{"action": "readWrite", "path": "database"}],
            "capabilities": ["sqliteDatabaseReadWriter"],
            "failureMode": {"kind": "result", "text": "SqliteTransactionFailure carries the native status when SQLite cannot begin the transaction."},
            "agentWarnings": ["Use with sqlite.commitTransaction on the success path and sqlite.rollbackTransaction on failure paths that happen after BEGIN succeeds."],
        },
        "sqlite.commitTransaction": {
            "summary": "Commit the current SQLite transaction without carrying a raw `COMMIT` SqlText constant in app source.",
            "inputs": [{"name": "database", "type": "SqliteDatabase"}],
            "outputs": [{"type": "Result", "values": ["Result", "Int32", "SqliteTransactionFailure"]}],
            "effects": [{"action": "readWrite", "path": "database"}],
            "capabilities": ["sqliteDatabaseReadWriter"],
            "failureMode": {"kind": "result", "text": "SqliteTransactionFailure carries the native status when SQLite cannot commit the current transaction."},
        },
        "sqlite.rollbackTransaction": {
            "summary": "Rollback the current SQLite transaction without carrying a raw `ROLLBACK` SqlText constant in app source.",
            "inputs": [{"name": "database", "type": "SqliteDatabase"}],
            "outputs": [{"type": "Result", "values": ["Result", "Int32", "SqliteTransactionFailure"]}],
            "effects": [{"action": "readWrite", "path": "database"}],
            "capabilities": ["sqliteDatabaseReadWriter"],
            "failureMode": {"kind": "result", "text": "SqliteTransactionFailure carries the native status when SQLite cannot rollback the current transaction."},
        },
        "sqlite.exec": {
            "summary": "Execute a complete SQL statement directly against a database handle.",
            "inputs": [{"name": "database", "type": "SqliteDatabase"}, {"name": "sql", "type": "SqlText"}],
            "outputs": [{"type": "Result", "values": ["Result", "Int32", "SqliteDatabaseExecFailure"]}],
            "effects": [{"action": "readWrite", "path": "database"}],
            "capabilities": ["sqliteDatabaseReadWriter"],
            "failureMode": {"kind": "result", "text": "SqliteDatabaseExecFailure carries the native status; dynamic values must use prepareStatement plus bind rows, not SQL interpolation."},
        },
        "sqlite.execStatus": {
            "summary": "Execute SQL and return the raw SQLite adapter status code.",
            "inputs": [{"name": "database", "type": "SqliteDatabase"}, {"name": "sql", "type": "SqlText"}],
            "outputs": [{"type": "Int32", "values": ["Int32"]}],
            "effects": [{"action": "readWrite", "path": "database"}],
            "capabilities": ["sqliteDatabaseReadWriter"],
            "failureMode": {"kind": "status-code", "text": "Zero means success; non-zero is a SQLite adapter error status."},
        },
        "sqlite.prepareStatement": {
            "summary": "Prepare one SQL statement and return an owned statement handle.",
            "inputs": [{"name": "database", "type": "SqliteDatabase"}, {"name": "sql", "type": "SqlText"}],
            "outputs": [{"type": "Result", "values": ["Result", "SqliteStatement", "SqliteStatementPrepareFailure"]}],
            "effects": [{"action": "readWrite", "path": "database"}],
            "capabilities": ["sqliteDatabaseReadWriter"],
            "failureMode": {"kind": "result", "text": "SqliteStatementPrepareFailure carries the native status; SQL must be a single statement and dynamic values must use ? placeholders."},
            "cleanup": {"required": True, "strategy": "call sqlite.finalizeStatement or defer it for every successfully prepared statement handle", "callTarget": "sqlite.finalizeStatement", "argumentName": "statement", "argumentType": "SqliteStatement", "resultType": "Int32", "ignoreKind": "ok", "errorType": "SqliteStatementFinalizeFailure"},
        },
        "sqlite.finalizeStatement": {
            "summary": "Finalize an owned prepared statement handle.",
            "inputs": [{"name": "statement", "type": "SqliteStatement"}],
            "outputs": [{"type": "Result", "values": ["Result", "Int32", "SqliteStatementFinalizeFailure"]}],
            "effects": [{"action": "readWrite", "path": "database"}],
            "capabilities": ["sqliteDatabaseReadWriter"],
            "failureMode": {"kind": "result", "text": "SqliteStatementFinalizeFailure reports native finalize failure; still treat the handle as consumed."},
        },
        "sqlite.resetStatement": {
            "summary": "Reset a prepared statement so it can be rebound or stepped again.",
            "inputs": [{"name": "statement", "type": "SqliteStatement"}],
            "outputs": [{"type": "Result", "values": ["Result", "Int32", "SqliteStatementResetFailure"]}],
            "effects": [{"action": "readWrite", "path": "database"}],
            "capabilities": ["sqliteDatabaseReadWriter"],
            "failureMode": {"kind": "result", "text": "SqliteStatementResetFailure carries the native reset status."},
        },
        "sqlite.stepStatement": {
            "summary": "Advance a prepared statement and return row/done status on the ok leg.",
            "inputs": [{"name": "statement", "type": "SqliteStatement"}],
            "outputs": [{"type": "Result", "values": ["Result", "SqliteStepResult", "SqliteStatementStepFailure"]}],
            "effects": [{"action": "readWrite", "path": "database"}],
            "capabilities": ["sqliteDatabaseReadWriter"],
            "failureMode": {"kind": "result", "text": "SqliteStatementStepFailure covers native statuses below the row/done range; compare ok values to rowSqliteStepResult or doneSqliteStepResult."},
        },
        "sqlite.bindInt64": {
            "summary": "Bind one Int64 value to a 1-based SQLite parameter index.",
            "inputs": [{"name": "statement", "type": "SqliteStatement"}, {"name": "parameterIndex", "type": "Int32"}, {"name": "value", "type": "Int64"}],
            "outputs": [{"type": "Result", "values": ["Result", "Int32", "SqliteStatementBindFailure"]}],
            "effects": [{"action": "readWrite", "path": "database"}],
            "capabilities": ["sqliteDatabaseReadWriter"],
            "failureMode": {"kind": "result", "text": "SqliteStatementBindFailure carries the native bind status; parameterIndex is 1-based."},
        },
        "sqlite.bindDouble": {
            "summary": "Bind one Float64 value to a 1-based SQLite parameter index.",
            "inputs": [{"name": "statement", "type": "SqliteStatement"}, {"name": "parameterIndex", "type": "Int32"}, {"name": "value", "type": "Float64"}],
            "outputs": [{"type": "Result", "values": ["Result", "Int32", "SqliteStatementBindFailure"]}],
            "effects": [{"action": "readWrite", "path": "database"}],
            "capabilities": ["sqliteDatabaseReadWriter"],
            "failureMode": {"kind": "result", "text": "SqliteStatementBindFailure carries the native bind status; parameterIndex is 1-based."},
        },
        "sqlite.bindText": {
            "summary": "Bind one null-terminated text value to a 1-based SQLite parameter index.",
            "inputs": [{"name": "statement", "type": "SqliteStatement"}, {"name": "parameterIndex", "type": "Int32"}, {"name": "value", "type": "SqliteText"}],
            "outputs": [{"type": "Result", "values": ["Result", "Int32", "SqliteStatementBindFailure"]}],
            "effects": [{"action": "readWrite", "path": "database"}],
            "capabilities": ["sqliteDatabaseReadWriter"],
            "failureMode": {"kind": "result", "text": "SqliteStatementBindFailure carries the native bind status; parameterIndex is 1-based and the text is copied by SQLite."},
        },
        "sqlite.bindBlob": {
            "summary": "Bind one blob pointer and byte count to a 1-based SQLite parameter index.",
            "inputs": [{"name": "statement", "type": "SqliteStatement"}, {"name": "parameterIndex", "type": "Int32"}, {"name": "value", "type": "SqliteBlob"}, {"name": "valueLength", "type": "SqliteByteCount"}],
            "outputs": [{"type": "Result", "values": ["Result", "Int32", "SqliteStatementBindFailure"]}],
            "effects": [{"action": "readWrite", "path": "database"}],
            "capabilities": ["sqliteDatabaseReadWriter"],
            "failureMode": {"kind": "result", "text": "SqliteStatementBindFailure carries the native bind status; parameterIndex is 1-based and the blob bytes are copied by SQLite."},
        },
        "sqlite.bindNull": {
            "summary": "Bind SQLite NULL to a 1-based parameter index.",
            "inputs": [{"name": "statement", "type": "SqliteStatement"}, {"name": "parameterIndex", "type": "Int32"}],
            "outputs": [{"type": "Result", "values": ["Result", "Int32", "SqliteStatementBindFailure"]}],
            "effects": [{"action": "readWrite", "path": "database"}],
            "capabilities": ["sqliteDatabaseReadWriter"],
            "failureMode": {"kind": "result", "text": "SqliteStatementBindFailure carries the native bind status; parameterIndex is 1-based."},
        },
        "sqlite.columnCount": {
            "summary": "Return the number of columns in a prepared statement result row shape.",
            "inputs": [{"name": "statement", "type": "SqliteStatement"}],
            "outputs": [{"type": "Int32", "values": ["Int32"]}],
            "effects": [{"action": "read", "path": "database"}],
            "capabilities": ["sqliteDatabaseReader"],
        },
        "sqlite.columnType": {
            "summary": "Return the SQLite type tag for a 0-based result column index.",
            "inputs": [{"name": "statement", "type": "SqliteStatement"}, {"name": "columnIndex", "type": "Int32"}],
            "outputs": [{"type": "SqliteColumnType", "values": ["SqliteColumnType"]}],
            "effects": [{"action": "read", "path": "database"}],
            "capabilities": ["sqliteDatabaseReader"],
        },
        "sqlite.columnName": {
            "summary": "Return the SQLite-owned name for a 0-based result column index. The pointer belongs to this prepared statement, not a process-global scratch buffer.",
            "inputs": [{"name": "statement", "type": "SqliteStatement"}, {"name": "columnIndex", "type": "Int32"}],
            "outputs": [{"type": "SqliteText", "values": ["SqliteText"]}],
            "effects": [{"action": "read", "path": "database"}],
            "capabilities": ["sqliteDatabaseReader"],
            "failureMode": {"kind": "caller-precondition", "text": "The returned pointer is SQLite-owned by the same statement and is invalidated by that statement's next pointer-returning column read, step, reset, or finalize; copy before retaining it. Other prepared statements do not overwrite this pointer."},
            "agentWarnings": [
                "SS3113 flags using this borrowed pointer after a later same-statement columnText/columnBlob/columnName read, step, or reset. Use or copy it before the next invalidating operation on the same statement.",
            ],
        },
        "sqlite.columnInt64": {
            "summary": "Read a 0-based result column as Int64.",
            "inputs": [{"name": "statement", "type": "SqliteStatement"}, {"name": "columnIndex", "type": "Int32"}],
            "outputs": [{"type": "Int64", "values": ["Int64"]}],
            "effects": [{"action": "read", "path": "database"}],
            "capabilities": ["sqliteDatabaseReader"],
        },
        "sqlite.columnDouble": {
            "summary": "Read a 0-based result column as Float64.",
            "inputs": [{"name": "statement", "type": "SqliteStatement"}, {"name": "columnIndex", "type": "Int32"}],
            "outputs": [{"type": "Float64", "values": ["Float64"]}],
            "effects": [{"action": "read", "path": "database"}],
            "capabilities": ["sqliteDatabaseReader"],
        },
        "sqlite.columnText": {
            "summary": "Read a 0-based result column as SQLite-owned text. The pointer is owned by the same prepared statement; another statement's column reads do not overwrite it.",
            "inputs": [{"name": "statement", "type": "SqliteStatement"}, {"name": "columnIndex", "type": "Int32"}],
            "outputs": [{"type": "SqliteText", "values": ["SqliteText"]}],
            "effects": [{"action": "read", "path": "database"}],
            "capabilities": ["sqliteDatabaseReader"],
            "failureMode": {"kind": "caller-precondition", "text": "Valid only until the same statement's next pointer-returning column read, step, reset, or finalize; closeDatabase also invalidates it. Copy before then if needed."},
            "agentWarnings": [
                "SS3113 flags using this borrowed pointer after a later same-statement columnText/columnBlob/columnName read, step, or reset. Use or copy it before the next invalidating operation on the same statement.",
            ],
        },
        "sqlite.columnBlob": {
            "summary": "Read a 0-based result column as a SQLite-owned blob pointer. The pointer is owned by the same prepared statement; another statement's column reads do not overwrite it.",
            "inputs": [{"name": "statement", "type": "SqliteStatement"}, {"name": "columnIndex", "type": "Int32"}],
            "outputs": [{"type": "SqliteBlob", "values": ["SqliteBlob"]}],
            "effects": [{"action": "read", "path": "database"}],
            "capabilities": ["sqliteDatabaseReader"],
            "failureMode": {"kind": "caller-precondition", "text": "Valid only until the same statement's next pointer-returning column read, step, reset, or finalize; closeDatabase also invalidates it. Pair with sqlite.columnByteCount before consuming."},
            "agentWarnings": [
                "SS3113 flags using this borrowed pointer after a later same-statement columnText/columnBlob/columnName read, step, or reset. Use or copy it before the next invalidating operation on the same statement.",
            ],
        },
        "sqlite.columnByteCount": {
            "summary": "Read the byte count for the current text or blob column value.",
            "inputs": [{"name": "statement", "type": "SqliteStatement"}, {"name": "columnIndex", "type": "Int32"}],
            "outputs": [{"type": "SqliteByteCount", "values": ["SqliteByteCount"]}],
            "effects": [{"action": "read", "path": "database"}],
            "capabilities": ["sqliteDatabaseReader"],
        },
        "sqlite.libraryVersion": {
            "summary": "Return the SQLite library version string from the native runtime.",
            "inputs": [],
            "outputs": [{"type": "SqliteText", "values": ["SqliteText"]}],
            "failureMode": {"kind": "none", "text": "The returned string is runtime-owned static memory."},
        },
    },
}


def _static_inputs(*pairs: tuple[str, str]) -> list[dict]:
    return [{"name": name, "type": type_name} for name, type_name in pairs]


def _static_value_output(type_name: str) -> list[dict]:
    return [{"type": type_name, "values": [type_name]}]


def _static_result_output(ok_type: str, error_type: str) -> list[dict]:
    return [{"type": "Result", "values": ["Result", ok_type, error_type]}]


def _static_target_contract(
    summary: str,
    *,
    inputs: list[dict] | None = None,
    outputs: list[dict] | None = None,
    effects: list[dict] | None = None,
    capabilities: list[str] | None = None,
    failure_kind: str = "none",
    failure_text: str = "",
    cleanup: dict | None = None,
    agent_warnings: list[str] | None = None,
    lowering_status: str = "lowered",
) -> dict:
    payload = {
        "summary": summary,
        "inputs": inputs or [],
        "outputs": outputs or [],
    }
    if effects:
        payload["effects"] = effects
    if capabilities:
        payload["capabilities"] = capabilities
    if failure_kind != "none" or failure_text:
        payload["failureMode"] = {"kind": failure_kind, "text": failure_text}
    if cleanup:
        payload["cleanup"] = cleanup
    if agent_warnings:
        payload["agentWarnings"] = agent_warnings
    if lowering_status != "lowered":
        payload["loweringStatus"] = lowering_status
    return payload


def _register_http_static_targets() -> None:
    http_docs = STD_DOC_STATIC_TARGETS.setdefault("standard.http", {})
    request_effect = [{"action": "read", "path": "http.request"}]
    response_effect = [{"action": "write", "path": "http.response"}]
    status_failure = "Non-zero status reports native HTTP adapter failure."
    form_urlencoded_warning = (
        "This is the application/x-www-form-urlencoded path only. multipart/form-data uses the http.multipartPart* request readers directly against HttpRequest, without caller scratch; the two body-reader families are intentionally separate today."
    )
    multipart_warning = (
        "This is the multipart/form-data path only. application/x-www-form-urlencoded forms use http.requestBodyText followed by http.formField into caller-owned scratch; the two body-reader families are intentionally separate today."
    )
    http_docs.update({
        "http.responseHtml": _static_target_contract(
            "Write an HTML response body with the standard text/html content type.",
            inputs=_static_inputs(("response", "HttpResponse"), ("status", "HttpStatusCode"), ("body", "HttpTextBody")),
            outputs=_static_value_output("Int32"),
            effects=response_effect,
            capabilities=["httpResponseWriter"],
            failure_kind="status-code",
            failure_text=status_failure,
        ),
        "http.responseText": _static_target_contract(
            "Write a text response body with an explicit content type.",
            inputs=_static_inputs(("response", "HttpResponse"), ("status", "HttpStatusCode"), ("body", "HttpTextBody"), ("contentType", "HttpContentType")),
            outputs=_static_value_output("Int32"),
            effects=response_effect,
            capabilities=["httpResponseWriter"],
            failure_kind="status-code",
            failure_text=status_failure,
        ),
        "http.redirect": _static_target_contract(
            "Send a redirect response in one call: writes the Location header and "
            "then an empty text/plain body with the provided status (usually 303 "
            "See Other for POST/redirect/GET). This replaces the repeated "
            "http.responseHeader(Location) + http.responseText(status, \"\") pair.",
            inputs=_static_inputs(("response", "HttpResponse"), ("status", "HttpStatusCode"), ("location", "HttpHeaderValue")),
            outputs=_static_value_output("Int32"),
            effects=response_effect,
            capabilities=["httpResponseWriter"],
            failure_kind="status-code",
            failure_text=status_failure,
        ),
        "http.responseBytes": _static_target_contract(
            "Write a byte response body with an explicit byte length and content type.",
            inputs=_static_inputs(("response", "HttpResponse"), ("status", "HttpStatusCode"), ("body", "HttpByteBody"), ("bodyLength", "HttpBodyLength"), ("contentType", "HttpContentType")),
            outputs=_static_value_output("Int32"),
            effects=response_effect,
            capabilities=["httpResponseWriter"],
            failure_kind="status-code",
            failure_text=status_failure,
        ),
        "http.responseSseEvent": _static_target_contract(
            "Write one Server-Sent Event frame to an HTTP response.",
            inputs=_static_inputs(("response", "HttpResponse"), ("status", "HttpStatusCode"), ("event", "SseEventName"), ("data", "SseEventData")),
            outputs=_static_value_output("Int32"),
            effects=response_effect,
            capabilities=["httpResponseWriter"],
            failure_kind="status-code",
            failure_text=status_failure,
        ),
        "http.responseHeader": _static_target_contract(
            "Write one HTTP response header before the response body is sent. For Set-Cookie session headers, include Secure only after trusted TLS detection; the native HTTP/1.1 adapter does not itself terminate TLS.",
            inputs=_static_inputs(("response", "HttpResponse"), ("name", "HttpHeaderName"), ("value", "HttpHeaderValue")),
            outputs=_static_value_output("Int32"),
            effects=response_effect,
            capabilities=["httpResponseWriter"],
            failure_kind="status-code",
            failure_text=status_failure,
            agent_warnings=[
                "Set-Cookie values for session/auth tokens should use HttpOnly and SameSite. Add Secure only when the request is known HTTPS: either a future direct TLS backend, or a trusted TLS terminator that strips/sets X-Forwarded-Proto before the app reads it with http.requestHeader.",
            ],
        ),
        "http.responseFile": _static_target_contract(
            "Serve a file under a public root directory without allowing path traversal. The native file path stamps Cache-Control, ETag, and Last-Modified when metadata is available; staticRoute also honors exact If-None-Match / If-Modified-Since validators with 304.",
            inputs=_static_inputs(("response", "HttpResponse"), ("status", "HttpStatusCode"), ("rootDirectory", "String"), ("requestedPath", "String")),
            outputs=_static_value_output("Int32"),
            effects=response_effect,
            capabilities=["httpResponseWriter"],
            failure_kind="status-code",
            failure_text="Non-zero status reports missing file, traversal attempt, or native send failure.",
        ),
        "http.ensureDirectory": _static_target_contract(
            "Create a directory path if it does not already exist.",
            inputs=_static_inputs(("directoryPath", "String")),
            outputs=_static_value_output("Int32"),
            effects=[{"action": "write", "path": "filesystem"}],
            failure_kind="status-code",
            failure_text="Non-zero status reports invalid path or filesystem failure.",
        ),
        "http.nowMillis": _static_target_contract(
            "Read the native HTTP runtime clock in milliseconds.",
            outputs=_static_value_output("Int64"),
            effects=[{"action": "read", "path": "clock"}],
        ),
    })
    for target, summary in {
        "http.requestMethod": "Read the dispatched HTTP request method.",
        "http.requestPath": "Read the dispatched HTTP request path.",
    }.items():
        http_docs[target] = _static_target_contract(
            summary,
            inputs=_static_inputs(("request", "HttpRequest")),
            outputs=_static_value_output("HttpRequestValue"),
            effects=request_effect,
            capabilities=["httpRequestReader"],
        )
    for target, input_name, summary in (
        ("http.requestHeader", "name", "Read a named request header value."),
        ("http.requestQueryParam", "name", "Read a named query parameter value."),
        ("http.requestPathParam", "name", "Read a named `:name` or `{name}` route path parameter value."),
        ("http.requestCookie", "cookieName", "Read a named cookie value from the Cookie header."),
    ):
        http_docs[target] = _static_target_contract(
            summary,
            inputs=_static_inputs(("request", "HttpRequest"), (input_name, "String")),
            outputs=_static_value_output("HttpRequestValue"),
            effects=request_effect,
            capabilities=["httpRequestReader"],
            failure_kind="null-sentinel",
            failure_text="Returns null when the named request value is absent or overflows native request scratch.",
        )
    http_docs["http.formField"] = _static_target_contract(
        "Parse an application/x-www-form-urlencoded body for one named field, URL-decode the value, and write it into caller-owned scratch memory. Allocate scratch with memory.allocateMemoryBytes (preferred) or c.malloc, keep it live until all consumers finish, then release it.",
        inputs=_static_inputs(("bodyText", "HttpTextBody"), ("fieldName", "String"), ("scratch", "OpaquePointer"), ("scratchCapacity", "ByteCount")),
        outputs=_static_value_output("HttpRequestValue"),
        effects=request_effect + [{"action": "write", "path": "memory.buffer"}],
        capabilities=["httpRequestReader"],
        failure_kind="null-sentinel",
        failure_text="Returns null when the field is absent, the body is null, percent escapes are malformed, or scratch is too small. Repeated keys return the first matching field.",
        agent_warnings=[
            form_urlencoded_warning,
            "http.formField does not allocate its result. Allocate caller-owned scratch with memory.allocateMemoryBytes (or c.malloc when interop is the point), branch on allocation failure with pointer.isNull, pass the pointer as scratch, and release it with memory.releaseMemoryBytes/c.free after the parsed value is no longer used.",
            "The returned HttpRequestValue aliases that scratch buffer. Do not release or overwrite scratch before validating, authenticating, rendering, or persisting the field value.",
        ],
    )
    http_docs["http.urlDecode"] = _static_target_contract(
        "URL-decode one form/query component into caller-owned scratch memory.",
        inputs=_static_inputs(("value", "String"), ("scratch", "OpaquePointer"), ("scratchCapacity", "ByteCount")),
        outputs=_static_value_output("String"),
        effects=[{"action": "write", "path": "memory.buffer"}],
        failure_kind="null-sentinel",
        failure_text="Returns null when input or scratch is null, a percent escape is malformed, or scratch is too small. `+` decodes to a space for form-compatible decoding.",
    )
    http_docs["http.urlEncode"] = _static_target_contract(
        "Percent-encode one string component into caller-owned scratch memory.",
        inputs=_static_inputs(("value", "String"), ("scratch", "OpaquePointer"), ("scratchCapacity", "ByteCount")),
        outputs=_static_value_output("String"),
        effects=[{"action": "write", "path": "memory.buffer"}],
        failure_kind="null-sentinel",
        failure_text="Returns null when input or scratch is null or scratch is too small. Unreserved RFC 3986 bytes pass through; spaces encode as %20.",
    )
    for target, output_type, summary in (
        (
            "http.requestBodyText",
            "HttpTextBody",
            "Read the request body as text. For JSON credential POST handlers, guard null, parse with json.createDocument, read fields with json.objectFieldAt plus json.cursorString into caller-owned scratch, then destroy the document on every path.",
        ),
        ("http.requestBodyBytes", "HttpByteBody", "Read the request body as bytes."),
    ):
        body_agent_warnings = []
        if target == "http.requestBodyText":
            body_agent_warnings.append(
                "JSON login/credentials POST pattern: read http.requestBodyText, guard with pointer.isNull, parse with json.createDocument, get the root with json.documentRoot, find username/password with json.objectFieldAt, copy values with json.cursorString into caller-owned scratch, and defer json.destroyDocument."
            )
        http_docs[target] = _static_target_contract(
            summary,
            inputs=_static_inputs(("request", "HttpRequest")),
            outputs=_static_value_output(output_type),
            effects=request_effect,
            capabilities=["httpRequestReader"],
            failure_kind="null-sentinel",
            failure_text="Returns null when the body is absent or not available in the requested representation.",
            agent_warnings=body_agent_warnings,
        )
    http_docs["http.requestBodyLength"] = _static_target_contract(
        "Read the request body byte length.",
        inputs=_static_inputs(("request", "HttpRequest")),
        outputs=_static_value_output("HttpBodyLength"),
        effects=request_effect,
        capabilities=["httpRequestReader"],
    )
    http_docs["http.requestValueLength"] = _static_target_contract(
        "Read the byte length of a nullable request-derived value. Null returns 0, so handlers can test cookie/header/query presence without touching request memory directly.",
        inputs=_static_inputs(("value", "HttpRequestValue")),
        outputs=_static_value_output("HttpBodyLength"),
        effects=request_effect,
        capabilities=["httpRequestReader"],
    )
    http_docs["http.requestValueIsEmpty"] = _static_target_contract(
        "Return true when a nullable request-derived value is null or an empty string.",
        inputs=_static_inputs(("value", "HttpRequestValue")),
        outputs=_static_value_output("Bool"),
        effects=request_effect,
        capabilities=["httpRequestReader"],
    )
    for target, output_type, summary in (
        ("http.multipartPartText", "HttpTextBody", "Read one multipart part as text."),
        ("http.multipartPartBytes", "HttpByteBody", "Read one multipart part as bytes."),
        ("http.multipartPartFilename", "HttpRequestValue", "Read one multipart part filename."),
        ("http.multipartPartContentType", "HttpContentType", "Read one multipart part content type."),
    ):
        http_docs[target] = _static_target_contract(
            f"{summary} This reads multipart/form-data directly from HttpRequest and does not parse application/x-www-form-urlencoded bodies.",
            inputs=_static_inputs(("request", "HttpRequest"), ("name", "String")),
            outputs=_static_value_output(output_type),
            effects=request_effect,
            capabilities=["httpRequestReader"],
            failure_kind="null-sentinel",
            failure_text="Returns null when the named multipart part or requested field is absent.",
            agent_warnings=[multipart_warning],
        )
    http_docs["http.multipartPartLength"] = _static_target_contract(
        "Read one multipart part byte length. This reads multipart/form-data directly from HttpRequest and does not parse application/x-www-form-urlencoded bodies.",
        inputs=_static_inputs(("request", "HttpRequest"), ("name", "String")),
        outputs=_static_value_output("HttpBodyLength"),
        effects=request_effect,
        capabilities=["httpRequestReader"],
        agent_warnings=[multipart_warning],
    )


def _register_json_static_targets() -> None:
    json_docs = STD_DOC_STATIC_TARGETS.setdefault("standard.json", {})
    json_deprecated_warning = ["Legacy builder/finder target; prefer JsonDocument CRUD targets for new code when mutation or typed error handling is needed."]
    primitive_types = [
        "Int64", "UInt64", "Int32", "UInt32", "Int16", "UInt16", "Int8", "UInt8",
        "DurationMilliseconds", "MonotonicMilliseconds", "UtcMilliseconds", "Bool", "Float64", "Float32", "String",
    ]
    numeric_types = {
        "Int64", "UInt64", "Int32", "UInt32", "Int16", "UInt16", "Int8", "UInt8",
        "DurationMilliseconds", "MonotonicMilliseconds", "UtcMilliseconds",
        "Float64", "Float32",
    }
    for type_name in primitive_types:
        if type_name in numeric_types:
            # For a number, JSON text IS the plain decimal string, so this is the
            # native, link-in-native/webServer NUMBER-TO-STRING formatter. Agents
            # reach for this instead of c.snprintf or reading integers as TEXT from
            # SQLite (the dashboard field-feedback forced workaround). Searchable as
            # "integer to string" / "format number as text".
            stringify_summary = (
                f"Format one {type_name} as text. For numbers the JSON encoding is "
                f"the plain decimal string, so this is the native {type_name}-to-String "
                f"formatter (integer/number to string, format number as text) — it links "
                f"in native and webServer builds, unlike a standard-library converter. "
                f"Result-shaped (bind ok/error)."
            )
        else:
            stringify_summary = (
                f"Encode one {type_name} value as JSON text using the high-level "
                f"Result-shaped stringify alias."
            )
        json_docs.setdefault(f"json.stringify.{type_name}", _static_target_contract(
            stringify_summary,
            inputs=_static_inputs(("value", type_name)),
            outputs=_static_result_output("JsonText", "JsonEncodeError"),
            failure_kind="result",
            failure_text="JsonEncodeError reports output-capacity, invalid input, or serialization failure. Use `bind ok`, `bind error`, and `branch error`.",
        ))
        json_docs.setdefault(f"json.encode.{type_name}", _static_target_contract(
            f"Encode one {type_name} value as JSON text using the legacy primitive encoder.",
            inputs=_static_inputs(("value", type_name)),
            outputs=_static_value_output("JsonText"),
            agent_warnings=json_deprecated_warning,
        ))
        if type_name != "String":
            json_docs.setdefault(f"json.parse.{type_name}", _static_target_contract(
                f"Parse a JSON {type_name} literal using the high-level Result-shaped parse alias.",
                inputs=_static_inputs(("jsonText", "JsonText")),
                outputs=_static_result_output(type_name, "JsonDecodeError"),
                failure_kind="result",
                failure_text="JsonDecodeError reports malformed, truncated, or wrong-type input. Use `bind ok`, `bind error`, and `branch error`.",
            ))
            json_docs.setdefault(f"json.decode.{type_name}", _static_target_contract(
                f"Decode one JSON primitive literal as {type_name} using the legacy primitive decoder.",
                inputs=_static_inputs(("value", "JsonText")),
                outputs=_static_value_output(type_name),
                failure_kind="sentinel-value",
                failure_text="Malformed input returns the runtime default for this primitive decoder; use high-level parse or JsonDocument APIs when malformed input must be distinguished.",
                agent_warnings=json_deprecated_warning,
            ))
    json_docs.setdefault("json.createBuilder", _static_target_contract(
        "Create a legacy JSON builder with a bounded output capacity.",
        inputs=_static_inputs(("capacity", "JsonCapacityBytes")),
        outputs=_static_value_output("JsonBuilder"),
        failure_kind="null-sentinel",
        failure_text="Returns null when the native JSON builder cannot allocate the requested capacity.",
        cleanup={"required": True, "strategy": "call json.destroyBuilder after finishBuilder or on every failure path", "callTarget": "json.destroyBuilder", "argumentName": "builder", "argumentType": "JsonBuilder", "resultType": "Int32"},
        agent_warnings=json_deprecated_warning,
    ))
    json_docs.setdefault("json.destroyBuilder", _static_target_contract(
        "Destroy a legacy JSON builder handle.",
        inputs=_static_inputs(("builder", "JsonBuilder")),
        outputs=_static_value_output("Int32"),
        agent_warnings=json_deprecated_warning,
    ))
    for target in ("json.objectOpen", "json.objectClose", "json.arrayOpen", "json.arrayClose", "json.elementNull"):
        json_docs.setdefault(target, _static_target_contract(
            f"Apply legacy builder operation {target}.",
            inputs=_static_inputs(("builder", "JsonBuilder")),
            outputs=_static_value_output("Int32"),
            failure_kind="status-code",
            failure_text="Non-zero status reports invalid builder state or capacity failure.",
            agent_warnings=json_deprecated_warning,
        ))
    for target, value_type in {
        "json.fieldInt64": "Int64",
        "json.fieldDouble": "Float64",
        "json.fieldBool": "Bool",
        "json.fieldString": "JsonStringValue",
    }.items():
        json_docs.setdefault(target, _static_target_contract(
            f"Write a legacy object field with {value_type} value.",
            inputs=_static_inputs(("builder", "JsonBuilder"), ("fieldName", "JsonFieldName"), ("value", value_type)),
            outputs=_static_value_output("Int32"),
            failure_kind="status-code",
            failure_text="Non-zero status reports invalid builder state or capacity failure.",
            agent_warnings=json_deprecated_warning,
        ))
    json_docs.setdefault("json.fieldNull", _static_target_contract(
        "Write a legacy object field with null value.",
        inputs=_static_inputs(("builder", "JsonBuilder"), ("fieldName", "JsonFieldName")),
        outputs=_static_value_output("Int32"),
        failure_kind="status-code",
        failure_text="Non-zero status reports invalid builder state or capacity failure.",
        agent_warnings=json_deprecated_warning,
    ))
    for target, value_type in {
        "json.elementInt64": "Int64",
        "json.elementDouble": "Float64",
        "json.elementBool": "Bool",
        "json.elementString": "JsonStringValue",
    }.items():
        json_docs.setdefault(target, _static_target_contract(
            f"Append a legacy array element with {value_type} value.",
            inputs=_static_inputs(("builder", "JsonBuilder"), ("value", value_type)),
            outputs=_static_value_output("Int32"),
            failure_kind="status-code",
            failure_text="Non-zero status reports invalid builder state or capacity failure.",
            agent_warnings=json_deprecated_warning,
        ))
    json_docs.setdefault("json.finishBuilder", _static_target_contract(
        "Finish a legacy builder and return its JSON text buffer.",
        inputs=_static_inputs(("builder", "JsonBuilder")),
        outputs=_static_value_output("JsonText"),
        failure_kind="null-sentinel",
        failure_text="Returns null when the builder is invalid or incomplete.",
        agent_warnings=json_deprecated_warning,
    ))
    json_docs.setdefault("json.builderLength", _static_target_contract(
        "Read the current output length of a legacy JSON builder.",
        inputs=_static_inputs(("builder", "JsonBuilder")),
        outputs=_static_value_output("JsonCapacityBytes"),
        agent_warnings=json_deprecated_warning,
    ))
    json_docs.setdefault("json.hasField", _static_target_contract(
        "Return non-zero when a flat JSON object has a named field.",
        inputs=_static_inputs(("jsonText", "JsonText"), ("fieldName", "JsonFieldName")),
        outputs=_static_value_output("Int32"),
        failure_kind="sentinel-value",
        failure_text="Non-zero means present; zero means absent or malformed flat-object input.",
        agent_warnings=json_deprecated_warning,
    ))
    json_docs.setdefault("json.findString", _static_target_contract(
        "Find a flat object string field into caller-owned scratch memory.",
        inputs=_static_inputs(("jsonText", "JsonText"), ("fieldName", "JsonFieldName"), ("scratch", "JsonScratchBuffer"), ("scratchCapacity", "JsonCapacityBytes")),
        outputs=_static_value_output("JsonStringValue"),
        failure_kind="null-sentinel",
        failure_text="Returns null when the field is absent, wrong type, malformed, or too large for scratch.",
        agent_warnings=json_deprecated_warning,
    ))
    for target, value_type in {"json.findInt64": "Int64", "json.findDouble": "Float64", "json.findBool": "Bool"}.items():
        json_docs.setdefault(target, _static_target_contract(
            f"Find a flat object field as {value_type}, returning missingDefault when not usable.",
            inputs=_static_inputs(("jsonText", "JsonText"), ("fieldName", "JsonFieldName"), ("missingDefault", value_type)),
            outputs=_static_value_output(value_type),
            failure_kind="sentinel-value",
            failure_text="missingDefault is returned when the field is absent, wrong type, or malformed.",
            agent_warnings=json_deprecated_warning,
        ))
    json_docs.setdefault("json.documentLength", _static_target_contract("Read the serialized length estimate for a JsonDocument.", inputs=_static_inputs(("document", "JsonDocument")), outputs=_static_value_output("JsonCapacityBytes")))
    for target, inputs in {
        "json.arrayElementAt": _static_inputs(("document", "JsonDocument"), ("cursor", "JsonCursor"), ("index", "Int64")),
        "json.cursorParent": _static_inputs(("document", "JsonDocument"), ("cursor", "JsonCursor")),
        "json.cursorAtPath": _static_inputs(("document", "JsonDocument"), ("path", "JsonPath")),
    }.items():
        json_docs.setdefault(target, _static_target_contract(f"Navigate a JsonDocument cursor with {target}.", inputs=inputs, outputs=_static_result_output("JsonCursor", "JsonAccessError"), failure_kind="result", failure_text="JsonAccessError reports missing path, wrong kind, or invalid cursor."))
    json_docs.setdefault("json.cursorKind", _static_target_contract("Read a JsonCursor value kind.", inputs=_static_inputs(("document", "JsonDocument"), ("cursor", "JsonCursor")), outputs=_static_value_output("JsonValueKind")))
    json_docs.setdefault("json.cursorIsNull", _static_target_contract("Return true when a JsonCursor points at a JSON null value.", inputs=_static_inputs(("document", "JsonDocument"), ("cursor", "JsonCursor")), outputs=_static_value_output("Bool")))
    for target, value_type in {"json.cursorDouble": "Float64", "json.cursorBool": "Bool"}.items():
        json_docs.setdefault(target, _static_target_contract(f"Read a cursor as {value_type}, returning missingDefault when not usable.", inputs=_static_inputs(("document", "JsonDocument"), ("cursor", "JsonCursor"), ("missingDefault", value_type)), outputs=_static_value_output(value_type), failure_kind="sentinel-value", failure_text="missingDefault is returned when the cursor is missing or wrong type."))
    json_docs.setdefault("json.cursorObjectFieldCount", _static_target_contract("Read the number of fields under an object cursor.", inputs=_static_inputs(("document", "JsonDocument"), ("cursor", "JsonCursor")), outputs=_static_result_output("Int64", "JsonAccessError"), failure_kind="result", failure_text="JsonAccessError reports wrong kind or invalid cursor."))
    json_docs.setdefault("json.cursorObjectFieldNameAt", _static_target_contract("Read the field name at a 0-based object field index into scratch memory.", inputs=_static_inputs(("document", "JsonDocument"), ("cursor", "JsonCursor"), ("index", "Int64"), ("scratch", "JsonScratchBuffer"), ("scratchCapacity", "JsonCapacityBytes")), outputs=_static_result_output("JsonFieldName", "JsonAccessError"), failure_kind="result", failure_text="JsonAccessError reports wrong kind, invalid index, or scratch capacity failure."))
    json_docs.setdefault("json.cursorObjectFieldValueAt", _static_target_contract("Read the field value cursor at a 0-based object field index.", inputs=_static_inputs(("document", "JsonDocument"), ("cursor", "JsonCursor"), ("index", "Int64")), outputs=_static_result_output("JsonCursor", "JsonAccessError"), failure_kind="result", failure_text="JsonAccessError reports wrong kind or invalid index."))
    for target, value_type in {
        "json.setObjectFieldDouble": "Float64",
        "json.setObjectFieldBool": "Bool",
    }.items():
        json_docs.setdefault(target, _static_target_contract(f"Set an object field to a {value_type} value.", inputs=_static_inputs(("document", "JsonDocument"), ("cursor", "JsonCursor"), ("fieldName", "JsonFieldName"), ("value", value_type)), outputs=_static_result_output("Int32", "JsonAccessError"), failure_kind="result", failure_text="JsonAccessError reports wrong kind, field limits, or capacity failure."))
    for target, value_type in {"json.setObjectFieldObject": "JsonCursor", "json.setObjectFieldArray": "JsonCursor"}.items():
        json_docs.setdefault(target, _static_target_contract(f"Create a child container at an object field and return its cursor.", inputs=_static_inputs(("document", "JsonDocument"), ("cursor", "JsonCursor"), ("fieldName", "JsonFieldName")), outputs=_static_result_output(value_type, "JsonAccessError"), failure_kind="result", failure_text="JsonAccessError reports wrong kind, field limits, or capacity failure."))
    json_docs.setdefault("json.setObjectFieldJsonText", _static_target_contract("Set an object field from raw JSON text and return the inserted cursor.", inputs=_static_inputs(("document", "JsonDocument"), ("cursor", "JsonCursor"), ("fieldName", "JsonFieldName"), ("jsonText", "JsonText")), outputs=_static_result_output("JsonCursor", "JsonAccessError"), failure_kind="result", failure_text="JsonAccessError reports malformed input, wrong kind, field limits, or capacity failure."))
    for prefix in ("appendArrayElement", "insertArrayElement", "replaceArrayElement"):
        indexed = prefix != "appendArrayElement"
        for suffix, value_type in {"String": "JsonStringValue", "Int64": "Int64", "Double": "Float64", "Bool": "Bool"}.items():
            inputs = _static_inputs(("document", "JsonDocument"), ("cursor", "JsonCursor"), *(([("index", "Int64")] if indexed else [])), ("value", value_type))
            json_docs.setdefault(f"json.{prefix}{suffix}", _static_target_contract(f"{prefix} {suffix} under an array cursor.", inputs=inputs, outputs=_static_result_output("Int32", "JsonAccessError"), failure_kind="result", failure_text="JsonAccessError reports wrong kind, invalid index, or capacity failure."))
        for suffix in ("Null", "Object", "Array", "JsonText"):
            extra_inputs = [] if suffix in {"Null", "Object", "Array"} else [("jsonText", "JsonText")]
            inputs = _static_inputs(("document", "JsonDocument"), ("cursor", "JsonCursor"), *(([("index", "Int64")] if indexed else [])), *extra_inputs)
            ok_type = "Int32" if suffix == "Null" else "JsonCursor"
            json_docs.setdefault(f"json.{prefix}{suffix}", _static_target_contract(f"{prefix} {suffix} under an array cursor.", inputs=inputs, outputs=_static_result_output(ok_type, "JsonAccessError"), failure_kind="result", failure_text="JsonAccessError reports wrong kind, invalid index, malformed JSON text, or capacity failure."))
    json_docs.setdefault("json.removeObjectField", _static_target_contract("Remove a named field from an object cursor.", inputs=_static_inputs(("document", "JsonDocument"), ("cursor", "JsonCursor"), ("fieldName", "JsonFieldName")), outputs=_static_result_output("Int32", "JsonAccessError"), failure_kind="result", failure_text="JsonAccessError reports wrong kind or missing field."))
    json_docs.setdefault("json.removeArrayElementAt", _static_target_contract("Remove the element at a 0-based array index.", inputs=_static_inputs(("document", "JsonDocument"), ("cursor", "JsonCursor"), ("index", "Int64")), outputs=_static_result_output("Int32", "JsonAccessError"), failure_kind="result", failure_text="JsonAccessError reports wrong kind or invalid index."))
    for target in ("json.clearObject", "json.clearArray"):
        json_docs.setdefault(target, _static_target_contract(f"Clear all children from {target.rsplit('.', 1)[1]}.", inputs=_static_inputs(("document", "JsonDocument"), ("cursor", "JsonCursor")), outputs=_static_result_output("Int32", "JsonAccessError"), failure_kind="result", failure_text="JsonAccessError reports wrong kind or invalid cursor."))


def _register_compiler_static_targets() -> None:
    console_docs = STD_DOC_STATIC_TARGETS.setdefault("compiler.console", {})
    console_effect = [{"action": "write", "path": "console.stdout"}]
    console_failure = "The native console writer returns an error status when stdout cannot accept the write."
    console_result = _static_result_output("Void", "Int32")
    console_docs.update({
        "console.writeLine": _static_target_contract(
            "Write one UTF-8 string followed by a newline to stdout.",
            inputs=_static_inputs(("text", "String")),
            outputs=console_result,
            effects=console_effect,
            failure_kind="result",
            failure_text=console_failure,
        ),
        "console.writeIntegerLine": _static_target_contract(
            "Write one Int64 followed by a newline to stdout.",
            inputs=_static_inputs(("value", "Int64")),
            outputs=console_result,
            effects=console_effect,
            failure_kind="result",
            failure_text=console_failure,
        ),
        "console.writeInteger": _static_target_contract(
            "Compatibility alias for console.writeIntegerLine.",
            inputs=_static_inputs(("value", "Int64")),
            outputs=console_result,
            effects=console_effect,
            failure_kind="result",
            failure_text=console_failure,
            agent_warnings=["Prefer console.writeIntegerLine in new code; console.writeInteger is an alias."],
        ),
        "console.writeFloatLine": _static_target_contract(
            "Write one Float64 followed by a newline to stdout using the native printf default precision.",
            inputs=_static_inputs(("value", "Float64")),
            outputs=console_result,
            effects=console_effect,
            failure_kind="result",
            failure_text=console_failure,
        ),
    })

    math_docs = STD_DOC_STATIC_TARGETS.setdefault("compiler.math", {})
    for target in ("math.addInt64", "math.subtractInt64", "math.multiplyInt64", "math.divideInt64", "math.moduloInt64"):
        failure_kind = "caller-precondition" if target in {"math.divideInt64", "math.moduloInt64"} else "none"
        failure_text = "Caller must ensure right is non-zero; runtime checks may trap on zero divisors." if failure_kind != "none" else ""
        math_docs[target] = _static_target_contract(
            f"Compute {target.rsplit('.', 1)[1]} on two Int64 operands.",
            inputs=_static_inputs(("left", "Int64"), ("right", "Int64")),
            outputs=_static_value_output("Int64"),
            failure_kind=failure_kind,
            failure_text=failure_text,
        )
    for target in (
        "math.equalInt64", "math.notEqualInt64", "math.lessThanInt64", "math.lessThanOrEqualInt64",
        "math.greaterThanInt64", "math.greaterThanOrEqualInt64",
    ):
        math_docs[target] = _static_target_contract(
            f"Compare two Int64 operands with {target.rsplit('.', 1)[1]}.",
            inputs=_static_inputs(("left", "Int64"), ("right", "Int64")),
            outputs=_static_value_output("Bool"),
        )
    for value_type, targets in (
        ("Int64", ("math.minInt64", "math.maxInt64")),
        ("Int32", ("math.minInt32", "math.maxInt32")),
        ("UInt64", ("math.minUInt64", "math.maxUInt64")),
        ("UInt32", ("math.minUInt32", "math.maxUInt32")),
        ("Float64", ("math.minFloat64", "math.maxFloat64")),
    ):
        for target in targets:
            math_docs[target] = _static_target_contract(
                f"Return the {'smaller' if '.min' in target else 'larger'} of two {value_type} operands.",
                inputs=_static_inputs(("left", value_type), ("right", value_type)),
                outputs=_static_value_output(value_type),
            )
    for value_type, target in (
        ("Int64", "math.clampInt64"),
        ("Int32", "math.clampInt32"),
        ("UInt64", "math.clampUInt64"),
        ("UInt32", "math.clampUInt32"),
        ("Float64", "math.clampFloat64"),
    ):
        math_docs[target] = _static_target_contract(
            f"Clamp one {value_type} value into the inclusive [low, high] range.",
            inputs=_static_inputs(("value", value_type), ("low", value_type), ("high", value_type)),
            outputs=_static_value_output(value_type),
        )
    for target in (
        "math.equalInt32", "math.notEqualInt32", "math.lessThanInt32", "math.lessThanOrEqualInt32",
        "math.greaterThanInt32", "math.greaterThanOrEqualInt32",
    ):
        math_docs[target] = _static_target_contract(
            f"Compare two Int32 operands with {target.rsplit('.', 1)[1]}.",
            inputs=_static_inputs(("left", "Int32"), ("right", "Int32")),
            outputs=_static_value_output("Bool"),
        )
    for target in ("math.bitwiseAndInt64", "math.bitwiseOrInt64", "math.bitwiseXorInt64"):
        math_docs[target] = _static_target_contract(
            f"Apply {target.rsplit('.', 1)[1]} to two Int64 operands.",
            inputs=_static_inputs(("left", "Int64"), ("right", "Int64")),
            outputs=_static_value_output("Int64"),
        )
    for target in ("math.shiftLeftInt64", "math.shiftRightLogicalInt64", "math.shiftRightArithmeticInt64"):
        math_docs[target] = _static_target_contract(
            f"Shift an Int64 value with {target.rsplit('.', 1)[1]}.",
            inputs=_static_inputs(("left", "Int64"), ("right", "Int64")),
            outputs=_static_value_output("Int64"),
            failure_kind="caller-precondition",
            failure_text="Caller must ensure right is a shift count in [0, 63].",
        )
    math_docs["math.bitwiseNotInt64"] = _static_target_contract(
        "Flip every bit in one Int64 operand.",
        inputs=_static_inputs(("value", "Int64")),
        outputs=_static_value_output("Int64"),
    )
    for target in ("math.addFloat64", "math.subtractFloat64", "math.multiplyFloat64", "math.divideFloat64"):
        math_docs[target] = _static_target_contract(
            f"Compute {target.rsplit('.', 1)[1]} on two Float64 operands.",
            inputs=_static_inputs(("left", "Float64"), ("right", "Float64")),
            outputs=_static_value_output("Float64"),
        )
    for target in (
        "math.equalFloat64", "math.notEqualFloat64", "math.lessThanFloat64", "math.lessThanOrEqualFloat64",
        "math.greaterThanFloat64", "math.greaterThanOrEqualFloat64",
    ):
        math_docs[target] = _static_target_contract(
            f"Compare two Float64 operands with {target.rsplit('.', 1)[1]}.",
            inputs=_static_inputs(("left", "Float64"), ("right", "Float64")),
            outputs=_static_value_output("Bool"),
        )
    for target in ("math.intToFloat", "math.convertInt64ToFloat64"):
        math_docs[target] = _static_target_contract(
            "Convert one Int64 value to Float64.",
            inputs=_static_inputs(("inputValue", "Int64")),
            outputs=_static_value_output("Float64"),
        )
    for target in ("math.floatToInt", "math.convertFloat64ToInt64"):
        math_docs[target] = _static_target_contract(
            "Convert one Float64 value to Int64 by truncating toward zero.",
            inputs=_static_inputs(("inputValue", "Float64")),
            outputs=_static_value_output("Int64"),
        )
    math_docs["math.signExtendInt32ToInt64"] = _static_target_contract(
        "Sign-extend one Int32 value to Int64.",
        inputs=_static_inputs(("inputValue", "Int32")),
        outputs=_static_value_output("Int64"),
    )
    math_docs["math.truncateInt64ToInt32"] = _static_target_contract(
        "Truncate one Int64 value to Int32.",
        inputs=_static_inputs(("inputValue", "Int64")),
        outputs=_static_value_output("Int32"),
    )
    math_docs["math.checkedMultiplyInt64"] = _static_target_contract(
        "Multiply two Int64 operands and report overflow on the error leg.",
        inputs=_static_inputs(("left", "Int64"), ("right", "Int64")),
        outputs=_static_result_output("Int64", "Bool"),
        failure_kind="result",
        failure_text="The error leg is true when signed Int64 multiplication overflows.",
    )

    pointer_docs = STD_DOC_STATIC_TARGETS.setdefault("compiler.pointer", {})
    pointer_docs.update({
        "pointer.loadByte": _static_target_contract(
            "Read one byte from buffer plus offset and return it as Int32.",
            inputs=_static_inputs(("buffer", "OpaquePointer"), ("offset", "ByteCount")),
            outputs=_static_value_output("Int32"),
            effects=[{"action": "read", "path": "memory.buffer"}],
            failure_kind="caller-precondition",
            failure_text="Caller must ensure buffer is non-null and offset is in bounds for the allocation.",
        ),
        "pointer.storeByte": _static_target_contract(
            "Write the low byte of value into buffer plus offset.",
            inputs=_static_inputs(("buffer", "OpaquePointer"), ("offset", "ByteCount"), ("value", "Int64")),
            outputs=_static_value_output("Int32"),
            effects=[{"action": "write", "path": "memory.buffer"}],
            failure_kind="caller-precondition",
            failure_text="Caller must ensure buffer is non-null, writable, and offset is in bounds for the allocation.",
        ),
        "pointer.offset": _static_target_contract(
            "Return buffer plus offset without dereferencing it.",
            inputs=_static_inputs(("buffer", "OpaquePointer"), ("offset", "ByteCount")),
            outputs=_static_value_output("OpaquePointer"),
            failure_kind="caller-precondition",
            failure_text="Caller must ensure the computed pointer remains within the same allocation or one past it before dereferencing.",
        ),
        "pointer.difference": _static_target_contract(
            "Return the byte-address difference between two pointers as Int64.",
            inputs=_static_inputs(("left", "OpaquePointer"), ("right", "OpaquePointer")),
            outputs=_static_value_output("Int64"),
            failure_kind="caller-precondition",
            failure_text="Caller must ensure both pointers belong to the same allocation for the difference to be meaningful.",
        ),
        "pointer.isNull": _static_target_contract(
            "Return true when pointer is null.",
            inputs=_static_inputs(("pointer", "OpaquePointer")),
            outputs=_static_value_output("Bool"),
        ),
    })

    text_docs = STD_DOC_STATIC_TARGETS.setdefault("compiler.text", {})
    text_docs["text.concat"] = _static_target_contract(
        "Concatenate two strings into a caller-owned buffer and return it as a "
        "String (string builder / append / join two strings / build a string). "
        "Lowers to a bounded snprintf with a fixed compiler-owned format, so there "
        "is no format-string-injection risk (unlike hand-written c.snprintf) and it "
        "links in EVERY target including native and webServer (unlike a standard-"
        "library converter that fails native links). Provide a buffer (e.g. from "
        "c.malloc) of `capacity` bytes; output is truncated to fit and null-terminated.",
        inputs=_static_inputs(
            ("left", "String"), ("right", "String"),
            ("buffer", "OpaquePointer"), ("capacity", "ByteCount")),
        outputs=_static_value_output("String"),
        effects=[{"action": "read", "path": "memory.buffer"},
                 {"action": "write", "path": "memory.buffer"}],
        failure_kind="caller-precondition",
        failure_text="Caller must ensure buffer is non-null and writable for `capacity` bytes; "
                     "if the combined length exceeds capacity-1 the result is truncated.",
    )
    text_docs["text.concat3"] = _static_target_contract(
        "Concatenate three strings into a caller-owned buffer and return it as a "
        "String — the prefix + value + suffix shape (e.g. building a Set-Cookie "
        "header) in one bounded call. Same safety/linking as text.concat.",
        inputs=_static_inputs(
            ("first", "String"), ("second", "String"), ("third", "String"),
            ("buffer", "OpaquePointer"), ("capacity", "ByteCount")),
        outputs=_static_value_output("String"),
        effects=[{"action": "read", "path": "memory.buffer"},
                 {"action": "write", "path": "memory.buffer"}],
        failure_kind="caller-precondition",
        failure_text="Caller must ensure buffer is writable for `capacity` bytes; output is truncated to fit.",
    )
    text_docs["text.fromInt64"] = _static_target_contract(
        "Format an Int64 as a decimal String into a caller-owned buffer (integer "
        "to string / number to text / format number as text / itoa). The discoverable native int→string "
        "formatter; links in every target. Avoids reading integers as TEXT from "
        "SQLite or dropping to c.snprintf. (json.stringify.Int64 does the same job.)",
        inputs=_static_inputs(("value", "Int64"), ("buffer", "OpaquePointer"), ("capacity", "ByteCount")),
        outputs=_static_value_output("String"),
        effects=[{"action": "write", "path": "memory.buffer"}],
        failure_kind="caller-precondition",
        failure_text="Caller must ensure buffer is writable for `capacity` bytes (>= 21 covers any Int64).",
    )
    text_docs["text.fromFloat64"] = _static_target_contract(
        "Format a Float64 as a String into a caller-owned buffer (float/number to "
        "string / format number as text) using %g. The discoverable native float→string formatter; links in "
        "every target.",
        inputs=_static_inputs(("value", "Float64"), ("buffer", "OpaquePointer"), ("capacity", "ByteCount")),
        outputs=_static_value_output("String"),
        effects=[{"action": "write", "path": "memory.buffer"}],
        failure_kind="caller-precondition",
        failure_text="Caller must ensure buffer is writable for `capacity` bytes.",
    )
    text_docs["text.contains"] = _static_target_contract(
        "Return true when `needle` occurs anywhere in `haystack` (compiler-lowered "
        "strstr != NULL). Native substring search / string contains; links in every "
        "target. Use it to check a request body contains a field, route by a path "
        "fragment, etc., without a stdlib op or a hand-rolled byte scan.",
        inputs=_static_inputs(("haystack", "String"), ("needle", "String")),
        outputs=_static_value_output("Bool"),
        effects=[{"action": "read", "path": "memory.buffer"}],
        failure_kind="caller-precondition",
        failure_text="Caller must ensure both values are non-null, null-terminated Strings.",
    )
    text_docs["text.substring"] = _static_target_contract(
        "Copy a bounded substring (`length` bytes starting at `start`) from `value` "
        "into a caller-owned buffer, null-terminate, and return the buffer as a "
        "String. Bounded — truncates to capacity-1 if length is too large, so the "
        "result is always safe. Pair with text.indexOf to extract the part before/"
        "after a delimiter (e.g. split `key=value` at the `=` offset). Compiler-"
        "lowered memcpy + null-terminator; links in every target.",
        inputs=_static_inputs(
            ("value", "String"), ("start", "Int64"), ("length", "Int64"),
            ("buffer", "OpaquePointer"), ("capacity", "ByteCount")),
        outputs=_static_value_output("String"),
        effects=[{"action": "read", "path": "memory.buffer"},
                 {"action": "write", "path": "memory.buffer"}],
        failure_kind="caller-precondition",
        failure_text="Caller must ensure start + length is in bounds for `value` and "
                     "buffer is writable for capacity bytes; length truncates to capacity-1 if larger.",
    )
    text_docs["text.indexOf"] = _static_target_contract(
        "Return the byte offset of the first occurrence of `needle` in `haystack`, "
        "or -1 if not found (compiler-lowered strstr position). Use for tokenizing "
        "/ parsing where text.contains (Bool) is not enough — e.g. splitting "
        "`key=value` by finding the `=` index. Links in every target.",
        inputs=_static_inputs(("haystack", "String"), ("needle", "String")),
        outputs=_static_value_output("Int64"),
        effects=[{"action": "read", "path": "memory.buffer"}],
        failure_kind="sentinel-value",
        failure_text="Returns -1 when `needle` is not present in `haystack`.",
    )
    text_docs["text.endsWith"] = _static_target_contract(
        "Return true when `value` ends with `suffix` (compiler-lowered branchless "
        "tail match: strncmp(value + (len_v - len_s), suffix, len_s) == 0, with a "
        "bounds guard for len_s > len_v). Anchored suffix match for content-type / "
        "extension routing (does this path end with `.css`). Links in every target.",
        inputs=_static_inputs(("value", "String"), ("suffix", "String")),
        outputs=_static_value_output("Bool"),
        effects=[{"action": "read", "path": "memory.buffer"}],
        failure_kind="caller-precondition",
        failure_text="Caller must ensure both values are non-null, null-terminated Strings.",
    )
    text_docs["text.startsWith"] = _static_target_contract(
        "Return true when `value` begins with `prefix` (compiler-lowered "
        "strncmp(value, prefix, strlen(prefix)) == 0). Anchored prefix match for "
        "routing (does this path start with /api/) — unlike text.contains, which "
        "matches anywhere. Links in every target.",
        inputs=_static_inputs(("value", "String"), ("prefix", "String")),
        outputs=_static_value_output("Bool"),
        effects=[{"action": "read", "path": "memory.buffer"}],
        failure_kind="caller-precondition",
        failure_text="Caller must ensure both values are non-null, null-terminated Strings.",
    )
    text_docs["text.equals"] = _static_target_contract(
        "Return true when two strings are byte-equal (compiler-lowered strcmp == 0). "
        "Native string equality / compare strings that links in every target — unlike "
        "stdlib.string.compareCString, which fails native/webServer links. Lets app "
        "logic branch on `status == \"open\"` without libc or a SQL round-trip.",
        inputs=_static_inputs(("left", "String"), ("right", "String")),
        outputs=_static_value_output("Bool"),
        effects=[{"action": "read", "path": "memory.buffer"}],
        failure_kind="caller-precondition",
        failure_text="Caller must ensure both values are non-null, null-terminated Strings.",
    )
    text_docs["text.length"] = _static_target_contract(
        "Return the byte length of a String (compiler-lowered strlen). Use "
        "`text.length(value)` then compare to 0 to validate emptiness instead of "
        "hand-rolling a pointer.loadByte check; links in every target.",
        inputs=_static_inputs(("value", "String")),
        outputs=_static_value_output("Int64"),
        effects=[{"action": "read", "path": "memory.buffer"}],
        failure_kind="caller-precondition",
        failure_text="Caller must ensure value is a non-null, null-terminated String.",
    )

    html_docs = STD_DOC_STATIC_TARGETS.setdefault("compiler.html", {})
    html_docs["html.fragmentConcat"] = _static_target_contract(
        "Concatenate two HtmlFragment values into a caller-owned buffer and "
        "return the buffer as HtmlFragment. This is the HTML-typed sibling of "
        "text.concat for reusable fragment helpers, render variable length list "
        "folds, and html fragment join workflows: it links in "
        "native/webServer builds, avoids binding a String result as HtmlFragment, "
        "and keeps SS4302's domain check meaningful.",
        inputs=_static_inputs(
            ("left", "HtmlFragment"), ("right", "HtmlFragment"),
            ("buffer", "OpaquePointer"), ("capacity", "ByteCount")),
        outputs=_static_value_output("HtmlFragment"),
        effects=[{"action": "read", "path": "memory.buffer"},
                 {"action": "write", "path": "memory.buffer"}],
        failure_kind="caller-precondition",
        failure_text="Caller must ensure buffer is non-null and writable for `capacity` bytes; output is truncated to fit and null-terminated.",
    )

    c_docs = STD_DOC_STATIC_TARGETS.setdefault("compiler.c", {})
    heap_cleanup = {"required": True, "strategy": "call c.free on every non-null ownership path", "callTarget": "c.free", "argumentName": "ptr", "argumentType": "OpaquePointer", "resultType": "Void"}
    c_docs.update({
        "c.malloc": _static_target_contract(
            "Allocate size bytes of uninitialized heap memory; release the returned pointer with c.free.",
            inputs=_static_inputs(("size", "ByteCount")),
            outputs=_static_value_output("OpaquePointer"),
            effects=[{"action": "allocate", "path": "heap"}],
            failure_kind="null-sentinel",
            failure_text="Returns null when the allocation fails.",
            cleanup=heap_cleanup,
            agent_warnings=["Prefer standard.memory.allocateMemoryBytes plus standard.memory.releaseMemoryBytes over raw c.malloc in new app code."],
        ),
        "c.calloc": _static_target_contract(
            "Allocate zero-initialized heap memory for count elements of size bytes; release with c.free.",
            inputs=_static_inputs(("count", "ByteCount"), ("size", "ByteCount")),
            outputs=_static_value_output("OpaquePointer"),
            effects=[{"action": "allocate", "path": "heap"}],
            failure_kind="null-sentinel",
            failure_text="Returns null when the allocation fails or count * size cannot be allocated.",
            cleanup=heap_cleanup,
        ),
        "c.alignedAlloc": _static_target_contract(
            "Allocate size bytes with the requested alignment; release with c.free.",
            inputs=_static_inputs(("alignment", "ByteCount"), ("size", "ByteCount")),
            outputs=_static_value_output("OpaquePointer"),
            effects=[{"action": "allocate", "path": "heap"}],
            failure_kind="null-sentinel",
            failure_text="Returns null when allocation fails or alignment/size preconditions are not satisfied by the host C runtime.",
            cleanup=heap_cleanup,
            agent_warnings=["Prefer a portable standard.memory wrapper once one exists; raw aligned allocation still requires caller-specific alignment and size preconditions."],
        ),
        "c.realloc": _static_target_contract(
            "Resize a heap allocation; success transfers ownership to the returned pointer, while failure leaves the input pointer owned by the caller.",
            inputs=_static_inputs(("ptr", "OpaquePointer"), ("size", "ByteCount")),
            outputs=_static_value_output("OpaquePointer"),
            effects=[{"action": "allocate", "path": "heap"}, {"action": "free", "path": "heap"}],
            failure_kind="null-sentinel",
            failure_text="Returns null when resizing fails; preserve the original pointer until success is known.",
            lowering_status="partial",
            agent_warnings=["Do not generate c.realloc from docs rows yet; ownership transfer requires caller-specific success and failure cleanup paths."],
        ),
        "c.free": _static_target_contract(
            "Release a pointer previously returned by a compatible heap allocator.",
            inputs=_static_inputs(("ptr", "OpaquePointer")),
            outputs=_static_value_output("Void"),
            effects=[{"action": "free", "path": "heap"}],
            failure_kind="none",
            failure_text="Pass only null or a live allocation pointer not already freed.",
        ),
        "c.exit": _static_target_contract(
            "Terminate the current process with the supplied status code.",
            inputs=_static_inputs(("code", "Int32")),
            outputs=_static_value_output("Void"),
            effects=[{"action": "write", "path": "process"}],
            agent_warnings=["c.exit does not return to SemanticScript cleanup paths; prefer returning ExitCode from main when possible."],
        ),
        "c.abort": _static_target_contract(
            "Abnormally terminate the current process.",
            inputs=[],
            outputs=_static_value_output("Void"),
            effects=[{"action": "write", "path": "process"}],
            agent_warnings=["c.abort bypasses normal cleanup and should not be generated for ordinary error handling."],
        ),
        "c.putchar": _static_target_contract(
            "Write one character code to stdout using the C runtime.",
            inputs=_static_inputs(("c", "Int32")),
            outputs=_static_value_output("Int32"),
            effects=[{"action": "write", "path": "console.stdout"}],
            failure_kind="negative-status",
            failure_text="A negative return status reports EOF or write failure.",
        ),
        "c.snprintf": _static_target_contract(
            "Format into a caller-owned bounded buffer using a compile-time constant format string.",
            inputs=_static_inputs(("buffer", "String"), ("bufferSize", "ByteCount"), ("format", "String")),
            outputs=_static_value_output("Int32"),
            effects=[{"action": "write", "path": "memory.buffer"}],
            failure_kind="snprintf-status",
            failure_text="A negative return reports formatting failure; a return value greater than or equal to bufferSize means truncation. Extra varargs follow the format argument.",
            agent_warnings=["The linter requires format to reference an immutable String constant. Never pass request/runtime data as the format string."],
        ),
        "c.strlen": _static_target_contract(
            "Return the byte length of a null-terminated string, excluding the terminator.",
            inputs=_static_inputs(("s", "String")),
            outputs=_static_value_output("ByteCount"),
            effects=[{"action": "read", "path": "memory.buffer"}],
            failure_kind="caller-precondition",
            failure_text="Caller must pass a non-null, null-terminated string.",
        ),
        "c.strcpy": _static_target_contract(
            "Copy a null-terminated string into a destination buffer.",
            inputs=_static_inputs(("destination", "String"), ("source", "String")),
            outputs=_static_value_output("String"),
            effects=[{"action": "write", "path": "memory.buffer"}, {"action": "read", "path": "memory.buffer"}],
            failure_kind="caller-precondition",
            failure_text="Caller must prove destination capacity is greater than source length plus the null terminator.",
            lowering_status="lowered",
            agent_warnings=["Prefer c.strcpySafe or c.snprintf when capacity is known; unbounded strcpy is rejected by strict safety checks in generated app code."],
        ),
        "c.strcat": _static_target_contract(
            "Append a null-terminated source string to a destination string.",
            inputs=_static_inputs(("destination", "String"), ("source", "String")),
            outputs=_static_value_output("String"),
            effects=[{"action": "write", "path": "memory.buffer"}, {"action": "read", "path": "memory.buffer"}],
            failure_kind="caller-precondition",
            failure_text="Caller must prove destination has enough remaining capacity for both strings and the null terminator.",
            agent_warnings=["Avoid generated c.strcat in web apps; prefer tracked write offsets plus c.snprintf or a bounded domain formatter."],
        ),
        "c.strcpySafe": _static_target_contract(
            "Copy a string into a caller-owned buffer with an explicit destination capacity.",
            inputs=_static_inputs(("destination", "String"), ("destinationSize", "ByteCount"), ("source", "String")),
            outputs=_static_value_output("Int32"),
            effects=[{"action": "write", "path": "memory.buffer"}, {"action": "read", "path": "memory.buffer"}],
            failure_kind="status-code",
            failure_text="Non-zero status reports null pointers, insufficient capacity, or platform runtime constraint failure.",
            lowering_status="partial",
            agent_warnings=["Availability follows the host C runtime; prefer c.snprintf for portable formatting when possible."],
        ),
        "c.strcatSafe": _static_target_contract(
            "Append a string into a caller-owned buffer with an explicit destination capacity.",
            inputs=_static_inputs(("destination", "String"), ("destinationSize", "ByteCount"), ("source", "String")),
            outputs=_static_value_output("Int32"),
            effects=[{"action": "write", "path": "memory.buffer"}, {"action": "read", "path": "memory.buffer"}],
            failure_kind="status-code",
            failure_text="Non-zero status reports null pointers, insufficient capacity, or platform runtime constraint failure.",
            lowering_status="partial",
            agent_warnings=["Availability follows the host C runtime; prefer tracked offsets plus c.snprintf for portable generated code."],
        ),
        "c.fopen": _static_target_contract(
            "Open a file with a C runtime mode string; close the returned handle with c.fclose.",
            inputs=_static_inputs(("path", "String"), ("mode", "String")),
            outputs=_static_value_output("FileHandle"),
            effects=[{"action": "open", "path": "file"}],
            failure_kind="null-sentinel",
            failure_text="Returns null when the file cannot be opened.",
            cleanup={"required": True, "strategy": "call c.fclose on every non-null ownership path", "callTarget": "c.fclose", "argumentName": "stream", "argumentType": "FileHandle", "resultType": "Int32"},
        ),
        "c.fclose": _static_target_contract(
            "Close a C FileHandle previously returned by c.fopen.",
            inputs=_static_inputs(("stream", "FileHandle")),
            outputs=_static_value_output("Int32"),
            effects=[{"action": "close", "path": "file"}],
            failure_kind="status-code",
            failure_text="Zero means success; EOF/non-zero reports close or flush failure.",
        ),
    })


_register_http_static_targets()
_register_json_static_targets()
_register_compiler_static_targets()
STD_DOC_STATIC_TYPES = {
    "standard.html": {
        "HtmlFragment": {
            "kind": "typeAlias",
            "underlyingType": "String",
            "summary": "Hydrated HTML fragment role alias inserted raw only into text-content positions where markup composition is intentional.",
            "usage": [
                "Use values produced by `html.hydrate.*` or trusted fragment helpers.",
                "Do not bind ordinary String concatenation results as `HtmlFragment`; use `html.fragmentConcat` for fragment folds.",
                "Fragments cannot hydrate quoted attributes or URL-bearing attributes.",
            ],
            "source": "standard.html type alias",
            "sourceFile": "SemanticScript/std/html/main.sem",
            "line": 33,
        },
        "HtmlTrustedFragment": {
            "kind": "typeAlias",
            "underlyingType": "String",
            "summary": "Trusted HTML fragment role alias for caller-reviewed markup inserted raw only into text-content positions.",
            "usage": [
                "Reserve for reviewed or sanitized markup where raw insertion is intentional.",
                "Do not use for quoted attributes or URL-bearing attributes.",
            ],
            "source": "standard.html type alias",
            "sourceFile": "SemanticScript/std/html/main.sem",
            "line": 34,
        },
        "HtmlDocument": {
            "kind": "typeAlias",
            "underlyingType": "String",
            "summary": "Full hydrated HTML document role alias, suitable for HTML response bodies after hydration.",
            "usage": [
                "Use as a rendered document/body value, not as an attribute value.",
                "Document values insert raw only in text-content positions when composed into another template.",
            ],
            "source": "standard.html type alias",
            "sourceFile": "SemanticScript/std/html/main.sem",
            "line": 35,
        },
        "HtmlSafeUrl": {
            "kind": "typeAlias",
            "underlyingType": "String",
            "summary": "Trusted URL text role alias required for HTML URL-bearing attributes.",
            "usage": [
                "Use `HtmlSafeUrl` for dynamic holes in `href`, `src`, `action`, `formaction`, and `poster` attributes.",
                "Plain `String` remains valid for text and non-URL quoted attribute holes, where hydration escapes it, but plain `String` is rejected in URL-bearing attributes.",
                "Create `HtmlSafeUrl` values only through std/compiler-owned validation or another explicit trust boundary; do not relabel arbitrary user input.",
            ],
            "exampleRows": [
                "storage local immutable profileHref HtmlSafeUrl \"/profile\"",
                "argument hydratePageCall profileHref HtmlSafeUrl profileHref",
            ],
            "source": "standard.html type alias",
            "sourceFile": "SemanticScript/std/html/main.sem",
            "line": 36,
        },
    },
    "standard.http": {
        "HttpStatusCode": {
            "kind": "typeAlias",
            "underlyingType": "Int32",
            "summary": "HTTP status-code role type used by native HTTP response writers.",
            "usage": [
                "Declare status constants as `HttpStatusCode` or `Int32` numeric values, then pass them to `status HttpStatusCode` arguments.",
                "Use numeric HTTP codes such as 200, 404, and 500; do not use stale dotted values such as `HttpStatus.Ok`.",
            ],
            "exampleRows": [
                "storage local immutable okStatus HttpStatusCode 200",
                "argument responseWriteCall status HttpStatusCode okStatus",
            ],
            "source": "standard.http type alias",
            "sourceFile": "SemanticScript/std/http/main.sem",
            "line": 33,
        },
        "HttpHeaderValue": {
            "kind": "typeAlias",
            "underlyingType": "String",
            "summary": "HTTP response/request header value role type used by `http.responseHeader` and header constants.",
            "usage": [
                "For Set-Cookie session/auth headers, include HttpOnly and SameSite by default.",
                "Append the `Secure` cookie attribute only when HTTPS is known: with today's native HTTP adapter that means a trusted TLS terminator strips and sets `X-Forwarded-Proto: https`; otherwise omit Secure for local HTTP or serve behind HTTPS.",
                "Use `http.requestHeader` with `forwardedProtoHeaderName`, guard null with `pointer.isNull`, then compare with `text.equals` against `forwardedProtoHttpsValue` before choosing the Secure suffix.",
                "For static assets, `staticRoute` and `http.responseFile` stamp `cacheControlHeaderName`, `etagHeaderName`, and `lastModifiedHeaderName`; custom handlers can read `ifNoneMatchHeaderName` / `ifModifiedSinceHeaderName` and choose their own 304 policy.",
            ],
            "exampleRows": [
                "storage local immutable cookieHeaderName HttpHeaderName setCookieHeaderName",
                "storage local immutable forwardedProtoName HttpHeaderName forwardedProtoHeaderName",
                "storage local immutable cacheHeaderName HttpHeaderName cacheControlHeaderName",
                "storage local immutable cacheHeaderValue HttpHeaderValue staticAssetCacheControlHeaderValue",
                "argument forwardedProtoReadCall name String forwardedProtoName",
                "argument protoHttpsCheckCall right String forwardedProtoHttpsValue",
            ],
            "source": "standard.http type alias",
            "sourceFile": "SemanticScript/std/http/main.sem",
            "line": 35,
        },
        "HttpTextBody": {
            "kind": "typeAlias",
            "underlyingType": "String",
            "summary": "HTTP text response body role type for `http.responseHtml` and `http.responseText`.",
            "usage": ["Pass a String-compatible value to body slots declared as `HttpTextBody`."],
            "source": "standard.http type alias",
            "sourceFile": "SemanticScript/std/http/main.sem",
            "line": 37,
        },
        "HttpContentType": {
            "kind": "typeAlias",
            "underlyingType": "String",
            "summary": "HTTP Content-Type header role type for response writers that accept explicit content types.",
            "usage": ["Prefer exported constants such as `plainTextContentType`, `htmlContentType`, `jsonContentType`, or `sseContentType` when available."],
            "source": "standard.http type alias",
            "sourceFile": "SemanticScript/std/http/main.sem",
            "line": 36,
        },
        "HttpRequestValue": {
            "kind": "typeAlias",
            "underlyingType": "String",
            "summary": "Nullable request-derived string role returned by native HTTP request readers.",
            "usage": ["Treat missing headers, cookies, path parameters, and query parameters as sentinel/empty request values according to the specific reader docs."],
            "source": "standard.http type alias",
            "sourceFile": "SemanticScript/std/http/main.sem",
            "line": 40,
        },
        "SessionTtlMillis": {
            "kind": "typeAlias",
            "underlyingType": "Int64",
            "summary": "Session time-to-live duration in milliseconds for `http.sessionExpiresAt`.",
            "usage": [
                "Use immutable Int64 constants such as `sessionDefaultTtlMillis` as the value passed to a `SessionTtlMillis` argument row.",
                "Call `http.nowMillis`, then `http.sessionExpiresAt`, when creating a session.",
            ],
            "exampleRows": [
                "call nowCall http.nowMillis",
                "argument expiresAtCall ttlMillis SessionTtlMillis sessionDefaultTtlMillis",
            ],
            "source": "standard.http type alias",
            "sourceFile": "SemanticScript/std/http/main.sem",
            "line": 41,
        },
        "SessionExpiresAtMillis": {
            "kind": "typeAlias",
            "underlyingType": "Int64",
            "summary": "Absolute Unix epoch millisecond timestamp when a session expires.",
            "usage": [
                "Persist the value returned by `http.sessionExpiresAt` with the session record.",
                "On authenticated requests, read `http.nowMillis` and call `http.sessionIsExpired`; reject the session when the result is true.",
            ],
            "exampleRows": [
                "bind value expiresAtMillis SessionExpiresAtMillis expiresAtCall",
                "argument sessionExpiredCall expiresAtMillis SessionExpiresAtMillis storedExpiresAtMillis",
            ],
            "source": "standard.http type alias",
            "sourceFile": "SemanticScript/std/http/main.sem",
            "line": 42,
        },
        "HttpByteBody": {
            "kind": "typeAlias",
            "underlyingType": "OpaquePointer",
            "summary": "HTTP byte-body pointer role paired with `HttpBodyLength` for binary response writers.",
            "usage": ["Pass an explicit byte length with every `HttpByteBody`; do not rely on string terminators for binary payloads."],
            "source": "standard.http type alias",
            "sourceFile": "SemanticScript/std/http/main.sem",
            "line": 38,
        },
        "HttpBodyLength": {
            "kind": "typeAlias",
            "underlyingType": "ByteCount",
            "summary": "HTTP body byte-count role paired with `HttpByteBody`.",
            "usage": ["Keep the byte count tied to the buffer lifetime and pass it to `bodyLength HttpBodyLength` slots."],
            "source": "standard.http type alias",
            "sourceFile": "SemanticScript/std/http/main.sem",
            "line": 39,
        },
    },
    "standard.sqlite": {
        "SqliteOpenMode": {
            "kind": "enum",
            "repr": "Int32",
            "summary": "SQLite database open-mode enum for `sqlite.openDatabase`.",
            "cases": [
                {"name": "readOnlySqliteOpenMode", "value": 1},
                {"name": "readWriteSqliteOpenMode", "value": 2},
                {"name": "readWriteCreateSqliteOpenMode", "value": 6},
                {"name": "inMemorySqliteOpenMode", "value": 14},
            ],
            "usage": [
                "Use the named case constants where possible, for example `argument openDatabaseCall mode SqliteOpenMode readWriteCreateSqliteOpenMode`.",
                "The values mirror SQLite open flags: READONLY=1, READWRITE=2, CREATE=4, MEMORY=8.",
            ],
            "exampleRows": [
                "call openDatabaseCall sqlite.openDatabase",
                "argument openDatabaseCall path String databasePath",
                "argument openDatabaseCall mode SqliteOpenMode readWriteCreateSqliteOpenMode",
                "run openDatabaseCall",
            ],
            "source": "built-in enum and standard.sqlite export",
            "sourceFile": "SemanticScript/std/sqlite/main.sem",
            "line": 29,
        },
        "SqliteStepResult": {
            "kind": "enum",
            "repr": "Int32",
            "summary": "SQLite statement step-result enum returned by `sqlite.stepStatement`.",
            "cases": [
                {"name": "rowSqliteStepResult", "value": 100},
                {"name": "doneSqliteStepResult", "value": 101},
            ],
            "usage": ["Compare step results against the named cases to distinguish row availability from completion."],
            "source": "built-in enum and standard.sqlite export",
            "sourceFile": "SemanticScript/std/sqlite/main.sem",
            "line": 35,
        },
        "SqliteColumnType": {
            "kind": "enum",
            "repr": "Int32",
            "summary": "SQLite column-type enum returned by `sqlite.columnType`.",
            "cases": [
                {"name": "integerSqliteColumnType", "value": 1},
                {"name": "floatSqliteColumnType", "value": 2},
                {"name": "textSqliteColumnType", "value": 3},
                {"name": "blobSqliteColumnType", "value": 4},
                {"name": "nullSqliteColumnType", "value": 5},
            ],
            "usage": ["Use column-type cases before selecting typed column readers when the schema is not already known."],
            "source": "built-in enum and standard.sqlite export",
            "sourceFile": "SemanticScript/std/sqlite/main.sem",
            "line": 39,
        },
        "SqlText": {
            "kind": "typeAlias",
            "underlyingType": "String",
            "summary": "Trusted SQL text role used by SQLite statement and exec operations.",
            "usage": [
                "Use `SqlText` for SQL constants and prefer `sql body NAME` rows in strict executable surfaces.",
                "Bind dynamic values through sqlite bind operations instead of interpolating them into SQL text.",
            ],
            "source": "standard.sqlite type alias",
            "sourceFile": "SemanticScript/std/sqlite/main.sem",
            "line": 24,
        },
        "SqliteDatabase": {
            "kind": "typeAlias",
            "underlyingType": "OpaquePointer",
            "summary": "Opaque SQLite database handle returned by `sqlite.openDatabase` and closed by `sqlite.closeDatabase`.",
            "usage": [
                "Close each successfully opened database on every ownership path.",
                "For a webServer process-lifetime handle, open in webServerStartup, assign the SqliteDatabase to module mutable storage or sharedState process storage, reuse it from handlers, and close it in webServerShutdown.",
                "This is single-process handle reuse, not a connection pool. The current native HTTP adapter is blocking and single-threaded; future concurrent dispatch needs an explicit guard, owner, or pool contract before sharing the handle.",
            ],
            "source": "standard.sqlite type alias",
            "sourceFile": "SemanticScript/std/sqlite/main.sem",
            "line": 21,
        },
        "SqliteStatement": {
            "kind": "typeAlias",
            "underlyingType": "OpaquePointer",
            "summary": "Opaque SQLite prepared-statement handle returned by `sqlite.prepareStatement` and finalized by `sqlite.finalizeStatement`.",
            "usage": ["Finalize each successfully prepared statement before closing the database."],
            "source": "standard.sqlite type alias",
            "sourceFile": "SemanticScript/std/sqlite/main.sem",
            "line": 22,
        },
        "SqliteQueryFailure": {
            "kind": "typeAlias",
            "underlyingType": "Int32",
            "summary": "SQLite status code role returned on the error leg of `sqlite.queryScalarInt64`.",
            "usage": [
                "Treat nonzero values as prepare, empty-result, step, or finalize failures from the one-shot scalar helper.",
                "Read `sqlite.errorMessage` on the same database when native detail is needed.",
            ],
            "source": "standard.sqlite type alias",
            "sourceFile": "SemanticScript/std/sqlite/main.sem",
            "line": 28,
        },
        "SqliteJournalModeFailure": {
            "kind": "typeAlias",
            "underlyingType": "Int32",
            "summary": "SQLite status code role returned on the error leg of `sqlite.enableWalMode`.",
            "usage": [
                "Use `sqliteJournalMode PROJECT wal` in build.sem for project-wide WAL opt-in.",
                "Use `sqlite.enableWalMode` during startup when WAL applies to one explicit database handle.",
                "Read `sqlite.errorMessage` on the same database when native detail is needed.",
            ],
            "source": "standard.sqlite type alias",
            "sourceFile": "SemanticScript/std/sqlite/main.sem",
            "line": 30,
        },
        "SqliteTransactionFailure": {
            "kind": "typeAlias",
            "underlyingType": "Int32",
            "summary": "SQLite status code role returned on transaction helper error legs.",
            "usage": [
                "Use with sqlite.beginImmediateTransaction, sqlite.commitTransaction, and sqlite.rollbackTransaction.",
                "On a failure after BEGIN succeeds, route cleanup through sqlite.rollbackTransaction before returning the original error where possible.",
            ],
            "source": "standard.sqlite type alias",
            "sourceFile": "SemanticScript/std/sqlite/main.sem",
            "line": 29,
        },
    },
    "standard.bcrypt": {
        "BcryptPlaintextPassword": {
            "kind": "typeAlias",
            "underlyingType": "String",
            "summary": "Untrusted plaintext-password role accepted by bcrypt.hashPassword and bcrypt.verifyPassword.",
            "usage": [
                "This is a String-backed role at argument sites: a value declared as `String` can be passed to a `BcryptPlaintextPassword` argument row.",
                "A guarded `HttpRequestValue` returned by `http.formField` for a password field may also be passed directly at the bcrypt plaintext argument row; the row is the trust-boundary evidence and the value must not be logged or persisted.",
                "Prefer `String` storage for literals when module-scope role-alias string constants are not supported by codegen; the role applies at the bcrypt argument slot.",
                "Never persist or log plaintext password values.",
            ],
            "exampleRows": [
                "call passwordFieldCall http.formField",
                "argument passwordFieldCall body HttpRequestValue requestBodyText",
                "argument passwordFieldCall name String passwordFieldName",
                "argument passwordFieldCall scratch OpaquePointer passwordScratchBuffer",
                "argument passwordFieldCall scratchCapacity Int64 passwordScratchCapacity",
                "run passwordFieldCall",
                "bind value passwordValue HttpRequestValue passwordFieldCall",
                "call passwordMissingCall pointer.isNull",
                "argument passwordMissingCall pointer OpaquePointer passwordValue",
                "run passwordMissingCall",
                "bind value passwordMissing Bool passwordMissingCall",
                "branch if condition passwordMissing target <missingPasswordLabel>",
                "argument hashPasswordCall plaintext BcryptPlaintextPassword passwordValue",
                "storage local immutable passwordText String \"correct-horse-battery-staple\"",
                "argument hashPasswordCall plaintext BcryptPlaintextPassword passwordText",
            ],
            "source": "standard.bcrypt type alias",
            "sourceFile": "SemanticScript/std/bcrypt/main.sem",
            "line": 29,
        },
        "BcryptPasswordHash": {
            "kind": "typeAlias",
            "underlyingType": "String",
            "summary": "Trusted bcrypt `$2b$NN$...` hash role accepted by bcrypt.verifyPassword.",
            "usage": [
                "This is a String-backed role at argument sites: a database String/SqliteText value that is trusted by schema or prior validation can be passed as `BcryptPasswordHash`.",
                "A successful bcrypt.hashPassword output buffer is a null-terminated hash string; it may be passed as the expected hash while the caller-owned buffer remains live.",
                "Validate persisted hashes with length 60 and `$2b$` prefix policy before treating them as trusted.",
            ],
            "exampleRows": [
                "argument verifyPasswordCall expectedHash BcryptPasswordHash storedPasswordHash",
            ],
            "source": "standard.bcrypt type alias",
            "sourceFile": "SemanticScript/std/bcrypt/main.sem",
            "line": 30,
        },
        "BcryptHashBuffer": {
            "kind": "typeAlias",
            "underlyingType": "OpaquePointer",
            "summary": "Caller-owned output buffer role for bcrypt.hashPassword.",
            "usage": [
                "This is an OpaquePointer-backed role at argument sites: a buffer returned by c.malloc or memory.allocateMemoryBytes can be passed as `BcryptHashBuffer`.",
                "Allocate at least bcryptHashBufferRequiredBytes (61) bytes and keep the buffer live until all hash reads, persistence, or verify calls are complete.",
                "Release the buffer with c.free or memory.releaseMemoryBytes, preferably via defer.",
            ],
            "exampleRows": [
                "call allocateHashBufferCall c.malloc",
                "argument hashPasswordCall outBuffer BcryptHashBuffer hashBuffer",
                "defer releaseHashBufferDefer c.free hashBuffer",
            ],
            "source": "standard.bcrypt type alias",
            "sourceFile": "SemanticScript/std/bcrypt/main.sem",
            "line": 31,
        },
        "SessionTokenHash": {
            "kind": "typeAlias",
            "underlyingType": "String",
            "summary": "Trusted at-rest verifier for a SessionToken, produced by bcrypt.hashSessionTokenResult and checked by bcrypt.verifySessionTokenResult.",
            "usage": [
                "This is a String-backed role at argument sites: persisted token hashes can be passed as `SessionTokenHash` after schema or prior validation.",
                "Store SessionTokenHash values produced by bcrypt.hashSessionTokenResult instead of raw SessionToken values; leaked hashes still require bcrypt work to test.",
                "Use bcrypt.verifySessionTokenResult for presented-token checks so mismatch and runtime failure stay distinct.",
            ],
            "exampleRows": [
                "argument hashSessionTokenCall token SessionToken sessionToken",
                "argument hashSessionTokenCall outBuffer BcryptHashBuffer sessionHashBuffer",
                "argument verifySessionTokenCall expectedHash SessionTokenHash storedSessionTokenHash",
            ],
            "source": "standard.bcrypt type alias",
            "sourceFile": "SemanticScript/std/bcrypt/main.sem",
            "line": 35,
        },
        "CsrfToken": {
            "kind": "typeAlias",
            "underlyingType": "String",
            "summary": "Trusted URL-safe anti-CSRF nonce produced by bcrypt.issueCsrfToken.",
            "usage": [
                "Issue with native-linkable bcrypt.issueCsrfToken, store server-side or inside an integrity-protected session, and embed the token in forms.",
                "Compare submitted form values with text.equals before mutating requests.",
                "Do not reuse SessionToken values as CSRF tokens; the separate role keeps bearer credentials and form nonces distinct.",
            ],
            "exampleRows": [
                "call issueCsrfTokenCall bcrypt.issueCsrfToken",
                "argument issueCsrfTokenCall tokenBuffer CsrfTokenBuffer csrfTokenBuffer",
                "argument csrfCompareCall right CsrfToken storedCsrfToken",
            ],
            "source": "standard.bcrypt type alias",
            "sourceFile": "SemanticScript/std/bcrypt/main.sem",
            "line": 38,
        },
        "CsrfTokenBuffer": {
            "kind": "typeAlias",
            "underlyingType": "OpaquePointer",
            "summary": "Caller-owned output buffer role for bcrypt.issueCsrfToken.",
            "usage": [
                "Allocate at least csrfTokenBufferRequiredBytes (44) bytes and keep the buffer live until form rendering or persistence is complete.",
                "Release the buffer with c.free or memory.releaseMemoryBytes, preferably via defer.",
            ],
            "exampleRows": [
                "call allocateCsrfTokenBufferCall c.malloc",
                "argument issueCsrfTokenCall tokenBuffer CsrfTokenBuffer csrfTokenBuffer",
                "defer releaseCsrfTokenBufferDefer c.free csrfTokenBuffer",
            ],
            "source": "standard.bcrypt type alias",
            "sourceFile": "SemanticScript/std/bcrypt/main.sem",
            "line": 39,
        },
    },
    "standard.json": {
        "JsonValueKind": {
            "kind": "enum",
            "repr": "Int32",
            "summary": "JSON cursor-kind enum used by document reader and builder APIs.",
            "cases": [
                {"name": "objectJsonValueKind", "value": 0},
                {"name": "arrayJsonValueKind", "value": 1},
                {"name": "stringJsonValueKind", "value": 2},
                {"name": "integerJsonValueKind", "value": 3},
                {"name": "doubleJsonValueKind", "value": 4},
                {"name": "booleanJsonValueKind", "value": 5},
                {"name": "nullJsonValueKind", "value": 6},
            ],
            "usage": ["Use named cases instead of raw integers when selecting or checking JSON cursor kinds."],
            "source": "standard.json enum",
            "sourceFile": "SemanticScript/std/json/main.sem",
            "line": 45,
        },
    },
    "compiler.http": {
        "MiddlewareControl": {
            "kind": "enum",
            "repr": "Int32",
            "summary": "Built-in native HTTP middleware control enum.",
            "cases": [
                {"name": "continueMiddlewareControl", "value": 0},
                {"name": "shortCircuitMiddlewareControl", "value": 1},
            ],
            "usage": [
                "Route middleware operations must declare `output operation OP MiddlewareControl`.",
                "`continueMiddlewareControl` allows the route handler to run; `shortCircuitMiddlewareControl` skips it after the middleware writes a response.",
            ],
            "source": "compiler built-in enum",
            "sourceFile": "docs/reference/syntax-inventory.md",
            "line": 334,
        },
    },
}
AUTHORITY_ACTIONS = frozenset({
    "allocate",
    "close",
    "execute",
    "open",
    "read",
    "send",
    "write",
})
CLEAN_DIRECTORY_NAMES = frozenset({"build", ".semcache", "__pycache__"})
CLEAN_FILE_SUFFIXES = frozenset({
    ".exe",
    ".ll",
    ".bc",
    ".obj",
    ".o",
    ".pdb",
    ".res",
    ".rc",
    ".vsix",
})
CLEAN_EXACT_RELATIVE_PATHS = frozenset({"apps/taskforge-tui/todos.json"})
CHECK_DIAGNOSTIC_WINDOW = 40
CHECK_TOOL_ERROR_WINDOW = 20
CHECK_REFERENCE_WINDOW = 40
FIX_REPAIR_WINDOW = 30
GRAPH_NODE_WINDOW = 80
GRAPH_EDGE_WINDOW = 160
SLICE_CALL_WINDOW = 25
SLICE_CALLER_WINDOW = 15
SLICE_CONTROL_FLOW_WINDOW = 25
SLICE_RETURN_WINDOW = 10
TEST_RESULT_WINDOW = 20
DEV_WATCH_FILE_WINDOW = 30
DEV_INTERFACE_MODULE_WINDOW = 20
SKILL_REGISTRY = (
    {
        "name": "getting-started",
        "description": "Project orientation: first commands, repository map, skill loading order, and change-surface rules.",
        "files": (
            "docs/getting-started.md",
            "docs/overview.md",
            "docs/README.md",
        ),
    },
    {
        "name": "language-core",
        "description": "Core SemanticScript language shape: modules, operations, rows, types, and dataflow.",
        "files": (
            "docs/language/README.md",
            "docs/language/program-structure.md",
            "docs/language/operations-dataflow.md",
            "docs/language/types-values.md",
        ),
    },
    {
        "name": "errors-effects-capabilities",
        "description": "Effect, failure, capability, and authority guidance for agent-safe SemanticScript edits.",
        "files": (
            "docs/language/errors-effects-capabilities.md",
            "docs/language/concurrency-time-cleanup.md",
        ),
    },
    {
        "name": "syntax-reference",
        "description": "Compact row, verb, and implementation-status reference for current SemanticScript syntax.",
        "files": (
            "docs/reference/verb-index.md",
            "docs/reference/syntax-inventory.md",
        ),
    },
    {
        "name": "graph-and-slice",
        "description": "Agent workflows for context retrieval, graph inspection, and semantic slicing.",
        "files": (
            "docs/agents.md",
            "docs/toolchain/agent-workflows.md",
        ),
    },
    {
        "name": "agent-tooling-research",
        "description": "Long-form research and experiments on agent-first SemanticScript tooling.",
        "files": (
            "research/README.md",
            "research/04-competitive-syntax-arena.md",
        ),
    },
    {
        "name": "taskforge-web-patterns",
        "description": "TaskForge Web status and native HTTP application patterns without bundling app source.",
        "files": (
            "docs/reference/roadmap.md",
            "docs/toolchain/native-http-runtime.md",
            "docs/language/native-http-api.md",
        ),
    },
    {
        "name": "sqlite-patterns",
        "description": "SQLite usage, cleanup, and JSON CRUD patterns.",
        "files": (
            "docs/language/json-crud.md",
            "docs/language/records-codecs-boundaries.md",
            "docs/reference/call-targets.md",
        ),
    },
    {
        "name": "http-html-patterns",
        "description": "Native HTTP, route, handler, and HTML boundary patterns.",
        "files": (
            "docs/language/native-http-api.md",
            "docs/toolchain/native-http-runtime.md",
            "docs/language/records-codecs-boundaries.md",
        ),
    },
    {
        "name": "patch-and-repair",
        "description": "Structured diagnostic, repair-plan, and patch-application workflow guidance.",
        "files": (
            "docs/toolchain/compiler.md",
            "docs/toolchain/linter.md",
            "docs/toolchain/agent-workflows.md",
            "research/README.md",
        ),
    },
    {
        "name": "package-dependencies",
        "description": "External dependency resolution: build.sem dependency rows, `sem deps` (sync/verify/list/cache/purge), the GitHub package format, cache, and sem.lock.",
        "files": (
            "docs/reference/package-management.md",
            "docs/language/project-layout-build-sem.md",
        ),
    },
)
DIAGNOSTIC_INDEX_PATHS = (
    "docs/toolchain/compiler.md",
    "docs/toolchain/linter.md",
    "docs/agents.md",
    "docs/reference/security-rules.md",
    "SemanticScript/linter/test_semlint.py",
)
SKILL_ALIASES = {
    "sem-start": "getting-started",
    "sem-getting-started": "getting-started",
    "sem-onboarding": "getting-started",
    "sem": "language-core",
    "sem-syntax": "syntax-reference",
    "sem-grammar": "syntax-reference",
    "sem-verbs": "syntax-reference",
    "sem-agent": "graph-and-slice",
    "sem-language": "language-core",
    "sem-diagnostics": "patch-and-repair",
    "sem-stdlib": "sqlite-patterns",
    "sem-builds": "patch-and-repair",
    "sem-packages": "package-dependencies",
    "sem-deps": "package-dependencies",
    "sem-testing": "graph-and-slice",
}
DIAGNOSTIC_EXPLAINERS = {
    "SS3101": {
        "title": "missing purpose metadata",
        "summary": "Operations should declare a purpose row so agents and reviewers can recover intent without guessing from implementation alone.",
        "whyItMatters": [
            "Long sessions lose context first in business intent, not in syntax.",
            "Purpose rows give repair tools a stable summary of why the operation exists."
        ],
        "commonFixes": [
            "Add a `purpose operation ...` row that states what the operation does in one sentence."
        ],
    },
    "SS3102": {
        "title": "missing invariant metadata",
        "summary": "Operations should declare at least one invariant row describing the safety or business rule that must remain true.",
        "whyItMatters": [
            "Invariants are the facts most likely to drift during multi-file agent edits.",
            "Explicit invariants make semantic regressions easier to catch in review and lint."
        ],
        "commonFixes": [
            "Add an `invariant operation ...` row that states the non-negotiable rule the operation preserves."
        ],
    },
    "SS3104": {
        "title": "missing capability coverage",
        "summary": "An operation declares an effect without an authorizing capability or authority proof.",
        "whyItMatters": [
            "Effects without authority are one of the fastest ways for semantic drift to hide in a codebase.",
            "Agents need explicit proof of who is allowed to perform side effects."
        ],
        "commonFixes": [
            "Add `authority OP ACTION PATH` when the authority is local and obvious.",
            "Declare a reusable capability and attach it with `useCapability` when the same proof recurs."
        ],
    },
    "SS3109": {
        "title": "authority grant matches no declared effect",
        "summary": "An operation has an `authority OP ACCESS PATH` grant whose access verb or path matches none of the operation's declared `effect` rows, so it authorizes nothing — and the effect it was meant to back is left unproven. SS3104 only checks that *some* authority row is present, so a transposed or mistyped grant slips through as 'covered'.",
        "whyItMatters": [
            "A grant that authorizes nothing gives a false sense of coverage: the effect looks proven but isn't.",
            "The most common cause is access/path transposition (`authority OP read X` for a `write X` effect) or a stale path that no longer matches any effect."
        ],
        "commonFixes": [
            "Align the grant to a declared effect: `authority OP <action> <path>` must use the same access verb and a path equal-or-broader than an `effect OP <action> <path>` row.",
            "Remove the grant if the effect it referenced is gone.",
            "Remember the order is access-first: `authority main write console.stdout`, mirroring `effect main write console.stdout`."
        ],
    },
    "SS3110": {
        "title": "column memory used after finalize/close (use-after-free)",
        "summary": "A value read from sqlite.columnText/columnBlob/columnName points into the prepared statement's own memory. Using it after an explicit `run` of finalizeStatement (same statement) or closeDatabase frees that memory first — the program builds and checks cleanly, then SIGSEGVs at runtime when the response writer dereferences the freed pointer.",
        "whyItMatters": [
            "This crash is invisible to both `check` and `build`; it only appears when the program runs and the response writer reads freed memory.",
            "Column pointers are owned by the statement, so their lifetime ends at finalize/close — not at the end of the operation."
        ],
        "commonFixes": [
            "Release with `defer <name> sqlite.finalizeStatement <statement>` so cleanup runs at scope exit, after the response is written.",
            "Or reorder: write the response (consume the column value) BEFORE the finalize/close rows.",
            "Copy the bytes out of the column value before finalize if you must finalize early."
        ],
    },
    "SS4105": {
        "title": "reference integrity: unresolved value or wrong attachment subject kind",
        "summary": "A row references a value that is not declared in the current operation, or an operation-body verb is attached to a subject that is not an operation. Every argument value must be a named `storage`/`bind`/input value, an integer / true / false literal, or a bare enum case constant; string literals and stale dotted enum-like values are rejected.",
        "whyItMatters": [
            "Argument values that are not declared names are the most common source of silent narrative drift during agent edits.",
            "Dotted enum-like values (`HttpStatus.Ok`) and inline strings (`\"application/json\"`) read like other languages but bypass the explicit-dataflow contract, so the linter forces them into supported named declarations."
        ],
        "commonFixes": [
            "Declare the value first, e.g. `storage local immutable contentType String \"application/json\"`, then reference `contentType` in the argument row.",
            "For real enums, use the bare case constant reported by `sem docs get TYPENAME --json`, for example `readWriteCreateSqliteOpenMode`.",
            "For HTTP status roles, declare numeric `HttpStatusCode` constants such as `storage local immutable okStatus HttpStatusCode 200`; there is no `HttpStatus.Ok` value syntax.",
            "When the diagnostic is `attachmentSubjectKindMismatch`, point the verb at an actual operation, or use a subject-flexible verb (`purpose`, `invariant`, `warning`)."
        ],
    },
    "SS3804": {
        "title": "typed collection runtime missing",
        "summary": "A call such as `TaskList.append` or `TaskMap.get` names a typed collection operation, but collection declarations are metadata today and do not allocate storage or implement methods.",
        "whyItMatters": [
            "The linter warning is the early signal; current codegen rejects the call instead of silently returning a zero result.",
            "Using collection metadata as if it were executable hides where storage, bounds checks, mutation, and failure handling must actually live."
        ],
        "commonFixes": [
            "Implement the behavior as an explicit SemanticScript operation and call that operation directly.",
            "Provide a real `runtimeBinding` only when a native collection backend exists.",
            "Keep `listType`, `mapType`, and `collectionOperation` rows as schema/contract metadata until executable collection support is wired."
        ],
    },
    "SS4107": {
        "title": "branch error source is not a fallible call",
        "summary": "`branch error source CALL target LABEL` requires CALL to expose a real error channel. Valid sources include known Result-shaped std/runtime calls and user operations declared `output operation OP Result OK ERROR`. Ordinary value calls use explicit Bool/status checks instead.",
        "whyItMatters": [
            "Branching off a call with no error channel is control-flow drift: the failure label can never be reached correctly, or older toolchains may route it from the wrong value.",
            "Result-shaped calls need both success and error disposition rows so the source states how each leg is handled."
        ],
        "commonFixes": [
            "If the target operation is intended to be fallible, declare `output operation OP Result OkType ErrorType` and use `bind ok`, `bind error`, then `branch error source CALL target LABEL`.",
            "For ordinary status/sentinel calls, bind the returned value and branch with an explicit comparison.",
            "Remove the `branch error source` row when the target truly cannot fail."
        ],
    },
    "SS3113": {
        "title": "column value used after a later same-statement read clobbered it",
        "summary": "A value from sqlite.columnText/columnBlob/columnName points into the prepared statement's own scratch buffer. A later columnText/columnBlob/columnName on the SAME statement overwrites that buffer, so the earlier value is silently corrupted by the time it is used (rendered, bound, written).",
        "whyItMatters": [
            "The corruption is invisible to a casual read — the value looks captured but the bytes are shared and get reused.",
            "Reading several text columns from one row and using them all later is the natural shape that triggers it."
        ],
        "commonFixes": [
            "Use each columnText value immediately (hydrate / copy / bind) BEFORE the next columnText on the same statement.",
            "Read integer columns with sqlite.columnInt64 (returned by value — no borrowed buffer) where possible.",
            "Split the read into one single-column statement per value when several texts must coexist."
        ],
    },
    "SS3114": {
        "title": "heap response body freed before write",
        "summary": "A buffer returned by c.malloc/calloc/realloc or memory.allocateMemoryBytes is passed as an HTTP response body after an explicit c.free or memory.releaseMemoryBytes has already run. The call rows look ordered, but the response writer dereferences freed memory when its `run` row executes.",
        "whyItMatters": [
            "This is the malloc-backed version of the response-body use-after-free: build succeeds, but the native HTTP adapter may SIGSEGV or send corrupted bytes.",
            "Argument rows only wire dataflow; the body is consumed by the response writer's execution row, so freeing between `argument ... body ...` and `run writeCall` is still unsafe."
        ],
        "commonFixes": [
            "Use `defer <name> c.free <buffer>` or `defer <name> memory.releaseMemoryBytes <buffer>` so cleanup runs at operation exit after the response writer.",
            "Or move the response writer's `run` row before the explicit free/release rows.",
            "Prefer standard.memory.allocateMemoryBytes/releaseMemoryBytes for new app code, but keep the same lifetime ordering."
        ],
    },
    "SS3635": {
        "title": "multiple SQLite writes should be atomic",
        "summary": "An operation performs more than one SQLite write (INSERT/UPDATE/DELETE) without wrapping them in a transaction. A failure between writes leaves the database half-updated.",
        "whyItMatters": [
            "Multi-step writes that are not atomic are the classic source of partial/corrupt state after an error.",
            "A task insert plus its activity-event insert must both commit or both roll back."
        ],
        "commonFixes": [
            "Wrap the writes in `BEGIN IMMEDIATE` … `COMMIT` (with a `ROLLBACK` on the failure path) via sqlite.exec.",
            "If the writes flow through a helper the linter can't see across, keep the BEGIN/COMMIT in the same operation as the writes."
        ],
    },
    "SS3639": {
        "title": "connection-global SQLite generated id",
        "summary": "Code uses `last_insert_rowid()` or `sqlite.lastInsertRowId` to recover an id from a prior INSERT. New code should make the INSERT return the id directly with `INSERT ... RETURNING id`, read column 0 from that INSERT statement, and pass the named id into later statements such as activity-log inserts.",
        "whyItMatters": [
            "The last-insert row id is mutable connection state, so triggers, helper writes, shared handles, or future concurrent dispatch can make the read observe the wrong row.",
            "A returned id is normal SemanticScript dataflow: prepare, bind, step to rowSqliteStepResult, read sqlite.columnInt64, drain/finalize, then bind the id explicitly into dependent writes.",
            "When the generated row and activity-log row must stay atomic, the migration belongs inside sqlite.beginImmediateTransaction / commitTransaction with rollback on failure paths."
        ],
        "commonFixes": [
            "Replace `last_insert_rowid()` and `sqlite.lastInsertRowId` with `INSERT INTO ... VALUES (...) RETURNING id`.",
            "Use `sem docs get sqlite.lastInsertRowId --json` and copy `target.usage.migration.sqlRows` plus `target.usage.migration.rows` for the prepare/bind/step/column/finalize/transaction skeleton.",
            "After reading the RETURNING column, step again to doneSqliteStepResult or finalize/reset before COMMIT. For borrowed text/blob columns, consume or copy before the same statement steps/resets/finalizes."
        ],
    },
    "SS3201": {
        "title": "dead store: a bound/stored value is never read",
        "summary": "A `bind` or `storage`/`set` produces a value that no later row reads on any path. Either a use is missing (the value was meant to be consumed) or the row is leftover.",
        "whyItMatters": [
            "A dead store is usually a dropped result — e.g. binding a value you forgot to branch on, or a rename that left the old name unused.",
            "It is also narrative drift: the row claims to matter but nothing depends on it."
        ],
        "commonFixes": [
            "Consume the value (branch on it, pass it as an argument, return it), or remove the row if it is genuinely unused.",
            "For a deliberately ignored call result, use `ignore value source CALL type T` instead of binding a name."
        ],
    },
    "SS3630": {
        "title": "unreachable row after terminal control flow",
        "summary": "A row sits after a `return`/`jump` (or an exhaustive branch) with no label that could route control back to it, so it can never execute.",
        "whyItMatters": [
            "Unreachable rows are dead narrative — a reader trusts them but they never run.",
            "They usually mean a missing label, a misplaced row, or a branch that should have fallen through."
        ],
        "commonFixes": [
            "Add the `label` that should precede the row, or move the row above the terminal transfer.",
            "Delete the row if it is genuinely dead."
        ],
    },
    "SS3106": {
        "title": "hidden failure: a fallible call's error channel is not handled",
        "summary": "A call that can fail has its error left unbound/unbranched, so a failure is silently dropped and execution continues as if it succeeded.",
        "whyItMatters": [
            "Silently dropping a failure is the fastest way to ship a program that 'succeeds' while its side effect never happened.",
            "Every fallible call needs an explicit disposition for both legs."
        ],
        "commonFixes": [
            "Add `bind error <name>Error <ErrorType> <call>` then `branch error source <call> target <failureLabel>`.",
            "If the call genuinely cannot fail in this context, use the value-only contract and document why."
        ],
    },
    "SS3624": {
        "title": "legacy JsonBuilder call",
        "summary": "A source row calls the legacy manual JsonBuilder API. New JSON output should use typed `json.stringify.<TypeName>` for scalar/record values, or the JsonDocument mutator API when the code needs to build or edit a document.",
        "whyItMatters": [
            "The builder surface hides state-machine and capacity failures behind status codes and borrowed output buffers.",
            "Typed stringify and JsonDocument mutators give the linter explicit failure, cleanup, and cursor-lifetime rows to verify."
        ],
        "commonFixes": [
            "For a known value type, replace the builder sequence with `json.stringify.<TypeName>`, then `bind ok`, `bind error`, and `branch error`.",
            "For incremental object/array construction, use `json.createEmptyDocument`, mutate with `json.setObjectField*` or `json.appendArrayElement*`, serialize with `json.serializeDocument`, and destroy with `json.destroyDocument` on every ownership path.",
            "Run `sem docs get json.stringify.String --json`, `sem docs get json.createEmptyDocument --json`, or `sem docs get json.serializeDocument --json` for row-level call, failure, and cleanup shapes."
        ],
    },
    "SS3625": {
        "title": "legacy JSON finder call",
        "summary": "A source row calls the legacy flat-object finder API (`json.findString`, `json.findInt64`, `json.findDouble`, `json.findBool`, or `json.hasField`). New JSON reads should parse once into JsonDocument, navigate with cursors, and read through typed cursor accessors.",
        "whyItMatters": [
            "The finder calls collapse absent fields, wrong types, malformed JSON, and scratch-buffer failures into sentinel values.",
            "JsonDocument cursor calls expose traversal and type failures as `JsonAccessError`, so source rows can branch explicitly."
        ],
        "commonFixes": [
            "Use `json.createDocument` with failure handling, bind the ok `JsonDocument`, and clean it up with `json.destroyDocument`.",
            "Navigate with `json.documentRoot` plus `json.objectFieldAt` or with `json.cursorAtPath`, then handle `JsonAccessError` before reading the cursor.",
            "Read with `json.cursorString`, `json.cursorInt64`, `json.cursorDouble`, or `json.cursorBool` as appropriate; use `sem docs get json.cursorAtPath --json` and `sem docs get json.cursorString --json` for exact rows."
        ],
    },
    "SS4001": {
        "title": "vague call name (missing `Call` role suffix)",
        "summary": "A `call <name> <target>` binding should end in the `Call` role suffix so call rows are visually distinct from values and labels (spec §6 naming roles).",
        "whyItMatters": [
            "Role suffixes let a reader (and repair tools) tell at a glance whether a name is a call, a value, an error, or a label.",
            "Consistent suffixes keep multi-file agent edits coherent."
        ],
        "commonFixes": [
            "Rename the call binding to end in `Call` (e.g. `open` -> `openCall`) and update its `run`/`argument`/`bind` references.",
            "(A `sem fix --apply-conventions` codemod for these mechanical renames is a planned follow-up.)"
        ],
    },
    "SS4002": {
        "title": "vague error name (missing `Error` role suffix)",
        "summary": "A `bind error <name> …` binding should end in the `Error` role suffix so error values are distinguishable from ok values at the call site.",
        "whyItMatters": [
            "The error suffix signals the failure channel explicitly, which the failure-flow rules and reviewers rely on.",
        ],
        "commonFixes": [
            "Rename the error binding to end in `Error` (e.g. `openErr` -> `openError`)."
        ],
    },
    "SS4003": {
        "title": "vague failure name (missing `Failure` role suffix)",
        "summary": "A `makeError <name> …` output should end in the `Failure` role suffix so constructed error values read as failures.",
        "whyItMatters": [
            "The `Failure` suffix marks a value that represents an error cause, distinct from the `Error` binding that captured one.",
        ],
        "commonFixes": [
            "Rename the makeError output to end in `Failure` (e.g. `notFound` -> `notFoundFailure`)."
        ],
    },
    "SS0106": {
        "title": "unused bind slot",
        "summary": "A `bind value`/`bind ok`/`bind error` introduces a name that no later row uses. The slot is declared but never consumed.",
        "whyItMatters": [
            "An unused bind is usually a forgotten branch or a leftover from an edit.",
            "For error binds specifically, an unused error often means the failure is being dropped."
        ],
        "commonFixes": [
            "Use the bound name (branch on it, pass it, return it), or drop the bind.",
            "To discard a call result deliberately, use `ignore value source CALL type T` instead of binding it."
        ],
    },
    "deferNotDominated": {
        "title": "cleanup defer does not dominate the exit it protects",
        "summary": "A resource is acquired, an all-paths `defer close...` is registered, and a later failure branches to a reject/fail label, but that same label is also reached from a failure edge before the resource was acquired. Current lowering inserts a path-local edge cleanup block for this forward exit-label shape, while the diagnostic still points out the ambiguous lifetime.",
        "whyItMatters": [
            "A shared exit label reached from both pre-acquisition and post-acquisition paths makes the resource lifetime hard to read and hard for older tooling to lower correctly.",
            "The compiler now emits edge cleanup for lowered defers in this shape, but split labels still make the ownership boundary explicit for reviewers and tools."
        ],
        "commonFixes": [
            "Give each pre-acquisition failure its OWN exit label (e.g. `openFailed`) so the shared post-acquisition reject label is dominated by the defer.",
            "Scope the cleanup to the paths where the resource is live with `deferRunOn <name> <label>`.",
            "Acquire the resource before any branch that can also target the shared cleanup label, so every path to that label has registered the defer."
        ],
    },
    "roleSuffixMismatch": {
        "title": "branch-error label should name a failure or recovery role",
        "summary": "A label targeted by `branch error` / `branchIfError` is where a failure lands, so its name should read as a recognized control role: a past-tense / `Failed` outcome (`openFailed`, `parseFailed`) OR a recovery/response role (`loginReject`, `importRollback`, `registerRedirect`, `retry`, `cleanup`). A vague target (`fooHandler`, `nextThing`) hides what the failure edge does.",
        "whyItMatters": [
            "Error-edge targets are read most during review and repair; a role-named label makes the control-flow graph self-documenting (spec §12).",
            "Recovery/response labels are legitimate failure targets — the rule accepts them, so you do not need to force a `*Failed` suffix onto a label that rejects a request or rolls back a transaction."
        ],
        "commonFixes": [
            "Name the label for its outcome (`…Failed`, or a past-tense `-ed` form) or its recovery role (reject, rollback, redirect, retry, fallback, cleanup, abort, cancel, unauthorized, notFound, timeout, recover, respond, done, exit).",
            "If the label genuinely just returns an error, a `*Failed` name is clearest; if it recovers (redirect/rollback), name it for that role."
        ],
    },
    "SS3617": {
        "title": "web server lifecycle hook contract mismatch",
        "summary": "`webServerStartup SERVER HANDLER` and `webServerShutdown SERVER HANDLER` handlers must name an existing operation, declare no inputs, and return bare `Int32`.",
        "whyItMatters": [
            "Lifecycle hooks run outside a request context, so there is no HttpRequest or HttpResponse ABI to pass.",
            "The native HTTP entrypoint calls the hook directly and uses the Int32 status to abort startup or override shutdown status."
        ],
        "commonFixes": [
            "Define the named hook operation if it is missing.",
            "Remove all `input operation HOOK ...` rows from startup and shutdown hook operations.",
            "Declare `output operation HOOK Int32` and return zero for success or a nonzero status for failure."
        ],
    },
    "SS3618": {
        "title": "route timeout is metadata-only",
        "summary": "`routeTimeout SERVER PATH BUDGET` records coverage intent, but the current native HTTP blocking runtime does not preempt a synchronous handler when that budget expires.",
        "whyItMatters": [
            "The row is still useful as coverage metadata for tools and future preemptive runtimes.",
            "A source file that only declares `routeTimeout` can otherwise look runtime-protected when no in-process timeout is enforced today."
        ],
        "commonFixes": [
            "Keep the row when you want coverage metadata, but do not rely on it for runtime preemption.",
            "Use handler-level checks or an external server/proxy timeout for actual synchronous-handler bounds.",
            "If the route intentionally has no timeout coverage, use `routeTimeoutOptOut SERVER PATH \"rationale\"` instead."
        ],
    },
    "SS3619": {
        "title": "response header runs after body writer",
        "summary": "`http.responseHeader` must run before the first response body/file/redirect writer. Once a body writer runs, the native response has latched its staged headers.",
        "whyItMatters": [
            "Set-Cookie, Location, Cache-Control, and custom headers written after the body writer can look source-valid while having no useful runtime effect.",
            "The linter tracks `run` order rather than declaration order, so hoisted call declarations are still legal when the header execution precedes the body execution."
        ],
        "commonFixes": [
            "Move the `http.responseHeader` run and its arguments before `http.responseText`, `http.responseHtml`, `http.responseBytes`, `http.responseSseEvent`, `http.responseFile`, or `http.redirect`.",
            "For redirects, prefer the single `http.redirect` target when it fits instead of manually pairing `Location` and an empty body."
        ],
    },
    "SSCG001": {
        "title": "codegen lowering failed after check passed",
        "summary": "A `codegen.lower` failure: the program parsed and may have passed `sem check`, but a requirement enforced only at native lowering was unmet (for example a `webServer` target missing its `serverHost`/`serverPort` rows, or a `submitWork`/dispatch target that is not a real user operation). `sem check` does not run the full lowering preflight, so `buildable: true` does not guarantee codegen succeeds.",
        "whyItMatters": [
            "This is the 'check is not build' gap: a green `check` can still fail at `build`. Treat `sem build` (plus a runtime smoke) as the authoritative compile gate.",
            "The message names the primary source row and operation; the missing requirement is almost always an operation-local declaration."
        ],
        "commonFixes": [
            "Read the primary source row in the message and add the declaration codegen needs (e.g. add `serverHost`/`serverPort` rows for a `webServer` target).",
            "Ensure dispatch/call targets (`submitWork`, etc.) name a real user `operation`, not a value or builtin.",
            "Run `sem build PATH` rather than relying on `sem check`; check is advisory and does not lower."
        ],
    },
    "SS3627": {
        "title": "invalid sql body island",
        "summary": "`sql body NAME` islands are indentation-sensitive and brace-sensitive. A literal `{` or `}` inside the island is parsed as a dynamic interpolation hole and rejected; dynamic values must use `?` placeholders plus `sqlite.bind*` rows, never string interpolation. The island must be indented under a `sql body NAME` line whose NAME matches a `storage ... SqlText` declaration.",
        "whyItMatters": [
            "Brace interpolation into SQL is exactly how injection bugs get in; the parser bans it so untrusted values can only enter through bound `?` parameters.",
            "A stray `{}` in DDL (e.g. `DEFAULT '{}'` for a JSON column) is the usual trigger and is a pure parse error, not a runtime issue."
        ],
        "commonFixes": [
            "Replace brace defaults in DDL with a brace-free literal (e.g. `DEFAULT ''`).",
            "For dynamic values, use a `?` placeholder in the SQL and a `sqlite.bindText`/`bindInt64` row — never an interpolated value.",
            "Declare `storage module immutable NAME SqlText` and put the statement, indented, under `sql body NAME`."
        ],
    },
    "SS2506": {
        "title": "unresolved or out-of-scope symbol reference",
        "summary": "A row references a symbol that is not in the current operation or module scope under the active SemanticScript rules.",
        "whyItMatters": [
            "Cross-module state and helper access are where agent edits most often drift into relying on implicit context.",
            "If the compiler/build path accepts the source but the semantic contract rejects it, the workflow needs an explicit model for that boundary."
        ],
        "commonFixes": [
            "Import or qualify the provider surface explicitly instead of relying on ambient module state.",
            "Thread the value through operation inputs/outputs when the reference is really cross-context data.",
            "If the project intentionally relies on a broader scope model, align the linter and build rules before trusting the check gate."
        ],
    },
    "SS0104": {
        "title": "unused errorCase",
        "summary": "An error case was declared but never constructed on any observed failure path.",
        "whyItMatters": [
            "Dead error variants often mean an incomplete failure path rather than harmless clutter.",
            "Agents should confirm whether the missing raise is the real bug before removing the declaration."
        ],
        "commonFixes": [
            "Wire the error case into the intended failure path.",
            "Remove the dead variant only if the domain truly no longer uses it."
        ],
    },
    "SS0106": {
        "title": "bind value bound but never read",
        "summary": "A `bind value`/`bind ok`/`bind error` slot was declared but never referenced on a later row. The bind names a result that nothing consumes — usually a dropped data-flow edge (a result you meant to thread onward) rather than harmless clutter. This is one of the highest-frequency advisories in real projects.",
        "whyItMatters": [
            "An unread bound value is often an omitted step: the result you meant to pass into the next call, comparison, or return was silently dropped.",
            "Because it fires often, triaging it quickly (use it, ignore it, or delete it) keeps `check` output signal-rich instead of noisy."
        ],
        "commonFixes": [
            "Reference the bound name on a later row — pass it as an `argument`, compare it, or return it.",
            "If the call is only for its side effect, use the matching `ignore` row (`ignore value`/`ignore ok`/`ignore void source`) instead of binding a value you won't read.",
            "Delete the bind only when the value is genuinely unused."
        ],
    },
    "SSRUN001": {
        "title": "runtime panic",
        "summary": "The program trapped with SemanticScript runtime panic context enabled.",
        "whyItMatters": [
            "This means execution reached a runtime safety boundary that static checks did not eliminate.",
            "The panic block should identify the source row, operation, and call involved."
        ],
        "commonFixes": [
            "Re-run under dev panic mode and inspect the referenced operation, call, and source row.",
            "Use `sem inspect-ir` or trace output when the failure depends on runtime lowering."
        ],
    },
    "SSRUN002": {
        "title": "native fault",
        "summary": "A fatal signal (or Windows structured exception) reached the process; the runtime caught it to report the last semantic site before terminating.",
        "whyItMatters": [
            "Unlike SSRUN001, the fault already happened: no guarded check could trap it ahead of time, so the report names the last operation/call the program entered rather than the exact offending row.",
            "The named site is the place to start: a wild or null pointer, exhausted stack, or illegal instruction is usually on or just after that call."
        ],
        "commonFixes": [
            "Open the operation and call named in `Last site` and check the pointer, length, or recursion bound used there.",
            "Re-run with `sem run --explain-crash` under dev panic mode for the site; rebuild with `--build-profile dev` if the report has no Last site (prod hides it).",
            "Note: on Windows an explicit abort()/__fastfail bypasses the handler, so a missing SSRUN002 with exit 0xC0000409 still means a deliberate abort."
        ],
    },
    "SEMSC_PARSE": {
        "title": "compiler parse failure",
        "summary": "The reference compiler could not parse the requested SemanticScript surface.",
        "whyItMatters": [
            "Agents should not keep editing blindly when the parser has already lost the source structure.",
            "Parse failures usually mean the next safe move is to restore a valid row shape before broader repairs."
        ],
        "commonFixes": [
            "Inspect the cited source line and restore a valid current-row form from docs/reference/syntax-inventory.md or `sem skills get sem --json`.",
            "Run `sem check --json` again after fixing the malformed row so higher-level diagnostics are trustworthy."
        ],
    },
    # ---- Parser / grammar family (SS000x) ----
    "SS0001": {
        "title": "unknown verb (unrecognized row)",
        "summary": "The first token of a row is not a known SemanticScript verb. Every row begins with a verb; indented foreign content (HTML/JSON/SQL islands) only opens after the matching body row.",
        "whyItMatters": [
            "A stray verb usually means a typo, a row that belongs inside an island that was not opened, or pre-cutover syntax the compiler no longer accepts.",
            "Markup lines (e.g. `<p>...`) are only valid inside an `html body template NAME` island; outside one they are read as verbs."
        ],
        "commonFixes": [
            "Check the verb spelling against the syntax inventory or `sem skills get language-core --json`.",
            "If the line is HTML/JSON/SQL, make sure the island was opened first (`html body template NAME`, `jsonBody NAME`, `sqlBody NAME`).",
            "If this is old syntax, run `sem migrate-syntax --diff <file>` then `--write`."
        ],
    },
    "SS0002": {
        "title": "row has too few arguments (arity)",
        "summary": "A row does not carry the number of tokens its verb requires. Frequently the subject-qualified cutover forms: `input operation OP NAME TYPE`, `output operation OP TYPE`.",
        "whyItMatters": [
            "Header rows must be independently checkable, so they name their owning operation and subject kind explicitly.",
            "Copying pre-cutover examples (`input HANDLER NAME TYPE`) is the most common cause."
        ],
        "commonFixes": [
            "Add the missing token(s) to match the row's required shape.",
            "For input/output/purpose/invariant rows, run `sem migrate-syntax --write <file>` to insert the `operation` subject qualifier automatically."
        ],
    },
    "SS0003": {
        "title": "syntax cutover: row uses a rejected pre-cutover form",
        "summary": "The linter no longer accepts the old unqualified/legacy row form. Subject-qualified header rows (`input operation ...`, `output operation ...`, `purpose operation ...`, `invariant operation ...`) and a handful of other forms replaced the originals.",
        "whyItMatters": [
            "Skill/doc examples may still show the pre-cutover shape; the compiler enforces the new one, so copy-paste fails here.",
            "The rewrite is 100% mechanical, which is why a dedicated converter exists."
        ],
        "commonFixes": [
            "Run `sem migrate-syntax --diff <file>` to preview, then `sem migrate-syntax --write <file>` to upgrade every cutover row at once.",
            "Or rewrite the single row to the shape shown in the diagnostic's fix candidate."
        ],
    },
    "SS0109": {
        "title": "html template declared but never hydrated",
        "summary": "An `html template NAME` (with its body) is declared but no `html.hydrate.NAME` call ever renders it. Like an unused call or label, the template markup is dead — usually a leftover or a typo'd hydrate target.",
        "whyItMatters": [
            "Dead template markup ships in source but never reaches a response, hiding intent.",
            "A typo in the hydrate target (`html.hydrate.Naem`) silently leaves the real template unrendered; this surfaces that."
        ],
        "commonFixes": [
            "Render it with `call <name>Call html.hydrate.<Template>` where the page is built.",
            "Delete the `html template`/`html body template` rows if the template is a leftover.",
        ],
    },
    "SS3640": {
        "title": "operation under-declares an external effect it performs",
        "summary": "An operation directly calls a builtin with a known external effect (writing console.stdout, writing the HTTP response) but declares no matching `effect` row. Advisory: declared effects are the machine-readable record of what an operation touches, and a missing one means a later edit can drop the call or the effect with nothing catching the drift.",
        "whyItMatters": [
            "The language's premise is that effects are explicit and checkable; an undeclared write to an observable resource breaks that contract.",
            "Effect rows are what authority/capability coverage and review hang off — an inferred-but-undeclared effect is invisible to those checks."
        ],
        "commonFixes": [
            "Add the effect row the fix candidate shows (e.g. `effect <op> write console.stdout`) and back it with a matching capability/authority.",
        ],
    },
    "SS2516": {
        "title": "placeholder modulePath from sem new",
        "summary": "The build tape still declares `modulePath PROJECT github.com/example/<name>`, the scaffold placeholder. Left unchanged it can resolve imports and dependency origins against a bogus path. Advisory (non-blocking).",
        "whyItMatters": [
            "Dependency resolution and import provenance key off modulePath; a placeholder origin can resolve oddly once you add dependencies or publish.",
            "It is a one-line fix that is easy to forget after `sem new`."
        ],
        "commonFixes": [
            "Set the project's real module path, e.g. `modulePath <project> github.com/<owner>/<repo>`.",
        ],
    },
    "SS3611": {
        "title": "duplicate route (same server, METHOD, and path)",
        "summary": "Two `route` rows register the same METHOD+path on one server. The native dispatcher matches the first, so every later duplicate is dead — its handler can never run.",
        "whyItMatters": [
            "A duplicate route is almost always a copy-paste bug; the second handler silently never executes.",
            "Dead route bindings hide intent and drift from the actual served surface."
        ],
        "commonFixes": [
            "Delete the duplicate route row, or give it a distinct method/path.",
        ],
    },
    "SS4302": {
        "title": "bind type contradicts the call's return-type domain",
        "summary": "A `bind` declares an opaque domain handle (HtmlFragment/HtmlDocument/JsonDocument/...) for a call that returns a String or scalar, or vice versa. Both lower to a pointer, so the type lie type-checks — but consuming the mislabeled value (e.g. hydrating it) dereferences garbage and crashes at runtime.",
        "whyItMatters": [
            "This is the exact shape behind the `string.concat` result bound as `HtmlFragment` SIGSEGV: a String op's result is not an HTML handle, but the shared i8* ABI hides it until runtime.",
            "Opaque domain handles are produced only by their domain's constructors (html.hydrate.*, the JSON builder, user ops that return them) — never by String/scalar calls."
        ],
        "commonFixes": [
            "Bind the call's real return type (the fix candidate shows it).",
            "To assemble an HTML fragment from pieces, use the HTML fragment/template path (html.hydrate with HtmlFragment holes), not a string concatenation."
        ],
    },
    # ---- Codegen / backend family (SSCG* lowering, SSBE* native backend) ----
    "SSCG002": {
        "title": "call could not be lowered to LLVM IR",
        "summary": "The compiler failed while lowering a specific call row to LLVM IR. The raw lowering error is in the message; the call's target, arg rows, or a referenced value is the place to look.",
        "whyItMatters": [
            "A call that parses and lints can still fail in codegen when an arg type, count, or target binding is wrong.",
            "This is a lowering-phase failure, so the fix is in SemanticScript source or a compiler lowering rule, never in the generated IR."
        ],
        "commonFixes": [
            "Inspect every `argument` row attached to the named call and confirm names/types match the target's inputs.",
            "Confirm the call target exists and supports the argument types you passed.",
        ],
    },
    "SSCG004": {
        "title": "constant declared with an unlowerable type",
        "summary": "A constant value (storage/argument) was declared with a type the backend cannot lower to an LLVM constant — typically an enum or domain type used directly as a raw const.",
        "whyItMatters": [
            "Records and domain types with no LLVM lowering are not usable as raw constants in codegen; only concrete primitives and enums (via their repr width) lower to LLVM constants.",
            "This surfaces at build time, so confirm a const's type is a lowerable primitive before relying on a green `check`."
        ],
        "commonFixes": [
            "Declare the const with a concrete primitive type, e.g. `storage local immutable okStatus Int32 200`.",
            "If you need an enum member semantically, declare it with the enum type (enums lower via their repr width) or compare against it at runtime rather than storing a record/domain value as a const.",
        ],
    },
    "SSCG005": {
        "title": "html.hydrate is missing a value for a template hole",
        "summary": "An `html.hydrate` call did not provide an argument for one of its template's named holes.",
        "whyItMatters": [
            "Every named hole in an htmlTemplate must be hydrated, or the rendered output is structurally incomplete.",
            "A single-identifier `{ name }` in raw markup/JS can be misread as a hole; keep literal braces inside a raw/script region."
        ],
        "commonFixes": [
            "Add an `argument <hydrateCall> <holeName> <Type> <valueName>` row for each missing hole.",
            "Confirm the hole name in the template matches the argument name exactly.",
        ],
    },
    "SSBE002": {
        "title": "output binary could not be written (locked or read-only)",
        "summary": "The native linker compiled the IR successfully but could not write the output executable. The usual cause on Windows is rebuilding while the previous binary is still running and holds a file lock.",
        "whyItMatters": [
            "This is a link-time write failure, not an IR/source error, so editing SemanticScript source will not help.",
            "It was previously reported under the generic SSBE999 (\"IR failed to compile\"), which sent agents toward the wrong diagnosis."
        ],
        "commonFixes": [
            "Stop the running process that holds the output binary, then rebuild.",
            "Run the program from a copy, or build to a different output path.",
            "Confirm the output directory is writable and not locked by another tool.",
        ],
    },
    # ---- Security rule family (SS43xx arithmetic-UB + SS46xx security) ----
    # Discoverable here so `sem explain <code>` works for every security rule.
    # The full rule x layer x CWE matrix lives in docs/reference/security-rules.md.
    "SS4308": {
        "title": "divide / modulo by a constant zero (CWE-369)",
        "summary": "math.divideInt64/moduloInt64 whose divisor is a provable constant 0. LLVM sdiv/srem by 0 is undefined behavior, so this is blocked on EVERY build (always-on security floor), not just under --strict.",
        "whyItMatters": [
            "A constant-zero divisor is never an intended program; it is pure UB with no legitimate use in any context.",
            "Catching it at compile time is strictly safer than relying on a runtime trap (which is disabled under --runtime-checks off)."
        ],
        "commonFixes": [
            "Change the divisor to a non-zero value, or guard the divide so it is unreachable when the divisor is zero.",
        ],
    },
    "SS4309": {
        "title": "shift count outside [0, 63] (CWE-682)",
        "summary": "A shift (math.shiftLeftInt64/shiftRight*) whose count is a provable constant outside [0, 63]. An out-of-range shift count is LLVM poison, not a wrap. Blocked on every build (always-on floor).",
        "whyItMatters": [
            "A constant out-of-range shift count is undefined at the LLVM level and never intended.",
        ],
        "commonFixes": [
            "Keep the shift count in [0, 63]; mask the count with `math.bitwiseAndInt64` against 63 first.",
        ],
    },
    "SS4601": {
        "title": "non-cryptographic pseudo-random source (CWE-338)",
        "summary": "A call to the libc PRNG family (c.rand/c.srand/c.random/...). These are deterministic generators, predictable, and must never back tokens, keys, nonces, salts, or session ids. Strict-blocked; advisory on default builds.",
        "whyItMatters": [
            "Predictable randomness in a security-sensitive value is a direct CWE-338 vulnerability.",
            "libc rand/srand are acceptable only for non-security sampling/simulation."
        ],
        "commonFixes": [
            "Use `bcrypt.randomBytes` (the platform CSPRNG in standard.bcrypt) for any security-sensitive value.",
        ],
    },
    "SS4602": {
        "title": "weak or missing bcrypt work factor (CWE-916)",
        "summary": "bcrypt.hashPassword with a missing cost argument or a provable constant cost below the security floor (10). A weak work factor is brute-forceable. Blocked on every non-test build (always-on floor); *.test.sem is exempt for fast test hashing.",
        "whyItMatters": [
            "A sub-floor or unspecified bcrypt cost has no legitimate production use.",
        ],
        "commonFixes": [
            "Pass `cost Int32 bcryptRecommendedCost` (12), or a higher application-policy constant.",
        ],
    },
    "SS4603": {
        "title": "non-constant shell command - OS command injection (CWE-78)",
        "summary": "c.system whose command is not a compile-time-constant string. Untrusted/runtime data in a shell command is command injection; there is no safe shell-parameterization in this toolchain. Strict-blocked; advisory on default builds.",
        "whyItMatters": [
            "A shell command built from input/runtime data is a classic CWE-78 vector with no parameterized form.",
        ],
        "commonFixes": [
            "Declare the command as a `storage module immutable <name> String \"...\"` and pass that, or avoid c.system.",
        ],
    },
    "SS4604": {
        "title": "hard-coded credential (CWE-798)",
        "summary": "A non-empty compile-time value bound to a secret-trust-typed (`typeTrust ... secret`) storage slot. A secret embedded in source is a hard-coded credential. Strict-blocked; advisory on default builds.",
        "whyItMatters": [
            "Secrets in source leak through version control, images, and logs, and cannot be rotated without a rebuild.",
        ],
        "commonFixes": [
            "Declare an empty `\"\"` sentinel and fill it at runtime from `c.getenv` / secure config.",
        ],
    },
    "SS3310": {
        "title": "non-constant format string - format-string injection (CWE-134)",
        "summary": "A c.snprintf/printf-family `format` argument that is not an immutable String constant. A runtime format string allows %n/%s injection. Reported by semlint, strict-blocked, and advisory on default builds.",
        "whyItMatters": [
            "An attacker-influenced format string can read or corrupt memory via %n/%s.",
        ],
        "commonFixes": [
            "Use a `storage * immutable String` or `const` String format and pass values as arguments, never as the format itself.",
        ],
    },
    "SS3911": {
        "title": "non-constant SQL text - SQL injection (CWE-89)",
        "summary": "A sqlite.prepareStatement/exec `sql` argument that is not a module-scope immutable SqlText constant. Building SQL from runtime data is SQL injection. Strict-blocked; advisory on default builds.",
        "whyItMatters": [
            "Concatenating untrusted data into SQL is the canonical injection vector.",
        ],
        "commonFixes": [
            "Use a module-scope immutable `SqlText` constant and bind dynamic values with sqlite.bind*, not string concatenation.",
        ],
    },
}


def _source_fingerprint(source: Path) -> str:
    try:
        return hashlib.sha256(source.read_bytes()).hexdigest()
    except OSError:
        return ""


def _file_sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def _file_sha256_with_error(path: Path) -> tuple[str, str]:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest(), ""
    except OSError as exc:
        return "", str(exc)


def _safe_stem(path: Path) -> str:
    stem = path.stem or "source"
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in stem)
    return safe or "source"


def _artifact_run_dir(source: Path, kind: str) -> Path:
    fingerprint = _source_fingerprint(source)[:12] or "nofingerprint"
    timestamp_ns = time.time_ns()
    root = source.resolve().parent / ".semcache" / "observability"
    run_dir = root / f"{kind}-{_safe_stem(source)}-{fingerprint}-{timestamp_ns}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def _write_json_artifact(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8", newline="\n")


def _read_agent_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schemaVersion") == "sem.artifactIndex.v0":
        profile_path = payload.get("artifacts", {}).get("profilePath")
        if profile_path:
            return _read_agent_json(Path(profile_path))
    return payload


def _nested_get(payload: dict, dotted: str, default=0):
    current = payload
    for part in dotted.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current


def _counter_delta(baseline: dict, candidate: dict) -> dict:
    keys = sorted(set(baseline) | set(candidate))
    return {
        key: {
            "baseline": baseline.get(key, 0),
            "candidate": candidate.get(key, 0),
            "delta": candidate.get(key, 0) - baseline.get(key, 0),
        }
        for key in keys
    }


def _profile_delta_payload(baseline_path: Path, candidate_path: Path) -> dict:
    baseline = _read_agent_json(baseline_path)
    candidate = _read_agent_json(candidate_path)
    return {
        "schemaVersion": "sem.profileDelta.v0",
        "tool": {"name": "sem", "version": VERSION},
        "inputs": {
            "baselinePath": str(baseline_path.resolve()),
            "candidatePath": str(candidate_path.resolve()),
            "baselineSchema": baseline.get("schemaVersion", ""),
            "candidateSchema": candidate.get("schemaVersion", ""),
        },
        "source": {
            "baselineFingerprint": _nested_get(baseline, "source.fingerprint", ""),
            "candidateFingerprint": _nested_get(candidate, "source.fingerprint", ""),
            "sameSource": (
                _nested_get(baseline, "source.fingerprint", "")
                == _nested_get(candidate, "source.fingerprint", "")
            ),
        },
        "build": {
            "baselineFingerprint": _nested_get(baseline, "build.fingerprint", ""),
            "candidateFingerprint": _nested_get(candidate, "build.fingerprint", ""),
            "sameBuild": (
                _nested_get(baseline, "build.fingerprint", "")
                == _nested_get(candidate, "build.fingerprint", "")
            ),
        },
        "run": {
            "durationNs": {
                "baseline": _nested_get(baseline, "run.durationNs", 0),
                "candidate": _nested_get(candidate, "run.durationNs", 0),
                "delta": (
                    _nested_get(candidate, "run.durationNs", 0)
                    - _nested_get(baseline, "run.durationNs", 0)
                ),
            },
            "traceEventCount": {
                "baseline": _nested_get(baseline, "run.traceEventCount", 0),
                "candidate": _nested_get(candidate, "run.traceEventCount", 0),
                "delta": (
                    _nested_get(candidate, "run.traceEventCount", 0)
                    - _nested_get(baseline, "run.traceEventCount", 0)
                ),
            },
        },
        "hot": {
            "operations": _counter_delta(
                _nested_get(baseline, "hot.operations", {}),
                _nested_get(candidate, "hot.operations", {})),
            "calls": _counter_delta(
                _nested_get(baseline, "hot.calls", {}),
                _nested_get(candidate, "hot.calls", {})),
            "branches": _counter_delta(
                _nested_get(baseline, "hot.branches", {}),
                _nested_get(candidate, "hot.branches", {})),
            "runtimeExternalCalls": _counter_delta(
                _nested_get(baseline, "hot.runtimeExternalCalls", {}),
                _nested_get(candidate, "hot.runtimeExternalCalls", {})),
        },
    }


def _starter_project_words(path: Path) -> list[str]:
    words = re.findall(r"[A-Za-z0-9]+", path.name)
    return words or ["starter", "project"]


def _starter_github_repo_details(repo_url: str) -> dict | None:
    text = (repo_url or "").strip()
    if not text:
        return None
    match = re.match(
        r"^https://github\.com/(?P<owner>[^/\s]+)/(?P<repo>[^/\s]+?)(?:\.git)?/?$",
        text,
        re.IGNORECASE,
    )
    if match is None:
        match = re.match(
            r"^git@github\.com:(?P<owner>[^/\s]+)/(?P<repo>[^/\s]+?)(?:\.git)?$",
            text,
            re.IGNORECASE,
        )
    if match is None:
        return None
    owner = match.group("owner")
    repo = match.group("repo")
    return {
        "githubRepoUrl": f"https://github.com/{owner}/{repo}",
        "githubRepoSlug": f"{owner}/{repo}",
        "modulePath": f"github.com/{owner}/{repo}",
    }


def _prompt_for_starter_github_url() -> str | None:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return None
    try:
        value = input("GitHub repo URL for this project (optional; press Enter to skip): ").strip()
    except EOFError:
        return None
    return value or None


def _prompt_for_starter_docs_index_opt_in() -> bool:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return False
    try:
        value = input(
            "Enable semantic docs index setup for this project? "
            "This can download the BAAI/bge-small-en-v1.5 embedding model later. [y/N]: "
        ).strip().lower()
    except EOFError:
        return False
    return value in {"y", "yes"}


def _starter_project_metadata(path: Path, github_repo: dict | None = None, template: str = "console") -> dict:
    words = _starter_project_words(path)
    slug = "-".join(word.lower() for word in words)
    project_name = "".join(word[:1].upper() + word[1:] for word in words)
    build_project = words[0].lower() + "".join(word[:1].upper() + word[1:] for word in words[1:])
    module_segment = "_".join(word.lower() for word in words)
    if slug[0].isdigit():
        slug = f"project-{slug}"
    if project_name[0].isdigit():
        project_name = f"Project{project_name}"
    if build_project[0].isdigit():
        build_project = f"project{build_project}"
    if module_segment[0].isdigit():
        module_segment = f"project_{module_segment}"
    return {
        "buildProject": build_project,
        "projectName": project_name,
        "projectTestName": f"{project_name}SmokeTest",
        "moduleName": f"app.{module_segment}",
        "moduleSegment": module_segment,
        "moduleAlias": build_project,
        "modulePath": (github_repo or {}).get("modulePath", f"github.com/example/{slug}"),
        "nativeOutput": f"{slug}.exe",
        "projectVersion": STARTER_PROJECT_VERSION,
        "testFileName": "main.test.sem",
        "githubRepoUrl": (github_repo or {}).get("githubRepoUrl", ""),
        "githubRepoSlug": (github_repo or {}).get("githubRepoSlug", ""),
        "template": template,
    }


def _starter_build_sem_text(meta: dict) -> str:
    if meta.get("template") == "web":
        return "\n".join([
            f"buildProject {meta['buildProject']}",
            f"project {meta['projectName']}",
            f"modulePath {meta['buildProject']} {meta['modulePath']}",
            f"languageVersion {meta['buildProject']} \"1.0\"",
            f"projectVersion {meta['buildProject']} \"{meta['projectVersion']}\"",
            f"projectLicense {meta['buildProject']} MIT",
            f"sourceRoot {meta['buildProject']} \".\"",
            f"registerModule {meta['buildProject']} {meta['moduleName']} \".\"",
            f"mainFile {meta['buildProject']} \"main.sem\"",
            f"testRoot {meta['buildProject']} \".\"",
            f"testPattern {meta['buildProject']} \"*.test.sem\"",
            "target webServer",
            "runtime native 1",
            f"targetRuntime {meta['buildProject']} webServer",
            f"buildProfile {meta['buildProject']} dev",
            f"optLevel {meta['buildProject']} 2",
            f"runtimeChecks {meta['buildProject']} panic",
            f"persistLlvmIr {meta['buildProject']} auto",
            f"nativeOutput {meta['buildProject']} \"{meta['nativeOutput']}\"",
            f"import {meta['moduleAlias']} {meta['moduleName']}",
            "",
        ])
    return "\n".join([
        f"buildProject {meta['buildProject']}",
        f"project {meta['projectName']}",
        f"modulePath {meta['buildProject']} {meta['modulePath']}",
        f"languageVersion {meta['buildProject']} \"1.0\"",
        f"projectVersion {meta['buildProject']} \"{meta['projectVersion']}\"",
        f"projectLicense {meta['buildProject']} MIT",
        f"sourceRoot {meta['buildProject']} \".\"",
        f"registerModule {meta['buildProject']} {meta['moduleName']} \".\"",
        f"mainFile {meta['buildProject']} \"main.sem\"",
        f"mainOperation {meta['buildProject']} main",
        f"testRoot {meta['buildProject']} \".\"",
        f"testPattern {meta['buildProject']} \"*.test.sem\"",
        "target console",
        "runtime native 1",
        "entry console main",
        f"targetRuntime {meta['buildProject']} nativeExe",
        f"buildProfile {meta['buildProject']} dev",
        f"optLevel {meta['buildProject']} 2",
        f"runtimeChecks {meta['buildProject']} panic",
        f"persistLlvmIr {meta['buildProject']} auto",
        f"nativeOutput {meta['buildProject']} \"{meta['nativeOutput']}\"",
        f"import {meta['moduleAlias']} {meta['moduleName']}",
        "",
        "# External dependencies (optional). Declare them here, then run",
        "# `sem deps sync` to fetch + verify + lock, and import by module path.",
        "# Fetching is build-time authority: only `sem deps sync` touches the",
        "# network; `sem check`/`sem build` resolve imports from the cache offline.",
        f"# dependency {meta['buildProject']} exampleLib github.com/OWNER/REPO v1.0.0",
        f"# dependencyFetch {meta['buildProject']} exampleLib github OWNER/REPO v1.0.0",
        f"# dependencyIntegrity {meta['buildProject']} exampleLib sha256:<archive-digest from first sync>",
        "# then in main.sem:  import exampleLib github.com/OWNER/REPO",
        "",
    ])


def _starter_main_sem_text(meta: dict) -> str:
    if meta.get("template") == "web":
        return "\n".join([
            f"module {meta['moduleName']}",
            f"purpose module {meta['moduleName']} \"Starter web module for {meta['projectName']}.\"",
            f"moduleOwns {meta['moduleName']} \"The routed HTTP health endpoint and server lifecycle hooks.\"",
            f"moduleDoesNotOwn {meta['moduleName']} \"Project registration and artifact policy; build.sem owns those rows.\"",
            f"invariant module {meta['moduleName']} \"The health route returns a plain-text 200 response when the native HTTP adapter accepts the write.\"",
            f"exportOperation {meta['moduleName']} healthHandler",
            f"exportOperation {meta['moduleName']} startup",
            f"exportOperation {meta['moduleName']} shutdown",
            "",
            "import http standard.http",
            "",
            "webServer appServer",
            "purpose webServer appServer \"Serve the starter HTTP health endpoint.\"",
            "serverHost appServer \"127.0.0.1\"",
            "serverPort appServer 8080",
            "webServerStartup appServer startup",
            "webServerShutdown appServer shutdown",
            "route appServer GET \"/health\" healthHandler",
            "routeTimeoutOptOut appServer \"/health\" \"starter health check is a bounded in-process response\"",
            "routeMiddlewareOptOut appServer \"/health\" \"public starter health check has no cross-cutting middleware yet\"",
            "",
            "storage module immutable healthBody HttpTextBody \"ok\"",
            "storage module immutable plainTextContentType HttpContentType \"text/plain; charset=utf-8\"",
            "storage module immutable okStatus HttpStatusCode 200",
            "storage module immutable successStatus Int32 0",
            "",
            "operation startup",
            "output operation startup Int32",
            "memory startup heap no",
            "async startup no",
            "purpose operation startup \"Run startup initialization before the HTTP listener starts.\"",
            "return value successStatus",
            "",
            "operation shutdown",
            "output operation shutdown Int32",
            "memory shutdown heap no",
            "async shutdown no",
            "purpose operation shutdown \"Run shutdown cleanup after the HTTP listener returns.\"",
            "return value successStatus",
            "",
            "operation healthHandler",
            "input operation healthHandler request HttpRequest",
            "input operation healthHandler response HttpResponse",
            "output operation healthHandler Int32",
            "effect healthHandler write http.response",
            "authority healthHandler write http.response",
            "memory healthHandler heap no",
            "async healthHandler no",
            "purpose operation healthHandler \"Write the health-check response body.\"",
            "invariant operation healthHandler \"The route writes exactly one text/plain response and returns the native response status.\"",
            "call responseWriteCall http.responseText",
            "argument responseWriteCall response HttpResponse response",
            "argument responseWriteCall status HttpStatusCode okStatus",
            "argument responseWriteCall body HttpTextBody healthBody",
            "argument responseWriteCall contentType HttpContentType plainTextContentType",
            "run responseWriteCall",
            "bind value responseStatus Int32 responseWriteCall",
            "return value responseStatus",
            "",
        ])
    return "\n".join([
        f"module {meta['moduleName']}",
        f"purpose module {meta['moduleName']} \"Starter console module for {meta['projectName']}.\"",
        f"moduleOwns {meta['moduleName']} \"The exported console entrypoint and its stdout write contract.\"",
        f"moduleDoesNotOwn {meta['moduleName']} \"Project registration and artifact policy; build.sem owns those rows.\"",
        f"invariant module {meta['moduleName']} \"The exported main operation writes one greeting line and exits successfully when stdout is available.\"",
        f"exportOperation {meta['moduleName']} main",
        "",
        "error MainError",
        "errorCase MainError ConsoleWriteFailed ConsoleWriteError",
        "",
        "storage module immutable greetingText String \"Hello, world!\"",
        "",
        "operation main",
        "input operation main console Console",
        "output operation main Result ExitCode MainError",
        "effect main write console.stdout",
        "authority main write console.stdout",
        "memory main heap no",
        "async main no",
        "purpose operation main \"Write a hello-world line to standard output and exit successfully.\"",
        "invariant operation main \"Exactly one greeting line is emitted before a success or console-write failure result is returned.\"",
        "",
        "call writeGreetingCall console.writeLine",
        "argument writeGreetingCall console Console console",
        "argument writeGreetingCall text String greetingText",
        "run writeGreetingCall",
        "ignore void source writeGreetingCall",
        "bind error writeGreetingError ConsoleWriteError writeGreetingCall",
        "branch error source writeGreetingCall target writeGreetingFailed",
        "storage local immutable successCode ExitCode 0",
        "return ok successCode",
        "label writeGreetingFailed",
        "makeError consoleWriteFailure MainError.ConsoleWriteFailed writeGreetingError",
        "return error consoleWriteFailure",
        "",
    ])


def _starter_test_sem_text(meta: dict) -> str:
    # A real assertion, not `return value 0`: compute 2 + 2, check it equals 4,
    # and exit 0 only when it does (exit 1 otherwise). This exercises codegen
    # and fails loudly if arithmetic lowering regresses — unlike a constant
    # return, which "passes" without proving anything. Replace it with a check
    # of your own operation's behavior.
    return "\n".join([
        f"project {meta['projectTestName']}",
        "target console",
        "runtime AgentRuntime 0.1",
        "entry console main",
        "",
        "operation main",
        "output operation main ExitCode",
        "memory main heap no",
        "async main no",
        "purpose operation main \"Assert a known identity (2 + 2 == 4) so a codegen regression fails this smoke test.\"",
        "invariant operation main \"Exits 0 only when the asserted identity holds; any other result is a nonzero failing exit.\"",
        "storage local immutable leftAddend Int64 2",
        "storage local immutable rightAddend Int64 2",
        "storage local immutable expectedSum Int64 4",
        "call computeSumCall math.addInt64",
        "argument computeSumCall left Int64 leftAddend",
        "argument computeSumCall right Int64 rightAddend",
        "run computeSumCall",
        "bind value actualSum Int64 computeSumCall",
        "call assertSumCall math.equalInt64",
        "argument assertSumCall left Int64 actualSum",
        "argument assertSumCall right Int64 expectedSum",
        "run assertSumCall",
        "bind value sumMatchesExpected Bool assertSumCall",
        "branch if condition sumMatchesExpected target assertionHeld",
        "storage local immutable assertionFailedExitCode ExitCode 1",
        "return value assertionFailedExitCode",
        "label assertionHeld",
        "storage local immutable assertionPassedExitCode ExitCode 0",
        "return value assertionPassedExitCode",
        "",
    ])


def _starter_gitignore_text(meta: dict) -> str:
    return "\n".join([
        "# SemanticScript build + dependency cache artifacts.",
        "# The fetched-dependency cache is a build input, not checked-in source.",
        ".semcache/",
        "**/.semcache/",
        "build/",
        "**/build/",
        f"{meta['nativeOutput']}",
        "*.exe",
        "*.ll",
        "*.obj",
        "*.o",
        "*.pdb",
        "__pycache__/",
        ".sem/docs.sqlite",
        ".sem/docs.sqlite-*",
        "",
        "# Local SQLite databases an app creates at runtime, including the WAL",
        "# sidecars (-wal/-shm) that `PRAGMA journal_mode = WAL` leaves on disk.",
        "# These are runtime state, not source; without the sidecars a `sem new`",
        "# project that enables WAL leaks *.db-wal/*.db-shm into git status.",
        "*.db",
        "*.db-wal",
        "*.db-shm",
        "",
        "# Keep sem.lock committed: it pins resolved dependency versions and",
        "# checksums so `sem deps sync` is reproducible across machines.",
        "!sem.lock",
        "",
    ])


def _starter_ci_workflow_text(meta: dict) -> str:
    lines = [
        "name: CI",
        "",
        "on:",
        "  push:",
        "  pull_request:",
        "  workflow_dispatch:",
        "",
        "permissions:",
        "  contents: read",
        "",
        "jobs:",
        "  validate:",
        "    runs-on: windows-latest",
        "    steps:",
        "      - name: Check out starter project",
        "        uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd # v6",
        "",
        "      - name: Check out SemanticScript toolchain",
        "        uses: actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd # v6",
        "        with:",
        "          repository: monstercameron/SemanticScript",
        "          path: SemanticScript",
        "",
        "      - name: Set up Python",
        "        uses: actions/setup-python@a309ff8b426b58ec0e2a45f0f869d46889d02405 # v6",
        "        with:",
        "          python-version: \"3.12\"",
        "          cache: pip",
        "          cache-dependency-path: SemanticScript/requirements.txt",
        "",
        "      - name: Install SemanticScript dependencies",
        "        run: |",
        "          python -m pip install --upgrade pip",
        "          python -m pip install -r SemanticScript/requirements.txt",
        "",
        "      - name: Check project",
        "        run: python SemanticScript/SemanticScript/tools/sem.py check --json .",
        "",
        "      - name: Run semantic smoke tests",
        "        run: python SemanticScript/SemanticScript/tools/sem.py test --json . --skip-python-harnesses",
        "",
        "      - name: Build native executable",
        "        run: python SemanticScript/SemanticScript/tools/sem.py build . -- --emit-exe",
        "",
    ]
    if meta.get("template") != "web":
        lines.extend([
            "      - name: Smoke run hello world",
            "        run: python SemanticScript/SemanticScript/tools/sem.py run .",
            "",
        ])
    return "\n".join(lines)


def _starter_project_payload(
    path: Path,
    *,
    force: bool = False,
    github_url: str | None = None,
    docs_index_opt_in: bool = False,
    template: str = "console",
) -> dict:
    root = path.resolve()
    github_repo = None
    if github_url:
        github_repo = _starter_github_repo_details(github_url)
        if github_repo is None:
            return {
                "schemaVersion": "sem.newProject.v1",
                "tool": {"name": "sem", "version": VERSION},
                "ok": False,
                "status": "invalid-github-url",
                "requestedPath": str(path),
                "error": "GitHub repo URL must look like https://github.com/OWNER/REPO or git@github.com:OWNER/REPO.git",
                "project": {
                    "root": str(root),
                    "githubRepoUrl": github_url,
                },
                "filesCreated": [],
                "filesOverwritten": [],
                "nextCommands": [],
            }
    meta = _starter_project_metadata(root, github_repo=github_repo, template=template)
    build_path = root / "build.sem"
    main_path = root / "main.sem"
    test_path = root / meta["testFileName"]
    workflow_path = root / ".github" / "workflows" / "ci.yml"
    gitignore_path = root / ".gitignore"
    docs_db_path = root / ".sem" / "docs.sqlite"
    files_created: list[str] = []
    files_overwritten: list[str] = []
    next_commands = [
        _next_command_entry(
            "check",
            "verify that the generated starter project parses, lints, and compiles cleanly",
            argv=["sem", "check", "--json", str(root)],
        ),
        _next_command_entry(
            "test",
            "run the generated semantic smoke test from the starter project",
            argv=["sem", "test", "--json", str(root), "--skip-python-harnesses"],
        ),
        _next_command_entry(
            "build",
            "emit the native executable for the starter project",
            argv=["sem", "build", str(root), "--", "--emit-exe"],
        ),
    ]
    if template == "web":
        next_commands.append(_next_command_entry(
            "dev",
            "print the watch/rerun plan for the web server (files to watch + the "
            "build/run commands to rerun on change); it emits the plan, it does "
            "not run a watcher",
            argv=["sem", "dev", str(root), "--json"],
        ))
    else:
        next_commands.insert(2, _next_command_entry(
            "run",
            "run the starter project through the JIT and confirm the hello-world output",
            argv=["sem", "run", str(root)],
        ))
    docs_index = {
        # `enabled` reports whether THIS scaffold opted into building a docs
        # index now — NOT whether `docs search` works. Keyword search works on
        # any built index with no model (see keywordSearch below); you can run
        # `sem docs index` / `sem docs search` at any time.
        "enabled": bool(docs_index_opt_in),
        "dbPath": str(docs_db_path),
        "embeddingProvider": DOCS_DEFAULT_EMBEDDING_PROVIDER,
        "embeddingModel": DOCS_DEFAULT_EMBEDDING_MODEL,
        "requirementsFile": str((ROOT.parent / "requirements-docs.txt").resolve()),
        # The embedding model is required ONLY for semantic (vector) ranking.
        # Keyword (FTS/BM25) search needs no model and works on the frozen exe.
        "allowModelDownloadRequired": True,
        "semanticSearchRequiresModel": True,
        "keywordSearch": {
            "available": True,
            "requiresModel": False,
            "note": (
                "`sem docs index --embedding-provider none` builds a model-free "
                "keyword index, and `sem docs search --embedding-provider none` "
                "queries it via FTS/BM25 — no embedding model or download needed."
            ),
        },
        "packagingNote": "Python CLI users install requirements-docs.txt; frozen sem.exe builds need the docs-embeddings packaging variant to run embeddings inside the executable.",
    }
    if docs_index_opt_in:
        docs_deps_command = f"python -m pip install -r {docs_index['requirementsFile']}"
        docs_deps_argv = None if getattr(sys, "frozen", False) else [sys.executable, "-m", "pip", "install", "-r", docs_index["requirementsFile"]]
        next_commands.extend([
            _next_command_entry(
                "docs-deps",
                "install optional dependencies for local semantic docs search",
                argv=docs_deps_argv,
                command=docs_deps_command,
                replayable=False,
            ),
            _next_command_entry(
                "docs-index",
                "build the local semantic docs index for this starter project",
                argv=[
                    "sem", "docs", "index", "--path", str(root), "--db", str(docs_db_path),
                    "--include-std", "--allow-model-download", "--json",
                ],
                command=f"sem docs index --path {root} --db {docs_db_path} --include-std --allow-model-download --json",
                replayable=False,
            ),
            _next_command_entry(
                "docs-search",
                "try semantic docs search after the index is built",
                argv=["sem", "docs", "search", "hello world console write", "--path", str(root), "--db", str(docs_db_path), "--json"],
                command=f"sem docs search \"hello world console write\" --path {root} --db {docs_db_path} --json",
                replayable=False,
            ),
        ])
    payload = {
        "schemaVersion": "sem.newProject.v1",
        "tool": {"name": "sem", "version": VERSION},
        "ok": False,
        "status": "error",
        "requestedPath": str(path),
        "project": {
            "root": str(root),
            "buildProject": meta["buildProject"],
            "projectName": meta["projectName"],
            "moduleName": meta["moduleName"],
            "modulePath": meta["modulePath"],
            "buildFile": str(build_path),
            "mainFile": str(main_path),
            "testFile": str(test_path),
            "workflowFile": str(workflow_path),
            "gitignoreFile": str(gitignore_path),
            "projectVersion": meta["projectVersion"],
            "nativeOutput": meta["nativeOutput"],
            "githubRepoUrl": meta["githubRepoUrl"],
            "githubRepoSlug": meta["githubRepoSlug"],
            "template": template,
            "docsIndex": docs_index,
        },
        "filesCreated": files_created,
        "filesOverwritten": files_overwritten,
        "nextCommands": next_commands,
    }
    try:
        if root.exists():
            if not root.is_dir():
                payload["error"] = "target path exists and is not a directory"
                payload["status"] = "path-not-directory"
                return payload
            existing_entries = list(root.iterdir())
            if existing_entries and not force:
                payload["error"] = "target directory already exists and is not empty; pass --force to overwrite the starter scaffold files"
                payload["status"] = "path-not-empty"
                return payload
        else:
            root.mkdir(parents=True, exist_ok=True)

        for target_path in (workflow_path.parent,):
            target_path.mkdir(parents=True, exist_ok=True)

        for target_path, text in (
            (build_path, _starter_build_sem_text(meta)),
            (main_path, _starter_main_sem_text(meta)),
            (test_path, _starter_test_sem_text(meta)),
            (workflow_path, _starter_ci_workflow_text(meta)),
            (gitignore_path, _starter_gitignore_text(meta)),
        ):
            if target_path.exists():
                files_overwritten.append(str(target_path))
            else:
                files_created.append(str(target_path))
            target_path.write_text(text, encoding="utf-8", newline="\n")
    except OSError as exc:
        payload["error"] = str(exc)
        payload["status"] = "write-failed"
        return payload

    payload["ok"] = True
    payload["status"] = "updated" if files_overwritten else "created"
    return payload


def _find_build_tape(start: Path) -> Path | None:
    candidate = start.resolve()
    if candidate.is_file():
        if candidate.name.lower() in {"build.sem", "build.sscript"}:
            return candidate
        candidate = candidate.parent

    for directory in (candidate, *candidate.parents):
        for build_name in ("build.sem", "build.sscript"):
            build_path = directory / build_name
            if build_path.is_file():
                return build_path
    return None


def _strip_separator(args: list[str]) -> list[str]:
    if args and args[0] == "--":
        return args[1:]
    return args


def _has_compiler_action(args: list[str]) -> bool:
    action_flags = {
        "--emit-exe",
        "--emit-ir",
        "--run",
        "--parse-only",
        "--lint",
        "--strict",
        "--inspect-ir",
        "--emit-trace-map",
        "--trace",
    }
    return any(arg in action_flags for arg in args)


def _run_compiler(source: Path, compiler_args: list[str]) -> int:
    semsc_path = ROOT / "compiler" / "semsc.py"
    command = [sys.executable, str(semsc_path), str(source), *compiler_args]
    return subprocess.call(command)


def _capture_compiler(source: Path, compiler_args: list[str],
                      timeout: int | None = None,
                      env: dict | None = None) -> subprocess.CompletedProcess:
    semsc_path = ROOT / "compiler" / "semsc.py"
    command = [sys.executable, str(semsc_path), str(source), *compiler_args]
    # The compiler emits UTF-8 (diagnostics include non-ASCII like `§3`). Decode
    # as UTF-8 explicitly so captured stderr isn't mojibake under the Windows
    # locale codec; `errors="replace"` keeps capture robust to stray bytes.
    return subprocess.run(command, capture_output=True, text=True,
                          encoding="utf-8", errors="replace",
                          timeout=timeout, env=env)


def _extract_flag(args: list[str], flag: str) -> tuple[bool, list[str]]:
    found = False
    kept = []
    for arg in args:
        if arg == flag:
            found = True
            continue
        kept.append(arg)
    return found, kept


def _split_sem_row(line: str) -> list[str]:
    try:
        return shlex.split(line, comments=True, posix=True)
    except ValueError:
        return line.strip().split()


def _scan_run_target_facts(source: Path) -> dict:
    files: list[Path] = [source]
    build_tape = source if source.name.lower() in {"build.sem", "build.sscript"} else None
    if build_tape is not None and build_tape.exists():
        try:
            build_text = build_tape.read_text(encoding="utf-8")
        except OSError:
            build_text = ""
        for raw in build_text.splitlines():
            tokens = _split_sem_row(raw.strip())
            if len(tokens) >= 3 and tokens[0] == "mainFile":
                main_path = Path(tokens[2])
                if not main_path.is_absolute():
                    main_path = build_tape.parent / main_path
                files.append(main_path)
    facts = {
        "target": "",
        "targetRuntime": "",
        "webServers": {},
        "routes": [],
        "sourceFiles": [str(path.resolve()) for path in files if path.exists()],
    }
    for path in files:
        if not path.exists():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for raw in text.splitlines():
            stripped = raw.strip()
            if not stripped or stripped.startswith("#"):
                continue
            tokens = _split_sem_row(stripped)
            if not tokens:
                continue
            verb = tokens[0]
            args = tokens[1:]
            if verb == "target" and args:
                facts["target"] = args[0]
            elif verb == "targetRuntime" and len(args) >= 2:
                facts["targetRuntime"] = args[1]
            elif verb == "webServer" and args:
                facts["webServers"].setdefault(args[0], {"host": "", "port": "", "routes": []})
            elif verb == "serverHost" and len(args) >= 2:
                facts["webServers"].setdefault(args[0], {"host": "", "port": "", "routes": []})["host"] = args[1]
            elif verb == "serverPort" and len(args) >= 2:
                facts["webServers"].setdefault(args[0], {"host": "", "port": "", "routes": []})["port"] = args[1]
            elif verb == "route" and len(args) >= 4:
                route = {
                    "server": args[0],
                    "method": args[1],
                    "path": args[2],
                    "handler": args[3],
                }
                facts["routes"].append(route)
                facts["webServers"].setdefault(args[0], {"host": "", "port": "", "routes": []})["routes"].append(route)
    return facts


def _run_not_executed_payload(source: Path, facts: dict, status: str, reason: str) -> dict:
    web_servers = facts.get("webServers", {})
    first_server = next(iter(web_servers.values()), {})
    host = first_server.get("host", "127.0.0.1") or "127.0.0.1"
    port = first_server.get("port", "") or ""
    base_url = f"http://{host}:{port}" if port else ""
    return {
        "schemaVersion": "sem.run.v1",
        "tool": {"name": "sem", "version": VERSION},
        "ok": False,
        "status": status,
        "source": {"path": str(source.resolve())},
        "targetKind": facts.get("targetRuntime") or facts.get("target") or "",
        "baseUrl": base_url,
        "routes": facts.get("routes", []),
        "target": {
            "kind": facts.get("targetRuntime") or facts.get("target") or "",
            "target": facts.get("target", ""),
            "targetRuntime": facts.get("targetRuntime", ""),
            "webServers": web_servers,
            "routes": facts.get("routes", []),
            "baseUrl": base_url,
        },
        "execution": {"ran": False, "reason": reason},
        "nextCommands": [
            _next_command_entry(
                "build",
                "emit the native executable for this long-running target",
                argv=["sem", "build", str(source.parent if source.name.lower() in {"build.sem", "build.sscript"} else source), "--", "--emit-exe"],
            ),
            _next_command_entry(
                "dev",
                "print the watch/rerun plan for long-running webServer targets "
                "(emits files-to-watch + commands-to-rerun; it does not run a "
                "watcher itself)",
                argv=["sem", "dev", str(source.parent if source.name.lower() in {"build.sem", "build.sscript"} else source), "--json"],
            ),
        ],
    }


def _project_surface_path(path: Path) -> Path:
    build_tape = _find_build_tape(path)
    requested = path.resolve()
    if build_tape is not None:
        return build_tape.parent.resolve()
    if requested.is_dir():
        return requested
    return requested


def _timed_call(func, *args, **kwargs):
    start = time.perf_counter_ns()
    result = func(*args, **kwargs)
    duration_ns = time.perf_counter_ns() - start
    return result, duration_ns


def _repo_root() -> Path:
    proc = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
    )
    if proc.returncode == 0 and proc.stdout.strip():
        return Path(proc.stdout.strip()).resolve()
    return Path.cwd().resolve()


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _is_ignored(path: Path, repo_root: Path) -> bool:
    proc = subprocess.run(
        ["git", "check-ignore", "-q", "--", str(path)],
        cwd=str(repo_root),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return proc.returncode == 0


def _clean_roots(paths: list[str], repo_root: Path) -> list[Path]:
    if not paths:
        return [repo_root]
    roots = []
    for raw_path in paths:
        candidate = Path(raw_path)
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
        resolved = candidate.resolve()
        if not _is_under(resolved, repo_root):
            raise ValueError(f"clean path escapes repository root: {raw_path}")
        roots.append(resolved)
    return roots


def _format_clean_target(path: Path, repo_root: Path) -> str:
    try:
        display = path.relative_to(repo_root)
    except ValueError:
        display = path
    text = str(display).replace(os.sep, "/")
    if path.is_dir() and not path.is_symlink():
        text += "/"
    return text


def _collect_clean_targets(paths: list[str]) -> tuple[Path, list[Path]]:
    repo_root = _repo_root()
    roots = _clean_roots(paths, repo_root)
    targets = set()

    for root in roots:
        if root.is_file():
            if root.suffix in CLEAN_FILE_SUFFIXES and _is_ignored(root, repo_root):
                targets.add(root)
            continue
        if not root.exists():
            continue
        for current, dirs, files in os.walk(root):
            current_path = Path(current)
            if ".git" in dirs:
                dirs.remove(".git")
            if "third_party" in dirs:
                dirs.remove("third_party")
            for dirname in list(dirs):
                child = current_path / dirname
                if dirname in CLEAN_DIRECTORY_NAMES and _is_ignored(child, repo_root):
                    targets.add(child)
                    dirs.remove(dirname)
            for filename in files:
                child = current_path / filename
                if child.suffix in CLEAN_FILE_SUFFIXES and _is_ignored(child, repo_root):
                    targets.add(child)

    for relative in CLEAN_EXACT_RELATIVE_PATHS:
        candidate = repo_root / relative
        if candidate.exists() and any(_is_under(candidate, root) for root in roots):
            if _is_ignored(candidate, repo_root):
                targets.add(candidate)

    return repo_root, sorted(targets, key=lambda item: str(item).lower())


def _remove_clean_target(path: Path, repo_root: Path) -> None:
    resolved = path.resolve()
    if not _is_under(resolved, repo_root):
        raise ValueError(f"refusing to clean path outside repository: {path}")
    if resolved.is_dir() and not resolved.is_symlink():
        shutil.rmtree(resolved)
    else:
        resolved.unlink()


def _directory_size_bytes(path: Path) -> int:
    total = 0
    for current, _, files in os.walk(path):
        for filename in files:
            try:
                total += (Path(current) / filename).stat().st_size
            except OSError:
                continue
    return total


def _collect_pyinstaller_temp_targets(
    temp_root: Path | None = None,
    *,
    min_age_seconds: int = 3600,
) -> tuple[Path, list[dict]]:
    root = (temp_root or Path(tempfile.gettempdir())).resolve()
    now = time.time()
    current_meipass = getattr(sys, "_MEIPASS", None)
    current_meipass_path = Path(current_meipass).resolve() if current_meipass else None
    targets: list[dict] = []
    if not root.exists():
        return root, []
    for child in sorted(root.iterdir(), key=lambda item: item.name.lower()):
        if not child.is_dir() or child.is_symlink() or not child.name.startswith("_MEI"):
            continue
        try:
            resolved = child.resolve()
            stat = child.stat()
        except OSError:
            continue
        if current_meipass_path is not None and resolved == current_meipass_path:
            continue
        if resolved.parent != root:
            continue
        age_seconds = int(max(0, now - stat.st_mtime))
        if age_seconds < min_age_seconds:
            continue
        targets.append({
            "path": resolved,
            "ageSeconds": age_seconds,
            "sizeBytes": _directory_size_bytes(resolved),
        })
    return root, targets


def _remove_pyinstaller_temp_target(path: Path, temp_root: Path) -> None:
    resolved = path.resolve()
    root = temp_root.resolve()
    if resolved.parent != root or not resolved.name.startswith("_MEI"):
        raise ValueError(f"refusing to clean non-PyInstaller temp path: {path}")
    if not resolved.is_dir() or resolved.is_symlink():
        raise ValueError(f"refusing to clean non-directory temp path: {path}")
    shutil.rmtree(resolved)


def _version_command(command: list[str]) -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    text = (proc.stdout or proc.stderr).splitlines()
    detail = text[0] if text else f"exit {proc.returncode}"
    return proc.returncode == 0, detail


def _doctor_check(name: str, ok: bool, detail: str, fix: str = "", optional: bool = False) -> dict:
    return {
        "name": name,
        "ok": bool(ok),
        "detail": detail,
        "fix": fix,
        "optional": bool(optional),
    }


def _pkg_config_exists(package_name: str) -> tuple[bool, str]:
    pkg_config = shutil.which("pkg-config")
    if not pkg_config:
        return False, "pkg-config missing"
    try:
        proc = subprocess.run(
            [pkg_config, "--modversion", package_name],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    detail = (proc.stdout or proc.stderr).strip() or f"exit {proc.returncode}"
    return proc.returncode == 0, detail


def _env_file_exists(var_name: str) -> tuple[bool, str]:
    value = os.environ.get(var_name, "")
    if not value:
        return False, f"{var_name} unset"
    path = Path(value)
    return path.exists(), str(path)


def _env_any_file_exists(var_names: list[str]) -> tuple[bool, str]:
    details = []
    for var_name in var_names:
        ok, detail = _env_file_exists(var_name)
        if ok:
            return True, f"{var_name}={detail}"
        details.append(detail)
    return False, "; ".join(details)


def _env_header_exists(
    header_path: str,
    *,
    root_var: str,
    include_var: str,
) -> tuple[bool, str]:
    candidates = []
    include_value = os.environ.get(include_var, "")
    if include_value:
        candidates.append(Path(include_value))
    root_value = os.environ.get(root_var, "")
    if root_value:
        candidates.append(Path(root_value) / "include")
    if not candidates:
        return False, f"{include_var}/{root_var} unset"
    for directory in candidates:
        candidate = directory / header_path
        if candidate.exists():
            return True, str(candidate)
    return False, "; ".join(str(directory / header_path) for directory in candidates)


def _doctor_payload() -> dict:
    python_ok = sys.version_info >= (3, 10)
    python_detail = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if python_ok and sys.version_info < (3, 11):
        python_detail += " (compatible; 3.11+ recommended for release validation)"
    checks = [
        _doctor_check(
            "python",
            python_ok,
            python_detail,
            "Install Python 3.10 or newer. Use Python 3.11 or newer for release validation.",
        ),
        _doctor_check(
            "llvmlite",
            importlib.util.find_spec("llvmlite") is not None,
            "available" if importlib.util.find_spec("llvmlite") is not None else "missing",
            "Run: python -m pip install -r requirements.txt",
        ),
    ]

    clang_env = os.environ.get("SEMSC_CLANG", "")
    zig_path = shutil.which("zig") or ""
    clang_path = clang_env or shutil.which("clang") or ""
    clang_ok = bool(clang_path) and (clang_env == "" or Path(clang_path).exists())
    c_compiler_ok = clang_ok or bool(zig_path)
    c_compiler_detail = clang_path or (f"zig cc={zig_path}" if zig_path else "missing")
    checks.append(_doctor_check(
        "clang",
        c_compiler_ok,
        c_compiler_detail,
        "Install LLVM/clang, install Zig, or set SEMSC_CLANG to a clang-compatible command.",
    ))

    if (ROOT.parent / "vscode-semanticscript").exists():
        node_path = shutil.which("node")
        node_ok = bool(node_path)
        node_detail = node_path or "missing"
        if node_ok:
            ok, detail = _version_command(["node", "--version"])
            node_ok = ok
            node_detail = detail
        checks.append(_doctor_check(
            "node",
            node_ok,
            node_detail,
            "Install Node.js 20 or newer for VS Code extension checks.",
        ))

    cmake_path = shutil.which("cmake")
    cmake_ok = bool(cmake_path)
    cmake_detail = cmake_path or "missing"
    if cmake_ok:
        ok, detail = _version_command(["cmake", "--version"])
        cmake_ok = ok
        cmake_detail = detail
    git_path = shutil.which("git")
    git_ok = bool(git_path)
    checks.append(_doctor_check(
        "native-http-runtime",
        cmake_ok and c_compiler_ok,
        f"cmake={cmake_detail}; cCompiler={c_compiler_detail}",
        "Install CMake plus LLVM/clang or Zig before building SemanticScript/runtime/native_http.",
    ))

    libuv_pkg_ok, libuv_pkg_detail = _pkg_config_exists("libuv")
    libuv_lib_ok, libuv_lib_detail = _env_any_file_exists(
        ["SEM_LIBUV_LIB", "SEM_LIBUV_LIBRARY"])
    libuv_header_ok, libuv_header_detail = _env_header_exists(
        "uv.h",
        root_var="SEM_LIBUV_ROOT",
        include_var="SEM_LIBUV_INCLUDE_DIR",
    )
    libuv_env_ok = libuv_lib_ok and libuv_header_ok
    libuv_fetch_ok = cmake_ok and git_ok
    libuv_fetch_detail = (
        "system libuv missing; CMake FetchContent fallback available"
        if libuv_fetch_ok else
        "system libuv missing; install git+CMake or set SEM_LIBUV_*"
    )
    checks.append(_doctor_check(
        "native-async-libuv",
        libuv_pkg_ok or libuv_env_ok or libuv_fetch_ok,
        (
            libuv_pkg_detail if libuv_pkg_ok
            else f"{libuv_lib_detail}; {libuv_header_detail}" if libuv_env_ok
            else libuv_fetch_detail
        ),
        "Install libuv 1.x, set SEM_LIBUV_ROOT/SEM_LIBUV_INCLUDE_DIR/SEM_LIBUV_LIB, or allow CMake FetchContent.",
        optional=True,
    ))

    curl_pkg_ok, curl_pkg_detail = _pkg_config_exists("libcurl")
    curl_lib_ok, curl_lib_detail = _env_any_file_exists(
        ["SEM_CURL_LIB", "SEM_CURL_LIBRARY"])
    curl_header_ok, curl_header_detail = _env_header_exists(
        "curl/curl.h",
        root_var="SEM_CURL_ROOT",
        include_var="SEM_CURL_INCLUDE_DIR",
    )
    curl_env_ok = curl_lib_ok and curl_header_ok
    curl_fetch_ok = cmake_ok and git_ok
    curl_fetch_detail = (
        "system libcurl missing; CMake FetchContent fallback available"
        if curl_fetch_ok else
        "system libcurl missing; install git+CMake or set SEM_CURL_*"
    )
    checks.append(_doctor_check(
        "native-http-client-libcurl",
        curl_pkg_ok or curl_env_ok or curl_fetch_ok,
        (
            curl_pkg_detail if curl_pkg_ok
            else f"{curl_lib_detail}; {curl_header_detail}" if curl_env_ok
            else curl_fetch_detail
        ),
        "Install libcurl, set SEM_CURL_ROOT/SEM_CURL_INCLUDE_DIR/SEM_CURL_LIB, or allow CMake FetchContent.",
        optional=True,
    ))

    return {
        "schemaVersion": "sem.doctor.v0",
        "tool": {"name": "sem", "version": VERSION},
        "checks": checks,
        "ok": all(check["ok"] or check.get("optional", False) for check in checks),
    }


def _load_semlint_module():
    module_name = "_sem_driver_semlint"
    if module_name in sys.modules:
        return sys.modules[module_name]
    semlint_path = ROOT / "linter" / "semlint.py"
    spec = importlib.util.spec_from_file_location(module_name, semlint_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load semlint from {semlint_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _line_payload(line) -> dict:
    return {
        "path": str(Path(line.path).resolve()),
        "line": int(line.number),
        "column": int(line.column),
    }


def _row_value(facts, verb: str, index: int = 0, default: str = "") -> str:
    for source_line in facts.lines:
        if source_line.tokens and source_line.verb == verb and len(source_line.args) > index:
            return source_line.args[index]
    return default


def _row_values(facts, verb: str, index: int = 0) -> list[str]:
    values = []
    for source_line in facts.lines:
        if source_line.tokens and source_line.verb == verb and len(source_line.args) > index:
            values.append(source_line.args[index])
    return values


def _syntax_status_counts() -> dict:
    counts = {"implemented": 0, "partial": 0, "notImplemented": 0}
    try:
        text = SYNTAX_INVENTORY_PATH.read_text(encoding="utf-8")
    except OSError:
        return counts
    counts["implemented"] = text.count("| Impl'd |")
    counts["partial"] = text.count("| Partial |")
    counts["notImplemented"] = text.count("| Not impl'd |")
    return counts


def _runtime_feature_flags() -> dict:
    runtime_root = ROOT / "runtime"
    third_party_root = ROOT.parent / "third_party"
    return {
        "nativeHttpRuntime": (runtime_root / "native_http" / "sem_http_runtime.c").exists(),
        "nativeHttpH2oBackend": False,
        "nativeHttpConcurrentDispatch": False,
        "nativeJsonRuntime": (runtime_root / "native_json" / "sem_json_runtime.c").exists(),
        "nativeSqliteRuntime": (runtime_root / "native_sqlite" / "sem_sqlite_runtime.c").exists(),
        "nativeWin32GuiRuntime": (
            runtime_root / "native_win32_gui" / "sem_win32_gui_runtime.c"
        ).exists(),
        "nativeWinui3GuiScaffold": (
            runtime_root / "native_winui3_gui" / "sem_winui3_gui_runtime.h"
        ).exists(),
        "nativeBcryptRuntime": (runtime_root / "native_bcrypt" / "sem_bcrypt_runtime.c").exists(),
        "vendoredSqlite": (third_party_root / "sqlite" / "sqlite3.c").exists(),
        "vendoredBcrypt": (third_party_root / "bcrypt").exists(),
    }


def _runtime_feature_docs() -> list[dict]:
    runtime_root = ROOT / "runtime"
    third_party_root = ROOT.parent / "third_party"
    specs = [
        {
            "name": "nativeHttpRuntime",
            "summary": (
                "Native HTTP/1.1 runtime adapter for routed target webServer "
                "programs. The current dispatcher is blocking and single-threaded."
            ),
            "path": runtime_root / "native_http" / "sem_http_runtime.c",
            "terms": [
                "target webServer", "route", "routeMiddleware", "HttpRequest",
                "HttpResponse", "native HTTP runtime", "SSE", "multipart",
                "cookies", "headers", "query parameters", "blocking",
                "single-threaded", "slow handler",
            ],
        },
        {
            "name": "nativeHttpConcurrentDispatch",
            "summary": (
                "Concurrent/nonblocking HTTP request dispatch is not implemented. "
                "The current native HTTP adapter accepts one connection, runs one "
                "handler synchronously, closes it, then accepts the next connection."
            ),
            "path": runtime_root / "native_http" / "sem_http_runtime.c",
            "availability": "unavailable-staged",
            "enabled": False,
            "terms": [
                "concurrent dispatch", "nonblocking HTTP", "async dispatch",
                "single-threaded", "blocking accept loop", "slow handler",
                "load testing", "request cancellation", "backpressure",
            ],
            "usage": [
                "Serialize current webServer smoke tests; do not fan out parallel clients against the blocking adapter.",
                "Use an external reverse proxy timeout or process supervisor for production-style concurrency until a nonblocking runtime lands.",
            ],
        },
        {
            "name": "nativeHttpH2oBackend",
            "summary": (
                "HTTP/2/H2O backend is staged only: the source has a guarded "
                "SEM_HTTP_WITH_H2O branch, but semsc.py does not wire HTTP/2 "
                "dispatch and the branch returns SS_HTTP_ERR_RUNTIME_UNAVAILABLE."
            ),
            "path": runtime_root / "native_http" / "sem_http_runtime.c",
            "availability": "unavailable-staged",
            "enabled": False,
            "terms": [
                "HTTP/2", "HTTP2", "H2O", "libh2o", "SEM_HTTP_WITH_H2O",
                "target webServer", "native HTTP runtime", "runtime unavailable",
            ],
            "usage": [
                "Use the default nativeHttpRuntime feature for current webServer builds; it is HTTP/1.1 and blocking.",
                "Do not set SEM_HTTP_WITH_H2O expecting a working server: the staged branch intentionally returns runtime-unavailable.",
            ],
        },
        {
            "name": "nativeJsonRuntime",
            "summary": "Native JSON parser/stringifier runtime used by json.parse and json.stringify targets.",
            "path": runtime_root / "native_json" / "sem_json_runtime.c",
            "terms": ["JSON runtime", "json.parse", "json.stringify", "JsonValueKind", "bounded scratch"],
        },
        {
            "name": "nativeSqliteRuntime",
            "summary": "Native SQLite runtime adapter for standard.sqlite database and statement operations.",
            "path": runtime_root / "native_sqlite" / "sem_sqlite_runtime.c",
            "terms": ["SQLite runtime", "sqlite.openDatabase", "SqliteDatabase", "SqliteStatement", "vendored sqlite"],
        },
        {
            "name": "nativeWin32GuiRuntime",
            "summary": "Native Win32 GUI bridge for target windowsGui programs that call standard.gui targets.",
            "path": runtime_root / "native_win32_gui" / "sem_win32_gui_runtime.c",
            "terms": ["Windows GUI runtime", "target windowsGui", "guiBackend win32", "standard.gui", "GuiSession", "GuiEvent"],
        },
        {
            "name": "nativeWinui3GuiScaffold",
            "summary": "WinUI 3 GUI backend scaffold headers; build integration is not a complete executable backend yet.",
            "path": runtime_root / "native_winui3_gui" / "sem_winui3_gui_runtime.h",
            "terms": ["WinUI 3 scaffold", "guiBackend winui3", "Windows App SDK", "partial GUI backend"],
        },
        {
            "name": "nativeBcryptRuntime",
            "summary": "Native bcrypt/password and random-byte runtime adapter.",
            "path": runtime_root / "native_bcrypt" / "sem_bcrypt_runtime.c",
            "terms": ["bcrypt runtime", "bcrypt.hashPassword", "bcrypt.verifyPassword", "randomBytes", "password hashing"],
        },
        {
            "name": "vendoredSqlite",
            "summary": "Vendored upstream SQLite source used by the native SQLite runtime.",
            "path": third_party_root / "sqlite" / "sqlite3.c",
            "terms": ["vendored sqlite", "third_party sqlite", "sqlite3.c"],
        },
        {
            "name": "vendoredBcrypt",
            "summary": "Vendored bcrypt implementation used by native bcrypt runtime support.",
            "path": third_party_root / "bcrypt",
            "terms": ["vendored bcrypt", "third_party bcrypt", "crypt_blowfish"],
        },
    ]
    flags = _runtime_feature_flags()
    docs: list[dict] = []
    for spec in specs:
        path = Path(spec["path"])
        docs.append({
            "name": spec["name"],
            "qualifiedName": spec["name"],
            "fullName": spec["name"],
            "module": "runtime",
            "moduleName": "runtime",
            "summary": spec["summary"],
            "availability": spec.get(
                "availability",
                "available" if flags.get(spec["name"], False) else "missing",
            ),
            "enabled": bool(spec.get("enabled", flags.get(spec["name"], False))),
            "terms": spec["terms"],
            "usage": spec.get("usage", [
                "Use docs_search/docs_get for the standard-library operations related to this feature before generating calls.",
                "Use readiness or doctor to separate source diagnostics from environment/runtime availability.",
            ]),
            "location": {
                "path": str(path.resolve()) if path.exists() else str(path),
                "line": 1,
            },
        })
    return docs


def _strip_markdown_inline(text: str) -> str:
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"\*\*([^*]*)\*\*", r"\1", text)
    return text.strip()


def _syntax_feature_docs(limit: int | None = None) -> list[dict]:
    try:
        lines = SYNTAX_INVENTORY_PATH.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    docs: list[dict] = []
    for line_number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped.startswith("|") or stripped.startswith("|---") or "Implementation status" in stripped:
            continue
        cells = re.split(r"\s+\|\s+", stripped.strip("|").strip(), maxsplit=2)
        if len(cells) != 3 or cells[0].strip().lower() == "syntax":
            continue
        syntax_raw = _strip_markdown_inline(cells[0])
        description = _strip_markdown_inline(cells[1])
        status = _strip_markdown_inline(cells[2]).strip()
        if not syntax_raw:
            continue
        docs.append({
            "name": syntax_raw,
            "qualifiedName": f"syntax.{syntax_raw}",
            "fullName": syntax_raw,
            "module": "language.syntax",
            "moduleName": "language.syntax",
            "summary": description,
            "status": status,
            "implementationStatus": status,
            "terms": [
                "coding feature", "language feature", "syntax row", "verb",
                "grammar", "strictExecutable", "refinedSyntax", syntax_raw.split(" ", 1)[0],
            ],
            "usage": [
                "Load sem-syntax for the compact row inventory before editing syntax.",
                "Parser, linter, docs, tests, and editor support must move together for syntax changes.",
            ],
            "location": {
                "path": str(SYNTAX_INVENTORY_PATH.resolve()),
                "line": line_number,
            },
        })
        if limit is not None and len(docs) >= limit:
            break
    return docs


def _language_guide_docs() -> list[dict]:
    operations_dataflow_path = ROOT.parent / "docs" / "language" / "operations-dataflow.md"
    optimization_guide_path = ROOT.parent / "docs" / "optimization-guide.md"
    return [
        {
            "name": "howDoILoop",
            "qualifiedName": "language.guide.howDoILoop",
            "fullName": "How do I loop",
            "module": "language.guide",
            "moduleName": "language.guide",
            "summary": (
                "Loop with explicit control-flow rows: declare a loopStart label, "
                "compute a Bool done condition, branch to the exit label when it is true, "
                "update loop state with set, then jump back to loopStart."
            ),
            "terms": [
                "how do I loop",
                "loop",
                "while loop",
                "for loop",
                "iteration",
                "control flow",
                "label loopStart",
                "branch if condition",
                "jump target loopStart",
                "set local",
                "mutable storage",
            ],
            "usage": [
                "Use `label NAME` for the loop head and exit target.",
                "Use a math comparison call to bind a Bool condition before `branch if condition CONDITION target LABEL`.",
                "Update the loop counter or accumulator with `set local NAME VALUE` before `jump target loopStart`.",
                "SemanticScript has no expression-level for/while syntax; loops are explicit rows.",
            ],
            "exampleRows": [
                "label loopStart",
                "call doneCheckCall math.greaterThanInt64",
                "argument doneCheckCall left Int64 currentIndex",
                "argument doneCheckCall right Int64 finalIndex",
                "run doneCheckCall",
                "bind value isDone Bool doneCheckCall",
                "branch if condition isDone target loopDone",
                "set local currentIndex nextIndex",
                "jump target loopStart",
                "label loopDone",
            ],
            "location": {
                "path": str(operations_dataflow_path.resolve()),
                "line": 109,
            },
        },
        {
            "name": "sqliteInsertReturningGeneratedId",
            "qualifiedName": "language.guide.sqliteInsertReturningGeneratedId",
            "fullName": "SQLite INSERT RETURNING generated id migration",
            "module": "language.guide",
            "moduleName": "language.guide",
            "summary": SQLITE_GENERATED_ID_RETURNING_GUIDANCE["summary"],
            "terms": SQLITE_GENERATED_ID_RETURNING_GUIDANCE["searchTerms"],
            "usage": [
                "Use this for SS3639, sqlite.lastInsertRowId, last_insert_rowid(), generated row ids, and activity-log inserts.",
                "The pattern is native/webServer-safe because the id flows through the INSERT statement result row, not connection-global state.",
                "Use sem docs get sqlite.lastInsertRowId --json and copy usage.migration.rows for the complete row group.",
                *SQLITE_GENERATED_ID_RETURNING_GUIDANCE["lifetimeRules"],
                *SQLITE_GENERATED_ID_RETURNING_GUIDANCE["transactionRules"],
            ],
            "exampleRows": [
                *SQLITE_GENERATED_ID_RETURNING_GUIDANCE["sqlRows"],
                *SQLITE_GENERATED_ID_RETURNING_GUIDANCE["rows"],
            ],
            "location": {
                "path": str(optimization_guide_path.resolve()),
                "line": 397,
            },
        },
    ]


def _build_context_payload(path: Path) -> dict:
    semlint = _load_semlint_module()
    requested = path
    build_tape = _find_build_tape(path)
    source_for_facts = build_tape if build_tape is not None else path
    facts = semlint.parse_file(source_for_facts) if source_for_facts.is_file() else None
    source_files, _errors = _symbol_source_files(path)
    syntax_counts = _syntax_status_counts()
    project = {
        "requestedPath": str(requested.resolve()),
        "projectRoot": str(build_tape.parent.resolve()) if build_tape else "",
        "buildTape": str(build_tape.resolve()) if build_tape else "",
        "buildProject": _row_value(facts, "buildProject") if facts else "",
        "projectName": _row_value(facts, "project") if facts else "",
        "modulePath": _row_value(facts, "modulePath", 1) if facts else "",
        "sourceRoots": [],
        "mainFile": _row_value(facts, "mainFile", 1) if facts else "",
        "mainOperation": _row_value(facts, "mainOperation", 1) if facts else "",
        "targetRuntime": _row_value(facts, "targetRuntime", 1) if facts else "",
        "asyncRuntime": _row_value(facts, "asyncRuntime", 1) if facts else "",
        "guiBackend": _row_value(facts, "guiBackend", 1) if facts else "",
        "targets": _row_values(facts, "target") if facts else [],
        "nativeOutput": _row_value(facts, "nativeOutput", 1) if facts else "",
    }
    if facts:
        project["sourceRoots"] = _row_values(facts, "sourceRoot", 1)
    return {
        "schemaVersion": "sem.context.v1",
        "tool": {"name": "sem", "version": VERSION},
        "project": project,
        "sourceFiles": [str(source.resolve()) for source in source_files],
        "tools": {
            "compiler": {
                "path": str((ROOT / "compiler" / "semsc.py").resolve()),
                "version": VERSION,
            },
            "linter": {
                "path": str((ROOT / "linter" / "semlint.py").resolve()),
                "version": VERSION,
            },
            "formatter": {
                "path": str((ROOT / "formatter" / "semfmt.py").resolve()),
                "version": VERSION,
            },
        },
        "runtimeFeatureFlags": _runtime_feature_flags(),
        "supportedSyntax": {
            "inventoryPath": str(SYNTAX_INVENTORY_PATH.resolve()),
            "statusCounts": syntax_counts,
            "languageModes": ["strictExecutable", "refinedSyntax", "permissiveExecutable"],
            "schemaVersion": SYNTAX_PAYLOAD_VERSION,
            "normalCommandsAutoMigrateOldSyntax": False,
            "currentRows": {
                "argument": "argument CALL PARAM TYPE VALUE",
                "bind": ["bind value NAME TYPE CALL", "bind ok NAME TYPE CALL", "bind error NAME TYPE CALL"],
                "branch": [
                    "branch if condition CONDITION target LABEL",
                    "branch error source CALL target LABEL",
                    "branch else target LABEL",
                ],
                "jump": "jump target LABEL",
                "return": ["return value VALUE", "return ok VALUE", "return error VALUE", "return void"],
                "ignore": [
                    "ignore value source CALL type TYPE",
                    "ignore ok source CALL type TYPE",
                    "ignore error source CALL",
                    "ignore void source CALL",
                ],
                "input": "input operation OP NAME TYPE",
                "output": "output operation OP TYPE",
                "authority": "authority OP ACTION PATH",
            },
        },
        "knownDeferredFeatures": {
            "partialSyntaxRows": syntax_counts["partial"],
            "notImplementedSyntaxRows": syntax_counts["notImplemented"],
        },
    }


def _symbol_source_files(path: Path) -> tuple[list[Path], list[str]]:
    semlint = _load_semlint_module()
    errors: list[str] = []
    requested = path.resolve()
    build_tape = _find_build_tape(path)
    if requested.is_file() and requested.name.lower() not in {"build.sem", "build.sscript"}:
        return [requested], errors
    if build_tape is None:
        return ([requested] if requested.is_file() else []), errors

    source_files = [build_tape.resolve()]
    try:
        build_facts = semlint.parse_file(build_tape)
        registered, main_files = semlint._collect_registered_modules(build_facts)
        for module_name, (_line, raw_path) in sorted(registered.items()):
            resolved = semlint._resolve_registered_module_source(
                module_name, raw_path, build_tape, main_files)
            if resolved is None:
                errors.append(f"registered module {module_name} did not resolve")
                continue
            source_files.append(Path(resolved).resolve())
    except (OSError, RuntimeError) as exc:
        errors.append(str(exc))

    deduped = []
    seen = set()
    for source in source_files:
        if source in seen:
            continue
        seen.add(source)
        deduped.append(source)
    return deduped, errors


def _requested_surface_kind(path: Path) -> str:
    requested = path.resolve()
    if requested.is_dir():
        return "directory"
    if requested.is_file() and requested.name.lower() in {"build.sem", "build.sscript"}:
        return "build-tape"
    if requested.is_file():
        return "source-file"
    return "path"


def _scope_label_from_sources(source_files: list[str] | list[Path]) -> str:
    return "project" if len(source_files) > 1 else "file"


def _payload_scope(path: Path, **scopes: str) -> dict:
    build_tape = _find_build_tape(path)
    payload = {
        "requestedSurface": _requested_surface_kind(path),
        "requestedPath": str(path.resolve()),
        "buildTape": str(build_tape.resolve()) if build_tape else "",
    }
    for name, value in scopes.items():
        if value:
            payload[name] = value
    return payload


def _surface_shift(path: Path, from_scope: str, to_scope: str, *, reason: str) -> dict:
    build_tape = _find_build_tape(path)
    requested = path.resolve()
    if build_tape is None or not requested.is_file() or requested.name.lower() in {"build.sem", "build.sscript"}:
        return {}
    if not from_scope or not to_scope or from_scope == to_scope:
        return {}
    return {
        "from": from_scope,
        "to": to_scope,
        "reason": reason,
        "buildTape": str(build_tape.resolve()),
    }


def _source_ref(line) -> dict:
    payload = _line_payload(line)
    payload["raw"] = line.raw
    return payload


def _operation_rows(operation, verb: str) -> list:
    return [
        source_line for source_line in operation.lines
        if source_line.tokens and source_line.verb == verb
    ]


def _signature_input_payload(source_line, operation) -> dict | None:
    args = source_line.args
    if source_line.verb != "input":
        return None
    if len(args) >= 4 and args[0] == "operation" and args[1] == operation.name:
        return {
            "subjectKind": args[0],
            "name": args[2],
            "type": args[3],
            "location": _line_payload(source_line),
        }
    if len(args) >= 3 and args[0] == operation.name:
        return {
            "subjectKind": "operation",
            "name": args[1],
            "type": args[2],
            "location": _line_payload(source_line),
        }
    return None


def _signature_output_payload(source_line, operation) -> dict | None:
    args = source_line.args
    if source_line.verb != "output":
        return None
    if len(args) >= 3 and args[0] == "operation" and args[1] == operation.name:
        return {
            "subjectKind": args[0],
            "type": args[2],
            "values": args[2:],
            "location": _line_payload(source_line),
        }
    if len(args) >= 2 and args[0] == operation.name:
        return {
            "subjectKind": "operation",
            "type": args[1],
            "values": args[1:],
            "location": _line_payload(source_line),
        }
    return None


def _effect_payload(source_line, operation) -> dict | None:
    args = source_line.args
    if source_line.verb == "effect" and len(args) >= 3 and args[0] == operation.name:
        return {
            "action": args[1],
            "path": args[2],
            "location": _line_payload(source_line),
        }
    return None


def _authority_payload(source_line, operation) -> dict | None:
    args = source_line.args
    if source_line.verb != "authority" or len(args) < 3 or args[0] != operation.name:
        return None
    if args[1] in AUTHORITY_ACTIONS:
        action, path = args[1], args[2]
    else:
        path, action = args[1], args[2]
    return {
        "action": action,
        "path": path,
        "location": _line_payload(source_line),
    }


def _call_reference_from_line(source_line) -> str:
    args = source_line.args
    if not args:
        return ""
    verb = source_line.verb
    if verb in {"argument", "run", "start", "await", "case", "startInGroup", "timeout", "cancelOn"}:
        return args[0]
    if verb == "arg":
        return args[0]
    if verb == "bind":
        if len(args) >= 4 and args[0] in {"value", "ok", "error"}:
            return args[3]
        if len(args) >= 3:
            return args[2]
    if verb in {"bindOk", "bindError"} and len(args) >= 3:
        return args[2]
    if verb == "ignore":
        if len(args) >= 3 and args[0] in CALL_DISPOSITION_VARIANTS and args[1] == "source":
            return args[2]
    if verb in {"ignoreOk", "ignoreValue"}:
        return args[0]
    if verb == "branch" and len(args) >= 5 and args[0] == "error" and args[1] == "source":
        return args[2]
    if verb == "branchIfError":
        return args[0]
    return ""


def _bind_variant_payload(source_line) -> tuple[str, dict] | None:
    args = source_line.args
    if source_line.verb == "bind":
        if len(args) >= 4 and args[0] in {"value", "ok", "error"}:
            return args[0], {
                "name": args[1],
                "type": args[2],
                "source": args[3],
                "location": _line_payload(source_line),
            }
        if len(args) >= 3:
            return "value", {
                "name": args[0],
                "type": args[1],
                "source": args[2],
                "location": _line_payload(source_line),
            }
    if source_line.verb == "bindOk" and len(args) >= 3:
        return "ok", {
            "name": args[0],
            "type": args[1],
            "source": args[2],
            "location": _line_payload(source_line),
        }
    if source_line.verb == "bindError" and len(args) >= 3:
        return "error", {
            "name": args[0],
            "type": args[1],
            "source": args[2],
            "location": _line_payload(source_line),
        }
    return None


def _ignore_variant_payload(source_line) -> tuple[str, dict] | None:
    args = source_line.args
    if source_line.verb == "ignore" and len(args) >= 3:
        variant = args[0]
        if variant in CALL_DISPOSITION_VARIANTS and args[1] == "source":
            payload = {
                "source": args[2],
                "location": _line_payload(source_line),
            }
            if len(args) >= 5 and args[3] == "type":
                payload["type"] = args[4]
            return variant, payload
    if source_line.verb == "ignoreOk" and len(args) >= 1:
        payload = {"source": args[0], "location": _line_payload(source_line)}
        if len(args) >= 2:
            payload["type"] = args[1]
        return "ok", payload
    if source_line.verb == "ignoreValue" and len(args) >= 1:
        variant = "void" if len(args) >= 2 and args[1] == "Void" else "value"
        payload = {"source": args[0], "location": _line_payload(source_line)}
        if variant == "value" and len(args) >= 2:
            payload["type"] = args[1]
        return variant, payload
    return None


def _branch_payload(source_line) -> dict | None:
    args = source_line.args
    if source_line.verb == "branch":
        if len(args) >= 5 and args[0] == "if" and args[1] == "condition" and args[3] == "target":
            return {
                "kind": "branch if",
                "condition": args[2],
                "target": args[4],
                "location": _line_payload(source_line),
            }
        if len(args) >= 5 and args[0] == "error" and args[1] == "source" and args[3] == "target":
            return {
                "kind": "branch error",
                "source": args[2],
                "target": args[4],
                "location": _line_payload(source_line),
            }
        if len(args) >= 3 and args[0] == "else" and args[1] == "target":
            return {
                "kind": "branch else",
                "target": args[2],
                "location": _line_payload(source_line),
            }
        if len(args) >= 1:
            return {
                "kind": "jump",
                "target": args[0],
                "location": _line_payload(source_line),
            }
    if source_line.verb == "branchIf" and len(args) >= 2:
        return {
            "kind": "branch if",
            "condition": args[0],
            "target": args[1],
            "location": _line_payload(source_line),
        }
    if source_line.verb == "branchIfError" and len(args) >= 2:
        return {
            "kind": "branch error",
            "source": args[0],
            "target": args[1],
            "location": _line_payload(source_line),
        }
    if source_line.verb == "jump" and len(args) >= 2 and args[0] == "target":
        return {
            "kind": "jump",
            "target": args[1],
            "location": _line_payload(source_line),
        }
    return None


def _return_payload(source_line) -> dict | None:
    args = source_line.args
    if source_line.verb == "return" and args and args[0] in CALL_DISPOSITION_VARIANTS:
        payload = {
            "variant": args[0],
            "location": _line_payload(source_line),
        }
        if args[0] != "void" and len(args) >= 2:
            payload["value"] = args[1]
        return payload
    legacy_variants = {
        "returnValue": "value",
        "returnOk": "ok",
        "returnError": "error",
        "returnVoid": "void",
    }
    if source_line.verb in legacy_variants:
        payload = {
            "variant": legacy_variants[source_line.verb],
            "location": _line_payload(source_line),
        }
        if payload["variant"] != "void" and args:
            payload["value"] = args[0]
        return payload
    return None


def _operation_call_payloads(operation) -> list[dict]:
    calls: dict[str, dict] = {}
    order: dict[str, int] = {}

    for source_line in operation.lines:
        if not source_line.tokens:
            continue
        args = source_line.args
        if source_line.verb == "call" and len(args) >= 2:
            calls[args[0]] = {
                "name": args[0],
                "target": args[1],
                "location": _line_payload(source_line),
                "arguments": [],
                "disposition": {
                    "run": False,
                    "start": False,
                    "await": False,
                    "bind": {variant: [] for variant in ("value", "ok", "error")},
                    "ignore": {variant: [] for variant in CALL_DISPOSITION_VARIANTS},
                    "branchError": [],
                },
            }
            order[args[0]] = source_line.number

    for source_line in operation.lines:
        if not source_line.tokens:
            continue
        args = source_line.args
        call_name = _call_reference_from_line(source_line)
        call_payload = calls.get(call_name)
        if call_payload is None:
            continue
        if source_line.verb == "argument" and len(args) >= 4:
            call_payload["arguments"].append({
                "parameter": args[1],
                "type": args[2],
                "value": args[3],
                "location": _line_payload(source_line),
            })
        elif source_line.verb == "arg" and len(args) >= 3:
            call_payload["arguments"].append({
                "parameter": args[1],
                "type": "",
                "value": args[2],
                "location": _line_payload(source_line),
            })
        elif source_line.verb in {"run", "start", "await"}:
            call_payload["disposition"][source_line.verb] = True
        elif source_line.verb == "case":
            call_payload["disposition"]["await"] = True
        else:
            bind_payload = _bind_variant_payload(source_line)
            if bind_payload is not None:
                variant, payload = bind_payload
                call_payload["disposition"]["bind"][variant].append(payload)
                continue
            ignore_payload = _ignore_variant_payload(source_line)
            if ignore_payload is not None:
                variant, payload = ignore_payload
                call_payload["disposition"]["ignore"][variant].append(payload)
                continue
            branch_payload = _branch_payload(source_line)
            if branch_payload is not None and branch_payload["kind"] == "branch error":
                call_payload["disposition"]["branchError"].append(branch_payload)

    return [
        calls[name]
        for name in sorted(calls, key=lambda item: order.get(item, 0))
    ]


def _operation_symbol(operation, semlint, facts=None) -> dict:
    inputs = []
    outputs = []
    effects = []
    capabilities = []
    authorities = []
    control_flow = []
    returns = []

    for source_line in operation.lines:
        if not source_line.tokens:
            continue
        args = source_line.args
        input_payload = _signature_input_payload(source_line, operation)
        output_payload = _signature_output_payload(source_line, operation)
        effect_payload = _effect_payload(source_line, operation)
        authority_payload = _authority_payload(source_line, operation)
        branch_payload = _branch_payload(source_line)
        return_payload = _return_payload(source_line)
        if input_payload is not None:
            inputs.append(input_payload)
        elif output_payload is not None:
            outputs.append(output_payload)
        elif effect_payload is not None:
            effects.append(effect_payload)
        elif source_line.verb == "useCapability" and len(args) >= 2 and args[0] == operation.name:
            capabilities.append({
                "name": args[1],
                "location": _line_payload(source_line),
            })
        elif authority_payload is not None:
            authorities.append(authority_payload)
        elif branch_payload is not None:
            control_flow.append(branch_payload)
        elif return_payload is not None:
            returns.append(return_payload)
    if facts is not None:
        for source_line in facts.lines:
            authority_payload = _authority_payload(source_line, operation)
            if authority_payload is not None and authority_payload not in authorities:
                authorities.append(authority_payload)

    return {
        "name": operation.name,
        "location": _line_payload(operation.line),
        "inputs": inputs,
        "outputs": outputs,
        "effects": effects,
        "capabilities": capabilities,
        "authorities": authorities,
        "calls": _operation_call_payloads(operation),
        "controlFlow": control_flow,
        "returns": returns,
    }


def _enum_case_value_payload(raw_value, next_value: int) -> tuple[dict, int]:
    payload = {}
    if raw_value is not None:
        payload["rawValue"] = raw_value
    try:
        value = next_value if raw_value is None else int(str(raw_value), 0)
    except (TypeError, ValueError):
        value = next_value
    payload["value"] = value
    return payload, value + 1


def _enum_symbol_payloads(facts) -> list[dict]:
    enums: dict[str, dict] = {}
    order: list[str] = []
    next_values: dict[str, int] = {}
    for source_line in facts.lines:
        if not source_line.tokens or source_line.verb != "enum" or not source_line.args:
            continue
        enum_name = source_line.args[0]
        repr_type = "Int32"
        if len(source_line.args) >= 3 and source_line.args[1] == "repr":
            repr_type = source_line.args[2]
        if enum_name not in enums:
            order.append(enum_name)
        enums[enum_name] = {
            "name": enum_name,
            "repr": repr_type,
            "location": _line_payload(source_line),
            "cases": [],
        }
        next_values[enum_name] = 0

    for source_line in facts.lines:
        if (not source_line.tokens or source_line.verb != "enumCase"
                or len(source_line.args) < 2):
            continue
        enum_name = source_line.args[0]
        enum_payload = enums.get(enum_name)
        if enum_payload is None:
            continue
        raw_value = source_line.args[2] if len(source_line.args) >= 3 else None
        value_payload, next_value = _enum_case_value_payload(
            raw_value, next_values.get(enum_name, 0))
        next_values[enum_name] = next_value
        enum_payload["cases"].append({
            "name": source_line.args[1],
            **value_payload,
            "location": _line_payload(source_line),
        })
    return [enums[name] for name in order]


def _symbol_payload_for_file(path: Path, semlint) -> tuple[dict, list[dict]]:
    facts = semlint.parse_file(path)
    operations = [
        _operation_symbol(operation, semlint, facts)
        for operation in sorted(facts.operations.values(), key=lambda item: item.line.number)
    ]
    routes = [
        {
            "server": route.server,
            "method": route.method,
            "path": route.path,
            "handler": route.handler,
            "location": _line_payload(route.line),
        }
        for route in facts.routes
    ]
    unresolved = []
    operation_names = set(facts.operations)
    for operation in facts.operations.values():
        calls = {
            source_line.args[0]
            for source_line in operation.lines
            if source_line.tokens and source_line.verb == "call" and len(source_line.args) >= 2
        }
        call_targets = {
            source_line.args[0]: source_line.args[1]
            for source_line in operation.lines
            if source_line.tokens and source_line.verb == "call" and len(source_line.args) >= 2
        }
        for source_line in operation.lines:
            if not source_line.tokens or not source_line.args:
                continue
            maybe_call = _call_reference_from_line(source_line)
            if maybe_call and maybe_call not in calls:
                unresolved.append({
                    "kind": "callAttachment",
                    "operation": operation.name,
                    "name": maybe_call,
                    "location": _line_payload(source_line),
                })
        for call_name, call_target in call_targets.items():
            if "." not in call_target and call_target not in operation_names:
                unresolved.append({
                    "kind": "localCallTarget",
                    "operation": operation.name,
                    "name": call_target,
                    "location": _line_payload(next(
                        line for line in operation.lines
                        if line.tokens and line.verb == "call" and line.args[0] == call_name
                    )),
                })
    file_payload = {
        "path": str(path.resolve()),
        "module": _row_value(facts, "module"),
        "imports": [
            {
                "module": item.module_name,
                "alias": item.alias or "",
                "syntax": item.syntax,
                "location": _line_payload(item.line),
            }
            for item in facts.module_imports
        ],
        "operations": operations,
        "enums": _enum_symbol_payloads(facts),
        "routes": routes,
    }
    return file_payload, unresolved


def _symbol_graph_payload(path: Path) -> dict:
    semlint = _load_semlint_module()
    source_files, errors = _symbol_source_files(path)
    files = []
    unresolved = []
    for source in source_files:
        if not source.exists() or source.suffix.lower() not in {".sem", ".sscript"}:
            continue
        try:
            file_payload, file_unresolved = _symbol_payload_for_file(source, semlint)
            files.append(file_payload)
            unresolved.extend(file_unresolved)
        except OSError as exc:
            errors.append(str(exc))
    operation_locations = {}
    for file_payload in files:
        for operation in file_payload["operations"]:
            operation_locations.setdefault(operation["name"], {
                "path": file_payload["path"],
                "location": operation["location"],
            })
    for file_payload in files:
        for route in file_payload["routes"]:
            target = operation_locations.get(route["handler"])
            route["handlerFile"] = target["path"] if target is not None else ""
            route["handlerLocation"] = target["location"] if target is not None else {}
    return {
        "schemaVersion": "sem.symbols.v1",
        "tool": {"name": "sem", "version": VERSION},
        "syntax": {
            "schemaVersion": SYNTAX_PAYLOAD_VERSION,
            "normalCommandsAutoMigrateOldSyntax": False,
            "rowForms": [
                "argument CALL PARAM TYPE VALUE",
                "bind value NAME TYPE CALL",
                "bind ok NAME TYPE CALL",
                "bind error NAME TYPE CALL",
                "branch if condition CONDITION target LABEL",
                "branch error source CALL target LABEL",
                "branch else target LABEL",
                "jump target LABEL",
                "return value VALUE",
                "return ok VALUE",
                "return error VALUE",
                "return void",
                "ignore value source CALL type TYPE",
                "ignore ok source CALL type TYPE",
                "ignore error source CALL",
                "ignore void source CALL",
                "input operation OP NAME TYPE",
                "output operation OP TYPE",
                "authority OP ACTION PATH",
            ],
        },
        "sourceFiles": [str(source.resolve()) for source in source_files],
        "files": files,
        "summary": {
            "fileCount": len(files),
            "operationCount": sum(len(file["operations"]) for file in files),
            "callCount": sum(
                len(operation["calls"])
                for file in files
                for operation in file["operations"]
            ),
            "routeCount": sum(len(file["routes"]) for file in files),
            "enumCount": sum(len(file.get("enums", [])) for file in files),
            "enumCaseCount": sum(
                len(enum.get("cases", []))
                for file in files
                for enum in file.get("enums", [])
            ),
            "unresolvedReferenceCount": len(unresolved),
        },
        "unresolvedReferences": unresolved,
        "errors": errors,
    }


def _docs_std_root(std_root: Path | None = None) -> Path:
    if std_root is not None:
        return std_root.resolve()
    for env_name in ("SEMANTICSCRIPT_STD_PATH", "SEMSC_STD_PATH"):
        raw_value = os.environ.get(env_name, "")
        for part in raw_value.split(os.pathsep):
            if part.strip():
                return Path(part).expanduser().resolve()
    return (ROOT / "std").resolve()


def _std_module_short_name(module_name: str) -> str:
    if module_name.startswith("standard."):
        return module_name.split(".", 1)[1]
    if module_name.startswith("compiler."):
        return module_name.split(".", 1)[1]
    return module_name


def _std_module_matches(module_name: str, requested: str) -> bool:
    if not requested:
        return True
    normalized = requested.strip()
    if not normalized:
        return True
    short_name = _std_module_short_name(module_name)
    return normalized in {module_name, short_name, f"standard.{normalized}", f"compiler.{normalized}"}


def _std_module_path_matches(path: Path, requested: str) -> bool:
    if not requested or not requested.strip():
        return True
    normalized = requested.strip()
    short_name = path.parent.name
    return normalized in {short_name, f"standard.{short_name}"}


def _std_main_files(std_root: Path) -> list[Path]:
    if not std_root.exists():
        return []
    return sorted(
        path.resolve()
        for path in std_root.glob("*/main.sem")
        if path.is_file()
    )


def _is_comment_line(source_line) -> bool:
    return source_line.raw.strip().startswith("#")


def _comment_body(source_line) -> str:
    stripped = source_line.raw.strip()
    if not stripped.startswith("#"):
        return ""
    return stripped[1:].strip()


def _preceding_comment_block(lines: list, target_line) -> list:
    target_index = -1
    for index, source_line in enumerate(lines):
        if source_line is target_line:
            target_index = index
            break
        if source_line.number == target_line.number and Path(source_line.path) == Path(target_line.path):
            target_index = index
            break
    if target_index <= 0:
        return []
    block = []
    index = target_index - 1
    while index >= 0 and not lines[index].raw.strip():
        index -= 1
    while index >= 0:
        source_line = lines[index]
        if not source_line.raw.strip():
            break
        if not _is_comment_line(source_line):
            break
        block.append(source_line)
        index -= 1
    return list(reversed(block))


def _typed_comment_payloads(lines: list) -> list[dict]:
    comments: list[dict] = []
    current: dict | None = None
    tag_pattern = re.compile(r"^([A-Za-z][A-Za-z0-9_-]*):\s*(.*)$")
    for source_line in lines:
        body = _comment_body(source_line)
        match = tag_pattern.match(body)
        if match and match.group(1) in STD_DOC_COMMENT_TAGS:
            current = {
                "tag": match.group(1),
                "text": match.group(2).strip(),
                "location": _line_payload(source_line),
            }
            comments.append(current)
            continue
        if current is None:
            continue
        continuation = body.strip()
        if not continuation or continuation.startswith("===") or continuation.startswith("---"):
            continue
        current["text"] = f"{current['text']} {continuation}".strip()
    return comments


def _comments_by_tag(comments: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for comment in comments:
        grouped.setdefault(comment["tag"], []).append(comment)
    return grouped


def _operation_text_row(source_line, operation_name: str) -> dict | None:
    verb = source_line.verb
    args = source_line.args
    if verb in {"purpose", "invariant"}:
        if len(args) >= 3 and args[0] == "operation" and args[1] == operation_name:
            return {
                "tag": verb,
                "text": " ".join(args[2:]).strip(),
                "location": _line_payload(source_line),
            }
        if len(args) >= 2 and args[0] == operation_name:
            return {
                "tag": verb,
                "text": " ".join(args[1:]).strip(),
                "location": _line_payload(source_line),
            }
    if verb == "failure" and len(args) >= 3 and args[0] == operation_name:
        return {
            "tag": verb,
            "name": args[1],
            "text": " ".join(args[2:]).strip(),
            "location": _line_payload(source_line),
        }
    if verb in {"warning", "guarantee", "security", "timing", "observability"} and len(args) >= 2 and args[0] == operation_name:
        return {
            "tag": verb,
            "text": " ".join(args[1:]).strip(),
            "location": _line_payload(source_line),
        }
    return None


def _operation_text_rows(operation) -> dict[str, list[dict]]:
    rows: dict[str, list[dict]] = {}
    for source_line in operation.lines:
        if not source_line.tokens:
            continue
        payload = _operation_text_row(source_line, operation.name)
        if payload is not None:
            rows.setdefault(payload["tag"], []).append(payload)
    return rows


def _operation_memory_rows(operation) -> list[dict]:
    rows = []
    for source_line in operation.lines:
        if source_line.verb == "memory" and len(source_line.args) >= 2 and source_line.args[0] == operation.name:
            rows.append({
                "policy": source_line.args[1:],
                "text": " ".join(source_line.args[1:]),
                "location": _line_payload(source_line),
            })
    return rows


def _operation_runtime_rows(facts, operation) -> dict[str, list[dict]]:
    rows: dict[str, list[dict]] = {
        "operationBody": [],
        "runtimeBinding": [],
        "runtimeBindingPrecondition": [],
        "runtimeBindingFailure": [],
    }
    for source_line in facts.lines:
        if source_line.verb not in rows or len(source_line.args) < 2 or source_line.args[0] != operation.name:
            continue
        rows[source_line.verb].append({
            "values": source_line.args[1:],
            "text": " ".join(source_line.args[1:]),
            "location": _line_payload(source_line),
        })
    return rows


def _operation_exports(facts, module_name: str, operation_name: str) -> list[dict]:
    exports = []
    for source_line in facts.lines:
        if source_line.verb != "exportOperation" or len(source_line.args) < 2:
            continue
        if source_line.args[0] == module_name and source_line.args[1] == operation_name:
            exports.append({
                "module": source_line.args[0],
                "name": source_line.args[1],
                "location": _line_payload(source_line),
            })
    return exports


def _exported_names(facts, verb: str, module_name: str) -> set[str]:
    names = set()
    for source_line in facts.lines:
        if source_line.verb == verb and len(source_line.args) >= 2 and source_line.args[0] == module_name:
            names.add(source_line.args[1])
    return names


def _capability_details(facts, module_name: str, capabilities: list[dict]) -> list[dict]:
    if facts is None:
        facts = argparse.Namespace(lines=[], capabilities={})
    exported_capabilities = _exported_names(facts, "exportCapability", module_name)
    details = []
    for capability_ref in capabilities:
        name = capability_ref["name"]
        fact = facts.capabilities.get(name)
        payload = {
            "name": name,
            "exported": name in exported_capabilities,
            "referenceLocation": capability_ref.get("location", {}),
        }
        if fact is not None:
            payload.update({
                "resource": fact.effect_path,
                "action": fact.access,
                "declarationLocation": _line_payload(fact.line),
            })
        details.append(payload)
    return details


NATIVE_LINKABLE_STDLIB_OPERATION_TARGETS: frozenset[str] = frozenset({
    "standard.bcrypt.issueSessionToken",
    "standard.bcrypt.issueCsrfToken",
})


def _operation_native_linkability(
    runtime_rows: dict[str, list[dict]],
    module_name: str = "",
    operation_name: str = "",
) -> dict:
    """Tell an agent whether a standard-library operation links in a native /
    webServer build, BEFORE they design around it.

    Native and webServer targets do not link the SemanticScript standard
    library object; only native runtime intrinsics (sqlite.*, json.*, http.*,
    math.* / memory.* / pointer.* primitives, bcrypt.*) and operations that
    lower to a runtime binding are callable there. A standard-library operation
    with an ordinary SemanticScript body (e.g. convert.convertSignedInt64ToString)
    compiles and `check`s clean but fails the native build loudly with SSCG002.
    The dashboard field log ranked discovering this late as a top time-sink.
    """
    lowers_to_binding = bool(runtime_rows.get("runtimeBinding")) or any(
        "runtimeBinding" in row.get("values", []) or row.get("text") == "runtimeBinding"
        for row in runtime_rows.get("operationBody", [])
    )
    if lowers_to_binding:
        return {
            "linksInNativeBuild": True,
            "note": "Lowers to a native runtime binding (runtimeBinding); links "
                    "in native and webServer builds.",
        }
    qualified_operation = f"{module_name}.{operation_name}" if module_name and operation_name else ""
    if qualified_operation in NATIVE_LINKABLE_STDLIB_OPERATION_TARGETS:
        return {
            "linksInNativeBuild": True,
            "note": "Compiler-owned native runtime lowering exists for this "
                    "standard-library operation target; it links in native and "
                    "webServer builds.",
        }
    return {
        "linksInNativeBuild": False,
        "note": "Standard-library operation with a SemanticScript body. Native "
                "and webServer builds link only native intrinsics and "
                "compiler-lowered DSLs, so calling this from a native/webServer "
                "target fails the build with SSCG002 (it works under console/JIT "
                "builds). Prefer a native intrinsic (sqlite.*, json.*, http.*, "
                "math.*, memory.*, bcrypt.*) or a lowered DSL (sql body / "
                "jsonBody / html template) on those targets.",
    }


def _operation_visibility(operation, exports: list[dict], runtime_rows: dict[str, list[dict]]) -> dict:
    runtime_internal = bool(runtime_rows.get("runtimeBinding") or runtime_rows.get("runtimeBindingPrecondition"))
    operation_body_runtime = any(
        "runtimeBinding" in row.get("values", []) or row.get("text") == "runtimeBinding"
        for row in runtime_rows.get("operationBody", [])
    )
    name_internal = operation.name.endswith("Native") or operation.name.startswith("_")
    internal = not exports and (runtime_internal or operation_body_runtime or name_internal)
    tier = "exported" if exports else ("internal" if internal else "helper")
    return {
        "exported": bool(exports),
        "internal": internal,
        "public": not internal,
        "apiTier": tier,
        "reason": "exportOperation" if exports else ("runtime-internal" if internal else "operation"),
    }


def _operation_agent_warnings(
    visibility: dict,
    capability_details: list[dict],
    native_linkability: dict | None = None,
    module_name: str = "",
    operation_name: str = "",
) -> list[str]:
    warnings = []
    if native_linkability is not None and not native_linkability.get("linksInNativeBuild", True):
        # Keep this string free of call-target tokens (the intrinsic list lives
        # in nativeLinkability.note, which is NOT indexed for search). agentWarnings
        # IS part of the FTS search text, so naming specific targets here would
        # make every library op match a search for that target.
        warnings.append(
            "Not linkable in native or webServer builds (SSCG002): standard-library "
            "operation with a SemanticScript body. On those targets use a native "
            "runtime intrinsic or a compiler-lowered DSL instead; available under "
            "interpreter and just-in-time builds."
        )
    if visibility.get("apiTier") == "helper":
        warnings.append("Unexported helper API: prefer exported standard-library operations when one exists.")
    if module_name == "standard.map" and operation_name.startswith("map."):
        warnings.append(
            "standard.map is structural bookkeeping only: it tracks entry counts, "
            "capacity, and key-present facts, but it does not store keys/values "
            "or provide executable put/get container operations."
        )
    hidden_capabilities = [detail["name"] for detail in capability_details if not detail.get("exported", False)]
    if hidden_capabilities:
        warnings.append(
            "Uses non-exported capability rows; callers may need explicit authority or a higher-level exported wrapper: "
            + ", ".join(hidden_capabilities)
        )
    return warnings


def _signature_text(inputs: list[dict], outputs: list[dict]) -> str:
    input_text = ", ".join(f"{item['name']}:{item['type']}" for item in inputs)
    output_values = []
    for output in outputs:
        if output.get("values"):
            output_values.append(" ".join(output["values"]))
        elif output.get("type"):
            output_values.append(output["type"])
    output_text = " | ".join(output_values) if output_values else "Void"
    return f"({input_text}) -> {output_text}"


def _first_text(items: list[dict]) -> str:
    for item in items:
        text = item.get("text", "").strip()
        if text:
            return text
    return ""


def _metadata_text(text_rows: dict[str, list[dict]]) -> str:
    parts = []
    for tag in ("purpose", "invariant", "warning", "guarantee", "failure", "security"):
        parts.extend(row.get("text", "") for row in text_rows.get(tag, []))
    return " ".join(part for part in parts if part).strip()


def _summary_from_doc(
    comments_by_tag: dict[str, list[dict]],
    text_rows: dict[str, list[dict]],
    summary_tag: str,
) -> tuple[str, str]:
    if summary_tag == "purpose":
        purpose = _first_text(text_rows.get("purpose", []))
        if purpose:
            return purpose, "purpose"
    else:
        tagged = _first_text(comments_by_tag.get(summary_tag, []))
        if tagged:
            return tagged, f"comment:{summary_tag}"
        row_text = _first_text(text_rows.get(summary_tag, []))
        if row_text:
            return row_text, summary_tag
    for tag, source in (("purpose", "purpose"), ("rationale", "comment:rationale"), ("invariant", "comment:invariant")):
        if tag == "purpose":
            text = _first_text(text_rows.get(tag, []))
        else:
            text = _first_text(comments_by_tag.get(tag, []))
        if text:
            return text, source
    return "", ""


def _result_value_name(operation_name: str) -> str:
    return f"{operation_name}Result"


def _call_name(operation_name: str) -> str:
    return f"{operation_name}Call"


def _target_call_base_name(target: str) -> str:
    parts = [part for part in target.split(".") if part]
    if len(parts) > 1:
        parts = parts[1:]
    if not parts:
        return "target"
    name = re.sub(r"[^A-Za-z0-9]", "", parts[0])
    for part in parts[1:]:
        cleaned = re.sub(r"[^A-Za-z0-9]", "", part)
        if cleaned:
            name += cleaned[:1].upper() + cleaned[1:]
    if not name:
        return "target"
    return name[:1].lower() + name[1:]


def _usage_call_template_for_target(target: str, call_base_name: str, inputs: list[dict], outputs: list[dict]) -> dict:
    call_name = _call_name(call_base_name)
    result_name = _result_value_name(call_base_name)
    error_name = f"{call_base_name}Error"
    argument_rows = [
        f"argument {call_name} {item['name']} {item['type']} <{item['name']}>"
        for item in inputs
    ]
    rows = [f"call {call_name} {target}", *argument_rows, f"run {call_name}"]
    result_rows = []
    output = outputs[0] if outputs else {}
    output_type = output.get("type", "") if output else "Void"
    output_values = output.get("values", []) if output else []
    result_value_name = result_name if output_type and output_type != "Void" else ""
    if output_values and output_values[0] == "Result":
        ok_type = output_values[1] if len(output_values) > 1 else "OK_TYPE"
        error_type = output_values[2] if len(output_values) > 2 else "ERROR_TYPE"
        if ok_type == "Void":
            result_rows.append(f"ignore void source {call_name}")
            result_value_name = ""
        else:
            result_rows.append(f"bind ok {result_name} {ok_type} {call_name}")
            result_value_name = result_name
    elif output_type and output_type != "Void":
        result_rows.append(f"bind value {result_name} {output_type} {call_name}")
        result_value_name = result_name
    else:
        result_rows.append(f"ignore void source {call_name}")
    return {
        "target": target,
        "callName": call_name,
        "errorName": error_name if output_values and output_values[0] == "Result" else "",
        "errorType": error_type if output_values and output_values[0] == "Result" else "",
        "resultName": result_value_name,
        "rows": [*rows, *result_rows],
        "argumentRows": argument_rows,
        "resultRows": result_rows,
        "templateScope": "call-and-bind-only",
    }


def _usage_call_template(module_short_name: str, operation_name: str, inputs: list[dict], outputs: list[dict]) -> dict:
    target = f"{module_short_name}.{operation_name}"
    return _usage_call_template_for_target(target, operation_name, inputs, outputs)


def _usage_failure_mode(comments_by_tag: dict[str, list[dict]], text_rows: dict[str, list[dict]], outputs: list[dict]) -> dict:
    failure_text = _first_text(comments_by_tag.get("failure", [])) or _first_text(text_rows.get("failure", []))
    source = "comment:failure" if comments_by_tag.get("failure") else ("failure" if failure_text else "")
    if not failure_text:
        metadata_text = _metadata_text(text_rows)
        lowered_metadata = metadata_text.lower()
        if any(phrase in lowered_metadata for phrase in ("returns null", "return null", "non-zero", "failure", "error", "must c.free", "caller frees")):
            failure_text = metadata_text
            source = "metadata"
    output_values = outputs[0].get("values", []) if outputs else []
    output_type = outputs[0].get("type", "") if outputs else ""
    lowered_failure = failure_text.lower()
    if output_values and output_values[0] == "Result":
        kind = "result"
    elif re.search(r"\b(returns?|return)\s+null\b|\bnull\s+(on|means|indicates)\b", lowered_failure):
        kind = "null-sentinel"
    elif "null" in lowered_failure and any(phrase in lowered_failure for phrase in ("no null", "must not be null", "null-pointer", "null pointer")):
        kind = "caller-precondition"
    elif output_type in {"Int32", "ExitCode", "GuiRuntimeStatusCode", "GuiSelectedIndex"} and any(word in lowered_failure for word in ("non-zero", "status", "failure", "error")):
        kind = "status-code"
    elif failure_text:
        kind = "documented-prose"
    else:
        kind = "none"
    return {
        "kind": kind,
        "text": failure_text,
        "source": source,
    }


def _cleanup_rows(call: dict, cleanup: dict) -> list[str]:
    if not cleanup.get("required") or not cleanup.get("callTarget") or not call.get("resultName"):
        return []
    call_base_name = call["callName"][:-4] if call.get("callName", "").endswith("Call") else call.get("callName", "cleanup")
    cleanup_call_name = f"{call_base_name}CleanupCall"
    argument_name = cleanup.get("argumentName", "ptr")
    argument_type = cleanup.get("argumentType", "OpaquePointer")
    result_type = cleanup.get("resultType", "Void")
    cleanup_source = call["resultName"]
    rows = []
    result_field = cleanup.get("resultField", {})
    if result_field:
        field_name = result_field.get("name", "")
        field_type = result_field.get("type", argument_type)
        field_value_name = result_field.get("valueName", f"{call_base_name}{field_name[:1].upper()}{field_name[1:]}")
        if field_name and field_type:
            rows.append(f"fieldGet {field_value_name} {field_type} {call['resultName']} {field_name}")
            cleanup_source = field_value_name
    ignore_kind = cleanup.get("ignoreKind", "")
    if result_type == "Void":
        ignore_row = f"ignore void source {cleanup_call_name}"
    elif ignore_kind == "ok":
        ignore_row = f"ignore ok source {cleanup_call_name} type {result_type}"
    else:
        ignore_row = f"ignore value source {cleanup_call_name} type {result_type}"
    rows.extend([
        f"call {cleanup_call_name} {cleanup['callTarget']}",
        f"argument {cleanup_call_name} {argument_name} {argument_type} {cleanup_source}",
        f"run {cleanup_call_name}",
        ignore_row,
    ])
    if ignore_kind == "ok" and cleanup.get("errorType"):
        cleanup_error_name = f"{call_base_name}CleanupError"
        rows.extend([
            f"bind error {cleanup_error_name} {cleanup['errorType']} {cleanup_call_name}",
            f"branch error source {cleanup_call_name} target <cleanupErrorLabel>",
        ])
    return rows


def _augment_cleanup_guidance(cleanup: dict) -> dict:
    cleanup = dict(cleanup or {})
    cleanup.setdefault("agentWarnings", [])
    if cleanup.get("callTarget") in {"c.free", "net.freeTextBody", "memory.releaseMemoryBytes", "standard.memory.releaseMemoryBytes"}:
        cleanup["requiredCallerEffects"] = [{"action": "free", "path": "heap"}]
        cleanup["authorityRows"] = [
            "effect <callerOperation> free heap",
            "capability <heapFreeCapability> heap free",
            "useCapability <callerOperation> <heapFreeCapability>",
        ]
        cleanup["agentWarnings"].append(f"{cleanup.get('callTarget')} cleanup requires caller free heap effect plus matching capability or authority.")
    else:
        cleanup.setdefault("requiredCallerEffects", [])
        cleanup.setdefault("authorityRows", [])
    if cleanup.get("required") and not cleanup.get("callTarget"):
        cleanup["agentWarnings"].append("Cleanup is required, but no cleanup call target was inferred; inspect ownership docs before generating code.")
    return cleanup


def _failure_handling_rows(call: dict, outputs: list[dict], failure_mode: dict) -> list[str]:
    kind = failure_mode.get("kind", "none")
    call_name = call.get("callName", "")
    result_name = call.get("resultName", "")
    call_base_name = call_name[:-4] if call_name.endswith("Call") else call_name
    if kind == "result":
        error_name = call.get("errorName") or f"{call_base_name}Error"
        error_type = call.get("errorType") or "ERROR_TYPE"
        return [
            f"bind error {error_name} {error_type} {call_name}",
            f"branch error source {call_name} target <errorLabel>",
        ]
    if kind == "null-sentinel" and result_name:
        null_check_call = f"{call_base_name}NullCheckCall"
        null_flag = f"{call_base_name}IsNull"
        return [
            f"call {null_check_call} pointer.isNull",
            f"argument {null_check_call} pointer OpaquePointer {result_name}",
            f"run {null_check_call}",
            f"bind value {null_flag} Bool {null_check_call}",
            f"branch if condition {null_flag} target <failureLabel>",
        ]
    if kind == "status-code" and result_name:
        status_check_call = f"{call_base_name}StatusCheckCall"
        success_status = f"{call_base_name}SuccessStatus"
        failed_flag = f"{call_base_name}Failed"
        status_type = outputs[0].get("type", "Int32") if outputs else "Int32"
        return [
            f"storage local immutable {success_status} {status_type} 0",
            f"call {status_check_call} math.notEqualInt32",
            f"argument {status_check_call} left {status_type} {result_name}",
            f"argument {status_check_call} right {status_type} {success_status}",
            f"run {status_check_call}",
            f"bind value {failed_flag} Bool {status_check_call}",
            f"branch if condition {failed_flag} target <failureLabel>",
        ]
    if kind == "negative-status" and result_name:
        status_check_call = f"{call_base_name}NegativeStatusCheckCall"
        zero_status = f"{call_base_name}ZeroStatus"
        failed_flag = f"{call_base_name}Failed"
        status_type = outputs[0].get("type", "Int32") if outputs else "Int32"
        return [
            f"storage local immutable {zero_status} {status_type} 0",
            f"call {status_check_call} math.lessThanInt32",
            f"argument {status_check_call} left {status_type} {result_name}",
            f"argument {status_check_call} right {status_type} {zero_status}",
            f"run {status_check_call}",
            f"bind value {failed_flag} Bool {status_check_call}",
            f"branch if condition {failed_flag} target <failureLabel>",
        ]
    if kind == "snprintf-status" and result_name:
        negative_check_call = f"{call_base_name}NegativeStatusCheckCall"
        zero_status = f"{call_base_name}ZeroStatus"
        failed_flag = f"{call_base_name}Failed"
        result_width_call = f"{call_base_name}ResultLengthCall"
        result_length = f"{call_base_name}ResultLength"
        truncation_check_call = f"{call_base_name}TruncationCheckCall"
        truncated_flag = f"{call_base_name}Truncated"
        return [
            f"storage local immutable {zero_status} Int32 0",
            f"call {negative_check_call} math.lessThanInt32",
            f"argument {negative_check_call} left Int32 {result_name}",
            f"argument {negative_check_call} right Int32 {zero_status}",
            f"run {negative_check_call}",
            f"bind value {failed_flag} Bool {negative_check_call}",
            f"branch if condition {failed_flag} target <formatFailureLabel>",
            f"call {result_width_call} math.signExtendInt32ToInt64",
            f"argument {result_width_call} inputValue Int32 {result_name}",
            f"run {result_width_call}",
            f"bind value {result_length} Int64 {result_width_call}",
            f"call {truncation_check_call} math.greaterThanOrEqualInt64",
            f"argument {truncation_check_call} left Int64 {result_length}",
            f"argument {truncation_check_call} right Int64 <bufferSize>",
            f"run {truncation_check_call}",
            f"bind value {truncated_flag} Bool {truncation_check_call}",
            f"branch if condition {truncated_flag} target <truncationLabel>",
        ]
    return []


def _usage_failure_handling(call: dict, outputs: list[dict], failure_mode: dict) -> dict:
    kind = failure_mode.get("kind", "none")
    if kind == "none":
        required = False
        phase = "none"
    elif kind == "caller-precondition":
        required = False
        phase = "before-call"
    elif kind == "sentinel-value":
        required = False
        phase = "after-call"
    elif kind == "documented-prose":
        required = False
        phase = "documented"
    else:
        required = True
        phase = "after-call"
    agent_warnings = []
    if kind == "sentinel-value":
        agent_warnings.append("Sentinel-value handling is domain-dependent; compare the result against the documented sentinel when absence is not acceptable.")
    if kind == "documented-prose":
        agent_warnings.append("Failure guidance is prose-only; inspect the text before deciding whether to branch, pre-size buffers, or document a caller precondition.")
    return {
        "required": required,
        "kind": kind,
        "phase": phase,
        "rows": _failure_handling_rows(call, outputs, failure_mode),
        "text": failure_mode.get("text", ""),
        "agentWarnings": agent_warnings,
    }


def _usage_preconditions(failure_mode: dict) -> dict:
    if failure_mode.get("kind") != "caller-precondition":
        return {"required": False, "text": "", "rows": []}
    return {
        "required": True,
        "text": failure_mode.get("text", ""),
        "rows": [],
        "callerMustEnsure": failure_mode.get("text", ""),
    }


def _usage_cleanup(comments_by_tag: dict[str, list[dict]], text_rows: dict[str, list[dict]], outputs: list[dict], memory_rows: list[dict]) -> dict:
    memory_text = " ".join(comment.get("text", "") for comment in comments_by_tag.get("memory", []))
    metadata_text = _metadata_text(text_rows)
    output_type = outputs[0].get("type", "") if outputs else ""
    lowered_memory = f"{memory_text} {metadata_text}".lower()
    returns_value = output_type not in {"", "Void"}
    heap_output = any(row.get("policy") == ["heap", "yes"] for row in memory_rows) and returns_value
    requires_free = returns_value and ("c.free" in lowered_memory or "heap-owned" in lowered_memory or "releasememorybytes" in lowered_memory or heap_output)
    cleanup = {
        "required": requires_free,
        "text": memory_text or (metadata_text if requires_free else ""),
        "source": "comment:memory" if memory_text else ("metadata" if requires_free and metadata_text else ("memory" if heap_output else "")),
    }
    if requires_free:
        cleanup_target = ""
        if "releasememorybytes" in lowered_memory:
            cleanup_target = "memory.releaseMemoryBytes"
        elif "c.free" in lowered_memory:
            cleanup_target = "c.free"
        cleanup.update({
            "strategy": "release returned non-null heap-owned value on every ownership path",
            "callTarget": cleanup_target,
        })
        if cleanup_target == "memory.releaseMemoryBytes":
            cleanup.update({"argumentName": "memoryBuffer", "argumentType": "OpaquePointer", "resultType": "Void"})
    return cleanup


def _operation_usage_payload(
    module_name: str,
    module_short_name: str,
    operation_name: str,
    inputs: list[dict],
    outputs: list[dict],
    effects: list[dict],
    capabilities: list[dict],
    capability_details: list[dict],
    comments_by_tag: dict[str, list[dict]],
    text_rows: dict[str, list[dict]],
    memory_rows: list[dict],
) -> dict:
    call = _usage_call_template(module_short_name, operation_name, inputs, outputs)
    failure_mode = _usage_failure_mode(comments_by_tag, text_rows, outputs)
    failure_handling = _usage_failure_handling(call, outputs, failure_mode)
    preconditions = _usage_preconditions(failure_mode)
    cleanup = _usage_cleanup(comments_by_tag, text_rows, outputs, memory_rows)
    cleanup = _augment_cleanup_guidance(cleanup)
    cleanup["rows"] = _cleanup_rows(call, cleanup)
    call["requiresFailureHandling"] = failure_handling["required"]
    call["requiresPreconditions"] = preconditions["required"]
    call["requiresCleanup"] = cleanup["required"]
    capability_guidance = _capability_usage_guidance(capabilities, capability_details)
    capability_guidance["authorityRows"] = list(dict.fromkeys([
        *capability_guidance["authorityRows"],
        *_effect_authority_rows(effects, capability_details),
    ]))
    return {
        "importRow": f"import {module_short_name} {module_name}",
        "call": call,
        "requiredCallerEffects": [
            {"action": effect["action"], "path": effect["path"]}
            for effect in effects
        ],
        "effectRows": [
            f"effect <callerOperation> {effect['action']} {effect['path']}"
            for effect in effects
        ],
        "requiredCapabilities": [detail for detail in capability_details],
        **capability_guidance,
        "failureMode": failure_mode,
        "failureHandling": failure_handling,
        "preconditions": preconditions,
        "cleanup": cleanup,
    }


def _std_operation_doc_payload(facts, path: Path, operation, summary_tag: str) -> dict:
    module_name = _row_value(facts, "module")
    module_short_name = _std_module_short_name(module_name)
    comment_block = _preceding_comment_block(facts.lines, operation.line)
    comments = _typed_comment_payloads(comment_block)
    comments_by_tag = _comments_by_tag(comments)
    text_rows = _operation_text_rows(operation)
    inputs = []
    outputs = []
    effects = []
    capabilities = []
    for source_line in operation.lines:
        if not source_line.tokens:
            continue
        input_payload = _signature_input_payload(source_line, operation)
        output_payload = _signature_output_payload(source_line, operation)
        effect_payload = _effect_payload(source_line, operation)
        if input_payload is not None:
            inputs.append(input_payload)
        elif output_payload is not None:
            outputs.append(output_payload)
        elif effect_payload is not None:
            effects.append(effect_payload)
        elif source_line.verb == "useCapability" and len(source_line.args) >= 2 and source_line.args[0] == operation.name:
            capabilities.append({
                "name": source_line.args[1],
                "location": _line_payload(source_line),
            })
    summary, summary_source = _summary_from_doc(comments_by_tag, text_rows, summary_tag)
    exports = _operation_exports(facts, module_name, operation.name)
    runtime_rows = _operation_runtime_rows(facts, operation)
    memory_rows = _operation_memory_rows(operation)
    capability_details = _capability_details(facts, module_name, capabilities)
    purpose_rows = text_rows.get("purpose", [])
    invariant_rows = text_rows.get("invariant", [])
    visibility = _operation_visibility(operation, exports, runtime_rows)
    native_linkability = _operation_native_linkability(runtime_rows, module_name, operation.name)
    return {
        "module": module_name,
        "moduleName": module_short_name,
        "name": operation.name,
        "qualifiedName": f"{module_short_name}.{operation.name}",
        "fullName": f"{module_name}.{operation.name}",
        "location": _line_payload(operation.line),
        "sourceFile": str(path.resolve()),
        "visibility": visibility,
        "nativeLinkability": native_linkability,
        "implementationStatus": "lowered",
        "statusTaxonomy": _docs_status_taxonomy(
            "lowered",
            detail="Operation rows are parsed and lowered as callable SemanticScript operations; runtime linkability is reported separately.",
        ),
        "agentWarnings": _operation_agent_warnings(
            visibility,
            capability_details,
            native_linkability,
            module_name,
            operation.name,
        ),
        "summary": summary,
        "summarySource": summary_source,
        "purpose": _first_text(purpose_rows),
        "invariants": [row["text"] for row in invariant_rows if row.get("text")],
        "signature": {
            "inputs": inputs,
            "outputs": outputs,
            "text": _signature_text(inputs, outputs),
        },
        "comments": comments,
        "commentsByTag": comments_by_tag,
        "metadata": text_rows,
        "effects": effects,
        "memory": memory_rows,
        "capabilities": capabilities,
        "capabilityDetails": capability_details,
        "runtime": runtime_rows,
        "exports": exports,
        "usage": _operation_usage_payload(
            module_name,
            module_short_name,
            operation.name,
            inputs,
            outputs,
            effects,
            capabilities,
            capability_details,
            comments_by_tag,
            text_rows,
            memory_rows,
        ),
    }


def _std_doc_list_item(operation_doc: dict) -> dict:
    signature = operation_doc["signature"]
    return {
        "module": operation_doc["module"],
        "moduleName": operation_doc["moduleName"],
        "name": operation_doc["name"],
        "qualifiedName": operation_doc["qualifiedName"],
        "fullName": operation_doc["fullName"],
        "signature": {
            "text": signature["text"],
            "inputs": [
                {"name": item["name"], "type": item["type"]}
                for item in signature.get("inputs", [])
            ],
            "outputs": [
                {"type": item.get("type", ""), "values": item.get("values", [])}
                for item in signature.get("outputs", [])
            ],
        },
        "summary": operation_doc["summary"],
        "summarySource": operation_doc["summarySource"],
        "location": operation_doc["location"],
        "sourceFile": operation_doc["sourceFile"],
        "visibility": operation_doc["visibility"],
        "implementationStatus": operation_doc.get("implementationStatus", ""),
        "statusTaxonomy": operation_doc.get("statusTaxonomy", {}),
        # Carry the STRUCTURED native-link signal into the compact match list,
        # not just the prose agentWarning: agents commonly read matches[0]
        # directly (docs get returns {matches:[...]}) and a machine consumer must
        # be able to filter "links in native/webServer build" without parsing the
        # SSCG002 warning text. See TODOS hit-list #1 / the "checks clean, won't
        # link" trust gap.
        "nativeLinkability": operation_doc.get("nativeLinkability"),
        "agentWarnings": operation_doc.get("agentWarnings", []),
        "purpose": operation_doc.get("purpose", ""),
        "invariants": operation_doc.get("invariants", []),
        "effects": [
            {"action": effect["action"], "path": effect["path"]}
            for effect in operation_doc.get("effects", [])
        ],
        "capabilities": [
            {"name": detail["name"], "resource": detail.get("resource", ""), "action": detail.get("action", "")}
            for detail in operation_doc.get("capabilityDetails", [])
        ],
        "failureMode": operation_doc.get("usage", {}).get("failureMode", {}),
        "cleanup": operation_doc.get("usage", {}).get("cleanup", {}),
    }


def _std_operation_matches(operation_doc: dict, query: str) -> bool:
    candidates = {
        operation_doc["name"],
        operation_doc["qualifiedName"],
        operation_doc["fullName"],
    }
    return query in candidates


def _std_target_matches(target_doc: dict, query: str) -> bool:
    candidates = {
        target_doc.get("target", ""),
        target_doc.get("qualifiedName", ""),
        target_doc.get("fullName", ""),
        target_doc.get("name", ""),
    }
    return query in candidates


DOCS_STATUS_TAXONOMY_LEGEND = {
    "lowered": "Current compiler/runtime lowering supports executable code generation for this surface.",
    "metadata": "Parsed/indexed as semantic contract data; it does not by itself emit runtime behavior.",
    "sync-fallback": "Runtime meaning exists, but the current backend collapses the async/concurrent shape to synchronous behavior.",
    "partial": "Mixed or incomplete support; inspect summary, warnings, usage, and readiness before generating code.",
    "refined": "Future/refined tooling surface; do not assume current parser/codegen support.",
    "unknown": "Status was not classified; inspect the source location before generating code.",
}


def _docs_status_taxonomy(value: str, *, detail: str = "") -> dict:
    raw_value = (value or "unknown").strip()
    lowered = raw_value.lower()
    aliases = {
        "impl'd": "lowered",
        "implemented": "lowered",
        "lowered": "lowered",
        "metadata": "metadata",
        "checked metadata": "metadata",
        "sync-fallback": "sync-fallback",
        "synchronous fallback": "sync-fallback",
        "partial": "partial",
        "reserved": "partial",
        "not impl'd": "refined",
        "proposed": "refined",
        "refined": "refined",
    }
    category = aliases.get(lowered, "unknown")
    return {
        "value": raw_value,
        "category": category,
        "meaning": DOCS_STATUS_TAXONOMY_LEGEND[category],
        "detail": detail,
    }


def _target_list_item(target_doc: dict) -> dict:
    item = {
        "kind": "callTarget",
        "module": target_doc.get("module", ""),
        "moduleName": target_doc.get("moduleName", ""),
        "name": target_doc.get("name", ""),
        "target": target_doc.get("target", ""),
        "qualifiedName": target_doc.get("qualifiedName", target_doc.get("target", "")),
        "fullName": target_doc.get("fullName", ""),
        "loweringStatus": target_doc.get("loweringStatus", ""),
        "statusTaxonomy": target_doc.get("statusTaxonomy", {}),
        "visibility": target_doc.get("visibility", {}),
        "agentWarnings": target_doc.get("agentWarnings", []),
        "signature": target_doc.get("signature", {}),
        "summary": target_doc.get("summary", ""),
        "effects": target_doc.get("effects", []),
        "capabilities": [
            {"name": detail["name"], "resource": detail.get("resource", ""), "action": detail.get("action", "")}
            for detail in target_doc.get("capabilityDetails", [])
        ],
        "failureMode": target_doc.get("failureMode", {}),
        "cleanup": target_doc.get("cleanup", {}),
    }
    if target_doc.get("migration"):
        item["migration"] = target_doc.get("migration")
    if target_doc.get("wrapperPolicy"):
        item["wrapperPolicy"] = target_doc.get("wrapperPolicy")
    return item


def _type_doc_payload(module_name: str, type_name: str, type_doc: dict) -> dict:
    source_file = type_doc.get("sourceFile", "")
    location_path = ""
    if source_file:
        candidate = ROOT.parent / source_file
        location_path = str(candidate.resolve() if candidate.exists() else candidate)
    qualified_name = f"{_std_module_short_name(module_name)}.{type_name}"
    implementation_status = type_doc.get("implementationStatus", "metadata")
    return {
        "kind": type_doc.get("kind", "type"),
        "module": module_name,
        "moduleName": _std_module_short_name(module_name),
        "name": type_name,
        "qualifiedName": qualified_name,
        "fullName": f"{module_name}.{type_name}",
        "summary": type_doc.get("summary", ""),
        "representation": type_doc.get("repr") or type_doc.get("underlyingType", ""),
        "repr": type_doc.get("repr", ""),
        "underlyingType": type_doc.get("underlyingType", ""),
        "cases": type_doc.get("cases", []),
        "usage": type_doc.get("usage", []),
        "exampleRows": type_doc.get("exampleRows", []),
        "implementationStatus": implementation_status,
        "statusTaxonomy": _docs_status_taxonomy(
            implementation_status,
            detail="Curated type/enum/record docs are schema metadata unless a row says otherwise.",
        ),
        "source": type_doc.get("source", "static-type-contract"),
        "visibility": {
            "exported": not module_name.startswith("compiler."),
            "public": True,
            "internal": False,
            "apiTier": "type-contract",
            "reason": type_doc.get("source", "static-type-contract"),
        },
        "location": {
            "path": location_path,
            "line": int(type_doc.get("line", 0) or 0),
            "column": 1,
        } if location_path else {},
    }


def _static_type_docs(module_name: str = "") -> list[dict]:
    docs: list[dict] = []
    for module, type_docs in sorted(STD_DOC_STATIC_TYPES.items()):
        if not _std_module_matches(module, module_name):
            continue
        for type_name, type_doc in sorted(type_docs.items()):
            docs.append(_type_doc_payload(module, type_name, type_doc))
    return docs


def _type_doc_matches(type_doc: dict, query: str) -> bool:
    candidates = {
        type_doc.get("name", ""),
        type_doc.get("qualifiedName", ""),
        type_doc.get("fullName", ""),
    }
    for case in type_doc.get("cases", []):
        candidates.add(case.get("name", ""))
    return query in candidates


def _type_list_item(type_doc: dict) -> dict:
    return {
        "kind": type_doc.get("kind", "type"),
        "module": type_doc.get("module", ""),
        "moduleName": type_doc.get("moduleName", ""),
        "name": type_doc.get("name", ""),
        "qualifiedName": type_doc.get("qualifiedName", ""),
        "fullName": type_doc.get("fullName", ""),
        "summary": type_doc.get("summary", ""),
        "representation": type_doc.get("representation", ""),
        "repr": type_doc.get("repr", ""),
        "underlyingType": type_doc.get("underlyingType", ""),
        "cases": type_doc.get("cases", []),
        "usage": type_doc.get("usage", []),
        "exampleRows": type_doc.get("exampleRows", []),
        "implementationStatus": type_doc.get("implementationStatus", ""),
        "statusTaxonomy": type_doc.get("statusTaxonomy", {}),
        "visibility": type_doc.get("visibility", {}),
        "location": type_doc.get("location", {}),
    }


def _module_targets(modules: list[dict]) -> list[dict]:
    return [target for module in modules for target in module.get("callTargets", [])]


def _module_text_row(source_line, module_name: str) -> dict | None:
    verb = source_line.verb
    args = source_line.args
    if verb in {"purpose", "invariant"} and len(args) >= 3 and args[0] == "module" and args[1] == module_name:
        return {
            "tag": verb,
            "text": " ".join(args[2:]).strip(),
            "location": _line_payload(source_line),
        }
    if verb in {"moduleOwns", "moduleDoesNotOwn", "moduleWarning", "moduleSecurity"} and len(args) >= 2 and args[0] == module_name:
        return {
            "tag": verb,
            "text": " ".join(args[1:]).strip(),
            "location": _line_payload(source_line),
        }
    return None


def _module_text_rows(facts, module_name: str) -> dict[str, list[dict]]:
    rows: dict[str, list[dict]] = {}
    for source_line in facts.lines:
        if not source_line.tokens:
            continue
        payload = _module_text_row(source_line, module_name)
        if payload is not None:
            rows.setdefault(payload["tag"], []).append(payload)
    return rows


def _module_line(facts, module_name: str):
    for source_line in facts.lines:
        if source_line.verb == "module" and source_line.args[:1] == [module_name]:
            return source_line
    return None


def _location_or_empty(source_line) -> dict:
    return _line_payload(source_line) if source_line is not None else {}


def _capability_usage_guidance(capabilities: list[dict], capability_details: list[dict]) -> dict:
    details_by_name = {detail.get("name", ""): detail for detail in capability_details}
    use_rows = []
    authority_rows = []
    local_capability_rows = []
    for capability in capabilities:
        name = capability["name"]
        detail = details_by_name.get(name, {})
        resource = detail.get("resource", "")
        action = detail.get("action", "")
        if detail.get("exported", False):
            use_rows.append(f"useCapability <callerOperation> {name}")
        elif resource and action:
            authority_rows.append(f"authority <callerOperation> {action} {resource}")
            local_name = f"local{name[:1].upper()}{name[1:]}"
            local_capability_rows.extend([
                f"capability {local_name} {resource} {action}",
                f"useCapability <callerOperation> {local_name}",
            ])
    return {
        "useCapabilityRows": use_rows,
        "authorityRows": authority_rows,
        "localCapabilityRows": local_capability_rows,
    }


def _effect_authority_rows(effects: list[dict], capability_details: list[dict]) -> list[str]:
    rows = []
    for effect in effects:
        action = effect.get("action", "")
        path = effect.get("path", "")
        covered_by_exported_capability = any(
            detail.get("exported") and detail.get("action") == action and detail.get("resource") == path
            for detail in capability_details
        )
        if action and path and not covered_by_exported_capability:
            rows.append(f"authority <callerOperation> {action} {path}")
    return rows


def _docs_import_row(module_name: str) -> str:
    if module_name.startswith("compiler."):
        return ""
    module_short_name = _std_module_short_name(module_name)
    return f"import {module_short_name} {module_name}"


def _target_usage_payload(
    module_name: str,
    target: str,
    inputs: list[dict],
    outputs: list[dict],
    effects: list[dict],
    capabilities: list[dict],
    capability_details: list[dict],
    failure_mode: dict,
    cleanup: dict,
) -> dict:
    call = _usage_call_template_for_target(target, _target_call_base_name(target), inputs, outputs)
    failure_handling = _usage_failure_handling(call, outputs, failure_mode)
    preconditions = _usage_preconditions(failure_mode)
    cleanup = dict(cleanup or {"required": False, "source": "", "text": ""})
    cleanup.setdefault("required", False)
    cleanup.setdefault("source", "")
    cleanup.setdefault("text", "")
    cleanup = _augment_cleanup_guidance(cleanup)
    cleanup["rows"] = _cleanup_rows(call, cleanup)
    call["requiresFailureHandling"] = failure_handling["required"]
    call["requiresPreconditions"] = preconditions["required"]
    call["requiresCleanup"] = cleanup["required"]
    capability_guidance = _capability_usage_guidance(capabilities, capability_details)
    capability_guidance["authorityRows"] = list(dict.fromkeys([
        *capability_guidance["authorityRows"],
        *_effect_authority_rows(effects, capability_details),
    ]))
    return {
        "availableForCodegen": True,
        "reason": "target loweringStatus is lowered; this call target has compiler/runtime codegen support",
        "importRequired": bool(_docs_import_row(module_name)),
        "importRow": _docs_import_row(module_name),
        "call": call,
        "requiredCallerEffects": [
            {"action": effect["action"], "path": effect["path"]}
            for effect in effects
        ],
        "effectRows": [
            f"effect <callerOperation> {effect['action']} {effect['path']}"
            for effect in effects
        ],
        "requiredCapabilities": [detail for detail in capability_details],
        **capability_guidance,
        "failureMode": failure_mode,
        "failureHandling": failure_handling,
        "preconditions": preconditions,
        "cleanup": cleanup,
    }


def _target_doc_payload(
    facts,
    module_name: str,
    target: str,
    *,
    name: str = "",
    type_name: str = "",
    exported: bool = False,
    location_source=None,
    comments: list[dict] | None = None,
) -> dict:
    static_doc = STD_DOC_STATIC_TARGETS.get(module_name, {}).get(target, {})
    comments = comments or []
    comments_by_tag = _comments_by_tag(comments)
    inputs = copy.deepcopy(static_doc.get("inputs", []))
    outputs = copy.deepcopy(static_doc.get("outputs", []))
    effects = copy.deepcopy(static_doc.get("effects", []))
    capability_refs = [
        {"name": capability_name, "location": _location_or_empty(location_source)}
        for capability_name in static_doc.get("capabilities", [])
    ]
    capability_details = _capability_details(facts, module_name, capability_refs)
    failure_mode = copy.deepcopy(static_doc.get("failureMode", {"kind": "none", "text": "", "source": ""}))
    failure_mode.setdefault("source", "static-target-contract" if failure_mode.get("text") else "")
    cleanup = copy.deepcopy(static_doc.get("cleanup", {"required": False, "source": "", "text": ""}))
    if cleanup.get("required"):
        cleanup.setdefault("source", "static-target-contract")
        cleanup.setdefault("text", cleanup.get("strategy", ""))
    lowering_status = static_doc.get("loweringStatus", "lowered" if inputs or outputs else "unknown")
    if lowering_status == "lowered":
        usage = _target_usage_payload(module_name, target, inputs, outputs, effects, capability_refs, capability_details, failure_mode, cleanup)
    else:
        usage = {
            "availableForCodegen": False,
            "reason": f"target loweringStatus is {lowering_status}; do not generate calls without backend support",
        }
    migration = copy.deepcopy(static_doc.get("migration", {}))
    if migration:
        usage["migration"] = migration
        usage["recommendedForNewCode"] = False
        usage["availableForCodegen"] = False
        usage["reason"] = (
            "Compatibility target only for generated-id recovery; use "
            "usage.migration.rows with INSERT ... RETURNING id for new "
            "native/webServer-safe code."
        )
    target_visibility = {
        "exported": exported,
        "internal": False,
        "public": lowering_status == "lowered",
        "apiTier": "compiler-lowered" if lowering_status == "lowered" else lowering_status,
        "reason": "static-target-contract" if location_source is None else "exportConstant",
    }
    agent_warnings = list(static_doc.get("agentWarnings", []))
    if lowering_status != "lowered":
        agent_warnings.append(f"Target loweringStatus is {lowering_status}; do not generate calls without backend support.")
    if failure_mode.get("kind") == "sentinel-value":
        agent_warnings.append("Sentinel-value handling is domain-dependent; compare against the documented sentinel when absence is not acceptable.")
    wrapper_policy = _libc_wrapper_policy_payload(target)
    if wrapper_policy:
        policy_decision = wrapper_policy.get("decision", "")
        policy_module = wrapper_policy.get("module", "")
        if policy_decision == "stdlib-wrapper-planned":
            agent_warnings.append(
                f"Raw {target} is an escape hatch. Prefer the {policy_module} wrapper when available; new app code should not grow direct c.* usage."
            )
        elif policy_decision == "native-adapter-required":
            agent_warnings.append(
                f"Raw {target} needs a native adapter before it becomes a normal SemanticScript API; do not generate app-level calls to it."
            )
            usage = {
                "availableForCodegen": False,
                "reason": f"wrapperPolicy.decision is {policy_decision}; use a standard-library adapter instead",
            }
            target_visibility["public"] = False
            target_visibility["apiTier"] = policy_decision
        elif policy_decision in {"no-public-wrapper", "abi-blocked"}:
            agent_warnings.append(
                f"Raw {target} is classified as {policy_decision}; do not generate app-level calls to it."
            )
            usage = {
                "availableForCodegen": False,
                "reason": f"wrapperPolicy.decision is {policy_decision}; use a safer standard-library API or adapter instead",
            }
            target_visibility["public"] = False
            target_visibility["apiTier"] = policy_decision
        elif policy_decision == "compiler-runtime-owned":
            agent_warnings.append(
                f"Raw {target} is owned by a compiler/runtime surface; use the owning standard module instead of calling the adapter symbol directly."
            )
    return {
        "kind": "callTarget",
        "module": module_name,
        "moduleName": _std_module_short_name(module_name),
        "name": name or _target_call_base_name(target),
        "type": type_name or "",
        "target": target,
        "qualifiedName": target,
        "fullName": f"{module_name}.{target}",
        "exported": exported,
        "visibility": target_visibility,
        "agentWarnings": agent_warnings,
        "source": "storage" if location_source is not None else "static-target-contract",
        "loweringStatus": lowering_status,
        "implementationStatus": lowering_status,
        "statusTaxonomy": _docs_status_taxonomy(
            lowering_status,
            detail="Call-target lowering status controls whether usage rows are safe to generate directly.",
        ),
        "summary": static_doc.get("summary", _first_text(comments_by_tag.get("rationale", []))),
        "invariants": [comment["text"] for comment in comments_by_tag.get("invariant", []) if comment.get("text")],
        "commentsByTag": comments_by_tag,
        "signature": {"inputs": inputs, "outputs": outputs, "text": _signature_text(inputs, outputs)},
        "effects": effects,
        "capabilities": capability_refs,
        "capabilityDetails": capability_details,
        "failureMode": failure_mode,
        "cleanup": cleanup,
        "migration": migration,
        "wrapperPolicy": wrapper_policy,
        "usage": usage,
        "comments": comments,
        "location": _location_or_empty(location_source),
    }


def _module_call_targets(facts, module_name: str) -> list[dict]:
    exported_constants = _exported_names(facts, "exportConstant", module_name)
    targets = []
    seen_targets = set()
    for source_line in facts.lines:
        args = source_line.args
        if source_line.verb != "storage" or len(args) < 5:
            continue
        if args[0] != "module":
            continue
        name = args[2]
        type_name = args[3]
        value = args[4]
        if name not in exported_constants:
            continue
        if not (type_name.endswith("RuntimeTarget") or (name.endswith("Target") and "." in value)):
            continue
        comments = _typed_comment_payloads(_preceding_comment_block(facts.lines, source_line))
        targets.append(_target_doc_payload(
            facts,
            module_name,
            value,
            name=name,
            type_name=type_name,
            exported=True,
            location_source=source_line,
            comments=comments,
        ))
        seen_targets.add(value)
    for target in sorted(STD_DOC_STATIC_TARGETS.get(module_name, {})):
        if target not in seen_targets:
            targets.append(_target_doc_payload(facts, module_name, target))
    return targets


def _module_record_type_docs(facts, module_name: str, path: Path) -> list[dict]:
    """Build type-doc payloads for the records a module declares so that
    `docs get <RecordName>` returns the record's fields. `facts.records` maps a
    record name to a list of (fieldName, fieldType) pairs."""
    short = _std_module_short_name(module_name)
    records = getattr(facts, "records", {}) or {}
    docs = []
    for record_name in sorted(records):
        fields = [{"name": field_name, "type": field_type}
                  for field_name, field_type in records[record_name]]
        field_summary = ", ".join(f"{f['name']}:{f['type']}" for f in fields)
        docs.append({
            "kind": "record",
            "module": module_name,
            "moduleName": short,
            "name": record_name,
            "qualifiedName": f"{short}.{record_name}",
            "fullName": f"{module_name}.{record_name}",
            "summary": f"Record `{record_name}` {{ {field_summary} }}." if fields
                       else f"Record `{record_name}` (no fields).",
            "representation": "record",
            "repr": "record",
            "underlyingType": "",
            "cases": [],
            "fields": fields,
            "usage": [],
            "exampleRows": [],
            "implementationStatus": "metadata",
            "statusTaxonomy": _docs_status_taxonomy(
                "metadata",
                detail="Module record docs expose parsed schema shape; record rows are semantic metadata unless a lowering path consumes them.",
            ),
            "source": "module-record",
            "visibility": {"exported": True, "public": True, "internal": False,
                           "apiTier": "type-contract", "reason": "module-record"},
            "sourceFile": str(path.resolve()),
        })
    return docs


def _std_module_doc_payload(facts, path: Path, operations: list[dict], summary_tag: str) -> dict:
    module_name = _row_value(facts, "module")
    module_short_name = _std_module_short_name(module_name)
    module_line = _module_line(facts, module_name)
    comments = _typed_comment_payloads(_preceding_comment_block(facts.lines, module_line)) if module_line is not None else []
    comments_by_tag = _comments_by_tag(comments)
    metadata = _module_text_rows(facts, module_name)
    summary, summary_source = _summary_from_doc(comments_by_tag, metadata, summary_tag)
    public_operations = [operation for operation in operations if operation["visibility"]["public"]]
    call_targets = _module_call_targets(facts, module_name)
    if public_operations:
        operation_status = "ok"
    elif operations:
        operation_status = "internal-only"
    else:
        operation_status = "no-operation-docs"
    return {
        "module": module_name,
        "moduleName": module_short_name,
        "sourceFile": str(path.resolve()),
        "location": _line_payload(module_line) if module_line is not None else {},
        "summary": summary,
        "summarySource": summary_source,
        "purpose": _first_text(metadata.get("purpose", [])),
        "invariants": [row["text"] for row in metadata.get("invariant", []) if row.get("text")],
        "comments": comments,
        "commentsByTag": comments_by_tag,
        "metadata": metadata,
        "operationDocStatus": operation_status,
        "operationCount": len(operations),
        "publicOperationCount": len(public_operations),
        "callTargets": call_targets,
        "records": _module_record_type_docs(facts, module_name, path),
    }


def _compiler_module_summary(module_name: str) -> str:
    summaries = {
        "compiler.console": "Compiler-lowered console stdout targets that do not require a standard-library import.",
        "compiler.math": "Compiler-lowered arithmetic, comparison, conversion, and checked arithmetic targets.",
        "compiler.pointer": "Compiler-lowered pointer and byte-buffer primitives.",
        "compiler.text": "Compiler-lowered string primitives (e.g. text.concat) that link in every target.",
        "compiler.c": "Selected compiler-lowered C runtime targets that require explicit effects and ownership handling.",
    }
    return summaries.get(module_name, "Compiler-lowered call targets.")


def _compiler_module_doc_payload(module_name: str) -> dict:
    targets = [
        _target_doc_payload(None, module_name, target)
        for target in sorted(STD_DOC_STATIC_TARGETS.get(module_name, {}))
    ]
    module_short_name = _std_module_short_name(module_name)
    summary = _compiler_module_summary(module_name)
    return {
        "module": module_name,
        "moduleName": module_short_name,
        "sourceFile": "",
        "location": {},
        "summary": summary,
        "summarySource": "comment:static-target-contract",
        "purpose": summary,
        "invariants": ["These targets are owned by compiler lowering; do not add import rows for compiler.* modules."],
        "comments": [],
        "commentsByTag": {},
        "metadata": {},
        "operationDocStatus": "no-operation-docs",
        "operationCount": 0,
        "publicOperationCount": 0,
        "callTargets": targets,
    }


def _compiler_module_docs(module_name: str = "") -> list[dict]:
    modules = []
    for compiler_module in sorted(name for name in STD_DOC_STATIC_TARGETS if name.startswith("compiler.")):
        if _std_module_matches(compiler_module, module_name):
            modules.append(_compiler_module_doc_payload(compiler_module))
    return modules


def _compact_module_doc(module_doc: dict) -> dict:
    return {
        "module": module_doc.get("module", ""),
        "moduleName": module_doc.get("moduleName", ""),
        "sourceFile": module_doc.get("sourceFile", ""),
        "location": module_doc.get("location", {}),
        "summary": module_doc.get("summary", ""),
        "summarySource": module_doc.get("summarySource", ""),
        "purpose": module_doc.get("purpose", ""),
        "operationDocStatus": module_doc.get("operationDocStatus", ""),
        "operationCount": module_doc.get("operationCount", 0),
        "publicOperationCount": module_doc.get("publicOperationCount", 0),
        "callTargetCount": len(module_doc.get("callTargets", [])),
    }


def _docs_inventory(module_name: str = "", summary_tag: str = "rationale", std_root: Path | None = None) -> tuple[list[dict], list[dict], list[str], Path]:
    semlint = _load_semlint_module()
    root = _docs_std_root(std_root)
    errors: list[str] = []
    operations: list[dict] = []
    modules: list[dict] = []
    if not root.exists():
        return operations, modules, [f"{root}: standard-library root does not exist"], root
    if not root.is_dir():
        return operations, modules, [f"{root}: standard-library root is not a directory"], root
    main_files = _std_main_files(root)
    if not main_files:
        return operations, modules, [f"{root}: no standard-library module main.sem files found"], root
    for path in main_files:
        if not _std_module_path_matches(path, module_name):
            continue
        try:
            facts = semlint.parse_file(path)
        except (OSError, RuntimeError) as exc:
            errors.append(f"{path}: {exc}")
            continue
        parsed_module_name = _row_value(facts, "module")
        if not _std_module_matches(parsed_module_name, module_name):
            continue
        module_operations = []
        for operation in sorted(facts.operations.values(), key=lambda item: item.line.number):
            operation_doc = _std_operation_doc_payload(facts, path, operation, summary_tag)
            operations.append(operation_doc)
            module_operations.append(operation_doc)
        modules.append(_std_module_doc_payload(facts, path, module_operations, summary_tag))
    modules.extend(_compiler_module_docs(module_name))
    return operations, modules, errors, root


def _docs_next_commands(
    command: str,
    operation_name: str,
    module_name: str,
    status: str,
    *,
    has_operations: bool = True,
    has_targets: bool = False,
    std_root: Path | None = None,
) -> list[dict]:
    std_path_args = ["--std-path", str(std_root)] if std_root is not None else []
    if command == "list":
        if not has_operations and not has_targets:
            return []
        argv = ["sem", "docs", "get", *std_path_args]
        if module_name:
            argv.extend(["--module", module_name])
        argv.append("--json")
        required_name = "operation" if has_operations else "target"
        required_description = "operation name from the docs list output" if has_operations else "call target from moduleDocs.callTargets"
        return [
            _next_command_entry(
                "docs",
                "inspect one documented API before generating call rows",
                argv=argv,
                command=_display_command(["sem", "docs", "get", *std_path_args, required_name.upper(), "--json"]),
                replayable=False,
                required_args=[{
                    "name": required_name,
                    "position": "final",
                    "description": required_description,
                }],
            )
        ]
    if status == "not-found":
        argv = ["sem", "docs", "list", *std_path_args, "--json"]
        if module_name:
            argv.extend(["--module", module_name])
        return [
            _next_command_entry(
                "docs",
                "list available documented operations, call targets, and types after a failed lookup",
                argv=argv,
            ),
            _next_command_entry(
                "docs-search",
                "search the indexed docs for nearby API, type, syntax, or runtime feature names before guessing",
                argv=["sem", "docs", "search", operation_name or "<query>", "--path", ".", "--json"],
                replayable=bool(operation_name),
                mcp_tool="docs_search",
                mcp_args={
                    "query": operation_name or "<query>",
                    "path": ".",
                    "watch": True,
                    "include_std": True,
                },
            ),
            _next_command_entry(
                "skills",
                "load the syntax reference when the missing name may be a row, verb, type, or enum form",
                argv=["sem", "skills", "get", "sem-syntax", "--full", "--json"],
                mcp_tool="skills_get",
                mcp_args={"names": ["sem-syntax"], "full": True},
            ),
        ]
    if status == "ambiguous":
        return [
            _next_command_entry(
                "docs",
                "disambiguate the operation lookup with --module",
                argv=["sem", "docs", "get", *std_path_args, "--module", "MODULE", operation_name, "--json"],
                replayable=False,
                required_args=[{
                    "name": "module",
                    "position": "--module",
                    "description": "module name from matches, such as http, standard.http, or compiler.console",
                }],
            )
        ]
    return []


@functools.lru_cache(maxsize=1)
def _libc_registry():
    """Load the compiler's libc registry as a standalone module.

    `sem.py` puts `SemanticScript/` on sys.path, but the registry lives under
    `SemanticScript/compiler/`, so load it directly by path. The registry is the
    single source of truth for `c.*` call targets; reusing it keeps `sem docs
    get c.<fn>` in lockstep with what the compiler will actually lower."""
    spec = importlib.util.spec_from_file_location(
        "libc_registry", str(ROOT / "compiler" / "libc_registry.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _libc_wrapper_policy_payload(operation_name: str) -> dict:
    name = (operation_name or "").strip()
    if not name.startswith("c.") or len(name) <= 2:
        return {}
    try:
        registry = _libc_registry()
    except OSError:
        return {}
    policy_for = getattr(registry, "c_wrapper_policy_for", None)
    if not callable(policy_for):
        return {}
    policy = policy_for(name)
    if not policy:
        return {}
    return {
        "decision": policy.get("decision", ""),
        "module": policy.get("module", ""),
        "reason": policy.get("reason", ""),
        "symbol": policy.get("symbol", ""),
        "semanticName": policy.get("semanticName", ""),
    }


def _libc_memory_contract_payload(c_symbol: str, inputs: list[dict]) -> tuple[list[dict], list[dict], dict, list[str]]:
    """Return safer fallback docs for raw libc memory-buffer targets."""
    memory_input_names = {
        "memcpy": ["destination", "source", "byteCount"],
        "wmemcpy": ["destination", "source", "byteCount"],
        "memmove": ["destination", "source", "byteCount"],
        "wmemmove": ["destination", "source", "byteCount"],
        "memcmp": ["leftBuffer", "rightBuffer", "byteCount"],
        "wmemcmp": ["leftBuffer", "rightBuffer", "byteCount"],
        "memset": ["destination", "value", "byteCount"],
        "wmemset": ["destination", "value", "byteCount"],
        "memcpy_s": ["destination", "destinationSize", "source", "byteCount"],
        "memmove_s": ["destination", "destinationSize", "source", "byteCount"],
        "memset_s": ["destination", "destinationSize", "value", "byteCount"],
    }
    names = memory_input_names.get(c_symbol)
    if not names:
        return inputs, [], {"kind": "none", "text": "", "source": ""}, []
    renamed_inputs = [
        {**item, "name": names[index] if index < len(names) else item.get("name", f"arg{index}")}
        for index, item in enumerate(inputs)
    ]
    reads_buffer = "source" in names or "leftBuffer" in names or "rightBuffer" in names
    writes_buffer = "destination" in names and c_symbol not in {"memcmp", "wmemcmp"}
    effects = []
    if reads_buffer:
        effects.append({"action": "read", "path": "memory.buffer"})
    if writes_buffer:
        effects.append({"action": "write", "path": "memory.buffer"})
    if c_symbol in {"memcpy_s", "memmove_s", "memset_s"}:
        failure_mode = {
            "kind": "status-code",
            "text": "A non-zero status reports invalid pointers, invalid sizes, overlap violations, or runtime constraint failure.",
            "source": "libc-memory-contract",
        }
    else:
        failure_mode = {
            "kind": "caller-precondition",
            "text": "Caller must ensure every buffer pointer is non-null and each readable or writable range covers byteCount bytes; use memmove for overlapping ranges.",
            "source": "libc-memory-contract",
        }
    warnings = [
        f"Raw c.{c_symbol} is a memory-buffer escape hatch. Prefer standard.memory wrappers with explicit capacity and overlap policy."
    ]
    return renamed_inputs, effects, failure_mode, warnings


def _libc_target_doc(operation_name: str) -> dict | None:
    """Build a docs target for a `c.<fn>` libc call from the libc registry.

    Returns None when the name is not a `c.*` target or is not a known libc
    function, so the caller can fall through to its normal not-found handling.
    Previously `sem docs get c.strlen` returned NO MATCH even though the symbol
    exists in the registry and lowers correctly — discovery was trial-and-error."""
    name = (operation_name or "").strip()
    if not name.startswith("c.") or len(name) <= 2:
        return None
    semantic_name = name[2:]
    try:
        registry = _libc_registry()
    except OSError:
        return None
    c_symbol = registry.resolve_c_symbol(semantic_name)
    signature = registry.ALL_FUNCTIONS.get(c_symbol)
    if signature is None:
        return None
    return_type, param_types, var_args = signature
    inputs = [
        {"name": f"arg{index}", "type": param_type}
        for index, param_type in enumerate(param_types)
    ]
    outputs = [] if return_type == "Void" else [{"type": return_type, "values": [return_type]}]
    inputs, effects, failure_mode, contract_warnings = _libc_memory_contract_payload(c_symbol, inputs)
    signature_text = _signature_text(inputs, outputs)
    if var_args:
        signature_text = signature_text.replace(") ->", ", ...) ->", 1)
    call_base = _target_call_base_name(name)
    summary = f"C standard library `{c_symbol}` exposed as the `{name}` call target."
    if c_symbol != semantic_name:
        summary += f" `{name}` is the spec-legal camelCase alias for the C symbol `{c_symbol}`."
    agent_warnings = []
    wrapper_policy = _libc_wrapper_policy_payload(name)
    if var_args:
        summary += (
            " Variadic: after the fixed parameters, append one `argument` row per "
            "conversion in the format string, in order. Variadic arguments are passed "
            "positionally with C default promotions, so a mismatch between the format "
            "string and the argument rows is undefined behavior and can crash at "
            "runtime (this is the known c.snprintf sharp edge)."
        )
        agent_warnings.append(
            "Variadic libc target: argument rows after the format string are "
            "positional and unchecked; a format/argument mismatch is undefined behavior."
        )
    if wrapper_policy:
        decision = wrapper_policy.get("decision", "")
        module = wrapper_policy.get("module", "")
        if decision == "stdlib-wrapper-planned":
            agent_warnings.append(
                f"Raw {name} is an escape hatch. Prefer the {module} wrapper when available."
            )
        elif decision == "native-adapter-required":
            agent_warnings.append(
                f"Raw {name} needs a native adapter before it becomes a normal SemanticScript API."
            )
        elif decision in {"no-public-wrapper", "abi-blocked"}:
            agent_warnings.append(
                f"Raw {name} is classified as {decision}; do not generate app-level calls to it."
            )
    agent_warnings.extend(contract_warnings)
    cleanup = {"required": False, "source": "", "text": ""}
    usage = _target_usage_payload("compiler.c", name, inputs, outputs, effects, [], [], failure_mode, cleanup)
    public = True
    api_tier = "compiler-lowered"
    if wrapper_policy.get("decision") in {"native-adapter-required", "no-public-wrapper", "abi-blocked"}:
        public = False
        api_tier = wrapper_policy.get("decision", api_tier)
        usage = {
            "availableForCodegen": False,
            "reason": f"wrapperPolicy.decision is {wrapper_policy.get('decision')}; use a safer standard-library API or adapter instead",
        }
    return {
        "kind": "callTarget",
        "module": "libc",
        "moduleName": "c",
        "name": call_base,
        "type": "",
        "target": name,
        "qualifiedName": name,
        "fullName": name,
        "exported": False,
        "visibility": {
            "exported": False, "internal": False, "public": public,
            "apiTier": api_tier, "reason": "libc-registry",
        },
        "agentWarnings": agent_warnings,
        "source": "libc-registry",
        "loweringStatus": "lowered",
        "implementationStatus": "lowered",
        "statusTaxonomy": _docs_status_taxonomy(
            "lowered",
            detail="libc registry targets lower through the compiler C interop path unless wrapperPolicy blocks public app generation.",
        ),
        "summary": summary,
        "invariants": [],
        "signature": {"inputs": inputs, "outputs": outputs, "text": signature_text},
        "effects": effects,
        "capabilities": [],
        "capabilityDetails": [],
        "failureMode": failure_mode,
        "cleanup": cleanup,
        "wrapperPolicy": wrapper_policy,
        "usage": usage,
    }


def _docs_payload(
    command: str,
    *,
    operation_name: str = "",
    module_name: str = "",
    summary_tag: str = "rationale",
    include_internal: bool = False,
    std_root: Path | None = None,
) -> dict:
    operations, modules, errors, root = _docs_inventory(module_name, summary_tag, std_root)
    query = {
        "command": command,
        "operation": operation_name,
        "module": module_name,
        "summaryTag": summary_tag,
        "includeInternal": include_internal,
    }
    base = {
        "schemaVersion": DOCS_PAYLOAD_VERSION,
        "tool": {"name": "sem", "version": VERSION},
        "stdRoot": str(root),
        "query": query,
        "errors": errors,
        "statusTaxonomyLegend": DOCS_STATUS_TAXONOMY_LEGEND,
    }
    inventory_blocked = bool(errors) and not operations and not modules
    if command == "list":
        visible_operations = operations if include_internal else [
            operation for operation in operations
            if operation["visibility"]["public"]
        ]
        target_items = [_target_list_item(target) for target in _module_targets(modules)]
        type_docs = _static_type_docs(module_name)
        type_items = [_type_list_item(type_doc) for type_doc in type_docs]
        module_names = sorted({module["module"] for module in modules})
        items = [_std_doc_list_item(operation) for operation in visible_operations]
        has_targets = bool(target_items)
        status = "tool-error" if inventory_blocked else ("partial" if errors else "ok")
        return {
            **base,
            "ok": not errors,
            "status": status,
            "nextCommands": _docs_next_commands(
                "list",
                operation_name,
                module_name,
                status,
                has_operations=bool(items),
                has_targets=has_targets,
                std_root=root,
            ),
            "modules": module_names,
            "moduleDocs": modules,
            "operations": items,
            "targets": target_items,
            "types": type_items,
            "summary": {
                "moduleCount": len(module_names),
                "operationCount": len(items),
                "targetCount": len(target_items),
                "typeCount": len(type_items),
                "scannedOperationCount": len(operations),
                "moduleWithoutOperationDocsCount": sum(1 for module in modules if module["operationDocStatus"] == "no-operation-docs"),
            },
        }
    searchable_operations = operations if include_internal else [
        operation for operation in operations
        if operation["visibility"]["public"]
    ]
    matches = [operation for operation in searchable_operations if _std_operation_matches(operation, operation_name)]
    target_matches = [] if matches else [target for target in _module_targets(modules) if _std_target_matches(target, operation_name)]
    record_type_docs = [record for module in modules for record in module.get("records", [])]
    type_docs = _static_type_docs(module_name) + record_type_docs
    type_matches = [] if matches or target_matches else [type_doc for type_doc in type_docs if _type_doc_matches(type_doc, operation_name)]
    if not matches and not target_matches and not type_matches and not inventory_blocked:
        libc_target = _libc_target_doc(operation_name)
        if libc_target is not None:
            libc_status = "partial" if errors else "ok"
            next_module = operation_name.split(".", 1)[0] if "." in operation_name else module_name
            return {
                **base,
                "ok": not errors,
                "status": libc_status,
                "nextCommands": _docs_next_commands("get", operation_name, next_module, libc_status, std_root=root),
                "operation": {},
                "target": libc_target,
                "type": {},
                "matches": [_target_list_item(libc_target)],
                "moduleDocs": [],
                "moduleDocMode": "compact",
                "summary": {
                    "matchCount": 1,
                    "operationMatchCount": 0,
                    "targetMatchCount": 1,
                    "typeMatchCount": 0,
                    "searchedOperationCount": len(searchable_operations),
                    "searchedTargetCount": len(_module_targets(modules)),
                    "searchedTypeCount": len(type_docs),
                    "scannedOperationCount": len(operations),
                },
            }
    if inventory_blocked:
        status = "tool-error"
        ok = False
    elif not matches and not target_matches and not type_matches:
        status = "not-found"
        ok = False
    elif len(matches) + len(target_matches) + len(type_matches) > 1:
        status = "ambiguous"
        ok = False
    elif errors:
        status = "partial"
        ok = False
    else:
        status = "ok"
        ok = True
    if matches:
        matched_module_names = {operation["module"] for operation in matches}
        payload_modules = [module for module in modules if module["module"] in matched_module_names]
    elif target_matches:
        matched_module_names = {target["module"] for target in target_matches}
        payload_modules = [module for module in modules if module["module"] in matched_module_names]
    elif type_matches:
        matched_module_names = {type_doc["module"] for type_doc in type_matches}
        payload_modules = [module for module in modules if module["module"] in matched_module_names]
    elif module_name:
        payload_modules = modules
    elif "." in operation_name:
        query_module = operation_name.split(".", 1)[0]
        payload_modules = [module for module in modules if _std_module_matches(module["module"], query_module)]
    else:
        payload_modules = []
    next_module_name = module_name
    if not next_module_name and "." in operation_name:
        next_module_name = operation_name.split(".", 1)[0]
    return {
        **base,
        "ok": ok,
        "status": status,
        "nextCommands": _docs_next_commands("get", operation_name, next_module_name, status, std_root=root),
        "operation": matches[0] if len(matches) == 1 else {},
        "target": target_matches[0] if len(target_matches) == 1 else {},
        "type": type_matches[0] if len(type_matches) == 1 else {},
        "matches": (
            [_std_doc_list_item(operation) for operation in matches]
            + [_target_list_item(target) for target in target_matches]
            + [_type_list_item(type_doc) for type_doc in type_matches]
        ),
        "moduleDocs": [_compact_module_doc(module) for module in payload_modules],
        "moduleDocMode": "compact",
        "summary": {
            "matchCount": len(matches) + len(target_matches) + len(type_matches),
            "operationMatchCount": len(matches),
            "targetMatchCount": len(target_matches),
            "typeMatchCount": len(type_matches),
            "searchedOperationCount": len(searchable_operations),
            "searchedTargetCount": len(_module_targets(modules)),
            "searchedTypeCount": len(type_docs),
            "scannedOperationCount": len(operations),
        },
    }


def _docs_default_db_path(path: Path) -> Path:
    root = path.parent if path.is_file() or path.suffix.lower() in {".sem", ".sscript"} else path
    return (root / ".sem" / "docs.sqlite").resolve()


def _docs_file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _docs_project_source_files(path: Path) -> tuple[list[Path], list[str]]:
    requested = path.resolve()
    if requested.is_file():
        if requested.suffix.lower() in {".sem", ".sscript"} or requested.name.lower() in {"build.sem", "build.sscript"}:
            return _symbol_source_files(requested)
        return [], [f"{requested}: not a SemanticScript source file"]
    build_tape = _find_build_tape(requested)
    if build_tape is not None:
        return _symbol_source_files(requested)
    if not requested.exists():
        return [], [f"{requested}: path does not exist"]
    if not requested.is_dir():
        return [], [f"{requested}: path is not a directory"]
    ignored_parts = {".git", ".sem", ".claude", "build", "dist", "__pycache__"}
    files = []
    for source in sorted(requested.rglob("*.sem")):
        if not source.is_file():
            continue
        if any(part in ignored_parts for part in source.relative_to(requested).parts[:-1]):
            continue
        files.append(source.resolve())
    for source in sorted(requested.rglob("*.sscript")):
        if not source.is_file():
            continue
        if any(part in ignored_parts for part in source.relative_to(requested).parts[:-1]):
            continue
        files.append(source.resolve())
    deduped = []
    seen = set()
    for source in files:
        if source in seen:
            continue
        seen.add(source)
        deduped.append(source)
    return deduped, []


def _docs_mark_source_kind(payload: dict, source_kind: str, root: Path) -> dict:
    payload = copy.deepcopy(payload)
    payload["sourceKind"] = source_kind
    payload["docsRoot"] = str(root.resolve())
    return payload


def _docs_module_doc_with_source_kind(module_doc: dict, source_kind: str, root: Path) -> dict:
    module_doc = _docs_mark_source_kind(module_doc, source_kind, root)
    module_doc["callTargets"] = [
        _docs_mark_source_kind(target, source_kind, root)
        for target in module_doc.get("callTargets", [])
    ]
    return module_doc


def _docs_project_inventory(
    path: Path,
    module_name: str = "",
    summary_tag: str = "rationale",
) -> tuple[list[dict], list[dict], list[str], Path, list[Path]]:
    semlint = _load_semlint_module()
    root = path.resolve()
    source_files, errors = _docs_project_source_files(root)
    operations: list[dict] = []
    modules: list[dict] = []
    for source in source_files:
        try:
            facts = semlint.parse_file(source)
        except (OSError, RuntimeError) as exc:
            errors.append(f"{source}: {exc}")
            continue
        parsed_module_name = _row_value(facts, "module")
        if not parsed_module_name and not facts.operations:
            continue
        if not _std_module_matches(parsed_module_name, module_name):
            continue
        module_operations = []
        for operation in sorted(facts.operations.values(), key=lambda item: item.line.number):
            operation_doc = _std_operation_doc_payload(facts, source, operation, summary_tag)
            operation_doc = _docs_mark_source_kind(operation_doc, "project", root)
            operations.append(operation_doc)
            module_operations.append(operation_doc)
        module_doc = _std_module_doc_payload(facts, source, module_operations, summary_tag)
        modules.append(_docs_module_doc_with_source_kind(module_doc, "project", root))
    return operations, modules, errors, root, source_files


def _docs_json_compact(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _docs_entry_location(payload: dict) -> dict:
    location = payload.get("location", {}) if isinstance(payload, dict) else {}
    if location:
        return location
    return {}


def _docs_entry_search_text(payload: dict) -> str:
    parts: list[str] = []

    def add(value) -> None:
        if value is None:
            return
        if isinstance(value, str):
            if value.strip():
                parts.append(value.strip())
            return
        if isinstance(value, (int, float, bool)):
            parts.append(str(value))
            return
        if isinstance(value, dict):
            for item in value.values():
                add(item)
            return
        if isinstance(value, list):
            for item in value:
                add(item)

    for key in (
        "kind", "module", "moduleName", "name", "qualifiedName", "fullName",
        "target", "summary", "purpose", "invariants", "agentWarnings",
        "representation", "repr", "underlyingType", "cases", "usage", "exampleRows",
        "status", "implementationStatus", "availability", "enabled", "terms",
        "migration",
    ):
        add(payload.get(key))
    add(payload.get("signature", {}).get("text"))
    for item in payload.get("signature", {}).get("inputs", []):
        add(item.get("name"))
        add(item.get("type"))
    for item in payload.get("signature", {}).get("outputs", []):
        add(item.get("type"))
        add(item.get("values"))
    for effect in payload.get("effects", []):
        add(effect.get("action"))
        add(effect.get("path"))
    for capability in payload.get("capabilityDetails", []):
        add(capability.get("name"))
        add(capability.get("resource"))
        add(capability.get("action"))
    add(payload.get("commentsByTag", {}))
    add(payload.get("metadata", {}))
    usage = payload.get("usage", {})
    if isinstance(usage, dict):
        add(usage.get("failureMode", {}))
        add(usage.get("failureHandling", {}))
        add(usage.get("preconditions", {}))
        add(usage.get("cleanup", {}))
        add(usage.get("migration", {}))
    else:
        add(usage)
    return "\n".join(parts)


def _docs_entry_from_payload(kind: str, payload: dict, root: Path, source_kind: str) -> dict:
    location = _docs_entry_location(payload)
    signature = payload.get("signature", {}) if isinstance(payload.get("signature", {}), dict) else {}
    name = payload.get("name") or payload.get("target") or payload.get("module") or ""
    qualified_name = payload.get("qualifiedName") or payload.get("target") or payload.get("module") or name
    full_name = payload.get("fullName") or qualified_name
    path = location.get("path") or location.get("file") or payload.get("sourceFile") or ""
    line = int(location.get("line", 0) or 0)
    search_text = _docs_entry_search_text({**payload, "kind": kind})
    return {
        "sourceKind": source_kind,
        "kind": kind,
        "module": payload.get("module", ""),
        "moduleName": payload.get("moduleName", ""),
        "name": name,
        "qualifiedName": qualified_name,
        "fullName": full_name,
        "target": payload.get("target", ""),
        "path": path,
        "line": line,
        "root": str(root.resolve()),
        "summary": payload.get("summary", ""),
        "signatureText": signature.get("text", ""),
        "searchText": search_text,
        "doc": payload,
    }


def _docs_collect_index_entries(
    project_path: Path | None,
    *,
    include_project: bool = True,
    include_std: bool = True,
    include_compiler: bool = True,
    summary_tag: str = "rationale",
    std_root: Path | None = None,
) -> tuple[list[dict], list[dict], list[str], dict]:
    entries: list[dict] = []
    documents: list[dict] = []
    errors: list[str] = []
    roots: dict[str, str] = {}

    if include_project and project_path is not None:
        project_operations, project_modules, project_errors, project_root, source_files = _docs_project_inventory(project_path, summary_tag=summary_tag)
        errors.extend(project_errors)
        roots["project"] = str(project_root.resolve())
        for source in source_files:
            if source.exists():
                stat = source.stat()
                documents.append({
                    "path": str(source.resolve()),
                    "root": str(project_root.resolve()),
                    "sourceKind": "project",
                    "hash": _docs_file_hash(source),
                    "mtime": stat.st_mtime,
                })
        for operation in project_operations:
            entries.append(_docs_entry_from_payload("operation", operation, project_root, "project"))
        for module_doc in project_modules:
            entries.append(_docs_entry_from_payload("module", module_doc, project_root, "project"))
            for target in module_doc.get("callTargets", []):
                entries.append(_docs_entry_from_payload("callTarget", target, project_root, "project"))

    if include_std or include_compiler:
        std_operations, std_modules, std_errors, resolved_std_root = _docs_inventory(summary_tag=summary_tag, std_root=std_root)
        errors.extend(std_errors)
        if include_std:
            roots["std"] = str(resolved_std_root.resolve())
        if include_compiler:
            roots["compiler"] = str(resolved_std_root.resolve())
        for module_doc in std_modules:
            module_source_kind = "compiler" if module_doc.get("module", "").startswith("compiler.") else "std"
            if module_source_kind == "std" and not include_std:
                continue
            if module_source_kind == "compiler" and not include_compiler:
                continue
            module_root = resolved_std_root
            module_doc = _docs_module_doc_with_source_kind(module_doc, module_source_kind, module_root)
            entries.append(_docs_entry_from_payload("module", module_doc, module_root, module_source_kind))
            source_file = module_doc.get("sourceFile", "")
            if source_file:
                source_path = Path(source_file)
                if source_path.exists():
                    stat = source_path.stat()
                    documents.append({
                        "path": str(source_path.resolve()),
                        "root": str(module_root.resolve()),
                        "sourceKind": module_source_kind,
                        "hash": _docs_file_hash(source_path),
                        "mtime": stat.st_mtime,
                    })
            for target in module_doc.get("callTargets", []):
                entries.append(_docs_entry_from_payload("callTarget", target, module_root, module_source_kind))
        if include_std:
            for operation in std_operations:
                if operation.get("module", "").startswith("compiler."):
                    continue
                operation = _docs_mark_source_kind(operation, "std", resolved_std_root)
                entries.append(_docs_entry_from_payload("operation", operation, resolved_std_root, "std"))
        for type_doc in _static_type_docs():
            type_source_kind = "compiler" if type_doc.get("module", "").startswith("compiler.") else "std"
            if type_source_kind == "std" and not include_std:
                continue
            if type_source_kind == "compiler" and not include_compiler:
                continue
            entries.append(_docs_entry_from_payload("type", type_doc, resolved_std_root, type_source_kind))
        if include_compiler:
            roots["syntax"] = str(SYNTAX_INVENTORY_PATH.parent.resolve())
            roots["language"] = str((ROOT.parent / "docs" / "language").resolve())
            roots["runtime"] = str((ROOT / "runtime").resolve())
            for guide_doc in _language_guide_docs():
                entries.append(_docs_entry_from_payload("languageGuide", guide_doc, ROOT.parent, "language"))
            for feature_doc in _syntax_feature_docs():
                entries.append(_docs_entry_from_payload("syntaxFeature", feature_doc, ROOT.parent, "syntax"))
            for feature_doc in _runtime_feature_docs():
                entries.append(_docs_entry_from_payload("runtimeFeature", feature_doc, ROOT.parent, "runtime"))
    return entries, documents, errors, roots


def _docs_connect_index(db_path: Path) -> sqlite3.Connection:
    db_path = db_path.resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except sqlite3.DatabaseError:
        pass
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _docs_connect_index_readonly(db_path: Path) -> sqlite3.Connection:
    db_path = db_path.resolve()
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _docs_close_quietly(conn: sqlite3.Connection | None) -> None:
    if conn is None:
        return
    try:
        conn.close()
    except sqlite3.DatabaseError:
        pass


def _docs_sqlite_vec_load(conn: sqlite3.Connection) -> tuple[bool, str]:
    try:
        import sqlite_vec  # type: ignore
    except Exception as exc:
        return False, f"sqlite-vec unavailable: {exc}"
    try:
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        return True, "sqlite-vec loaded"
    except Exception as exc:
        try:
            conn.enable_load_extension(False)
        except Exception:
            pass
        return False, f"sqlite-vec load failed: {exc}"


def _docs_ensure_index_schema(conn: sqlite3.Connection, *, enable_sqlite_vec: bool = True) -> dict:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS docs_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS docs_documents (
            path TEXT PRIMARY KEY,
            root TEXT NOT NULL,
            source_kind TEXT NOT NULL,
            hash TEXT NOT NULL,
            mtime REAL NOT NULL,
            indexed_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS docs_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            root TEXT NOT NULL,
            source_kind TEXT NOT NULL,
            kind TEXT NOT NULL,
            module TEXT NOT NULL,
            module_name TEXT NOT NULL,
            name TEXT NOT NULL,
            qualified_name TEXT NOT NULL,
            full_name TEXT NOT NULL,
            target TEXT NOT NULL,
            path TEXT NOT NULL,
            line INTEGER NOT NULL,
            summary TEXT NOT NULL,
            signature_text TEXT NOT NULL,
            search_text TEXT NOT NULL,
            doc_json TEXT NOT NULL,
            embedding_provider TEXT NOT NULL,
            embedding_model TEXT NOT NULL,
            embedding_status TEXT NOT NULL,
            embedding BLOB,
            updated_at REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS docs_entries_lookup_idx ON docs_entries(qualified_name, full_name, target, name);
        CREATE INDEX IF NOT EXISTS docs_entries_scope_idx ON docs_entries(root, source_kind, kind, module);
        """
    )
    conn.execute("INSERT OR REPLACE INTO docs_meta(key, value) VALUES (?, ?)", ("schemaVersion", str(DOCS_INDEX_SCHEMA_VERSION)))
    fts_available = True
    try:
        conn.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS docs_fts USING fts5(name, module, summary, body, entry_id UNINDEXED)"
        )
    except sqlite3.DatabaseError:
        fts_available = False
    sqlite_vec_loaded = False
    sqlite_vec_message = "disabled"
    sqlite_vec_table = False
    if enable_sqlite_vec:
        sqlite_vec_loaded, sqlite_vec_message = _docs_sqlite_vec_load(conn)
        if sqlite_vec_loaded:
            try:
                conn.execute(
                    f"CREATE VIRTUAL TABLE IF NOT EXISTS docs_vec USING vec0(embedding float[{DOCS_DEFAULT_EMBEDDING_DIMENSIONS}])"
                )
                sqlite_vec_table = True
            except sqlite3.DatabaseError as exc:
                sqlite_vec_message = f"sqlite-vec table unavailable: {exc}"
                sqlite_vec_table = False
    return {
        "ftsAvailable": fts_available,
        "sqliteVecAvailable": sqlite_vec_loaded and sqlite_vec_table,
        "sqliteVecMessage": sqlite_vec_message,
    }


def _docs_validate_index_schema(conn: sqlite3.Connection, *, enable_sqlite_vec: bool = True) -> tuple[dict, list[str]]:
    errors: list[str] = []
    expected_tables = {"docs_meta", "docs_documents", "docs_entries"}
    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'virtual table')")
    }
    missing = sorted(expected_tables - tables)
    if missing:
        errors.append(f"missing docs index tables: {', '.join(missing)}")
    expected_entry_columns = {
        "id", "root", "source_kind", "kind", "module", "module_name", "name",
        "qualified_name", "full_name", "target", "path", "line", "summary",
        "signature_text", "search_text", "doc_json", "embedding_provider",
        "embedding_model", "embedding_status", "embedding", "updated_at",
    }
    if "docs_entries" in tables:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(docs_entries)")}
        missing_columns = sorted(expected_entry_columns - columns)
        if missing_columns:
            errors.append(f"docs_entries missing columns: {', '.join(missing_columns)}")
    expected_document_columns = {"path", "root", "source_kind", "hash", "mtime", "indexed_at"}
    if "docs_documents" in tables:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(docs_documents)")}
        missing_columns = sorted(expected_document_columns - columns)
        if missing_columns:
            errors.append(f"docs_documents missing columns: {', '.join(missing_columns)}")
    meta = {}
    if "docs_meta" in tables:
        try:
            meta = {row["key"]: row["value"] for row in conn.execute("SELECT key, value FROM docs_meta")}
        except sqlite3.DatabaseError as exc:
            errors.append(f"docs_meta unreadable: {exc}")
    schema_version = meta.get("schemaVersion", "")
    if schema_version and schema_version != str(DOCS_INDEX_SCHEMA_VERSION):
        errors.append(f"docs index schema version {schema_version} is not supported by this tool")
    fts_available = "docs_fts" in tables
    sqlite_vec_available = False
    sqlite_vec_message = "not indexed"
    if enable_sqlite_vec and "docs_vec" in tables:
        loaded, message = _docs_sqlite_vec_load(conn)
        sqlite_vec_available = loaded
        sqlite_vec_message = message
    return {
        "ftsAvailable": fts_available,
        "sqliteVecAvailable": sqlite_vec_available,
        "sqliteVecMessage": sqlite_vec_message,
    }, errors


def _docs_clear_index(conn: sqlite3.Connection, *, fts_available: bool, sqlite_vec_available: bool) -> None:
    if fts_available:
        try:
            conn.execute("DELETE FROM docs_fts")
        except sqlite3.DatabaseError:
            pass
    if sqlite_vec_available:
        try:
            conn.execute("DELETE FROM docs_vec")
        except sqlite3.DatabaseError:
            pass
    conn.execute("DELETE FROM docs_entries")
    conn.execute("DELETE FROM docs_documents")


def _docs_rebuild_index_schema(conn: sqlite3.Connection) -> None:
    for table_name in ("docs_vec", "docs_fts", "docs_entries", "docs_documents", "docs_meta"):
        try:
            conn.execute(f"DROP TABLE IF EXISTS {table_name}")
        except sqlite3.DatabaseError:
            pass


def _docs_tokens(text: str) -> list[str]:
    return [token.lower() for token in re.findall(r"[A-Za-z0-9]+", text or "")]


_DOCS_SENTENCE_TRANSFORMER_CACHE: dict[str, object] = {}


def _docs_sentence_transformer_embedding(
    text: str,
    model_name: str,
    *,
    query: bool = False,
    allow_model_download: bool = DOCS_DEFAULT_ALLOW_MODEL_DOWNLOAD,
) -> list[float]:
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore
    except Exception as exc:
        raise RuntimeError(f"sentence-transformers unavailable: {exc}") from exc
    model = _DOCS_SENTENCE_TRANSFORMER_CACHE.get(model_name)
    if model is None:
        model = SentenceTransformer(model_name, local_files_only=not allow_model_download)
        _DOCS_SENTENCE_TRANSFORMER_CACHE[model_name] = model
    prefix = "query: " if query else "passage: "
    encoded = model.encode([prefix + text], normalize_embeddings=True)[0]
    return [float(value) for value in encoded]


def _docs_embedding(
    text: str,
    *,
    provider: str,
    model: str,
    query: bool = False,
    allow_model_download: bool = DOCS_DEFAULT_ALLOW_MODEL_DOWNLOAD,
) -> tuple[list[float] | None, str, str]:
    if provider == "none":
        return None, "disabled", "embedding provider disabled"
    if provider == "sentence-transformers":
        try:
            return _docs_sentence_transformer_embedding(
                text,
                model,
                query=query,
                allow_model_download=allow_model_download,
            ), "fresh", "sentence-transformers"
        except Exception as exc:
            return None, "failed", str(exc)
    if provider == "auto":
        return _docs_embedding(
            text,
            provider="sentence-transformers",
            model=model,
            query=query,
            allow_model_download=allow_model_download,
        )
    return None, "failed", f"unknown embedding provider {provider}"


def _docs_vector_to_blob(vector: list[float] | None) -> bytes | None:
    if vector is None:
        return None
    return array.array("f", vector).tobytes()


def _docs_blob_to_vector(blob: bytes | None) -> list[float]:
    if not blob:
        return []
    values = array.array("f")
    values.frombytes(blob)
    return [float(value) for value in values]


def _docs_cosine(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right))


def _docs_sqlite_vec_serialize(vector: list[float]) -> bytes:
    try:
        import sqlite_vec  # type: ignore
        return sqlite_vec.serialize_float32(vector)
    except Exception:
        return _docs_vector_to_blob(vector) or b""


def _docs_scope_delete(conn: sqlite3.Connection, root: str, source_kind: str, *, fts_available: bool, sqlite_vec_available: bool) -> None:
    ids = [row[0] for row in conn.execute(
        "SELECT id FROM docs_entries WHERE root = ? AND source_kind = ?",
        (root, source_kind),
    )]
    if fts_available:
        for entry_id in ids:
            conn.execute("DELETE FROM docs_fts WHERE rowid = ?", (entry_id,))
    if sqlite_vec_available:
        for entry_id in ids:
            try:
                conn.execute("DELETE FROM docs_vec WHERE rowid = ?", (entry_id,))
            except sqlite3.DatabaseError:
                pass
    conn.execute("DELETE FROM docs_entries WHERE root = ? AND source_kind = ?", (root, source_kind))
    conn.execute("DELETE FROM docs_documents WHERE root = ? AND source_kind = ?", (root, source_kind))


def _docs_insert_entry(
    conn: sqlite3.Connection,
    entry: dict,
    *,
    now: float,
    provider: str,
    model: str,
    fts_available: bool,
    sqlite_vec_available: bool,
    allow_model_download: bool,
) -> tuple[str, str, str]:
    vector, embedding_status, embedding_detail = _docs_embedding(
        entry["searchText"],
        provider=provider,
        model=model,
        allow_model_download=allow_model_download,
    )
    stored_provider = "sentence-transformers" if provider == "auto" else provider
    vector_blob = _docs_vector_to_blob(vector)
    cursor = conn.execute(
        """
        INSERT INTO docs_entries(
            root, source_kind, kind, module, module_name, name, qualified_name,
            full_name, target, path, line, summary, signature_text, search_text,
            doc_json, embedding_provider, embedding_model, embedding_status,
            embedding, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            entry["root"], entry["sourceKind"], entry["kind"], entry["module"], entry["moduleName"],
            entry["name"], entry["qualifiedName"], entry["fullName"], entry["target"], entry["path"],
            entry["line"], entry["summary"], entry["signatureText"], entry["searchText"],
            _docs_json_compact(entry["doc"]), stored_provider, model, embedding_status, vector_blob, now,
        ),
    )
    entry_id = int(cursor.lastrowid)
    if fts_available:
        conn.execute(
            "INSERT INTO docs_fts(rowid, name, module, summary, body, entry_id) VALUES (?, ?, ?, ?, ?, ?)",
            (entry_id, entry["name"], entry["module"], entry["summary"], entry["searchText"], entry_id),
        )
    if sqlite_vec_available and vector is not None and len(vector) == DOCS_DEFAULT_EMBEDDING_DIMENSIONS:
        try:
            conn.execute(
                "INSERT INTO docs_vec(rowid, embedding) VALUES (?, ?)",
                (entry_id, _docs_sqlite_vec_serialize(vector)),
            )
        except sqlite3.DatabaseError as exc:
            embedding_detail = f"{embedding_detail}; sqlite-vec insert failed: {exc}" if embedding_detail else f"sqlite-vec insert failed: {exc}"
    return embedding_status, embedding_detail, stored_provider


def _docs_index_payload(
    path: Path,
    *,
    db_path: Path | None = None,
    include_std: bool = True,
    include_compiler: bool = True,
    summary_tag: str = "rationale",
    std_root: Path | None = None,
    embedding_provider: str = DOCS_DEFAULT_EMBEDDING_PROVIDER,
    embedding_model: str = DOCS_DEFAULT_EMBEDDING_MODEL,
    enable_sqlite_vec: bool = True,
    allow_model_download: bool = DOCS_DEFAULT_ALLOW_MODEL_DOWNLOAD,
) -> dict:
    db_path = (db_path or _docs_default_db_path(path)).resolve()
    entries, documents, errors, roots = _docs_collect_index_entries(
        path,
        include_project=True,
        include_std=include_std,
        include_compiler=include_compiler,
        summary_tag=summary_tag,
        std_root=std_root,
    )
    now = time.time()
    embedding_counts: dict[str, int] = {}
    embedding_messages: set[str] = set()
    effective_embedding_providers: set[str] = set()
    meta_embedding_provider = embedding_provider
    conn: sqlite3.Connection | None = None
    try:
        conn = _docs_connect_index(db_path)
        try:
            schema = _docs_ensure_index_schema(conn, enable_sqlite_vec=enable_sqlite_vec)
        except sqlite3.DatabaseError:
            with conn:
                _docs_rebuild_index_schema(conn)
                schema = _docs_ensure_index_schema(conn, enable_sqlite_vec=enable_sqlite_vec)
        schema, schema_errors = _docs_validate_index_schema(conn, enable_sqlite_vec=enable_sqlite_vec)
        if schema_errors:
            with conn:
                _docs_rebuild_index_schema(conn)
                schema = _docs_ensure_index_schema(conn, enable_sqlite_vec=enable_sqlite_vec)
            schema, schema_errors = _docs_validate_index_schema(conn, enable_sqlite_vec=enable_sqlite_vec)
            if schema_errors:
                _docs_close_quietly(conn)
                return {
                    "schemaVersion": DOCS_INDEX_PAYLOAD_VERSION,
                    "tool": {"name": "sem", "version": VERSION},
                    "ok": False,
                    "status": "stale-schema",
                    "dbPath": str(db_path),
                    "path": str(path.resolve()),
                    "roots": roots,
                    "errors": schema_errors,
                    "summary": {"entryCount": 0, "documentCount": 0, "sourceKinds": [], "embeddingCounts": {}},
                    "features": schema,
                }
        with conn:
            _docs_clear_index(
                conn,
                fts_available=bool(schema["ftsAvailable"]),
                sqlite_vec_available=bool(schema["sqliteVecAvailable"]),
            )
            for document in documents:
                conn.execute(
                    "INSERT OR REPLACE INTO docs_documents(path, root, source_kind, hash, mtime, indexed_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (document["path"], document["root"], document["sourceKind"], document["hash"], document["mtime"], now),
                )
            for entry in entries:
                status, detail, stored_provider = _docs_insert_entry(
                    conn,
                    entry,
                    now=now,
                    provider=embedding_provider,
                    model=embedding_model,
                    fts_available=bool(schema["ftsAvailable"]),
                    sqlite_vec_available=bool(schema["sqliteVecAvailable"]),
                    allow_model_download=allow_model_download,
                )
                embedding_counts[status] = embedding_counts.get(status, 0) + 1
                effective_embedding_providers.add(stored_provider)
                if detail:
                    embedding_messages.add(detail)
            conn.execute("INSERT OR REPLACE INTO docs_meta(key, value) VALUES (?, ?)", ("updatedAt", str(now)))
            meta_embedding_provider = next(iter(effective_embedding_providers)) if len(effective_embedding_providers) == 1 else embedding_provider
            conn.execute("INSERT OR REPLACE INTO docs_meta(key, value) VALUES (?, ?)", ("embeddingProvider", meta_embedding_provider))
            conn.execute("INSERT OR REPLACE INTO docs_meta(key, value) VALUES (?, ?)", ("embeddingModel", embedding_model))
            conn.execute("INSERT OR REPLACE INTO docs_meta(key, value) VALUES (?, ?)", ("includeStd", "true" if include_std else "false"))
            conn.execute("INSERT OR REPLACE INTO docs_meta(key, value) VALUES (?, ?)", ("includeCompiler", "true" if include_compiler else "false"))
        _docs_close_quietly(conn)
    except (OSError, sqlite3.DatabaseError) as exc:
        _docs_close_quietly(conn)
        return {
            "schemaVersion": DOCS_INDEX_PAYLOAD_VERSION,
            "tool": {"name": "sem", "version": VERSION},
            "ok": False,
            "status": "corrupt-index",
            "dbPath": str(db_path),
            "path": str(path.resolve()),
            "roots": roots,
            "errors": [f"{db_path}: docs index could not be written: {exc}"],
            "summary": {"entryCount": 0, "documentCount": 0, "sourceKinds": [], "embeddingCounts": {}},
            "features": {},
        }
    embedding_failed = embedding_provider != "none" and embedding_counts.get("failed", 0) > 0
    all_errors = list(errors)
    if embedding_failed:
        all_errors.append(
            "real semantic embedding generation failed for "
            f"{embedding_counts.get('failed', 0)} docs entries; install sentence-transformers "
            f"and ensure model {embedding_model} is available"
        )
    status = "ok"
    if embedding_failed and errors:
        status = "partial"
    elif embedding_failed:
        status = "embedding-error"
    elif errors:
        status = "partial"
    return {
        "schemaVersion": DOCS_INDEX_PAYLOAD_VERSION,
        "tool": {"name": "sem", "version": VERSION},
        "ok": not all_errors,
        "status": status,
        "dbPath": str(db_path),
        "path": str(path.resolve()),
        "roots": roots,
        "errors": all_errors,
        "summary": {
            "entryCount": len(entries),
            "documentCount": len(documents),
            "sourceKinds": sorted({entry["sourceKind"] for entry in entries}),
            "embeddingCounts": embedding_counts,
        },
        "features": {
            **schema,
            "embeddingProvider": meta_embedding_provider,
            "embeddingModel": embedding_model,
            "allowModelDownload": allow_model_download,
            "embeddingMessages": sorted(embedding_messages),
        },
    }


def _docs_index_status_payload(db_path: Path) -> dict:
    db_path = db_path.resolve()
    if not db_path.exists():
        return {
            "schemaVersion": DOCS_INDEX_PAYLOAD_VERSION,
            "tool": {"name": "sem", "version": VERSION},
            "ok": False,
            "status": "missing",
            "dbPath": str(db_path),
            "summary": {},
            "features": {},
        }
    conn: sqlite3.Connection | None = None
    try:
        conn = _docs_connect_index_readonly(db_path)
        schema, schema_errors = _docs_validate_index_schema(conn, enable_sqlite_vec=True)
        if schema_errors:
            _docs_close_quietly(conn)
            return {
                "schemaVersion": DOCS_INDEX_PAYLOAD_VERSION,
                "tool": {"name": "sem", "version": VERSION},
                "ok": False,
                "status": "stale-schema",
                "dbPath": str(db_path),
                "summary": {},
                "features": schema,
                "errors": schema_errors,
            }
        meta = {row["key"]: row["value"] for row in conn.execute("SELECT key, value FROM docs_meta")}
        source_kinds = [row[0] for row in conn.execute("SELECT DISTINCT source_kind FROM docs_entries ORDER BY source_kind")]
        embedding_counts = {row[0]: row[1] for row in conn.execute("SELECT embedding_status, COUNT(*) FROM docs_entries GROUP BY embedding_status")}
        entry_count = int(conn.execute("SELECT COUNT(*) FROM docs_entries").fetchone()[0])
        document_count = int(conn.execute("SELECT COUNT(*) FROM docs_documents").fetchone()[0])
        _docs_close_quietly(conn)
    except (OSError, sqlite3.DatabaseError) as exc:
        _docs_close_quietly(conn)
        return {
            "schemaVersion": DOCS_INDEX_PAYLOAD_VERSION,
            "tool": {"name": "sem", "version": VERSION},
            "ok": False,
            "status": "corrupt-index",
            "dbPath": str(db_path),
            "summary": {},
            "features": {},
            "errors": [f"{db_path}: docs index is unreadable: {exc}"],
        }
    return {
        "schemaVersion": DOCS_INDEX_PAYLOAD_VERSION,
        "tool": {"name": "sem", "version": VERSION},
        "ok": True,
        "status": "ok",
        "dbPath": str(db_path),
        "summary": {
            "entryCount": entry_count,
            "documentCount": document_count,
            "sourceKinds": source_kinds,
            "embeddingCounts": embedding_counts,
            "updatedAt": meta.get("updatedAt", ""),
        },
        "features": {
            **schema,
            "embeddingProvider": meta.get("embeddingProvider", ""),
            "embeddingModel": meta.get("embeddingModel", ""),
            "includeStd": meta.get("includeStd", ""),
            "includeCompiler": meta.get("includeCompiler", ""),
        },
    }


def _docs_search_fts(conn: sqlite3.Connection, query_text: str, limit: int) -> dict[int, float]:
    tokens = _docs_tokens(query_text)
    if not tokens:
        return {}
    fts_query = " OR ".join(tokens)
    try:
        rows = conn.execute(
            "SELECT rowid, bm25(docs_fts) AS rank FROM docs_fts WHERE docs_fts MATCH ? ORDER BY rank LIMIT ?",
            (fts_query, max(limit * 4, limit)),
        ).fetchall()
    except sqlite3.DatabaseError:
        rows = []
    scores: dict[int, float] = {}
    total = max(len(rows), 1)
    for index, row in enumerate(rows):
        scores[int(row[0])] = (total - index) / total
    return scores


def _docs_search_like(conn: sqlite3.Connection, query_text: str, limit: int) -> dict[int, float]:
    tokens = _docs_tokens(query_text)
    if not tokens:
        return {}
    pattern = "%" + "%".join(tokens) + "%"
    rows = conn.execute(
        "SELECT id FROM docs_entries WHERE lower(search_text) LIKE ? LIMIT ?",
        (pattern, max(limit * 4, limit)),
    ).fetchall()
    total = max(len(rows), 1)
    return {int(row[0]): (total - index) / total for index, row in enumerate(rows)}


def _docs_vector_min_score(provider: str) -> float:
    return 0.15


def _docs_search_vectors(
    conn: sqlite3.Connection,
    query_text: str,
    *,
    provider: str,
    model: str,
    limit: int,
    sqlite_vec_available: bool,
    allow_model_download: bool,
) -> tuple[dict[int, float], str]:
    query_vector, status, detail = _docs_embedding(
        query_text,
        provider=provider,
        model=model,
        query=True,
        allow_model_download=allow_model_download,
    )
    if query_vector is None:
        return {}, detail or status
    if provider == "auto" and "sentence-transformers" in detail:
        effective_backend = "sentence-transformers"
    else:
        effective_backend = provider
    min_score = _docs_vector_min_score(effective_backend)
    if sqlite_vec_available and len(query_vector) == DOCS_DEFAULT_EMBEDDING_DIMENSIONS:
        try:
            vec_count = int(conn.execute("SELECT COUNT(*) FROM docs_vec").fetchone()[0])
            embedding_count = int(conn.execute(
                "SELECT COUNT(*) FROM docs_entries WHERE embedding_status = 'fresh' AND embedding IS NOT NULL "
                "AND embedding_provider = ? AND embedding_model = ?",
                (effective_backend, model),
            ).fetchone()[0])
            joined_count = int(conn.execute(
                "SELECT COUNT(*) FROM docs_vec JOIN docs_entries ON docs_vec.rowid = docs_entries.id "
                "WHERE docs_entries.embedding_status = 'fresh' AND docs_entries.embedding IS NOT NULL "
                "AND docs_entries.embedding_provider = ? AND docs_entries.embedding_model = ?",
                (effective_backend, model),
            ).fetchone()[0])
            if vec_count <= 0 or vec_count != embedding_count or joined_count != embedding_count:
                raise sqlite3.DatabaseError(
                    f"sqlite-vec row count {vec_count} / joined count {joined_count} does not match embedding row count {embedding_count}"
                )
            rows = conn.execute(
                "SELECT rowid, distance FROM docs_vec WHERE embedding MATCH ? AND k = ?",
                (_docs_sqlite_vec_serialize(query_vector), max(limit * 4, limit)),
            ).fetchall()
            scores = {
                int(row[0]): score
                for row in rows
                for score in [1.0 / (1.0 + float(row[1]))]
                if score >= min_score
            }
            return scores, f"sqlite-vec; effectiveBackend={effective_backend}"
        except sqlite3.DatabaseError as exc:
            detail = f"sqlite-vec query failed: {exc}; used python cosine fallback"
    rows = conn.execute(
        "SELECT id, embedding FROM docs_entries WHERE embedding_status = 'fresh' AND embedding IS NOT NULL "
        "AND embedding_provider = ? AND embedding_model = ?",
        (effective_backend, model),
    ).fetchall()
    scored: list[tuple[int, float]] = []
    for row in rows:
        vector = _docs_blob_to_vector(row["embedding"])
        score = _docs_cosine(query_vector, vector)
        if score >= min_score:
            scored.append((int(row["id"]), score))
    scored.sort(key=lambda item: item[1], reverse=True)
    backend = f"python cosine; effectiveBackend={effective_backend}"
    if detail:
        backend = f"{detail}; {backend}"
    return {entry_id: score for entry_id, score in scored[:max(limit * 4, limit)]}, backend


def _docs_structured_boost(row: sqlite3.Row, query_tokens: list[str]) -> float:
    haystacks = {
        "name": row["name"].lower(),
        "qualified": row["qualified_name"].lower(),
        "module": row["module"].lower(),
        "signature": row["signature_text"].lower(),
    }
    target = row["target"].lower()
    boost = 0.0
    for token in query_tokens:
        if token in haystacks["qualified"]:
            boost += 2.0
        elif token in haystacks["name"]:
            boost += 1.5
        elif token in haystacks["module"]:
            boost += 1.0
        elif token in haystacks["signature"]:
            boost += 0.5
    joined = " ".join(query_tokens)
    if joined and joined in haystacks["qualified"]:
        boost += 5.0
    query_set = set(query_tokens)
    if target == "html.fragmentconcat":
        if {"html", "fragment"} <= query_set or {"fragment", "join"} <= query_set:
            boost += 8.0
        if {"render", "list"} <= query_set or {"variable", "length", "list"} <= query_set:
            boost += 8.0
    if target in {"text.concat", "text.concat3"}:
        if {"string", "concat"} <= query_set or {"string", "builder"} <= query_set:
            boost += 6.0
    if target in {"text.fromint64", "text.fromfloat64"}:
        if {"int", "string"} <= query_set or {"integer", "format"} <= query_set:
            boost += 7.0
        if {"format", "number", "text"} <= query_set or {"number", "string"} <= query_set:
            boost += 7.0
    return boost


def _docs_effective_search_limit(limit: int) -> tuple[int, list[str]]:
    if limit < 1:
        return limit, [f"docs search --limit must be at least 1, got {limit}"]
    return min(limit, DOCS_SEARCH_MAX_LIMIT), []


def _docs_result_confidence(
    *,
    exact_boost: float,
    fts_score: float,
    vector_score: float,
    structured_boost: float,
) -> str:
    if exact_boost > 0:
        return "exact"
    if fts_score > 0 and structured_boost >= 2.0 and vector_score >= 0.25:
        return "strong"
    if fts_score > 0 and (structured_boost >= 1.0 or vector_score >= 0.25):
        return "medium"
    return "weak"


def _docs_search_payload(
    query_text: str,
    *,
    db_path: Path,
    limit: int = 10,
    embedding_provider: str = "auto",
    embedding_model: str = "",
    allow_model_download: bool = DOCS_DEFAULT_ALLOW_MODEL_DOWNLOAD,
    include_docs: bool = False,
) -> dict:
    db_path = db_path.resolve()
    requested_limit = limit
    limit, limit_errors = _docs_effective_search_limit(limit)

    def index_next_commands() -> list[dict]:
        return [
            _next_command_entry(
                "docs-index",
                "build the local docs search index before searching from the CLI",
                argv=[
                    "sem", "docs", "index", "--path", ".", "--db", str(db_path),
                    "--include-std", "--embedding-provider", "none", "--json",
                ],
                mcp_tool="docs_reindex",
                mcp_args={
                    "path": ".",
                    "db": str(db_path),
                    "include_std": True,
                    "background": False,
                    "embedding_provider": "none",
                },
            )
        ]

    if limit_errors:
        return {
            "schemaVersion": DOCS_SEARCH_PAYLOAD_VERSION,
            "tool": {"name": "sem", "version": VERSION},
            "ok": False,
            "status": "invalid-arguments",
            "dbPath": str(db_path),
            "query": {"text": query_text, "limit": requested_limit, "requestedLimit": requested_limit},
            "results": [],
            "errors": limit_errors,
        }
    if not db_path.exists():
        return {
            "schemaVersion": DOCS_SEARCH_PAYLOAD_VERSION,
            "tool": {"name": "sem", "version": VERSION},
            "ok": False,
            "status": "index-missing",
            "dbPath": str(db_path),
            "query": {"text": query_text, "limit": limit, "requestedLimit": requested_limit},
            "results": [],
            "errors": [f"{db_path}: docs index does not exist; run sem docs index first"],
            "nextCommands": index_next_commands(),
        }
    conn: sqlite3.Connection | None = None
    try:
        conn = _docs_connect_index_readonly(db_path)
        schema, schema_errors = _docs_validate_index_schema(conn, enable_sqlite_vec=True)
        if schema_errors:
            _docs_close_quietly(conn)
            return {
                "schemaVersion": DOCS_SEARCH_PAYLOAD_VERSION,
                "tool": {"name": "sem", "version": VERSION},
                "ok": False,
                "status": "stale-schema",
                "dbPath": str(db_path),
                "query": {"text": query_text, "limit": limit, "requestedLimit": requested_limit},
                "features": schema,
                "results": [],
                "errors": schema_errors,
            }
        meta = {row["key"]: row["value"] for row in conn.execute("SELECT key, value FROM docs_meta")}
    except (OSError, sqlite3.DatabaseError) as exc:
        _docs_close_quietly(conn)
        return {
            "schemaVersion": DOCS_SEARCH_PAYLOAD_VERSION,
            "tool": {"name": "sem", "version": VERSION},
            "ok": False,
            "status": "corrupt-index",
            "dbPath": str(db_path),
            "query": {"text": query_text, "limit": limit, "requestedLimit": requested_limit},
            "results": [],
            "errors": [f"{db_path}: docs index is unreadable: {exc}"],
        }
    provider = embedding_provider
    if provider == "auto":
        provider = meta.get("embeddingProvider") or DOCS_DEFAULT_EMBEDDING_PROVIDER
    model = embedding_model or meta.get("embeddingModel") or DOCS_DEFAULT_EMBEDDING_MODEL
    try:
        fts_scores = _docs_search_fts(conn, query_text, limit) if schema["ftsAvailable"] else _docs_search_like(conn, query_text, limit)
        if not fts_scores:
            fts_scores = _docs_search_like(conn, query_text, limit)
        vector_scores, vector_backend = _docs_search_vectors(
            conn,
            query_text,
            provider=provider,
            model=model,
            limit=limit,
            sqlite_vec_available=bool(schema["sqliteVecAvailable"]),
            allow_model_download=allow_model_download,
        )
        vector_candidate_ids = set(vector_scores)
        candidate_ids = set(fts_scores) | vector_candidate_ids
        query_tokens = _docs_tokens(query_text)
        if query_tokens:
            exact_rows = conn.execute(
                "SELECT id FROM docs_entries WHERE lower(name) = ? OR lower(qualified_name) = ? OR lower(full_name) = ? OR lower(target) = ?",
                (query_text.lower(), query_text.lower(), query_text.lower(), query_text.lower()),
            ).fetchall()
            candidate_ids.update(int(row[0]) for row in exact_rows)
    except (OSError, sqlite3.DatabaseError, json.JSONDecodeError) as exc:
        _docs_close_quietly(conn)
        return {
            "schemaVersion": DOCS_SEARCH_PAYLOAD_VERSION,
            "tool": {"name": "sem", "version": VERSION},
            "ok": False,
            "status": "corrupt-index",
            "dbPath": str(db_path),
            "query": {"text": query_text, "limit": limit, "requestedLimit": requested_limit, "embeddingProvider": provider, "embeddingModel": model},
            "features": schema,
            "results": [],
            "errors": [f"{db_path}: docs index query failed: {exc}"],
        }
    if not candidate_ids:
        _docs_close_quietly(conn)
        return {
            "schemaVersion": DOCS_SEARCH_PAYLOAD_VERSION,
            "tool": {"name": "sem", "version": VERSION},
            "ok": True,
            "status": "ok",
            "dbPath": str(db_path),
            "query": {"text": query_text, "limit": limit, "requestedLimit": requested_limit, "embeddingProvider": provider, "embeddingModel": model},
            "features": {**schema, "vectorBackend": vector_backend, "includeDocs": include_docs, "allowModelDownload": allow_model_download},
            "results": [],
            "summary": {"resultCount": 0, "candidateCount": 0, "noConfidentMatches": True, "confidenceCounts": {"exact": 0, "strong": 0, "medium": 0, "weak": 0}},
        }
    try:
        placeholders = ",".join("?" for _ in candidate_ids)
        rows = conn.execute(f"SELECT * FROM docs_entries WHERE id IN ({placeholders})", tuple(candidate_ids)).fetchall()
        scored_results = []
        for row in rows:
            entry_id = int(row["id"])
            fts_score = float(fts_scores.get(entry_id, 0.0))
            vector_score = float(vector_scores.get(entry_id, 0.0))
            structured_boost = _docs_structured_boost(row, query_tokens)
            exact_boost = 20.0 if query_text.lower() in {
                row["name"].lower(), row["qualified_name"].lower(), row["full_name"].lower(), row["target"].lower(),
            } else 0.0
            doc = json.loads(row["doc_json"])
            visibility = doc.get("visibility", {}) if isinstance(doc.get("visibility", {}), dict) else {}
            if visibility.get("internal"):
                structured_boost -= 8.0
            elif visibility.get("public"):
                structured_boost += 2.0
            if row["kind"] == "callTarget":
                structured_boost += 1.0
            score = exact_boost + structured_boost + (fts_score * 4.0) + (vector_score * 10.0)
            confidence = _docs_result_confidence(
                exact_boost=exact_boost,
                fts_score=fts_score,
                vector_score=vector_score,
                structured_boost=structured_boost,
            )
            result = {
                "score": score,
                "confidence": confidence,
                "ftsScore": fts_score,
                "vectorScore": vector_score,
                "structuredBoost": structured_boost,
                "sourceKind": row["source_kind"],
                "kind": row["kind"],
                "module": row["module"],
                "moduleName": row["module_name"],
                "name": row["name"],
                "qualifiedName": row["qualified_name"],
                "fullName": row["full_name"],
                "target": row["target"],
                "summary": row["summary"],
                "signature": row["signature_text"],
                "location": {"file": row["path"], "line": row["line"]},
                "freshness": row["embedding_status"],
            }
            if row["kind"] == "syntaxFeature":
                result["implementationStatus"] = doc.get("implementationStatus", "")
            if row["kind"] == "runtimeFeature":
                result["enabled"] = bool(doc.get("enabled", False))
                result["availability"] = doc.get("availability", "")
            if include_docs:
                result["doc"] = doc
            scored_results.append(result)
        scored_results.sort(key=lambda item: item["score"], reverse=True)
        results = scored_results[:limit]
    except (OSError, sqlite3.DatabaseError, json.JSONDecodeError) as exc:
        _docs_close_quietly(conn)
        return {
            "schemaVersion": DOCS_SEARCH_PAYLOAD_VERSION,
            "tool": {"name": "sem", "version": VERSION},
            "ok": False,
            "status": "corrupt-index",
            "dbPath": str(db_path),
            "query": {"text": query_text, "limit": limit, "requestedLimit": requested_limit, "embeddingProvider": provider, "embeddingModel": model},
            "features": schema,
            "results": [],
            "errors": [f"{db_path}: docs index result hydration failed: {exc}"],
        }
    _docs_close_quietly(conn)
    return {
        "schemaVersion": DOCS_SEARCH_PAYLOAD_VERSION,
        "tool": {"name": "sem", "version": VERSION},
        "ok": True,
        "status": "ok",
        "dbPath": str(db_path),
        "query": {"text": query_text, "limit": limit, "requestedLimit": requested_limit, "embeddingProvider": provider, "embeddingModel": model},
        "features": {**schema, "vectorBackend": vector_backend, "includeDocs": include_docs, "allowModelDownload": allow_model_download},
        "results": results,
        "agentGuidance": {
            "codegenSafe": bool(include_docs),
            "text": (
                "Search results are discovery candidates. Use docs get for API/type results, "
                "slice for project anchors, or --include-docs for syntax/runtime feature results "
                "before generating calls that depend on effects, failures, cleanup, capabilities, "
                "preconditions, syntax support, or runtime availability."
            ),
        },
        "summary": {
            "resultCount": len(results),
            "candidateCount": len(candidate_ids),
            "noConfidentMatches": not any(result.get("confidence") in {"exact", "strong", "medium"} for result in results),
            "confidenceCounts": {
                confidence: sum(1 for result in results if result.get("confidence") == confidence)
                for confidence in ("exact", "strong", "medium", "weak")
            },
        },
    }


def _version_payload() -> dict:
    frozen = bool(getattr(sys, "frozen", False))
    def component_path(relative_path: str) -> str:
        if frozen:
            return f"packaged://SemanticScript/{relative_path}"
        return str((ROOT / relative_path).resolve())

    def component_payload(relative_path: str) -> dict:
        payload = {
            "path": component_path(relative_path),
            "version": VERSION,
        }
        if frozen:
            payload["pathKind"] = "packaged-logical"
            payload["pathsEphemeral"] = False
        else:
            payload["pathKind"] = "source-file"
        return payload

    emitted_schemas = [
        "sem.agentDocs.v1",
        "sem.bootstrap.v1",
        "sem.check.v1",
        "sem.context.v1",
        "sem.deps.v1",
        "sem.dev.v1",
        "sem.docs.v1",
        "sem.docsIndex.v1",
        "sem.docsSearch.v1",
        "sem.doctor.v0",
        "sem.eval.v1",
        "sem.explain.v1",
        "sem.fixPlan.v1",
        "sem.graph.v1",
        "sem.help.v1",
        "sem.literalRepin.v1",
        "sem.newProject.v1",
        "sem.patch.v1",
        "sem.readiness.v1",
        "sem.reference.v1",
        "sem.run.v1",
        "sem.self.v1",
        "sem.size.v1",
        "sem.skills.v1",
        "sem.symbols.v1",
        "sem.test.v1",
        "sem.version.v1",
    ]
    return {
        "schemaVersion": "sem.version.v1",
        "tool": {"name": "sem", "version": VERSION},
        "emittedSchemas": emitted_schemas,
        "schemaManifest": {
            "stable": [schema for schema in emitted_schemas if schema.endswith(".v1")],
            "provisional": [schema for schema in emitted_schemas if not schema.endswith(".v1")],
            "policy": "docs/reference/contract-stability.md",
        },
        "compiler": component_payload("compiler/semsc.py"),
        "linter": component_payload("linter/semlint.py"),
        "formatter": component_payload("formatter/semfmt.py"),
        "runtimeFeatureFlags": _runtime_feature_flags(),
        "syntax": {
            "schemaVersion": SYNTAX_PAYLOAD_VERSION,
            "statusCounts": _syntax_status_counts(),
        },
        "packaging": {
            "frozen": frozen,
            "kind": "pyinstaller-onefile" if frozen else "source-python",
            "selfHostedNative": False,
            "executable": str(Path(sys.executable).resolve()),
            "releaseRepository": DEFAULT_RELEASE_REPOSITORY,
            "releaseArtifacts": [
                {
                    "platform": DEFAULT_RELEASE_PLATFORM,
                    "kind": "single-file-windows-exe",
                    "assetNames": [
                        "sem.exe",
                        "semanticscript-sem-windows-x64-<TAG>.exe",
                    ],
                }
            ],
            "tempExtraction": {
                "directoryPattern": "_MEI*",
                "cleanupCommand": "sem clean --pyinstaller-temp --force",
                "note": (
                    "PyInstaller onefile extracts its embedded payload on each "
                    "invocation; source checkouts do not."
                ),
            },
        },
    }


def _collect_facts_bundle(path: Path) -> dict:
    semlint = _load_semlint_module()
    source_files, errors = _symbol_source_files(path)
    bundle = []
    for source in source_files:
        if not source.exists() or source.suffix.lower() not in {".sem", ".sscript"}:
            continue
        try:
            bundle.append({
                "path": source,
                "facts": semlint.parse_file(source),
            })
        except (OSError, RuntimeError) as exc:
            errors.append(str(exc))
    return {
        "semlint": semlint,
        "sourceFiles": source_files,
        "files": bundle,
        "errors": errors,
    }


def _diagnostic_expected_actual(diagnostic: dict) -> tuple[str, str]:
    code = diagnostic.get("code", "")
    kind = diagnostic.get("kind", "")
    gap_edge = diagnostic.get("gapEdge", "")
    subject = diagnostic.get("subjectName", "")
    if code == "SS3104":
        return (
            "capability or authority covering the declared effect",
            f"no capability proof found for {subject or 'operation'}",
        )
    if code == "SS3101":
        return (
            "purpose row describing the operation intent",
            "purpose metadata is missing",
        )
    if code == "SS3102":
        return (
            "invariant row describing the safety or business rule",
            "invariant metadata is missing",
        )
    if code.startswith("SS01"):
        return (
            "at least one valid use site or removal of the dead declaration",
            "no live use sites were discovered",
        )
    if gap_edge:
        return (
            f"supporting `{gap_edge}` row or equivalent evidence",
            "supporting row was not found",
        )
    if kind:
        return (
            f"rule `{kind}` satisfied",
            "rule violation detected",
        )
    return ("valid SemanticScript row graph", "validation gap detected")


def _normalize_lint_diagnostic(diagnostic: dict) -> dict:
    expected, actual = _diagnostic_expected_actual(diagnostic)
    primary = diagnostic.get("primary", {})
    fix_candidates = list(diagnostic.get("fixCandidates", []))
    auto_applicable = any(candidate.get("autoApplicable") for candidate in fix_candidates)
    fix_safety = "requires-human-review"
    if auto_applicable:
        fix_safety = "local-edit"
    elif diagnostic.get("code") in {"SS3104", "SS3101", "SS3102"}:
        fix_safety = "local-edit"
    return {
        "code": diagnostic.get("code", ""),
        "severity": diagnostic.get("severity", ""),
        "source": "linter",
        "kind": diagnostic.get("kind", ""),
        "message": (
            diagnostic.get("intentSlogan")
            or diagnostic.get("invariantRule")
            or diagnostic.get("kind")
            or diagnostic.get("code", "")
        ),
        "span": {
            "file": str(Path(primary.get("path", "")).resolve()) if primary.get("path") else "",
            "line": int(primary.get("line", 0) or 0),
            "column": int(primary.get("column", 0) or 0),
            "role": primary.get("role", ""),
        },
        "subjectName": diagnostic.get("subjectName", ""),
        "subjectKind": diagnostic.get("subjectKind", ""),
        "gapEdge": diagnostic.get("gapEdge", ""),
        "expected": expected,
        "actual": actual,
        "help": diagnostic.get("agentHint", ""),
        "invariantRule": diagnostic.get("invariantRule", ""),
        "specAnchor": diagnostic.get("specAnchor", ""),
        "blocksCompile": bool(diagnostic.get("blocksCompile", False)),
        "confidence": diagnostic.get("confidence", ""),
        "effort": diagnostic.get("effort", ""),
        "citations": list(diagnostic.get("citations", [])),
        "fixCandidates": fix_candidates,
        "repair": {
            "id": fix_candidates[0].get("name", "") if fix_candidates else "",
            "safe": auto_applicable or diagnostic.get("code") in {"SS3104"},
            "fixSafety": fix_safety,
        },
        "explain": {
            "code": diagnostic.get("code", ""),
            "command": f"sem explain {diagnostic.get('code', '')} --json".strip(),
        },
    }


def _collect_lint_diagnostics(path: Path) -> tuple[list[dict], list[str]]:
    bundle = _collect_facts_bundle(path)
    semlint = bundle["semlint"]
    diagnostics: list[dict] = []
    errors: list[str] = list(bundle["errors"])
    for item in bundle["files"]:
        source = item["path"]
        try:
            for diagnostic in semlint.lint_path(source):
                diagnostics.append(_normalize_lint_diagnostic(diagnostic.to_json()))
        except (OSError, RuntimeError) as exc:
            errors.append(f"{source}: {exc}")
    diagnostics.sort(key=lambda item: (
        not item.get("blocksCompile", False),
        item.get("severity", ""),
        item.get("code", ""),
        item.get("span", {}).get("file", ""),
        item.get("span", {}).get("line", 0),
        item.get("span", {}).get("column", 0),
    ))
    return diagnostics, errors


def _compiler_check_probe(source: Path, compiler_args: list[str]) -> dict:
    try:
        proc = _capture_compiler(
            source,
            ["--parse-only", "--lint", "--diagnostics-format", "json", *compiler_args],
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "attempted": True,
            "ok": False,
            "returnCode": 2,
            "stdout": "",
            "stderr": str(exc),
        }
    return {
        "attempted": True,
        "ok": proc.returncode == 0,
        "returnCode": int(proc.returncode),
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def _compiler_lower_check_probe(source: Path, compiler_args: list[str]) -> dict:
    """Run the compiler's full codegen lowering as a preflight (`--lower-check`)
    and report whether it succeeds. This surfaces every codegen-phase error
    (SSCG*/SSBE*) that `--parse-only` cannot, so `check` can make `buildable`
    predict `build`. Slower than the parse probe (it runs codegen), so callers
    should only invoke it when the parse/lint probe is already clean."""
    try:
        proc = _capture_compiler(
            source,
            ["--lower-check", "--quiet", "--diagnostics-format", "json", *compiler_args],
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "attempted": True,
            "ok": False,
            "returnCode": 2,
            "stdout": "",
            "stderr": str(exc),
        }
    return {
        "attempted": True,
        "ok": proc.returncode == 0,
        "returnCode": int(proc.returncode),
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def _normalize_compiler_diagnostic(diagnostic: dict) -> dict:
    primary = diagnostic.get("primary", {}) or {}
    suggested_fixes = list(diagnostic.get("suggestedFixes", []))
    return {
        "code": diagnostic.get("code", ""),
        "severity": diagnostic.get("severity", "error"),
        "source": "compiler",
        "kind": diagnostic.get("phase", ""),
        "message": diagnostic.get("message", ""),
        "span": {
            "file": str(Path(primary.get("path", "")).resolve()) if primary.get("path") else "",
            "line": int(primary.get("line", 0) or 0),
            "column": int(primary.get("column", 0) or 0),
            "role": primary.get("role", ""),
        },
        "subjectName": "",
        "subjectKind": "",
        "gapEdge": "",
        "expected": "SemanticScript source that parses, checks, and lowers successfully",
        "actual": diagnostic.get("message", ""),
        "help": diagnostic.get("agentHint", ""),
        "invariantRule": "",
        "specAnchor": "",
        "blocksCompile": bool(diagnostic.get("blocksCompile", True)),
        "confidence": "high",
        "effort": "unknown",
        "citations": [],
        "fixCandidates": [
            {
                "name": f"compilerFix{index}",
                "shape": suggestion,
                "autoApplicable": False,
            }
            for index, suggestion in enumerate(suggested_fixes, start=1)
        ],
        "repair": {
            "id": "",
            "safe": False,
            "fixSafety": "requires-human-review",
        },
        "compilerPhase": diagnostic.get("phase", ""),
        "semanticStack": list(diagnostic.get("semanticStack", [])),
        "loweringTrace": list(diagnostic.get("loweringTrace", [])),
        "backendExcerpt": diagnostic.get("backendExcerpt", ""),
        "direction": diagnostic.get("direction", ""),
        "explain": {
            "code": diagnostic.get("code", ""),
            "command": f"sem explain {diagnostic.get('code', '')} --json".strip(),
        },
    }


def _parse_error_guidance(message: str) -> tuple[str, list[str]]:
    """Map a bare parser message to actionable help + fix shapes. The parser
    tier had no help/fix candidates (the "worse tier"); this recovers the most
    common cases so an agent gets a concrete next step instead of a raw string."""
    lower = message.lower()
    if "references unknown htmltemplate" in lower or "references unknown template" in lower:
        return (
            "`html body template NAME` instantiates a template that must already "
            "be declared with `html template NAME` earlier in the file. Add the "
            "declaration first.",
            ["html template <name>"],
        )
    if lower.startswith("html requires") or "html requires:" in lower:
        return (
            "Declare `html template NAME`, then open the body with `html body "
            "template NAME` followed by the indented HTML island; {hole} "
            "placeholders become typed hydrate arguments.",
            ["html template <name>", "html body template <name>"],
        )
    if lower.startswith("unknown verb"):
        if "<" in message:  # a markup line read as a verb
            return (
                "This looks like HTML/markup outside an island. Raw markup is only "
                "valid inside an `html body template NAME` block (opened after "
                "`html template NAME`). Open the island first, or quote the text.",
                ["html template <name>", "html body template <name>"],
            )
        return (
            "Unrecognized row verb. Check the spelling against the syntax "
            "inventory; if this is pre-cutover syntax, run `sem migrate-syntax "
            "--diff <file>` then `--write` to upgrade it.",
            ["sem migrate-syntax --write <file>"],
        )
    if "requires: input operation" in lower or "requires: output operation" in lower:
        return (
            "Header rows are subject-qualified: `input operation OP NAME TYPE` / "
            "`output operation OP TYPE`. Run `sem migrate-syntax --write <file>` "
            "to insert the `operation` qualifier automatically.",
            ["sem migrate-syntax --write <file>"],
        )
    if "purpose requires" in lower or "invariant requires" in lower:
        return (
            "`purpose`/`invariant` name their subject kind: e.g. `purpose "
            "operation OP \"...\"`. `purpose` also accepts capability/webServer/"
            "record/etc. Run `sem migrate-syntax --write <file>` for the cutover.",
            ["purpose operation <op> \"...\""],
        )
    if "ignore" in lower and "void" in lower and "discard" in lower:
        return (
            "A Void result is discarded with `ignore void source CALL`, not "
            "`ignore ok ... type Void`.",
            ["ignore void source <call>"],
        )
    return (
        "Inspect the source row named by the parser failure and re-run sem check "
        "after correcting the syntax.",
        [],
    )


def _normalize_compiler_parse_error(stderr_text: str) -> dict | None:
    # Two shapes: with a line number ("... : line 12: msg") and without
    # ("... : msg", e.g. the html-body template errors). Match both.
    # Anchor the path to a source extension so a path containing ": " can't
    # mis-split; fall back to a non-greedy path match if the extension differs.
    match = re.match(
        r"^semsc: parse error in (.+?\.(?:sem|sscript|test\.sem)): (?:line (\d+): )?(.+)$",
        stderr_text.strip(), re.DOTALL)
    if not match:
        match = re.match(
            r"^semsc: parse error in (.+?): (?:line (\d+): )?(.+)$",
            stderr_text.strip(), re.DOTALL)
    if not match:
        return None
    path_text, line_text, message = match.groups()
    message = message.strip()
    help_text, fix_shapes = _parse_error_guidance(message)
    return {
        "code": "SEMSC_PARSE",
        "severity": "error",
        "source": "compiler",
        "kind": "parse",
        "message": message,
        "span": {
            "file": str(Path(path_text).resolve()),
            "line": int(line_text) if line_text else 0,
            "column": 1,
            "role": "compilerError",
        },
        "subjectName": "",
        "subjectKind": "",
        "gapEdge": "",
        "expected": "valid SemanticScript syntax that the parser accepts",
        "actual": message,
        "help": help_text,
        "invariantRule": "",
        "specAnchor": "",
        "blocksCompile": True,
        "confidence": "high",
        "effort": "unknown",
        "citations": [],
        "fixCandidates": [
            {"name": f"parseFix{index}", "shape": shape, "autoApplicable": False}
            for index, shape in enumerate(fix_shapes, start=1)
        ],
        "repair": {
            "id": "",
            "safe": False,
            "fixSafety": "requires-human-review",
        },
        "compilerPhase": "parse",
        "semanticStack": [],
        "loweringTrace": [],
        "backendExcerpt": "",
        "direction": "The parser rejected the current row before semantic analysis or lowering could continue.",
        "explain": {
            "code": "SEMSC_PARSE",
            "command": "",
        },
    }


def _compiler_diagnostics_from_payload(payload) -> list[dict]:
    diagnostics = []
    if isinstance(payload, dict):
        if payload.get("schema") == "semsc.diagnostic.v1":
            diagnostics.append(_normalize_compiler_diagnostic(payload))
    elif isinstance(payload, list):
        for item in payload:
            diagnostics.extend(_compiler_diagnostics_from_payload(item))
    return diagnostics


def _collect_compiler_diagnostics(compiler: dict) -> tuple[list[dict], list[str]]:
    stderr_text = (compiler.get("stderr") or "").strip()
    if compiler.get("ok", False):
        return [], []
    if not stderr_text:
        return [], ["compiler failed without diagnostics output"]
    try:
        parsed = json.loads(stderr_text)
    except json.JSONDecodeError:
        parsed = None
    if parsed is not None:
        diagnostics = _compiler_diagnostics_from_payload(parsed)
        if diagnostics:
            return diagnostics, []

    diagnostics = []
    remainder = []
    for line in stderr_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            parsed_line = json.loads(stripped)
        except json.JSONDecodeError:
            remainder.append(line)
            continue
        line_diagnostics = _compiler_diagnostics_from_payload(parsed_line)
        if line_diagnostics:
            diagnostics.extend(line_diagnostics)
        else:
            remainder.append(line)
    if diagnostics:
        extra = "\n".join(item for item in remainder if item.strip()).strip()
        return diagnostics, ([extra[:2000]] if extra else [])

    parse_error = _normalize_compiler_parse_error(stderr_text)
    if parse_error is not None:
        return [parse_error], []
    return [], [stderr_text[:2000]]


def _stringify_argv(argv: list[object]) -> list[str]:
    return [str(part) for part in argv if str(part)]


def _materialize_cli_argv(argv: list[str]) -> tuple[list[str], list[str]]:
    display_argv = list(argv)
    if display_argv and display_argv[0] == "sem":
        if getattr(sys, "frozen", False):
            return [sys.executable, *display_argv[1:]], display_argv
        return [sys.executable, str((ROOT / "tools" / "sem.py").resolve()), *display_argv[1:]], display_argv
    return display_argv, display_argv


def _display_command(argv: list[str]) -> str:
    return subprocess.list2cmdline(argv)


_MCP_VALUE_FLAGS = {
    "check": {"--with-readiness": False, "--full": False, "--json": False},
    "readiness": {"--json": False},
    "graph": {"--kind": True, "--full": False, "--json": False},
    "slice": {
        "--operation": True,
        "--route": True,
        "--symbol": True,
        "--effect": True,
        "--capability": True,
        "--type": True,
        "--full": False,
        "--json": False,
    },
    "explain": {"--json": False},
    "fix": {"--plan": False, "--include-warnings": False, "--full": False, "--json": False},
    "patch": {"--dry-run": False, "--apply": False, "--json": False},
    "test": {
        "--skip-python-harnesses": False,
        "--allow-red-preflight-harnesses": False,
        "--full": False,
        "--json": False,
    },
    "dev": {"--trace": False, "--full": False, "--json": False},
    "size": {"--json": False},
    "help": {"--json": False},
    "agent-docs": {"--json": False, "--max-bytes": True},
    "skills": {"--json": False, "--all": False, "--full": False},
}


def _sem_argv_positionals(argv: list[str], command: str) -> list[str]:
    value_flags = _MCP_VALUE_FLAGS.get(command, {})
    positionals: list[str] = []
    index = 2
    while index < len(argv):
        token = argv[index]
        takes_value = value_flags.get(token)
        if takes_value is True:
            index += 2
            continue
        if token.startswith("-"):
            index += 1
            continue
        positionals.append(token)
        index += 1
    return positionals


def _sem_argv_flag_value(argv: list[str], flag: str) -> str | None:
    try:
        index = argv.index(flag)
    except ValueError:
        return None
    next_index = index + 1
    if next_index >= len(argv):
        return None
    value = argv[next_index]
    if value.startswith("-"):
        return None
    return value


def _infer_mcp_next_command(argv: list[str]) -> tuple[str | None, dict | None]:
    if len(argv) < 2 or argv[0] != "sem":
        return None, None
    command = argv[1]
    positionals = _sem_argv_positionals(argv, command)
    path = positionals[-1] if positionals else "."

    if command == "check":
        return "check", {
            "path": path,
            "with_readiness": "--with-readiness" in argv,
            "full": "--full" in argv,
        }
    if command == "readiness":
        return "readiness", {"path": path}
    if command == "graph":
        return "graph", {
            "path": path,
            "kind": _sem_argv_flag_value(argv, "--kind") or "summary",
            "full": "--full" in argv,
        }
    if command == "slice":
        args: dict[str, object] = {"path": path, "full": "--full" in argv}
        anchor_flags = {
            "--operation": "operation",
            "--route": "route",
            "--symbol": "symbol",
            "--effect": "effect",
            "--capability": "capability",
            "--type": "type_name",
        }
        for flag, key in anchor_flags.items():
            value = _sem_argv_flag_value(argv, flag)
            if value:
                args[key] = value
                break
        return "slice", args
    if command == "explain":
        code = positionals[0] if positionals else ""
        return "explain", {"code": code}
    if command == "fix":
        return "fix_plan", {
            "path": path,
            "include_warnings": "--include-warnings" in argv,
            "full": "--full" in argv,
        }
    if command == "patch":
        args = {"apply": "--apply" in argv}
        if positionals:
            args["plan_path"] = positionals[-1]
        return "patch", args
    if command == "test":
        return "test", {
            "path": path,
            "skip_python_harnesses": "--skip-python-harnesses" in argv,
            "allow_red_preflight_harnesses": "--allow-red-preflight-harnesses" in argv,
            "full": "--full" in argv,
        }
    if command == "dev":
        return "dev", {"path": path, "trace": "--trace" in argv, "full": "--full" in argv}
    if command == "size":
        return "size", {"path": path}
    if command == "help":
        return "help", {"path": path}
    if command == "agent-docs":
        return "agent_docs", {
            "path": path,
            "max_bytes": int(_sem_argv_flag_value(argv, "--max-bytes") or DEFAULT_AGENT_DOC_MAX_BYTES),
        }
    if command == "skills" and len(argv) >= 3:
        subcommand = argv[2]
        names = [item for item in positionals if item not in {"get", "list"}]
        if subcommand == "list":
            return "skills_list", {}
        if subcommand == "get":
            return "skills_get", {
                "names": names,
                "all_skills": "--all" in argv,
                "full": "--full" in argv,
            }
    return None, None


def _next_command_entry(
    kind: str,
    reason: str,
    *,
    argv: list[object] | None = None,
    command: str | None = None,
    cwd: str | None = None,
    replayable: bool | None = None,
    artifact_inputs: list[dict] | None = None,
    required_args: list[dict] | None = None,
    mcp_tool: str | None = None,
    mcp_args: dict | None = None,
) -> dict:
    entry = {
        "kind": kind,
        "reason": reason,
    }
    normalized_argv = _stringify_argv(argv or [])
    if normalized_argv:
        replay_argv, display_argv = _materialize_cli_argv(normalized_argv)
        entry["argv"] = replay_argv
        entry["command"] = command or _display_command(display_argv)
        entry["cwd"] = cwd or str(Path.cwd().resolve())
        if not mcp_tool:
            inferred_mcp_tool, inferred_mcp_args = _infer_mcp_next_command(normalized_argv)
            mcp_tool = inferred_mcp_tool
            mcp_args = inferred_mcp_args
    elif command:
        entry["command"] = command
        if cwd:
            entry["cwd"] = cwd
    else:
        raise ValueError("next command entries require argv or command")
    if replayable is None:
        replayable = not artifact_inputs and not required_args
    entry["replayable"] = bool(replayable)
    if artifact_inputs:
        entry["artifactInputs"] = artifact_inputs
    if required_args:
        entry["requiredArgs"] = required_args
    if mcp_tool:
        entry["mcpTool"] = mcp_tool
        entry["mcpArgs"] = mcp_args or {}
    return entry


def _append_next_command(
    entries: list[dict],
    seen: set[str],
    kind: str,
    command: str,
    reason: str,
    *,
    argv: list[object] | None = None,
    cwd: str | None = None,
    replayable: bool | None = None,
    artifact_inputs: list[dict] | None = None,
    required_args: list[dict] | None = None,
    mcp_tool: str | None = None,
    mcp_args: dict | None = None,
) -> None:
    dedupe_key = json.dumps(
        {
            "kind": kind,
            "argv": _stringify_argv(argv or []),
            "command": command,
            "artifactInputs": artifact_inputs or [],
            "requiredArgs": required_args or [],
            "mcpTool": mcp_tool or "",
            "mcpArgs": mcp_args or {},
        },
        sort_keys=True,
    )
    if not command or dedupe_key in seen:
        return
    seen.add(dedupe_key)
    entries.append(
        _next_command_entry(
            kind,
            reason,
            argv=argv,
            command=None if argv else command,
            cwd=cwd,
            replayable=replayable,
            artifact_inputs=artifact_inputs,
            required_args=required_args,
            mcp_tool=mcp_tool,
            mcp_args=mcp_args,
        )
    )


def _patch_artifact_input(source_argv: list[object]) -> dict:
    replay_argv, display_argv = _materialize_cli_argv(_stringify_argv(source_argv))
    return {
        "name": "planPath",
        "kind": "file",
        "schemaVersion": "sem.fixPlan.v1",
        "producedBy": {
            "argv": replay_argv,
            "command": _display_command(display_argv),
        },
        "appendAsFinalArg": True,
        "description": "save the full fix-plan JSON to a file and append that path as the final patch argument",
    }


def _is_project_surface(path: Path) -> bool:
    resolved = path.resolve()
    return _find_build_tape(path) is not None or resolved.is_dir()


def _graph_followup_entry(
    path: Path,
    *,
    project_kind: str = "summary",
    file_kind: str = "calls",
    project_reason: str,
    file_reason: str,
) -> dict:
    resolved = str(path.resolve())
    if _is_project_surface(path):
        project_surface = _project_surface_path(path)
        return _next_command_entry(
            "graph",
            project_reason,
            argv=["sem", "graph", "--kind", project_kind, "--json", project_surface],
        )
    return _next_command_entry(
        "graph",
        file_reason,
        argv=["sem", "graph", "--kind", file_kind, "--json", resolved],
    )


def _compact_list(items: list, limit: int) -> tuple[list, dict | None]:
    total = len(items)
    if total <= limit:
        return list(items), None
    return list(items[:limit]), {
        "returned": limit,
        "total": total,
        "truncated": total - limit,
    }


def _top_count_entries(values: list[str], limit: int = 8) -> list[dict]:
    counts = {}
    for value in values:
        if not value:
            continue
        counts[value] = counts.get(value, 0) + 1
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [{"name": name, "count": count} for name, count in ranked[:limit]]


def _diagnostic_focus_anchors(diagnostics: list[dict], limit: int = 5) -> dict:
    return {
        "topFiles": _top_count_entries(
            [item.get("span", {}).get("file", "") for item in diagnostics],
            limit=limit,
        ),
        "topOperations": _top_count_entries(
            [
                item.get("subjectName", "")
                for item in diagnostics
                if item.get("subjectKind") == "operation" and item.get("subjectName")
            ],
            limit=limit,
        ),
        "topRoutes": _top_count_entries(
            [
                item.get("subjectName", "")
                for item in diagnostics
                if item.get("subjectKind") == "route" and item.get("subjectName")
            ],
            limit=limit,
        ),
        "topCodes": _top_count_entries([item.get("code", "") for item in diagnostics], limit=limit),
    }


def _payload_view(payload: dict) -> dict:
    return payload.setdefault("view", {"mode": "compact", "truncation": {}})


def _record_truncation(payload: dict, field: str, window: dict | None) -> None:
    if window is None:
        return
    view = _payload_view(payload)
    view["truncation"][field] = window


def _compact_check_payload_for_cli(path: Path, payload: dict, *, full: bool) -> dict:
    compacted = copy.deepcopy(payload)
    if full:
        compacted["view"] = {"mode": "full", "truncation": {}}
        return compacted
    diagnostics, diagnostics_window = _compact_list(compacted.get("diagnostics", []), CHECK_DIAGNOSTIC_WINDOW)
    compacted["diagnostics"] = diagnostics
    _record_truncation(compacted, "diagnostics", diagnostics_window)
    tool_errors, tool_errors_window = _compact_list(compacted.get("toolErrors", []), CHECK_TOOL_ERROR_WINDOW)
    compacted["toolErrors"] = tool_errors
    compacted["errors"] = list(tool_errors)
    _record_truncation(compacted, "toolErrors", tool_errors_window)
    unresolved, unresolved_window = _compact_list(compacted.get("unresolvedReferences", []), CHECK_REFERENCE_WINDOW)
    compacted["unresolvedReferences"] = unresolved
    _record_truncation(compacted, "unresolvedReferences", unresolved_window)
    if "view" not in compacted:
        compacted["view"] = {"mode": "full", "truncation": {}}
    return compacted


def _compact_fix_payload_for_cli(path: Path, payload: dict, *, full: bool) -> dict:
    compacted = copy.deepcopy(payload)
    if full:
        compacted["view"] = {"mode": "full", "truncation": {}}
        return compacted
    repairs_sorted = sorted(
        compacted.get("repairs", []),
        key=lambda repair: (
            0 if repair.get("edits") and repair.get("fixSafety") in {"safe", "local-edit"} else
            1 if repair.get("reviewEdits") else
            2,
            repair.get("diagnostic", ""),
            repair.get("subjectName", ""),
        ),
    )
    repairs, repairs_window = _compact_list(repairs_sorted, FIX_REPAIR_WINDOW)
    compacted["repairs"] = repairs
    _record_truncation(compacted, "repairs", repairs_window)
    if "view" not in compacted:
        compacted["view"] = {"mode": "full", "truncation": {}}
    return compacted


def _compact_graph_payload_for_cli(path: Path, payload: dict, *, full: bool) -> dict:
    compacted = copy.deepcopy(payload)
    if full:
        compacted["view"] = {"mode": "full", "truncation": {}}
        return compacted
    nodes, nodes_window = _compact_list(compacted.get("nodes", []), GRAPH_NODE_WINDOW)
    edges, edges_window = _compact_list(compacted.get("edges", []), GRAPH_EDGE_WINDOW)
    compacted["nodes"] = nodes
    compacted["edges"] = edges
    _record_truncation(compacted, "nodes", nodes_window)
    _record_truncation(compacted, "edges", edges_window)
    if "view" not in compacted:
        compacted["view"] = {"mode": "full", "truncation": {}}
    return compacted


def _compact_slice_payload_for_cli(path: Path, payload: dict, *, full: bool) -> dict:
    compacted = copy.deepcopy(payload)
    if full:
        compacted["view"] = {"mode": "full", "truncation": {}}
        return compacted
    called_operations, called_window = _compact_list(compacted.get("calledOperations", []), SLICE_CALL_WINDOW)
    callers, callers_window = _compact_list(compacted.get("callers", []), SLICE_CALLER_WINDOW)
    compacted["calledOperations"] = called_operations
    compacted["callers"] = callers
    _record_truncation(compacted, "calledOperations", called_window)
    _record_truncation(compacted, "callers", callers_window)
    operation = compacted.get("operation")
    if isinstance(operation, dict):
        calls, calls_window = _compact_list(operation.get("calls", []), SLICE_CALL_WINDOW)
        control_flow, control_window = _compact_list(operation.get("controlFlow", []), SLICE_CONTROL_FLOW_WINDOW)
        returns, returns_window = _compact_list(operation.get("returns", []), SLICE_RETURN_WINDOW)
        operation["calls"] = [
            {
                "name": call.get("name", ""),
                "target": call.get("target", ""),
                "location": call.get("location", {}),
            }
            for call in calls
        ]
        operation["controlFlow"] = control_flow
        operation["returns"] = returns
        _record_truncation(compacted, "operation.calls", calls_window)
        _record_truncation(compacted, "operation.controlFlow", control_window)
        _record_truncation(compacted, "operation.returns", returns_window)
    if "view" not in compacted:
        compacted["view"] = {"mode": "full", "truncation": {}}
    return compacted


def _compact_dev_payload_for_cli(path: Path, payload: dict, *, full: bool) -> dict:
    compacted = copy.deepcopy(payload)
    if full:
        compacted["view"] = {"mode": "full", "truncation": {}}
        return compacted
    watch = compacted.get("watch")
    if isinstance(watch, dict):
        files, files_window = _compact_list(watch.get("files", []), DEV_WATCH_FILE_WINDOW)
        watch["files"] = files
        _record_truncation(compacted, "watch.files", files_window)
    interface_fingerprints = compacted.get("interfaceFingerprints")
    if isinstance(interface_fingerprints, dict):
        modules, modules_window = _compact_list(interface_fingerprints.get("modules", []), DEV_INTERFACE_MODULE_WINDOW)
        interface_fingerprints["modules"] = modules
        _record_truncation(compacted, "interfaceFingerprints.modules", modules_window)
    if "view" not in compacted:
        compacted["view"] = {"mode": "full", "truncation": {}}
    return compacted


def _compact_test_payload_for_cli(path: Path, payload: dict, *, full: bool) -> dict:
    compacted = copy.deepcopy(payload)
    if full:
        compacted["view"] = {"mode": "full", "truncation": {}}
        return compacted
    results, results_window = _compact_list(compacted.get("results", []), TEST_RESULT_WINDOW)
    compacted["results"] = results
    _record_truncation(compacted, "results", results_window)
    if "view" not in compacted:
        compacted["view"] = {"mode": "full", "truncation": {}}
    return compacted


def _check_next_commands(path: Path, diagnostics: list[dict], status: str, *, include_readiness: bool) -> list[dict]:
    resolved = str(path.resolve())
    entries: list[dict] = []
    seen: set[str] = set()
    has_tests = bool(_discover_test_entries(path))
    build_tape = _find_build_tape(path)
    project_diag_with_file_entry = bool(build_tape is not None and path.resolve().is_file() and path.name.lower() not in {"build.sem", "build.sscript"})
    for diagnostic in diagnostics[:8]:
        code = diagnostic.get("code", "")
        if code and _diagnostic_has_explainer(code):
            _append_next_command(
                entries,
                seen,
                "explain",
                f"sem explain {code} --json",
                "load the current rule explanation for this diagnostic code",
                argv=["sem", "explain", code, "--json"],
            )
        if diagnostic.get("subjectKind") == "operation" and diagnostic.get("subjectName"):
            _append_next_command(
                entries,
                seen,
                "slice",
                f"sem slice --operation {diagnostic['subjectName']} --json {resolved}",
                "inspect the semantic neighborhood around the affected operation",
                argv=["sem", "slice", "--operation", diagnostic["subjectName"], "--json", resolved],
            )
    if any(item.get("repair", {}).get("id") for item in diagnostics):
        fix_argv = ["sem", "fix", "--plan", "--json"]
        if status == "ok-with-warnings":
            fix_argv.append("--include-warnings")
        fix_argv.append(resolved)
        _append_next_command(
            entries,
            seen,
            "fix",
            _display_command(fix_argv),
            "generate a reviewable repair plan for the current diagnostics",
            argv=fix_argv,
        )
    graph_entry = _graph_followup_entry(
        path,
        project_kind="summary",
        file_kind="calls",
        project_reason=(
            "inspect the compact project graph before drilling into a file-local semantic neighborhood"
            if project_diag_with_file_entry else
            "inspect the compact project graph before editing shared behavior"
        ),
        file_reason=(
            "inspect the local file graph before editing while keeping the current project-scoped diagnostics in view"
            if project_diag_with_file_entry else
            "inspect the local call graph before editing shared behavior"
        ),
    )
    entries.append(graph_entry)
    if not include_readiness:
        _append_next_command(
            entries,
            seen,
            "readiness",
            f"sem readiness --json {resolved}",
            "inspect environment and runtime-adapter readiness separately from source diagnostics",
            argv=["sem", "readiness", "--json", resolved],
        )
    if status in {"ok", "ok-with-warnings"} and has_tests:
        _append_next_command(
            entries,
            seen,
            "test",
            f"sem test --json {resolved}",
            "verify the current source state beyond syntax and lint passes",
            argv=["sem", "test", "--json", resolved],
        )
    return entries


def _readiness_next_commands(path: Path, payload: dict) -> list[dict]:
    resolved = str(path.resolve())
    entries: list[dict] = []
    seen: set[str] = set()
    _append_next_command(
        entries,
        seen,
        "doctor",
        "sem doctor --json",
        "inspect the current toolchain and environment state",
        argv=["sem", "doctor", "--json"],
    )
    _append_next_command(
        entries,
        seen,
        "check",
        f"sem check --json {resolved}",
        "separate environment blockers from source-level diagnostics",
        argv=["sem", "check", "--json", resolved],
    )
    if payload.get("sourceStatus") and payload.get("sourceStatus") != "ok":
        fix_argv = ["sem", "fix", "--plan", "--json"]
        if payload.get("sourceStatus") == "ok-with-warnings":
            fix_argv.append("--include-warnings")
        fix_argv.append(resolved)
        _append_next_command(
            entries,
            seen,
            "fix",
            _display_command(fix_argv),
            "inspect structured repair guidance for the source diagnostics before treating readiness as an environment problem",
            argv=fix_argv,
        )
    if payload.get("graphSummary", {}).get("routeCount", 0):
        _append_next_command(
            entries,
            seen,
            "graph",
            f"sem graph --kind routes --json {resolved}",
            "inspect the route-hosting surface that depends on runtime availability",
            argv=["sem", "graph", "--kind", "routes", "--json", resolved],
        )
    return entries


def _fix_plan_next_commands(path: Path, *, patchable: bool, plan_usable: bool, status: str, focus_anchors: dict | None = None) -> list[dict]:
    resolved = str(path.resolve())
    entries = []
    full_fix_argv = ["sem", "fix", "--plan", "--json", "--full", resolved]
    patch_artifact = _patch_artifact_input(full_fix_argv)
    if status == "actionable" and patchable and plan_usable:
        entries.extend([
            _next_command_entry(
                "fix",
                "emit a complete repair plan payload before saving it for patch execution",
                argv=full_fix_argv,
            ),
            _next_command_entry(
                "patch",
                "preview the exact edits before mutating source files",
                argv=["sem", "patch", "--dry-run", "--json"],
                command="sem patch --dry-run --json PLAN_PATH",
                replayable=False,
                artifact_inputs=[patch_artifact],
            ),
            _next_command_entry(
                "patch",
                "apply the reviewed repair plan with formatter and check verification",
                argv=["sem", "patch", "--apply", "--json"],
                command="sem patch --apply --json PLAN_PATH",
                replayable=False,
                artifact_inputs=[patch_artifact],
            ),
        ])
    elif status == "mixed" and patchable and plan_usable:
        entries.extend([
            _next_command_entry(
                "fix",
                "emit a complete repair plan payload before saving it for patch execution",
                argv=full_fix_argv,
            ),
            _next_command_entry(
                "patch",
                "preview the limited machine-applicable edits before deciding whether the mixed plan is worth applying",
                argv=["sem", "patch", "--dry-run", "--json"],
                command="sem patch --dry-run --json PLAN_PATH",
                replayable=False,
                artifact_inputs=[patch_artifact],
            ),
        ])
    if status == "blocked":
        entries.append(
            _next_command_entry(
                "check",
                "resolve compiler-blocking diagnostics before trusting a machine patch plan",
                argv=["sem", "check", "--json", resolved],
            )
        )
        entries.append(
            _next_command_entry(
                "explain",
                "load the compiler-parse recovery guidance before retrying repair planning",
                argv=["sem", "explain", "SEMSC_PARSE", "--json"],
            )
        )
        return entries
    if status in {"suggestions-only", "mixed"}:
        entries.append(
            _next_command_entry(
                "check",
                (
                    "recompute diagnostics after manually reviewing the suggestions-only plan"
                    if status == "suggestions-only"
                    else "recompute diagnostics after reviewing the mixed machine-and-manual repair plan"
                ),
                argv=["sem", "check", "--json", resolved],
            )
        )
        top_operation = ((focus_anchors or {}).get("topOperations") or [{}])[0].get("name", "")
        top_file = ((focus_anchors or {}).get("topFiles") or [{}])[0].get("name", "")
        if top_operation:
            entries.append(
                _next_command_entry(
                    "slice",
                    "focus the first review pass on the operation attracting the most remaining diagnostics",
                    argv=["sem", "slice", "--operation", top_operation, "--json", resolved],
                )
            )
        elif top_file:
            entries.append(
                _next_command_entry(
                    "check",
                    "narrow the first review pass to the hottest source file instead of re-reading the full project surface",
                    argv=["sem", "check", "--json", top_file],
                )
            )
        entries.append(
            _graph_followup_entry(
                path,
                project_kind="routes" if status == "mixed" else "summary",
                file_kind="calls",
                project_reason=(
                    "inspect the compact project graph because no machine-applicable patch was derived"
                    if status == "suggestions-only"
                    else "inspect the project route graph to decide whether the remaining non-patchable diagnostics cluster around one surface"
                ),
                file_reason=(
                    "inspect the surrounding call graph because no machine-applicable patch was derived"
                    if status == "suggestions-only"
                    else "inspect the surrounding call graph to decide whether the remaining non-patchable diagnostics cluster around one surface"
                ),
            )
        )
        return entries
    entries.append(
        _next_command_entry(
            "check",
            "recompute the current diagnostic set after reviewing the plan",
            argv=["sem", "check", "--json", resolved],
        )
    )
    if _discover_test_entries(path):
        entries.append(
            _next_command_entry(
                "test",
                "run test discovery once the repair plan is accepted",
                argv=["sem", "test", "--json", resolved],
            )
        )
    else:
        entries.append(
            _graph_followup_entry(
                path,
                project_kind="summary",
                file_kind="calls",
                project_reason="inspect the compact project graph when no tests are available for this surface",
                file_reason="inspect the surrounding call graph when no tests are available for this surface",
            )
        )
    return entries


def _patch_next_commands(plan: dict, mode: str, ok: bool) -> list[dict]:
    input_path = str(Path(plan.get("inputPath", ".")).resolve())
    input_resolved = Path(input_path)
    input_plan_path = str(Path(plan.get("_inputPlanPath", "")).resolve()) if plan.get("_inputPlanPath") else ""
    if not ok:
        return [
            _next_command_entry(
                "fix",
                "regenerate the repair plan against the current file contents",
                argv=["sem", "fix", "--plan", "--json", input_path],
            ),
            _next_command_entry(
                "check",
                "confirm the current source state before applying a new plan",
                argv=["sem", "check", "--json", input_path],
            ),
        ]
    if mode == "dry-run":
        patch_entry = (
            _next_command_entry(
                "patch",
                "apply the reviewed plan once the dry-run diff is acceptable",
                argv=["sem", "patch", "--apply", "--json", input_plan_path],
            )
            if input_plan_path else
            _next_command_entry(
                "patch",
                "apply the reviewed plan once the dry-run diff is acceptable",
                argv=["sem", "patch", "--apply", "--json"],
                command="sem patch --apply --json PLAN_PATH",
                replayable=False,
                artifact_inputs=[{
                    "name": "planPath",
                    "kind": "file",
                    "schemaVersion": "sem.fixPlan.v1",
                    "appendAsFinalArg": True,
                    "description": "reuse the reviewed plan file from the current dry-run step",
                }],
            )
        )
        return [
            patch_entry,
            _next_command_entry(
                "check",
                "verify the current diagnostics before real application",
                argv=["sem", "check", "--json", input_path],
            ),
        ]
    return [
        _next_command_entry(
            "check",
            "re-run structured diagnostics after the patch landed",
            argv=["sem", "check", "--json", input_path],
        ),
        *([
            _next_command_entry(
                "test",
                "verify behavior after the patch and formatter normalization",
                argv=["sem", "test", "--json", input_path],
            )
        ] if _discover_test_entries(input_resolved) else []),
        _graph_followup_entry(
            input_resolved,
            project_kind="summary",
            file_kind="calls",
            project_reason="inspect the compact post-patch project graph if shared behavior changed",
            file_reason="inspect the post-patch call graph if shared behavior changed",
        ),
    ]


def _test_next_commands(path: Path, failed: int, *, source_ok: bool, python_harnesses_deferred: bool = False) -> list[dict]:
    resolved = str(path.resolve())
    fix_reason = (
        "generate candidate repairs for issues surfaced by the failing tests"
        if failed else
        "generate candidate repairs for source diagnostics that block a clean test loop"
    )
    entries = [
        _next_command_entry(
            "check",
            "inspect structured diagnostics for the same project surface",
            argv=["sem", "check", "--json", resolved],
        ),
        _graph_followup_entry(
            path,
            project_kind="summary",
            file_kind="calls",
            project_reason="inspect the compact project graph around failing semantic tests or app harnesses",
            file_reason="inspect the call graph around failing semantic tests or app harnesses",
        ),
    ]
    if failed or not source_ok:
        entries.insert(
            0,
            _next_command_entry(
                "fix",
                fix_reason,
                argv=["sem", "fix", "--plan", "--json", resolved],
            ),
        )
    if python_harnesses_deferred and not source_ok:
        entries.insert(
            1,
            _next_command_entry(
                "test",
                "gather runtime-harness signal even while semantic preflight diagnostics are still red",
                argv=["sem", "test", "--json", "--allow-red-preflight-harnesses", resolved],
            ),
        )
    return entries


def _explain_next_commands(code: str, *, repeatable: bool = True) -> list[dict]:
    entries = [
        _next_command_entry(
            "skills",
            "load the current diagnostic and repair workflow guidance for this tool version",
            argv=["sem", "skills", "get", "sem-diagnostics", "--full", "--json"],
            mcp_tool="skills_get",
            mcp_args={"names": ["sem-diagnostics"], "full": True},
        ),
    ]
    if code == "SS3639":
        entries.extend([
            _next_command_entry(
                "docs-get",
                "open the generated-id migration rows attached to the deprecated sqlite.lastInsertRowId target",
                argv=["sem", "docs", "get", "sqlite.lastInsertRowId", "--json"],
                mcp_tool="docs_get",
                mcp_args={"operation": "sqlite.lastInsertRowId"},
            ),
            _next_command_entry(
                "docs-search",
                "discover the native/webServer-safe INSERT RETURNING generated-id guide",
                argv=[
                    "sem", "docs", "search", "insert returning generated id sqlite",
                    "--embedding-provider", "none", "--json",
                ],
                mcp_tool="docs_search",
                mcp_args={
                    "query": "insert returning generated id sqlite",
                    "include_std": True,
                    "embedding_provider": "none",
                },
            ),
        ])
    if repeatable:
        entries.append(
            _next_command_entry(
                "related",
                "re-use this command after following a related diagnostic edge from the current explainer",
                argv=["sem", "explain", code, "--json"],
            )
        )
    return entries


def _graph_next_commands(path: Path, kind: str, payload: dict | None = None) -> list[dict]:
    resolved = str(path.resolve())
    followup_target = str(_project_surface_path(path)) if _is_project_surface(path) else resolved
    entries = [
        _next_command_entry(
            "check",
            "pair the architecture view with the current structured diagnostics",
            argv=["sem", "check", "--json", resolved],
        )
    ]
    payload = payload or {}
    if kind == "summary":
        if payload.get("summary", {}).get("routeCount", 0):
            entries.append(
                _next_command_entry(
                    "graph",
                    "expand the compact summary into concrete route anchors before drilling into one handler",
                    argv=["sem", "graph", "--kind", "routes", "--json", followup_target],
                )
            )
        else:
            entries.append(
                _next_command_entry(
                    "graph",
                    "expand the compact summary into a concrete call graph once you know this surface has no routes",
                    argv=["sem", "graph", "--kind", "calls", "--json", followup_target],
                )
            )
        return entries
    if kind == "routes":
        first_route = next((edge for edge in payload.get("edges", []) if edge.get("kind") == "route"), None)
        if first_route is not None:
            entries.append(
                _next_command_entry(
                    "slice",
                    "zoom into one concrete route neighborhood before editing a handler",
                    argv=["sem", "slice", "--route", f"{first_route['method']}:{first_route['path']}", "--json", followup_target],
                )
            )
        return entries
    if kind == "effects":
        first_effect = next((edge for edge in payload.get("edges", []) if edge.get("kind") == "effect"), None)
        if first_effect is not None:
            entries.append(
                _next_command_entry(
                    "slice",
                    "zoom into one concrete effect neighborhood before editing authority or cleanup behavior",
                    argv=["sem", "slice", "--effect", first_effect["path"], "--json", followup_target],
                )
            )
        return entries
    if kind in {"capabilities", "auth"}:
        first_capability = next((edge for edge in payload.get("edges", []) if edge.get("kind") == "useCapability"), None)
        if first_capability is not None:
            entries.append(
                _next_command_entry(
                    "slice",
                    "zoom into one concrete capability neighborhood before editing authority coverage",
                    argv=["sem", "slice", "--capability", first_capability["capability"], "--json", followup_target],
                )
            )
            return entries
    operation_name = ""
    first_edge = next((edge for edge in payload.get("edges", []) if edge.get("fromOperation")), None)
    if first_edge is not None:
        operation_name = first_edge.get("fromOperation", "")
    if not operation_name:
        first_node = next((node for node in payload.get("nodes", []) if node.get("kind") == "operation"), None)
        if first_node is not None:
            operation_name = first_node.get("name", "")
    if operation_name:
        entries.append(
            _next_command_entry(
                "slice",
                "zoom from graph structure into one concrete semantic neighborhood before editing",
                argv=["sem", "slice", "--operation", operation_name, "--json", followup_target],
            )
        )
    return entries


def _slice_next_commands(path: Path, payload: dict) -> list[dict]:
    resolved = str(path.resolve())
    anchor = payload.get("anchor", {})
    base_entries = [
        _next_command_entry(
            "check",
            "pair the slice result with the current diagnostic set",
            argv=["sem", "check", "--json", resolved],
        ),
        _graph_followup_entry(
            path,
            project_kind="summary",
            file_kind="calls",
            project_reason="inspect the compact project graph around the current slice anchor before expanding further",
            file_reason="inspect the wider architecture around the current slice anchor",
        ),
    ]
    if payload.get("anchorOptions") or not anchor.get("name"):
        return base_entries
    operation_name = ""
    refresh_argv: list[object] | None = None
    if payload.get("operation"):
        operation_name = payload["operation"].get("name", "")
    if anchor.get("kind") == "route" and anchor.get("name"):
        refresh_argv = ["sem", "slice", "--route", anchor["name"], "--json", resolved]
        refresh_command = _display_command(_stringify_argv(refresh_argv))
    elif operation_name:
        refresh_argv = ["sem", "slice", "--operation", operation_name, "--json", resolved]
        refresh_command = _display_command(_stringify_argv(refresh_argv))
    else:
        refresh_argv = ["sem", "slice", f"--{anchor.get('kind', 'operation')}", anchor.get("name", ""), "--json", resolved]
        refresh_command = _display_command(_stringify_argv(refresh_argv))
    return [
        *base_entries,
        _next_command_entry(
            "slice",
            "re-run the same anchor after related edits to refresh the local semantic neighborhood",
            argv=refresh_argv,
            command=refresh_command,
        ),
    ]


def _size_next_commands(path: Path) -> list[dict]:
    resolved = str(path.resolve())
    return [
        _graph_followup_entry(
            path,
            project_kind="summary",
            file_kind="calls",
            project_reason="inspect the compact project graph that contributes to the current source footprint",
            file_reason="inspect the call graph that contributes to the current source footprint",
        ),
        _next_command_entry(
            "check",
            "pair footprint facts with the current diagnostics and runtime readiness",
            argv=["sem", "check", "--json", resolved],
        ),
    ]


def _build_check_payload(path: Path, compiler_args: list[str], *, include_readiness: bool = False, lower_check: bool = False) -> dict:
    context = _build_context_payload(path)
    symbols = _symbol_graph_payload(path)
    lint_diagnostics, lint_errors = _collect_lint_diagnostics(path)
    build_tape = _find_build_tape(path)
    compiler_source = build_tape if build_tape is not None else path
    compiler = _compiler_check_probe(compiler_source, compiler_args)
    compiler_diagnostics, compiler_errors = _collect_compiler_diagnostics(compiler)
    # Universal codegen preflight (opt-in via `lower_check`, set by `sem check`):
    # if parse + semantic + the compiler's own lint are clean, run the full
    # lowering (`--lower-check`) so `buildable` reflects whether codegen actually
    # succeeds — closing the A3 gap ("check says buildable:true but build fails
    # SSCGxxxx") for EVERY codegen error, not just the structural webServer/const
    # prerequisites. Off by default so internal callers (fix-plan, patch, test,
    # dev) keep the cheap parse-level probe; skipped for already-broken programs
    # so the fast path stays fast and we never codegen garbage.
    if lower_check:
        _probe_compiler_errors = sum(
            1 for item in compiler_diagnostics
            if item.get("severity") == "error" or item.get("blocksCompile"))
        if compiler["ok"] and _probe_compiler_errors == 0 and not compiler_errors:
            lower = _compiler_lower_check_probe(compiler_source, compiler_args)
            if not lower["ok"]:
                lower_diagnostics, lower_errors = _collect_compiler_diagnostics(lower)
                compiler_diagnostics = list(compiler_diagnostics) + list(lower_diagnostics)
                compiler_errors = list(compiler_errors) + list(lower_errors)
                if not lower_diagnostics and not lower_errors:
                    # Codegen failed but emitted no parseable diagnostic; record a
                    # transport error so `buildable` still flips false (fail closed).
                    compiler_errors = list(compiler_errors) + [
                        f"lowering preflight failed (rc={lower.get('returnCode')}) "
                        "with no parseable diagnostic"]
    diagnostics = list(lint_diagnostics) + list(compiler_diagnostics)
    severity_rank = {"error": 0, "warning": 1, "info": 2}
    diagnostics.sort(key=lambda item: (
        not item.get("blocksCompile", False),
        severity_rank.get(item.get("severity", ""), 9),
        item.get("span", {}).get("file", ""),
        item.get("span", {}).get("line", 0),
        item.get("span", {}).get("column", 0),
        item.get("code", ""),
    ))
    readiness = _readiness_payload(path) if include_readiness else None
    compiler_error_count = sum(1 for item in compiler_diagnostics if item.get("severity") == "error" or item.get("blocksCompile"))
    compiler_warning_count = sum(1 for item in compiler_diagnostics if item.get("severity") == "warning" and not item.get("blocksCompile"))
    lint_error_count = sum(1 for item in lint_diagnostics if item.get("severity") == "error" or item.get("blocksCompile"))
    lint_warning_count = sum(1 for item in lint_diagnostics if item.get("severity") == "warning" and not item.get("blocksCompile"))
    errors = compiler_error_count + lint_error_count
    warnings = compiler_warning_count + lint_warning_count
    transport_errors = lint_errors + compiler_errors + list(symbols["errors"])
    buildable = bool(compiler["ok"] and compiler_error_count == 0 and not compiler_errors)
    lint_clean = lint_error_count == 0 and not lint_errors
    ok = bool(buildable and lint_clean and not transport_errors)
    status = "ok"
    if transport_errors and errors == 0:
        status = "tool-error"
    elif not buildable:
        status = "compiler-error"
    elif not lint_clean:
        status = "lint-diagnostics"
    elif warnings:
        status = "ok-with-warnings"
    payload = {
        "schemaVersion": "sem.check.v1",
        "tool": {"name": "sem", "version": VERSION},
        "input": {
            "requestedPath": str(path.resolve()),
            "compilerSource": str(compiler_source.resolve()) if compiler_source.exists() else str(compiler_source),
            "buildTape": context["project"].get("buildTape", ""),
        },
        "ok": ok,
        "status": status,
        "buildable": buildable,
        # `noBlockingLintErrors` is the clearer canonical name: it means "no
        # COMPILE-BLOCKING lint errors", NOT "zero lint findings" — warnings
        # (e.g. SS3604/SS4001) can still be present while this is true. Read
        # summary.lintWarnings / the diagnostics list for the full picture.
        # `lintClean` is retained as a deprecated alias for back-compat.
        "noBlockingLintErrors": lint_clean,
        "lintClean": lint_clean,
        "scope": _payload_scope(
            path,
            compilerScope="project" if build_tape is not None else ("directory" if path.resolve().is_dir() else "file"),
            contextScope=_scope_label_from_sources(context["sourceFiles"]),
            diagnosticsScope="project" if build_tape is not None else ("directory" if path.resolve().is_dir() else "file"),
        ),
        "surfaceShift": _surface_shift(
            path,
            _requested_surface_kind(path),
            "project" if build_tape is not None else ("directory" if path.resolve().is_dir() else "file"),
            reason="diagnostic scope expanded from the requested entry surface to the effective compiler surface",
        ),
        "project": context["project"],
        "sourceFiles": context["sourceFiles"],
        "diagnostics": diagnostics,
        "summary": {
            "errors": errors + len(transport_errors),
            "warnings": warnings,
            "repairable": sum(1 for item in diagnostics if item.get("repair", {}).get("id")),
            "compileBlocking": sum(1 for item in diagnostics if item.get("blocksCompile")),
            "toolErrors": len(transport_errors),
            "compilerErrors": compiler_error_count,
            "lintErrors": lint_error_count,
            "compilerWarnings": compiler_warning_count,
            "lintWarnings": lint_warning_count,
            "topCodes": _top_count_entries([item.get("code", "") for item in diagnostics]),
        },
        "compiler": {
            "attempted": compiler["attempted"],
            "ok": compiler["ok"],
            "returnCode": compiler["returnCode"],
            "stdoutSnippet": (compiler["stdout"] or "")[:2000],
            "stderrSnippet": (compiler["stderr"] or "")[:2000],
        },
        "unresolvedReferences": symbols["unresolvedReferences"],
        "graphSummary": symbols["summary"],
        "runtimeFeatureFlags": context["runtimeFeatureFlags"],
        "supportedSyntax": context["supportedSyntax"],
        "errors": transport_errors,
        "toolErrors": transport_errors,
    }
    if include_readiness:
        payload["targetReadiness"] = readiness
    payload["nextCommands"] = _check_next_commands(path, diagnostics, payload["status"], include_readiness=include_readiness)
    return payload


def _narrative_entries_for_operation(operation_name: str, facts) -> dict[str, list[dict]]:
    entries = {
        "purpose": [],
        "invariant": [],
        "warning": [],
        "security": [],
        "observability": [],
    }
    for source_line in facts.lines:
        if not source_line.tokens:
            continue
        args = source_line.args
        verb = source_line.verb
        if verb not in {"purpose", "invariant", "warning", "security", "observability"}:
            continue
        text = ""
        if len(args) >= 3 and args[0] == "operation" and args[1] == operation_name:
            text = args[2]
        elif len(args) >= 2 and args[0] == operation_name:
            text = args[1]
        if text:
            entries[verb].append({
                "text": text,
                "location": _line_payload(source_line),
            })
    return entries


def _module_narrative_entries(facts) -> list[dict]:
    entries = []
    interesting_verbs = {
        "purpose",
        "invariant",
        "moduleOwns",
        "moduleDoesNotOwn",
        "moduleWarning",
        "moduleSecurity",
        "moduleObservability",
    }
    for source_line in facts.lines:
        if not source_line.tokens or source_line.verb not in interesting_verbs:
            continue
        text = source_line.args[-1] if source_line.args else ""
        entries.append({
            "kind": source_line.verb,
            "text": text,
            "location": _line_payload(source_line),
        })
    return entries


def _facts_operation_lookup(bundle: dict) -> dict[str, tuple[Path, object, object]]:
    lookup = {}
    for item in bundle["files"]:
        source = item["path"]
        facts = item["facts"]
        for operation in facts.operations.values():
            lookup.setdefault(operation.name, (source, facts, operation))
    return lookup


def _graph_payload(path: Path, kind: str) -> dict:
    kind = kind or "summary"
    graph_surface = path
    graph_surface_shift = {}
    if kind == "routes":
        project_surface = _project_surface_path(path)
        if project_surface != path.resolve():
            graph_surface = project_surface
            graph_surface_shift = _surface_shift(
                path,
                _requested_surface_kind(path),
                "project",
                reason="route graph expanded from the requested source file to the effective project surface so handler linkage can be resolved",
            )
    symbols = _symbol_graph_payload(graph_surface)
    bundle = None if kind == "summary" else _collect_facts_bundle(graph_surface)
    edges = []
    nodes = []

    if kind == "summary":
        payload = {
            "schemaVersion": "sem.graph.v1",
            "tool": {"name": "sem", "version": VERSION},
            "ok": not symbols["errors"],
            "status": "ok" if not symbols["errors"] else "partial",
            "completeContext": not symbols["errors"],
            "kind": "summary",
            "inputPath": str(path.resolve()),
            "scope": _payload_scope(path, retrievalScope=_scope_label_from_sources(symbols["sourceFiles"])),
            "summary": symbols["summary"],
            "sourceFiles": symbols["sourceFiles"],
            "errors": list(symbols["errors"]),
        }
        payload["nextCommands"] = _graph_next_commands(path, kind, payload)
        return payload

    if kind == "calls":
        for file_payload in symbols["files"]:
            for operation in file_payload["operations"]:
                nodes.append({"kind": "operation", "name": operation["name"], "file": file_payload["path"]})
                for call in operation["calls"]:
                    edges.append({
                        "kind": "call",
                        "fromOperation": operation["name"],
                        "callName": call["name"],
                        "target": call["target"],
                        "location": call["location"],
                    })
    elif kind == "effects":
        for file_payload in symbols["files"]:
            for operation in file_payload["operations"]:
                for effect in operation["effects"]:
                    edges.append({
                        "kind": "effect",
                        "operation": operation["name"],
                        "action": effect["action"],
                        "path": effect["path"],
                        "location": effect["location"],
                    })
    elif kind in {"capabilities", "auth"}:
        for file_payload in symbols["files"]:
            for operation in file_payload["operations"]:
                for capability in operation["capabilities"]:
                    edges.append({
                        "kind": "useCapability",
                        "operation": operation["name"],
                        "capability": capability["name"],
                        "location": capability["location"],
                    })
                for authority in operation.get("authorities", []):
                    edges.append({
                        "kind": "authority",
                        "operation": operation["name"],
                        "action": authority["action"],
                        "path": authority["path"],
                        "location": authority["location"],
                    })
    elif kind == "routes":
        seen_route_nodes = set()
        seen_handler_nodes = set()
        for file_payload in symbols["files"]:
            for route in file_payload["routes"]:
                route_node = f"{route['method']}:{route['path']}"
                if route_node not in seen_route_nodes:
                    seen_route_nodes.add(route_node)
                    nodes.append({
                        "kind": "route",
                        "name": route_node,
                        "file": file_payload["path"],
                        "location": route["location"],
                    })
                handler_name = route.get("handler", "")
                if handler_name and handler_name not in seen_handler_nodes:
                    seen_handler_nodes.add(handler_name)
                    nodes.append({
                        "kind": "operation",
                        "name": handler_name,
                        "file": route.get("handlerFile") or file_payload["path"],
                        "location": route.get("handlerLocation") or route["location"],
                    })
                edges.append({
                    "kind": "route",
                    "method": route["method"],
                    "path": route["path"],
                    "handler": route["handler"],
                    "location": route["location"],
                    "handlerFile": route.get("handlerFile", ""),
                    "handlerLocation": route.get("handlerLocation", {}),
                })
    elif kind == "dataflow":
        for file_payload in symbols["files"]:
            for operation in file_payload["operations"]:
                edges.append({
                    "kind": "operationDataflow",
                    "operation": operation["name"],
                    "inputs": operation["inputs"],
                    "outputs": operation["outputs"],
                    "calls": operation["calls"],
                    "returns": operation["returns"],
                })
    elif kind == "types":
        for item in bundle["files"]:
            facts = item["facts"]
            for name, fields in sorted(facts.records.items()):
                edges.append({
                    "kind": "record",
                    "name": name,
                    "fields": [{"name": field_name, "type": field_type} for field_name, field_type in fields],
                    "file": str(item["path"].resolve()),
                })
            for result in facts.result_types.values():
                edges.append({
                    "kind": "result",
                    "name": result.name,
                    "okType": result.ok_type,
                    "errorType": result.error_type,
                    "file": str(item["path"].resolve()),
                })
    elif kind == "ownership":
        for item in bundle["files"]:
            entries = _module_narrative_entries(item["facts"])
            if entries:
                edges.append({
                    "kind": "moduleOwnership",
                    "file": str(item["path"].resolve()),
                    "entries": entries,
                })
    else:
        return {
            "schemaVersion": "sem.graph.v1",
            "tool": {"name": "sem", "version": VERSION},
            "ok": False,
            "status": "error",
            "completeContext": False,
            "kind": kind,
            "inputPath": str(path.resolve()),
            "scope": _payload_scope(path, retrievalScope=_scope_label_from_sources(symbols["sourceFiles"])),
            "error": f"unsupported graph kind: {kind}",
            "supportedKinds": ["summary", "calls", "effects", "capabilities", "auth", "routes", "dataflow", "types", "ownership"],
        }

    payload = {
        "schemaVersion": "sem.graph.v1",
        "tool": {"name": "sem", "version": VERSION},
        "ok": not (symbols["errors"] or (bundle["errors"] if bundle is not None else [])),
        "status": "ok" if not (symbols["errors"] or (bundle["errors"] if bundle is not None else [])) else "partial",
        "completeContext": not (symbols["errors"] or (bundle["errors"] if bundle is not None else [])),
        "kind": kind,
        "inputPath": str(path.resolve()),
        "scope": _payload_scope(
            path,
            retrievalScope="project" if graph_surface != path.resolve() else _scope_label_from_sources(symbols["sourceFiles"]),
        ),
        "surfaceShift": graph_surface_shift,
        "sourceFiles": symbols["sourceFiles"],
        "summary": {
            "edgeCount": len(edges),
            "nodeCount": len(nodes),
            "fileCount": len(symbols["files"]),
        },
        "nodes": nodes,
        "edges": edges,
        "errors": list(symbols["errors"]) + list(bundle["errors"] if bundle is not None else []),
    }
    payload["nextCommands"] = _graph_next_commands(path, kind, payload)
    return payload


def _find_related_paths(root: Path, needle: str, patterns: tuple[str, ...]) -> list[str]:
    if not needle:
        return []
    candidates = []
    for pattern in patterns:
        for path in root.glob(pattern):
            if not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            if needle in text:
                candidates.append(str(path.resolve()))
    return sorted(set(candidates))


def _find_related_tests(root: Path, needle: str) -> list[str]:
    return _find_related_paths(root, needle, ("**/*test*.py", "**/*.test.sem", "**/*.test.sscript"))


def _find_related_docs(root: Path, needle: str) -> list[str]:
    return _find_related_paths(root, needle, ("**/README.md", "**/*.md"))


def _slice_operation_payload(path: Path, operation_name: str) -> dict:
    bundle = _collect_facts_bundle(path)
    symbols = _symbol_graph_payload(path)
    slice_errors = list(bundle["errors"]) + list(symbols["errors"])
    lookup = _facts_operation_lookup(bundle)
    target = lookup.get(operation_name)
    if target is None:
        return {
            "schemaVersion": "sem.slice.v1",
            "tool": {"name": "sem", "version": VERSION},
            "ok": False,
            "completeContext": False,
            "errors": slice_errors,
            "scope": _payload_scope(path, retrievalScope=_scope_label_from_sources(symbols["sourceFiles"])),
            "anchor": {"kind": "operation", "name": operation_name},
            "error": f"unknown operation: {operation_name}",
        }
    source, facts, operation = target
    operation_symbol = _operation_symbol(operation, bundle["semlint"], facts)
    callers = []
    routes = []
    for file_payload in symbols["files"]:
        for candidate in file_payload["operations"]:
            for call in candidate["calls"]:
                if call["target"] == operation_name:
                    callers.append({
                        "operation": candidate["name"],
                        "callName": call["name"],
                        "location": call["location"],
                    })
        for route in file_payload["routes"]:
            if route["handler"] == operation_name:
                routes.append(route)
    narratives = _narrative_entries_for_operation(operation_name, facts)
    project_root = _find_build_tape(path).parent if _find_build_tape(path) is not None else source.parent
    related_tests = _find_related_tests(project_root, operation_name)
    related_docs = _find_related_docs(ROOT.parent / "docs", operation_name)
    return {
        "schemaVersion": "sem.slice.v1",
        "tool": {"name": "sem", "version": VERSION},
        "ok": True,
        "completeContext": not slice_errors,
        "errors": slice_errors,
        "scope": _payload_scope(path, retrievalScope=_scope_label_from_sources(symbols["sourceFiles"])),
        "anchor": {"kind": "operation", "name": operation_name},
        "files": [str(source.resolve())],
        "operation": operation_symbol,
        "effects": operation_symbol["effects"],
        "capabilities": operation_symbol["capabilities"],
        "calledOperations": [
            {
                "callName": call["name"],
                "target": call["target"],
                "location": call["location"],
            }
            for call in operation_symbol["calls"]
        ],
        "callers": callers,
        "routes": routes,
        "purposes": narratives["purpose"],
        "invariants": narratives["invariant"],
        "warnings": narratives["warning"],
        "securityNotes": narratives["security"],
        "observabilityNotes": narratives["observability"],
        "relatedTests": related_tests[:20],
        "relatedDocs": related_docs[:20],
    }


def _slice_capability_payload(path: Path, capability_name: str) -> dict:
    symbols = _symbol_graph_payload(path)
    bundle = _collect_facts_bundle(path)
    slice_errors = list(bundle["errors"]) + list(symbols["errors"])
    uses = []
    declarations = []
    for item in bundle["files"]:
        facts = item["facts"]
        capability = facts.capabilities.get(capability_name)
        if capability is not None:
            declarations.append({
                "name": capability.name,
                "effectPath": capability.effect_path,
                "access": capability.access,
                "location": _line_payload(capability.line),
            })
    for file_payload in symbols["files"]:
        for operation in file_payload["operations"]:
            for capability in operation["capabilities"]:
                if capability["name"] == capability_name:
                    uses.append({
                        "operation": operation["name"],
                        "location": capability["location"],
                    })
    return {
        "schemaVersion": "sem.slice.v1",
        "tool": {"name": "sem", "version": VERSION},
        "ok": bool(declarations or uses),
        "completeContext": not slice_errors,
        "errors": slice_errors,
        "scope": _payload_scope(path, retrievalScope=_scope_label_from_sources(symbols["sourceFiles"])),
        "anchor": {"kind": "capability", "name": capability_name},
        "declarations": declarations,
        "uses": uses,
    }


def _slice_effect_payload(path: Path, effect_query: str) -> dict:
    symbols = _symbol_graph_payload(path)
    slice_errors = list(symbols["errors"])
    matches = []
    for file_payload in symbols["files"]:
        for operation in file_payload["operations"]:
            for effect in operation["effects"]:
                effect_name = f"{effect['action']} {effect['path']}"
                if effect_query in effect_name or effect_query == effect["path"]:
                    matches.append({
                        "operation": operation["name"],
                        "action": effect["action"],
                        "path": effect["path"],
                        "location": effect["location"],
                    })
    return {
        "schemaVersion": "sem.slice.v1",
        "tool": {"name": "sem", "version": VERSION},
        "ok": bool(matches),
        "completeContext": not slice_errors,
        "errors": slice_errors,
        "scope": _payload_scope(path, retrievalScope=_scope_label_from_sources(symbols["sourceFiles"])),
        "anchor": {"kind": "effect", "name": effect_query},
        "matches": matches,
    }


def _slice_type_payload(path: Path, type_name: str) -> dict:
    symbols = _symbol_graph_payload(path)
    bundle = _collect_facts_bundle(path)
    slice_errors = list(bundle["errors"]) + list(symbols["errors"])
    matches = []
    record_fields = []
    result_types = []
    alias_declarations = []
    enum_declarations = []
    enum_cases = []
    for file_payload in symbols["files"]:
        for enum_payload in file_payload.get("enums", []):
            if enum_payload.get("name") == type_name:
                enum_declarations.append({
                    "name": type_name,
                    "repr": enum_payload.get("repr", ""),
                    "location": enum_payload.get("location", {}),
                })
                enum_cases = list(enum_payload.get("cases", []))
        for operation in file_payload["operations"]:
            for item in operation["inputs"]:
                if item.get("type") == type_name:
                    matches.append({"kind": "input", "operation": operation["name"], "location": item["location"], "name": item.get("name", "")})
            for item in operation["outputs"]:
                if item.get("type") == type_name:
                    matches.append({"kind": "output", "operation": operation["name"], "location": item["location"]})
            for call in operation["calls"]:
                for argument in call["arguments"]:
                    if argument.get("type") == type_name:
                        matches.append({"kind": "argument", "operation": operation["name"], "callName": call["name"], "location": argument["location"]})
                for bind_list in call["disposition"]["bind"].values():
                    for bind in bind_list:
                        if bind.get("type") == type_name:
                            matches.append({"kind": "bind", "operation": operation["name"], "callName": call["name"], "location": bind["location"], "name": bind["name"]})
    for item in bundle["files"]:
        facts = item["facts"]
        for source_line in facts.lines:
            if source_line.tokens and source_line.verb == "type" and source_line.args and source_line.args[0] == type_name:
                alias_declarations.append({
                    "name": type_name,
                    "type": " ".join(source_line.args[1:]),
                    "location": _line_payload(source_line),
                })
        if type_name in facts.records:
            record_fields = [{"name": field_name, "type": field_type} for field_name, field_type in facts.records[type_name]]
        if type_name in facts.result_types:
            result = facts.result_types[type_name]
            result_types.append({"name": result.name, "okType": result.ok_type, "errorType": result.error_type})
    return {
        "schemaVersion": "sem.slice.v1",
        "tool": {"name": "sem", "version": VERSION},
        "ok": bool(matches or record_fields or result_types or alias_declarations
                   or enum_declarations or enum_cases),
        "completeContext": not slice_errors,
        "errors": slice_errors,
        "scope": _payload_scope(path, retrievalScope=_scope_label_from_sources(symbols["sourceFiles"])),
        "anchor": {"kind": "type", "name": type_name},
        "uses": matches,
        "aliasDeclarations": alias_declarations,
        "enumDeclarations": enum_declarations,
        "enumCases": enum_cases,
        "recordFields": record_fields,
        "resultTypes": result_types,
    }


def _slice_symbol_payload(path: Path, symbol_name: str) -> dict:
    operation_payload = _slice_operation_payload(path, symbol_name)
    if operation_payload.get("ok"):
        operation_payload["anchor"] = {"kind": "symbol", "name": symbol_name, "resolvedKind": "operation"}
        operation_payload["symbolType"] = "operation"
        return operation_payload

    capability_payload = _slice_capability_payload(path, symbol_name)
    if capability_payload.get("ok"):
        capability_payload["anchor"] = {"kind": "symbol", "name": symbol_name, "resolvedKind": "capability"}
        capability_payload["symbolType"] = "capability"
        return capability_payload

    type_payload = _slice_type_payload(path, symbol_name)
    if type_payload.get("ok"):
        type_payload["anchor"] = {"kind": "symbol", "name": symbol_name, "resolvedKind": "type"}
        type_payload["symbolType"] = "type"
        return type_payload

    bundle = _collect_facts_bundle(path)
    slice_errors = list(bundle["errors"])
    declarations = []
    declaration_sites = set()
    resolved_kind = ""
    for item in bundle["files"]:
        facts = item["facts"]
        if symbol_name in facts.consts:
            const_fact = facts.consts[symbol_name]
            declaration_sites.add((str(item["path"].resolve()), const_fact.line.number))
            resolved_kind = resolved_kind or "const"
            declarations.append({
                "kind": "const",
                "name": const_fact.name,
                "type": const_fact.type_name,
                "value": const_fact.value,
                "location": _line_payload(const_fact.line),
            })
        for source_line in facts.lines:
            if not source_line.tokens:
                continue
            args = source_line.args
            if source_line.verb == "storage" and len(args) >= 4 and args[2] == symbol_name:
                declaration_sites.add((str(item["path"].resolve()), source_line.number))
                resolved_kind = resolved_kind or "storage"
                declarations.append({
                    "kind": "storage",
                    "scope": args[0],
                    "mutability": args[1],
                    "name": args[2],
                    "type": args[3],
                    "value": " ".join(args[4:]),
                    "location": _line_payload(source_line),
                })
            elif source_line.verb == "type" and args and args[0] == symbol_name:
                declaration_sites.add((str(item["path"].resolve()), source_line.number))
                resolved_kind = resolved_kind or "typeAlias"
                declarations.append({
                    "kind": "typeAlias",
                    "name": args[0],
                    "type": " ".join(args[1:]),
                    "location": _line_payload(source_line),
                })

    uses = []
    for item in bundle["files"]:
        facts = item["facts"]
        for operation in facts.operations.values():
            for source_line in operation.lines:
                if not source_line.tokens or symbol_name not in source_line.args:
                    continue
                site = (str(item["path"].resolve()), source_line.number)
                if site in declaration_sites:
                    continue
                uses.append({
                    "operation": operation.name,
                    "verb": source_line.verb,
                    "location": _line_payload(source_line),
                    "raw": source_line.raw,
                })

    ok = bool(declarations or uses)
    payload = {
        "schemaVersion": "sem.slice.v1",
        "tool": {"name": "sem", "version": VERSION},
        "ok": ok,
        "completeContext": not slice_errors,
        "errors": slice_errors,
        "scope": _payload_scope(path, retrievalScope=_scope_label_from_sources([item["path"] for item in bundle["files"]])),
        "anchor": {"kind": "symbol", "name": symbol_name, "resolvedKind": resolved_kind},
        "symbolType": resolved_kind,
        "declarations": declarations,
        "uses": uses,
        "relatedDocs": _find_related_docs(ROOT.parent, symbol_name),
        "relatedTests": _find_related_tests(ROOT.parent, symbol_name),
    }
    if not ok:
        payload["error"] = f"unknown symbol: {symbol_name}"
    return payload


def _slice_payload(path: Path, args: argparse.Namespace) -> dict:
    anchor_values = {
        "operation": getattr(args, "operation", None),
        "route": getattr(args, "route", None),
        "symbol": getattr(args, "symbol", None),
        "effect": getattr(args, "effect", None),
        "capability": getattr(args, "capability", None),
        "type": getattr(args, "type_name", None),
    }
    selected_anchors = [name for name, value in anchor_values.items() if value]
    if len(selected_anchors) != 1:
        payload = {
            "schemaVersion": "sem.slice.v1",
            "tool": {"name": "sem", "version": VERSION},
            "ok": False,
            "completeContext": True,
            "errors": [],
            "inputPath": str(path.resolve()),
            "scope": _payload_scope(path, retrievalScope=_requested_surface_kind(path)),
            "anchorOptions": selected_anchors,
            "error": (
                "slice requires exactly one anchor; choose one of --operation, --route, --symbol, --effect, --capability, or --type"
                if not selected_anchors
                else f"slice requires exactly one anchor; received {', '.join(selected_anchors)}"
            ),
        }
    elif args.operation:
        payload = _slice_operation_payload(path, args.operation)
    elif args.route:
        method, _, route_path = args.route.partition(":")
        route_surface = _project_surface_path(path) if _find_build_tape(path) is not None else path
        symbols = _symbol_graph_payload(route_surface)
        for file_payload in symbols["files"]:
            for route in file_payload["routes"]:
                if route["method"].upper() == method.upper() and route["path"] == route_path:
                    payload = _slice_operation_payload(route_surface, route["handler"])
                    payload["anchor"] = {"kind": "route", "name": args.route}
                    payload["route"] = route
                    payload["selectedRoute"] = route
                    payload["handlerOperation"] = payload.get("operation", {})
                    payload["routeDeclarationFile"] = route.get("location", {}).get("path", "")
                    payload["handlerFile"] = route.get("handlerFile") or next(iter(payload.get("files", [])), "")
                    payload["inputPath"] = str(path.resolve())
                    payload["scope"] = _payload_scope(
                        path,
                        retrievalScope="project" if _find_build_tape(path) is not None else _scope_label_from_sources(symbols["sourceFiles"]),
                    )
                    payload["surfaceShift"] = _surface_shift(
                        path,
                        _requested_surface_kind(path),
                        "project",
                        reason="route slice expanded from the requested registration surface to the effective project surface so the handler neighborhood can be resolved",
                    )
                    break
            else:
                continue
            break
        else:
            payload = {
                "schemaVersion": "sem.slice.v1",
                "tool": {"name": "sem", "version": VERSION},
                "ok": False,
                "completeContext": not symbols["errors"],
                "errors": list(symbols["errors"]),
                "scope": _payload_scope(path, retrievalScope=_scope_label_from_sources(symbols["sourceFiles"])),
                "anchor": {"kind": "route", "name": args.route},
                "error": f"unknown route: {args.route}",
            }
    elif args.symbol:
        payload = _slice_symbol_payload(path, args.symbol)
    elif args.effect:
        payload = _slice_effect_payload(path, args.effect)
    elif args.capability:
        payload = _slice_capability_payload(path, args.capability)
    elif args.type_name:
        payload = _slice_type_payload(path, args.type_name)
    else:
        payload = {
            "schemaVersion": "sem.slice.v1",
            "tool": {"name": "sem", "version": VERSION},
            "ok": False,
            "error": "slice requires one of --operation, --route, --symbol, --effect, --capability, or --type",
        }
    if payload.get("schemaVersion") == "sem.slice.v1":
        payload.setdefault("inputPath", str(path.resolve()))
        payload.setdefault(
            "status",
            "ok"
            if payload.get("ok", False) and payload.get("completeContext", True) else
            "partial"
            if payload.get("ok", False) else
            "not-found"
            if payload.get("error", "").startswith("unknown ") else
            "error",
        )
        payload.setdefault("nextCommands", _slice_next_commands(path, payload))
    return payload


def _size_payload(path: Path) -> dict:
    bundle = _collect_facts_bundle(path)
    symbols = _symbol_graph_payload(path)
    total_bytes = 0
    total_lines = 0
    helper_counts: dict[str, int] = {}
    source_sizes = []
    for item in bundle["files"]:
        source = item["path"]
        try:
            text = source.read_text(encoding="utf-8")
        except OSError:
            text = ""
        size = len(text.encode("utf-8"))
        line_count = len(text.splitlines())
        total_bytes += size
        total_lines += line_count
        source_sizes.append({
            "path": str(source.resolve()),
            "bytes": size,
            "lines": line_count,
        })
    for file_payload in symbols["files"]:
        for operation in file_payload["operations"]:
            for call in operation["calls"]:
                target = call["target"]
                family = target.split(".", 1)[0] if "." in target else "local"
                helper_counts[family] = helper_counts.get(family, 0) + 1
    retained_helpers = [
        {"family": family, "callCount": count}
        for family, count in sorted(helper_counts.items())
    ]
    return {
        "schemaVersion": "sem.size.v1",
        "tool": {"name": "sem", "version": VERSION},
        "inputPath": str(path.resolve()),
        "ok": not (bundle["errors"] or symbols["errors"]),
        "status": "ok" if not (bundle["errors"] or symbols["errors"]) else "partial",
        "scope": _payload_scope(path, retrievalScope=_scope_label_from_sources(symbols["sourceFiles"])),
        "summary": {
            "fileCount": len(source_sizes),
            "sourceBytes": total_bytes,
            "sourceLines": total_lines,
            "operationCount": symbols["summary"]["operationCount"],
            "callCount": symbols["summary"]["callCount"],
            "routeCount": symbols["summary"]["routeCount"],
        },
        "sourceFiles": source_sizes,
        "retainedHelpers": retained_helpers,
        "runtimeFeatureFlags": _runtime_feature_flags(),
        "profileBudget": {
            "status": "not-yet-computed",
            "note": "Artifact-size and backend-retention accounting is not yet computed by this wrapper; this payload currently summarizes source and helper-family footprint.",
        },
        "errors": list(bundle["errors"]) + list(symbols["errors"]),
        "nextCommands": _size_next_commands(path),
    }


def _runtime_requirements(symbols: dict) -> list[str]:
    families = set()
    for file_payload in symbols["files"]:
        if file_payload["routes"]:
            families.add("nativeHttpRuntime")
        for operation in file_payload["operations"]:
            for effect in operation["effects"]:
                effect_path = effect["path"]
                if effect_path.startswith("http."):
                    families.add("nativeHttpRuntime")
                elif effect_path.startswith("database.") or effect_path.startswith("sqlite."):
                    families.add("nativeSqliteRuntime")
            for call in operation["calls"]:
                target = call["target"]
                if target.startswith("http."):
                    families.add("nativeHttpRuntime")
                elif target.startswith("sqlite."):
                    families.add("nativeSqliteRuntime")
                elif target.startswith("json."):
                    families.add("nativeJsonRuntime")
                elif target.startswith("bcrypt."):
                    families.add("nativeBcryptRuntime")
                elif target.startswith("gui."):
                    families.add("nativeWin32GuiRuntime")
    return sorted(families)


def _readiness_payload(path: Path) -> dict:
    context = _build_context_payload(path)
    symbols = _symbol_graph_payload(path)
    check_payload = _build_check_payload(path, [], include_readiness=False)
    doctor = _doctor_payload()
    checks = {check["name"]: check for check in doctor["checks"]}
    required_runtimes = _runtime_requirements(symbols)
    runtime_flags = context["runtimeFeatureFlags"]
    missing_runtimes = [name for name in required_runtimes if not runtime_flags.get(name, False)]
    blocking_checks = []
    if not checks.get("python", {}).get("ok", False):
        blocking_checks.append("python")
    if not checks.get("llvmlite", {}).get("ok", False):
        blocking_checks.append("llvmlite")
    partial_checks = []
    if not checks.get("clang", {}).get("ok", False):
        partial_checks.append("clang")
    status = "supported"
    if blocking_checks or missing_runtimes:
        status = "blocked"
    elif not check_payload.get("buildable", False):
        status = "source-diagnostics"
    elif not check_payload.get("ok", False):
        status = "quality-diagnostics"
    elif partial_checks:
        status = "partial"
    payload = {
        "schemaVersion": "sem.readiness.v1",
        "tool": {"name": "sem", "version": VERSION},
        "inputPath": str(path.resolve()),
        "status": status,
        "ok": status == "supported",
        "scope": _payload_scope(
            path,
            sourceCheckScope=check_payload["scope"]["diagnosticsScope"],
            runtimeScope="project" if context["project"].get("buildTape") or path.resolve().is_dir() else "file",
        ),
        "requestedTargets": list(context["project"].get("targets", [])) or ["host"],
        "requiredRuntimeAdapters": required_runtimes,
        "missingRuntimeAdapters": missing_runtimes,
        "blockingChecks": [
            {
                "name": name,
                "detail": checks.get(name, {}).get("detail", ""),
                "fix": checks.get(name, {}).get("fix", ""),
            }
            for name in blocking_checks
        ],
        "partialChecks": [
            {
                "name": name,
                "detail": checks.get(name, {}).get("detail", ""),
                "fix": checks.get(name, {}).get("fix", ""),
            }
            for name in partial_checks
        ],
        "doctorStatus": doctor["ok"],
        "sourceOk": bool(check_payload.get("ok", False)),
        "buildableSource": bool(check_payload.get("buildable", False)),
        "lintCleanSource": bool(check_payload.get("lintClean", False)),
        "sourceStatus": check_payload.get("status", ""),
        "sourceSummary": check_payload.get("summary", {}),
        "graphSummary": symbols["summary"],
        "runtimeFeatureFlags": runtime_flags,
        "note": (
            "supported means the wrapper sees no obvious environment or runtime-adapter blockers. "
            "It does not yet guarantee backend-specific artifact emission for every target."
        ),
    }
    payload["nextCommands"] = _readiness_next_commands(path, payload)
    return payload


def _interface_fingerprints(path: Path) -> dict:
    bundle = _collect_facts_bundle(path)
    module_hashes = []
    for item in bundle["files"]:
        module_hashes.append({
            "path": str(item["path"].resolve()),
            "sha256": _file_sha256(item["path"]),
        })
    hasher = hashlib.sha256()
    for module in module_hashes:
        hasher.update(module["path"].encode("utf-8"))
        hasher.update(module["sha256"].encode("utf-8"))
    return {
        "algorithm": "sha256-sem-interface-v1",
        "projectHash": hasher.hexdigest(),
        "modules": module_hashes,
    }


def _dev_payload(path: Path, trace: bool) -> dict:
    context, context_ns = _timed_call(_build_context_payload, path)
    readiness, readiness_ns = _timed_call(_readiness_payload, path)
    check_payload, check_ns = _timed_call(_build_check_payload, path, [], include_readiness=False)
    build_tape = _find_build_tape(path)
    requested = path.resolve()
    project_surface = _project_surface_path(path)
    symbols, symbols_ns = _timed_call(_symbol_graph_payload, project_surface)
    watch_sources, watch_errors = _symbol_source_files(project_surface)
    source_ok = bool(check_payload.get("ok", False))
    source_buildable = bool(check_payload.get("buildable", False))
    discovered_tests, test_discovery_ns = _timed_call(_discover_test_entries, path)
    has_tests = bool(discovered_tests) and source_buildable
    has_runtime_harnesses = any(entry["kind"] == "python" for entry in discovered_tests)
    rerun = ["check", "graph"]
    if has_tests:
        rerun.insert(1, "test")
    route_count = symbols["summary"]["routeCount"]
    restart_on_success = source_buildable and route_count > 0
    watch_files = sorted(set([str(item.resolve()) for item in watch_sources]))
    if context["project"].get("buildTape"):
        watch_files.append(context["project"]["buildTape"])
        watch_files = sorted(set(watch_files))
    watch_scope = "project" if build_tape is not None or requested.is_dir() else "file"
    graph_kind = "routes" if watch_scope == "project" and route_count > 0 else ("summary" if watch_scope == "project" else "calls")
    graph_reason = (
        "inspect route-level project changes while the watched files move"
        if graph_kind == "routes" else
        "inspect compact project graph changes while the watched files move"
        if graph_kind == "summary" else
        "inspect graph changes while the watched files move"
    )
    actions = [
        _next_command_entry(
            "check",
            "recompute project diagnostics for the watched surface",
            argv=["sem", "check", "--json", str(path.resolve())],
        ),
        _next_command_entry(
            "graph",
            graph_reason,
            argv=["sem", "graph", "--kind", graph_kind, "--json", str((project_surface if watch_scope == "project" else path).resolve())],
        ),
        {
            "kind": "restart",
            "enabled": restart_on_success,
            "reason": (
                "routes are present and the current source state is ready for process restart"
                if restart_on_success else
                "routes are present, but the current source state is not ready for restart"
                if route_count > 0 else
                "no route-hosting surface detected"
            ),
        },
    ]
    if not source_ok:
        actions.insert(
            1,
            _next_command_entry(
                "fix",
                "generate repair guidance before trying to restart or rerun tests",
                argv=["sem", "fix", "--plan", "--json", str(path.resolve())],
            ),
        )
    if has_tests:
        actions.insert(
            1 if source_ok else 2,
            _next_command_entry(
                "test",
                "rerun project tests once the watched surface is at least buildable",
                argv=["sem", "test", "--json", str(path.resolve())],
            ),
        )
    elif not source_ok and has_runtime_harnesses:
        actions.insert(
            2,
            _next_command_entry(
                "test",
                "gather runtime-harness signal even while semantic diagnostics are still red",
                argv=["sem", "test", "--json", "--allow-red-preflight-harnesses", str(path.resolve())],
            ),
        )
    interface_fingerprints, interface_ns = _timed_call(_interface_fingerprints, path)
    trace_payload = {
        "enabled": bool(trace),
        "requested": bool(trace),
        "diagnosticsPassthrough": True,
    }
    if trace:
        trace_payload["phaseDurationsMs"] = {
            "context": round(context_ns / 1_000_000, 3),
            "readiness": round(readiness_ns / 1_000_000, 3),
            "check": round(check_ns / 1_000_000, 3),
            "symbols": round(symbols_ns / 1_000_000, 3),
            "interfaceFingerprints": round(interface_ns / 1_000_000, 3),
            "testDiscovery": round(test_discovery_ns / 1_000_000, 3),
        }
        trace_payload["factCounts"] = {
            "watchFiles": len(watch_files),
            "discoveredTests": len(discovered_tests),
            "routeCount": route_count,
        }
    return {
        "schemaVersion": "sem.dev.v1",
        "tool": {"name": "sem", "version": VERSION},
        "ok": source_ok and readiness.get("status") == "supported",
        "status": (
            "ready"
            if source_ok and readiness.get("status") == "supported" else
            "blocked"
            if readiness.get("status") == "blocked" else
            "quality-diagnostics"
            if source_buildable and not source_ok else
            "diagnostics"
            if not source_buildable else
            "partial"
        ),
        "mode": "watch-plan",
        "inputPath": str(path.resolve()),
        "scope": _payload_scope(
            path,
            watchScope=watch_scope,
            sourceCheckScope=check_payload["scope"]["diagnosticsScope"],
        ),
        "surfaceShift": _surface_shift(
            path,
            _requested_surface_kind(path),
            watch_scope,
            reason="watch planning expanded from the requested entry surface to the effective project surface",
        ),
        "sourceOk": source_ok,
        "buildableSource": source_buildable,
        "sourceStatus": check_payload.get("status", ""),
        "sourceSummary": check_payload.get("summary", {}),
        "watch": {
            "planOnly": True,
            "files": watch_files,
            "rerun": rerun,
            "restartOnSuccess": restart_on_success,
            "errors": watch_errors,
        },
        "restart": {
            "runnableCli": restart_on_success,
            "reason": actions[-1]["reason"],
        },
        "trace": trace_payload,
        "interfaceFingerprints": interface_fingerprints,
        "targetReadiness": readiness,
        "actions": actions,
        "nextCommands": [item for item in actions if item.get("command")],
    }


def _discover_test_entries(path: Path) -> list[dict]:
    requested = path.resolve()
    build_tape = _find_build_tape(path)
    if requested.is_file() and requested.suffix.lower() in {".sem", ".sscript"} and ".test." in requested.name:
        return [{"kind": "semantic", "path": requested, "name": requested.stem}]
    if requested.is_file() and build_tape is None:
        discovered = []
        seen = set()
        if requested.suffix.lower() in {".sem", ".sscript"}:
            companion = requested.with_name(f"{requested.stem}.test{requested.suffix}")
            if companion.is_file():
                seen.add(companion.resolve())
                discovered.append({"kind": "semantic", "path": companion.resolve(), "name": companion.stem})
        for candidate in (
            requested.parent / "scripts" / f"test_{requested.stem}.py",
            requested.parent / "tests" / f"test_{requested.stem}.py",
        ):
            resolved = candidate.resolve()
            if candidate.is_file() and resolved not in seen:
                seen.add(resolved)
                discovered.append({"kind": "python", "path": resolved, "name": resolved.stem})
        return sorted(discovered, key=lambda item: (item["kind"], str(item["path"]).lower()))
    roots = []
    if build_tape is not None:
        roots.append(build_tape.parent.resolve())
    elif requested.is_dir():
        roots.append(requested)
    else:
        roots.append(requested.parent)
    discovered = []
    seen = set()
    for root in roots:
        for pattern, kind in (
            ("**/*.test.sem", "semantic"),
            ("**/*.test.sscript", "semantic"),
            ("**/build.test.sem", "semantic"),
            ("**/scripts/test_*.py", "python"),
            ("**/tests/*.py", "python"),
        ):
            for candidate in root.glob(pattern):
                if not candidate.is_file():
                    continue
                resolved = candidate.resolve()
                if resolved in seen:
                    continue
                seen.add(resolved)
                discovered.append({"kind": kind, "path": resolved, "name": resolved.stem})
    return sorted(discovered, key=lambda item: (item["kind"], str(item["path"]).lower()))


def _semantic_test_is_trivial(test_path: Path) -> bool:
    """True when a semantic test exercises no behavior — no `call` and no
    `branch` rows, i.e. it just returns a constant. Such a test "passes" the
    semantic-check lane without proving anything (false confidence), so `sem
    test` flags it. Best-effort: any read/parse trouble => not trivial."""
    try:
        text = test_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    has_call = False
    has_branch = False
    for raw in text.splitlines():
        verb = raw.strip().split(" ", 1)[0] if raw.strip() else ""
        if verb == "call":
            has_call = True
        elif verb in ("branch", "branchIfError", "branchSelected"):
            has_branch = True
    return not (has_call or has_branch)


def _execute_semantic_contract(test_path: Path, timeout: int = 20) -> dict:
    """JIT-run a buildable semantic `.test.sem` and report whether its process
    exit code signals an assertion failure.

    `sem test`'s semantic lane is otherwise check-only — a `.test.sem` whose
    `main` returns a nonzero ExitCode still "passes" because the exit code was
    never observed. This executes the contract so a behavioral assertion can
    actually fail the suite. A *clean* nonzero exit (no compiler-error stderr) is
    an assertion failure. A run that can't compile/launch standalone (e.g. cross-
    module or webServer context, or a timeout/hang) is reported as not-executed
    rather than failed, so it never spuriously regresses a previously-green test.
    """
    try:
        proc = _capture_compiler(test_path, ["--run"], timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"executed": False, "exitCode": None,
                "reason": f"execution timed out after {timeout}s (not standalone-runnable, e.g. a server loop)"}
    except OSError as exc:
        return {"executed": False, "exitCode": None, "reason": f"could not launch: {exc}"}
    stderr = proc.stderr or ""
    # A compile/run-setup failure (parse-only passed but full codegen/link or
    # import/entry resolution failed under --run — common for a contract fragment
    # with no `entry`/`target`) is NOT an assertion failure. The compiler emits a
    # structured diagnostic block for these; a real program run does not.
    compile_failure_markers = (
        "semsc:", "phase: codegen", "phase: backend", "phase: check",
        "blocks_compile:", "error SSCG", "error SSBE", "error SEMSC",
    )
    if any(marker in stderr for marker in compile_failure_markers):
        return {"executed": False, "exitCode": proc.returncode,
                "reason": "not standalone-runnable under --run (no entry/context or codegen-only failure); check-validated only"}
    # A contract that reaches a native runtime intrinsic (sqlite.*, http.*,
    # bcrypt.*, json document API, …) cannot JIT-run: the in-process JIT links
    # no native adapters and refuses with a clear message + exit 3. That is NOT
    # an assertion failure — the contract is behaviorally untested under JIT, so
    # report not-executed (it must be exercised from a built exe / runtime
    # harness). Without this, gating-on would falsely fail every native test.
    if "native runtime intrinsics" in stderr and "in-process JIT" in stderr:
        return {"executed": False, "exitCode": proc.returncode,
                "reason": "uses native runtime intrinsics not available under the in-process JIT; "
                          "exercise it from a built executable or a runtime harness instead"}
    if proc.returncode == 0:
        return {"executed": True, "exitCode": 0, "reason": "exited 0"}
    return {"executed": True, "exitCode": proc.returncode,
            "reason": f"assertion failure - main returned nonzero exit code {proc.returncode}"}


def _semantic_contract_requests_native_exe(test_path: Path) -> bool:
    """Return true when test metadata asks sem test to use the native exe lane.

    Standard-library smokes can be valid source contracts while still being
    wrong for the in-process JIT. Keep this metadata-driven so native-only
    tests do not have to crash first before `sem test` chooses the right lane.
    """
    try:
        text = test_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    lowered = text.lower()
    return (
        "native exe" in lowered
        and ("built and run" in lowered or "build and run" in lowered)
    )


def _execute_native_semantic_contract(test_path: Path, timeout: int = 120) -> dict:
    """Build a `.test.sem` as a native executable and run it once.

    Native build/link gaps are reported as `unsupported`, not as semantic
    assertion failures. A successfully built executable that exits nonzero is a
    real runtime assertion failure.
    """
    with tempfile.TemporaryDirectory(prefix="sem-native-test-") as temp_dir:
        exe_path = Path(temp_dir) / f"{test_path.stem}.exe"
        try:
            compile_proc = _capture_compiler(
                test_path,
                ["--emit-exe", str(exe_path)],
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return {
                "attempted": True,
                "built": False,
                "executed": False,
                "exitCode": None,
                "status": "unsupported",
                "reason": f"native executable build timed out after {timeout}s",
            }
        except OSError as exc:
            return {
                "attempted": True,
                "built": False,
                "executed": False,
                "exitCode": None,
                "status": "unsupported",
                "reason": f"could not launch native build: {exc}",
            }
        if compile_proc.returncode != 0:
            return {
                "attempted": True,
                "built": False,
                "executed": False,
                "exitCode": compile_proc.returncode,
                "status": "unsupported",
                "reason": "native executable build failed; runtime harness unsupported for this surface in the current environment",
                "stdoutSnippet": (compile_proc.stdout or "")[:2000],
                "stderrSnippet": (compile_proc.stderr or "")[:2000],
            }
        try:
            run_proc = subprocess.run(
                [str(exe_path)],
                cwd=str(test_path.resolve().parent),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            return {
                "attempted": True,
                "built": True,
                "executed": False,
                "exitCode": None,
                "status": "failed",
                "reason": f"native executable timed out after {int(exc.timeout or timeout)}s",
                "stdoutSnippet": (exc.stdout or "")[:2000],
                "stderrSnippet": (exc.stderr or "")[:2000],
            }
        except OSError as exc:
            return {
                "attempted": True,
                "built": True,
                "executed": False,
                "exitCode": None,
                "status": "unsupported",
                "reason": f"could not run native executable: {exc}",
            }
        return {
            "attempted": True,
            "built": True,
            "executed": True,
            "exitCode": run_proc.returncode,
            "status": "passed" if run_proc.returncode == 0 else "failed",
            "reason": "native executable exited 0" if run_proc.returncode == 0 else
                      f"native executable returned nonzero exit code {run_proc.returncode}",
            "stdoutSnippet": (run_proc.stdout or "")[:2000],
            "stderrSnippet": (run_proc.stderr or "")[:2000],
        }


def _semantic_execution_status(execution: dict | None) -> str:
    if execution is None:
        return "not-attempted"
    if not execution.get("executed"):
        reason = str(execution.get("reason", "")).lower()
        if "native runtime intrinsics" in reason or "in-process jit" in reason:
            return "unavailable"
        return "skipped"
    return "passed" if execution.get("exitCode") in (0, None) else "failed"


def _python_harness_command(harness_path: Path) -> tuple[list[str], str, str]:
    configured = os.environ.get("SEM_TEST_PYTHON") or os.environ.get("PYTHON")
    if configured:
        try:
            configured_argv = shlex.split(configured, posix=(os.name != "nt"))
        except ValueError:
            configured_argv = [configured]
        return [*configured_argv, str(harness_path)], "environment", ""
    if getattr(sys, "frozen", False):
        current_executable = Path(sys.executable).resolve()
        for executable_name, prefix_args in (
            ("python", []),
            ("python3", []),
            ("py", ["-3"]),
        ):
            resolved = shutil.which(executable_name)
            if not resolved:
                continue
            try:
                if Path(resolved).resolve() == current_executable:
                    continue
            except OSError:
                pass
            return [resolved, *prefix_args, str(harness_path)], "path", ""
        return [], "missing", (
            "no Python interpreter found for project harness execution from packaged sem.exe; "
            "set SEM_TEST_PYTHON or install python/py on PATH"
        )
    return [sys.executable, str(harness_path)], "current-process", ""


def _run_test_payload(path: Path, include_python_harnesses: bool = True, allow_red_preflight_harnesses: bool = False, execute_contracts: bool = False) -> dict:
    preflight = _build_check_payload(path, [], include_readiness=False)
    preflight_ok = bool(preflight.get("ok", False))
    # A test run's pass/fail must reflect whether the project COMPILES and whether
    # the selected tests pass — not whether the linter is silent. `preflight.ok`
    # is False for any non-blocking advisory, so gating the overall result on it
    # made a buildable project with passing tests report ok:false /
    # status:diagnostics. Gate on `buildable` instead; advisories stay visible via
    # `compositeStatus` and the per-test diagnostics.
    preflight_buildable = bool(preflight.get("buildable", preflight_ok))
    discovered = _discover_test_entries(path)
    build_tape = _find_build_tape(path)
    requested = path.resolve()
    runtime_probe_mode = bool(
        allow_red_preflight_harnesses
        and not preflight_ok
        and (build_tape is not None or requested.is_dir())
    )
    runtime_cwd = str(
        (
            build_tape.parent
            if build_tape is not None else
            path.resolve()
            if path.resolve().is_dir() else
            path.resolve().parent
        ).resolve()
    )
    results = []
    passed = 0
    failed = 0
    skipped = 0
    selected = 0
    semantic_contract_discovered = 0
    semantic_contract_executed = 0
    semantic_contract_failed = 0
    trivial_semantic_tests = 0
    source_checks_executed = 0
    jit_contracts_attempted = 0
    jit_contracts_executed = 0
    jit_contracts_failed = 0
    jit_contracts_unavailable = 0
    native_harness_discovered = 0
    native_harness_attempted = 0
    native_harness_executed = 0
    native_harness_failed = 0
    native_harness_unsupported = 0
    python_harness_discovered = 0
    python_harness_executed = 0
    python_harness_failed = 0
    for entry in discovered:
        start = time.time()
        if entry["kind"] == "semantic":
            if runtime_probe_mode:
                semantic_contract_discovered += 1
                results.append({
                    "name": entry["name"],
                    "kind": entry["kind"],
                    "lane": "semantic-contract",
                    "executionModel": "semantic-check",
                    "path": str(entry["path"]),
                    "status": "skipped",
                    "reason": "semantic contract execution deferred while gathering runtime harness signal on a red project surface",
                })
                skipped += 1
                continue
            semantic_contract_discovered += 1
            semantic_contract_executed += 1
            payload = _build_check_payload(entry["path"], [])
            ok = bool(payload["ok"])
            source_checks_executed += 1
            selected += 1
            trivial = _semantic_test_is_trivial(Path(entry["path"]))
            if trivial:
                trivial_semantic_tests += 1
            # Opt-in: JIT-run non-trivial, buildable contracts so a behavioral
            # assertion (main returning a nonzero ExitCode) actually fails the
            # suite, instead of the check-only lane silently passing it.
            execution = None
            native_execution = None
            native_required = _semantic_contract_requests_native_exe(Path(entry["path"]))
            if execute_contracts and ok and not trivial:
                if native_required:
                    native_harness_discovered += 1
                    native_harness_attempted += 1
                    native_execution = _execute_native_semantic_contract(Path(entry["path"]))
                else:
                    jit_contracts_attempted += 1
                    execution = _execute_semantic_contract(Path(entry["path"]))
                    jit_status = _semantic_execution_status(execution)
                    if jit_status == "passed":
                        jit_contracts_executed += 1
                    elif jit_status == "failed":
                        jit_contracts_executed += 1
                        jit_contracts_failed += 1
                    elif jit_status == "unavailable":
                        jit_contracts_unavailable += 1
                        native_harness_discovered += 1
                        native_harness_attempted += 1
                        native_execution = _execute_native_semantic_contract(Path(entry["path"]))
            assertion_failed = bool(
                execution and execution["executed"]
                and execution["exitCode"] not in (0, None)
            )
            native_failed = bool(native_execution and native_execution.get("status") == "failed")
            native_unsupported = bool(native_execution and native_execution.get("status") == "unsupported")
            if native_execution is not None:
                if native_execution.get("executed"):
                    native_harness_executed += 1
                if native_failed:
                    native_harness_failed += 1
                elif native_unsupported:
                    native_harness_unsupported += 1
            final_ok = ok and not assertion_failed and not native_failed
            duration_ms = int((time.time() - start) * 1000)
            if native_execution and native_execution.get("executed"):
                execution_model = "semantic-check+native-exe"
                runtime_coverage = "native-runtime-exercised"
            elif native_execution and native_execution.get("status") == "unsupported":
                execution_model = "semantic-check+native-exe-unsupported"
                runtime_coverage = "native-runtime-unsupported"
            elif execution and execution.get("executed"):
                execution_model = "semantic-check+jit-run"
                runtime_coverage = "jit-executed"
            elif execution and _semantic_execution_status(execution) == "unavailable":
                execution_model = "semantic-check+jit-unavailable"
                runtime_coverage = "runtime-unavailable"
            else:
                execution_model = "semantic-check"
                runtime_coverage = "source-checked"
            result = {
                "name": entry["name"],
                "kind": entry["kind"],
                "lane": "semantic-contract",
                "executionModel": execution_model,
                "path": str(entry["path"]),
                "status": "passed" if final_ok else "failed",
                "durationMs": duration_ms,
                "summary": payload["summary"],
                "checkStatus": payload["status"],
                "diagnostics": payload["diagnostics"],
                "checkCommand": f"sem check --json {entry['path']}",
                # A semantic test is check-validated; unless executed it asserts
                # nothing behaviorally. Surfaced so a green run isn't mistaken for
                # behavioral coverage.
                "exercisesAssertions": not trivial,
                "sourceCheck": {
                    "executed": True,
                    "status": payload["status"],
                },
                "jitExecution": {
                    "attempted": bool(execution),
                    "executed": bool(execution and execution.get("executed")),
                    "status": _semantic_execution_status(execution),
                    "reason": execution.get("reason") if execution else "",
                },
                "nativeExecution": native_execution or {
                    "attempted": False,
                    "built": False,
                    "executed": False,
                    "status": "not-required" if not native_required else "not-attempted",
                    "reason": "",
                },
                "runtimeCoverage": runtime_coverage,
                "warning": (
                    "test exercises no assertions (no call/branch rows) — it only "
                    "proves the file parses, checks, and is buildable"
                    if trivial else None
                ),
            }
            if execution is not None:
                result["execution"] = execution
            results.append(result)
            if final_ok:
                passed += 1
            else:
                failed += 1
                semantic_contract_failed += 1
            continue
        python_harness_discovered += 1
        if entry["kind"] == "python" and not preflight_ok and not allow_red_preflight_harnesses:
            results.append({
                "name": entry["name"],
                "kind": entry["kind"],
                "lane": "runtime-harness",
                "executionModel": "process-harness",
                "path": str(entry["path"]),
                "cwd": runtime_cwd,
                "status": "skipped",
                "reason": "python harness execution deferred until semantic preflight is clean",
            })
            skipped += 1
            continue
        if entry["kind"] == "python" and not include_python_harnesses:
            results.append({
                "name": entry["name"],
                "kind": entry["kind"],
                "lane": "runtime-harness",
                "executionModel": "process-harness",
                "path": str(entry["path"]),
                "cwd": runtime_cwd,
                "status": "skipped",
                "reason": "python harness execution disabled",
            })
            skipped += 1
            continue
        selected += 1
        python_harness_executed += 1
        command, interpreter_source, command_error = _python_harness_command(Path(entry["path"]))
        if command_error:
            duration_ms = int((time.time() - start) * 1000)
            failed += 1
            python_harness_failed += 1
            results.append({
                "name": entry["name"],
                "kind": entry["kind"],
                "lane": "runtime-harness",
                "executionModel": "process-harness",
                "path": str(entry["path"]),
                "cwd": runtime_cwd,
                "status": "error",
                "durationMs": duration_ms,
                "stdoutSnippet": "",
                "stderrSnippet": "",
                "pythonInterpreterSource": interpreter_source,
                "command": [],
                "error": command_error,
            })
            continue
        try:
            proc = subprocess.run(
                command,
                cwd=runtime_cwd,
                capture_output=True,
                text=True,
                timeout=600,
            )
            duration_ms = int((time.time() - start) * 1000)
            ok = proc.returncode == 0
        except subprocess.TimeoutExpired as exc:
            duration_ms = int((time.time() - start) * 1000)
            failed += 1
            python_harness_failed += 1
            results.append({
                "name": entry["name"],
                "kind": entry["kind"],
                "lane": "runtime-harness",
                "executionModel": "process-harness",
                "path": str(entry["path"]),
                "cwd": runtime_cwd,
                "status": "timed-out",
                "durationMs": duration_ms,
                "timeoutSeconds": int(exc.timeout or 600),
                "stdoutSnippet": (exc.stdout or "")[:2000],
                "stderrSnippet": (exc.stderr or "")[:2000],
                "pythonInterpreterSource": interpreter_source,
                "command": _display_command(command),
                "error": "python harness timed out",
            })
            continue
        except OSError as exc:
            duration_ms = int((time.time() - start) * 1000)
            failed += 1
            python_harness_failed += 1
            results.append({
                "name": entry["name"],
                "kind": entry["kind"],
                "lane": "runtime-harness",
                "executionModel": "process-harness",
                "path": str(entry["path"]),
                "cwd": runtime_cwd,
                "status": "error",
                "durationMs": duration_ms,
                "stdoutSnippet": "",
                "stderrSnippet": "",
                "pythonInterpreterSource": interpreter_source,
                "command": _display_command(command),
                "error": str(exc),
            })
            continue
        results.append({
            "name": entry["name"],
            "kind": entry["kind"],
            "lane": "runtime-harness",
            "executionModel": "process-harness",
            "path": str(entry["path"]),
            "cwd": runtime_cwd,
            "status": "passed" if ok else "failed",
            "durationMs": duration_ms,
            "stdoutSnippet": proc.stdout[:2000],
            "stderrSnippet": proc.stderr[:2000],
            "pythonInterpreterSource": interpreter_source,
            "command": _display_command(command),
        })
        if ok:
            passed += 1
        else:
            failed += 1
            python_harness_failed += 1
    runtime_harness_discovered = python_harness_discovered + native_harness_discovered
    runtime_harness_executed = python_harness_executed + native_harness_executed
    runtime_harness_failed = python_harness_failed + native_harness_failed
    runtime_signal_status = (
        "deferred"
        if any(
            result.get("kind") == "python"
            and result.get("status") == "skipped"
            and "semantic preflight" in result.get("reason", "")
            for result in results
        ) else
        "failed"
        if runtime_harness_failed else
        "executed"
        if runtime_harness_executed else
        "unsupported"
        if native_harness_unsupported else
        "not-requested"
        if python_harness_discovered and not include_python_harnesses else
        "none"
    )
    runtime_harness_status = (
        "deferred"
        if runtime_signal_status == "deferred" else
        "failed"
        if runtime_harness_failed else
        "passed"
        if runtime_harness_executed else
        "unsupported"
        if runtime_signal_status == "unsupported" else
        "not-requested"
        if runtime_signal_status == "not-requested" else
        "none"
    )
    semantic_contract_status = (
        "deferred"
        if runtime_probe_mode and semantic_contract_executed == 0 else
        "failed"
        if semantic_contract_failed else
        "passed"
        if semantic_contract_executed else
        "none"
    )
    status = "passed"
    if not preflight_buildable:
        status = "diagnostics"
    elif not preflight_ok and selected == 0 and skipped:
        status = "diagnostics"
    elif selected == 0:
        status = "no-tests"
    elif failed:
        status = "failed"
    payload = {
        "schemaVersion": "sem.test.v1",
        "tool": {"name": "sem", "version": VERSION},
        "inputPath": str(path.resolve()),
        "ok": status == "passed" and preflight_buildable,
        "status": status,
        "compositeStatus": (
            f"{preflight.get('status', 'ok')}/runtime-{runtime_harness_status}"
            if not preflight_ok else
            f"ok/runtime-{runtime_harness_status}"
        ),
        "scope": _payload_scope(
            path,
            preflightScope=preflight["scope"]["diagnosticsScope"],
            discoveryScope="project" if _find_build_tape(path) is not None or path.resolve().is_dir() else "file",
        ),
        "preflightCheck": {
            "ok": preflight_ok,
            "status": preflight.get("status", ""),
            "summary": preflight.get("summary", {}),
        },
        "preflightStatus": preflight.get("status", ""),
        "semanticContractStatus": semantic_contract_status,
        "runtimeHarnessStatus": runtime_harness_status,
        "discoveredTests": len(discovered),
        "selectedTests": selected,
        "executedTests": passed + failed,
        "passedTests": passed,
        "failedTests": failed,
        "skippedTests": skipped,
        "pythonHarnessesDeferred": any(
            result.get("kind") == "python"
            and result.get("status") == "skipped"
            and "semantic preflight" in result.get("reason", "")
            for result in results
        ),
        "coverageSummary": {
            "sourceChecksExecuted": source_checks_executed,
            "semanticContractsDiscovered": semantic_contract_discovered,
            "semanticContractsExecuted": semantic_contract_executed,
            "semanticContractsFailed": semantic_contract_failed,
            "trivialSemanticTests": trivial_semantic_tests,
            "jitContractsAttempted": jit_contracts_attempted,
            "jitContractsExecuted": jit_contracts_executed,
            "jitContractsFailed": jit_contracts_failed,
            "jitContractsUnavailable": jit_contracts_unavailable,
            "runtimeHarnessesDiscovered": runtime_harness_discovered,
            "runtimeHarnessesExecuted": runtime_harness_executed,
            "runtimeHarnessesFailed": runtime_harness_failed,
            "pythonHarnessesDiscovered": python_harness_discovered,
            "pythonHarnessesExecuted": python_harness_executed,
            "pythonHarnessesFailed": python_harness_failed,
            "nativeHarnessesDiscovered": native_harness_discovered,
            "nativeHarnessesAttempted": native_harness_attempted,
            "nativeHarnessesExecuted": native_harness_executed,
            "nativeHarnessesFailed": native_harness_failed,
            "nativeHarnessesUnsupported": native_harness_unsupported,
            "runtimeSignalStatus": runtime_signal_status,
        },
        "results": results,
    }
    if trivial_semantic_tests:
        payload["warnings"] = [
            f"{trivial_semantic_tests} semantic test(s) exercise no assertions "
            f"(no call/branch rows). A passing `sem test` for these only proves "
            f"they parse, check, and build — not that any behavior is correct."
        ]
    payload["nextCommands"] = _test_next_commands(
        path,
        failed,
        source_ok=preflight_ok,
        python_harnesses_deferred=payload["pythonHarnessesDeferred"],
    )
    return payload


def _skill_registry_payload() -> list[dict]:
    alias_groups: dict[str, list[str]] = {}
    for alias, canonical in SKILL_ALIASES.items():
        alias_groups.setdefault(canonical, []).append(alias)
    payload = []
    paths_ephemeral = bool(getattr(sys, "frozen", False))
    for entry in SKILL_REGISTRY:
        files = [str((ROOT.parent / relative).resolve()) for relative in entry["files"]]
        item = {
            "name": entry["name"],
            "description": entry["description"],
            "files": files,
            "fileSources": list(entry["files"]),
            "aliases": sorted(alias_groups.get(entry["name"], [])),
            "pathsEphemeral": paths_ephemeral,
        }
        if paths_ephemeral:
            item["contentHint"] = (
                "`files` resolve inside the packaged executable's temporary extraction directory. "
                "Use `sem skills get NAME --full --json` for durable inline skill bodies."
            )
        payload.append(item)
    return payload


def _markdown_heading_index(text: str) -> list[dict]:
    headings = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if line[: len(line) - len(line.lstrip())]:
            continue
        stripped = line.lstrip()
        if not stripped.startswith("#"):
            continue
        level = len(stripped) - len(stripped.lstrip("#"))
        title = stripped[level:].strip()
        if not title:
            continue
        headings.append({
            "line": line_number,
            "level": level,
            "title": title,
        })
    return headings


def _skill_content(name: str, *, include_full_content: bool = False) -> dict | None:
    for entry in SKILL_REGISTRY:
        if entry["name"] != name:
            continue
        aliases = sorted(alias for alias, canonical in SKILL_ALIASES.items() if canonical == name)
        sections = []
        file_summaries = []
        total_bytes = 0
        for relative in entry["files"]:
            path = ROOT.parent / relative
            if not path.exists():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            total_bytes += len(text.encode("utf-8"))
            file_summary = {
                "source": relative,
                "path": str(path.resolve()),
                "bytes": len(text.encode("utf-8")),
                "lineCount": len(text.splitlines()),
                "headings": _markdown_heading_index(text),
            }
            file_summaries.append(file_summary)
            if include_full_content:
                sections.append(f"# Source: {relative}\n\n{text.strip()}\n")
        payload = {
            "name": entry["name"],
            "resolvedName": entry["name"],
            "description": entry["description"],
            "files": [str((ROOT.parent / relative).resolve()) for relative in entry["files"]],
            "fileSources": list(entry["files"]),
            "aliases": aliases,
            "contentMode": "full" if include_full_content else "summary",
            "contentBytes": total_bytes,
            "fileSummaries": file_summaries,
            "sectionIndex": [
                {
                    "source": summary["source"],
                    "line": heading["line"],
                    "level": heading["level"],
                    "title": heading["title"],
                }
                for summary in file_summaries
                for heading in summary["headings"]
            ],
        }
        if include_full_content:
            payload["content"] = "\n".join(sections).strip() + ("\n" if sections else "")
        else:
            # Summary mode returns `files` as filesystem paths. In the packaged
            # sem.exe those resolve into a PyInstaller `_MEI*` extraction dir
            # that is deleted when the process exits, so the paths are not
            # re-readable later. Tell the caller to use --full for durable
            # inline bodies instead of chasing ephemeral paths.
            payload["pathsEphemeral"] = bool(getattr(sys, "frozen", False))
            payload["contentHint"] = (
                "`files` are filesystem paths, not bodies; in the packaged "
                "sem.exe they resolve into a temporary extraction directory "
                "removed on process exit. Pass --full (contentMode=full) to "
                "receive durable inline bodies."
            )
        return payload
    return None


@functools.lru_cache(maxsize=1)
def _diagnostic_index_payload() -> dict[str, dict]:
    index: dict[str, dict] = {
        "SSRUN001": {
            "code": "SSRUN001",
            "title": "runtime panic",
            "summary": "The program trapped with SemanticScript runtime panic context.",
            "references": [],
            "relatedCodes": [],
        },
        "SSRUN002": {
            "code": "SSRUN002",
            "title": "native fault",
            "summary": "A fatal signal or structured exception was caught and reported with the last semantic site.",
            "references": [],
            "relatedCodes": ["SSRUN001"],
        },
    }
    comment_pattern = re.compile(r"#\s*((?:SS(?:RUN)?\d{4,5})(?:\s*/\s*SS(?:RUN)?\d{4,5})*)\s+(.*)")
    code_pattern = re.compile(r"SS(?:RUN)?\d{4,5}")
    for relative in DIAGNOSTIC_INDEX_PATHS:
        path = ROOT.parent / relative
        if not path.exists():
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for index_line, line in enumerate(lines, start=1):
            matches = code_pattern.findall(line)
            if not matches:
                continue
            title = ""
            comment_match = comment_pattern.match(line.strip())
            if comment_match:
                title = comment_match.group(2).strip()
                title = re.sub(r"\s+\(.*$", "", title).strip()
            excerpt = line.strip()
            for code in matches:
                entry = index.setdefault(code, {
                    "code": code,
                    "title": title or code,
                    "summary": title or code,
                    "references": [],
                    "relatedCodes": [],
                })
                if title and entry.get("title", code) == code:
                    entry["title"] = title
                    entry["summary"] = title
                entry["references"].append({
                    "path": str(path.resolve()),
                    "line": index_line,
                    "excerpt": excerpt,
                })
                related = [item for item in matches if item != code]
                if related:
                    current = set(entry.get("relatedCodes", []))
                    current.update(related)
                    entry["relatedCodes"] = sorted(current)
    return index


def _diagnostic_has_explainer(code: str) -> bool:
    if not code:
        return False
    if code in DIAGNOSTIC_EXPLAINERS:
        return True
    return code in _diagnostic_index_payload()


def _diagnostic_explain_payload(code: str) -> dict:
    index = _diagnostic_index_payload()
    entry = index.get(code)
    curated = DIAGNOSTIC_EXPLAINERS.get(code, {})
    if entry is None and not curated:
        return {
            "schemaVersion": "sem.explain.v1",
            "tool": {"name": "sem", "version": VERSION},
            "ok": False,
            "status": "not-found",
            "code": code,
            "found": False,
            "title": "",
            "summary": "",
            "references": [],
            "relatedCodes": [],
            "whyItMatters": [],
            "commonFixes": [],
            "nextCommands": _explain_next_commands(code, repeatable=False),
        }
    if entry is None:
        # No index reference yet, but we ship a curated explainer for this code
        # (e.g. a newly added diagnostic). Treat the curated entry as a found
        # explainer rather than reporting the code as unknown.
        return {
            "schemaVersion": "sem.explain.v1",
            "tool": {"name": "sem", "version": VERSION},
            "ok": True,
            "status": "ok",
            "code": code,
            "found": True,
            "title": curated.get("title", ""),
            "summary": curated.get("summary", ""),
            "references": [],
            "relatedCodes": [],
            "whyItMatters": curated.get("whyItMatters", []),
            "commonFixes": curated.get("commonFixes", []),
            "note": "Curated explainer; no repository index reference recorded yet.",
            "nextCommands": _explain_next_commands(code),
        }
    return {
        "schemaVersion": "sem.explain.v1",
        "tool": {"name": "sem", "version": VERSION},
        "ok": True,
        "status": "ok",
        "code": code,
        "found": True,
        "title": curated.get("title", entry.get("title", code)),
        "summary": curated.get("summary", entry.get("summary", entry.get("title", code))),
        "references": entry.get("references", []),
        "relatedCodes": entry.get("relatedCodes", []),
        "whyItMatters": curated.get("whyItMatters", []),
        "commonFixes": curated.get("commonFixes", []),
        "note": "This is a repository-backed explainer built from the current docs and linter tests. Use the cited sources for full rule context.",
        "nextCommands": _explain_next_commands(code),
    }


def _operation_insert_anchor(operation) -> int:
    line_numbers = [
        source_line.number
        for source_line in operation.lines
        if source_line.tokens
        and source_line.verb in {
            "input",
            "output",
            "effect",
            "useCapability",
            "authority",
            "memory",
            "async",
            "purpose",
            "invariant",
        }
    ]
    return max(line_numbers) if line_numbers else operation.line.number


# Verbs whose syntax cutover is a pure in-place subject-qualifier insertion
# (`input main x` -> `input operation main x`). The migrator never reorders
# these rows, so a positional `replaceLine` on their line is provably correct.
# Other rewrites the migrator performs (notably `branch` else-arm synthesis) can
# be line-count-neutral yet REORDER rows, which would make positional indexing
# read the wrong line — those are deliberately excluded from auto-apply.
_CUTOVER_AUTOFIX_VERBS = frozenset({"input", "output", "purpose", "invariant"})


def _is_inplace_cutover_rewrite(before_line: str, after_line: str) -> bool:
    """True only when `after_line` is `before_line` with exactly one subject-kind
    token inserted right after the verb, and the verb is a known in-place cutover
    verb. This rejects line-count-neutral reorders (e.g. a `branch` row whose
    migrated content moved to a different line), where trusting `after[L-1]`
    positionally would corrupt the file."""
    before_tokens = before_line.split()
    after_tokens = after_line.split()
    if not before_tokens or not after_tokens:
        return False
    if before_tokens[0] not in _CUTOVER_AUTOFIX_VERBS:
        return False
    # Same verb, one extra token inserted at index 1, identical tail.
    if after_tokens[0] != before_tokens[0]:
        return False
    if len(after_tokens) != len(before_tokens) + 1:
        return False
    return after_tokens[2:] == before_tokens[1:]


@functools.lru_cache(maxsize=256)
def _migrated_file_lines(file_path: str) -> tuple[tuple[str, ...], tuple[str, ...]] | None:
    """Return (original_lines, migrated_lines) for a file via the authoritative
    `syntax_migration.migrate_text`, but ONLY when the migration preserves the
    line count. The syntax cutover qualifies rows in place (`input` ->
    `input operation`, etc.), so equal line counts mean a per-line `replaceLine`
    reproduces the migrated row exactly. Returns None when the file can't be read
    or the line count changed (then auto-apply is skipped — preview-only fix).
    Even with equal line counts, callers must additionally confirm the specific
    row is an in-place rewrite (see `_is_inplace_cutover_rewrite`) because the
    migrator can reorder `branch` rows without changing the line count."""
    try:
        from tools import syntax_migration
    except ImportError:
        return None
    try:
        original = Path(file_path).read_text(encoding="utf-8")
    except OSError:
        return None
    result = syntax_migration.migrate_text(original)
    migrated = getattr(result, "text", None)
    if migrated is None or migrated == original:
        return None
    before = original.splitlines()
    after = migrated.splitlines()
    if len(before) != len(after):
        return None
    return tuple(before), tuple(after)


_CALL_NAME_LEADING_VERBS = {
    # Verbs where the call name is at args[0] (the call site is the leading
    # identifier). Renaming a call binding must rewrite every such row that
    # references it inside the enclosing operation.
    "call", "run", "runChecked", "start", "await",
    "startInGroup", "timeout", "cancelOn",
    "argument", "arg", "case",
}


def _line_references_call_subject(verb: str, args: list, name: str) -> bool:
    """True if this row attaches to a call binding named NAME — used by the
    SS4001 rename codemod to identify every call-attachment row inside an
    operation that must be rewritten when the call's name changes. Covers the
    standard grammar: call/argument/run*/start/await/bind*/branch error
    source/ignore */case/startInGroup/timeout/cancelOn."""
    if not args:
        return False
    if verb in _CALL_NAME_LEADING_VERBS and args[0] == name:
        return True
    if verb == "ignore" and len(args) >= 3 and args[1] == "source" and args[2] == name:
        return True
    if verb == "bind" and len(args) >= 4 and args[3] == name:
        return True
    if verb in {"bindOk", "bindError"} and len(args) >= 3 and args[2] == name:
        return True
    if verb == "branch" and len(args) >= 4 and args[0] == "error" and args[1] == "source" and args[2] == name:
        return True
    return False


def _rename_local_name_edits(source: Path, operation: object, old_name: str, new_name: str) -> list[dict]:
    """Return replaceLine edits for a local value/error/failure rename.

    The rename is intentionally scoped to the enclosing operation and to rows
    whose tokenized args mention OLD_NAME. That keeps the codemod useful for
    mechanical role-suffix repairs without turning it into a global refactor.
    """
    try:
        file_text = Path(source).read_text(encoding="utf-8")
    except OSError:
        return []
    file_lines = file_text.split("\n")
    pattern = re.compile(r"\b" + re.escape(old_name) + r"\b")
    edits: list[dict] = []
    file_path_str = str(Path(source).resolve())
    for source_line in operation.lines:
        if not source_line.tokens or source_line.verb.startswith("#"):
            continue
        if old_name not in source_line.args:
            continue
        idx = source_line.number - 1
        if not (0 <= idx < len(file_lines)):
            continue
        original = file_lines[idx]
        rewritten = pattern.sub(new_name, original)
        if rewritten != original:
            edits.append({
                "op": "replaceLine",
                "file": file_path_str,
                "line": source_line.number,
                "text": rewritten,
            })
    return edits


def _enclosing_operation_for_diagnostic(diagnostic: dict, operation_lookup: dict) -> tuple | None:
    """Locate the operation that contains the diagnostic's primary span line.
    Used by per-call style rules (SS4001) where the diagnostic's subject is the
    call name, not the operation, so subject_name cannot key operation_lookup
    directly. The check-payload's serialized form strips the linter's `related`
    field, so we identify the enclosing operation by scanning each operation's
    own .lines for the diagnostic's line number — robust to that filtering."""
    span = diagnostic.get("span") or diagnostic.get("primary") or {}
    if not isinstance(span, dict):
        return None
    file_str = span.get("file") or span.get("path") or ""
    line_no = int(span.get("line", 0) or 0)
    if not file_str or not line_no:
        return None
    try:
        target_path = Path(file_str).resolve()
    except (OSError, ValueError):
        return None
    for source, facts, operation in operation_lookup.values():
        try:
            source_path = Path(source).resolve()
        except (OSError, ValueError, TypeError):
            continue
        if source_path != target_path:
            continue
        for source_line in operation.lines:
            if source_line.number == line_no:
                return (Path(source), facts, operation)
    return None


def _repair_plan_for_diagnostic(path: Path, diagnostic: dict, bundle: dict, *, operation_lookup: dict[str, tuple[Path, object, object]] | None = None) -> dict:
    lookup = operation_lookup if operation_lookup is not None else _facts_operation_lookup(bundle)
    code = diagnostic.get("code", "")
    subject_name = diagnostic.get("subjectName", "")
    subject_kind = diagnostic.get("subjectKind", "")
    fix_candidates = list(diagnostic.get("fixCandidates", []))
    repair = {
        "diagnostic": code,
        "kind": diagnostic.get("kind", ""),
        "subjectName": subject_name,
        "subjectKind": subject_kind,
        "fixSafety": diagnostic.get("repair", {}).get("fixSafety", "requires-human-review"),
        "edits": [],
        "suggestions": [
            {
                "name": candidate.get("name", ""),
                "shape": candidate.get("shape", ""),
                "autoApplicable": bool(candidate.get("autoApplicable", False)),
            }
            for candidate in fix_candidates
        ],
        "verification": [
            f"sem check --json {path}",
            f"sem fmt --check {path}",
        ],
    }
    if code in ("SS0002", "SS0003"):
        # Syntax-cutover rows are rewritten deterministically by
        # `sem migrate-syntax`. Reuse that migrator to produce the exact
        # rewritten row and emit it as an auto-applicable `replaceLine` edit, so
        # `sem fix`/`patch` can apply the single fix every new user hits first
        # (previously gated as requires-human-review).
        span = diagnostic.get("span", {})
        file_path = span.get("file") or ""
        line_no = int(span.get("line", 0) or 0)
        migrated_pair = _migrated_file_lines(file_path) if file_path else None
        if migrated_pair is not None and 0 < line_no <= len(migrated_pair[1]):
            before_line = migrated_pair[0][line_no - 1]
            after_line = migrated_pair[1][line_no - 1]
            if before_line != after_line and _is_inplace_cutover_rewrite(before_line, after_line):
                repair["fixSafety"] = "local-edit"
                for suggestion in repair["suggestions"]:
                    if suggestion.get("name") in ("runMigrateSyntax", "rewriteToNewSyntax"):
                        suggestion["autoApplicable"] = True
                repair["edits"].append({
                    "op": "replaceLine",
                    "file": file_path,
                    "line": line_no,
                    "text": after_line,
                })
        return repair
    if code == "SS3104":
        for suggestion in repair["suggestions"]:
            if suggestion.get("name") == "inlineAuthority":
                effect_path = diagnostic.get("actual", "")
                if "declares `" in effect_path and effect_path.endswith("`"):
                    effect_text = effect_path.split("declares `", 1)[1][:-1]
                    parts = effect_text.split()
                    if len(parts) == 3 and parts[0] == subject_name:
                        suggestion["shape"] = f"authority {parts[0]} {parts[1]} {parts[2]}"
    operation_entry = lookup.get(subject_name)
    if operation_entry is None and subject_kind == "operation":
        return repair
    if code == "SS3104" and operation_entry is not None:
        source, _facts, operation = operation_entry
        for source_line in operation.lines:
            if not source_line.tokens or source_line.verb != "effect":
                continue
            args = source_line.args
            if len(args) >= 3 and args[0] == subject_name:
                for suggestion in repair["suggestions"]:
                    if suggestion.get("name") == "inlineAuthority":
                        suggestion["shape"] = f"authority {subject_name} {args[1]} {args[2]}"
                repair["edits"].append({
                    "op": "insertAfterLine",
                    "file": str(source.resolve()),
                    "afterLine": _operation_insert_anchor(operation),
                    "text": f"authority {subject_name} {args[1]} {args[2]}",
                })
                break
    elif code == "SS3101" and operation_entry is not None:
        source, _facts, operation = operation_entry
        repair["fixSafety"] = "requires-human-review"
        repair["edits"].append({
            "op": "insertAfterLine",
            "file": str(source.resolve()),
            "afterLine": _operation_insert_anchor(operation),
            "text": f'purpose operation {subject_name} "<describe {subject_name} purpose>"',
        })
    elif code == "SS3102" and operation_entry is not None:
        source, _facts, operation = operation_entry
        repair["fixSafety"] = "requires-human-review"
        repair["edits"].append({
            "op": "insertAfterLine",
            "file": str(source.resolve()),
            "afterLine": _operation_insert_anchor(operation),
            "text": f'invariant operation {subject_name} "<state the key invariant for {subject_name}>"',
        })
    elif code == "SS4001" and subject_name and not subject_name.endswith("Call"):
        # Mechanical rename codemod: vague call names (SS4001) → append `Call`
        # suffix on the binding AND every reference inside the enclosing
        # operation. The dashboard logged 57+ such renames in one cycle; doing
        # them by hand is the boilerplate the field log ranked the #3 pain.
        # Subject is the call name, so locate the enclosing operation via the
        # diagnostic's `related[role=enclosingOperation]` span rather than
        # operation_lookup (which keys on operation name, not call name).
        enclosing = _enclosing_operation_for_diagnostic(diagnostic, lookup)
        if enclosing is not None:
            source, _facts, operation = enclosing
            new_name = subject_name + "Call"
            try:
                file_text = Path(source).read_text(encoding="utf-8")
            except OSError:
                file_text = None
            if file_text is not None:
                file_lines = file_text.split("\n")
                # `\b` word-boundary regex with count=1 rewrites only the first
                # whole-word occurrence on the line. On a call-attachment row
                # the call name is the first identifier of that name (after the
                # verb keyword), so a single replacement is precise and avoids
                # rewriting any unrelated later token that happens to share the
                # name (e.g. a value arg that coincidentally matches).
                pattern = re.compile(r"\b" + re.escape(subject_name) + r"\b")
                file_path_str = str(Path(source).resolve())
                for source_line in operation.lines:
                    if not source_line.tokens:
                        continue
                    if not _line_references_call_subject(
                            source_line.verb, source_line.args, subject_name):
                        continue
                    idx = source_line.number - 1
                    if not (0 <= idx < len(file_lines)):
                        continue
                    original = file_lines[idx]
                    rewritten = pattern.sub(new_name, original, count=1)
                    if rewritten != original:
                        repair["edits"].append({
                            "op": "replaceLine",
                            "file": file_path_str,
                            "line": source_line.number,
                            "text": rewritten,
                        })
                if repair["edits"]:
                    repair["fixSafety"] = "local-edit"
                    for suggestion in repair["suggestions"]:
                        if suggestion.get("name") == "renameToDescriptive":
                            suggestion["autoApplicable"] = True
    elif code == "SS4002" and subject_name and not subject_name.endswith("Error"):
        enclosing = _enclosing_operation_for_diagnostic(diagnostic, lookup)
        if enclosing is not None:
            source, _facts, operation = enclosing
            repair["edits"].extend(
                _rename_local_name_edits(Path(source), operation, subject_name, subject_name + "Error")
            )
            if repair["edits"]:
                repair["fixSafety"] = "local-edit"
                for suggestion in repair["suggestions"]:
                    if suggestion.get("name") == "renameToDescriptive":
                        suggestion["autoApplicable"] = True
    elif code == "SS4003" and subject_name and not subject_name.endswith("Failure"):
        enclosing = _enclosing_operation_for_diagnostic(diagnostic, lookup)
        if enclosing is not None:
            source, _facts, operation = enclosing
            repair["edits"].extend(
                _rename_local_name_edits(Path(source), operation, subject_name, subject_name + "Failure")
            )
            if repair["edits"]:
                repair["fixSafety"] = "local-edit"
                for suggestion in repair["suggestions"]:
                    if suggestion.get("name") == "renameToDescriptive":
                        suggestion["autoApplicable"] = True
    return repair


def _build_fix_plan_payload(path: Path, compiler_args: list[str], *, include_warnings: bool = False) -> dict:
    check_payload = _build_check_payload(path, compiler_args)
    bundle = _collect_facts_bundle(path)
    check_scope = check_payload.get("scope", {})
    operation_lookup = (
        _facts_operation_lookup(bundle)
        if all(isinstance(item, dict) and "facts" in item for item in bundle.get("files", []))
        else {}
    )
    repair_diagnostics = []
    for diagnostic in check_payload["diagnostics"]:
        if not include_warnings and diagnostic.get("severity") == "warning" and not diagnostic.get("blocksCompile"):
            continue
        if diagnostic.get("repair", {}).get("id") or diagnostic.get("code") in {"SS3101", "SS3102", "SS3104"}:
            repair_diagnostics.append(diagnostic)
    repairs = [
        _repair_plan_for_diagnostic(path.resolve(), diagnostic, bundle, operation_lookup=operation_lookup)
        for diagnostic in repair_diagnostics
    ]
    for repair in repairs:
        if repair.get("edits") and repair.get("fixSafety") not in {"safe", "local-edit"}:
            repair["reviewEdits"] = list(repair.get("edits", []))
            repair["edits"] = []
    # Distinct diagnostics can target the same row (e.g. a cutover row trips both
    # SS0002 arity and SS0003 syntax), each emitting the identical replaceLine
    # edit. Collapse duplicates so the plan carries one edit per target line.
    seen_edit_keys: set = set()
    for repair in repairs:
        deduped = []
        for edit in repair.get("edits", []):
            key = (edit.get("file"), edit.get("op"), edit.get("line"), edit.get("afterLine"))
            if key in seen_edit_keys:
                continue
            seen_edit_keys.add(key)
            deduped.append(edit)
        repair["edits"] = deduped
    patchable_repairs = [repair for repair in repairs if repair.get("edits")]
    review_only_repairs = [repair for repair in repairs if repair.get("reviewEdits")]
    suggestion_only_repairs = [repair for repair in repairs if not repair.get("edits") and not repair.get("reviewEdits")]
    file_hashes = {}
    for repair in patchable_repairs:
        for edit in repair.get("edits", []):
            target_path = edit.get("file", "")
            if not target_path:
                continue
            target = Path(target_path)
            if target.exists():
                file_hashes[str(target.resolve())] = _file_sha256(target)
    status = "actionable"
    if check_payload["status"] == "compiler-error":
        # A compiler error normally means no machine-applicable plan — except
        # when the blocking rows are themselves the thing we can fix in place
        # (the syntax cutover blocks parsing yet has deterministic local edits).
        # Report "mixed" so the plan stays usable, steering the caller through
        # `sem patch --dry-run` (re-check) before `--apply`.
        status = "mixed" if patchable_repairs else "blocked"
    elif not repairs:
        status = "no-repairs"
    elif not patchable_repairs:
        status = "suggestions-only"
    elif review_only_repairs or suggestion_only_repairs:
        status = "mixed"
    plan_usable = status in {"actionable", "mixed"}
    focus_anchors = _diagnostic_focus_anchors(repair_diagnostics)
    return {
        "schemaVersion": "sem.fixPlan.v1",
        "tool": {"name": "sem", "version": VERSION},
        "inputPath": str(path.resolve()),
        "ok": status == "actionable",
        "status": status,
        "planUsable": plan_usable,
        "scope": _payload_scope(
            path,
            diagnosticScope=check_scope.get("diagnosticsScope", "file"),
            repairScope=_scope_label_from_sources(bundle["files"]),
        ),
        "diagnosticCount": len(check_payload["diagnostics"]),
        "repairCount": len(repairs),
        "patchableRepairCount": len(patchable_repairs),
        "focusAnchors": focus_anchors,
        "repairSummary": {
            "patchable": len(patchable_repairs),
            "reviewOnlyEdits": len(review_only_repairs),
            "suggestionsOnly": len(suggestion_only_repairs),
            "topDiagnosticCodes": _top_count_entries([repair.get("diagnostic", "") for repair in repairs]),
        },
        "repairs": repairs,
        "preconditions": {
            "fileHashes": file_hashes,
        },
        "checkSummary": check_payload["summary"],
        "checkStatus": check_payload["status"],
        "blockingReason": (
            "compiler diagnostics are present and the current repair planner only trusts source-level repair plans after successful compiler validation"
            if status == "blocked" else
            f"{len(patchable_repairs)} machine-applicable repairs are available, but {len(review_only_repairs) + len(suggestion_only_repairs)} repairs still require review; preview the plan before applying any edit"
            if status == "mixed" else
            "only review-only edits or human-review suggestions were derived; no machine-applicable patch is available for the current diagnostics"
            if status == "suggestions-only" else
            "no actionable machine repair was derived from the current diagnostics"
            if status == "no-repairs" else ""
        ),
        "nextCommands": _fix_plan_next_commands(
            path,
            patchable=bool(patchable_repairs),
            plan_usable=plan_usable,
            status=status,
            focus_anchors=focus_anchors,
        ),
    }


def _load_plan(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _patch_error_payload(mode: str, error: str, *, details=None, next_commands=None, input_plan_path: str = "") -> dict:
    return {
        "schemaVersion": "sem.patch.v1",
        "tool": {"name": "sem", "version": VERSION},
        "ok": False,
        "mode": mode,
        "inputPlanPath": input_plan_path,
        "applied": False,
        "rolledBack": False,
        "error": error,
        "details": list(details or []),
        "staleFiles": [],
        "filesChanged": [],
        "editCount": 0,
        "verification": {"formatOk": None, "checkOk": None, "checkSummary": {}},
        "nextCommands": list(next_commands or []),
    }


def _validate_patch_plan(plan: dict) -> list[str]:
    errors = []
    if not isinstance(plan, dict):
        return ["patch plan must be a JSON object"]
    if plan.get("schemaVersion") != "sem.fixPlan.v1":
        errors.append("patch plan schemaVersion must be sem.fixPlan.v1")
    truncation = ((plan.get("view") or {}).get("truncation") or {})
    if truncation.get("repairs"):
        errors.append("patch plan is truncated; regenerate it with `sem fix --plan --json --full <PATH>` before patch execution")
    if plan.get("planUsable") is False or plan.get("status") in {"blocked", "suggestions-only", "no-repairs"}:
        errors.append("patch plan is not actionable; regenerate after resolving blocking diagnostics or review-only suggestions")
    repairs = plan.get("repairs")
    if not isinstance(repairs, list):
        errors.append("patch plan repairs must be a list")
        return errors
    allowed_ops = {"insertAfterLine", "replaceLine"}
    for repair_index, repair in enumerate(repairs):
        edits = repair.get("edits", [])
        if not isinstance(edits, list):
            errors.append(f"repair[{repair_index}] edits must be a list")
            continue
        for edit_index, edit in enumerate(edits):
            op = edit.get("op", "")
            if op not in allowed_ops:
                errors.append(f"repair[{repair_index}].edits[{edit_index}] unsupported op `{op}`")
                continue
            if not edit.get("file"):
                errors.append(f"repair[{repair_index}].edits[{edit_index}] missing file")
            if op == "insertAfterLine" and "afterLine" not in edit:
                errors.append(f"repair[{repair_index}].edits[{edit_index}] missing afterLine")
            if op == "replaceLine" and "line" not in edit:
                errors.append(f"repair[{repair_index}].edits[{edit_index}] missing line")
    return errors


def _apply_insert_after_line(lines: list[str], after_line: int, text: str) -> list[str]:
    new_lines = list(lines)
    insertion_index = int(after_line)
    new_lines[insertion_index:insertion_index] = [text + "\n"]
    return new_lines


def _apply_replace_line(lines: list[str], line_number: int, text: str) -> list[str]:
    new_lines = list(lines)
    index = int(line_number) - 1
    new_lines[index] = text + "\n"
    return new_lines


def _validate_edit_coordinate(lines: list[str], edit: dict) -> str:
    op = edit.get("op", "")
    if op == "insertAfterLine":
        after_line = int(edit.get("afterLine", 0))
        if after_line < 0 or after_line > len(lines):
            return f"insertAfterLine afterLine {after_line} is outside 0..{len(lines)}"
        return ""
    if op == "replaceLine":
        line_number = int(edit.get("line", 0))
        if line_number < 1 or line_number > len(lines):
            return f"replaceLine line {line_number} is outside 1..{len(lines)}"
    return ""


def _execute_patch_plan(plan: dict, mode: str) -> dict:
    validation_errors = _validate_patch_plan(plan)
    if validation_errors:
        return _patch_error_payload(
            mode,
            "invalid patch plan",
            details=validation_errors,
            next_commands=[
                _next_command_entry(
                    "fix",
                    "regenerate the plan from the current SemanticScript diagnostics",
                    argv=["sem", "fix", "--plan", "--json", str(Path(plan.get("inputPath", ".")).resolve())],
                )
            ],
            input_plan_path=str(plan.get("_inputPlanPath", "")),
        )
    file_hashes = dict(plan.get("preconditions", {}).get("fileHashes", {}))
    stale = []
    for file_name, expected_hash in sorted(file_hashes.items()):
        current_hash, read_error = _file_sha256_with_error(Path(file_name))
        if expected_hash and expected_hash != current_hash:
            entry = {
                "file": file_name,
                "expectedHash": expected_hash,
                "actualHash": current_hash,
            }
            if read_error:
                entry["detail"] = read_error
            stale.append(entry)
    if stale:
        return {
            "schemaVersion": "sem.patch.v1",
            "tool": {"name": "sem", "version": VERSION},
            "ok": False,
            "mode": mode,
            "applied": False,
            "rolledBack": False,
            "error": "patch precondition failed; one or more target files changed since the plan was generated",
            "details": [],
            "staleFiles": stale,
            "filesChanged": [],
            "editCount": 0,
            "verification": {"formatOk": None, "checkOk": None, "checkSummary": {}},
            "nextCommands": _patch_next_commands(plan, mode, False),
        }
    changed_files = {}
    original_texts = {}
    for repair in plan.get("repairs", []):
        for edit in repair.get("edits", []):
            target = Path(edit["file"]).resolve()
            current = changed_files.get(target)
            if current is None:
                try:
                    original_text = target.read_text(encoding="utf-8")
                except OSError as exc:
                    return _patch_error_payload(
                        mode,
                        "unable to read patch target",
                        details=[f"{target}: {exc}"],
                        next_commands=_patch_next_commands(plan, mode, False),
                    )
                original_texts[target] = original_text
                current = original_text.splitlines(keepends=True)
            coordinate_error = _validate_edit_coordinate(current, edit)
            if coordinate_error:
                return _patch_error_payload(
                    mode,
                    "patch precondition failed; repair coordinates no longer match the current file shape",
                    details=[f"{target}: {coordinate_error}"],
                    next_commands=_patch_next_commands(plan, mode, False),
                )
            if edit.get("op") == "insertAfterLine":
                current = _apply_insert_after_line(current, int(edit.get("afterLine", 0)), edit.get("text", ""))
            elif edit.get("op") == "replaceLine":
                current = _apply_replace_line(current, int(edit.get("line", 1)), edit.get("text", ""))
            changed_files[target] = current

    details = []
    if mode == "apply":
        try:
            for target, lines in changed_files.items():
                target.write_text("".join(lines), encoding="utf-8", newline="\n")
        except OSError as exc:
            for restore_target, original_text in original_texts.items():
                try:
                    restore_target.write_text(original_text, encoding="utf-8", newline="\n")
                except OSError:
                    pass
            return _patch_error_payload(
                mode,
                "unable to write patched files",
                details=[str(exc)],
                next_commands=_patch_next_commands(plan, mode, False),
                input_plan_path=str(plan.get("_inputPlanPath", "")),
            )

    verification = {"formatOk": None, "checkOk": None, "checkSummary": {}, "rolledBack": False}
    if mode == "apply":
        if changed_files:
            semfmt_path = ROOT / "formatter" / "semfmt.py"
            format_proc = subprocess.run(
                [sys.executable, str(semfmt_path), *[str(path) for path in changed_files]],
                check=False,
                capture_output=True,
                text=True,
            )
            verification["formatOk"] = format_proc.returncode == 0
            if not verification["formatOk"]:
                if format_proc.stderr.strip():
                    details.append(format_proc.stderr[:2000])
                if format_proc.stdout.strip():
                    details.append(format_proc.stdout[:2000])
        else:
            verification["formatOk"] = True
        if verification["formatOk"]:
            input_path = Path(plan.get("inputPath", Path.cwd()))
            check_payload = _build_check_payload(input_path, [])
            verification["checkOk"] = bool(check_payload.get("ok", False))
            verification["checkSummary"] = check_payload.get("summary", {})
        else:
            verification["checkOk"] = False
        if changed_files and (not verification["formatOk"] or not verification["checkOk"]):
            for target, original_text in original_texts.items():
                try:
                    target.write_text(original_text, encoding="utf-8", newline="\n")
                except OSError as exc:
                    details.append(f"rollback failed for {target}: {exc}")
            verification["rolledBack"] = True
    command_ok = mode != "apply" or (
        bool(verification.get("formatOk", False))
        and bool(verification.get("checkOk", False))
        and not verification.get("rolledBack", False)
    )
    return {
        "schemaVersion": "sem.patch.v1",
        "tool": {"name": "sem", "version": VERSION},
        "ok": command_ok,
        "mode": mode,
        "inputPlanPath": str(plan.get("_inputPlanPath", "")),
        "scope": _payload_scope(
            Path(plan.get("inputPath", Path.cwd())),
            repairScope="file",
        ),
        "applied": mode == "apply" and not verification.get("rolledBack", False),
        "rolledBack": verification.get("rolledBack", False),
        "details": details,
        "filesChanged": [str(path) for path in sorted(changed_files, key=lambda item: str(item).lower())],
        "editCount": sum(len(repair.get("edits", [])) for repair in plan.get("repairs", [])),
        "verification": verification,
        "nextCommands": _patch_next_commands(plan, mode, command_ok),
    }


def _parse_trace_events(stderr_text: str) -> tuple[list[dict], str]:
    events = []
    non_trace_lines = []
    for line in stderr_text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("{"):
            non_trace_lines.append(line)
            continue
        try:
            event = json.loads(stripped)
        except json.JSONDecodeError:
            non_trace_lines.append(line)
            continue
        if event.get("schemaVersion") == "sem.traceEvent.v0":
            events.append(event)
        else:
            non_trace_lines.append(line)
    return events, "\n".join(non_trace_lines)


def _counter_dict(items):
    counts = {}
    for item in items:
        key = item or ""
        counts[key] = counts.get(key, 0) + 1
    return counts


def _profile_from_trace(source: Path, proc: subprocess.CompletedProcess,
                        events: list[dict], duration_ns: int,
                        inspect_payload: dict | None = None) -> dict:
    operations = _counter_dict(
        event.get("operation")
        for event in events
        if event.get("event") == "op.enter")
    calls = _counter_dict(
        f"{event.get('operation')}::{event.get('name')}->{event.get('target')}"
        for event in events
        if event.get("event") == "call.start")
    branches = _counter_dict(
        f"{event.get('operation')}::{event.get('name')}->{event.get('target')}"
        for event in events
        if event.get("event") == "branch.decision")
    returns = _counter_dict(
        f"{event.get('operation')}::{event.get('name')}:{event.get('valueStatus')}"
        for event in events
        if event.get("event") == "return.value")
    source_info = {}
    build_info = {}
    trace_map_info = {}
    if inspect_payload:
        source_info = inspect_payload.get("source", {})
        build_info = inspect_payload.get("build", {})
        trace_map_info = {
            "schemaVersion": inspect_payload.get("traceMap", {}).get("schemaVersion", ""),
            "siteCount": len(inspect_payload.get("traceMap", {}).get("sites", [])),
        }
    return {
        "schemaVersion": "sem.profile.v0",
        "tool": {"name": "sem", "version": VERSION},
        "source": {
            "path": str(source.resolve()),
            "fingerprint": source_info.get("fingerprint", ""),
        },
        "build": {
            "fingerprint": build_info.get("fingerprint", ""),
            "profile": build_info.get("profile", ""),
            "runtimeChecks": build_info.get("runtimeChecks", ""),
            "optLevel": build_info.get("optLevel", None),
        },
        "traceMap": trace_map_info,
        "run": {
            "returnCode": proc.returncode,
            "durationNs": duration_ns,
            "wallTimeNs": duration_ns,
            "startupTimeNs": 0,
            "startupTimeSource": "notSeparatedForJitDriver",
            "stdoutBytes": len(proc.stdout.encode("utf-8")),
            "stderrBytes": len(proc.stderr.encode("utf-8")),
            "traceEventCount": len(events),
        },
        "hot": {
            "operations": operations,
            "calls": calls,
            "branches": branches,
            "returns": returns,
            "runtimeExternalCalls": _counter_dict(
                event.get("target")
                for event in events
                if event.get("event") == "call.start"
                and str(event.get("target", "")).startswith((
                    "http.", "sqlite.", "json.", "gui.", "bcrypt.", "c."))),
        },
        "http": {
            "requestCount": 0,
            "note": "HTTP request tracing is runtime-adapter work; no request loop was observed by this run.",
        },
        "measurement": {
            "traceInstrumentation": "enabled",
            "profileSource": "aggregatedTraceEvents",
            "overheadWarning": "Trace instrumentation changes runtime cost; compare profiles against profiles, not raw non-traced runs.",
        },
    }


def _inspect_payload(source: Path, compiler_args: list[str]) -> dict | None:
    proc = _capture_compiler(source, ["--inspect-ir", *compiler_args])
    if proc.returncode != 0:
        return None
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None


def _parse_crash_last_site(descriptor: str, result: dict) -> None:
    """Parse an SSRUN002 `Last site` descriptor emitted by the codegen, e.g.
    `operation main call lenCall -> c.strlen line 13` or `operation main line
    8`, into the same operation/call/line fields SSRUN001 reports."""
    match = re.match(
        r"operation (?P<op>\S+)(?: call (?P<call>\S+) -> (?P<target>\S+))?"
        r" line (?P<line>\d+)",
        descriptor.strip())
    if not match:
        return
    result["operation"] = match.group("op")
    if match.group("call"):
        result["call"] = f"{match.group('call')} -> {match.group('target')}"
    result["line"] = int(match.group("line"))


def _parse_crash_stack_frame(line: str) -> dict | None:
    """Parse one SSRUN002 call-stack frame, e.g.
    `#1 operation middleStep (call middleCall line 34)` or `#0 operation main
    (entry)`, into a structured frame."""
    match = re.match(
        r"#(?P<index>\d+) operation (?P<op>\S+)"
        r"(?: \(call (?P<call>\S+) line (?P<line>\d+)\))?",
        line.strip())
    if not match:
        return None
    frame = {"index": int(match.group("index")), "operation": match.group("op")}
    if match.group("call"):
        frame["call"] = match.group("call")
        frame["line"] = int(match.group("line"))
    return frame


def _parse_runtime_panic(stderr_text: str) -> dict:
    lines = stderr_text.splitlines()
    panic_index = next(
        (idx for idx, line in enumerate(lines)
         if ("SSRUN001" in line and "runtime panic" in line)
         or ("SSRUN002" in line and "native fault" in line)),
        None)
    if panic_index is None:
        return {}
    block = lines[panic_index:]
    code = "SSRUN002" if "SSRUN002" in lines[panic_index] else "SSRUN001"
    result = {"code": code, "raw": "\n".join(block)}
    current_section = ""
    for line in block:
        stripped = line.strip()
        if not stripped:
            continue
        if (stripped.endswith(":")
                and not stripped.startswith(("file:", "line:", "operation:", "call:", "reason:", "status:"))):
            current_section = stripped[:-1].lower()
            continue
        if stripped.startswith("reason:"):
            result["reason"] = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("status:"):
            result["status"] = stripped.split(":", 1)[1].strip()
        elif stripped.startswith("Signal:"):
            result["fault"] = stripped.split(":", 1)[1].strip()
            sig_match = re.match(r"(\d+)\s*\((\S+)\)", result["fault"])
            if sig_match:
                result["signalNumber"] = int(sig_match.group(1))
                result["signalName"] = sig_match.group(2)
        elif stripped.startswith("Exception:"):
            result["fault"] = stripped.split(":", 1)[1].strip()
            exc_match = re.match(r"(\S+)\s*\(code (\d+)\)", result["fault"])
            if exc_match:
                result["signalName"] = exc_match.group(1)
                result["exceptionCode"] = int(exc_match.group(2))
        elif current_section.startswith("call stack"):
            frame = _parse_crash_stack_frame(stripped)
            if frame is not None:
                result.setdefault("callStack", []).append(frame)
        elif current_section == "last site":
            _parse_crash_last_site(stripped, result)
        elif current_section == "location" and stripped.startswith("file:"):
            result["file"] = stripped.split(":", 1)[1].strip()
        elif current_section == "location" and stripped.startswith("line:"):
            raw_line = stripped.split(":", 1)[1].strip()
            try:
                result["line"] = int(raw_line)
            except ValueError:
                result["line"] = raw_line
        elif current_section == "location" and stripped.startswith("operation:"):
            result["operation"] = stripped.split(":", 1)[1].strip()
        elif current_section == "location" and stripped.startswith("call:"):
            result["call"] = stripped.split(":", 1)[1].strip()
        elif current_section == "source" and "|" in stripped:
            result["sourceRow"] = stripped
        elif current_section == "direction":
            result.setdefault("direction", stripped)
    return result


def _crash_fix_candidates(panic: dict, return_code: int) -> list[str]:
    code = panic.get("code")
    if code == "SSRUN001":
        return [
            "Patch the SemanticScript source row named by panic.sourceRow or the last trace event.",
            "Use sem inspect-ir to inspect the operation, call, and LLVM block mapping.",
            "If this is prod/traps mode, rerun with --build-profile dev --runtime-checks panic for source context.",
        ]
    if code == "SSRUN002":
        op = panic.get("operation") or "the operation named in panic.operation"
        call = panic.get("call")
        site = f"{op} / call {call}" if call else op
        return [
            f"The fault landed in {site}: check the pointer, length, index, or recursion bound used on or just after that call.",
            f"Open the row at line {panic.get('line', '?')} ({panic.get('signalName', 'fatal signal')}) and verify any c.* / pointer argument is non-null and in range.",
            "If panic has no operation (prod/traps mode hides it), rebuild with --build-profile dev and rerun sem run --explain-crash.",
        ]
    if return_code != 0:
        return [
            "No SSRUN002 context was captured. On Windows an explicit abort()/__fastfail (exit 0xC0000409) bypasses the handler — check for a deliberate process.abort path.",
            "Rebuild with --build-profile dev --runtime-checks panic and rerun; inspect the last trace event for the final operation entered.",
        ]
    return [
        "No crash detected: the program exited cleanly. Re-check the input that was expected to fail.",
    ]


def _explain_crash(source: Path, compiler_args: list[str]) -> int:
    inspect = _inspect_payload(source, compiler_args)
    artifact_dir = _artifact_run_dir(source, "crash")
    exe_path = artifact_dir / ("sem-crash.exe" if os.name == "nt" else "sem-crash")
    trace_map_path = artifact_dir / "trace-map.json"
    trace_events_path = artifact_dir / "trace-events.jsonl"
    crash_report_path = artifact_dir / "crash.json"
    artifact_index_path = artifact_dir / "artifact-index.json"
    compile_args = [
        "--trace",
        "--emit-exe", str(exe_path),
        "--emit-trace-map", str(trace_map_path),
        "--build-dir", str(artifact_dir / "build"),
        "--quiet",
        *compiler_args,
    ]
    compile_proc = _capture_compiler(source, compile_args, timeout=300)
    common_artifacts = {
        "artifactDir": str(artifact_dir),
        "artifactIndexPath": str(artifact_index_path),
        "crashReportPath": str(crash_report_path),
        "traceMapPath": str(trace_map_path) if trace_map_path.exists() else "",
        "traceEventsPath": str(trace_events_path),
        "executablePath": str(exe_path),
    }
    if compile_proc.returncode != 0 or not exe_path.exists():
        payload = {
            "schemaVersion": "sem.crash.v0",
            "tool": {"name": "sem", "version": VERSION},
            "phase": "compile",
            "source": {"path": str(source.resolve())},
            "compile": {
                "returnCode": compile_proc.returncode,
                "stdout": compile_proc.stdout,
                "stderr": compile_proc.stderr,
            },
            "suspectedCategory": "compileFailure",
            "fixCandidates": [
                "Inspect compiler diagnostics before runtime crash analysis.",
                "Run sem inspect-ir to verify source-to-LLVM lowering context.",
            ],
            "artifacts": common_artifacts,
        }
        _write_json_artifact(crash_report_path, payload)
        _write_json_artifact(artifact_index_path, {
            "schemaVersion": "sem.artifactIndex.v0",
            "tool": {"name": "sem", "version": VERSION},
            "kind": "crash",
            "phase": "compile",
            "source": payload["source"],
            "artifacts": common_artifacts,
        })
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 1
    start = time.perf_counter_ns()
    run_proc = subprocess.run([str(exe_path)], capture_output=True, text=True)
    duration_ns = time.perf_counter_ns() - start
    events, non_trace_stderr = _parse_trace_events(run_proc.stderr)
    trace_events_path.write_text(
        "".join(json.dumps(event, sort_keys=True) + "\n" for event in events),
        encoding="utf-8", newline="\n")
    panic = _parse_runtime_panic(non_trace_stderr)
    compiler_args_text = " ".join(compiler_args)
    build_profile = "prod" if "--build-profile prod" in compiler_args_text else "dev"
    runtime_checks = "panic"
    if "--runtime-checks off" in compiler_args_text:
        runtime_checks = "off"
    elif "--runtime-checks traps" in compiler_args_text or build_profile == "prod":
        runtime_checks = "traps"
    last_event = events[-1] if events else {}
    context_operation = (
        panic.get("operation")
        or last_event.get("operation")
        or ""
    )
    route_contexts = [
        {
            "server": route.get("server", ""),
            "method": route.get("method", ""),
            "path": route.get("path", ""),
            "handler": route.get("handler", ""),
            "siteId": route.get("siteId", ""),
        }
        for route in (inspect or {}).get("routes", [])
        if route.get("handler") == context_operation
    ]
    payload = {
        "schemaVersion": "sem.crash.v0",
        "tool": {"name": "sem", "version": VERSION},
        "phase": "run",
        "source": {
            "path": str(source.resolve()),
            "fingerprint": (inspect or {}).get("source", {}).get("fingerprint", ""),
        },
        "build": {
            "fingerprint": (inspect or {}).get("build", {}).get("fingerprint", ""),
            "profile": build_profile,
            "runtimeChecks": runtime_checks,
        },
        "run": {
            "returnCode": run_proc.returncode,
            "durationNs": duration_ns,
            "stdout": run_proc.stdout,
            "stderrNonTrace": non_trace_stderr,
        },
        "panic": panic,
        "semanticContext": {
            "operation": context_operation,
            "call": panic.get("call", ""),
            "callStack": panic.get("callStack", []),
            "routes": route_contexts,
            "lastEvent": last_event,
        },
        "lastTraceEvents": events[-20:],
        "suspectedCategory": (
            "runtimePanic" if panic.get("code") == "SSRUN001"
            else "nativeFault" if panic.get("code") == "SSRUN002"
            else "nativeTrap" if run_proc.returncode != 0
            else "noCrash"),
        "fixCandidates": _crash_fix_candidates(panic, run_proc.returncode),
        "artifacts": common_artifacts,
    }
    _write_json_artifact(crash_report_path, payload)
    _write_json_artifact(artifact_index_path, {
        "schemaVersion": "sem.artifactIndex.v0",
        "tool": {"name": "sem", "version": VERSION},
        "kind": "crash",
        "phase": "run",
        "source": payload["source"],
        "build": payload["build"],
        "artifacts": common_artifacts,
        "suspectedCategory": payload["suspectedCategory"],
    })
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if run_proc.returncode != 0 else 1


def command_build(args: argparse.Namespace) -> int:
    requested = Path(args.path)
    # --standalone: compile a single source file straight to a native exe via the
    # compiler's single-file path, skipping build.sem discovery. This closes the
    # "no single-file native build / scratch run" gap — agents proving a native
    # snippet no longer have to scaffold a throwaway project.
    if getattr(args, "standalone", False):
        if not requested.is_file():
            print(f"sem build --standalone: `{args.path}` is not a file. Pass a single "
                  f".sem/.sscript source to build it directly.", file=sys.stderr)
            return 2
        standalone_args = _strip_separator(list(args.compiler_args))
        trailing_strict, standalone_args = _extract_flag(standalone_args, "--strict")
        if (bool(getattr(args, "strict", False)) or trailing_strict) and "--strict" not in standalone_args:
            standalone_args = list(standalone_args) + ["--strict"]
        if not _has_compiler_action(standalone_args):
            standalone_args = ["--emit-exe", *standalone_args]
        return _run_compiler(requested, standalone_args)
    build_tape = _find_build_tape(requested)
    if build_tape is None:
        print(
            f"sem build: no build.sem found from {args.path}. `sem build` builds "
            f"a project (a directory with a build.sem tape), not a lone source "
            f"file. Pass the project directory or add a build.sem; to compile this "
            f"single file to a native exe use `sem build --standalone {args.path}`, "
            f"or `sem check {args.path}` / `sem run {args.path}`.",
            file=sys.stderr,
        )
        return 2

    # A bare-file arg does NOT build that file: `sem build` resolves the nearest
    # ancestor build.sem and builds that whole project. Silently ignoring the
    # file arg was a documented surprise — make the redirect visible.
    if (requested.is_file()
            and requested.name.lower() not in {"build.sem", "build.sscript"}):
        print(
            f"sem build: building project tape {build_tape}; the `{requested.name}` "
            f"argument selects that project, it is not built as a standalone file.",
            file=sys.stderr,
        )

    compiler_args = _strip_separator(list(args.compiler_args))
    trailing_strict, compiler_args = _extract_flag(compiler_args, "--strict")
    if (bool(getattr(args, "strict", False)) or trailing_strict) and "--strict" not in compiler_args:
        # CI ratchet: gate the native build on the strict executable wall too.
        compiler_args = list(compiler_args) + ["--strict"]
    if not _has_compiler_action(compiler_args):
        compiler_args = ["--emit-exe", *compiler_args]
    if getattr(args, "platform", None):
        compiler_args = [f"--platform-filter={args.platform}", *compiler_args]
    return _run_compiler(build_tape, compiler_args)


def command_run(args: argparse.Namespace) -> int:
    build_tape = _find_build_tape(Path(args.path))
    source = build_tape if build_tape is not None else Path(args.path)
    compiler_args = _strip_separator(list(args.compiler_args))
    trace, compiler_args = _extract_flag(compiler_args, "--trace")
    profile, compiler_args = _extract_flag(compiler_args, "--profile")
    json_output, compiler_args = _extract_flag(compiler_args, "--json")
    explain_crash, compiler_args = _extract_flag(compiler_args, "--explain-crash")
    trace = trace or bool(getattr(args, "trace", False))
    profile = profile or bool(getattr(args, "profile", False))
    json_output = json_output or bool(getattr(args, "json", False))
    explain_crash = explain_crash or bool(getattr(args, "explain_crash", False))

    if explain_crash:
        return _explain_crash(source, compiler_args)

    target_facts = _scan_run_target_facts(source)
    target_kind = target_facts.get("targetRuntime") or target_facts.get("target")
    if target_kind in {"webServer", "windowsGui"} and not profile:
        reason = (
            "webServer targets are long-running native executables; `sem run` "
            "does not start them through the in-process JIT. Build the executable "
            "or use `sem dev` for the watch/restart loop."
            if target_kind == "webServer"
            else "windowsGui targets are non-console native executables; build them with `sem build`."
        )
        payload = _run_not_executed_payload(
            source,
            target_facts,
            "long-running-target" if target_kind == "webServer" else "non-console-target",
            reason,
        )
        if json_output:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(f"sem run: {reason}", file=sys.stderr)
            base_url = payload.get("target", {}).get("baseUrl")
            if base_url:
                print(f"target URL: {base_url}", file=sys.stderr)
            print("next: sem build PATH -- --emit-exe", file=sys.stderr)
        return 2

    if profile:
        artifact_dir = _artifact_run_dir(source, "profile")
        profile_path = artifact_dir / "profile.json"
        trace_events_path = artifact_dir / "trace-events.jsonl"
        inspect_ir_path = artifact_dir / "inspect-ir.json"
        artifact_index_path = artifact_dir / "artifact-index.json"
        inspect = _inspect_payload(source, compiler_args)
        run_args = ["--run", "--trace", *compiler_args]
        start = time.perf_counter_ns()
        proc = _capture_compiler(source, run_args)
        duration_ns = time.perf_counter_ns() - start
        events, non_trace_stderr = _parse_trace_events(proc.stderr)
        if proc.returncode != 0 and not events:
            payload = {
                "schemaVersion": "sem.profileFailure.v0",
                "tool": {"name": "sem", "version": VERSION},
                "phase": "compile",
                "source": {
                    "path": str(source.resolve()),
                    "fingerprint": (inspect or {}).get("source", {}).get("fingerprint", ""),
                },
                "build": {
                    "fingerprint": (inspect or {}).get("build", {}).get("fingerprint", ""),
                    "profile": (inspect or {}).get("build", {}).get("profile", ""),
                    "runtimeChecks": (inspect or {}).get("build", {}).get("runtimeChecks", ""),
                },
                "compile": {
                    "returnCode": proc.returncode,
                    "durationNs": duration_ns,
                    "stdout": proc.stdout,
                    "stderr": non_trace_stderr,
                },
                "suspectedCategory": "compileFailure",
                "fixCandidates": [
                    "Inspect compiler diagnostics before profile analysis.",
                    "Run sem inspect-ir to verify source-to-LLVM lowering context.",
                    "Do not treat this payload as a performance profile.",
                ],
                "artifacts": {
                    "artifactDir": str(artifact_dir),
                    "artifactIndexPath": str(artifact_index_path),
                    "profilePath": str(profile_path),
                    "traceEventsPath": str(trace_events_path),
                    "inspectIrPath": str(inspect_ir_path) if inspect is not None else "",
                },
            }
            trace_events_path.write_text("", encoding="utf-8", newline="\n")
            if inspect is not None:
                _write_json_artifact(inspect_ir_path, inspect)
            _write_json_artifact(profile_path, payload)
            _write_json_artifact(artifact_index_path, {
                "schemaVersion": "sem.artifactIndex.v0",
                "tool": {"name": "sem", "version": VERSION},
                "kind": "profileFailure",
                "phase": "compile",
                "source": payload["source"],
                "build": payload["build"],
                "artifacts": payload["artifacts"],
                "suspectedCategory": payload["suspectedCategory"],
            })
            print(json.dumps(payload, indent=2, sort_keys=True))
            return proc.returncode
        payload = _profile_from_trace(source, proc, events, duration_ns, inspect)
        payload["artifacts"] = {
            "artifactDir": str(artifact_dir),
            "artifactIndexPath": str(artifact_index_path),
            "profilePath": str(profile_path),
            "traceEventsPath": str(trace_events_path),
            "inspectIrPath": str(inspect_ir_path) if inspect is not None else "",
        }
        payload["optimizationLoop"] = {
            "schemaVersion": "sem.optimizationLoop.v0",
            "steps": [
                "inspect-ir",
                "profile-baseline",
                "patch-source",
                "check-and-test",
                "profile-candidate",
                "compare-profile-delta",
            ],
            "comparisonKey": payload.get("build", {}).get("fingerprint", ""),
            "deltaFields": [
                "run.durationNs",
                "run.traceEventCount",
                "hot.operations",
                "hot.calls",
                "hot.branches",
                "hot.runtimeExternalCalls",
            ],
        }
        trace_events_path.write_text(
            "".join(json.dumps(event, sort_keys=True) + "\n" for event in events),
            encoding="utf-8", newline="\n")
        if inspect is not None:
            _write_json_artifact(inspect_ir_path, inspect)
        _write_json_artifact(profile_path, payload)
        index_payload = {
            "schemaVersion": "sem.artifactIndex.v0",
            "tool": {"name": "sem", "version": VERSION},
            "kind": "profile",
            "source": payload.get("source", {}),
            "build": payload.get("build", {}),
            "artifacts": payload["artifacts"],
            "comparisonKey": payload["optimizationLoop"]["comparisonKey"],
        }
        _write_json_artifact(artifact_index_path, index_payload)
        # Profile mode is an agent surface. Keep stdout as the JSON report and
        # embed application stdout/stderr sizes instead of interleaving streams.
        print(json.dumps(payload, indent=2, sort_keys=True))
        if non_trace_stderr:
            print(non_trace_stderr, file=sys.stderr)
        return proc.returncode

    run_args = ["--run"]
    if trace:
        run_args.append("--trace")
    run_args.extend(compiler_args)
    return _run_compiler(source, run_args)


EVAL_PAYLOAD_VERSION = "sem.eval.v1"
EVAL_WRAPPER_MODULE = "sem.eval.scratch"
EVAL_DEFAULT_MAX_OUTPUT_BYTES = 64 * 1024
EVAL_DEFAULT_TIMEOUT_SECONDS = 30
_RUN_METRICS_SENTINEL = "__SEM_RUN_METRICS__ "

# Snippet verbs that declare module-level context rather than executable
# operation-body steps. The wrapper hoists these above `operation main` so a
# snippet can bring its own imports, error categories, records, and capabilities
# while the rest of the rows stay inside the generated main body.
_SNIPPET_MODULE_DECL_VERBS = frozenset({
    "import", "error", "errorCase", "record", "field", "enum", "enumCase",
    "capability", "type", "alias", "sharedState",
})


def _snippet_looks_like_full_program(text: str) -> bool:
    """A snippet that declares its own ``project`` or ``operation`` header is a
    complete program; pass it through verbatim instead of wrapping it."""
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        verb = stripped.split(None, 1)[0]
        if verb in {"project", "operation", "entry"}:
            return True
    return False


def _program_has_runtime_entrypoint(text: str) -> bool:
    """True if a full-program source has something the compiler turns into a
    real entrypoint: an explicit ``entry`` row, or a ``webServer`` with at least
    one ``route`` (which emits a native HTTP entrypoint). Without either, the
    compiler builds in library mode (a stub ``main`` that returns 0) and nothing
    the author wrote executes.

    This mirrors the compiler's gate, which keys on ``entry`` plus any declared
    web server having routes (`active_servers`) — independent of the `target`
    row — so a routed server under any target is correctly seen as runnable."""
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        verb = stripped.split(None, 1)[0]
        if verb in {"entry", "route"}:
            return True
    return False


def _split_snippet_rows(text: str) -> tuple[list[str], list[str], bool]:
    """Partition snippet lines into hoisted module declarations and operation
    body rows. Returns ``(header_lines, body_lines, has_top_level_return)``.

    Comments and blank lines are attached to the next row's zone so in-source
    rationale stays adjacent to what it documents.
    """
    header: list[str] = []
    body: list[str] = []
    has_return = False
    pending: list[str] = []
    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            pending.append(line)
            continue
        tokens = stripped.split()
        verb = tokens[0]
        second = tokens[1] if len(tokens) > 1 else ""
        is_header = verb in _SNIPPET_MODULE_DECL_VERBS or (
            verb == "storage" and second == "module")
        target = header if is_header else body
        target.extend(pending)
        pending = []
        target.append(line)
        if not is_header and verb == "return":
            has_return = True
    body.extend(pending)
    return header, body, has_return


def _wrap_snippet(text: str) -> tuple[str, int]:
    """Wrap snippet body rows in the minimal console-program shape.

    Returns ``(wrapped_source, body_line_offset)`` where ``body_line_offset`` is
    the number of generated header lines that precede the first injected body
    row, so diagnostics can be remapped to snippet-relative line numbers.
    """
    header_decls, body_rows, has_return = _split_snippet_rows(text)
    uses_console = "console." in text
    lines = [
        "project SemScriptEval",
        "target console",
        "runtime native 1",
        f"module {EVAL_WRAPPER_MODULE}",
        "entry console main",
        "",
    ]
    if header_decls:
        lines += header_decls + [""]
    lines += [
        "operation main",
        "output operation main ExitCode",
    ]
    if uses_console:
        # The authority row satisfies the effect contract; no capability/error
        # type is generated because the wrapper does not itself handle write
        # failures — that is the snippet's contract to make explicit.
        lines += [
            "effect main write console.stdout",
            "authority main write console.stdout",
        ]
    lines += [
        "memory main heap no",
        "async main no",
        ("purpose operation main \"Evaluate a SemanticScript snippet through "
         "the JIT and return a process exit code.\""),
    ]
    body_line_offset = len(lines)
    lines += body_rows
    if not has_return:
        lines += [
            "storage local immutable replSuccessExitCode ExitCode 0",
            "return value replSuccessExitCode",
        ]
    return "\n".join(lines) + "\n", body_line_offset


def _split_stream(text: str) -> tuple[str, list[str]]:
    """Return ``(text, lines)`` for a captured stream. The trailing empty line
    produced by a final newline is dropped so ``stdoutLines`` reflects emitted
    lines rather than the terminator."""
    if not text:
        return "", []
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return text, lines


def _cap_output(text: str, max_bytes: int) -> tuple[str, int, bool]:
    """Cap a captured stream to ``max_bytes`` UTF-8 bytes. Returns
    ``(text, byte_count, truncated)`` with truncation on a character boundary."""
    encoded = text.encode("utf-8", errors="replace")
    byte_count = len(encoded)
    if byte_count <= max_bytes:
        return text, byte_count, False
    capped = encoded[:max_bytes].decode("utf-8", errors="ignore")
    return capped, byte_count, True


def _extract_run_metrics(stderr_text: str, expected_nonce: str) -> tuple[dict | None, str]:
    """Pull the genuine ``__SEM_RUN_METRICS__`` sentinel out of compiler stderr.

    Returns ``(metrics_or_none, remaining_stderr)``. Only a sentinel whose
    embedded ``nonce`` matches ``expected_nonce`` is accepted, which rejects
    accidental look-alikes and casual spoofing; the compiler emits its sentinel
    last (after the program runs), so the last matching line wins. Non-matching
    look-alike lines are left in the stream as the program output they are.

    This is best-effort telemetry, not a security boundary: ``eval`` already runs
    arbitrary native code, and the nonce is passed to the child's environment, so
    a determined program with libc access could read it back and forge a line.
    Only the cosmetic metrics would be affected; nothing security-sensitive
    depends on them.
    """
    metrics = None
    kept: list[str] = []
    for line in stderr_text.splitlines():
        if line.startswith(_RUN_METRICS_SENTINEL):
            try:
                parsed = json.loads(line[len(_RUN_METRICS_SENTINEL):])
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict) and parsed.get("nonce") == expected_nonce:
                metrics = parsed  # genuine; last one wins. Strip from stderr.
                continue
        kept.append(line)
    remaining = "\n".join(kept)
    if stderr_text.endswith("\n") and remaining:
        remaining += "\n"
    return metrics, remaining


def _remap_diagnostics(diagnostics: list[dict], mode: str, offset: int) -> list[dict]:
    """Annotate wrapped-program diagnostics with snippet-relative line numbers.

    Only applies to wrapped snippets; full-program input keeps its own lines.
    Best-effort: rows hoisted to the header or moved across zones may not map
    exactly, so the original ``line`` is preserved and ``snippetLine`` is added
    alongside it.
    """
    if mode != "snippet":
        return diagnostics
    annotated = []
    for diag in diagnostics:
        diag = dict(diag)
        span = diag.get("span")
        if isinstance(span, dict) and isinstance(span.get("line"), int):
            wrapped_line = span["line"]
            span = dict(span)
            span["wrappedLine"] = wrapped_line
            if wrapped_line > offset:
                span["snippetLine"] = wrapped_line - offset
            diag["span"] = span
        annotated.append(diag)
    return annotated


def _add_eval_advisory(payload: dict, code: str, message: str) -> None:
    """Append an eval-sourced advisory note to the payload's diagnostics and
    linter notes so a programmatically-detected caveat travels the same channel
    as compiler/linter findings."""
    note = {"code": code, "severity": "warning", "message": message,
            "source": "eval", "blocksCompile": False}
    payload.setdefault("diagnostics", []).append(note)
    payload.setdefault("notes", {}).setdefault("linter", []).append(note)


def _eval_next_commands(status: str, library_mode: bool) -> list[dict]:
    """Machine-facing next steps keyed off the eval outcome.

    Entries follow the repo-wide `nextCommands` shape (`_next_command_entry`):
    each carries `kind`, `reason`, `command`, and an always-present `replayable`
    flag. They are advisory hints, not literal replays — eval compiles ephemeral
    source in a temp dir, so there is no persistent path to point `argv` at, and
    every entry is therefore `replayable: false`.
    """
    commands: list[dict] = []
    if library_mode:
        commands.append(_next_command_entry(
            "add-entry",
            "no entry operation ran; add one so the program executes",
            command="add an `entry console main` row, or pass snippet body rows",
            replayable=False))
    if status in {"compile-failed", "crashed"}:
        commands.append(_next_command_entry(
            "inspect-diagnostics",
            "inspect the full diagnostics for this source",
            command="sem check --json <source>",
            replayable=False))
    if status == "compile-failed":
        commands.append(_next_command_entry(
            "repair-plan",
            "generate a structured repair plan for the blocking diagnostics",
            command="sem fix --plan --json <source>",
            replayable=False))
    if status == "timeout":
        commands.append(_next_command_entry(
            "increase-timeout",
            "the run exceeded the wall-clock budget; allow more time",
            command="sem eval --timeout 120 <source>",
            replayable=False))
    return commands


EVAL_NATIVE_RUNTIME_PREFIXES = (
    "sqlite.",
    "http.",
    "bcrypt.",
    "json.",
    "net.",
    "event.",
    "gui.",
)


def _eval_native_runtime_targets(source_text: str) -> list[str]:
    targets: list[str] = []
    seen: set[str] = set()
    for raw_line in source_text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split()
        if len(parts) < 3 or parts[0] != "call":
            continue
        target = parts[2]
        if target.startswith(EVAL_NATIVE_RUNTIME_PREFIXES) and target not in seen:
            seen.add(target)
            targets.append(target)
    return targets


def _eval_payload(text: str, *, max_output_bytes: int, timeout: int,
                  show_source: bool, source_path: Path | None = None) -> dict:
    """Compile and JIT-run a snippet (or full program), returning sem.eval.v1."""
    mode = "program" if _snippet_looks_like_full_program(text) else "snippet"
    if mode == "program":
        wrapped, offset = text if text.endswith("\n") else text + "\n", 0
    else:
        wrapped, offset = _wrap_snippet(text)

    # A full program with no runtime entrypoint compiles in library mode: a stub
    # main returns 0 and nothing the author wrote runs. Flag it so an empty,
    # exit-0 result is never silently mistaken for a successful run.
    library_mode = mode == "program" and not _program_has_runtime_entrypoint(text)

    payload: dict = {
        "schemaVersion": EVAL_PAYLOAD_VERSION,
        "tool": {"name": "sem", "version": VERSION},
        "mode": mode,
        "libraryMode": library_mode,
        "lineOffset": offset,
    }
    if show_source:
        payload["wrappedSource"] = wrapped

    # ignore_cleanup_errors: a killed/crashed JIT child can leave a build file
    # mapped on Windows; a cleanup PermissionError must not mask the result.
    with tempfile.TemporaryDirectory(prefix="sem-eval-",
                                     ignore_cleanup_errors=True) as tmp:
        if source_path is not None and mode == "program":
            run_source_path = Path(source_path)
        else:
            run_source_path = Path(tmp) / "snippet.sem"
            run_source_path.write_text(wrapped, encoding="utf-8", newline="\n")
        build_root = Path(tmp) / "build"

        check = _build_check_payload(run_source_path, [])
        diagnostics = _remap_diagnostics(
            list(check.get("diagnostics", [])), mode, offset)
        payload["diagnostics"] = diagnostics
        # Non-strict mode runs even when notes exist, so surface them grouped by
        # origin: `notes.linter` are agent-safety/style findings, `notes.compiler`
        # are parser/codegen findings from the compiler probe. The merged
        # `diagnostics` list is retained for callers that want one stream.
        payload["notes"] = {
            "linter": [d for d in diagnostics if d.get("source") == "linter"],
            "compiler": [d for d in diagnostics if d.get("source") == "compiler"],
        }
        payload["summary"] = check.get("summary", {})
        compile_blocking = int(check.get("summary", {}).get("compileBlocking", 0))

        execution: dict = {
            "ran": False,
            "exitCode": None,
            "timing": {},
            "memory": {},
        }
        output = {
            "stdout": "", "stdoutLines": [], "stderr": "", "stderrLines": [],
            "byteCount": 0, "truncated": False,
        }

        # Always attempt the run rather than pre-gating on the linter's opinion.
        # Some lint diagnostics are flagged compile-blocking but the backend
        # tolerates them (e.g. deprecated rows), so the authoritative signal is
        # whether codegen + JIT actually completed. Diagnostics are reported
        # regardless; the outcome is classified from the run below.
        native_targets = _eval_native_runtime_targets(wrapped)
        if native_targets:
            payload["ok"] = False
            payload["status"] = "native-runtime-unavailable"
            payload["execution"] = execution
            payload["output"] = output
            payload["nativeRuntimeTargets"] = native_targets
            _add_eval_advisory(
                payload,
                "SSEVAL002",
                "sem eval uses the JIT runner and does not link native runtime "
                "adapters for targets such as " + ", ".join(native_targets[:5])
            )
            payload["nextCommands"] = [
                _next_command_entry(
                    "build",
                    "build the project or file through the native target pipeline instead of eval",
                    command="sem build <project> -- --emit-exe",
                    replayable=False,
                )
            ]
            return payload

        run_args = ["--run", "--run-metrics", "--quiet",
                    "--persist-llvm-ir", "no",
                    "--build-root", str(build_root)]
        # A per-run nonce, passed through the environment, lets us authenticate
        # the compiler's end-of-run metrics sentinel against any look-alike line
        # the running program might print.
        nonce = secrets.token_hex(8)
        run_env = dict(os.environ)
        run_env["SEM_RUN_METRICS_NONCE"] = nonce
        total_start = time.perf_counter_ns()
        try:
            proc = _capture_compiler(run_source_path, run_args,
                                     timeout=timeout, env=run_env)
        except subprocess.TimeoutExpired:
            payload["ok"] = False
            payload["status"] = "timeout"
            execution["timeoutSeconds"] = timeout
            payload["execution"] = execution
            payload["output"] = output
            payload["nextCommands"] = _eval_next_commands("timeout", library_mode)
            return payload
        total_ns = time.perf_counter_ns() - total_start

        metrics, stderr_clean = _extract_run_metrics(proc.stderr or "", nonce)
        stdout_text, stdout_byte_count, stdout_truncated = _cap_output(
            proc.stdout or "", max_output_bytes)
        stderr_text, stderr_byte_count, stderr_truncated = _cap_output(
            stderr_clean, max_output_bytes)
        stdout_str, stdout_lines = _split_stream(stdout_text)
        stderr_str, stderr_lines = _split_stream(stderr_text)
        output = {
            "stdout": stdout_str,
            "stdoutLines": stdout_lines,
            "stderr": stderr_str,
            "stderrLines": stderr_lines,
            "byteCount": stdout_byte_count + stderr_byte_count,
            "truncated": stdout_truncated or stderr_truncated,
        }

        payload["output"] = output

        # The metrics sentinel is emitted only after cmain() returns normally.
        # Its presence is the authoritative "ran to completion" signal.
        ran_to_completion = metrics is not None
        timing: dict = {
            "totalNs": total_ns,
            "totalUs": round(total_ns / 1000, 3),
        }
        if ran_to_completion:
            execute_ns = metrics.get("executeNs")
            peak_bytes = metrics.get("peakWorkingSetBytes")
            memory_source = metrics.get("memorySource", "unavailable")
            if isinstance(execute_ns, int):
                timing["executeNs"] = execute_ns
                timing["executeUs"] = round(execute_ns / 1000, 3)
                timing["compileNs"] = max(total_ns - execute_ns, 0)
            payload["execution"] = {
                "ran": True,
                "exitCode": proc.returncode,
                "timing": timing,
                "memory": {
                    "peakWorkingSetBytes": peak_bytes,
                    "peakWorkingSetKib": (round(peak_bytes / 1024)
                                          if isinstance(peak_bytes, int) else None),
                    "source": memory_source,
                },
            }
            payload["ok"] = True
            payload["status"] = "ok" if proc.returncode == 0 else "nonzero-exit"
            if library_mode:
                _add_eval_advisory(
                    payload, "SSEVAL001",
                    "no `entry` row: compiled in library mode, so the stub main "
                    "returned 0 and no operation you wrote was executed")
            payload["nextCommands"] = _eval_next_commands(
                payload["status"], library_mode)
            return payload

        # No sentinel: the program never returned. A negative return code (POSIX
        # signal) or an NTSTATUS-style Windows code (>= 0x80000000) is an abnormal
        # termination — a runtime crash. Otherwise a compiler diagnostic on stderr
        # (`SSCG...`/`semsc:`) or a blocking diagnostic with no output means codegen
        # never produced a runnable program.
        rc = proc.returncode
        abnormal_termination = rc is not None and (rc < 0 or rc >= 0x80000000)
        produced_output = bool((proc.stdout or "").strip())
        compile_signature = ("SSCG" in stderr_clean) or ("semsc:" in stderr_clean)
        execution["timing"] = timing
        if not abnormal_termination and (
                compile_signature or (compile_blocking > 0 and not produced_output)):
            payload["ok"] = False
            payload["status"] = "compile-failed"
        else:
            execution["ran"] = True
            execution["exitCode"] = rc
            payload["ok"] = False
            payload["status"] = "crashed"
        payload["execution"] = execution
        payload["nextCommands"] = _eval_next_commands(payload["status"], library_mode)
        return payload


def _read_eval_source(args: argparse.Namespace) -> tuple[str | None, str | None, Path | None]:
    """Resolve snippet text from --code, a path, or stdin (`-`).

    Returns ``(text, error, source_path)``; exactly one of text/error is non-None.
    ``source_path`` is set only when the input came from an existing file so
    full-program eval can preserve normal compiler import and asset resolution.
    """
    code = getattr(args, "code", None)
    if code is not None:
        return code, None, None
    path = getattr(args, "path", None)
    if path in (None, "-"):
        return sys.stdin.read(), None, None
    candidate = Path(path)
    if candidate.exists():
        try:
            return candidate.read_text(encoding="utf-8"), None, candidate.resolve()
        except OSError as exc:
            return None, f"cannot read snippet: {exc}", None
    # The positional did not resolve to a file. If it looks like inline
    # SemanticScript source (multi-token or multi-line), treat it as code so
    # `sem eval "operation main ..."` works without --code — the common reach
    # for a quick probe. A bare path-like token (no whitespace) still reports a
    # clear file error rather than silently compiling a mistyped filename.
    if "\n" in path or " " in path.strip():
        return path, None, None
    return None, (
        f"cannot read snippet: {path}: no such file "
        "(pass an existing path, use --code for inline source, or '-' for stdin)"
    ), None


def _emit_eval_input_error(message: str, human: bool) -> int:
    if human:
        print(f"sem eval: {message}", file=sys.stderr)
    else:
        print(json.dumps({
            "schemaVersion": EVAL_PAYLOAD_VERSION,
            "tool": {"name": "sem", "version": VERSION},
            "ok": False,
            "status": "input-error",
            "error": message,
        }, indent=2, sort_keys=True))
    return 2


def command_eval(args: argparse.Namespace) -> int:
    human = bool(getattr(args, "human", False))
    text, error, source_path = _read_eval_source(args)
    if error is not None:
        return _emit_eval_input_error(error, human)

    # A non-positive timeout would disable the wall-clock bound entirely (or
    # break subprocess); that bound is a safety control for a surface that runs
    # arbitrary compiled code, so require it.
    timeout = getattr(args, "timeout", None)
    timeout = int(EVAL_DEFAULT_TIMEOUT_SECONDS if timeout is None else timeout)
    if timeout < 1:
        return _emit_eval_input_error("--timeout must be at least 1 second", human)
    max_output_bytes = getattr(args, "max_output_bytes", None)
    max_output_bytes = int(EVAL_DEFAULT_MAX_OUTPUT_BYTES
                           if max_output_bytes is None else max_output_bytes)
    if max_output_bytes < 1:
        return _emit_eval_input_error("--max-output-bytes must be at least 1", human)
    payload = _eval_payload(
        text,
        max_output_bytes=max_output_bytes,
        timeout=timeout,
        show_source=bool(getattr(args, "show_source", False)),
        source_path=source_path,
    )

    if human:
        _print_eval_human(payload)
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload.get("ok") else 1


def _print_eval_human(payload: dict) -> None:
    """Render a sem.eval.v1 payload for a human reader."""
    status = payload.get("status", "")
    if payload.get("output", {}).get("stdout"):
        sys.stdout.write(payload["output"]["stdout"])
        if not payload["output"]["stdout"].endswith("\n"):
            sys.stdout.write("\n")
    for diag in payload.get("diagnostics", []):
        span = diag.get("span", {})
        line = span.get("snippetLine", span.get("line", "?"))
        print(f"{diag.get('severity', 'info')} {diag.get('code', '')} "
              f"line {line}: {diag.get('message', '')}", file=sys.stderr)
    execution = payload.get("execution", {})
    if execution.get("ran"):
        timing = execution.get("timing", {})
        memory = execution.get("memory", {})
        exec_us = timing.get("executeUs")
        peak_kib = memory.get("peakWorkingSetKib")
        detail = f"exit {execution.get('exitCode')}"
        if exec_us is not None:
            detail += f", execute {exec_us}µs"
        if peak_kib is not None:
            detail += f", peak {peak_kib}KiB ({memory.get('source')})"
        print(f"[{status}] {detail}", file=sys.stderr)
    else:
        print(f"[{status}] did not run", file=sys.stderr)


def command_check(args: argparse.Namespace) -> int:
    compiler_args = _strip_separator(list(args.compiler_args))
    trailing_json, compiler_args = _extract_flag(compiler_args, "--json")
    trailing_full, compiler_args = _extract_flag(compiler_args, "--full")
    trailing_readiness, compiler_args = _extract_flag(compiler_args, "--with-readiness")
    json_output = bool(getattr(args, "json", False) or trailing_json)
    full_output = bool(getattr(args, "full", False) or trailing_full)
    include_readiness = bool(getattr(args, "with_readiness", False) or trailing_readiness)
    # A directory with no build.sem is not a checkable surface — the compiler
    # would try to open() the directory as a file and report a misleading
    # "Permission denied" / "Is a directory" OS error. Detect it here and give
    # the actionable guidance instead.
    requested_path = Path(args.path)
    sem_files = (sorted(p.name for p in requested_path.glob("*.sem"))
                 if requested_path.is_dir() else [])
    # Fire only when the directory clearly holds source (`.sem` files) but has
    # no build tape. A tapeless dir with no `.sem` files is left to the normal
    # path so this guard never pre-empts a project root that simply hasn't been
    # scaffolded yet.
    if (requested_path.is_dir() and sem_files
            and _find_build_tape(requested_path) is None):
        suggestion = (
            f"pass a source file (e.g. `sem check {requested_path.as_posix()}/{sem_files[0]}`)"
        )
        message = (
            f"no build.sem (or build.sscript) found in directory "
            f"'{requested_path}'. Add a build tape to make it a project, or "
            f"{suggestion}."
        )
        if json_output:
            print(json.dumps({
                "schemaVersion": "sem.check.v1",
                "tool": {"name": "sem", "version": VERSION},
                "ok": False,
                "status": "tool-error",
                "buildable": False,
                "lintClean": False,
                "diagnostics": [],
                "errors": [message],
                "toolErrors": [message],
            }, indent=2, sort_keys=True))
        else:
            print(f"sem check: {message}", file=sys.stderr)
        return 2
    # Build the same project-scoped payload the --json path uses, so the human
    # surface no longer diverges from --json — the field log flagged this as a
    # real bug: missingInvariant appeared in the streamed compiler output but
    # not in --json's diagnostics; SS2516 appeared in --json but not human. The
    # underlying compiler still runs --lower-check + --lint (so this matches
    # the prior `buildable` semantics); only the surface format changes.
    payload = _build_check_payload(Path(args.path), compiler_args,
                                   include_readiness=include_readiness, lower_check=True)
    if include_readiness and "targetReadiness" in payload and not payload["targetReadiness"].get("ok", False):
        payload["ok"] = False
        if payload["status"] in {"ok", "ok-with-warnings"}:
            payload["status"] = payload["targetReadiness"].get("status", "partial")
    if json_output:
        payload = _compact_check_payload_for_cli(Path(args.path), payload, full=full_output)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if payload["ok"] else 1
    # Human emit: same diagnostics as --json, formatted compactly. The summary
    # footer is the headline P10 asked for ("blocking:N, warnings:M rather than
    # a bare boolean") so `ok` alone is no longer the only signal.
    for diag in payload.get("diagnostics", []) or []:
        severity = diag.get("severity") or "warning"
        code = diag.get("code") or ""
        span = diag.get("span") or diag.get("primary") or {}
        location_text = ""
        if isinstance(span, dict):
            span_file = span.get("file") or ""
            span_line = span.get("line") or 0
            if span_file:
                location_text = f"{Path(span_file).name}:{span_line}"
            elif span_line:
                location_text = f"line {span_line}"
        message = diag.get("message") or ""
        prefix = severity if not code else f"{severity} [{code}]"
        if location_text:
            print(f"{prefix} {location_text}: {message}")
        else:
            print(f"{prefix}: {message}")
    for tool_error in payload.get("toolErrors", []) or []:
        print(f"tool-error: {tool_error}", file=sys.stderr)
    summary = payload.get("summary", {}) or {}
    blocking = int(summary.get("compileBlocking", 0) or 0)
    warnings_count = int(summary.get("warnings", 0) or 0)
    total_errors = int(summary.get("errors", 0) or 0)
    non_blocking_errors = max(0, total_errors - blocking)
    print(
        f"sem check: status={payload.get('status', 'unknown')}, "
        f"blocking={blocking}, warnings={warnings_count}, "
        f"errors={non_blocking_errors}"
    )
    return 0 if payload.get("ok") else 1


def command_emit_ir(args: argparse.Namespace) -> int:
    build_tape = _find_build_tape(Path(args.path))
    source = build_tape if build_tape is not None else Path(args.path)
    return _run_compiler(source, ["--emit-ir", *_strip_separator(list(args.compiler_args))])


def command_clean(args: argparse.Namespace) -> int:
    if getattr(args, "pyinstaller_temp", False):
        temp_root, targets = _collect_pyinstaller_temp_targets(
            min_age_seconds=max(0, int(getattr(args, "min_age_seconds", 3600))),
        )
        if not targets:
            print(f"sem clean: no stale PyInstaller _MEI* temp directories found under {temp_root}")
            return 0
        for target in targets:
            prefix = "Removing" if args.force else "Would remove"
            size_mb = target["sizeBytes"] / (1024 * 1024)
            print(f"{prefix} {target['path']} ({size_mb:.1f} MiB, age {target['ageSeconds']}s)")
        if not args.force:
            print("sem clean: dry run; pass --force to remove listed PyInstaller temp directories")
            return 0
        try:
            for target in targets:
                _remove_pyinstaller_temp_target(Path(target["path"]), temp_root)
        except (OSError, ValueError) as exc:
            print(f"sem clean: {exc}", file=sys.stderr)
            return 2
        return 0
    if args.all_ignored:
        mode = "-Xdf" if args.force else "-Xdn"
        pathspecs = list(args.paths) or ["."]
        command = ["git", "clean", mode, "--", *pathspecs]
        return subprocess.call(command)
    try:
        repo_root, targets = _collect_clean_targets(list(args.paths))
        if not targets:
            print("sem clean: no ignored SemanticScript build artifacts found")
            return 0
        for target in targets:
            prefix = "Removing" if args.force else "Would remove"
            print(f"{prefix} {_format_clean_target(target, repo_root)}")
        if not args.force:
            print("sem clean: dry run; pass --force to remove listed artifacts")
            return 0
        for target in sorted(targets, key=lambda item: len(item.parts), reverse=True):
            _remove_clean_target(target, repo_root)
        return 0
    except (OSError, ValueError) as exc:
        print(f"sem clean: {exc}", file=sys.stderr)
        return 2


def command_inspect_ir(args: argparse.Namespace) -> int:
    build_tape = _find_build_tape(Path(args.path))
    source = build_tape if build_tape is not None else Path(args.path)
    return _run_compiler(source, ["--inspect-ir", *_strip_separator(list(args.compiler_args))])


def command_lint(args: argparse.Namespace) -> int:
    if args.engine != "semlint":
        print(f"sem lint: unsupported engine {args.engine}", file=sys.stderr)
        return 2
    build_tape = _find_build_tape(Path(args.path))
    source = build_tape if build_tape is not None else Path(args.path)
    semlint_path = ROOT / "linter" / "semlint.py"
    command = [
        sys.executable,
        str(semlint_path),
        str(source),
        *_strip_separator(list(args.linter_args)),
    ]
    return subprocess.call(command)


def command_fmt(args: argparse.Namespace) -> int:
    semfmt_path = ROOT / "formatter" / "semfmt.py"
    formatter_args = _strip_separator(list(args.formatter_args))
    if args.check and "--check" not in formatter_args:
        formatter_args.insert(0, "--check")
    if args.diff and "--diff" not in formatter_args:
        formatter_args.insert(0, "--diff")
    if args.paths:
        formatter_args.extend(args.paths)
    elif not formatter_args:
        formatter_args.append(".")
    command = [sys.executable, str(semfmt_path), *formatter_args]
    return subprocess.call(command)


def command_compare_profiles(args: argparse.Namespace) -> int:
    payload = _profile_delta_payload(Path(args.baseline), Path(args.candidate))
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def command_bench(args: argparse.Namespace) -> int:
    bench_script = ROOT / "bench" / "run_benchmarks.py"
    command = [sys.executable, str(bench_script)]
    if args.json:
        command.append("--json")
    if args.runs is not None:
        command.extend(["--runs", str(args.runs)])
    if args.warmup is not None:
        command.extend(["--warmup", str(args.warmup)])
    for name in args.benchmark:
        command.extend(["--benchmark", name])
    return subprocess.call(command)


def command_doctor(args: argparse.Namespace) -> int:
    payload = _doctor_payload()
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        for check in payload["checks"]:
            status = "ok" if check["ok"] else "missing"
            print(f"{status:7} {check['name']}: {check['detail']}")
            if not check["ok"] and check["fix"]:
                print(f"        fix: {check['fix']}")
    return 0 if payload["ok"] else 1


def _load_semdeps():
    compiler_dir = ROOT / "compiler"
    if str(compiler_dir) not in sys.path:
        sys.path.insert(0, str(compiler_dir))
    import semdeps
    return semdeps


def _deps_next_commands(build_tape: str, status: str) -> list[dict]:
    entries: list[dict] = []
    seen: set[str] = set()
    if status in ("pending", "verify-failed", "error", "unlocked"):
        _append_next_command(
            entries, seen, "deps-sync",
            f"sem deps sync {build_tape}",
            "fetch, verify, and lock the declared dependencies",
            argv=["sem", "deps", "sync", build_tape])
    _append_next_command(
        entries, seen, "check",
        f"sem check --json {build_tape}",
        "re-check the project against the materialized dependency cache",
        argv=["sem", "check", "--json", build_tape])
    return entries


def _deps_payload(start: Path, action: str, *, allow_network: bool, force: bool = False,
                  remove_lock: bool = False) -> dict:
    semdeps = _load_semdeps()
    base = {"schemaVersion": "sem.deps.v1", "action": action, "dependencies": []}
    build_tape = _find_build_tape(start)

    if action == "cache":
        # Cache inventory is about the machine cache, not one project — it works
        # with or without a build tape. Lists the shared cache always, plus the
        # project-local .semcache when a build tape is found.
        shared_root = semdeps._shared_cache_root()
        roots = [("shared", shared_root)]
        if build_tape is not None:
            roots.append(("project", os.path.join(
                os.path.dirname(str(build_tape)), semdeps.DEFAULT_CACHE_DIR)))
        base.update(
            ok=True, status="ok",
            sharedCacheDir=shared_root,
            buildTape=str(build_tape) if build_tape else "",
            cached=semdeps.list_cached_packages(roots),
            nextCommands=[])
        return base

    if build_tape is None:
        base.update(ok=False, status="no-build-tape",
                    error=f"no build.sem found from {start}", nextCommands=[])
        return base
    source = build_tape.read_text(encoding="utf-8")
    try:
        config = semdeps.parse_build_sem(source, str(build_tape))
    except semdeps.DependencyError as exc:
        base.update(ok=False, status="error", buildTape=str(build_tape),
                    error=str(exc),
                    nextCommands=_deps_next_commands(str(build_tape), "error"))
        return base

    base.update(
        project=config.project_name,
        buildTape=str(build_tape),
        cacheDir=config.cache_dir,
        sharedCacheDir=config.shared_cache_dir,
        cacheDirExplicit=config.cache_dir_explicit,
        lockPath=config.lock_path,
    )

    def describe(spec, status, *, resolved="", integrity="", detail="", cache_dir=""):
        row = {
            "alias": spec.alias,
            "modulePath": spec.module_path,
            "version": spec.version,
            "sourceKind": spec.source_kind,
            "status": status,
        }
        if resolved:
            row["resolved"] = resolved
        if integrity:
            row["integrity"] = integrity
        if detail:
            row["detail"] = detail
        if cache_dir:
            row["cacheDir"] = cache_dir
        return row

    if action == "purge":
        removed = semdeps.purge(config, remove_lock=remove_lock)
        base.update(ok=True, status="purged", removed=removed)
        for spec in config.specs:
            base["dependencies"].append(describe(spec, "purged"))
        base["nextCommands"] = _deps_next_commands(str(build_tape), "pending")
        return base

    if action == "sync":
        try:
            resolved = semdeps.sync(config, allow_network=allow_network, force=force)
        except semdeps.DependencyError as exc:
            base.update(ok=False, status="error", error=str(exc),
                        nextCommands=_deps_next_commands(str(build_tape), "error"))
            return base
        warnings: list[str] = []
        for item in resolved:
            row = describe(
                item.spec, "cached" if item.from_cache else "synced",
                resolved=item.lock_entry.resolved,
                integrity=item.lock_entry.integrity,
                cache_dir=item.cache_dir)
            if item.warnings:
                row["warnings"] = list(item.warnings)
                warnings.extend(item.warnings)
            base["dependencies"].append(row)
        base.update(ok=True, status="synced")
        if warnings:
            base["warnings"] = warnings
    elif action == "verify":
        try:
            verify_rows = semdeps.verify(config)
        except semdeps.DependencyError as exc:
            base.update(ok=False, status="error", error=str(exc),
                        nextCommands=_deps_next_commands(str(build_tape), "error"))
            return base
        results = {alias: (ok, detail) for alias, ok, detail in verify_rows}
        ok_all = all(ok for ok, _ in results.values()) if results else True
        for spec in config.specs:
            ok, detail = results.get(spec.alias, (False, "unknown"))
            base["dependencies"].append(describe(
                spec, "ok" if ok else "failed", detail=detail))
        base.update(ok=ok_all, status="verified" if ok_all else "verify-failed")
    else:  # list
        try:
            locked = {e.alias: e for e in (semdeps.read_lock(config) or [])}
        except semdeps.DependencyError as exc:
            base.update(ok=False, status="error", error=str(exc),
                        nextCommands=_deps_next_commands(str(build_tape), "error"))
            return base
        any_pending = False
        any_unlocked = False
        for spec in config.specs:
            cache_dir = semdeps.cache_dir_for(config, spec)
            materialized = os.path.isdir(cache_dir)
            entry = locked.get(spec.alias)
            if materialized and entry:
                status = "locked"
            elif materialized:
                status = "unlocked"
                any_unlocked = True
            else:
                status = "pending"
                any_pending = True
            base["dependencies"].append(describe(
                spec, status,
                resolved=entry.resolved if entry else "",
                integrity=entry.integrity if entry else "",
                cache_dir=cache_dir if materialized else ""))
        base.update(
            ok=not any_pending,
            status="pending" if any_pending else ("unlocked" if any_unlocked else "ready"))

    base["nextCommands"] = _deps_next_commands(str(build_tape), base["status"])
    return base


def command_deps(args: argparse.Namespace) -> int:
    action = getattr(args, "deps_action", None) or "list"
    allow_network = not getattr(args, "offline", False)
    payload = _deps_payload(
        Path(args.path), action, allow_network=allow_network,
        force=getattr(args, "force", False), remove_lock=getattr(args, "lock", False))
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if payload.get("ok") else 1
    if payload["status"] in ("no-build-tape", "error"):
        print(f"sem deps: {payload['error']}", file=sys.stderr)
        return 1
    if action == "cache":
        cached = payload.get("cached", [])
        print(f"shared cache: {payload.get('sharedCacheDir')}")
        if not cached:
            print("no cached packages")
        for entry in cached:
            kib = entry["bytes"] / 1024
            print(f"- [{entry['scope']}] {entry['key']} ({entry['sourceKind']}, "
                  f"{entry['fileCount']} files, {kib:.1f} KiB)")
        return 0
    print(f"project: {payload.get('project') or '(unnamed)'}")
    print(f"action: {action}  status: {payload['status']}")
    if action == "purge":
        removed = payload.get("removed", [])
        print(f"removed {len(removed)} path(s)")
        for path in removed:
            print(f"- {path}")
        return 0
    if not payload["dependencies"]:
        print("no external dependencies declared")
    for dep in payload["dependencies"]:
        line = f"- {dep['alias']} {dep['modulePath']} ({dep['sourceKind']}): {dep['status']}"
        if dep.get("detail") and dep["status"] not in ("ok", "synced", "cached", "locked"):
            line += f" — {dep['detail']}"
        print(line)
    for warning in payload.get("warnings", []):
        print(f"warning: {warning}")
    return 0 if payload.get("ok") else 1


AGENT_DOC_FILENAMES = ("AGENTS.md", "CLAUDE.md")
DEFAULT_AGENT_DOC_MAX_BYTES = 250_000


def _agent_doc_search_start(path: Path) -> Path:
    resolved = path.resolve()
    if resolved.is_file() or resolved.suffix.lower() in {".sem", ".sscript"}:
        return resolved.parent
    if resolved.exists():
        return resolved
    return resolved.parent if resolved.parent.exists() else Path.cwd().resolve()


def _find_agent_doc_paths(path: Path) -> tuple[Path, list[Path]]:
    start = _agent_doc_search_start(path)
    for directory in (start, *start.parents):
        docs = [directory / filename for filename in AGENT_DOC_FILENAMES if (directory / filename).is_file()]
        if docs:
            return directory.resolve(), docs
    return start.resolve(), []


def _agent_docs_payload(path: Path, *, max_bytes: int = DEFAULT_AGENT_DOC_MAX_BYTES) -> dict:
    root, docs = _find_agent_doc_paths(path)
    safe_max_bytes = max(1, int(max_bytes))
    documents = []
    for doc_path in docs:
        raw = doc_path.read_bytes()
        truncated = len(raw) > safe_max_bytes
        content = raw[:safe_max_bytes].decode("utf-8", errors="replace")
        documents.append({
            "name": doc_path.name,
            "path": str(doc_path.resolve()),
            "relativePath": doc_path.name,
            "bytes": len(raw),
            "truncated": truncated,
            "content": content,
        })
    status = "found" if documents else "not-found"
    no_docs_guidance = (
        "Fresh `sem new` projects do not scaffold AGENTS.md or CLAUDE.md. "
        "A not-found result is expected unless the repository has project-local agent rules; "
        "continue by loading version-matched sem skills."
    )
    return {
        "schemaVersion": "sem.agentDocs.v1",
        "tool": {"name": "sem", "version": VERSION},
        "ok": True,
        "status": status,
        "severity": "info",
        "emptyIsExpected": not documents,
        "absenceMeaning": "" if documents else no_docs_guidance,
        "requestedPath": str(path),
        "projectRoot": str(root),
        "searchStart": str(_agent_doc_search_start(path)),
        "readOrder": list(AGENT_DOC_FILENAMES),
        "summary": (
            "Apply project-local AGENTS.md / CLAUDE.md before editing; "
            "then load version-matched sem skills for tool and language guidance."
        ) if documents else (
            "No project-local AGENTS.md or CLAUDE.md was found from the requested path upward; "
            "fall back to version-matched sem skills."
        ),
        "documents": documents,
        "nextCommands": [
            _next_command_entry(
                "skills",
                "load version-matched SemanticScript guidance after project-local agent docs",
                argv=["sem", "skills", "get", *MCP_BOOTSTRAP_SKILLS, "--full", "--json"],
                mcp_tool="skills_get",
                mcp_args=dict(MCP_BOOTSTRAP_SKILLS_MCP_ARGS),
            ),
            _next_command_entry(
                "help",
                "inspect project state and available workflows",
                argv=["sem", "help", "--json", str(path.resolve())],
                mcp_tool="help",
                mcp_args={"path": str(path.resolve())},
            ),
        ],
    }


def command_agent_docs(args: argparse.Namespace) -> int:
    payload = _agent_docs_payload(Path(args.path), max_bytes=args.max_bytes)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    print(payload["summary"])
    for document in payload["documents"]:
        marker = " (truncated)" if document["truncated"] else ""
        print(f"\n# {document['name']} ({document['path']}){marker}")
        print(document["content"])
    return 0


def _project_workflows(path: Path) -> list[dict]:
    resolved = str(path.resolve())
    docs_db_path = str(_docs_default_db_path(path))

    def step(
        kind: str,
        reason: str,
        argv: list[object],
        *,
        command: str | None = None,
        replayable: bool | None = None,
        required_args: list[dict] | None = None,
        artifact_inputs: list[dict] | None = None,
        mcp_tool: str | None = None,
        mcp_args: dict | None = None,
    ) -> dict:
        return _next_command_entry(
            kind,
            reason,
            argv=argv,
            command=command,
            replayable=replayable,
            required_args=required_args,
            artifact_inputs=artifact_inputs,
            mcp_tool=mcp_tool,
            mcp_args=mcp_args,
        )

    return [
        {
            "id": "bootstrap-orient",
            "title": "Bootstrap and orient",
            "when": "Starting from a plain executable, a new checkout, or a cold MCP session.",
            "goal": "Load version-matched rules, inspect project state, and prove the language tool path is alive.",
            "steps": [
                step("bootstrap", "load the plain-executable startup contract", ["sem", "bootstrap", "--json", resolved]),
                step("agent-docs", "load project-local AGENTS.md / CLAUDE.md instructions", ["sem", "agent-docs", "--json", resolved], mcp_tool="agent_docs", mcp_args={"path": resolved}),
                step("skills", "load getting-started, language, agent workflow, and syntax guidance", ["sem", "skills", "get", *MCP_BOOTSTRAP_SKILLS, "--full", "--json"], mcp_tool="skills_get", mcp_args=dict(MCP_BOOTSTRAP_SKILLS_MCP_ARGS)),
                step("help", "inspect state and ordered next steps for this path", ["sem", "help", "--json", resolved], mcp_tool="help", mcp_args={"path": resolved}),
                step("eval", "run a zero-project smoke snippet when no project is open yet", ["sem", "eval", "--code", MCP_BOOTSTRAP_EVAL_CODE, "--json"], command="sem eval --code <semantic smoke snippet> --json", mcp_tool="eval", mcp_args={"code": MCP_BOOTSTRAP_EVAL_CODE}),
            ],
            "doneWhen": "The agent has loaded project docs and skills, knows the project path, and can call sem/MCP tools without guessing.",
        },
        {
            "id": "create-project",
            "title": "Create or scaffold a project",
            "when": "Starting a new app or creating a minimal repro.",
            "goal": "Create build.sem, source, tests, and optional docs-index setup from the supported starter shape.",
            "steps": [
                step("new", "create the starter SemanticScript project scaffold", ["sem", "new", "--json", "--enable-docs-index", "PROJECT_PATH"], command="sem new --json --enable-docs-index PROJECT_PATH", replayable=False, required_args=[{"name": "projectPath", "position": "final", "description": "new or empty target directory"}]),
                step("help", "inspect the scaffolded project workflow", ["sem", "help", "--json", resolved], mcp_tool="help", mcp_args={"path": resolved}),
                step("check", "prove the starter source contract is green", ["sem", "check", "--json", resolved], mcp_tool="check", mcp_args={"path": resolved}),
                step("test", "run starter semantic and harness tests", ["sem", "test", "--json", resolved], mcp_tool="test", mcp_args={"path": resolved}),
            ],
            "doneWhen": "The scaffold checks and tests cleanly, and docs search is ready if enabled.",
        },
        {
            "id": "learn-language-syntax",
            "title": "Learn language and syntax features",
            "when": "Writing rows, changing parser/linter/editor support, or checking if a syntax feature exists.",
            "goal": "Resolve current row forms and implementation status before editing or inventing syntax.",
            "steps": [
                step("skills", "load the compact syntax and language rules", ["sem", "skills", "get", "sem", "sem-syntax", "--full", "--json"], mcp_tool="skills_get", mcp_args={"names": ["sem", "sem-syntax"], "full": True}),
                step("docs-search", "search current syntax features and implementation status", ["sem", "docs", "search", "languageMode strictExecutable", "--path", resolved, "--db", docs_db_path, "--json"], mcp_tool="docs_search", mcp_args={"query": "languageMode strictExecutable", "path": resolved, "watch": True, "include_std": True}),
                step("explain", "load rule guidance when diagnostics name the syntax problem", ["sem", "explain", "SEMSC_PARSE", "--json"], mcp_tool="explain", mcp_args={"code": "SEMSC_PARSE"}),
            ],
            "doneWhen": "The agent can cite the current row form and whether the feature is implemented, partial, or not implemented.",
        },
        {
            "id": "discover-apis-capabilities-runtime",
            "title": "Discover APIs, capabilities, types, and runtime features",
            "when": "Calling stdlib/compiler targets, choosing runtime-backed features, or handling effects/cleanup.",
            "goal": "Find exact argument names, result handling, capabilities, cleanup rows, type/enums, and runtime availability.",
            "steps": [
                step("docs-index", "refresh the local docs index for project, stdlib, syntax, and runtime features", ["sem", "docs", "index", "--path", resolved, "--db", docs_db_path, "--include-std", "--embedding-provider", "none", "--json"], mcp_tool="docs_reindex", mcp_args={"path": resolved, "db": docs_db_path, "include_std": True, "background": True, "embedding_provider": "none"}),
                step("docs-search", "search for the capability, API, type, syntax, or runtime feature", ["sem", "docs", "search", "<capability, API, type, syntax, or runtime need>", "--path", resolved, "--db", docs_db_path, "--json"], command='sem docs search "<capability, API, type, syntax, or runtime need>" --path PATH --json', replayable=False, mcp_tool="docs_search", mcp_args={"query": "<capability, API, type, syntax, or runtime need>", "path": resolved, "watch": True, "include_std": True}),
                step("docs", "hydrate exact rows for a selected API/type/enum result before generating calls", ["sem", "docs", "get", "OPERATION_TARGET_TYPE_OR_ENUM", "--json"], command="sem docs get OPERATION_TARGET_TYPE_OR_ENUM --json", replayable=False, required_args=[{"name": "operation", "position": "first", "description": "selected operation, call target, type, or enum from docs_search"}], mcp_tool="docs_get", mcp_args={"operation": "<selected operation, target, type, or enum>"}),
                step("readiness", "separate source design from runtime/toolchain availability", ["sem", "readiness", "--json", resolved], mcp_tool="readiness", mcp_args={"path": resolved}),
            ],
            "doneWhen": "Generated code is based on docs rows, not guessed target names, capabilities, or runtime behavior.",
        },
        {
            "id": "dependencies",
            "title": "Resolve dependencies",
            "when": "Imports reference external packages or build.sem declares dependency rows.",
            "goal": "Materialize, verify, and lock dependencies before diagnosing source imports.",
            "steps": [
                step("deps", "list dependency state without network access", ["sem", "deps", "list", "--json", resolved], mcp_tool="deps", mcp_args={"action": "list", "path": resolved}),
                step("deps", "sync declared dependencies when imports are pending", ["sem", "deps", "sync", "--json", resolved], mcp_tool="deps", mcp_args={"action": "sync", "path": resolved}),
                step("deps", "verify cached dependency integrity", ["sem", "deps", "verify", "--json", resolved], mcp_tool="deps", mcp_args={"action": "verify", "path": resolved}),
            ],
            "doneWhen": "Dependency imports resolve and verification is clean or the payload names the external blocker.",
        },
        {
            "id": "inspect-understand",
            "title": "Inspect and understand existing code",
            "when": "Before editing shared behavior, routes, effects, ownership, or unfamiliar files.",
            "goal": "Use structured project facts instead of ad hoc file reading as the first pass.",
            "steps": [
                step("context", "load project roots, runtime flags, and supported syntax summary", ["sem", "context", "--json", resolved], mcp_tool="context", mcp_args={"path": resolved}),
                step("symbols", "load source files, operations, calls, effects, and unresolved references", ["sem", "symbols", "--json", resolved], mcp_tool="symbols", mcp_args={"path": resolved}),
                step("graph", "inspect compact architecture before drilling in", ["sem", "graph", "--kind", "summary", "--json", resolved], mcp_tool="graph", mcp_args={"path": resolved, "kind": "summary"}),
                step("slice", "focus on one operation, route, symbol, effect, capability, or type", ["sem", "slice", "--operation", "OPERATION", "--json", resolved], command="sem slice --operation OPERATION --json PATH", replayable=False, required_args=[{"name": "operation", "position": "--operation", "description": "operation name from graph or symbols"}], mcp_tool="slice", mcp_args={"path": resolved, "operation": "<operation>"}),
                step("size", "measure source/helper footprint before expensive retrieval", ["sem", "size", "--json", resolved], mcp_tool="size", mcp_args={"path": resolved}),
            ],
            "doneWhen": "The edit target and surrounding semantic neighborhood are known.",
        },
        {
            "id": "author-edit-validate",
            "title": "Author, format, and validate source",
            "when": "After making or planning source changes.",
            "goal": "Keep syntax, lint, formatting, and semantic preflight tight before runtime work.",
            "steps": [
                step("check", "parse and lint the current source/project state", ["sem", "check", "--json", resolved], mcp_tool="check", mcp_args={"path": resolved}),
                step("fmt", "check formatting before committing or generating repair plans", ["sem", "fmt", "--check", resolved]),
                step("graph", "confirm architecture changed where expected", ["sem", "graph", "--kind", "summary", "--json", resolved], mcp_tool="graph", mcp_args={"path": resolved, "kind": "summary"}),
            ],
            "doneWhen": "Check is ok or diagnostics are structured enough for repair planning.",
        },
        {
            "id": "diagnose-repair",
            "title": "Diagnose and repair",
            "when": "check/test/build returns diagnostics or compiler errors.",
            "goal": "Explain the rule, inspect the local semantic slice, generate a plan, preview, apply, and re-check.",
            "steps": [
                step("explain", "load diagnostic intent and safe repair guidance", ["sem", "explain", "CODE", "--json"], command="sem explain CODE --json", replayable=False, required_args=[{"name": "code", "position": "first", "description": "diagnostic code from check/test/build"}], mcp_tool="explain", mcp_args={"code": "<diagnostic code>"}),
                step("fix", "generate a reviewable repair plan without mutating source", ["sem", "fix", "--plan", "--json", resolved], mcp_tool="fix_plan", mcp_args={"path": resolved}),
                step("patch", "preview machine-applicable edits first", ["sem", "patch", "--dry-run", "--json", "PLAN.json"], command="sem patch --dry-run --json PLAN.json", replayable=False, required_args=[{"name": "planPath", "position": "final", "description": "saved full sem.fixPlan.v1 payload"}], mcp_tool="patch", mcp_args={"plan_path": "<plan path>", "apply": False}),
                step("patch", "apply the reviewed repair plan", ["sem", "patch", "--apply", "--json", "PLAN.json"], command="sem patch --apply --json PLAN.json", replayable=False, required_args=[{"name": "planPath", "position": "final", "description": "saved full sem.fixPlan.v1 payload"}], mcp_tool="patch", mcp_args={"plan_path": "<plan path>", "apply": True}),
                step("check", "recompute diagnostics after repair", ["sem", "check", "--json", resolved], mcp_tool="check", mcp_args={"path": resolved}),
            ],
            "doneWhen": "Diagnostics are resolved or remaining items are explicitly manual/non-patchable.",
        },
        {
            "id": "build-run-debug",
            "title": "Build, run, and debug runtime behavior",
            "when": "Source preflight is clean and runtime behavior or native artifacts matter.",
            "goal": "Prove readiness, compile/run, and inspect generated/runtime failures.",
            "steps": [
                step("readiness", "check compiler/runtime/adapter prerequisites separately from source", ["sem", "readiness", "--json", resolved], mcp_tool="readiness", mcp_args={"path": resolved}),
                step("build", "compile the project or source through the public wrapper", ["sem", "build", resolved]),
                step("run", "run through the JIT with structured crash triage when needed", ["sem", "run", "--json", "--explain-crash", resolved]),
                step("eval", "try a focused snippet or repro without project scaffolding", ["sem", "eval", "--code", "<rows>", "--json"], command="sem eval --code <rows> --json", replayable=False, mcp_tool="eval", mcp_args={"code": "<rows>"}),
                step("emit-ir", "inspect LLVM IR when debugging lowering/codegen", ["sem", "emit-ir", resolved]),
            ],
            "doneWhen": "The program builds/runs or the blocker is assigned to readiness, source diagnostics, or runtime/codegen.",
        },
        {
            "id": "test-dev-loop",
            "title": "Test and iterate",
            "when": "Behavior should be verified repeatedly or watched during active work.",
            "goal": "Use semantic preflight plus harnesses, then optional watch plans for fast iteration.",
            "steps": [
                step("test", "run semantic preflight and project harnesses", ["sem", "test", "--json", resolved], mcp_tool="test", mcp_args={"path": resolved}),
                step("test", "collect runtime signal even while semantic preflight is red when useful", ["sem", "test", "--json", "--allow-red-preflight-harnesses", resolved], mcp_tool="test", mcp_args={"path": resolved, "allow_red_preflight_harnesses": True}),
                step("dev", "emit an agent-first watch/restart plan", ["sem", "dev", "--json", resolved], mcp_tool="dev", mcp_args={"path": resolved}),
            ],
            "doneWhen": "Composite test status is green, or failures are classified as source, runtime harness, or environment.",
        },
        {
            "id": "migrate-modernize",
            "title": "Migrate or modernize syntax",
            "when": "Old row names or legacy examples appear in source/docs.",
            "goal": "Convert old syntax intentionally and verify parser/linter/docs/editor surfaces stay aligned.",
            "steps": [
                step("migrate-syntax", "rewrite supported legacy rows to current cutover forms", ["sem", "migrate-syntax", resolved, "--json"], command="sem migrate-syntax PATH --json"),
                step("skills", "reload current syntax rules after migration", ["sem", "skills", "get", "sem-syntax", "--full", "--json"], mcp_tool="skills_get", mcp_args={"names": ["sem-syntax"], "full": True}),
                step("check", "verify migrated source", ["sem", "check", "--json", resolved], mcp_tool="check", mcp_args={"path": resolved}),
            ],
            "doneWhen": "Legacy forms are gone and current parser/linter/docs agree.",
        },
        {
            "id": "clean-profile-maintain",
            "title": "Clean, profile, and maintain",
            "when": "Preparing a branch, release, benchmark, or cleanup pass.",
            "goal": "Remove ignored artifacts safely, inspect performance/profile outputs, and keep generated state out of reviews.",
            "steps": [
                step("clean", "preview generated artifacts before deletion", ["sem", "clean"]),
                step("clean", "remove ignored SemanticScript artifacts after review", ["sem", "clean", "--force"]),
                step("bench", "run benchmark harnesses when performance is the change surface", ["sem", "bench"]),
                step("compare-profiles", "compare agent/runtime profile JSON files", ["sem", "compare-profiles", "BASELINE.json", "CANDIDATE.json"], command="sem compare-profiles BASELINE.json CANDIDATE.json", replayable=False, required_args=[{"name": "baseline", "position": "first", "description": "baseline profile JSON"}, {"name": "candidate", "position": "second", "description": "candidate profile JSON"}]),
            ],
            "doneWhen": "Artifacts are intentional, performance signal is captured when relevant, and review diffs are clean.",
        },
    ]


def _help_goal_pointers(path: Path) -> list[dict]:
    resolved = str(path.resolve())
    docs_db_path = str(_docs_default_db_path(path))
    return [
        {
            "goal": "build a web app",
            "capabilities": ["http", "html", "sqlite", "webServer lifecycle"],
            "skills": ["taskforge-web-patterns", "http-html-patterns", "sqlite-patterns"],
            "startCommands": [
                "sem new --template web PROJECT_PATH",
                f"sem docs search \"webServerStartup http.responseText sqlite.openDatabase html.hydrate\" --path {resolved} --db {docs_db_path} --json",
            ],
            "docsGet": ["http.responseText", "sqlite.openDatabase", "sqlite.queryScalarInt64", "http.formField"],
            "workflowId": "discover-apis-capabilities-runtime",
        },
        {
            "goal": "fix diagnostics",
            "capabilities": ["explain", "fix plan", "patch dry-run"],
            "skills": ["sem-diagnostics"],
            "startCommands": [
                f"sem check --json {resolved}",
                "sem explain CODE --json",
                f"sem fix --plan --json {resolved}",
            ],
            "workflowId": "diagnose-repair",
        },
        {
            "goal": "inspect a codebase",
            "capabilities": ["graph", "slice", "symbols"],
            "skills": ["sem-agent"],
            "startCommands": [
                f"sem graph --kind summary --json {resolved}",
                f"sem graph --kind routes --json {resolved}",
                f"sem slice --operation NAME --json {resolved}",
            ],
            "workflowId": "inspect-understand",
        },
    ]


def _help_payload(start: Path) -> dict:
    """Recommend the next step for an agent working on this project.

    Reports project state (build tape, declared/unsynced dependencies) and an
    ordered, replayable nextCommands list so an agent always has a concrete
    "what do I run now" answer, not just a flag dump."""
    resolved = str(start.resolve())
    build_tape = _find_build_tape(start)
    state = {
        "buildTape": str(build_tape) if build_tape else "",
        "declaredDependencies": 0,
        "dependenciesSynced": True,
        "pendingDependencies": [],
    }
    entries: list[dict] = []
    seen: set[str] = set()
    start_skill_args = list(MCP_BOOTSTRAP_SKILLS)
    _append_next_command(
        entries, seen, "agent-docs",
        f"sem agent-docs --json {resolved}",
        "load project-local AGENTS.md / CLAUDE.md instructions before built-in skills",
        argv=["sem", "agent-docs", "--json", resolved],
        mcp_tool="agent_docs",
        mcp_args={"path": resolved})
    _append_next_command(
        entries, seen, "skills",
        "sem skills get sem-start sem sem-agent sem-syntax --full --json",
        "load version-matched getting-started, agent workflow, and syntax rules before editing",
        argv=["sem", "skills", "get", *start_skill_args, "--full", "--json"],
        mcp_tool="skills_get",
        mcp_args={"names": start_skill_args, "full": True})
    docs_db_path = str(_docs_default_db_path(start))
    _append_next_command(
        entries, seen, "docs-index",
        f"sem docs index --path {resolved} --db {docs_db_path} --include-std --embedding-provider none --json",
        "build the local CLI docs search index without optional embedding dependencies",
        argv=[
            "sem", "docs", "index", "--path", resolved, "--db", docs_db_path,
            "--include-std", "--embedding-provider", "none", "--json",
        ],
        mcp_tool="docs_reindex",
        mcp_args={
            "path": resolved,
            "db": docs_db_path,
            "include_std": True,
            "background": True,
            "embedding_provider": "none",
        })
    _append_next_command(
        entries, seen, "docs-search",
        f"sem docs search \"<capability, API, type, syntax, or runtime need>\" --path {resolved} --db {docs_db_path} --json",
        "discover stdlib/project APIs, syntax rows, runtime features, argument names, capabilities, failures, and cleanup before generating calls",
        argv=["sem", "docs", "search", "<capability, API, type, syntax, or runtime need>", "--path", resolved, "--db", docs_db_path, "--json"],
        replayable=False,
        mcp_tool="docs_search",
        mcp_args={
            "query": "<capability, API, type, syntax, or runtime need>",
            "path": resolved,
            "watch": True,
            "include_std": True,
        })
    if build_tape is not None:
        semdeps = _load_semdeps()
        try:
            config = semdeps.parse_build_sem(
                build_tape.read_text(encoding="utf-8"), str(build_tape))
            state["declaredDependencies"] = len(config.specs)
            _resolved, pending = semdeps.resolve_import_registry(config)
            pending_paths = sorted(pending.keys())
            state["pendingDependencies"] = pending_paths
            state["dependenciesSynced"] = not pending_paths
            if pending_paths:
                _append_next_command(
                    entries, seen, "deps-sync",
                    f"sem deps sync {resolved}",
                    "materialize declared external dependencies so imports resolve",
                    argv=["sem", "deps", "sync", resolved],
                    mcp_tool="deps",
                    mcp_args={"action": "sync", "path": resolved})
        except (OSError, semdeps.DependencyError):
            pass
    _append_next_command(
        entries, seen, "check",
        f"sem check --json {resolved}",
        "gate the project: parse, lint, and semantic checks",
        argv=["sem", "check", "--json", resolved],
        mcp_tool="check",
        mcp_args={"path": resolved})
    _append_next_command(
        entries, seen, "graph",
        f"sem graph --kind summary --json {resolved}",
        "inspect architecture: operations, calls, effects, and routes",
        argv=["sem", "graph", "--kind", "summary", "--json", resolved],
        mcp_tool="graph",
        mcp_args={"path": resolved, "kind": "summary"})
    _append_next_command(
        entries, seen, "test",
        f"sem test --json {resolved}",
        "run semantic preflight and harness tests once check is clean",
        argv=["sem", "test", "--json", resolved],
        mcp_tool="test",
        mcp_args={"path": resolved})
    return {
        "schemaVersion": "sem.help.v1",
        "tool": {"name": "sem", "version": VERSION},
        "summary": ("Recommended loop: skills -> docs_search/docs_get when APIs, types, syntax, runtime features, or capabilities are unknown -> "
                    "(deps sync) -> check -> graph/slice -> explain -> fix -> patch -> test. "
                    "Run the first nextCommand entry next."),
        "loop": ["skills", "docs search/get", "deps sync", "check", "graph/slice", "explain",
                 "fix", "patch", "test"],
        "goalPointers": _help_goal_pointers(start),
        "workflows": _project_workflows(start),
        "state": state,
        "nextCommands": entries,
    }


def command_help(args: argparse.Namespace) -> int:
    payload = _help_payload(Path(args.path))
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    print(payload["summary"])
    print(f"build tape: {payload['state']['buildTape'] or '(none)'}")
    if payload["state"]["pendingDependencies"]:
        print("unsynced dependencies: "
              + ", ".join(payload["state"]["pendingDependencies"]))
    print("workflow modes:")
    for workflow in payload.get("workflows", []):
        print(f"- {workflow['id']}: {workflow['goal']}")
    print("goal pointers:")
    for pointer in payload.get("goalPointers", []):
        print(f"- {pointer['goal']}: skills {', '.join(pointer['skills'])}; workflow {pointer['workflowId']}")
    print("next steps:")
    for item in payload["nextCommands"]:
        label = item.get("command") or " ".join(item.get("argv", []))
        print(f"- {label}\n    {item['reason']}")
    return 0


def _bootstrap_payload(start: Path | None = None) -> dict:
    project_root = str((start or Path(".")).resolve())
    source_sem = ["python", str((ROOT / "tools" / "sem.py").resolve())]
    start_skill_args = list(MCP_BOOTSTRAP_SKILLS)
    first_tool_calls = [
        {
            "tool": "agent_docs",
            "args": {"path": "."},
            "cli": "sem agent-docs --json .",
            "reason": "load project-local AGENTS.md / CLAUDE.md instructions from the MCP server cwd",
        },
        {
            "tool": "skills_get",
            "args": {"names": start_skill_args, "full": True},
            "cli": "sem skills get sem-start sem sem-agent sem-syntax --full --json",
            "reason": "load version-matched getting-started, language, agent workflow, and syntax rules",
        },
        {
            "tool": "help",
            "args": {"path": "."},
            "cli": "sem help --json .",
            "reason": "inspect project state and get replayable next steps",
        },
        {
            "tool": "docs_search",
            "args": {
                "query": "<capability, API, type, syntax, or runtime need>",
                "path": ".",
                "watch": True,
                "include_std": True,
            },
            "cli": 'sem docs search "<capability, API, type, syntax, or runtime need>" --path . --json',
            "reason": "discover stdlib/user APIs, capability rows, syntax rows, and runtime features before generating calls",
        },
        {
            "tool": "eval",
            "args": {"code": MCP_BOOTSTRAP_EVAL_CODE},
            "cli": "sem eval --code <semantic smoke snippet> --json",
            "reason": "optional zero-project smoke test for the language and runtime path",
        },
    ]
    if getattr(sys, "frozen", False):
        source_checkout = {
            "available": False,
            "note": "This is a frozen release executable; use releaseExecutable commands.",
        }
    else:
        source_checkout = {
            "available": True,
            "serverCommand": f"{_display_command(source_sem)} mcp",
            "versionCommand": f"{_display_command(source_sem)} --version --json",
            "skillsCommand": f"{_display_command(source_sem)} skills get sem-start sem sem-agent sem-syntax --full --json",
        }
    next_commands = [
        _next_command_entry(
            "mcp",
            "start the stdio MCP server from an installed release executable",
            argv=["sem", "mcp"],
            command="sem.exe mcp",
        ),
        _next_command_entry(
            "agent-docs",
            "load project-local AGENTS.md / CLAUDE.md instructions through CLI or MCP",
            argv=["sem", "agent-docs", "--json", "."],
            mcp_tool="agent_docs",
            mcp_args={"path": "."},
        ),
        _next_command_entry(
            "skills",
            "load the same getting-started guidance through the CLI",
            argv=["sem", "skills", "get", *start_skill_args, "--full", "--json"],
            mcp_tool="skills_get",
            mcp_args={"names": start_skill_args, "full": True},
        ),
        _next_command_entry(
            "docs-index",
            "build the local CLI docs search index without optional embedding dependencies",
            argv=[
                "sem", "docs", "index", "--path", ".", "--include-std",
                "--embedding-provider", "none", "--json",
            ],
            command="sem docs index --path . --include-std --embedding-provider none --json",
            mcp_tool="docs_reindex",
            mcp_args={
                "path": ".",
                "include_std": True,
                "background": True,
                "embedding_provider": "none",
            },
        ),
        _next_command_entry(
            "docs-search",
            "search API/capability/type/syntax/runtime docs before generating stdlib calls",
            argv=["sem", "docs", "search", "<capability, API, type, syntax, or runtime need>", "--path", ".", "--json"],
            command='sem docs search "<capability, API, type, syntax, or runtime need>" --path . --json',
            replayable=False,
            mcp_tool="docs_search",
            mcp_args={
                "query": "<capability, API, type, syntax, or runtime need>",
                "path": ".",
                "watch": True,
                "include_std": True,
            },
        ),
        _next_command_entry(
            "eval",
            "run a zero-project SemanticScript smoke snippet",
            argv=["sem", "eval", "--code", MCP_BOOTSTRAP_EVAL_CODE, "--json"],
            command="sem eval --code <semantic smoke snippet> --json",
            mcp_tool="eval",
            mcp_args={"code": MCP_BOOTSTRAP_EVAL_CODE},
        ),
    ]
    return {
        "schemaVersion": "sem.bootstrap.v1",
        "tool": {"name": "sem", "version": VERSION},
        "ok": True,
        "status": "ok",
        "summary": "Start MCP, load project agent docs, load sem-start/sem/sem-agent/sem-syntax, then use help and docs_search before editing or generating calls.",
        "releaseExecutable": {
            "serverCommand": "sem.exe mcp",
            "versionCommand": "sem.exe version --json",
            "agentDocsCommand": "sem.exe agent-docs --json .",
            "skillsCommand": "sem.exe skills get sem-start sem sem-agent sem-syntax --full --json",
        },
        "sourceCheckout": source_checkout,
        "mcp": {
            "serverCommand": "sem.exe mcp",
            "transport": "stdio",
            "clientConfig": {
                "command": "sem.exe",
                "args": ["mcp"],
                "cwd": "<project-root>",
            },
            "handshakeInstructions": MCP_HANDSHAKE_INSTRUCTIONS.strip(),
            "firstToolCalls": first_tool_calls,
        },
        "projectAgentDocs": {
            "tool": "agent_docs",
            "args": {"path": "."},
            "cli": "sem agent-docs --json .",
            "purpose": "Load project-local AGENTS.md / CLAUDE.md into the MCP session before relying on built-in skills.",
        },
        "docs": {
            "purpose": "Use docs_search for capability/API/type/syntax/runtime discovery and docs_get for exact usage rows before generating standard-library calls.",
            "cliIndex": "sem docs index --path . --include-std --embedding-provider none --json",
            "modelFreeDefault": True,
            "mcpSearch": {
                "tool": "docs_search",
                "args": {
                    "query": "<capability, API, type, syntax, or runtime need>",
                    "path": ".",
                    "watch": True,
                    "include_std": True,
                },
            },
            "mcpGet": {"tool": "docs_get", "args": {"operation": "<selected operation, target, type, or enum>"}},
            "cliSearch": 'sem docs search "<capability, API, type, syntax, or runtime need>" --path . --json',
            "cliGet": "sem docs get OPERATION_TARGET_TYPE_OR_ENUM --json",
            "freshInstallNote": "CLI docs search needs a model-free SQLite index first; run `sem docs index --embedding-provider none`, or use MCP docs_search with watch=true to start or reuse the background index worker.",
        },
        "languageSmoke": {
            "mcp": {"tool": "eval", "args": {"code": MCP_BOOTSTRAP_EVAL_CODE}},
            "cli": "sem eval --code <semantic smoke snippet> --json",
            "explanation": "Writes `semantic tools ready` and demonstrates the explicit console write error branch before any project is open.",
            "rowSummary": ["declare ConsoleWriteError", "write one line", "branch on write failure", "make an explicit error value"],
            "expectedStdout": "semantic tools ready\n",
        },
        "skills": {
            "start": start_skill_args,
            "aliases": {
                "sem-start": "getting-started",
                "sem": "language-core",
                "sem-agent": "graph-and-slice",
                "sem-syntax": "syntax-reference",
            },
        },
        "workflows": _project_workflows(start or Path(".")),
        "projectRoot": project_root,
        "nextCommands": next_commands,
    }


def command_bootstrap(args: argparse.Namespace) -> int:
    payload = _bootstrap_payload(Path(args.path))
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    print(payload["summary"])
    print()
    print(MCP_BOOTSTRAP_HELP.rstrip())
    source_checkout = payload["sourceCheckout"]
    if source_checkout.get("available"):
        print("Source checkout server:")
        print(f"  {source_checkout['serverCommand']}")
    else:
        print("Source checkout server:")
        print(f"  {source_checkout.get('note', 'not available from this executable')}")
    print()
    print("Exact CLI fallback:")
    print("  sem.exe skills get sem-start sem sem-agent sem-syntax --full --json")
    print("  sem.exe docs index --path . --include-std --embedding-provider none --json")
    print('  sem.exe docs search "<capability, API, type, syntax, or runtime need>" --path . --json')
    return 0


def command_version(args: argparse.Namespace) -> int:
    payload = _version_payload()
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        # Plain `sem version` previously printed only `sem 0.0.1`, hiding the one
        # thing an agent checks version for first: which native runtimes exist
        # (they decide whether an HTTP/SQLite/JSON/auth app is achievable in
        # native builds at all). Surface the enabled runtimes + syntax cutover
        # here so the capability check no longer requires --json.
        print(f"sem {VERSION}")
        flags = payload.get("runtimeFeatureFlags", {})
        enabled = sorted(name for name, on in flags.items() if on)
        print("native runtimes: " + (", ".join(enabled) if enabled else "none detected"))
        counts = payload.get("syntax", {}).get("statusCounts", {})
        if counts:
            print(
                "syntax cutover: "
                f"{counts.get('implemented', 0)} implemented, "
                f"{counts.get('partial', 0)} partial, "
                f"{counts.get('notImplemented', 0)} not implemented"
            )
        print("(run `sem version --json` for the full machine-readable report)")
    return 0


def command_new(args: argparse.Namespace) -> int:
    github_url = getattr(args, "github_url", None)
    if not args.json and not github_url:
        github_url = _prompt_for_starter_github_url()
    docs_index_opt_in = bool(getattr(args, "enable_docs_index", False))
    if not args.json and not docs_index_opt_in and not bool(getattr(args, "no_docs_index", False)):
        docs_index_opt_in = _prompt_for_starter_docs_index_opt_in()
    payload = _starter_project_payload(
        Path(args.path),
        force=bool(args.force),
        github_url=github_url,
        docs_index_opt_in=docs_index_opt_in,
        template=getattr(args, "template", "console"),
    )
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        if payload["ok"]:
            print(f"created starter project at {payload['project']['root']}")
            for path in payload["filesCreated"]:
                print(f"- created {path}")
            for path in payload["filesOverwritten"]:
                print(f"- updated {path}")
            if payload["project"].get("githubRepoUrl"):
                print(f"- github {payload['project']['githubRepoUrl']}")
            if payload["project"].get("docsIndex", {}).get("enabled"):
                print("- semantic docs index setup enabled")
            print("next:")
            for item in payload["nextCommands"]:
                print(f"- {item['command']}")
        else:
            print(f"sem new: {payload['error']}", file=sys.stderr)
    return 0 if payload["ok"] else 1


def command_readiness(args: argparse.Namespace) -> int:
    payload = _readiness_payload(Path(args.path))
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"status: {payload['status']}")
        print(f"targets: {', '.join(payload['requestedTargets'])}")
        if payload["blockingChecks"]:
            print("blocking:")
            for check in payload["blockingChecks"]:
                print(f"- {check['name']}: {check['detail']}")
        if payload["partialChecks"]:
            print("partial:")
            for check in payload["partialChecks"]:
                print(f"- {check['name']}: {check['detail']}")
    return 0 if payload["ok"] else 1


def command_context(args: argparse.Namespace) -> int:
    payload = _build_context_payload(Path(args.path))
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    project = payload["project"]
    print(f"project root: {project.get('projectRoot') or '(single file)'}")
    print(f"build tape: {project.get('buildTape') or '(none)'}")
    print(f"source files: {len(payload['sourceFiles'])}")
    print("use --json for machine-readable context")
    return 0


def command_symbols(args: argparse.Namespace) -> int:
    payload = _symbol_graph_payload(Path(args.path))
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if not payload["errors"] else 1
    summary = payload["summary"]
    print(f"files: {summary['fileCount']}")
    print(f"operations: {summary['operationCount']}")
    print(f"calls: {summary['callCount']}")
    print(f"routes: {summary['routeCount']}")
    print(f"unresolved references: {summary['unresolvedReferenceCount']}")
    print("use --json for machine-readable symbol graph")
    return 0 if not payload["errors"] else 1


def _print_std_doc_operation(operation: dict) -> None:
    print(f"{operation['fullName']}{operation['signature']['text']}")
    if operation.get("summary"):
        print(operation["summary"])
    if operation.get("purpose"):
        print(f"purpose: {operation['purpose']}")
    if operation.get("invariants"):
        print("invariants:")
        for invariant in operation["invariants"]:
            print(f"- {invariant}")
    for tag in STD_DOC_COMMENT_TAGS:
        comments = operation.get("commentsByTag", {}).get(tag, [])
        if comments:
            print(f"{tag}:")
            for comment in comments:
                print(f"- {comment['text']}")
    for tag in ("purpose", "invariant", "warning", "guarantee", "failure", "security", "timing", "observability"):
        rows = operation.get("metadata", {}).get(tag, [])
        if rows:
            print(f"{tag} rows:")
            for row in rows:
                name = f"{row.get('name')}: " if row.get("name") else ""
                print(f"- {name}{row['text']}")
    if operation.get("effects"):
        print("effects:")
        for effect in operation["effects"]:
            print(f"- {effect['action']} {effect['path']}")
    if operation.get("capabilityDetails"):
        print("capabilities:")
        for capability in operation["capabilityDetails"]:
            resource = capability.get("resource", "")
            action = capability.get("action", "")
            suffix = f" {resource} {action}" if resource or action else ""
            print(f"- {capability['name']}{suffix}")
    if operation.get("memory"):
        print("memory rows:")
        for memory_row in operation["memory"]:
            print(f"- {memory_row['text']}")
    usage = operation.get("usage", {})
    if usage:
        print("usage rows:")
        for row in usage.get("call", {}).get("rows", []):
            print(f"- {row}")


def _print_std_doc_target(target: dict) -> None:
    print(f"{target['target']}{target['signature']['text']}")
    if target.get("summary"):
        print(target["summary"])
    # Surface the return/failure contract. For status-code targets this is the
    # only place the success value is stated (e.g. bcrypt.verifyPassword returns
    # 1 on match, 0 on mismatch) — guessing it (0 == success, the C idiom) can
    # silently invert authentication, so it must be visible in the human output.
    failure_mode = target.get("failureMode") or {}
    if failure_mode.get("text"):
        print(f"returns: {failure_mode['text']}")
    # Agent warnings carry the sharp-edge hazards (e.g. the c.snprintf
    # format-string crash) — the reader who would hit them is exactly the one
    # reading the human view, so surface them here, not only in --json.
    for warning in target.get("agentWarnings") or []:
        print(f"warning: {warning}")
    if target.get("loweringStatus") and target.get("loweringStatus") != "lowered":
        print(f"loweringStatus: {target['loweringStatus']}")
    usage = target.get("usage", {})
    if usage.get("call"):
        print("usage rows:")
        for row in usage.get("call", {}).get("rows", []):
            print(f"- {row}")
    if usage.get("failureHandling", {}).get("rows"):
        print("failure handling rows:")
        for row in usage["failureHandling"]["rows"]:
            print(f"- {row}")


def _print_std_doc_type(type_doc: dict) -> None:
    representation = type_doc.get("representation", "")
    suffix = f" ({representation})" if representation else ""
    print(f"{type_doc.get('fullName') or type_doc.get('name')}{suffix}")
    if type_doc.get("summary"):
        print(type_doc["summary"])
    if type_doc.get("cases"):
        print("cases:")
        for case in type_doc["cases"]:
            print(f"- {case['name']} = {case['value']}")
    if type_doc.get("usage"):
        print("usage:")
        for row in type_doc["usage"]:
            print(f"- {row}")
    if type_doc.get("exampleRows"):
        print("example rows:")
        for row in type_doc["exampleRows"]:
            print(f"- {row}")


def command_docs(args: argparse.Namespace) -> int:
    if args.docs_command == "list":
        payload = _docs_payload(
            "list",
            module_name=args.module or "",
            summary_tag=args.summary_tag,
            include_internal=bool(args.all),
            std_root=Path(args.std_path) if args.std_path else None,
        )
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            for operation in payload["operations"]:
                summary = f" - {operation['summary']}" if operation.get("summary") else ""
                print(f"{operation['fullName']}{operation['signature']['text']}{summary}")
            for target in payload.get("targets", []):
                signature = target.get("signature", {}).get("text", "")
                summary = f" - {target['summary']}" if target.get("summary") else ""
                print(f"{target['fullName']}{signature}{summary}")
            for type_doc in payload.get("types", []):
                representation = type_doc.get("representation", "")
                suffix = f" ({representation})" if representation else ""
                summary = f" - {type_doc['summary']}" if type_doc.get("summary") else ""
                print(f"{type_doc['fullName']}{suffix}{summary}")
        return 0 if payload.get("ok") else 1
    if args.docs_command == "get":
        payload = _docs_payload(
            "get",
            operation_name=args.operation,
            module_name=args.module or "",
            summary_tag="rationale",
            include_internal=bool(args.all),
            std_root=Path(args.std_path) if args.std_path else None,
        )
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        elif payload.get("status") == "ok" and payload.get("operation"):
            _print_std_doc_operation(payload["operation"])
        elif payload.get("status") == "ok" and payload.get("target"):
            _print_std_doc_target(payload["target"])
        elif payload.get("status") == "ok" and payload.get("type"):
            _print_std_doc_type(payload["type"])
        elif payload.get("status") == "ambiguous":
            print(f"docs get: {args.operation} is ambiguous; pass --module", file=sys.stderr)
            for match in payload.get("matches", []):
                print(f"- {match.get('fullName') or match.get('target')}", file=sys.stderr)
        else:
            # `docs get` resolves call targets, curated enums, and operations.
            # Type aliases / syntax forms live in `sem reference`, and keyword
            # `sem docs search` (no embedding model needed) covers everything —
            # point there instead of a dead end, since the query may be a type.
            print(
                f"docs get: no operation, call target, or curated type named "
                f"{args.operation}. If it is a type alias or syntax form, try "
                f"`sem reference {args.operation}`; for a broad lookup use "
                f"`sem docs search \"{args.operation}\"` (no model needed).",
                file=sys.stderr)
        return 0 if payload.get("ok") else 1
    if args.docs_command == "index":
        path = Path(args.path)
        db_path = Path(args.db) if args.db else _docs_default_db_path(path)
        payload = _docs_index_payload(
            path,
            db_path=db_path,
            include_std=bool(args.include_std),
            include_compiler=not bool(args.no_compiler),
            summary_tag=args.summary_tag,
            std_root=Path(args.std_path) if args.std_path else None,
            embedding_provider=args.embedding_provider,
            embedding_model=args.embedding_model,
            enable_sqlite_vec=not bool(args.no_sqlite_vec),
            allow_model_download=bool(args.allow_model_download),
        )
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(f"indexed {payload['summary']['entryCount']} docs entries into {payload['dbPath']}")
            if payload.get("errors"):
                print("errors:", file=sys.stderr)
                for error in payload["errors"]:
                    print(f"- {error}", file=sys.stderr)
        return 0 if payload.get("ok") else 1
    if args.docs_command == "search":
        db_path = Path(args.db) if args.db else _docs_default_db_path(Path(args.path))
        payload = _docs_search_payload(
            args.query,
            db_path=db_path,
            limit=args.limit,
            embedding_provider=args.embedding_provider,
            embedding_model=args.embedding_model,
            allow_model_download=bool(args.allow_model_download),
            include_docs=bool(args.include_docs),
        )
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            for result in payload.get("results", []):
                location = result.get("location", {})
                print(f"{result['score']:.3f} {result.get('confidence', 'weak')} {result['qualifiedName']} {location.get('file', '')}:{location.get('line', 0)}")
                if result.get("summary"):
                    print(f"  {result['summary']}")
        return 0 if payload.get("ok") else 1
    if args.docs_command == "status":
        db_path = Path(args.db) if args.db else _docs_default_db_path(Path(args.path))
        payload = _docs_index_status_payload(db_path)
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(f"status: {payload['status']}")
            print(f"db: {payload['dbPath']}")
            if payload.get("summary"):
                print(f"entries: {payload['summary'].get('entryCount', 0)}")
        return 0 if payload.get("ok") else 1
    print(f"docs: unsupported command {args.docs_command}", file=sys.stderr)
    return 2


def command_size(args: argparse.Namespace) -> int:
    payload = _size_payload(Path(args.path))
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if not payload.get("errors") else 1
    summary = payload["summary"]
    print(f"files: {summary['fileCount']}")
    print(f"source bytes: {summary['sourceBytes']}")
    print(f"operations: {summary['operationCount']}")
    print(f"calls: {summary['callCount']}")
    print("use --json for machine-readable size output")
    return 0 if not payload.get("errors") else 1


def _split_markdown_table_row(line: str) -> list[str]:
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|"):
        body = body[:-1]
    cells: list[str] = []
    current: list[str] = []
    escaped = False
    in_code = False
    for ch in body:
        if escaped:
            current.append(ch)
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if ch == "`":
            in_code = not in_code
            current.append(ch)
            continue
        if ch == "|" and not in_code:
            cells.append("".join(current).strip())
            current = []
            continue
        current.append(ch)
    if escaped:
        current.append("\\")
    cells.append("".join(current).strip())
    return cells


_REFERENCE_STATUS_LEGEND = {
    "impl'd": {
        "category": "implemented",
        "meaning": "Implemented in the Python reference compiler unless the row description narrows the surface.",
    },
    "partial": {
        "category": "partial",
        "meaning": "Parsed, metadata-only, stubbed, linter-only, or otherwise incomplete; read each row description for the specific unfinished part.",
        "nextCommand": "sem reference --status Partial --json",
    },
    "not impl'd": {
        "category": "notImplemented",
        "meaning": "Committed syntax or runtime surface with no meaningful implementation yet.",
        "nextCommand": "sem reference --status \"Not impl'd\" --json",
    },
    "proposed": {
        "category": "proposed",
        "meaning": "Candidate refined syntax, not committed to the compiler surface.",
        "nextCommand": "sem reference --status Proposed --json",
    },
}


_REFERENCE_DIAGNOSTIC_SYNTAX_LINKS = (
    {
        "code": "SS3104",
        "syntax": (
            "`effect OP ACTION PATH`",
            "`capability NAME EFFECT_PATH ACCESS`",
            "`useCapability TARGET CAPABILITY`",
            "`authority OP ACTION PATH`",
        ),
        "reason": "Effect rows must be covered by a capability/useCapability edge or an inline authority row.",
    },
    {
        "code": "SS3109",
        "syntax": ("`effect OP ACTION PATH`", "`authority OP ACTION PATH`"),
        "reason": "Authority rows must use the same action/path direction as the effect they prove.",
    },
    {
        "code": "SS3612",
        "syntax": ("`output operation OP TYPE...`", "`return value VALUE`", "`return void`"),
        "reason": "Void-output operations should end with return void, not an ABI-sentinel return value row.",
    },
    {
        "code": "SS4001",
        "syntax": ("`call CALL TARGET`",),
        "reason": "Call bindings should use the Call role suffix so call rows are visually distinct from values.",
    },
    {
        "code": "SS4002",
        "syntax": ("`bind error ERROR TYPE CALL`",),
        "reason": "Error bindings should use the Error role suffix.",
    },
    {
        "code": "SS4003",
        "syntax": ("`makeError NAME ERROR.VARIANT [SOURCE]`",),
        "reason": "Constructed error values should use the Failure role suffix.",
    },
    {
        "code": "SS4101",
        "syntax": ("`call CALL TARGET`", "`run CALL`", "`argument CALL ARG_NAME TYPE VALUE`"),
        "reason": "Call attachment rows must reference a declared call object or resolvable operation target.",
    },
    {
        "code": "SS4102",
        "syntax": (
            "`label NAME`",
            "`jump target LABEL`",
            "`branch if condition CONDITION target LABEL`",
            "`branch error source CALL target LABEL`",
        ),
        "reason": "Control-flow rows must target declared labels in the current operation.",
    },
    {
        "code": "SS4105",
        "syntax": (
            "`argument CALL ARG_NAME TYPE VALUE`",
            "`branch if condition CONDITION target LABEL`",
            "`return value VALUE`",
            "`set SCOPE NAME VALUE ...`",
        ),
        "reason": "Rows that consume values must point at declared inputs, storage, binds, literals, or enum cases.",
    },
    {
        "code": "SS4301",
        "syntax": ("`argument CALL ARG_NAME TYPE VALUE`",),
        "reason": "Argument rows carry declared types and are checked against the callee signature.",
    },
)


def _reference_status_info(status: str) -> dict:
    lowered = status.strip().lower()
    for marker in ("not impl'd", "impl'd", "partial", "proposed"):
        info = _REFERENCE_STATUS_LEGEND[marker]
        if marker in lowered:
            return dict(info)
    return {"category": "unknown", "meaning": "Status not recognized; inspect the inventory source row."}


def _reference_diagnostic_links_for_row(syntax: str, description: str) -> list[dict]:
    haystack = f"{syntax} {description}".lower()
    links = []
    for spec in _REFERENCE_DIAGNOSTIC_SYNTAX_LINKS:
        markers = spec["syntax"]
        if not any(marker.lower() in haystack for marker in markers):
            continue
        code = spec["code"]
        explainer = DIAGNOSTIC_EXPLAINERS.get(code, {})
        links.append({
            "code": code,
            "title": explainer.get("title", ""),
            "reason": spec["reason"],
            "explainCommand": f"sem explain {code} --json",
        })
    return links


def _reference_diagnostic_index(rows: list[dict]) -> list[dict]:
    index = []
    for spec in _REFERENCE_DIAGNOSTIC_SYNTAX_LINKS:
        code = spec["code"]
        syntax_rows = []
        for row in rows:
            if code not in row.get("diagnosticCodes", []):
                continue
            syntax_rows.append({
                "syntax": row["syntax"],
                "description": row["description"],
                "status": row["status"],
                "statusCategory": row["statusCategory"],
            })
        explainer = DIAGNOSTIC_EXPLAINERS.get(code, {})
        index.append({
            "code": code,
            "title": explainer.get("title", ""),
            "url": f"docs/reference/diagnostic-codes.md#{code.lower()}",
            "reason": spec["reason"],
            "rowCount": len(syntax_rows),
            "syntaxRows": syntax_rows,
            "nextCommands": [
                f"sem explain {code} --json",
                f"sem reference {code} --json",
            ],
        })
    return index


def _syntax_inventory_rows() -> list[dict]:
    """Parse docs/reference/syntax-inventory.md's markdown table into
    {syntax, description, status} rows. The grammar is otherwise only reachable
    by reading the file; `sem reference` surfaces it so an agent can look up a
    row form (e.g. how to write a branch) instead of discovering each one a parse
    error at a time."""
    try:
        text = SYNTAX_INVENTORY_PATH.read_text(encoding="utf-8")
    except OSError:
        return []
    rows = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = _split_markdown_table_row(stripped)
        if len(cells) < 3:
            continue
        syntax = cells[0]
        status = cells[-1]
        description = "|".join(cells[1:-1]).strip()  # tolerate pipes in prose
        # Skip the header row and the |---|---|---| separator.
        if syntax in ("Syntax", "") or set(syntax) <= {"-", ":", " "}:
            continue
        row = {"syntax": syntax, "description": description, "status": status}
        status_info = _reference_status_info(status)
        row["statusCategory"] = status_info["category"]
        if status_info["category"] == "partial":
            row["unfinishedDetails"] = description
            row["statusNextCommand"] = status_info.get("nextCommand", "")
        diagnostic_links = _reference_diagnostic_links_for_row(syntax, description)
        if diagnostic_links:
            row["diagnosticCodes"] = [link["code"] for link in diagnostic_links]
            row["diagnosticLinks"] = diagnostic_links
        rows.append(row)
    return rows


def command_reference(args: argparse.Namespace) -> int:
    rows = _syntax_inventory_rows()
    query = (getattr(args, "query", None) or "").strip().lower()
    status_filter = (getattr(args, "status", None) or "").strip().lower()
    matched = []
    for row in rows:
        diagnostic_haystack = " ".join(
            [
                *row.get("diagnosticCodes", []),
                *[link.get("title", "") for link in row.get("diagnosticLinks", [])],
            ]
        )
        haystack = f"{row['syntax']} {row['description']} {diagnostic_haystack}".lower()
        if query and query not in haystack:
            continue
        if status_filter and status_filter not in row["status"].lower():
            continue
        matched.append(row)
    payload = {
        "schemaVersion": "sem.reference.v1",
        "tool": {"name": "sem", "version": VERSION},
        "query": query or None,
        "statusFilter": status_filter or None,
        "totalRows": len(rows),
        "matchCount": len(matched),
        "rows": matched,
        "source": str(SYNTAX_INVENTORY_PATH),
        "statusLegend": _REFERENCE_STATUS_LEGEND,
        "diagnosticIndex": _reference_diagnostic_index(rows),
        "diagnosticLookup": (
            "Rows with known diagnostic triggers include diagnosticCodes and diagnosticLinks. "
            "Query a code directly, for example `sem reference SS3104 --json`, then use "
            "`sem explain CODE --json` for repair guidance."
        ),
        "examples": [
            {
                "goal": "show implemented syntax rows",
                "command": "sem reference --status \"Impl'd\" --json",
            },
            {
                "goal": "show partial syntax rows",
                "command": "sem reference --status Partial --json",
            },
            {
                "goal": "cross-reference a diagnostic to syntax rows",
                "command": "sem reference SS3104 --json",
            },
        ],
        # `reference` indexes language SYNTAX FORMS only. Standard-library
        # operations (e.g. memory.allocateMemoryBytes, string.appendCStringTo
        # DestinationBuffer) are NOT here — find them with `docs search <need>`
        # (keyword search needs no embedding model) or `docs get <target>`.
        "operationLookup": (
            "This index covers language syntax forms only. For standard-library "
            "operations/APIs use `sem docs search \"<capability or need>\"` "
            "(keyword search works with no model) or `sem docs get <target>`."
        ),
    }
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True))
        return 0 if rows else 1
    if not rows:
        print("sem reference: syntax inventory not found", file=sys.stderr)
        return 1
    if not matched:
        print(f"no syntax rows match {query!r}"
              + (f" with status ~ {status_filter!r}" if status_filter else ""))
        print("try a broader term, e.g. `sem reference branch` or `sem reference set`")
        # reference is a syntax-form index; standard-library operations live in
        # the docs surface, so point a likely operation/API query there.
        print("for a standard-library operation or API (e.g. allocate a buffer, "
              "append a string), use `sem docs search \"<need>\"` "
              "(no model needed) or `sem docs get <target>`")
        return 0
    for row in matched:
        print(row["syntax"])
        print(f"    {row['description']}  [{row['status']}]")
        if row.get("diagnosticCodes"):
            print(f"    diagnostics: {', '.join(row['diagnosticCodes'])}")
    print(f"\n{len(matched)} of {len(rows)} rows"
          + (f" matching {query!r}" if query else "") + "; use --json for structured output")
    print("examples: sem reference --status Partial --json; sem reference SS3104 --json")
    print("note: sem reference is syntax-only. For standard-library operations/APIs, "
          "use `sem docs search \"<need>\"` or `sem docs get <target>`.")
    return 0


def command_dev(args: argparse.Namespace) -> int:
    payload = _dev_payload(Path(args.path), bool(args.trace))
    if args.json:
        payload = _compact_dev_payload_for_cli(Path(args.path), payload, full=bool(getattr(args, "full", False)))
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if payload["status"] != "blocked" else 1
    print("watch plan only; use --json for machine-readable agent workflow facts")
    print(f"watch files: {len(payload['watch']['files'])}")
    print(f"rerun: {', '.join(payload['watch']['rerun'])}")
    return 0 if payload["status"] != "blocked" else 1


def command_test(args: argparse.Namespace) -> int:
    payload = _run_test_payload(
        Path(args.path),
        include_python_harnesses=not args.skip_python_harnesses,
        allow_red_preflight_harnesses=bool(getattr(args, "allow_red_preflight_harnesses", False)),
        execute_contracts=not bool(getattr(args, "no_execute_contracts", False)),
    )
    if args.json:
        payload = _compact_test_payload_for_cli(Path(args.path), payload, full=bool(getattr(args, "full", False)))
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"status: {payload['status']}")
        print(f"discovered: {payload['discoveredTests']}")
        print(f"passed: {payload['passedTests']}")
        print(f"failed: {payload['failedTests']}")
        print(f"skipped: {payload['skippedTests']}")
        for warning in payload.get("warnings", []):
            print(f"warning: {warning}", file=sys.stderr)
    return 0 if payload["ok"] else 1


def command_graph(args: argparse.Namespace) -> int:
    payload = _graph_payload(Path(args.path), args.kind)
    if args.json:
        payload = _compact_graph_payload_for_cli(Path(args.path), payload, full=bool(getattr(args, "full", False)))
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if payload.get("ok", True) and not payload.get("errors") else 1
    summary = payload.get("summary", {})
    print(f"kind: {payload.get('kind', '')}")
    print(f"files: {summary.get('fileCount', 0)}")
    print(f"edges: {summary.get('edgeCount', 0)}")
    print("use --json for machine-readable graph output")
    return 0 if payload.get("ok", True) and not payload.get("errors") else 1


def command_slice(args: argparse.Namespace) -> int:
    payload = _slice_payload(Path(args.path), args)
    if args.json:
        payload = _compact_slice_payload_for_cli(Path(args.path), payload, full=bool(getattr(args, "full", False)))
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if payload.get("ok") else 1
    anchor = payload.get("anchor", {})
    print(f"anchor: {anchor.get('kind', '')} {anchor.get('name', '')}")
    if payload.get("operation"):
        operation = payload["operation"]
        print(f"operation: {operation.get('name', '')}")
        print(f"calls: {len(operation.get('calls', []))}")
        print(f"effects: {len(operation.get('effects', []))}")
    elif payload.get("matches") is not None:
        print(f"matches: {len(payload.get('matches', []))}")
    elif payload.get("uses") is not None:
        print(f"uses: {len(payload.get('uses', []))}")
    else:
        print(payload.get("error", "use --json for machine-readable slice output"))
    return 0 if payload.get("ok") else 1


def command_explain(args: argparse.Namespace) -> int:
    payload = _diagnostic_explain_payload(args.code)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if payload.get("found") else 1
    if not payload.get("found"):
        print(f"unknown diagnostic code: {args.code}", file=sys.stderr)
        return 1
    print(f"{payload['code']}: {payload['title']}")
    if payload.get("summary"):
        print(payload["summary"])
    if payload.get("whyItMatters"):
        print("why it matters:")
        for item in payload["whyItMatters"]:
            print(f"- {item}")
    if payload.get("commonFixes"):
        print("common fixes:")
        for fix in payload["commonFixes"]:
            print(f"- {fix}")
    if payload.get("relatedCodes"):
        print(f"related: {', '.join(payload['relatedCodes'])}")
    # Drop linter test-suite references: an agent reading `explain` wants the
    # rule's real definition or a use site, not the linter's own test fixtures.
    # Surfacing `test_*.py` grep hits as "references" was noise — and for an
    # uncurated code it looked like the only content the command had.
    references = [
        reference for reference in payload.get("references", [])
        if "test" not in os.path.basename(reference.get("path", "")).lower()
        and "/tests/" not in reference.get("path", "").replace("\\", "/").lower()
    ]
    if not payload.get("whyItMatters") and not payload.get("commonFixes"):
        print("note: no curated guidance for this code yet — showing its rule "
              "kind and any source references.")
    for reference in references[:8]:
        print(f"- {reference['path']}:{reference['line']}  {reference['excerpt']}")
    return 0


def command_fix(args: argparse.Namespace) -> int:
    compiler_args = _strip_separator(list(args.compiler_args))
    trailing_plan, compiler_args = _extract_flag(compiler_args, "--plan")
    trailing_json, compiler_args = _extract_flag(compiler_args, "--json")
    trailing_full, compiler_args = _extract_flag(compiler_args, "--full")
    trailing_include_warnings, compiler_args = _extract_flag(compiler_args, "--include-warnings")
    plan_mode = bool(args.plan or trailing_plan)
    json_output = bool(args.json or trailing_json)
    full_output = bool(getattr(args, "full", False) or trailing_full)
    include_warnings = bool(getattr(args, "include_warnings", False) or trailing_include_warnings)
    if not plan_mode:
        print("sem fix currently supports --plan only", file=sys.stderr)
        return 2
    payload = _build_fix_plan_payload(Path(args.path), compiler_args, include_warnings=include_warnings)
    if json_output:
        payload = _compact_fix_payload_for_cli(Path(args.path), payload, full=full_output)
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"repairs: {len(payload['repairs'])}")
        for repair in payload["repairs"]:
            print(f"- {repair['diagnostic']} {repair['kind']} edits={len(repair['edits'])}")
    return 0 if payload.get("planUsable", False) else 1


def command_patch(args: argparse.Namespace) -> int:
    mode = "apply" if args.apply else "dry-run"
    resolved_plan_path = str(Path(args.plan_path).resolve())
    try:
        plan = _load_plan(Path(args.plan_path))
        if isinstance(plan, dict):
            plan["_inputPlanPath"] = resolved_plan_path
    except (OSError, json.JSONDecodeError) as exc:
        payload = _patch_error_payload(
            mode,
            f"unable to load patch plan: {exc}",
            next_commands=[
                _next_command_entry(
                    "fix",
                    "generate a fresh repair plan and save it to a JSON file before patching",
                    argv=["sem", "fix", "--plan", "--json"],
                    command="sem fix --plan --json PATH",
                    replayable=False,
                    required_args=[
                        {
                            "name": "path",
                            "position": "final",
                            "description": "project file or directory to inspect before generating the plan",
                        }
                    ],
                )
            ],
            input_plan_path=resolved_plan_path,
        )
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(payload["error"], file=sys.stderr)
        return 1
    try:
        payload = _execute_patch_plan(plan, mode)
    except OSError as exc:
        payload = _patch_error_payload(
            mode,
            f"patch execution failed: {exc}",
            next_commands=_patch_next_commands(plan, mode, False),
            input_plan_path=resolved_plan_path,
        )
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"mode: {payload['mode']}")
        print(f"files changed: {len(payload['filesChanged'])}")
        for path in payload["filesChanged"]:
            print(f"- {path}")
    return 0 if payload["ok"] else 1


def _print_text_for_console(text: str) -> None:
    try:
        print(text)
    except UnicodeEncodeError:
        encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
        safe = text.encode(encoding, errors="replace").decode(encoding, errors="replace")
        print(safe)


def command_skills(args: argparse.Namespace) -> int:
    if args.skills_command in (None, "list"):
        payload = {
            "schemaVersion": "sem.skills.v1",
            "tool": {"name": "sem", "version": VERSION},
            "ok": True,
            "status": "ok",
            "skills": _skill_registry_payload(),
            "aliasIndex": dict(sorted(SKILL_ALIASES.items())),
            "recommendedFirstNames": list(MCP_BOOTSTRAP_SKILLS),
            "nextCommands": [
                _next_command_entry(
                    "skills",
                    "load getting-started, core, agent workflow, and syntax guidance from the current tool version",
                    argv=["sem", "skills", "get", *MCP_BOOTSTRAP_SKILLS, "--full", "--json"],
                    mcp_tool="skills_get",
                    mcp_args=dict(MCP_BOOTSTRAP_SKILLS_MCP_ARGS),
                )
            ],
        }
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            for skill in payload["skills"]:
                print(f"{skill['name']}: {skill['description']}")
        return 0
    if args.skills_command in ("get", "load"):
        requested_names = list(args.names)
        requested_pairs = [
            (requested_name, SKILL_ALIASES.get(requested_name, requested_name))
            for requested_name in args.names
        ]
        if args.all:
            requested_pairs = [
                (skill["name"], skill["name"])
                for skill in _skill_registry_payload()
            ]
            requested_names = [requested for requested, _resolved in requested_pairs]
        entries = []
        include_full_content = bool(args.full or not args.json)
        for requested_name, name in requested_pairs:
            skill = _skill_content(name, include_full_content=include_full_content)
            if skill is not None:
                skill = dict(skill)
                skill["requestedName"] = requested_name
                skill["displayName"] = requested_name
                entries.append(skill)
        resolved_names = [skill["resolvedName"] for skill in entries]
        found_pairs = {
            (skill["requestedName"], skill["resolvedName"])
            for skill in entries
        }
        missing_names = [
            requested_name
            for requested_name, resolved_name in requested_pairs
            if (requested_name, resolved_name) not in found_pairs
        ]
        payload = {
            "schemaVersion": "sem.skills.v1",
            "tool": {"name": "sem", "version": VERSION},
            "ok": not missing_names,
            "status": (
                "ok"
                if entries and not missing_names else
                "partial"
                if entries else
                "missing"
            ),
            "skills": entries,
            "aliasIndex": dict(sorted(SKILL_ALIASES.items())),
            "requestedNames": requested_names,
            "resolvedNames": resolved_names,
            "requestMap": [
                {"requested": requested, "resolved": resolved}
                for requested, resolved in requested_pairs
            ],
            "missingNames": missing_names,
            "contentMode": "full" if include_full_content else "summary",
            "nextCommands": [
                _next_command_entry(
                    "check",
                    "run the current toolchain against the project after loading the matching skill",
                    argv=["sem", "check", "--json"],
                    command="sem check --json PATH",
                    replayable=False,
                    mcp_tool="check",
                    mcp_args={"path": "<project file or directory>"},
                    required_args=[
                        {
                            "name": "path",
                            "position": "final",
                            "description": "project file or directory to inspect after loading the skill",
                        }
                    ],
                )
            ],
        }
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            for skill in entries:
                requested_name = skill.get("requestedName") or skill["name"]
                if requested_name != skill["name"]:
                    print(f"== {requested_name} ({skill['name']}) ==")
                else:
                    print(f"== {skill['name']} ==")
                _print_text_for_console(skill["content"])
        return 0 if entries and not missing_names else 1
    print("sem skills requires a subcommand", file=sys.stderr)
    return 2


def command_migrate_syntax(args: argparse.Namespace) -> int:
    migration_path = ROOT / "tools" / "syntax_migration.py"
    command = [sys.executable, str(migration_path)]
    if args.write:
        command.append("--write")
    if args.diff:
        command.append("--diff")
    if args.json:
        command.append("--json")
    command.extend(args.paths)
    return subprocess.call(command)


def _repin_literals_in_text(text: str, base_dir: Path) -> tuple[str, list[dict], list[str]]:
    """Recompute `literalBytes`/`literalDigest` rows from the current bytes of
    each literal's `literalSource` file. Returns (new_text, changes, missing).
    Only existing pin rows are updated (their value is rewritten in place);
    rows are never inserted or removed, so formatting is preserved."""
    lines = text.split("\n")
    sources: dict[str, str] = {}
    for line in lines:
        parts = line.split(None, 2)
        if len(parts) >= 3 and parts[0] == "literalSource":
            sources[parts[1]] = parts[2].strip().strip('"')
    computed: dict[str, tuple[int, str] | None] = {}
    missing: list[str] = []
    for name, raw_path in sources.items():
        path = Path(raw_path) if os.path.isabs(raw_path) else (base_dir / raw_path)
        try:
            data = path.read_bytes()
        except OSError:
            computed[name] = None
            missing.append(name)
            continue
        computed[name] = (len(data), hashlib.sha256(data).hexdigest())
    changes: list[dict] = []
    for index, line in enumerate(lines):
        tokens = line.split()
        if (len(tokens) >= 3 and tokens[0] == "literalBytes"
                and computed.get(tokens[1])):
            new_value = str(computed[tokens[1]][0])
            if tokens[2] != new_value:
                lines[index] = re.sub(
                    r"^(\s*literalBytes\s+" + re.escape(tokens[1]) + r"\s+)\S+",
                    lambda m: m.group(1) + new_value, line)
                changes.append({"literal": tokens[1], "field": "literalBytes",
                                "old": tokens[2], "new": new_value})
        elif (len(tokens) >= 4 and tokens[0] == "literalDigest"
                and tokens[2] == "sha256" and computed.get(tokens[1])):
            new_hex = computed[tokens[1]][1]
            if tokens[3] != new_hex:
                lines[index] = re.sub(
                    r"^(\s*literalDigest\s+" + re.escape(tokens[1]) + r"\s+sha256\s+)\S+",
                    lambda m: m.group(1) + new_hex, line)
                changes.append({"literal": tokens[1], "field": "literalDigest",
                                "old": tokens[3], "new": new_hex})
    return "\n".join(lines), changes, missing


def command_literal_repin(args: argparse.Namespace) -> int:
    """Recompute literalBytes/literalDigest pins from each literal's source
    file. Preview by default; `--write` applies. Closes the manual repin loop
    (a build-time-generated literalSource changes its bytes/hash every regen)."""
    target = Path(args.path)
    if target.is_dir():
        files = sorted(target.rglob("*.sem")) + sorted(target.rglob("*.sscript"))
    elif target.is_file():
        files = [target]
    else:
        print(f"sem literal repin: path not found: {args.path}", file=sys.stderr)
        return 2
    write = bool(getattr(args, "write", False))
    json_out = bool(getattr(args, "json", False))
    file_reports: list[dict] = []
    total_changes = 0
    for source_file in files:
        try:
            text = source_file.read_text(encoding="utf-8")
        except OSError as exc:
            file_reports.append({"file": str(source_file), "error": str(exc)})
            continue
        new_text, changes, missing = _repin_literals_in_text(text, source_file.parent)
        if not changes and not missing:
            continue
        total_changes += len(changes)
        if changes and write:
            source_file.write_text(new_text, encoding="utf-8", newline="\n")
        file_reports.append({
            "file": str(source_file),
            "changes": changes,
            "missingSources": missing,
            "applied": bool(changes and write),
        })
    had_error = any(report.get("error") for report in file_reports)
    had_missing = any(report.get("missingSources") for report in file_reports)
    payload = {
        "schemaVersion": "sem.literalRepin.v1",
        "tool": {"name": "sem", "version": VERSION},
        # `ok` reflects a clean repin: not ok when a source file was missing or a
        # .sem file could not be read, so a CI/JSON consumer can gate on it.
        "ok": not (had_error or had_missing),
        "mode": "write" if write else "preview",
        "totalChanges": total_changes,
        "files": file_reports,
    }
    if json_out:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if payload["ok"] else 1
    if not file_reports:
        print("sem literal repin: all literal pins are up to date.")
        return 0
    verb = "repinned" if write else "would repin"
    for report in file_reports:
        if report.get("error"):
            print(f"  {report['file']}: error: {report['error']}", file=sys.stderr)
            continue
        for change in report["changes"]:
            print(f"  {report['file']}: {verb} {change['literal']} "
                  f"{change['field']} {change['old']} -> {change['new']}")
        for name in report["missingSources"]:
            print(f"  {report['file']}: WARNING {name} literalSource file is "
                  f"missing; cannot repin", file=sys.stderr)
    if not write and total_changes:
        print("\nrun with --write to apply these pin updates.")
    return 0 if payload["ok"] else 1


def _github_releases_api_url(repository: str) -> str:
    return f"https://api.github.com/repos/{repository}/releases"


def _fetch_github_releases(repository: str) -> list[dict]:
    url = _github_releases_api_url(repository)
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"SemanticScript-sem/{VERSION}",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def _release_channel_matches(release: dict, channel: str) -> bool:
    if release.get("draft"):
        return False
    prerelease = bool(release.get("prerelease"))
    tag = str(release.get("tag_name", ""))
    if channel == "stable":
        return not prerelease
    if channel == "prerelease":
        return prerelease
    if channel == "main":
        return prerelease and tag.startswith("main-")
    return True


def _release_asset_for_platform(release: dict, platform: str) -> dict | None:
    assets = list(release.get("assets") or [])
    if platform == DEFAULT_RELEASE_PLATFORM:
        for asset in assets:
            if asset.get("name") == "sem.exe":
                return asset
        for asset in assets:
            name = str(asset.get("name", ""))
            if name.startswith("semanticscript-sem-windows-x64-") and name.endswith(".exe"):
                return asset
    return None


def _select_release(releases: list[dict], *, channel: str) -> dict | None:
    candidates = [release for release in releases if _release_channel_matches(release, channel)]
    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda release: str(release.get("published_at") or release.get("created_at") or ""),
        reverse=True,
    )[0]


def _self_release_payload_from_releases(
    releases: list[dict],
    *,
    repository: str,
    channel: str,
    platform: str,
) -> dict:
    release = _select_release(releases, channel=channel)
    if release is None:
        return {
            "schemaVersion": SELF_PAYLOAD_VERSION,
            "ok": False,
            "status": "release-not-found",
            "repository": repository,
            "channel": channel,
            "platform": platform,
            "apiUrl": _github_releases_api_url(repository),
            "latestEndpointUsed": False,
            "reason": "no non-draft GitHub release matched the requested channel",
        }
    asset = _release_asset_for_platform(release, platform)
    return {
        "schemaVersion": SELF_PAYLOAD_VERSION,
        "ok": asset is not None,
        "status": "ok" if asset is not None else "asset-not-found",
        "repository": repository,
        "channel": channel,
        "platform": platform,
        "apiUrl": _github_releases_api_url(repository),
        "latestEndpointUsed": False,
        "release": {
            "tag": release.get("tag_name", ""),
            "name": release.get("name", ""),
            "prerelease": bool(release.get("prerelease")),
            "draft": bool(release.get("draft")),
            "publishedAt": release.get("published_at", ""),
            "htmlUrl": release.get("html_url", ""),
        },
        "asset": (
            {
                "name": asset.get("name", ""),
                "size": asset.get("size", 0),
                "browserDownloadUrl": asset.get("browser_download_url", ""),
            }
            if asset is not None else None
        ),
        "availableAssets": [
            {
                "name": item.get("name", ""),
                "size": item.get("size", 0),
                "browserDownloadUrl": item.get("browser_download_url", ""),
            }
            for item in release.get("assets", [])
        ],
    }


def _self_latest_payload(repository: str, channel: str, platform: str) -> dict:
    try:
        releases = _fetch_github_releases(repository)
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        return {
            "schemaVersion": SELF_PAYLOAD_VERSION,
            "ok": False,
            "status": "release-query-failed",
            "repository": repository,
            "channel": channel,
            "platform": platform,
            "apiUrl": _github_releases_api_url(repository),
            "latestEndpointUsed": False,
            "error": str(exc),
        }
    return _self_release_payload_from_releases(
        releases,
        repository=repository,
        channel=channel,
        platform=platform,
    )


def _download_release_asset(url: str, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": f"SemanticScript-sem/{VERSION}"})
    with urllib.request.urlopen(request, timeout=60) as response:
        with output_path.open("wb") as out:
            shutil.copyfileobj(response, out)


def _self_download_payload(args: argparse.Namespace, *, update_mode: bool) -> dict:
    repository = getattr(args, "repo", DEFAULT_RELEASE_REPOSITORY)
    channel = getattr(args, "channel", "prerelease")
    platform = getattr(args, "platform", DEFAULT_RELEASE_PLATFORM)
    payload = _self_latest_payload(repository, channel, platform)
    output_arg = getattr(args, "output", None)
    if update_mode and output_arg is None:
        output_path = Path(sys.executable).with_name(Path(sys.executable).name + ".new")
    elif output_arg is None:
        asset_name = (payload.get("asset") or {}).get("name") or "sem.exe"
        output_path = Path.cwd() / asset_name
    else:
        output_path = Path(output_arg)
    payload["action"] = "update" if update_mode else "download"
    payload["outputPath"] = str(output_path.resolve())
    payload["applied"] = False
    payload["nextCommands"] = []
    if not payload.get("ok"):
        return payload
    asset = payload.get("asset") or {}
    download_url = asset.get("browserDownloadUrl", "")
    if not download_url:
        payload["ok"] = False
        payload["status"] = "asset-url-missing"
        return payload
    if getattr(args, "dry_run", False):
        payload["status"] = "preview"
        payload["nextCommands"].append(_next_command_entry(
            "self-download",
            "download the selected release artifact",
            argv=["sem", "self", "download", "--channel", channel, "--output", str(output_path)],
        ))
        return payload
    try:
        _download_release_asset(download_url, output_path)
    except (OSError, urllib.error.URLError) as exc:
        payload["ok"] = False
        payload["status"] = "download-failed"
        payload["error"] = str(exc)
        return payload
    payload["status"] = "downloaded"
    payload["applied"] = True
    if update_mode:
        payload["nextCommands"].append(_next_command_entry(
            "replace-executable",
            "replace the running sem executable after this process exits; Windows locks the current exe while it is running",
            argv=["powershell", "-NoProfile", "-Command", f"Move-Item -Force {str(output_path)!r} {str(Path(sys.executable))!r}"],
            replayable=False,
        ))
    return payload


def command_self(args: argparse.Namespace) -> int:
    if args.self_command == "latest":
        payload = _self_latest_payload(args.repo, args.channel, args.platform)
    elif args.self_command == "download":
        payload = _self_download_payload(args, update_mode=False)
    elif args.self_command == "update":
        payload = _self_download_payload(args, update_mode=True)
    else:
        print("sem self requires a subcommand", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        if payload.get("status") in {"ok", "downloaded", "preview"}:
            release = payload.get("release") or {}
            asset = payload.get("asset") or {}
            print(f"{payload['status']}: {release.get('tag', '<unknown>')} {asset.get('name', '')}".strip())
            if payload.get("outputPath"):
                print(f"output: {payload['outputPath']}")
        else:
            print(f"sem self: {payload.get('status', 'error')}: {payload.get('error') or payload.get('reason', '')}", file=sys.stderr)
    return 0 if payload.get("ok") else 1


def command_mcp(args: argparse.Namespace) -> int:
    try:
        from tools import sem_mcp
    except ModuleNotFoundError as exc:
        if exc.name == "mcp":
            print(
                "sem mcp: the Model Context Protocol SDK is not installed.\n"
                '        fix: python -m pip install "mcp>=1.2"',
                file=sys.stderr,
            )
            return 2
        raise
    if getattr(args, "list_tools", False):
        sem_mcp.main(["--list-tools"])
        return 0
    server_args = ["--transport", args.transport]
    if args.host is not None:
        server_args += ["--host", args.host]
    if args.port is not None:
        server_args += ["--port", str(args.port)]
    if args.path is not None:
        server_args += ["--path", args.path]
    if getattr(args, "docs_path", None) is not None:
        server_args += ["--docs-path", args.docs_path]
    if getattr(args, "docs_db", None) is not None:
        server_args += ["--docs-db", args.docs_db]
    if getattr(args, "docs_watch_interval", None) is not None:
        server_args += ["--docs-watch-interval", str(args.docs_watch_interval)]
    if getattr(args, "docs_allow_model_download", False):
        server_args += ["--docs-allow-model-download"]
    if getattr(args, "no_docs_std", False):
        server_args += ["--no-docs-std"]
    sem_mcp.main(server_args)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sem",
        description="SemanticScript project tool driver",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Bootstrap an MCP-capable agent:\n"
            "  sem.exe mcp\n"
            f"  Load project agent docs: {MCP_BOOTSTRAP_AGENT_DOCS_CALL}\n"
            f"  Then load versioned skills: {MCP_BOOTSTRAP_TOOL_CALL}\n"
            '  Then: help {"path":"."}\n'
            f"  Capability/API/type/syntax/runtime discovery: {MCP_BOOTSTRAP_DOCS_SEARCH}\n"
            f"  Optional language smoke (writes one line and shows the explicit error branch): {MCP_BOOTSTRAP_EVAL_CALL}\n"
            "\n"
            "For the full startup contract, run: sem bootstrap --json"
        ),
    )
    parser.add_argument("--version", action="version", version=f"sem {VERSION}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser(
        "build",
        help="discover build.sem and compile the project",
    )
    build.add_argument("--strict", action="store_true",
                       help="gate the build on the strict executable wall "
                            "(fallible-contract, effect/authority, SS3xxx rules)")
    build.add_argument("--standalone", action="store_true",
                       help="compile a single source file to a native exe directly "
                            "(no build.sem project required) — tightens the proof loop "
                            "for one-off snippets instead of scaffolding a throwaway project")
    build.add_argument("path", nargs="?", default=".")
    build.add_argument(
        "--platform", default=None,
        help=("filter which platforms to build from the build.sem `platforms` "
              "array. Accepts os tokens (macos, linux, windows) and/or os/arch "
              "pairs (macos/arm64, linux/x86_64), comma-separated."))
    build.add_argument("compiler_args", nargs=argparse.REMAINDER)
    build.set_defaults(func=command_build)

    run = subparsers.add_parser(
        "run",
        help="discover build.sem or use a source file and run it through the JIT",
    )
    run.add_argument("--trace", action="store_true",
                     help="emit agent JSONL trace events to stderr")
    run.add_argument("--profile", action="store_true",
                     help="aggregate trace events into an agent profile JSON report")
    run.add_argument("--json", action="store_true",
                     help="request JSON output for agent run modes")
    run.add_argument("--explain-crash", dest="explain_crash",
                     action="store_true",
                     help="run as a subprocess and emit a crash triage JSON report")
    run.add_argument("path", nargs="?", default=".")
    run.add_argument("compiler_args", nargs=argparse.REMAINDER)
    run.set_defaults(func=command_run)

    eval_cmd = subparsers.add_parser(
        "eval",
        help=("JIT-run a SemanticScript snippet (auto-wrapped in a minimal "
              "console program) or a full program and emit a sem.eval.v1 "
              "run report with execution metrics and captured output"),
    )
    eval_cmd.add_argument("path", nargs="?", default=None,
                          help="snippet/program file, inline source, or '-' / omitted for stdin")
    eval_cmd.add_argument("--code", default=None,
                          help="snippet source passed inline instead of a path")
    eval_cmd.add_argument("--json", action="store_true",
                          help="emit the sem.eval.v1 JSON payload (the default)")
    eval_cmd.add_argument("--human", action="store_true",
                          help="render program output and a status line instead of JSON")
    eval_cmd.add_argument("--show-source", dest="show_source",
                          action="store_true",
                          help="include the wrapped program source in the payload")
    eval_cmd.add_argument("--max-output-bytes", dest="max_output_bytes",
                          type=int, default=EVAL_DEFAULT_MAX_OUTPUT_BYTES,
                          help="cap captured stdout/stderr bytes (default 65536)")
    eval_cmd.add_argument("--timeout", type=int,
                          default=EVAL_DEFAULT_TIMEOUT_SECONDS,
                          help="seconds before the run is abandoned (default 30)")
    eval_cmd.set_defaults(func=command_eval)

    version = subparsers.add_parser(
        "version",
        help="emit SemanticScript toolchain version facts",
    )
    version.add_argument("--json", action="store_true",
                         help="emit machine-readable version facts")
    version.set_defaults(func=command_version)

    self_cmd = subparsers.add_parser(
        "self",
        help="discover, download, or stage a release sem executable",
    )
    self_cmd.add_argument("--json", action="store_true",
                          help="emit machine-readable self-management facts")
    self_subparsers = self_cmd.add_subparsers(dest="self_command", required=True)
    self_latest = self_subparsers.add_parser(
        "latest",
        help="query GitHub releases for the newest matching sem artifact",
    )
    self_latest.add_argument("--json", action="store_true",
                             help="emit machine-readable release facts")
    self_latest.add_argument("--repo", default=DEFAULT_RELEASE_REPOSITORY,
                             help="GitHub owner/repo to query")
    self_latest.add_argument("--channel", choices=("stable", "prerelease", "main", "any"), default="prerelease",
                             help="release channel to select; uses the releases API, not /releases/latest")
    self_latest.add_argument("--platform", default=DEFAULT_RELEASE_PLATFORM,
                             help="artifact platform to select")
    self_latest.set_defaults(func=command_self)

    self_download = self_subparsers.add_parser(
        "download",
        help="download the selected release artifact",
    )
    self_download.add_argument("--json", action="store_true",
                               help="emit machine-readable download facts")
    self_download.add_argument("--repo", default=DEFAULT_RELEASE_REPOSITORY,
                               help="GitHub owner/repo to query")
    self_download.add_argument("--channel", choices=("stable", "prerelease", "main", "any"), default="prerelease",
                               help="release channel to select")
    self_download.add_argument("--platform", default=DEFAULT_RELEASE_PLATFORM,
                               help="artifact platform to select")
    self_download.add_argument("--output", default=None,
                               help="destination path; defaults to the asset name in the current directory")
    self_download.add_argument("--dry-run", action="store_true",
                               help="resolve the selected release without downloading")
    self_download.set_defaults(func=command_self)

    self_update = self_subparsers.add_parser(
        "update",
        help="download a replacement executable next to the current sem executable",
    )
    self_update.add_argument("--json", action="store_true",
                             help="emit machine-readable update facts")
    self_update.add_argument("--repo", default=DEFAULT_RELEASE_REPOSITORY,
                             help="GitHub owner/repo to query")
    self_update.add_argument("--channel", choices=("stable", "prerelease", "main", "any"), default="prerelease",
                             help="release channel to select")
    self_update.add_argument("--platform", default=DEFAULT_RELEASE_PLATFORM,
                             help="artifact platform to select")
    self_update.add_argument("--output", default=None,
                             help="staging path; defaults to the current executable name plus .new")
    self_update.add_argument("--dry-run", action="store_true",
                             help="resolve the selected release without downloading")
    self_update.set_defaults(func=command_self)

    bootstrap = subparsers.add_parser(
        "bootstrap",
        help="print the MCP and agent onboarding bootstrap contract",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=MCP_BOOTSTRAP_HELP,
    )
    bootstrap.add_argument("--json", action="store_true",
                           help="emit machine-readable bootstrap guidance")
    bootstrap.add_argument("path", nargs="?", default=".",
                           help="project path used for path-relative examples")
    bootstrap.set_defaults(func=command_bootstrap)

    agent_docs = subparsers.add_parser(
        "agent-docs",
        help="load project-local AGENTS.md / CLAUDE.md instructions",
    )
    agent_docs.add_argument("--json", action="store_true",
                            help="emit machine-readable project agent docs")
    agent_docs.add_argument("--max-bytes", type=int,
                            default=DEFAULT_AGENT_DOC_MAX_BYTES,
                            help="maximum bytes to include per document")
    agent_docs.add_argument("path", nargs="?", default=".",
                            help="project path used to search upward for agent docs")
    agent_docs.set_defaults(func=command_agent_docs)

    new = subparsers.add_parser(
        "new",
        help="create a starter SemanticScript project with source, test, and CI scaffold files",
    )
    new.add_argument("--json", action="store_true",
                     help="emit machine-readable scaffold results")
    new.add_argument("--force", action="store_true",
                     help="overwrite the starter scaffold files when the target directory already exists")
    new.add_argument("--github-url",
                     help="optional GitHub repository URL used to replace the placeholder modulePath during setup")
    new.add_argument("--template", choices=("console", "web"), default="console",
                     help="starter project template to create")
    docs_index_group = new.add_mutually_exclusive_group()
    docs_index_group.add_argument("--enable-docs-index", action="store_true",
                                  help="add next steps for an opt-in local semantic docs index")
    docs_index_group.add_argument("--no-docs-index", action="store_true",
                                  help="skip the interactive semantic docs index prompt")
    new.add_argument("path")
    new.set_defaults(func=command_new)

    check = subparsers.add_parser(
        "check",
        help="parse and lint a build.sem project or source file",
    )
    check.add_argument("--json", action="store_true",
                       help="emit machine-readable check diagnostics and context")
    check.add_argument("--full", action="store_true",
                       help="disable compact JSON windows and emit the full machine payload")
    check.add_argument("--with-readiness", action="store_true",
                       help="embed readiness facts into the check payload instead of keeping readiness as a separate hop")
    check.add_argument("path", nargs="?", default=".")
    check.add_argument("compiler_args", nargs=argparse.REMAINDER)
    check.set_defaults(func=command_check)

    emit_ir = subparsers.add_parser(
        "emit-ir",
        help="discover build.sem or use a source file and emit LLVM IR",
    )
    emit_ir.add_argument("path", nargs="?", default=".")
    emit_ir.add_argument("compiler_args", nargs=argparse.REMAINDER)
    emit_ir.set_defaults(func=command_emit_ir)

    clean = subparsers.add_parser(
        "clean",
        help="preview or remove ignored SemanticScript build artifacts",
    )
    clean.add_argument("--force", action="store_true",
                       help="delete artifacts instead of printing a dry run")
    clean.add_argument("--all-ignored", action="store_true",
                       help="target all ignored files under the provided paths")
    clean.add_argument("--pyinstaller-temp", action="store_true",
                       help="preview or remove stale PyInstaller _MEI* extraction directories from the system temp directory")
    clean.add_argument("--min-age-seconds", type=int, default=3600,
                       help="minimum age for --pyinstaller-temp targets (default 3600)")
    clean.add_argument("paths", nargs="*",
                       help="optional git pathspecs; defaults to known generated artifact patterns")
    clean.set_defaults(func=command_clean)

    inspect_ir = subparsers.add_parser(
        "inspect-ir",
        help="emit agent-readable JSON mapping SemanticScript source to LLVM IR",
    )
    inspect_ir.add_argument("path", nargs="?", default=".")
    inspect_ir.add_argument("compiler_args", nargs=argparse.REMAINDER)
    inspect_ir.set_defaults(func=command_inspect_ir)

    compare_profiles = subparsers.add_parser(
        "compare-profiles",
        help="compare two agent profile JSON reports or artifact indexes",
    )
    compare_profiles.add_argument("baseline")
    compare_profiles.add_argument("candidate")
    compare_profiles.set_defaults(func=command_compare_profiles)

    lint = subparsers.add_parser(
        "lint",
        help="run the SemanticScript linter for a project or source file",
    )
    lint.add_argument("--engine", default="semlint", choices=("semlint",),
                      help="linter engine to use")
    lint.add_argument("path", nargs="?", default=".")
    lint.add_argument("linter_args", nargs=argparse.REMAINDER)
    lint.set_defaults(func=command_lint)

    fmt = subparsers.add_parser(
        "fmt",
        help="format SemanticScript .sem and .sscript files",
    )
    fmt.add_argument("--check", action="store_true",
                     help="exit non-zero when formatting drift is found")
    fmt.add_argument("--diff", action="store_true",
                     help="print unified diffs instead of writing files")
    fmt.add_argument("paths", nargs="*")
    fmt.add_argument("formatter_args", nargs=argparse.REMAINDER)
    fmt.set_defaults(func=command_fmt)

    bench = subparsers.add_parser(
        "bench",
        help="run SemanticScript LLVM benchmarks",
    )
    bench.add_argument("--json", action="store_true",
                       help="emit stable benchmark JSON")
    bench.add_argument("--runs", type=int,
                       help="measured iterations per benchmark")
    bench.add_argument("--warmup", type=int,
                       help="warmup iterations per benchmark")
    bench.add_argument("--benchmark", action="append", default=[],
                       help="benchmark name to run; may be repeated")
    bench.set_defaults(func=command_bench)

    doctor = subparsers.add_parser(
        "doctor",
        help="check local SemanticScript toolchain prerequisites",
    )
    doctor.add_argument("--json", action="store_true",
                        help="emit machine-readable prerequisite checks")
    doctor.set_defaults(func=command_doctor)

    deps = subparsers.add_parser(
        "deps",
        help="resolve, fetch, verify, and lock external SemanticScript dependencies declared in build.sem",
    )
    deps.add_argument("deps_action", nargs="?", default="list",
                      choices=("sync", "verify", "list", "purge", "cache"),
                      help="sync fetches+locks (network); verify checks the cache offline; "
                           "list shows declared state; purge removes this project's cached deps; "
                           "cache inventories all materialized packages")
    deps.add_argument("--json", action="store_true",
                      help="emit machine-readable dependency facts")
    deps.add_argument("--offline", action="store_true",
                      help="never access the network; only path/local dependencies and the existing cache are materialized")
    deps.add_argument("--force", action="store_true",
                      help="on sync, ignore the cache and re-fetch + re-verify every dependency (repairs a corrupt cache)")
    deps.add_argument("--lock", action="store_true",
                      help="on purge, also delete sem.lock")
    deps.add_argument("path", nargs="?", default=".",
                      help="project path or build.sem to resolve dependencies for")
    deps.set_defaults(func=command_deps)

    help_cmd = subparsers.add_parser(
        "help",
        help="emit the recommended next-step agent workflow for a project (sem.help.v1)")
    help_cmd.add_argument("--json", action="store_true",
                          help="emit machine-readable next-step guidance")
    help_cmd.add_argument("path", nargs="?", default=".",
                          help="project path or build.sem to summarize next steps for")
    help_cmd.set_defaults(func=command_help)

    readiness = subparsers.add_parser(
        "readiness",
        help="emit target, runtime, and toolchain readiness facts for agent workflows",
    )
    readiness.add_argument("--json", action="store_true",
                           help="emit machine-readable readiness facts")
    readiness.add_argument("path", nargs="?", default=".")
    readiness.set_defaults(func=command_readiness)

    context = subparsers.add_parser(
        "context",
        help="emit project context for agents and tooling",
    )
    context.add_argument("--json", action="store_true",
                         help="emit machine-readable project context")
    context.add_argument("path", nargs="?", default=".")
    context.set_defaults(func=command_context)

    symbols = subparsers.add_parser(
        "symbols",
        help="emit a source symbol graph for agents and tooling",
    )
    symbols.add_argument("--json", action="store_true",
                         help="emit machine-readable symbol graph")
    symbols.add_argument("path", nargs="?", default=".")
    symbols.set_defaults(func=command_symbols)

    docs = subparsers.add_parser(
        "docs",
        help="list, get, index, or search SemanticScript API documentation",
    )
    docs_subparsers = docs.add_subparsers(dest="docs_command", required=True)
    docs_list = docs_subparsers.add_parser(
        "list",
        help="list documented operations and call targets with short summaries",
    )
    docs_list.add_argument("--json", action="store_true",
                           help="emit machine-readable docs inventory")
    docs_list.add_argument("--std-path",
                           help="standard-library root to inspect; defaults to env vars then bundled std")
    docs_list.add_argument("--module",
                           help="limit results to one standard module, such as http or standard.http")
    docs_list.add_argument("--summary-tag", default="rationale",
                           choices=(*STD_DOC_COMMENT_TAGS, "purpose"),
                           help="prefer this typed comment tag for list summaries")
    docs_list.add_argument("--all", action="store_true",
                           help="include internal runtimeBinding helper operations")
    docs_list.set_defaults(func=command_docs)

    docs_get = docs_subparsers.add_parser(
        "get",
        help="get documentation for one operation or call target",
    )
    docs_get.add_argument("--json", action="store_true",
                          help="emit machine-readable operation documentation")
    docs_get.add_argument("--std-path",
                          help="standard-library root to inspect; defaults to env vars then bundled std")
    docs_get.add_argument("--module",
                          help="limit lookup to one standard module, such as http or standard.http")
    docs_get.add_argument("--all", action="store_true",
                          help="allow lookup of internal runtimeBinding helper operations")
    docs_get.add_argument("operation",
                          help="operation, target, type, enum, module.name, or full module-qualified name")
    docs_get.set_defaults(func=command_docs)

    docs_index = docs_subparsers.add_parser(
        "index",
        help="build or refresh a SQLite docs search index for project/std APIs",
    )
    docs_index.add_argument("--json", action="store_true",
                            help="emit machine-readable index result")
    docs_index.add_argument("--path", default=".",
                            help="project/source path to index")
    docs_index.add_argument("--db",
                            help="SQLite index path; defaults to PATH/.sem/docs.sqlite")
    docs_index.add_argument("--std-path",
                            help="standard-library root to include when --include-std is set")
    docs_index.add_argument("--include-std", action="store_true",
                            help="also index standard-library docs")
    docs_index.add_argument("--no-compiler", action="store_true",
                            help="skip compiler-owned static target docs")
    docs_index.add_argument("--summary-tag", default="rationale",
                            choices=(*STD_DOC_COMMENT_TAGS, "purpose"),
                            help="prefer this typed comment tag for summaries")
    docs_index.add_argument("--embedding-provider", default=DOCS_DEFAULT_EMBEDDING_PROVIDER,
                            choices=("none", "sentence-transformers", "auto"),
                            help="real embedding provider for vector search rows")
    docs_index.add_argument("--embedding-model", default=DOCS_DEFAULT_EMBEDDING_MODEL,
                            help="embedding model name for sentence-transformers provider")
    docs_index.add_argument("--allow-model-download", action="store_true",
                            help="allow sentence-transformers to download the model if it is not already cached locally")
    docs_index.add_argument("--no-sqlite-vec", action="store_true",
                            help="disable optional sqlite-vec virtual-table integration")
    docs_index.set_defaults(func=command_docs)

    docs_search = docs_subparsers.add_parser(
        "search",
        help="search a SQLite docs index with hybrid FTS/vector ranking",
    )
    docs_search.add_argument("--json", action="store_true",
                             help="emit machine-readable search results")
    docs_search.add_argument("--path", default=".",
                             help="project/source path used to infer default DB location")
    docs_search.add_argument("--db",
                             help="SQLite index path; defaults to PATH/.sem/docs.sqlite")
    docs_search.add_argument("--limit", type=int, default=10,
                             help="maximum results to return")
    docs_search.add_argument("--embedding-provider", default="auto",
                             choices=("none", "sentence-transformers", "auto"),
                             help="query embedding provider; auto follows index metadata")
    docs_search.add_argument("--embedding-model", default="",
                               help="embedding model name for sentence-transformers provider")
    docs_search.add_argument("--allow-model-download", action="store_true",
                             help="allow sentence-transformers to download the query model if it is not already cached locally")
    docs_search.add_argument("--include-docs", action="store_true",
                             help="include full docs objects in each result; default search results are compact")
    docs_search.add_argument("query",
                             help="English, operation-like, or type/effect-oriented query")
    docs_search.set_defaults(func=command_docs)

    docs_status = docs_subparsers.add_parser(
        "status",
        help="inspect a SQLite docs search index",
    )
    docs_status.add_argument("--json", action="store_true",
                             help="emit machine-readable index status")
    docs_status.add_argument("--path", default=".",
                             help="project/source path used to infer default DB location")
    docs_status.add_argument("--db",
                             help="SQLite index path; defaults to PATH/.sem/docs.sqlite")
    docs_status.set_defaults(func=command_docs)

    graph = subparsers.add_parser(
        "graph",
        help="emit an agent-first architecture graph derived from SemanticScript source",
    )
    graph.add_argument("--kind", default="summary",
                       choices=("summary", "calls", "effects", "capabilities", "auth", "routes", "dataflow", "types", "ownership"),
                       help="graph view to emit")
    graph.add_argument("--json", action="store_true",
                       help="emit machine-readable graph payload")
    graph.add_argument("--full", action="store_true",
                       help="disable compact JSON windows and emit the full machine payload")
    graph.add_argument("path", nargs="?", default=".")
    graph.set_defaults(func=command_graph)

    slice_cmd = subparsers.add_parser(
        "slice",
        help="emit the semantic neighborhood around an operation, route, effect, capability, or type",
    )
    slice_cmd.add_argument("--json", action="store_true",
                           help="emit machine-readable slice payload")
    slice_cmd.add_argument("--full", action="store_true",
                           help="disable compact JSON windows and emit the full machine payload")
    slice_cmd.add_argument("--operation")
    slice_cmd.add_argument("--route",
                           help="route anchor in METHOD:/path form, for example POST:/todos")
    slice_cmd.add_argument("--symbol",
                           help="symbol anchor; resolves operations, capabilities, type aliases, consts, and storage declarations")
    slice_cmd.add_argument("--effect")
    slice_cmd.add_argument("--capability")
    slice_cmd.add_argument("--type", dest="type_name")
    slice_cmd.add_argument("path", nargs="?", default=".")
    slice_cmd.set_defaults(func=command_slice)

    explain = subparsers.add_parser(
        "explain",
        help="explain a SemanticScript compiler, linter, or runtime diagnostic code",
    )
    explain.add_argument("--json", action="store_true",
                         help="emit machine-readable diagnostic explanation")
    explain.add_argument("code")
    explain.set_defaults(func=command_explain)

    fix = subparsers.add_parser(
        "fix",
        help="generate structured repair plans for SemanticScript diagnostics",
    )
    fix.add_argument("--plan", action="store_true",
                     help="emit a reviewable repair plan instead of applying edits")
    fix.add_argument("--json", action="store_true",
                     help="emit machine-readable repair plans")
    fix.add_argument("--full", action="store_true",
                     help="disable compact JSON windows and emit the full machine payload")
    fix.add_argument("--include-warnings", action="store_true",
                     help="include warning-level diagnostics when synthesizing repair suggestions")
    fix.add_argument("path", nargs="?", default=".")
    fix.add_argument("compiler_args", nargs=argparse.REMAINDER)
    fix.set_defaults(func=command_fix)

    patch = subparsers.add_parser(
        "patch",
        help="apply or preview a structured SemanticScript repair plan",
    )
    mode = patch.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true",
                      help="preview a plan without changing files")
    mode.add_argument("--apply", action="store_true",
                      help="apply a previously generated plan")
    patch.add_argument("--json", action="store_true",
                       help="emit machine-readable patch results")
    patch.add_argument("plan_path")
    patch.set_defaults(func=command_patch)

    skills = subparsers.add_parser(
        "skills",
        help="list or load version-matched agent skills from the current repository",
    )
    # Accept `--json` on the bare `skills` group too, so `sem skills --json`
    # (the inventory in machine form) works without naming the `list`
    # subcommand. Subcommands define their own `--json` for the qualified form.
    skills.add_argument("--json", action="store_true",
                        help="emit machine-readable skill inventory (bare `skills`)")
    skills_subparsers = skills.add_subparsers(dest="skills_command", required=False)
    skills_list = skills_subparsers.add_parser(
        "list",
        help="list built-in SemanticScript agent skills",
    )
    skills_list.add_argument("--json", action="store_true",
                             help="emit machine-readable skill inventory")
    skills_list.set_defaults(func=command_skills)

    # `load` is accepted as an alias for `get`: it is the natural verb agents
    # try first, and rejecting it was a documented onboarding snag.
    skills_get = skills_subparsers.add_parser(
        "get",
        aliases=["load"],
        help="load one or more built-in SemanticScript agent skills",
    )
    skills_get.add_argument("--json", action="store_true",
                            help="emit machine-readable skill content")
    skills_get.add_argument("--all", action="store_true",
                            help="return every visible built-in skill")
    skills_get.add_argument("--full", action="store_true",
                            help="include full raw skill bodies instead of the summary-first JSON shape")
    skills_get.add_argument("names", nargs="*")
    skills_get.set_defaults(func=command_skills)

    # Bare `sem skills` defaults to the inventory rather than erroring on a
    # missing subcommand — `list` is the discovery entry point agents reach
    # for first. Set after add_subparsers so it overrides the subparsers
    # action's None default; `json` is defaulted so the bare form has the
    # attribute the handler reads.
    skills.set_defaults(func=command_skills, skills_command="list", json=False)

    size = subparsers.add_parser(
        "size",
        help="emit agent-readable source and helper-footprint facts",
    )
    size.add_argument("--json", action="store_true",
                      help="emit machine-readable size facts")
    size.add_argument("path", nargs="?", default=".")
    size.set_defaults(func=command_size)

    dev = subparsers.add_parser(
        "dev",
        help="emit an agent-first watch plan for iterative edit loops",
    )
    dev.add_argument("--json", action="store_true",
                     help="emit machine-readable watch-plan facts")
    dev.add_argument("--full", action="store_true",
                     help="disable compact JSON windows and emit the full machine payload")
    dev.add_argument("--trace", action="store_true",
                     help="include phase-timing and cache-fact intent in the watch plan")
    dev.add_argument("path", nargs="?", default=".")
    dev.set_defaults(func=command_dev)

    test = subparsers.add_parser(
        "test",
        help="run a first-pass SemanticScript and harness test surface",
    )
    test.add_argument("--json", action="store_true",
                      help="emit machine-readable test results")
    test.add_argument("--full", action="store_true",
                      help="disable compact JSON windows and emit the full machine payload")
    test.add_argument("--skip-python-harnesses", action="store_true",
                      help="skip Python-based app harnesses and run only SemanticScript test files")
    test.add_argument("--allow-red-preflight-harnesses", action="store_true",
                      help="run Python harnesses even when semantic preflight diagnostics are still red")
    # Behavioral gating is ON by default: a non-trivial *.test.sem whose `main`
    # returns a nonzero ExitCode now FAILS the suite (it is JIT-run and the exit
    # code observed). Contracts that reach native runtime intrinsics can't JIT-run
    # and are reported not-executed (never a spurious failure). --execute-contracts
    # is kept as a no-op for back-compat; --no-execute-contracts restores the old
    # check-only behavior.
    test.add_argument("--execute-contracts", action="store_true",
                      help="(default) JIT-run non-trivial *.test.sem contracts and fail on a nonzero "
                           "exit (behavioral assertion); kept for back-compat — gating is now on by default")
    test.add_argument("--no-execute-contracts", action="store_true",
                      help="restore check-only semantic tests (do not JIT-run contracts; a nonzero "
                           "main exit will NOT fail the suite)")
    test.add_argument("path", nargs="?", default=".")
    test.set_defaults(func=command_test)

    reference = subparsers.add_parser(
        "reference",
        help="look up SemanticScript row syntax forms (the grammar), so you don't "
             "discover each one via a parse error",
    )
    reference.add_argument("query", nargs="?", default=None,
                           help="substring to filter syntax forms (e.g. 'branch', 'set', 'authority')")
    reference.add_argument("--status", default=None,
                           help="filter by implementation status (Impl'd / Partial / ...)")
    reference.add_argument("--json", action="store_true")
    reference.set_defaults(func=command_reference)

    migrate_syntax = subparsers.add_parser(
        "migrate-syntax",
        help="explicitly convert legacy SemanticScript row syntax",
    )
    migrate_syntax.add_argument("--write", action="store_true",
                                help="rewrite files in place")
    migrate_syntax.add_argument("--diff", action="store_true",
                                help="print unified diffs")
    migrate_syntax.add_argument("--json", action="store_true",
                                help="emit machine-readable migration results")
    migrate_syntax.add_argument("paths", nargs="+")
    migrate_syntax.set_defaults(func=command_migrate_syntax)

    literal = subparsers.add_parser(
        "literal",
        help="manage external-literal pins (literalBytes/literalDigest)",
    )
    literal_subparsers = literal.add_subparsers(dest="literal_command", required=True)
    literal_repin = literal_subparsers.add_parser(
        "repin",
        help="recompute literalBytes/literalDigest from each literal's source file",
    )
    literal_repin.add_argument("path",
                               help="a .sem file or a directory to scan")
    literal_repin.add_argument("--write", action="store_true",
                               help="apply the updated pins in place (default: preview)")
    literal_repin.add_argument("--json", action="store_true",
                               help="emit machine-readable repin results")
    literal_repin.set_defaults(func=command_literal_repin)

    mcp_server = subparsers.add_parser(
        "mcp",
        help="run the SemanticScript MCP server (Model Context Protocol); stdio by default, "
        "pass --transport streamable-http to serve over HTTP",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            MCP_BOOTSTRAP_HELP
            + "\nMCP initialize instructions repeat these first calls for clients "
            "that surface server guidance."
        ),
    )
    mcp_server.add_argument(
        "--transport",
        choices=("stdio", "streamable-http", "sse"),
        default="stdio",
        help="transport to serve on (default: stdio)",
    )
    mcp_server.add_argument("--host", help="bind host for HTTP transports (default: 127.0.0.1)")
    mcp_server.add_argument("--port", type=int, help="bind port for HTTP transports (default: 8000)")
    mcp_server.add_argument("--path", help="HTTP route for the streamable-http transport")
    mcp_server.add_argument(
        "--list-tools",
        dest="list_tools",
        action="store_true",
        help="print the MCP tool catalog as JSON and exit without serving",
    )
    mcp_server.add_argument("--docs-path", help="start a background docs index worker for this project/source path")
    mcp_server.add_argument("--docs-db", help="SQLite docs index path for the background docs worker")
    mcp_server.add_argument("--docs-watch-interval", type=float, help="background docs polling interval in seconds")
    mcp_server.add_argument("--docs-allow-model-download", action="store_true", help="allow the MCP docs worker to download the embedding model when it is not cached")
    mcp_server.add_argument("--no-docs-std", action="store_true", help="do not include std docs in the MCP background docs index")
    mcp_server.set_defaults(func=command_mcp)

    return parser


def _stdout_pipe_is_broken() -> bool:
    """Best-effort: is the stdout pipe actually broken/closed? Used to narrow the
    Windows EINVAL case (a generic errno) so an unrelated OSError(EINVAL) from a
    subprocess/file op is NOT misread as a broken pipe and silently swallowed."""
    out = sys.stdout
    if out is None or getattr(out, "closed", False):
        return True
    try:
        out.flush()
    except OSError:
        return True
    return False


def _handle_broken_pipe() -> int:
    """A downstream consumer closed the pipe (e.g. `| head` or PowerShell
    `Select-Object -First N`). The payload was being emitted successfully, so a
    truncating reader is not a tool failure and must not surface as a nonzero
    (e.g. 255) exit that would mislead a CI exit-code check. Redirect stdout to
    devnull so the interpreter's shutdown flush can't raise a second
    BrokenPipeError, then exit cleanly."""
    try:
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
    except (OSError, ValueError):
        pass
    return 0


def main(argv: list[str] | None = None) -> int:
    _force_utf8_streams()
    if argv is None:
        argv = sys.argv[1:]
    try:
        if "--version" in argv and "--json" in argv and len(argv) == 2:
            print(json.dumps(_version_payload(), indent=2, sort_keys=True))
            return 0
        parser = build_parser()
        args = parser.parse_args(argv)
        return int(args.func(args))
    except BrokenPipeError:
        return _handle_broken_pipe()
    except OSError as exc:
        # EPIPE is an unambiguous broken pipe. Windows surfaces a closed stdout
        # pipe as the generic EINVAL, so only treat EINVAL as a broken pipe when
        # stdout is actually broken — otherwise an unrelated OSError(EINVAL)
        # (e.g. a subprocess launch failure) would be masked as a clean exit.
        if exc.errno == errno.EPIPE or (
                exc.errno == errno.EINVAL and _stdout_pipe_is_broken()):
            return _handle_broken_pipe()
        raise


if __name__ == "__main__":
    raise SystemExit(main())

// SemanticScript editor support for the refined compiler.
//
// Highlighting comes from syntaxes/semanticscript.tm-language.json, which is
// generated from the compiler's shape table (`refined grammar --textmate`).
// Diagnostics come from `refined check --json` on the project that owns the
// file: the nearest directory above it that holds build.sem, or the file itself
// when it is not in a project.
"use strict";

const vscode = require("vscode");
const cp = require("child_process");
const fs = require("fs");
const path = require("path");

let diagnostics;
let output;

function setting(name, fallback) {
  const value = vscode.workspace.getConfiguration("semanticScript").get(name);
  return value === undefined || value === "" ? fallback : value;
}

function compilerPath() {
  const configured = setting("compilerPath", "");
  if (configured) {
    return configured;
  }
  for (const folder of vscode.workspace.workspaceFolders || []) {
    const candidate = path.join(folder.uri.fsPath, "semanticscript", "compiler", "refined");
    if (fs.existsSync(path.join(candidate, "__main__.py"))) {
      return candidate;
    }
  }
  return null;
}

function projectFor(file) {
  let dir = path.dirname(file);
  for (;;) {
    if (fs.existsSync(path.join(dir, "build.sem"))) {
      return dir;
    }
    const parent = path.dirname(dir);
    if (parent === dir) {
      break;
    }
    dir = parent;
  }
  return file.endsWith(".test.sem") ? file.slice(0, -".test.sem".length) + ".sem" : file;
}

function runCompiler(args, cwd) {
  const compiler = compilerPath();
  if (!compiler) {
    return Promise.reject(new Error(
      "SemanticScript: the refined compiler was not found; set semanticScript.compilerPath"));
  }
  const python = setting("pythonPath", "python");
  return new Promise((resolve) => {
    cp.execFile(python, [compiler, ...args], { cwd, maxBuffer: 16 * 1024 * 1024 },
      (error, stdout, stderr) => resolve({ error, stdout, stderr }));
  });
}

async function check(document) {
  if (!document || document.languageId !== "semanticscript" || document.uri.scheme !== "file") {
    return;
  }
  const target = projectFor(document.uri.fsPath);
  let result;
  try {
    result = await runCompiler(["check", target, "--json"], path.dirname(document.uri.fsPath));
  } catch (err) {
    vscode.window.showWarningMessage(err.message);
    return;
  }
  let payload;
  try {
    payload = JSON.parse(result.stdout);
  } catch (_err) {
    output.appendLine(result.stdout + result.stderr);
    return;
  }
  const byFile = new Map();
  for (const d of payload.diagnostics || []) {
    const file = path.resolve(d.file);
    const line = Math.max(0, (d.line || 1) - 1);
    const range = new vscode.Range(line, 0, line, Number.MAX_SAFE_INTEGER);
    const item = new vscode.Diagnostic(range, d.message, vscode.DiagnosticSeverity.Error);
    item.code = d.code;
    item.source = "semanticscript";
    if (!byFile.has(file)) {
      byFile.set(file, []);
    }
    byFile.get(file).push(item);
  }
  // clear every file of this project, then set what was reported
  diagnostics.forEach((uri) => {
    if (uri.fsPath.startsWith(fs.statSync(target).isDirectory() ? target : path.dirname(target))) {
      diagnostics.delete(uri);
    }
  });
  for (const [file, items] of byFile) {
    diagnostics.set(vscode.Uri.file(file), items);
  }
}

function runInTerminal(command) {
  const editor = vscode.window.activeTextEditor;
  if (!editor) {
    return;
  }
  const compiler = compilerPath();
  if (!compiler) {
    vscode.window.showWarningMessage("SemanticScript: set semanticScript.compilerPath");
    return;
  }
  const target = projectFor(editor.document.uri.fsPath);
  const terminal = vscode.window.createTerminal(`SemanticScript ${command}`);
  terminal.show();
  const q = (s) => `"${s}"`;
  terminal.sendText(`${q(setting("pythonPath", "python"))} ${q(compiler)} ${command} ${q(target)}`);
}

function activate(context) {
  diagnostics = vscode.languages.createDiagnosticCollection("semanticscript");
  output = vscode.window.createOutputChannel("SemanticScript");
  context.subscriptions.push(diagnostics, output);
  context.subscriptions.push(
    vscode.workspace.onDidSaveTextDocument((doc) => {
      if (setting("checkOnSave", true)) {
        check(doc);
      }
    }),
    vscode.workspace.onDidOpenTextDocument((doc) => {
      if (setting("checkOnSave", true)) {
        check(doc);
      }
    }),
    vscode.commands.registerCommand("semanticscript.check", () =>
      check(vscode.window.activeTextEditor && vscode.window.activeTextEditor.document)),
    vscode.commands.registerCommand("semanticscript.run", () => runInTerminal("run")),
    vscode.commands.registerCommand("semanticscript.test", () => runInTerminal("test")),
  );
  for (const doc of vscode.workspace.textDocuments) {
    check(doc);
  }
}

function deactivate() {}

module.exports = { activate, deactivate };

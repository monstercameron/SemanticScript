'use strict';

const childProcess = require('child_process');
const fs = require('fs');
const path = require('path');
const vscode = require('vscode');

const declarationVerbs = new Set([
  'project', 'target', 'runtime', 'entry', 'module', 'dependency', 'dependencyEffect',
  'dependencyExports', 'dependencyFunction', 'dependencyFunctionInput',
  'dependencyFunctionOutput', 'dependencyFunctionEffect', 'dependencyFunctionAsync',
  'importModule', 'type', 'typeInvariant', 'typeRepresentation', 'typeTrust',
  'typeMemory', 'typeLayout', 'record', 'field', 'enum', 'enumCase', 'error',
  'errorCase', 'operation', 'webServer', 'serverHost', 'serverPort', 'route',
  'routeTimeout', 'routeMiddleware', 'jsonCodec', 'policy', 'errorPolicy',
  'validator', 'codec', 'schema', 'unknownFields', 'resource', 'resourceKey',
  'resourceValue', 'resourceKind', 'adapter', 'boundary', 'mapper', 'retryPolicy',
  'timeoutBudget', 'capability', 'authority', 'mutex', 'shared', 'channel',
  'const', 'var', 'testCovers',
]);

const contextVerbs = new Set([
  'input', 'output', 'effect', 'memory', 'async', 'purpose', 'invariant', 'warning',
  'failure', 'guarantee', 'security', 'timing', 'observability',
]);

const actionVerbs = new Set([
  'set', 'call', 'arg', 'run', 'start', 'await', 'bind', 'bindOk',
  'bindError', 'ignoreOk', 'ignoreValue', 'makeError', 'new', 'fieldGet', 'fieldSet', 'timeout', 'cancelOn',
  'defer', 'deferLog', 'deferAwaitLog', 'deferWhenExitLog', 'select', 'selectCase',
  'runSelect', 'taskGroup', 'startInGroup', 'awaitGroup', 'bindGroupError',
  'send', 'receive', 'lock', 'unlock', 'useRetry', 'useCapability',
]);

const controlVerbs = new Set([
  'label', 'branch', 'branchIf', 'branchIfError', 'branchSelected',
  'branchIfGroupError', 'branchIfChannelClosed', 'returnOk', 'returnError',
  'returnValue',
]);

const roleSuffixPattern = /(Call|Error|Failed|Failure|Result|Option|Request|Response|Token|Timeout|Deadline|Defer|Group|Policy|Codec|Validator|Mapper|Adapter|Boundary|Resource|Capability|Authority|Channel|Mutex|Lock|Select|Record|Field|Enum|Variant|Value|Counter|Step|Accumulator|Divisor|Remainder|Span|Metric|Trace)$/;

const primitiveTargets = new Map([
  ['console.writeLine', 'puts(text) -> i32. Writes one text line.'],
  ['console.writeIntegerLine', 'printf("%lld\\n", value) -> i32. Writes one integer line.'],
  ['console.writeInteger', 'Alias for console.writeIntegerLine.'],
  ['math.addI64', 'i64 addition. Infallible math target; use bind.'],
  ['math.subtractI64', 'i64 subtraction. Infallible math target; use bind.'],
  ['math.multiplyI64', 'i64 multiplication. Infallible math target; use bind.'],
  ['math.divideI64', 'i64 signed division. Infallible in the current AST model; use bind.'],
  ['math.moduloI64', 'i64 signed remainder. Infallible in the current AST model; use bind.'],
  ['math.equalI64', 'i64 equality comparison returning Bool.'],
  ['math.notEqualI64', 'i64 inequality comparison returning Bool.'],
  ['math.lessThanI64', 'i64 less-than comparison returning Bool.'],
  ['math.lessThanOrEqualI64', 'i64 less-than-or-equal comparison returning Bool.'],
  ['math.greaterThanI64', 'i64 greater-than comparison returning Bool.'],
  ['math.greaterThanOrEqualI64', 'i64 greater-than-or-equal comparison returning Bool.'],
  ['math.checkedMultiplyI64', 'i64 signed multiply with overflow detection. Fallible target; use bindOk, bindError, and branchIfError.'],
  ['math.subI64', 'Alias for math.subtractI64.'],
  ['math.mulI64', 'Alias for math.multiplyI64.'],
  ['math.divI64', 'Alias for math.divideI64.'],
  ['math.modI64', 'Alias for math.moduloI64.'],
  ['math.eqI64', 'Alias for math.equalI64.'],
  ['math.neI64', 'Alias for math.notEqualI64.'],
  ['math.ltI64', 'Alias for math.lessThanI64.'],
  ['math.leI64', 'Alias for math.lessThanOrEqualI64.'],
  ['math.gtI64', 'Alias for math.greaterThanI64.'],
  ['math.geI64', 'Alias for math.greaterThanOrEqualI64.'],
]);

const domainMethods = new Set([
  'add', 'addPositiveStep', 'subtract', 'subtractStep', 'subtractPositiveStep',
  'multiply', 'multiplyByStep', 'multiplyByCounter', 'divide', 'modulo', 'moduloBy',
  'equal', 'notEqual',
  'lessThan', 'lessThanOrEqual', 'greaterThan', 'greaterThanOrEqual',
  'square', 'checkedMultiply', 'checkedMultiplyByCounter', 'checkedMultiplyByStep',
]);

const primitiveTypes = new Map([
  ['I64', '64-bit integer.'],
  ['I32', '32-bit integer.'],
  ['ExitCode', '32-bit process exit code.'],
  ['Bool', 'Boolean value.'],
  ['String', 'Null-terminated UTF-8 string.'],
  ['Void', 'No useful success value. Used with ignoreOk/ignoreValue to make explicit discards visible.'],
  ['DurationMilliseconds', '64-bit duration in milliseconds.'],
  ['MonotonicMilliseconds', '64-bit monotonic timestamp in milliseconds.'],
  ['UtcMilliseconds', '64-bit UTC timestamp in milliseconds.'],
]);

const opaqueInputs = new Set([
  'console', 'process', 'environment', 'httpRequest', 'databaseClient', 'clock',
]);

const verbHoverText = new Map([
  ['project', 'Top-level declaration: project NAME.'],
  ['target', 'Top-level declaration: target NAME.'],
  ['runtime', 'Top-level declaration: runtime NAME VERSION.'],
  ['entry', 'Top-level declaration: entry MODE OPERATION.'],
  ['module', 'Top-level module declaration. Parsed as project context by the current compiler.'],
  ['dependency', 'Dependency declaration. Dependency contract metadata is parsed for tooling context.'],
  ['dependencyEffect', 'Dependency effect declaration.'],
  ['dependencyExports', 'Dependency export declaration.'],
  ['dependencyFunction', 'Dependency function declaration metadata.'],
  ['dependencyFunctionInput', 'Dependency function input metadata.'],
  ['dependencyFunctionOutput', 'Dependency function output metadata.'],
  ['dependencyFunctionEffect', 'Dependency function effect metadata.'],
  ['dependencyFunctionAsync', 'Dependency function async metadata.'],
  ['importModule', 'Import declaration: importModule DOTTED.PATH as ALIAS.'],
  ['type', 'Type alias declaration: type ALIAS UNDERLYING [extra-tokens].'],
  ['typeInvariant', 'Type metadata: typeInvariant TYPE "text". Multi-valued invariant context for a type.'],
  ['typeRepresentation', 'Type metadata: typeRepresentation TYPE UNDERLYING ARGS...'],
  ['typeTrust', 'Type metadata: typeTrust TYPE untrusted|trusted|sanitized|internal|public.'],
  ['typeMemory', 'Type metadata: typeMemory TYPE inline|heap|arena.'],
  ['typeLayout', 'Type metadata: typeLayout TYPE row|column|packed.'],
  ['record', 'Record declaration: record NAME [layout KIND] [align N]. Parsed by the current compiler.'],
  ['field', 'Record field declaration: field RECORD_NAME FIELD_NAME FIELD_TYPE.'],
  ['enum', 'Enum declaration: enum NAME [repr TYPE]. Parsed by the current compiler.'],
  ['enumCase', 'Enum case declaration: enumCase ENUM_NAME CASE_NAME [VALUE].'],
  ['error', 'Error type declaration: error NAME.'],
  ['errorCase', 'Error variant declaration: errorCase ERROR_TYPE VARIANT [CAUSE_TYPE].'],
  ['operation', 'Operation declaration. Header/context lines attach to this operation.'],
  ['webServer', 'Web server declaration: webServer NAME. Parsed as metadata.'],
  ['serverHost', 'Web server metadata: serverHost SERVER_NAME "host".'],
  ['serverPort', 'Web server metadata: serverPort SERVER_NAME PORT.'],
  ['route', 'Web server route: route SERVER METHOD PATH HANDLER_OPERATION.'],
  ['routeTimeout', 'Web server route timeout metadata.'],
  ['routeMiddleware', 'Web server route middleware metadata.'],
  ['jsonCodec', 'Contract-heavy JSON codec declaration.'],
  ['codec', 'Contract-heavy codec declaration.'],
  ['schema', 'Codec schema attachment: schema CODEC_NAME RECORD_NAME.'],
  ['unknownFields', 'Codec unknown-field policy: unknownFields CODEC_NAME reject|keep|ignore.'],
  ['validator', 'Contract-heavy validator declaration.'],
  ['mapper', 'Contract-heavy mapper declaration.'],
  ['adapter', 'Contract-heavy adapter declaration.'],
  ['boundary', 'Contract-heavy boundary declaration.'],
  ['policy', 'Policy declaration. Policies are semantic nodes, not casual helpers.'],
  ['errorPolicy', 'Error policy declaration for mapping failures to domain/public outcomes.'],
  ['retryPolicy', 'Retry policy declaration. Parsed as policy metadata.'],
  ['timeoutBudget', 'Timeout budget declaration. Parsed as policy metadata.'],
  ['resource', 'Resource declaration: resource NAME kind KIND.'],
  ['resourceKey', 'Resource key metadata.'],
  ['resourceValue', 'Resource value metadata.'],
  ['resourceKind', 'Resource kind metadata.'],
  ['capability', 'Capability declaration: capability NAME EFFECT_PATH ACCESS.'],
  ['authority', 'Authority metadata: authority OPERATION EFFECT_PATH ACCESS.'],
  ['mutex', 'Top-level mutex declaration. Parsed as metadata.'],
  ['shared', 'Top-level shared-state declaration. Parsed as metadata.'],
  ['channel', 'Top-level channel declaration. Parsed as metadata.'],
  ['testCovers', 'Top-level coverage metadata: testCovers TEST_NAME TARGET_NAME.'],
  ['input', 'Operation metadata: input OPERATION PARAM_NAME PARAM_TYPE.'],
  ['output', 'Operation metadata: output OPERATION TYPE_EXPR.'],
  ['effect', 'Operation metadata: declares an external effect.'],
  ['memory', 'Operation metadata: declares memory behavior.'],
  ['async', 'Operation metadata: async yes|no.'],
  ['purpose', 'Hard metadata: declares what an operation or abstraction is for.'],
  ['invariant', 'Hard metadata: declares a condition future edits must preserve.'],
  ['warning', 'Hard metadata: declares a hazard future agents must read before editing.'],
  ['failure', 'Hard metadata: declares a named failure and explanation.'],
  ['guarantee', 'Hard metadata: declares a guarantee attached to an operation or abstraction.'],
  ['security', 'Hard metadata: declares security context agents must preserve.'],
  ['timing', 'Hard metadata: declares timing behavior or constraints.'],
  ['observability', 'Hard metadata: declares trace/log/metric context.'],
  ['const', 'Body declaration statement: const NAME TYPE VALUE.'],
  ['var', 'Body declaration statement: var NAME TYPE INITIAL_VALUE.'],
  ['label', 'Control-flow statement: label NAME. Labels are first-class basic blocks.'],
  ['call', 'Call lifecycle statement: call CALL_NAME TARGET_PATH.'],
  ['arg', 'Call lifecycle statement: arg CALL_NAME ARG_NAME VALUE_NAME.'],
  ['timeout', 'Call lifecycle statement: timeout CALL_NAME DURATION_VALUE.'],
  ['cancelOn', 'Call lifecycle statement: cancelOn CALL_NAME CANCELLATION_TOKEN.'],
  ['run', 'Call lifecycle statement: execute call immediately.'],
  ['start', 'Call lifecycle statement: begin async work. Parsed by current compiler.'],
  ['await', 'Call lifecycle statement: wait for started async work. Parsed by current compiler.'],
  ['bind', 'Binding statement for infallible calls: bind VALUE TYPE CALL_NAME.'],
  ['bindOk', 'Binding statement for success leg: bindOk VALUE TYPE CALL_NAME.'],
  ['bindError', 'Binding statement for failure leg: bindError ERROR ERROR_TYPE CALL_NAME. Must pair with branchIfError.'],
  ['ignoreOk', 'Binding statement: ignoreOk CALL_NAME TYPE explicitly discards a fallible call success value.'],
  ['ignoreValue', 'Binding statement: ignoreValue CALL_NAME TYPE explicitly discards an infallible call result.'],
  ['makeError', 'Error construction: makeError NAME ERROR_TYPE.VARIANT [SOURCE_VALUE].'],
  ['new', 'Reserved record I/O statement: new VALUE_NAME RECORD_NAME. Parsed, not lowered by current compiler.'],
  ['fieldGet', 'Reserved record I/O statement: fieldGet OUT_NAME TYPE RECORD_VALUE FIELD_NAME.'],
  ['fieldSet', 'Reserved record I/O statement: fieldSet RECORD_VALUE FIELD_NAME VALUE_NAME.'],
  ['taskGroup', 'Reserved structured-concurrency statement: taskGroup NAME [maxTasks N] [cancelOnFirstError yes|no].'],
  ['startInGroup', 'Reserved structured-concurrency statement: startInGroup CALL_NAME GROUP_NAME.'],
  ['awaitGroup', 'Reserved structured-concurrency statement: awaitGroup GROUP_NAME.'],
  ['bindGroupError', 'Reserved structured-concurrency statement: bindGroupError ERROR TYPE GROUP_NAME.'],
  ['branchIfGroupError', 'Reserved structured-concurrency control statement.'],
  ['defer', 'Reserved cleanup statement: defer NAME TARGET_PATH ARGS...'],
  ['deferLog', 'Reserved cleanup statement that logs cleanup failure.'],
  ['deferAwaitLog', 'Reserved async cleanup statement that awaits and logs cleanup failure.'],
  ['deferWhenExitLog', 'Reserved conditional cleanup statement.'],
  ['send', 'Reserved channel statement: send CHANNEL_NAME VALUE.'],
  ['receive', 'Reserved channel statement: receive OUT_NAME TYPE CHANNEL_NAME.'],
  ['lock', 'Reserved lock statement: lock MUTEX_NAME.'],
  ['unlock', 'Reserved lock statement: unlock MUTEX_NAME.'],
  ['select', 'Reserved select declaration statement.'],
  ['selectCase', 'Reserved select case statement.'],
  ['runSelect', 'Reserved select execution statement.'],
  ['useRetry', 'Reserved policy attachment: useRetry CALL_NAME RETRY_POLICY_NAME.'],
  ['useCapability', 'Reserved policy attachment: useCapability OPERATION_OR_CALL CAPABILITY_NAME.'],
  ['set', 'Mutation statement: set VAR_NAME VALUE_NAME.'],
  ['branch', 'Control-flow statement: branch LABEL_NAME.'],
  ['branchIf', 'Control-flow statement: branchIf BOOL_VALUE LABEL_NAME. False leg falls through.'],
  ['branchIfError', 'Control-flow statement: branchIfError CALL_NAME LABEL_NAME.'],
  ['branchIfChannelClosed', 'Reserved control-flow statement for closed channel branch.'],
  ['branchSelected', 'Reserved control-flow statement for select result branch.'],
  ['returnOk', 'Return success value from Result operation.'],
  ['returnError', 'Return typed error value from Result operation.'],
  ['returnValue', 'Return plain value.'],
]);

const semanticLegend = new vscode.SemanticTokensLegend([
  'agentscriptDeclarationVerb',
  'agentscriptContextVerb',
  'agentscriptActionVerb',
  'agentscriptControlVerb',
  'agentscriptRoleSuffix',
  'agentscriptPrimitiveTarget',
  'agentscriptDomainTarget',
  'agentscriptErrorVariant',
  'agentscriptOpaqueInput',
  'agentscriptDeclaredName',
  'agentscriptConstName',
  'agentscriptMutableName',
  'agentscriptCallObject',
  'agentscriptArgumentName',
  'agentscriptLabelName',
  'agentscriptEffectPath',
  'type',
  'namespace',
  'variable',
  'string',
  'number',
  'comment',
], []);

let activeDecorations = [];
let segmentColoringEnabled = true;
let segmentColorMode = 'background';
let decorationUpdateTimeout = null;
let linterEnabled = true;
let linterRunMode = 'onSave';
let linterPythonPath = 'python';
let linterConfiguredPath = '';
let diagnosticCollection = null;
let lintStatusBarItem = null;
const lintUpdateTimeouts = new Map();
const runningLintProcesses = new Map();

const verbStyles = {
  declaration: { color: '#FF7B72', fontWeight: '600' },
  context: { color: '#7EE787', fontWeight: '600' },
  action: { color: '#DCDCAA', fontWeight: '600' },
  control: { color: '#79C0FF', fontWeight: '600' },
  unknown: {
    color: '#FF6B6B',
    fontWeight: '700',
    textDecoration: 'underline wavy #FF6B6B',
  },
};

const classifyVerb = (verb) => {
  if (declarationVerbs.has(verb)) {
    return 'declaration';
  }

  if (contextVerbs.has(verb)) {
    return 'context';
  }

  if (actionVerbs.has(verb)) {
    return 'action';
  }

  if (controlVerbs.has(verb)) {
    return 'control';
  }

  return 'unknown';
};

const classifyLine = (lineText) => {
  const trimmedLine = lineText.trim();

  if (trimmedLine.length === 0) {
    return null;
  }

  if (trimmedLine.startsWith('#')) {
    return 'comment';
  }

  const verb = trimmedLine.split(/\s+/, 1)[0];
  return classifyVerb(verb);
};

const createDecorationOptions = (backgroundColor, overviewRulerColor) => {
  const options = {
    isWholeLine: true,
  };

  if (segmentColorMode === 'background' || segmentColorMode === 'both') {
    options.backgroundColor = backgroundColor;
  }

  if (segmentColorMode === 'overview' || segmentColorMode === 'both') {
    options.overviewRulerColor = overviewRulerColor;
    options.overviewRulerLane = vscode.OverviewRulerLane.Left;
  }

  return options;
};

const createDecorations = () => ({
  declaration: vscode.window.createTextEditorDecorationType(createDecorationOptions(
    'rgba(197, 134, 192, 0.045)',
    'rgba(197, 134, 192, 0.90)'
  )),
  context: vscode.window.createTextEditorDecorationType(createDecorationOptions(
    'rgba(78, 201, 176, 0.050)',
    'rgba(78, 201, 176, 0.90)'
  )),
  action: vscode.window.createTextEditorDecorationType(createDecorationOptions(
    'rgba(220, 220, 170, 0.040)',
    'rgba(220, 220, 170, 0.90)'
  )),
  control: vscode.window.createTextEditorDecorationType(createDecorationOptions(
    'rgba(86, 156, 214, 0.055)',
    'rgba(86, 156, 214, 0.90)'
  )),
  comment: vscode.window.createTextEditorDecorationType(createDecorationOptions(
    'rgba(106, 153, 85, 0.040)',
    'rgba(106, 153, 85, 0.80)'
  )),
  unknown: vscode.window.createTextEditorDecorationType(createDecorationOptions(
    'rgba(244, 71, 71, 0.095)',
    'rgba(244, 71, 71, 0.90)'
  )),
});

let decorations = createDecorations();

const createVerbDecorations = () => ({
  declaration: vscode.window.createTextEditorDecorationType(verbStyles.declaration),
  context: vscode.window.createTextEditorDecorationType(verbStyles.context),
  action: vscode.window.createTextEditorDecorationType(verbStyles.action),
  control: vscode.window.createTextEditorDecorationType(verbStyles.control),
  unknown: vscode.window.createTextEditorDecorationType(verbStyles.unknown),
});

let verbDecorations = createVerbDecorations();

const disposeDecorations = () => {
  Object.keys(decorations).forEach((key) => {
    decorations[key].dispose();
  });

  Object.keys(verbDecorations).forEach((key) => {
    verbDecorations[key].dispose();
  });
};

const clearDecorations = (editor) => {
  Object.keys(decorations).forEach((key) => {
    editor.setDecorations(decorations[key], []);
  });

  Object.keys(verbDecorations).forEach((key) => {
    editor.setDecorations(verbDecorations[key], []);
  });
};

const updateSegmentDecorations = (editor) => {
  if (!editor || editor.document.languageId !== 'agentscript') {
    return;
  }

  if (!segmentColoringEnabled) {
    clearDecorations(editor);
    return;
  }

  const rangesByKind = {
    declaration: [],
    context: [],
    action: [],
    control: [],
    comment: [],
    unknown: [],
  };
  const verbRangesByKind = {
    declaration: [],
    context: [],
    action: [],
    control: [],
    unknown: [],
  };

  for (let lineIndex = 0; lineIndex < editor.document.lineCount; lineIndex += 1) {
    const line = editor.document.lineAt(lineIndex);
    const kind = classifyLine(line.text);

    if (!kind || !rangesByKind[kind]) {
      continue;
    }

    rangesByKind[kind].push(line.range);

    if (kind !== 'comment') {
      const verbStart = line.firstNonWhitespaceCharacterIndex;
      const verbText = line.text.slice(verbStart).split(/\s+/, 1)[0];

      if (verbText && verbRangesByKind[kind]) {
        verbRangesByKind[kind].push(new vscode.Range(
          lineIndex,
          verbStart,
          lineIndex,
          verbStart + verbText.length
        ));
      }
    }
  }

  Object.keys(rangesByKind).forEach((kind) => {
    editor.setDecorations(decorations[kind], rangesByKind[kind]);
  });

  Object.keys(verbRangesByKind).forEach((kind) => {
    editor.setDecorations(verbDecorations[kind], verbRangesByKind[kind]);
  });
};

const scheduleDecorationUpdate = (editor) => {
  if (decorationUpdateTimeout) {
    clearTimeout(decorationUpdateTimeout);
  }

  decorationUpdateTimeout = setTimeout(() => {
    updateSegmentDecorations(editor || vscode.window.activeTextEditor);
  }, 75);
};

const tokenizeLine = (lineText) => {
  const tokens = [];
  const tokenPattern = /"([^"\\]|\\.)*"|#.*$|\S+/g;
  let match;

  while ((match = tokenPattern.exec(lineText)) !== null) {
    tokens.push({
      text: match[0],
      start: match.index,
      length: match[0].length,
    });
  }

  return tokens;
};

const isDomainTarget = (text) => {
  const parts = text.split('.');
  return parts.length === 2
    && /^[A-Z][A-Za-z0-9_]*$/.test(parts[0])
    && domainMethods.has(parts[1]);
};

const operationReferenceVerbs = new Set([
  'input', 'output', 'effect', 'memory', 'async', 'purpose', 'invariant',
  'warning', 'failure', 'guarantee', 'security', 'timing', 'observability',
  'authority',
]);

const namedDeclarationVerbs = new Set([
  'project', 'operation', 'webServer', 'record', 'enum', 'error', 'codec',
  'jsonCodec', 'validator', 'mapper', 'adapter', 'boundary', 'policy',
  'errorPolicy', 'retryPolicy', 'timeoutBudget', 'resource', 'capability',
  'mutex', 'shared', 'channel',
]);

const singleCallReferenceVerbs = new Set([
  'run', 'start', 'await', 'timeout', 'cancelOn', 'ignoreOk', 'ignoreValue',
  'useRetry',
]);

const branchLabelPositions = new Map([
  ['branch', 1],
  ['branchIf', 2],
  ['branchIfError', 2],
  ['branchIfGroupError', 2],
  ['branchIfChannelClosed', 2],
  ['branchSelected', 3],
]);

const isLowerQualifiedName = (text) => /^[a-z][A-Za-z0-9_]*(?:\.[a-zA-Z_][A-Za-z0-9_]*)+$/.test(text);

const contextTokenTypeForSymbol = (text, index, tokens) => {
  const verb = tokens && tokens[0] ? tokens[0].text : '';

  if (index === 0) {
    return null;
  }

  if (verb === 'const' && index === 1) {
    return 'agentscriptConstName';
  }

  if (verb === 'var' && index === 1) {
    return 'agentscriptMutableName';
  }

  if (verb === 'set' && index === 1) {
    return 'agentscriptMutableName';
  }

  if (verb === 'label' && index === 1) {
    return 'agentscriptLabelName';
  }

  if (branchLabelPositions.get(verb) === index) {
    return 'agentscriptLabelName';
  }

  if (verb === 'call' && index === 1) {
    return 'agentscriptCallObject';
  }

  if (verb === 'arg' && index === 1) {
    return 'agentscriptCallObject';
  }

  if (verb === 'arg' && index === 2) {
    return 'agentscriptArgumentName';
  }

  if (singleCallReferenceVerbs.has(verb) && index === 1) {
    return 'agentscriptCallObject';
  }

  if ((verb === 'bind' || verb === 'bindOk' || verb === 'bindError') && index === 3) {
    return 'agentscriptCallObject';
  }

  if (verb === 'makeError' && index === 1) {
    return 'agentscriptMutableName';
  }

  if (namedDeclarationVerbs.has(verb) && index === 1) {
    return 'agentscriptDeclaredName';
  }

  if (operationReferenceVerbs.has(verb) && index === 1) {
    return 'agentscriptDeclaredName';
  }

  if ((verb === 'effect' || verb === 'dependencyEffect') && index >= 2 && isLowerQualifiedName(text)) {
    return 'agentscriptEffectPath';
  }

  if ((verb === 'capability' || verb === 'authority') && index === 2 && isLowerQualifiedName(text)) {
    return 'agentscriptEffectPath';
  }

  return null;
};

const domainTargetHoverText = (text) => {
  const methodName = text.split('.')[1];

  if (methodName && methodName.startsWith('checkedMultiply')) {
    return 'AST.md: checked domain multiply lowers to `math.checkedMultiplyI64`; it is fallible and should use `bindOk`, `bindError`, and `branchIfError`.';
  }

  if (methodName === 'square') {
    return 'AST.md: domain `square` is a semantic method for multiplying a value by itself while keeping the source domain context visible.';
  }

  return 'AST.md: `TypeName.methodName` lowers to an underlying primitive based on the alias type while preserving domain context in source.';
};

const tokenTypeForSymbol = (text, index, tokens) => {
  if (index === 0) {
    const classification = classifyVerb(text);

    if (classification === 'declaration') {
      return 'agentscriptDeclarationVerb';
    }

    if (classification === 'context') {
      return 'agentscriptContextVerb';
    }

    if (classification === 'action') {
      return 'agentscriptActionVerb';
    }

    if (classification === 'control') {
      return 'agentscriptControlVerb';
    }
  }

  if (text.startsWith('#')) {
    return 'comment';
  }

  if (text.startsWith('"')) {
    return 'string';
  }

  if (/^-?\d+$/.test(text)) {
    return 'number';
  }

  const contextTokenType = contextTokenTypeForSymbol(text, index, tokens);

  if (contextTokenType) {
    return contextTokenType;
  }

  if (opaqueInputs.has(text)) {
    return 'agentscriptOpaqueInput';
  }

  if (primitiveTargets.has(text)) {
    return 'agentscriptPrimitiveTarget';
  }

  if (isDomainTarget(text)) {
    return 'agentscriptDomainTarget';
  }

  if (/^[A-Z][A-Za-z0-9_]*\.[A-Z][A-Za-z0-9_]*$/.test(text)) {
    return 'agentscriptErrorVariant';
  }

  if (tokens && tokens[0] && tokens[0].text === 'call' && index === 2) {
    return 'namespace';
  }

  if (/^[A-Z][A-Za-z0-9_]*$/.test(text)) {
    return 'type';
  }

  if (/^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+$/.test(text)) {
    return 'namespace';
  }

  if (/^[a-z][A-Za-z0-9_]*$/.test(text)) {
    return 'variable';
  }

  return null;
};

const provideDocumentSemanticTokens = (document) => {
  const builder = new vscode.SemanticTokensBuilder(semanticLegend);

  for (let lineIndex = 0; lineIndex < document.lineCount; lineIndex += 1) {
    const lineText = document.lineAt(lineIndex).text;
    const tokens = tokenizeLine(lineText);

    tokens.forEach((token, tokenIndex) => {
      const contextTokenType = contextTokenTypeForSymbol(token.text, tokenIndex, tokens);
      const suffixMatch = token.text.match(roleSuffixPattern);

      if (tokenIndex > 0 && suffixMatch && /^[a-z][A-Za-z0-9_]*$/.test(token.text)) {
        const suffixStart = token.start + token.text.length - suffixMatch[0].length;

        if (suffixStart > token.start) {
          builder.push(lineIndex, token.start, suffixStart - token.start, contextTokenType || 'variable', []);
        }

        builder.push(lineIndex, suffixStart, suffixMatch[0].length, 'agentscriptRoleSuffix', []);
        return;
      }

      const tokenType = tokenTypeForSymbol(token.text, tokenIndex, tokens);

      if (tokenType) {
        builder.push(lineIndex, token.start, token.length, tokenType, []);
      }
    });
  }

  return builder.build();
};

const registerSemanticTokens = (context) => {
  const provider = {
    provideDocumentSemanticTokens,
  };

  context.subscriptions.push(
    vscode.languages.registerDocumentSemanticTokensProvider(
      { language: 'agentscript' },
      provider,
      semanticLegend
    )
  );
};

const getTokenAtPosition = (document, position) => {
  const lineText = document.lineAt(position.line).text;
  const tokens = tokenizeLine(lineText);

  for (let index = 0; index < tokens.length; index += 1) {
    const token = tokens[index];
    const tokenEnd = token.start + token.length;

    if (position.character >= token.start && position.character <= tokenEnd) {
      return {
        token,
        tokenIndex: index,
        tokens,
      };
    }
  }

  return null;
};

const markdownHover = (title, body) => {
  const markdown = new vscode.MarkdownString();
  markdown.appendMarkdown(`**${title}**\n\n`);
  markdown.appendMarkdown(body);
  return new vscode.Hover(markdown);
};

const roleSuffixHover = (token, character) => {
  const suffixMatch = token.text.match(roleSuffixPattern);

  if (!suffixMatch) {
    return null;
  }

  const suffix = suffixMatch[0];
  const suffixStart = token.start + token.text.length - suffix.length;

  if (character < suffixStart) {
    return null;
  }

  return markdownHover(
    `Role suffix: ${suffix}`,
    'AgentScript role suffixes are context markers. They tell agents and tools what semantic kind a symbol represents.'
  );
};

const provideHover = (document, position) => {
  const found = getTokenAtPosition(document, position);

  if (!found) {
    return null;
  }

  const { token, tokenIndex, tokens } = found;
  const text = token.text;

  const suffixHover = roleSuffixHover(token, position.character);

  if (suffixHover && tokenIndex > 0) {
    return suffixHover;
  }

  if (tokenIndex === 0 && verbHoverText.has(text)) {
    return markdownHover(`AST verb: ${text}`, verbHoverText.get(text));
  }

  if (primitiveTargets.has(text)) {
    return markdownHover(`Primitive call target: ${text}`, primitiveTargets.get(text));
  }

  if (isDomainTarget(text)) {
    return markdownHover(
      `Domain-typed method: ${text}`,
      domainTargetHoverText(text)
    );
  }

  if (/^[A-Z][A-Za-z0-9_]*\.[A-Z][A-Za-z0-9_]*$/.test(text)) {
    return markdownHover(
      `Error variant: ${text}`,
      '`makeError NAME ErrorType.Variant [source]` creates a typed error value for `returnError`.'
    );
  }

  if (primitiveTypes.has(text)) {
    return markdownHover(`Primitive type: ${text}`, primitiveTypes.get(text));
  }

  if (opaqueInputs.has(text)) {
    return markdownHover(
      `Opaque input: ${text}`,
      'AST.md: opaque dependency inputs may appear in `arg` lines to preserve dependency context, but they do not flow into computation.'
    );
  }

  if (tokens[0] && tokens[0].text === 'call' && tokenIndex === 1) {
    return markdownHover(
      `Call object: ${text}`,
      'A call object is a named semantic node. Related `arg`, `run`, `bind*`, `ignoreOk`, `ignoreValue`, and `branchIfError` lines should reference this name.'
    );
  }

  return null;
};

const registerHovers = (context) => {
  context.subscriptions.push(
    vscode.languages.registerHoverProvider(
      { language: 'agentscript' },
      { provideHover }
    )
  );
};

const syncConfiguration = () => {
  const segmentConfig = vscode.workspace.getConfiguration('agentScript.segmentColors');
  segmentColoringEnabled = segmentConfig.get('enabled', true);
  segmentColorMode = segmentConfig.get('colorMode', 'background');

  const linterConfig = vscode.workspace.getConfiguration('agentScript.linter');
  linterEnabled = linterConfig.get('enabled', true);
  linterRunMode = linterConfig.get('run', 'onSave');
  linterPythonPath = linterConfig.get('pythonPath', 'python');
  linterConfiguredPath = linterConfig.get('path', '');
};

const isAgentScriptDocument = (document) => (
  document && document.languageId === 'agentscript' && document.uri.scheme === 'file'
);

const candidateLinterPaths = (document) => {
  const candidates = [];
  const workspaceFolder = document ? vscode.workspace.getWorkspaceFolder(document.uri) : null;
  const addAncestorCandidates = (startPath) => {
    let currentPath = path.resolve(startPath);
    const rootPath = path.parse(currentPath).root;

    while (currentPath && currentPath !== rootPath) {
      candidates.push(path.join(currentPath, 'AgentScript', 'linter', 'aslint.py'));
      candidates.push(path.join(currentPath, 'linter', 'aslint.py'));
      currentPath = path.dirname(currentPath);
    }
  };

  if (linterConfiguredPath) {
    if (path.isAbsolute(linterConfiguredPath)) {
      candidates.push(linterConfiguredPath);
    } else if (workspaceFolder) {
      candidates.push(path.join(workspaceFolder.uri.fsPath, linterConfiguredPath));
    }
  }

  const workspaceFolders = vscode.workspace.workspaceFolders || [];
  workspaceFolders.forEach((folder) => {
    candidates.push(path.join(folder.uri.fsPath, 'AgentScript', 'linter', 'aslint.py'));
    candidates.push(path.join(folder.uri.fsPath, 'linter', 'aslint.py'));
    candidates.push(path.join(folder.uri.fsPath, '..', 'AgentScript', 'linter', 'aslint.py'));
    addAncestorCandidates(folder.uri.fsPath);
  });

  if (document && document.fileName) {
    addAncestorCandidates(path.dirname(document.fileName));
  }

  candidates.push(path.join(__dirname, 'tools', 'aslint.py'));

  return candidates;
};

const findLinterPath = (document) => {
  const seen = new Set();
  const candidates = candidateLinterPaths(document);

  for (const candidate of candidates) {
    const normalized = path.normalize(candidate);

    if (seen.has(normalized)) {
      continue;
    }

    seen.add(normalized);

    if (fs.existsSync(normalized)) {
      return normalized;
    }
  }

  return null;
};

const severityFromLinter = (severity) => {
  if (severity === 'error') {
    return vscode.DiagnosticSeverity.Error;
  }

  if (severity === 'warning') {
    return vscode.DiagnosticSeverity.Warning;
  }

  return vscode.DiagnosticSeverity.Information;
};

const diagnosticRange = (document, lineNumber, columnNumber) => {
  const lineIndex = Math.max(0, Math.min(document.lineCount - 1, (lineNumber || 1) - 1));
  const line = document.lineAt(lineIndex);
  const startCharacter = Math.max(0, Math.min(line.text.length, (columnNumber || 1) - 1));
  const wordRange = document.getWordRangeAtPosition(new vscode.Position(lineIndex, startCharacter));

  if (wordRange) {
    return wordRange;
  }

  return new vscode.Range(
    lineIndex,
    startCharacter,
    lineIndex,
    Math.min(line.text.length, startCharacter + 1)
  );
};

const parseLinterDiagnostics = (document, stdout) => {
  let records;

  try {
    records = JSON.parse(stdout || '[]');
  } catch (_error) {
    return [
      new vscode.Diagnostic(
        new vscode.Range(0, 0, 0, Math.max(1, document.lineAt(0).text.length)),
        'aslint returned invalid JSON diagnostics.',
        vscode.DiagnosticSeverity.Error
      ),
    ];
  }

  if (!Array.isArray(records)) {
    return [];
  }

  return records.map((record) => {
    const diagnostic = new vscode.Diagnostic(
      diagnosticRange(document, record.line, record.column),
      record.message || String(record.rule || 'AgentScript lint diagnostic'),
      severityFromLinter(record.severity)
    );
    diagnostic.source = 'aslint';
    diagnostic.code = record.rule || undefined;
    return diagnostic;
  });
};

const setLinterStatus = (text, tooltip) => {
  if (!lintStatusBarItem) {
    return;
  }

  lintStatusBarItem.text = text;
  lintStatusBarItem.tooltip = tooltip || '';
  lintStatusBarItem.show();
};

const clearLinterStatusLater = () => {
  if (!lintStatusBarItem) {
    return;
  }

  setTimeout(() => {
    if (lintStatusBarItem) {
      lintStatusBarItem.hide();
    }
  }, 2500);
};

const runLinterForDocument = (document, showMissingLinterMessage = false) => {
  if (!diagnosticCollection || !isAgentScriptDocument(document)) {
    return;
  }

  if (!linterEnabled) {
    diagnosticCollection.delete(document.uri);
    return;
  }

  const linterPath = findLinterPath(document);

  if (!linterPath) {
    diagnosticCollection.delete(document.uri);

    if (showMissingLinterMessage) {
      vscode.window.showWarningMessage(
        'AgentScript linter not found. Set agentScript.linter.path or open the AgentScript repo root.'
      );
    }

    return;
  }

  const documentKey = document.uri.toString();
  const existingProcess = runningLintProcesses.get(documentKey);

  if (existingProcess) {
    existingProcess.kill();
  }

  setLinterStatus('$(sync~spin) AgentScript lint', document.fileName);

  const lintProcess = childProcess.spawn(
    linterPythonPath,
    [linterPath, document.fileName, '--format', 'json', '--fail-on', 'none'],
    {
      cwd: vscode.workspace.getWorkspaceFolder(document.uri)?.uri.fsPath || path.dirname(document.fileName),
      windowsHide: true,
    }
  );

  runningLintProcesses.set(documentKey, lintProcess);

  let stdout = '';
  let stderr = '';

  lintProcess.stdout.on('data', (chunk) => {
    stdout += chunk.toString();
  });

  lintProcess.stderr.on('data', (chunk) => {
    stderr += chunk.toString();
  });

  lintProcess.on('error', (error) => {
    runningLintProcesses.delete(documentKey);
    diagnosticCollection.set(document.uri, [
      new vscode.Diagnostic(
        new vscode.Range(0, 0, 0, Math.max(1, document.lineAt(0).text.length)),
        `Failed to run aslint with ${linterPythonPath}: ${error.message}`,
        vscode.DiagnosticSeverity.Error
      ),
    ]);
    setLinterStatus('$(error) AgentScript lint failed', error.message);
    clearLinterStatusLater();
  });

  lintProcess.on('close', () => {
    if (runningLintProcesses.get(documentKey) !== lintProcess) {
      return;
    }

    runningLintProcesses.delete(documentKey);

    if (stderr.trim() && !stdout.trim()) {
      diagnosticCollection.set(document.uri, [
        new vscode.Diagnostic(
          new vscode.Range(0, 0, 0, Math.max(1, document.lineAt(0).text.length)),
          stderr.trim(),
          vscode.DiagnosticSeverity.Error
        ),
      ]);
      setLinterStatus('$(error) AgentScript lint failed', stderr.trim());
      clearLinterStatusLater();
      return;
    }

    const diagnostics = parseLinterDiagnostics(document, stdout);
    diagnosticCollection.set(document.uri, diagnostics);

    if (diagnostics.length > 0) {
      setLinterStatus(`$(warning) AgentScript lint ${diagnostics.length}`, `${diagnostics.length} diagnostic(s)`);
    } else {
      setLinterStatus('$(check) AgentScript lint clean', document.fileName);
    }

    clearLinterStatusLater();
  });
};

const scheduleLinterRun = (document, delayMilliseconds = 350) => {
  if (!isAgentScriptDocument(document)) {
    return;
  }

  const key = document.uri.toString();
  const existingTimeout = lintUpdateTimeouts.get(key);

  if (existingTimeout) {
    clearTimeout(existingTimeout);
  }

  lintUpdateTimeouts.set(key, setTimeout(() => {
    lintUpdateTimeouts.delete(key);
    runLinterForDocument(document);
  }, delayMilliseconds));
};

const registerLinter = (context) => {
  diagnosticCollection = vscode.languages.createDiagnosticCollection('aslint');
  lintStatusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
  lintStatusBarItem.command = 'agentscript.runLinter';

  context.subscriptions.push(diagnosticCollection, lintStatusBarItem);

  context.subscriptions.push(
    vscode.commands.registerCommand('agentscript.runLinter', () => {
      const editor = vscode.window.activeTextEditor;

      if (!editor || !isAgentScriptDocument(editor.document)) {
        vscode.window.showInformationMessage('Open an AgentScript file to run the linter.');
        return;
      }

      runLinterForDocument(editor.document, true);
    })
  );

  context.subscriptions.push(
    vscode.workspace.onDidSaveTextDocument((document) => {
      if (linterRunMode === 'onSave') {
        runLinterForDocument(document);
      }
    })
  );

  context.subscriptions.push(
    vscode.workspace.onDidOpenTextDocument((document) => {
      if (linterRunMode !== 'manual') {
        scheduleLinterRun(document, 100);
      }
    })
  );

  context.subscriptions.push(
    vscode.workspace.onDidCloseTextDocument((document) => {
      diagnosticCollection.delete(document.uri);
      const key = document.uri.toString();
      const existingTimeout = lintUpdateTimeouts.get(key);

      if (existingTimeout) {
        clearTimeout(existingTimeout);
        lintUpdateTimeouts.delete(key);
      }
    })
  );

  vscode.workspace.textDocuments.forEach((document) => {
    if (linterRunMode !== 'manual') {
      scheduleLinterRun(document, 100);
    }
  });
};

const activate = (context) => {
  syncConfiguration();
  disposeDecorations();
  decorations = createDecorations();
  verbDecorations = createVerbDecorations();
  registerSemanticTokens(context);
  registerHovers(context);
  registerLinter(context);

  context.subscriptions.push({
    dispose: disposeDecorations,
  });

  context.subscriptions.push(
    vscode.commands.registerCommand('agentscript.toggleSegmentColors', () => {
      segmentColoringEnabled = !segmentColoringEnabled;
      vscode.window.visibleTextEditors.forEach(updateSegmentDecorations);
      vscode.window.showInformationMessage(`AgentScript segment colors ${segmentColoringEnabled ? 'enabled' : 'disabled'}.`);
    })
  );

  context.subscriptions.push(
    vscode.window.onDidChangeActiveTextEditor((editor) => {
      scheduleDecorationUpdate(editor);
    })
  );

  context.subscriptions.push(
    vscode.workspace.onDidChangeTextDocument((event) => {
      const editor = vscode.window.visibleTextEditors.find((candidate) => (
        candidate.document === event.document
      ));
      scheduleDecorationUpdate(editor);

      if (linterRunMode === 'onType') {
        scheduleLinterRun(event.document);
      }
    })
  );

  context.subscriptions.push(
    vscode.workspace.onDidChangeConfiguration((event) => {
      if (event.affectsConfiguration('agentScript.segmentColors') || event.affectsConfiguration('agentScript.linter')) {
        disposeDecorations();
        syncConfiguration();
        decorations = createDecorations();
        verbDecorations = createVerbDecorations();
        vscode.window.visibleTextEditors.forEach(updateSegmentDecorations);

        if (!linterEnabled && diagnosticCollection) {
          diagnosticCollection.clear();
        } else if (linterRunMode !== 'manual') {
          vscode.workspace.textDocuments.forEach((document) => scheduleLinterRun(document, 100));
        }
      }
    })
  );

  vscode.window.visibleTextEditors.forEach(updateSegmentDecorations);
};

const deactivate = () => {
  activeDecorations.forEach((decoration) => decoration.dispose());
  activeDecorations = [];
  runningLintProcesses.forEach((lintProcess) => lintProcess.kill());
  runningLintProcesses.clear();
  lintUpdateTimeouts.forEach((timeoutHandle) => clearTimeout(timeoutHandle));
  lintUpdateTimeouts.clear();
  disposeDecorations();
};

module.exports = {
  activate,
  deactivate,
};

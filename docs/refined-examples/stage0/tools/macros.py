"""DSL macros and generated tests shared by the stage0 modules."""
from semgen import Generator, q


def front(sfx, source, fail, stage="model", prefix=""):
    """Lex, group, and model a source held in let `source` into values suffixed with sfx. stage: rows | model |
    modelCatch (the model call's error is caught as model<sfx>Error, for the caller to branch on)."""
    p = prefix
    lines = [
        f"lex{sfx}: tokens{sfx} = lexer.tokenize({source}, store) ? {fail}",
        f"newWords{sfx}: words{sfx} = syntax.Words.new(store)",
        f"newRows{sfx}: rows{sfx} = syntax.Rows.new(store)",
        f"group{sfx}: syntax.groupRows({source}, tokens{sfx}, words{sfx}, rows{sfx}) ? {fail}",
    ]
    if stage == "rows":
        return lines
    lines += [
        f"newEntities{sfx}: entities{sfx} = {p}Entities.new(store)",
        f"newNames{sfx}: names{sfx} = {p}EntityNames.new(store)",
    ]
    if stage == "model":
        lines.append(f"model{sfx}: {p}buildModel({source}, words{sfx}, rows{sfx}, entities{sfx}, names{sfx}) ? {fail}")
    else:
        lines.append(f"model{sfx}: {p}buildModel({source}, words{sfx}, rows{sfx}, entities{sfx}, names{sfx}) "
                     f"! rejection{sfx}")
        lines.append(f"iferr model{sfx} rejected{sfx} {fail}")
    return lines


Generator.macros["front"] = front


def reject_test(name, purpose, verifies, cases, runner):
    """A test that runs each (source, expected) case through `runner(sfx)` (DSL lines ending in a step that
    catches the rejection as rejection<sfx> and branches to rejected<sfx> on error, else to refused), then compares
    the diagnostic with the expected text."""
    out = [f"test {name} {q(purpose)}"]
    out += [f"  verifies {a} {b}" for a, b in verifies]
    out.append("  region store 4194304")
    for i, (src, exp) in enumerate(cases):
        out.append(f"  let source{i} String {q(src)}")
        out.append(f"  let expected{i} String {q(exp)}")
    out.append("  let refusedText String \"the front end refused the source or a step failed\"")
    out.append(":begin")
    for i, (src, exp) in enumerate(cases):
        if i > 0:
            out.append(f":case{i}")
        out += ["  " + ln for ln in runner(i)]
        out.append(f":rejected{i}")
        out.append(f"  describe{i}: described{i} = syntax.diagnostic(source{i}, rejection{i}, store)")
        out.append(f"  expect{i}: test.assertEqualString(expected{i}, described{i})")
        out.append(f"  goto {'case' + str(i + 1) if i + 1 < len(cases) else 'finished'}")
    out.append(":finished")
    out.append("  return")
    out.append(":refused")
    out.append("  failRefused: test.fail(refusedText)")
    out.append("  return")
    return "\n".join(out) + "\n"


def expect_entity(name, key, kind, first, count):
    return [
        f"find{name}: {name}Position = EntityNames.get(namesX, {name}Name=\"{key}\") ? refused",
        f"read{name}: {name}Entity = Entities.getOrTrap(entitiesX, {name}Position)",
        f"kindOf{name}: {name}Kind = Entity.kind({name}Entity)",
        f"expectKind{name}: test.assertEqualInt64({name}KindExpected={kind}, {name}Kind)",
        f"firstOf{name}: {name}First = Entity.first({name}Entity)",
        f"expectFirst{name}: test.assertEqualInt64({name}FirstExpected={first}, {name}First)",
        f"countOf{name}: {name}Count = Entity.count({name}Entity)",
        f"expectCount{name}: test.assertEqualInt64({name}CountExpected={count}, {name}Count)",
    ]


Generator.macros["expectEntity"] = expect_entity


def cap(s):
    return s[:1].upper() + s[1:]


def view(name, word, fail):
    """A view of the source text a word covers, in value `name`; a word outside the source jumps to `fail`."""
    n = cap(name)
    return [
        f"read{n}Start: {name}Start = syntax.Word.start({word})",
        f"read{n}Offset: {name}Offset = string.Position.offset({name}Start)",
        f"read{n}Length: {name}Length = syntax.Word.length({word})",
        f"cut{n}: {name} = string.slice(source, {name}Offset, {name}Length) ? {fail}",
    ]


def rows_begin():
    """Walk the rows of `entity` after its `is` row: `row`, `predicateWord`, and `predicate` for each, then a match
    on the predicate (the caller writes its cases); `:finish` follows the last row."""
    return [
        "let rowIndex Int64 0 mut",
        "readEntityFirst: entityFirst = model.Entity.first(entity)",
        "readEntityCount: entityCount = model.Entity.count(entity)",
        "findEnd: entityEnd = math.addInt64(entityFirst, entityCount)",
        "findStart: rowStart = math.addInt64(entityFirst, 1)",
        "set rowIndex rowStart",
        "goto eachRow",
        ":eachRow loop=while max=entityCount",
        "endCheck: rowsDone = compare.greaterOrEqualInt64(rowIndex, entityEnd)",
        "if rowsDone finish readRow",
        ":readRow in=eachRow",
        "fetchRow: row = syntax.Rows.getOrTrap(rows, rowIndex)",
        "readPredicateWord: predicateWord = wordAt(words, row, 1)",
        "findPredicate: predicate = lookupPredicate(source, predicateWord) ?^",
        "match predicate",
    ]


def rows_next(refuse="refuse"):
    out = [
        ":nextRow in=eachRow",
        "advanceRow: nextIndex = math.addInt64(rowIndex, 1)",
        "set rowIndex nextIndex",
        "goto eachRow",
    ]
    if refuse == "refuse":
        out += [
            ":refuse",
            "makeRefused: refusedError = syntax.Rejection.unsupportedPredicate(predicateWord)",
            "raise refusedError",
        ]
    return out


def word_at(name, offset):
    return [f"read{cap(name)}: {name} = wordAt(words, row, {offset})"]


def reject(variant, word, label=None):
    """A block that raises Rejection.<variant> at a word."""
    label = label or variant
    return [f":{label}", f"make{cap(label)}: {label}Error = syntax.Rejection.{variant}({word})", f"raise {label}Error"]


def put_text(name, literal=None):
    """Append text to `buffer`: a named literal (`@s name "text"`) or an existing String value (`@s name`)."""
    if literal is None:
        return [f"buffer.appendString(buffer, {name})"]
    return [f"buffer.appendString(buffer, {name}={literal})"]


def put_word(word, prefix=None):
    """Append a word's source text to `buffer`, after a prefix let (`@w word valuePrefix`)."""
    out = []
    if prefix is not None:
        out.append(f"buffer.appendString(buffer, {prefix})")
    out.append(f"syntax.putWord(buffer, source, {word})")
    return out


def put_value(word):
    return ['buffer.appendString(buffer, valuePrefix="v_")', f"syntax.putWord(buffer, source, {word})"]


Generator.macros["s"] = put_text
Generator.macros["w"] = put_word
Generator.macros["v"] = put_value
Generator.macros["view"] = view
Generator.macros["rowsBegin"] = rows_begin
Generator.macros["rowsNext"] = rows_next
Generator.macros["wordAt"] = word_at
Generator.macros["reject"] = reject

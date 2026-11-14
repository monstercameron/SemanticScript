"""Generate stage0's model, subset, and emitc modules (and the Rejection parts of syntax) from the DSL files."""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import semgen  # noqa: E402
from semgen import Program, Generator, Module, q  # noqa: E402
import macros  # noqa: E402

STAGE0 = os.path.join(semgen.WT, "docs", "refined-examples", "stage0")

REJECTIONS = [
    ("strayMark", "this mark is not part of a word"),
    ("gluedWords", "words are separated by spaces"),
    ("danglingDot", "a dotted name ends with a dot"),
    ("shortRow", "a row has a subject, a predicate, and a payload"),
    ("outsideSource", "a word lies outside the source"),
    ("unsupportedKind", "this entity kind is outside the stage0 subset"),
    ("strayRow", "this row's subject is not the entity above it"),
    ("duplicateName", "this name is already declared"),
    ("badMain", "main takes no input, gives an ExitCode, and raises nothing"),
    ("noMain", "the module has no main operation"),
    ("unsupportedPredicate", "this predicate is outside the stage0 subset here"),
    ("unsupportedPayload", "this payload is outside the stage0 subset"),
    ("unsupportedType", "this type is outside the stage0 subset"),
    ("badLiteral", "this literal does not fit its type"),
    ("unsupportedEscape", "stage0 does not read \\x escapes in text"),
    ("unknownValue", "no value has this name"),
    ("wrongType", "this value has another type"),
    ("unsupportedTarget", "this call target is outside the stage0 subset"),
    ("wrongArgument", "this argument does not match the target's slot, type, or mode"),
    ("argumentCount", "the call passes the wrong number of arguments"),
    ("unknownLabel", "no label has this name"),
    ("unknownCall", "no call in this operation has this name"),
    ("unsupportedStep", "this step is outside the stage0 subset"),
    ("notMutable", "this value is immutable"),
    ("splitBlock", "this label's steps are not together"),
    ("unsupportedLoop", "stage0 compiles forEach loops over lists only"),
    ("notFailing", "this call cannot fail, so there is no error to branch on"),
    ("lostName", "stage0 lost track of a name it had checked; this is a fault in stage0"),
    ("typeOrder", "a record or enum holds only types declared above it"),
    ("unknownVariant", "this variant is not one of the matched enum's"),
    ("unknownOwner", "no operation of this module has this name"),
    ("invalidCharacter", "no word begins with this character"),
    ("unterminatedText", "quoted text is not closed before the end of its line"),
    ("integerTooLarge", "this integer is too large for Int64"),
    ("notModule", "a module's file begins with its `<name> is module` entity"),
    ("badProject", "build.sem names its modules with `includesModule` and its entry as `<module>.main`"),
]


def split_entities(text):
    """(comment+entity chunks) of a formatted .sem file: header comment first, then each entity with the comment
    lines directly above it."""
    blocks = text.strip("\n").split("\n\n")
    return blocks


def entity_name(block):
    for ln in block.split("\n"):
        t = ln.split()
        if len(t) >= 3 and t[1] == "is" and not ln.startswith("#"):
            return t[0], t[2]
    return None, None


def regenerate_syntax(path):
    """Replace Rejection, rejectionWord, and rejectionMessage in syntax.sem."""
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    blocks = split_entities(text)
    rej = ["Rejection is enum", 'Rejection purpose "Why stage0 refuses a source, with the word the diagnostic points at"',
           "Rejection typeParameter none"] + [f"Rejection variant {n} Word" for n, _m in REJECTIONS]
    word = ["rejectionWord is operation", 'rejectionWord purpose "Read the word a rejection points at"',
            'rejectionWord invariant givesWord "Gives the word every variant of a rejection carries"',
            "rejectionWord typeParameter none",
            "rejectionWord input rejection Rejection copied", "rejectionWord output Word",
            "rejectionWord outputOwnedBy none", "rejectionWord raises none", "rejectionWord effect none",
            "rejectionWord uses none", "rejectionWord memoryHeap false", "rejectionWord async false",
            "rejectionWord maxRecursion none", "rejectionWord label begin loopKind none",
            "rejectionWord label begin within none"]
    for n, _m in REJECTIONS:
        word += [f"rejectionWord label {n}Case loopKind none", f"rejectionWord label {n}Case within none"]
    word.append("rejectionWord let none")
    word.append("rejectionWord at begin match rejection Rejection")
    word += [f"rejectionWord at begin case Rejection.{n} bind {n}Word Word goto {n}Case" for n, _m in REJECTIONS]
    word += [f"rejectionWord at {n}Case return ok {n}Word" for n, _m in REJECTIONS]
    msg = ["rejectionMessage is operation", 'rejectionMessage purpose "Say why a source is refused, in words"',
           'rejectionMessage invariant givesMessage "Gives the message that says why each variant of a rejection refuses '
           'a source"', "rejectionMessage typeParameter none",
           "rejectionMessage input rejection Rejection copied", "rejectionMessage input region Region borrowed",
           "rejectionMessage output String", "rejectionMessage outputOwnedBy region", "rejectionMessage raises none",
           "rejectionMessage effect none", "rejectionMessage uses none", "rejectionMessage memoryHeap true",
           "rejectionMessage async false", "rejectionMessage maxRecursion none",
           "rejectionMessage label begin loopKind none", "rejectionMessage label begin within none"]
    for n, _m in REJECTIONS:
        msg += [f"rejectionMessage label {n}Case loopKind none", f"rejectionMessage label {n}Case within none"]
    msg += [f"rejectionMessage let {n}Text String {q(m)} immutable" for n, m in REJECTIONS]
    msg.append("rejectionMessage at begin match rejection Rejection")
    msg += [f"rejectionMessage at begin case Rejection.{n} bind {n}Word Word goto {n}Case" for n, _m in REJECTIONS]
    msg += [f"rejectionMessage at {n}Case return ok {n}Text" for n, _m in REJECTIONS]
    repl = {"Rejection": "\n".join(rej), "rejectionWord": "\n".join(word), "rejectionMessage": "\n".join(msg)}
    out = []
    for b in blocks:
        name, kind = entity_name(b)
        if name in repl:
            # keep comment lines above the entity
            comments = [ln for ln in b.split("\n") if ln.startswith("#")]
            lead = []
            for ln in b.split("\n"):
                if ln.startswith("#"):
                    lead.append(ln)
                else:
                    break
            out.append("\n".join(lead + [repl[name]]))
        else:
            out.append(b)
    new = semgen.format_text("\n\n".join(out) + "\n")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(new)


def header_of(path):
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().split("\n")
    out = []
    for ln in lines:
        if ln.startswith("#") or ln == "":
            out.append(ln)
        else:
            break
    while out and out[-1] == "":
        out.pop()
    return out


def model_tests():
    cases = [
        ("demo is module\nmeters is alias\n", "2:11: this entity kind is outside the stage0 subset (alias)"),
        ("demo is module\nother path demo\n", "2:1: this row's subject is not the entity above it (other)"),
        ("demo is module\ndemo is module\n", "2:1: this name is already declared (demo)"),
        ("demo path demo\n", "1:1: this row's subject is not the entity above it (demo)"),
        ("demo is module extra\n", "1:6: this payload is outside the stage0 subset (is)"),
    ]
    return macros.reject_test(
        "rejectTest", "Kinds outside the subset, stray rows, module-level names declared twice, and long `is` rows are "
        "refused at the word concerned", [("buildModel", "rejectsOutsideModel")], cases,
        lambda i: macros.front(i, f"source{i}", "refused", "modelCatch"))


import tests_gen  # noqa: E402
EXTRA = {"model": model_tests, "subset": lambda: tests_gen.subset_tests(STAGE0), "emitc": lambda: tests_gen.emitc_tests(STAGE0)}

# the built-in types, numbered by their row: (name, literal, plain, kind, C type)
BUILTIN_TYPES = [
    ("String", "text", False, 1, "ss_string"),
    ("Int64", "integer", True, 1, "int64_t"),
    ("ExitCode", "exitCode", True, 1, "int"),
    ("Bool", "flag", True, 1, "bool"),
    ("Byte", "byte", True, 1, "uint8_t"),
    ("Region", "noLiteral", True, 1, "ss_region *"),
    ("standard error", "noLiteral", True, 2, "int64_t"),
    ("buffer.ByteBuffer", "noLiteral", False, 1, "int64_t"),
    ("process.Arguments", "noLiteral", False, 1, "int64_t"),
    ("time.Deadline", "noLiteral", True, 1, "int64_t"),
    ("Bytes", "noLiteral", False, 1, "ss_string"),
]
TYPE_CODES = {n: i for i, (n, *_r) in enumerate(BUILTIN_TYPES, 1)}
# string.Position is a record of the standard library: stage0 declares it in a module of its own, `string`, which the
# driver puts before the program's modules, so it is always the first declared type
TYPE_CODES["string.Position"] = len(BUILTIN_TYPES) + 1
SLOTS = {"String": 2, "Bytes": 2}
MODE_CODES = {"copied": 1, "borrowed": 2, "borrowedMutable": 3, "owned": 4}

# every standard library target stage0 compiles, with its C spelling: (target, before, between, after); a target
# whose spelling is "host" goes through the runtime's refined_host, as the LLVM backend calls it
HOST = ("host", "", "")
BUILTINS = [
    ("console.writeLine", "ss_write_line(", ", ", ")"),
    ("console.write", "ss_write(", ", ", ")"),
    ("console.writeIntegerLine", "ss_write_integer_line(", ", ", ")"),
    ("console.writeError", "ss_write_error(", ", ", ")"),
    ("math.addInt64", "ss_add(", ", ", ")"),
    ("math.subtractInt64", "ss_subtract(", ", ", ")"),
    ("math.multiplyInt64", "ss_multiply(", ", ", ")"),
    ("math.divideInt64", "ss_divide(", ", ", ")"),
    ("math.remainderInt64", "ss_remainder(", ", ", ")"),
    ("math.negateInt64", "ss_negate(", ", ", ")"),
    ("math.absoluteInt64", "ss_absolute(", ", ", ")"),
    ("math.powerInt64", "ss_power(", ", ", ")"),
    ("compare.equalInt64", "(", " == ", ")"),
    ("compare.notEqualInt64", "(", " != ", ")"),
    ("compare.lessThanInt64", "(", " < ", ")"),
    ("compare.lessOrEqualInt64", "(", " <= ", ")"),
    ("compare.greaterThanInt64", "(", " > ", ")"),
    ("compare.greaterOrEqualInt64", "(", " >= ", ")"),
    ("compare.equalByte", "(", " == ", ")"),
    ("compare.notEqualByte", "(", " != ", ")"),
    ("compare.lessThanByte", "(", " < ", ")"),
    ("compare.lessOrEqualByte", "(", " <= ", ")"),
    ("compare.greaterThanByte", "(", " > ", ")"),
    ("compare.greaterOrEqualByte", "(", " >= ", ")"),
    ("logic.and", "(", " && ", ")"),
    ("logic.or", "(", " || ", ")"),
    ("logic.xor", "(", " != ", ")"),
    ("logic.not", "(!", "", ")"),
    ("convert.exitCodeToInt64", "((int64_t)", "", ")"),
    ("convert.int64ToExitCode", "ss_exit_code(", "", ")"),
    ("convert.byteToInt64", "((int64_t)", "", ")"),
    ("convert.int64ToByte", "ss_to_byte(", "", ")"),
    ("byte.isLetter", "ss_is_letter(", "", ")"),
    ("byte.isDigit", "ss_is_digit(", "", ")"),
    ("byte.isLetterOrDigit", "ss_is_letter_or_digit(", "", ")"),
    ("byte.isSpace", "ss_is_space(", "", ")"),
    ("byte.equals", "(", " == ", ")"),
    ("byte.isPunctuation", "ss_is_punctuation(", "", ")"),
    ("string.byteLength", "ss_byte_length(", ", ", ")"),
    ("string.equals", "ss_equals(", ", ", ")"),
    ("string.startsWith", "ss_starts_with(", ", ", ")"),
    ("string.concat", "ss_concat(", ", ", ")"),
    ("string.fromInt64", "ss_from_int64(", ", ", ")"),
    ("string.toInt64", "ss_to_int64(", ", ", ")"),
    ("string.slice", "ss_slice(", ", ", ")"),
    ("string.byteAt", "ss_byte_at(", ", ", ")"),
    ("string.byteAtOrTrap", "ss_byte_at_or_trap(", ", ", ")"),
    ("string.find", "ss_find(", ", ", ")"),
    ("string.toBytes", "ss_to_bytes(", ", ", ")"),
    ("string.advancePosition", "ss_advance_position(", ", ", ")"),
    ("string.fromBytes", *HOST),
    ("buffer.new", *HOST),
    ("buffer.appendString", *HOST),
    ("buffer.appendByte", *HOST),
    ("buffer.appendInt64", *HOST),
    ("buffer.length", *HOST),
    ("buffer.toString", *HOST),
    ("buffer.toBytes", *HOST),
    ("process.argumentCount", *HOST),
    ("process.argument", *HOST),
    ("process.newArguments", *HOST),
    ("process.addArgument", *HOST),
    ("time.sleep", *HOST),
    ("log.debug", *HOST),
    ("log.info", *HOST),
    ("log.warn", *HOST),
    ("log.error", *HOST),
    ("time.Deadline.after", *HOST),
    ("fs.readAll", *HOST),
    ("fs.writeAll", *HOST),
    ("fs.createDirectory", *HOST),
    ("process.run", *HOST),
]


def library_sig(target):
    """A standard library target's signature: `<module>.<target>`, or `<module>.<Type>.<target>`."""
    from refined.library import LIBRARY as LIB
    parts = target.split(".")
    if len(parts) == 3:
        return LIB[parts[0]]["types"][parts[1]].targets[parts[2]]
    return LIB[parts[0]]["targets"][parts[1]]


def builtin_rows():
    from refined.library import LIBRARY as LIB
    rows = []
    for target, *_spelling in BUILTINS:
        sig = library_sig(target)
        ps = [(p.name, TYPE_CODES[p.type], MODE_CODES[p.mode] if p.type != "Region" else 2) for p in sig.inputs]
        # an argument's mode as the call writes it: copied -> copy (1), borrowed -> lend (2), ...
        while len(ps) < 4:
            ps.append(("", 0, 0))
        out = TYPE_CODES[sig.output] if sig.output else 0
        rows.append((target, len(sig.inputs), ps, out, 7 if sig.raises else 0, sig.raises or ""))
    return rows


def host_key(target):
    """The name refined_host dispatches on: the target, each argument's slot count, and the result's; a scoped
    target takes the scope text (a pointer and a length) after its arguments (D-38)."""
    sig = library_sig(target)
    counts = [SLOTS.get(p.type, 1) for p in sig.inputs] + ([2] if sig.scoped else [])
    nres = SLOTS.get(sig.output, 1) if sig.output else 0
    return f"{target}|{','.join(str(c) for c in counts)}|{nres}", sum(counts), nres


def table_text(name, purpose, rtype, rows):
    out = [f"table {name} {q(purpose)} {rtype}"]
    for rname, cells in rows:
        out.append(f"  row {rname} " + " ".join(f"{k}={v}" for k, v in cells))
    return "\n".join(out) + "\n"


def row_name(text):
    parts = re.split(r"[^A-Za-z0-9]", text)
    return parts[0][:1].lower() + parts[0][1:] + "".join(p[:1].upper() + p[1:] for p in parts[1:])


def lookup_op(name, purpose, table, rowtype, field, count, missing, output):
    lines = [f"op {name} {q(purpose)}", "  input source String borrowed", "  input word syntax.Word copied",
             f"  output {output}", "  raises syntax.Rejection", ":begin", "  goto scan",
             f":scan loop=forEach max={count} over={table}", "  next " + table + " entry compare missing",
             ":compare in=scan", f"  readText: entryText = {rowtype}.text(entry)",
             "  sameText: isSame = syntax.isText(source, word, entryText) ?^", "  if isSame found scan", ":found",
             f"  readFound: foundValue = {rowtype}.{field}(entry)", "  return foundValue", ":missing",
             f"  makeMissing: missingError = syntax.Rejection.{missing}(word)", "  raise missingError"]
    return "\n".join(lines) + "\n"


CONTEXT = ["purpose", "invariant", "rationale", "risk", "note", "todo", "deprecated"]
PREDICATES = ["path", "imports", "exports", "grants", "typeParameter", "field", "variant", "in", "instantiates",
              "type", "value", "input", "output", "outputOwnedBy", "raises", "effect", "uses", "memoryHeap", "async",
              "maxRecursion", "label", "let", "at", "invokes", "argument", "result", "ownedBy", "cleanedBy", "borrows",
              "catch", "suppresses", "strategy", "maxBytes", "released", "rowType", "row", "cell",
              "invokesReference"]
STEPS = [("do", "doCall"), ("set", "setValue"), ("goto", "jump"), ("branch", "branchIf"), ("match", "matchValue"),
         ("case", "caseOf"), ("return", "returnOk"), ("start", "startTask"), ("join", "joinTask")]
FACTS = [("purpose", "other"), ("rationale", "other"), ("risk", "other"), ("note", "other"), ("todo", "other"),
         ("loopKind", "loopKind"), ("within", "within"), ("maxIterations", "maxIterations"), ("over", "over"),
         ("counter", "other")]
LOOPS = [("none", 0), ("while", 1), ("doWhile", 2), ("counted", 3), ("forever", 4), ("forEach", 5)]


def subset_tables():
    t = []
    t.append(table_text("builtinTypes", "The built-in types of the stage0 subset; a type's number is its row's position",
                        "TypeRow", [(row_name(n) + "Type", [("text", q(n)), ("literal", f"LiteralKind.{lit}"),
                                                             ("plain", "true" if plain else "false"), ("kind", str(k))])
                                    for n, lit, plain, k, _c in BUILTIN_TYPES]))
    prow = [(w + "Word", [("text", q(w)), ("predicate", "Predicate.contextRow")]) for w in CONTEXT]
    prow += [(w + "Word", [("text", q(w)), ("predicate", f"Predicate.{w}Row")]) for w in PREDICATES]
    t.append(table_text("predicateWords", "Every predicate the stage0 subset reads", "PredicateRow", prow))
    t.append(table_text("stepWords", "The step words of the stage0 subset (`branch` and `return` are refined by the "
                        "word after them)", "StepRow",
                        [(w + "Step", [("text", q(w)), ("verb", f"StepVerb.{v}")]) for w, v in STEPS]))
    t.append(table_text("factWords", "The label facts of the stage0 subset", "FactRow",
                        [(w + "Fact", [("text", q(w)), ("fact", f"LabelFact.{f}")]) for w, f in FACTS]))
    t.append(table_text("loopWords", "The loop kinds and their numbers", "LoopRow",
                        [(w + "Loop", [("text", q(w)), ("number", str(n))]) for w, n in LOOPS]))
    brows = []
    for target, count, ps, out, raises, err in builtin_rows():
        cells = [("text", q(target)), ("count", str(count))]
        for i, (slot, ty, md) in enumerate(ps, 1):
            cells += [(f"slot{i}", q(slot)), (f"type{i}", str(ty)), (f"mode{i}", str(md))]
        cells += [("output", str(out)), ("raises", str(raises)), ("error", q(err))]
        brows.append((row_name(target) + "Target", cells))
    t.append(table_text("builtinTargets", "Every standard library target of the stage0 subset", "BuiltinRow", brows))
    return "\n".join(t)


def subset_lookups():
    return "\n".join([
        lookup_op("lookupPredicate", "Find a predicate word and return what its row states", "predicateWords",
                  "PredicateRow", "predicate", len(CONTEXT) + len(PREDICATES), "unsupportedPredicate", "Predicate"),
        lookup_op("lookupStep", "Find a step word and return the verb it begins", "stepWords", "StepRow", "verb",
                  len(STEPS), "unsupportedStep", "StepVerb"),
        lookup_op("lookupFact", "Find a label fact word and return what it states", "factWords", "FactRow", "fact",
                  len(FACTS), "unsupportedPredicate", "LabelFact"),
        lookup_op("lookupLoop", "Find a loop kind word and return its number", "loopWords", "LoopRow", "number",
                  len(LOOPS), "unsupportedPayload", "Int64"),
    ])


def emitc_tables():
    t = []
    rows = []
    for target, before, between, after in BUILTINS:
        host = before == "host"
        key, nargs, nres = host_key(target) if host else ("", 0, 0)
        sig = library_sig(target)
        scope = sorted(sig.effects)[0] if sig.scoped else ("", "")
        rows.append((row_name(target) + "Spelling", [("text", q(target)), ("before", q("" if host else before)),
                                                       ("between", q(between)), ("after", q(after)),
                                                       ("host", "true" if host else "false"), ("key", q(key)),
                                                       ("slots", str(nargs)), ("results", str(nres)),
                                                       ("scoped", "true" if sig.scoped else "false"),
                                                       ("verb", q(scope[0])), ("resource", q(scope[1]))]))
    t.append(table_text("cTargets", "The C spelling of every standard library target of the subset, in the order of "
                        "subset's builtinTargets", "CTarget", rows))
    t.append(table_text("cTypes", "The C spelling of every built-in type, numbered as subset numbers them", "CType",
                        [(row_name(n) + "Spelling", [("text", q(n)), ("cType", q(c))])
                         for n, _l, _p, _k, c in BUILTIN_TYPES]))
    with open(os.path.join(HERE, "prelude.c"), encoding="utf-8") as fh:
        prelude = fh.read()
    t.append("constant prelude \"The runtime every emitted program starts with\" String " + q(prelude))
    return "\n".join(t)


SUBST = {"emitc": lambda t: t.replace("%%TABLES%%", emitc_tables()),
         "subset":lambda t: t.replace("%%TABLES%%", subset_tables()).replace("%%LOOKUPS%%", subset_lookups())
         .replace("%%BUILTIN_COUNT%%", str(len(BUILTINS)))}


def generate(prog, name, dsl_file, header, test_header):
    with open(os.path.join(HERE, dsl_file), encoding="utf-8") as fh:
        text = fh.read()
    if name in SUBST:
        text = SUBST[name](text)
    if name in EXTRA:
        text += "\n" + EXTRA[name]()
    m = Module(name)
    prog.modules[name] = m
    g = Generator(prog, m)
    g.declare(text)
    g.parse(text)
    return g, header, test_header


SAMPLE_BUILD = """# A stage0 sample program (docs/refined-examples/stage0/samples). Run it with
# `refined run`, or compile it with stage0 and run what stage0 builds.

{name} is project
{name} purpose "{purpose}"
{name} target console
{name} version "0.1.0"
{name} language refined 1
{name} standardLibrary 1
{allows}
{name} requires none
{includes}
{name} entry {entry}.main
"""
SAMPLE_AUTHORITY = """# Authority approved for this project (`refined approve`). A program runs only with authority
# listed here; build.sem asking for more stops `refined run`, `test`, and executable builds.
{authority}
"""
# what each sample may do besides writing to standard output
SAMPLE_ALLOWS = {"files": ['read fs.files "build/"', 'write fs.files "build/"']}
# a sample of several modules is a folder of .dsl files, one per module, in the order build.sem includes them
SAMPLE_PROJECTS = {"modules": ["shapes", "app"]}


def sample_modules(name):
    """[(module name, dsl text)] of a sample, in the order build.sem includes them."""
    folder = os.path.join(HERE, "samples")
    if name in SAMPLE_PROJECTS:
        out = []
        for module in SAMPLE_PROJECTS[name]:
            with open(os.path.join(folder, name, module + ".dsl"), encoding="utf-8") as fh:
                out.append((module, fh.read()))
        return out
    with open(os.path.join(folder, name + ".dsl"), encoding="utf-8") as fh:
        return [(name, fh.read())]


def generate_samples(prog, names):
    folder = os.path.join(HERE, "samples")
    found = sorted([fn[:-4] for fn in os.listdir(folder) if fn.endswith(".dsl")] + list(SAMPLE_PROJECTS))
    for name in found:
        if names and name not in names:
            continue
        modules = sample_modules(name)
        out = os.path.join(STAGE0, "samples", name)
        os.makedirs(out, exist_ok=True)
        lines = 0
        for module, text in modules:
            m = Module(module)
            prog.modules[module] = m
            g = Generator(prog, m)
            g.declare(text)
            g.parse(text)
            purpose = re.search(r'^module \w+ "([^"]*)"', text, re.M).group(1)
            header = ["# Tests for the " + module + " module of the stage0 sample `" + name + "`."]
            f, tf = g.render([], header)
            f = f.lstrip("\n")
            with open(os.path.join(out, module + ".sem"), "w", encoding="utf-8", newline="\n") as fh:
                fh.write(f)
            if tf is not None:
                with open(os.path.join(out, module + ".test.sem"), "w", encoding="utf-8", newline="\n") as fh:
                    fh.write(tf)
            lines += f.count(chr(10))
        allows = ["write console.stdout none"] + SAMPLE_ALLOWS.get(name, [])
        with open(os.path.join(out, "build.sem"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(SAMPLE_BUILD.format(
                name=name, purpose=purpose + "; a stage0 sample both runs agree on", entry=modules[-1][0],
                allows="\n".join(f"{name} allows {a}" for a in allows),
                includes="\n".join(f"{name} includesModule {module}" for module, _t in modules)))
        with open(os.path.join(out, "authority.approved"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(SAMPLE_AUTHORITY.format(authority="\n".join(allows)))
        print(f"sample {name}: {lines} lines")


def main(which):
    prog = Program()
    prog.load_sem("lexer", os.path.join(STAGE0, "lexer.sem"))
    syn = os.path.join(STAGE0, "syntax.sem")
    if "syntax" in which:
        regenerate_syntax(syn)
    prog.load_sem("syntax", syn)
    gens = []
    for name in ("model", "subset", "emitc", "stage0"):
        dsl = os.path.join(HERE, name + ".dsl")
        if not os.path.exists(dsl):
            prog.load_sem(name, os.path.join(STAGE0, name + ".sem"))
            continue
        hdr = os.path.join(HERE, name + ".header")
        thdr = os.path.join(HERE, name + ".test.header")
        header = open(hdr, encoding="utf-8").read().rstrip("\n").split("\n") if os.path.exists(hdr) else \
            header_of(os.path.join(STAGE0, name + ".sem"))
        tsem = os.path.join(STAGE0, name + ".test.sem")
        theader = open(thdr, encoding="utf-8").read().rstrip("\n").split("\n") if os.path.exists(thdr) else \
            (header_of(tsem) if os.path.exists(tsem) else None)
        g, header, theader = generate(prog, name, name + ".dsl", header, theader)
        if name in which:
            f, tf = g.render(header, theader)
            with open(os.path.join(STAGE0, name + ".sem"), "w", encoding="utf-8", newline="\n") as fh:
                fh.write(f)
            if tf is not None:
                with open(os.path.join(STAGE0, name + ".test.sem"), "w", encoding="utf-8", newline="\n") as fh:
                    fh.write(tf)
            print(f"{name}: {f.count(chr(10))} lines" + (f", tests {tf.count(chr(10))} lines" if tf else ""))


if __name__ == "__main__":
    if sys.argv[1:2] == ["samples"]:
        generate_samples(Program(), sys.argv[2:])
    else:
        main(sys.argv[1:] or ["syntax", "model", "subset", "emitc", "stage0"])

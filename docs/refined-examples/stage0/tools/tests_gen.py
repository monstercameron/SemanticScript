"""Generated tests for subset and emitc."""
import os
from semgen import q
import macros

REFUSED = 'let refusedText String "the front end refused the source or a step failed"'


def sample(stage0, name):
    with open(os.path.join(stage0, "samples", name, name + ".sem"), encoding="utf-8") as fh:
        return fh.read()


def mutate(base, old, new, word, message, at=None):
    """Replace one line, and give the diagnostic expected at `word` on that line (or on the line `at`)."""
    lines = base.split("\n")
    idx = lines.index(old)
    lines[idx] = new
    if at is not None:
        idx = lines.index(at)
        new = at
    col = new.index(" " + word) + 2 if not new.startswith(word + " ") else 1
    return "\n".join(lines), f"{idx + 1}:{col}: {message} ({word})"


def collections(sfx, region="store"):
    return [
        f"newTypes{sfx}: types{sfx} = Types.new({region})",
        f"newTypeNames{sfx}: typeNames{sfx} = TypeNames.new({region})",
        f"newMembers{sfx}: members{sfx} = Members.new({region})",
        f"newParams{sfx}: params{sfx} = Params.new({region})",
        f"newTargets{sfx}: targets{sfx} = Targets.new({region})",
        f"newOps{sfx}: ops{sfx} = Ops.new({region})",
        f"newOpNames{sfx}: opNames{sfx} = OpNames.new({region})",
        f"newOwners{sfx}: owners{sfx} = Owners.new({region})",
        f"newConstants{sfx}: constants{sfx} = Values.new({region})",
        f"newGlobalTypeNames{sfx}: globalTypeNames{sfx} = TypeNames.new({region})",
        f"newGlobalTargets{sfx}: globalTargets{sfx} = Targets.new({region})",
    ]


def declare(sfx, source, mark):
    """The built-in names, then the declarations of the module that starts the source."""
    return "\n  ".join([
        f"builtins{sfx}: declareBuiltins({source}, types{sfx}, globalTypeNames{sfx}, params{sfx}, "
        f"globalTargets{sfx}, store) ? refused",
        f"findEnd{sfx}: end{sfx} = nextModule(entities{sfx}, 0)",
        f"declare{sfx}: checkModuleDeclarations({source}, words{sfx}, rows{sfx}, entities{sfx}, 0, end{sfx}, "
        f"types{sfx}, typeNames{sfx}, members{sfx}, params{sfx}, targets{sfx}, ops{sfx}, opNames{sfx}, owners{sfx}, "
        f"constants{sfx}, globalTypeNames{sfx}, globalTargets{sfx}, store) {mark}"])


DECLARE_SOURCE = """demo is module
demo path demo
demo imports none
demo exports main

Point is record
Point typeParameter none
Point field x Int64
Point field label String

Shape is enum
Shape typeParameter none
Shape variant dot Int64
Shape variant empty none

Points is typeInstance
Points in none
Points instantiates list.List Point

main is operation
main input none
main output ExitCode
main raises none
"""


def subset_tests(stage0):
    squares = sample(stage0, "squares")
    out = []
    # ---- declarations
    t = [f"test declareTest {q('Built-in and declared types are numbered, members kept in order, and every target entered with its slots')}",
         "  verifies checkModuleDeclarations declaresTypes", "  verifies checkModuleDeclarations declaresTargets",
         "  verifies declareBuiltins numbersBuiltins", "  verifies nextModule findsModuleEnd",
         "  region store 4194304", f"  let source String {q(DECLARE_SOURCE)}", "  " + REFUSED, ":begin"]
    t += ["  " + x for x in macros.front("X", "source", "refused", "model", prefix="model.")]
    t += ["  " + x for x in collections("X")]
    t.append("  " + declare("X", "source", "? refused"))
    t += [
        "  countTypes: typeCount = Types.length(typesX)",
        "  expectTypes: test.assertEqualInt64(fourteen=14, typeCount)",
        "  findPoint: pointCode = TypeNames.get(typeNamesX, pointName=\"Point\") ? refused",
        "  expectPoint: test.assertEqualInt64(twelve=12, pointCode)",
        "  readPoint: pointInfo = typeInfoOf(typesX, pointCode)",
        "  readPointText: pointText = TypeInfo.holdsText(pointInfo)",
        "  expectPointText: test.assertTrue(pointText)",
        "  findShape: shapeCode = TypeNames.get(typeNamesX, shapeName=\"Shape\") ? refused",
        "  readShape: shapeInfo = typeInfoOf(typesX, shapeCode)",
        "  readShapeNarrow: shapeNarrow = TypeInfo.narrow(shapeInfo)",
        "  expectShapeNarrow: test.assertTrue(shapeNarrow)",
        "  countMembers: memberCount = Members.length(membersX)",
        "  expectMembers: test.assertEqualInt64(four=4, memberCount)",
        "  findNew: pointNew = Targets.get(targetsX, newName=\"Point.new\") ? refused",
        "  readNewCount: newCount = TargetInfo.paramCount(pointNew)",
        "  expectNewCount: test.assertEqualInt64(three=3, newCount)",
        "  findPointLabel: hasLabel = Targets.contains(targetsX, labelName=\"Point.label\")",
        "  expectLabel: test.assertTrue(hasLabel)",
        "  findDot: hasDot = Targets.contains(targetsX, dotName=\"Shape.dot\")",
        "  expectDot: test.assertTrue(hasDot)",
        "  findAppend: hasAppend = Targets.contains(targetsX, appendName=\"Points.append\")",
        "  expectAppend: test.assertTrue(hasAppend)",
        "  findWrite: hasWrite = Targets.contains(targetsX, writeName=\"console.writeLine\")",
        "  expectWrite: test.assertTrue(hasWrite)",
        "  findMain: mainTarget = Targets.get(targetsX, mainName=\"main\") ? refused",
        "  readMainOutput: mainOutput = TargetInfo.output(mainTarget)",
        "  expectMainOutput: test.assertEqualInt64(three, mainOutput)",
        "  findPublished: publishedNew = Targets.contains(globalTargetsX, publishedName=\"demo.Point.new\")",
        "  expectPublished: test.assertTrue(publishedNew)",
        "  findPublishedType: publishedCode = TypeNames.get(globalTypeNamesX, publishedType=\"demo.Point\") ? refused",
        "  expectPublishedType: test.assertEqualInt64(twelve, publishedCode)",
        "  findString: stringCode = TypeNames.get(globalTypeNamesX, stringName=\"String\") ? refused",
        "  expectString: test.assertEqualInt64(one=1, stringCode)",
        "  findBytes: bytesCode = TypeNames.get(globalTypeNamesX, bytesName=\"Bytes\") ? refused",
        "  expectBytes: test.assertEqualInt64(eleven=11, bytesCode)",
        "  countModel: modelCount = model.Entities.length(entitiesX)",
        "  expectEnd: test.assertEqualInt64(modelCount, endX)",
        "  findBareType: bareType = TypeNames.contains(globalTypeNamesX, pointName)",
        "  bareAbsent: noBareType = logic.not(bareType)",
        "  expectNoBareType: test.assertTrue(noBareType)",
        "  return",
        ":refused",
        "  failRefused: test.fail(refusedText)",
        "  return",
    ]
    out.append("\n".join(t))
    # ---- one operation
    t = [f"test operationTest {q('The squares sample: main values, calls, labels, and steps are collected in source order')}",
         "  verifies checkOperation collectsOperation", "  verifies checkOperation checksOperation",
         "  region store 4194304", f"  let source String {q(squares)}", "  " + REFUSED, ":begin"]
    t += ["  " + x for x in macros.front("X", "source", "refused", "model", prefix="model.")]
    t += ["  " + x for x in collections("X")]
    t.append("  " + declare("X", "source", "? refused"))
    t += [
        "  newValues: values = Values.new(store)",
        "  newCalls: calls = Calls.new(store)",
        "  newArguments: arguments = Arguments.new(store)",
        "  newLabels: labels = Labels.new(store)",
        "  newSteps: steps = Steps.new(store)",
        "  checkMain: checkOperation(source, wordsX, rowsX, entitiesX, typesX, typeNamesX, membersX, paramsX, "
        "targetsX, opsX, ownersX, constantsX, 0, values, calls, arguments, labels, steps) ? refused",
        "  countValues: valueCount = Values.length(values)",
        "  expectValues: test.assertEqualInt64(eight=8, valueCount)",
        "  countCalls: callCount = Calls.length(calls)",
        "  expectCalls: test.assertEqualInt64(four=4, callCount)",
        "  countArguments: argumentCount = Arguments.length(arguments)",
        "  expectArguments: test.assertEqualInt64(seven=7, argumentCount)",
        "  countLabels: labelCount = Labels.length(labels)",
        "  expectLabels: test.assertEqualInt64(six=6, labelCount)",
        "  countSteps: stepCount = Steps.length(steps)",
        "  expectSteps: test.assertEqualInt64(eleven=11, stepCount)",
        "  findLoopLabel: loop = Labels.get(labels, loopName=\"nextSquare\") ? refused",
        "  readLoopKind: loopKind = LabelInfo.kind(loop)",
        "  expectLoopKind: test.assertEqualInt64(one=1, loopKind)",
        "  readBounded: bounded = LabelInfo.bounded(loop)",
        "  expectBounded: test.assertTrue(bounded)",
        "  return",
        ":refused",
        "  failRefused: test.fail(refusedText)",
        "  return",
    ]
    out.append("\n".join(t))
    # ---- refusals
    cases = [(squares, None)]
    m = []
    m.append(mutate(squares, "pastLimitCheck suppresses none", "pastLimitCheck defers none",
                    "defers", "this predicate is outside the stage0 subset here"))
    m.append(mutate(squares, "main let one Int64 1 immutable", "main let one Float64 1 immutable", "Float64",
                    "this type is outside the stage0 subset"))
    m.append(mutate(squares, "main let okCode ExitCode 0 immutable", "main let okCode ExitCode 300 immutable", "300",
                    "this literal does not fit its type"))
    m.append(mutate(squares, "square invokes math.multiplyInt64", "square invokes math.wrappingMultiplyInt64", "math.wrappingMultiplyInt64",
                    "this call target is outside the stage0 subset"))
    m.append(mutate(squares, "addOne argument right Int64 one copy", "addOne argument right Int64 one lend", "lend",
                    "this argument does not match the target's slot, type, or mode"))
    m.append(mutate(squares, "addOne argument right Int64 one copy", "addOne argument right Int64 okCode copy",
                    "okCode", "this value has another type"))
    m.append(mutate(squares, "main at begin goto nextSquare", "main at begin goto nowhere", "nowhere",
                    "no label has this name"))
    m.append(mutate(squares, "main at advance set number nextNumber", "main at advance set one nextNumber", "one",
                    "this value is immutable"))
    m.append(mutate(squares, "main at finished return ok okCode", "main at finished return ok doneCode", "doneCode",
                    "no value has this name"))
    m.append(mutate(squares, "main at printSquare branch ifError printIt goto failed else goto advance",
                    "main at printSquare branch ifError square goto failed else goto advance", "square",
                    "this call cannot fail, so there is no error to branch on"))
    m.append(mutate(squares, "main at advance goto nextSquare", "main at printSquare goto nextSquare", "printSquare",
                    "this label's steps are not together"))
    m.append(mutate(squares, "main input none", "main input count Int64 copied", "main",
                    "main takes no input, gives an ExitCode, and raises nothing", at="main is operation"))
    m.append(mutate(squares, "addOne in main", "addOne in elsewhere", "elsewhere",
                    "no operation of this module has this name"))
    m.append(mutate(squares, "main label nextSquare loopKind while", "main label nextSquare loopKind sometimes",
                    "sometimes", "this payload is outside the stage0 subset"))
    cases = m
    t = macros.reject_test(
        "rejectTest", "Predicates, payloads, types, literals, targets, arguments, labels, values, owners, and blocks "
        "outside the subset are refused at the word concerned", [("checkProgram", "rejectsOutsideSubset")], cases,
        lambda i: macros.front(i, f"source{i}", "refused", "model", prefix="model.") +
        [f"check{i}: checkProgram(source{i}, words{i}, rows{i}, entities{i}) ! rejection{i}",
         f"iferr check{i} rejected{i} refused"])
    out.append(t)
    # ---- acceptance, diagnose, and declaration refusals
    order_src = DECLARE_SOURCE.replace("Point field x Int64\n", "Point field x Int64\nPoint field shape Shape\n")
    shape_line = order_src.split("\n").index("Point field shape Shape") + 1
    t = [f"test acceptTest {q('The squares sample is accepted and diagnosed as accepted; a record holding an enum declared below it, and a source that does not begin with its module, are refused')}",
         "  verifies checkProgram acceptsSubset", "  verifies diagnose reportsFirstProblem",
         "  verifies checkModuleDeclarations rejectsOutsideDeclarations",
         "  region store 4194304", f"  let source String {q(squares)}",
         f"  let orderSource String {q(order_src)}",
         f"  let orderExpected String {q(f'{shape_line}:19: a record or enum holds only types declared above it (Shape)')}",
         f"  let noMainSource String {q('Point is record' + chr(10) + 'Point typeParameter none' + chr(10))}",
         f"  let noMainExpected String {q('1:1: a module' + chr(39) + 's file begins with its `<name> is module` entity (Point)')}",
         "  " + REFUSED, ":begin"]
    t += ["  " + x for x in macros.front("X", "source", "refused", "model", prefix="model.")]
    t += [
        "  acceptIt: checkProgram(source, wordsX, rowsX, entitiesX) ? refused",
        "  describeIt: described = diagnose(source, store)",
        "  expectAccepted: test.assertEqualString(acceptedText=\"accepted\", described)",
        "  describeOrder: orderDescribed = diagnose(orderSource, store)",
        "  expectOrder: test.assertEqualString(orderExpected, orderDescribed)",
    ]
    t += ["  " + x for x in macros.front("Y", "noMainSource", "refused", "model", prefix="model.")]
    t += ["  " + x for x in collections("Y")]
    t.append("  " + declare("Y", "noMainSource", "! noMainError"))
    t += [
        "  iferr declareY noMainRefused refused",
        ":noMainRefused",
        "  describeNoMain: noMainDescribed = syntax.diagnostic(noMainSource, noMainError, store)",
        "  expectNoMain: test.assertEqualString(noMainExpected, noMainDescribed)",
        "  return",
        ":refused",
        "  failRefused: test.fail(refusedText)",
        "  return",
    ]
    out.append("\n".join(t))
    return "\n@tests\n\n" + "\n\n".join(out) + "\n"


def emitc_tests(stage0):
    squares = sample(stage0, "squares")
    bad = squares.replace("square invokes math.multiplyInt64", "square invokes math.wrappingMultiplyInt64")
    bad_line = bad.split("\n").index("square invokes math.wrappingMultiplyInt64") + 1
    bad_column = "square invokes math.wrappingMultiplyInt64".index("math.") + 1
    bad_where = f"{bad_line}:{bad_column}: this call target is outside the stage0 subset (math.wrappingMultiplyInt64)"
    no_entry_where = f"{squares.split(chr(10)).index('squares is module') + 1}:1: the module has no main operation (squares)"
    snippets = [
        ("mainWrapper", "int main(int argc, char **argv) {\n  refined_start(argc, argv);\n  return o_squares_main();\n}\n"),
        ("signature", "static int o_squares_main(void) {\n"),
        ("constantText", "static const int64_t k_squares_limit = 5;\n"),
        ("constantRead", "  int64_t v_limit = k_squares_limit;\n"),
        ("passText", '{ ss_pass(&n_nextSquare, v_limit, "nextSquare"); goto l_nextSquare; }'),
        ("resetText", "{ n_nextSquare = 0; goto l_nextSquare; }"),
        ("callText", "  f_printIt = ss_write_integer_line(v_squared);\n"),
        ("returnText", "  { int ss_result = v_okCode; return ss_result; }\n"),
    ]
    t = [f"test emitTest {q('The squares sample is written as C: the prelude, its constant, a function for main with its locals, labels, and jumps that count and reset the loop passes, and a C main; a source outside the subset is refused')}",
         "  verifies emitProgram writesC", "  verifies emitProgram countsLoopPasses",
         "  verifies emitProgram refusesOutsideSubset",
         "  region store 16777216", f"  let source String {q(squares)}", f"  let badSource String {q(bad)}",
         f"  let badExpected String {q(bad_where)}",
         f"  let noEntryExpected String {q(no_entry_where)}",
         "  " + REFUSED]
    for name, text in snippets:
        t.append(f"  let {name} String {q(text)}")
    t.append(":begin")
    t += ["  " + x for x in macros.front("X", "source", "refused", "model", prefix="model.")]
    t += [
        "  newC: cText = buffer.new(store)",
        "  emit: emitProgram(cText, source, wordsX, rowsX, entitiesX, entry=\"squares.main\") ? refused",
        "  readC: written = buffer.toString(cText, store) ? refused",
    ]
    for name, _text in snippets:
        t.append(f"  find{name[:1].upper() + name[1:]}: {name}At = string.find(written, {name}) ? refused")
    t += ["  " + x for x in macros.front("Y", "badSource", "refused", "model", prefix="model.")]
    t += [
        "  newBadC: badC = buffer.new(store)",
        "  emitBad: emitProgram(badC, badSource, wordsY, rowsY, entitiesY, entry) ! badError",
        "  iferr emitBad badRefused refused",
        ":badRefused",
        "  describeBad: badDescribed = syntax.diagnostic(badSource, badError, store)",
        "  expectBad: test.assertEqualString(badExpected, badDescribed)",
        "  newOtherC: otherC = buffer.new(store)",
        "  emitOther: emitProgram(otherC, source, wordsX, rowsX, entitiesX, otherEntry=\"squares.start\") ! otherError",
        "  iferr emitOther otherRefused refused",
        ":otherRefused",
        "  describeOther: otherDescribed = syntax.diagnostic(source, otherError, store)",
        "  expectOther: test.assertEqualString(noEntryExpected, otherDescribed)",
        "  return",
        ":refused",
        "  failRefused: test.fail(refusedText)",
        "  return",
    ]
    return "\n@tests\n\n" + "\n".join(t) + "\n"

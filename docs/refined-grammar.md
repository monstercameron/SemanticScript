# Refined syntax: row shapes

Generated from `semanticscript/compiler/refined/shapes.py`. Do not edit by hand.

Every row is `<subject> <predicate> <payload>`. Context rows (`purpose`, `invariant`, `verifies`, `rationale`, `risk`, `note`, `todo`, `deprecated`) come directly after the `is` row, in that order.

## `project`

| Predicate | Rows | Shape |
| --- | --- | --- |
| `target` | exactly one | `console\|library` |
| `module` | one or more (`none` alone when empty) | `<dotted.path>` |
| `entry` | exactly one | `none`<br>`<target>` |

## `module`

| Predicate | Rows | Shape |
| --- | --- | --- |
| `path` | exactly one | `<dotted.path>` |
| `imports` | one or more (`none` alone when empty) | `none`<br>`<dotted.path>` |
| `exports` | one or more (`none` alone when empty) | `none`<br>`<name>` |

## `record`

| Predicate | Rows | Shape |
| --- | --- | --- |
| `typeParam` | one or more (`none` alone when empty) | `none`<br>`<Type> any\|plain` |
| `field` | one or more (`none` alone when empty) | `<name> <Type>` |

## `enum`

| Predicate | Rows | Shape |
| --- | --- | --- |
| `typeParam` | one or more (`none` alone when empty) | `none`<br>`<Type> any\|plain` |
| `variant` | one or more (`none` alone when empty) | `<name> none`<br>`<name> <Type>` |

## `alias`

| Predicate | Rows | Shape |
| --- | --- | --- |
| `for` | exactly one | `<Type>` |
| `indexes` | exactly one | `none`<br>`<Type>` |

## `instance`

| Predicate | Rows | Shape |
| --- | --- | --- |
| `instantiates` | exactly one | `<Type> <Type>...` |

## `table`

| Predicate | Rows | Shape |
| --- | --- | --- |
| `of` | exactly one | `<Type>` |
| `row` | one or more (`none` alone when empty) | `<name> <integer>` |
| `cell` | one or more (`none` alone when empty) | `<name> <name> <literal\|name>` |

## `capability`

| Predicate | Rows | Shape |
| --- | --- | --- |
| `grants` | one or more (`none` alone when empty) | `connect\|listen\|read\|readWrite\|spawn\|write <module.resource>` |
| `scope` | exactly one | `none`<br>`"<text>"` |

## `operationInstance`

| Predicate | Rows | Shape |
| --- | --- | --- |
| `instantiates` | exactly one | `<name> <Type>...` |

## `operationType`

| Predicate | Rows | Shape |
| --- | --- | --- |
| `input` | one or more (`none` alone when empty) | `none`<br>`<name> <Type> borrowed\|borrowedMutable\|owned\|value` |
| `output` | exactly one | `none`<br>`<Type>` |
| `outputOwner` | exactly one | `none`<br>`caller`<br>`<name>` |
| `raises` | exactly one | `none`<br>`<Type>` |
| `effect` | one or more (`none` alone when empty) | `none`<br>`connect\|listen\|read\|readWrite\|spawn\|write <module.resource>` |
| `async` | exactly one | `false\|true` |

## `operation`

| Predicate | Rows | Shape |
| --- | --- | --- |
| `typeParam` | one or more (`none` alone when empty) | `none`<br>`<Type> any\|plain` |
| `input` | one or more (`none` alone when empty) | `none`<br>`<name> <Type> borrowed\|borrowedMutable\|owned\|value` |
| `output` | exactly one | `none`<br>`<Type>` |
| `outputOwner` | exactly one | `none`<br>`caller`<br>`<name>` |
| `raises` | exactly one | `none`<br>`<Type>` |
| `effect` | one or more (`none` alone when empty) | `none`<br>`connect\|listen\|read\|readWrite\|spawn\|write <module.resource>` |
| `uses` | one or more (`none` alone when empty) | `none`<br>`<name>` |
| `memory` | exactly one | `heap false\|true` |
| `async` | exactly one | `false\|true` |
| `maxRecursion` | exactly one | `none`<br>`<integer>` |
| `label` | zero or more | `<label> loopKind counted\|doWhile\|forEach\|forever\|none\|while`<br>`<label> within none`<br>`<label> within <label>`<br>`<label> maxIterations <integer>`<br>`<label> maxIterations <name>`<br>`<label> maxIterations unbounded`<br>`<label> counter <name>`<br>`<label> over <name>`<br>`<label> because "<text>"`<br>`<label> purpose "<text>"`<br>`<label> rationale "<text>"`<br>`<label> risk concurrency\|data\|failure\|memory\|security\|timing "<text>"`<br>`<label> note "<text>"`<br>`<label> todo "<text>"` |
| `let` | zero or more | `<name> immutable\|mutable <Type> <literal\|name\|unset>` |
| `at` | zero or more | `<label> do <name>`<br>`<label> start <name>`<br>`<label> start <name> into <name>`<br>`<label> join <name>`<br>`<label> cancel <name>`<br>`<label> awaitSlot <name>`<br>`<label> defer <name>`<br>`<label> set <name> <name>`<br>`<label> goto <label>`<br>`<label> branch if <name> goto <label> else goto <label>`<br>`<label> branch ifError <name> goto <label> else goto <label>`<br>`<label> branch ifNext <name> bind <name> <Type> goto <label> else goto <label>`<br>`<label> match <name> <Type>`<br>`<label> case <Enum.variant> bind none none goto <label>`<br>`<label> case <Enum.variant> bind <name> <Type> goto <label>`<br>`<label> return ok none`<br>`<label> return ok <name>`<br>`<label> return error <name>` |

## `test`

| Predicate | Rows | Shape |
| --- | --- | --- |
| `typeParam` | one or more (`none` alone when empty) | `none`<br>`<Type> any\|plain` |
| `input` | one or more (`none` alone when empty) | `none`<br>`<name> <Type> borrowed\|borrowedMutable\|owned\|value` |
| `output` | exactly one | `none`<br>`<Type>` |
| `outputOwner` | exactly one | `none`<br>`caller`<br>`<name>` |
| `raises` | exactly one | `none`<br>`<Type>` |
| `effect` | one or more (`none` alone when empty) | `none`<br>`connect\|listen\|read\|readWrite\|spawn\|write <module.resource>` |
| `uses` | one or more (`none` alone when empty) | `none`<br>`<name>` |
| `memory` | exactly one | `heap false\|true` |
| `async` | exactly one | `false\|true` |
| `maxRecursion` | exactly one | `none`<br>`<integer>` |
| `label` | zero or more | `<label> loopKind counted\|doWhile\|forEach\|forever\|none\|while`<br>`<label> within none`<br>`<label> within <label>`<br>`<label> maxIterations <integer>`<br>`<label> maxIterations <name>`<br>`<label> maxIterations unbounded`<br>`<label> counter <name>`<br>`<label> over <name>`<br>`<label> because "<text>"`<br>`<label> purpose "<text>"`<br>`<label> rationale "<text>"`<br>`<label> risk concurrency\|data\|failure\|memory\|security\|timing "<text>"`<br>`<label> note "<text>"`<br>`<label> todo "<text>"` |
| `let` | zero or more | `<name> immutable\|mutable <Type> <literal\|name\|unset>` |
| `at` | zero or more | `<label> do <name>`<br>`<label> start <name>`<br>`<label> start <name> into <name>`<br>`<label> join <name>`<br>`<label> cancel <name>`<br>`<label> awaitSlot <name>`<br>`<label> defer <name>`<br>`<label> set <name> <name>`<br>`<label> goto <label>`<br>`<label> branch if <name> goto <label> else goto <label>`<br>`<label> branch ifError <name> goto <label> else goto <label>`<br>`<label> branch ifNext <name> bind <name> <Type> goto <label> else goto <label>`<br>`<label> match <name> <Type>`<br>`<label> case <Enum.variant> bind none none goto <label>`<br>`<label> case <Enum.variant> bind <name> <Type> goto <label>`<br>`<label> return ok none`<br>`<label> return ok <name>`<br>`<label> return error <name>` |

## `call`

| Predicate | Rows | Shape |
| --- | --- | --- |
| `in` | exactly one | `<name>` |
| `invokes` | exactly one | `<target>` |
| `invokesReference` | exactly one | `<name>` |
| `arg` | one or more (`none` alone when empty) | `none`<br>`<name> <Type> <name> copy\|give\|lend\|lendMutable` |
| `out` | exactly one | `none`<br>`<name> <Type>` |
| `ownedBy` | exactly one | `none`<br>`<name>` |
| `cleanedBy` | exactly one | `none`<br>`<name>` |
| `borrows` | exactly one | `none`<br>`<name>` |
| `catch` | exactly one | `none`<br>`<name> <Type>` |

## `task`

| Predicate | Rows | Shape |
| --- | --- | --- |
| `in` | exactly one | `<name>` |
| `invokes` | exactly one | `<target>` |
| `invokesReference` | exactly one | `<name>` |
| `arg` | one or more (`none` alone when empty) | `none`<br>`<name> <Type> <name> copy\|give\|lend\|lendMutable` |
| `out` | exactly one | `none`<br>`<name> <Type>` |
| `ownedBy` | exactly one | `none`<br>`<name>` |
| `cleanedBy` | exactly one | `none`<br>`<name>` |
| `borrows` | exactly one | `none`<br>`<name>` |
| `catch` | exactly one | `none`<br>`<name> <Type>` |

## `cleanup`

| Predicate | Rows | Shape |
| --- | --- | --- |
| `in` | exactly one | `<name>` |
| `call` | exactly one | `<name>` |
| `cleans` | exactly one | `<name>` |
| `onFailure` | exactly one | `suppress\|trap` |
| `because` | exactly one | `"<text>"` |

## `region`

| Predicate | Rows | Shape |
| --- | --- | --- |
| `in` | exactly one | `<name>` |
| `strategy` | exactly one | `arena` |
| `capacity` | exactly one | `<integer>` |
| `released` | exactly one | `atProcessExit\|atReturn` |

## `taskGroup`

| Predicate | Rows | Shape |
| --- | --- | --- |
| `in` | exactly one | `<name>` |
| `limit` | exactly one | `<integer>` |


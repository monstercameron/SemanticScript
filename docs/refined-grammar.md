# Refined syntax: row shapes

Generated from `semanticscript/compiler/refined/shapes.py`. Do not edit by hand.

Every row is `<subject> <predicate> <payload>`. Context rows (`purpose`, `invariant`, `verifies`, `rationale`, `risk`, `note`, `todo`, `deprecated`) come directly after the `is` row, in that order.

## `project`

| Predicate | Rows | Shape |
| --- | --- | --- |
| `target` | exactly one | `console\|library` |
| `version` | exactly one | `"<text>"` |
| `language` | exactly one | `refined <integer>` |
| `standardLibrary` | exactly one | `<integer>` |
| `allows` | one or more (`none` alone when empty) | `none`<br>`connect\|listen\|load\|read\|readWrite\|spawn\|write <module.resource> none`<br>`connect\|listen\|load\|read\|readWrite\|spawn\|write <module.resource> "<text>"` |
| `requires` | one or more (`none` alone when empty) | `none`<br>`<name> "<text>" "<text>"` |
| `includesModule` | one or more | `<dotted.path>` |
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
| `typeParameter` | one or more (`none` alone when empty) | `none`<br>`<Type> any\|plain` |
| `field` | one or more | `<name> <Type>` |

## `enum`

| Predicate | Rows | Shape |
| --- | --- | --- |
| `typeParameter` | one or more (`none` alone when empty) | `none`<br>`<Type> any\|plain` |
| `variant` | one or more | `<name> none`<br>`<name> <Type>` |

## `alias`

| Predicate | Rows | Shape |
| --- | --- | --- |
| `typeParameter` | exactly one | `none` |
| `aliasOf` | exactly one | `<Type>` |
| `indexes` | exactly one | `none`<br>`<Type>` |

## `typeInstance`

| Predicate | Rows | Shape |
| --- | --- | --- |
| `in` | exactly one | `none`<br>`<name>` |
| `instantiates` | exactly one | `<Type> <Type>...` |

## `constant`

| Predicate | Rows | Shape |
| --- | --- | --- |
| `type` | exactly one | `<Type>` |
| `value` | exactly one | `<literal>` |

## `table`

| Predicate | Rows | Shape |
| --- | --- | --- |
| `rowType` | exactly one | `<Type>` |
| `row` | one or more | `<name> <integer>` |
| `cell` | one or more | `<name> <name> <literal\|name>` |

## `capability`

| Predicate | Rows | Shape |
| --- | --- | --- |
| `grants` | one or more | `connect\|listen\|load\|read\|readWrite\|spawn\|write <module.resource> none`<br>`connect\|listen\|load\|read\|readWrite\|spawn\|write <module.resource> "<text>"` |

## `operationInstance`

| Predicate | Rows | Shape |
| --- | --- | --- |
| `in` | exactly one | `none`<br>`<name>` |
| `instantiates` | exactly one | `<name> <Type>...` |

## `operationType`

| Predicate | Rows | Shape |
| --- | --- | --- |
| `typeParameter` | one or more (`none` alone when empty) | `none`<br>`<Type> any\|plain` |
| `input` | one or more (`none` alone when empty) | `none`<br>`<name> <Type> borrowed\|borrowedMutable\|copied\|owned` |
| `output` | exactly one | `none`<br>`<Type>` |
| `outputOwnedBy` | exactly one | `none`<br>`caller`<br>`<name>` |
| `raises` | exactly one | `none`<br>`<Type>` |
| `effect` | one or more (`none` alone when empty) | `none`<br>`connect\|listen\|load\|read\|readWrite\|spawn\|write <module.resource>` |
| `async` | exactly one | `false\|true` |

## `operation`

| Predicate | Rows | Shape |
| --- | --- | --- |
| `typeParameter` | one or more (`none` alone when empty) | `none`<br>`<Type> any\|plain` |
| `input` | one or more (`none` alone when empty) | `none`<br>`<name> <Type> borrowed\|borrowedMutable\|copied\|owned` |
| `output` | exactly one | `none`<br>`<Type>` |
| `outputOwnedBy` | exactly one | `none`<br>`caller`<br>`<name>` |
| `raises` | exactly one | `none`<br>`<Type>` |
| `effect` | one or more (`none` alone when empty) | `none`<br>`connect\|listen\|load\|read\|readWrite\|spawn\|write <module.resource>` |
| `uses` | one or more (`none` alone when empty) | `none`<br>`<name>` |
| `memoryHeap` | exactly one | `false\|true` |
| `async` | exactly one | `false\|true` |
| `maxRecursion` | exactly one | `none`<br>`<integer>` |
| `label` | one or more | `<label> purpose "<text>"`<br>`<label> rationale "<text>"`<br>`<label> risk concurrency\|data\|failure\|memory\|security\|timing "<text>"`<br>`<label> note "<text>"`<br>`<label> todo "<text>"`<br>`<label> loopKind counted\|doWhile\|forEach\|forever\|none\|while`<br>`<label> within none`<br>`<label> within <label>`<br>`<label> maxIterations <integer>`<br>`<label> maxIterations <name>`<br>`<label> maxIterations unbounded`<br>`<label> counter <name>`<br>`<label> over <name>` |
| `let` | one or more (`none` alone when empty) | `none`<br>`<name> <Type> <literal\|name\|unset> immutable\|mutable` |
| `at` | one or more | `<label> do <name>`<br>`<label> start <name> into none`<br>`<label> start <name> into <name>`<br>`<label> join <name>`<br>`<label> cancel <name>`<br>`<label> awaitSlot <name>`<br>`<label> defer <name>`<br>`<label> set <name> <name>`<br>`<label> goto <label>`<br>`<label> branch if <name> goto <label> else goto <label>`<br>`<label> branch ifError <name> goto <label> else goto <label>`<br>`<label> branch ifNext <name> bind <name> <Type> goto <label> else goto <label>`<br>`<label> match <name> <Type>`<br>`<label> case <Enum.variant> bind none none goto <label>`<br>`<label> case <Enum.variant> bind <name> <Type> goto <label>`<br>`<label> return ok none`<br>`<label> return ok <name>`<br>`<label> return error <name>` |

## `test`

| Predicate | Rows | Shape |
| --- | --- | --- |
| `typeParameter` | one or more (`none` alone when empty) | `none`<br>`<Type> any\|plain` |
| `input` | one or more (`none` alone when empty) | `none`<br>`<name> <Type> borrowed\|borrowedMutable\|copied\|owned` |
| `output` | exactly one | `none`<br>`<Type>` |
| `outputOwnedBy` | exactly one | `none`<br>`caller`<br>`<name>` |
| `raises` | exactly one | `none`<br>`<Type>` |
| `effect` | one or more (`none` alone when empty) | `none`<br>`connect\|listen\|load\|read\|readWrite\|spawn\|write <module.resource>` |
| `uses` | one or more (`none` alone when empty) | `none`<br>`<name>` |
| `memoryHeap` | exactly one | `false\|true` |
| `async` | exactly one | `false\|true` |
| `maxRecursion` | exactly one | `none`<br>`<integer>` |
| `label` | one or more | `<label> purpose "<text>"`<br>`<label> rationale "<text>"`<br>`<label> risk concurrency\|data\|failure\|memory\|security\|timing "<text>"`<br>`<label> note "<text>"`<br>`<label> todo "<text>"`<br>`<label> loopKind counted\|doWhile\|forEach\|forever\|none\|while`<br>`<label> within none`<br>`<label> within <label>`<br>`<label> maxIterations <integer>`<br>`<label> maxIterations <name>`<br>`<label> maxIterations unbounded`<br>`<label> counter <name>`<br>`<label> over <name>` |
| `let` | one or more (`none` alone when empty) | `none`<br>`<name> <Type> <literal\|name\|unset> immutable\|mutable` |
| `at` | one or more | `<label> do <name>`<br>`<label> start <name> into none`<br>`<label> start <name> into <name>`<br>`<label> join <name>`<br>`<label> cancel <name>`<br>`<label> awaitSlot <name>`<br>`<label> defer <name>`<br>`<label> set <name> <name>`<br>`<label> goto <label>`<br>`<label> branch if <name> goto <label> else goto <label>`<br>`<label> branch ifError <name> goto <label> else goto <label>`<br>`<label> branch ifNext <name> bind <name> <Type> goto <label> else goto <label>`<br>`<label> match <name> <Type>`<br>`<label> case <Enum.variant> bind none none goto <label>`<br>`<label> case <Enum.variant> bind <name> <Type> goto <label>`<br>`<label> return ok none`<br>`<label> return ok <name>`<br>`<label> return error <name>` |

## `call`

| Predicate | Rows | Shape |
| --- | --- | --- |
| `in` | exactly one | `<name>` |
| `invokes` | exactly one | `<target>` |
| `invokesReference` | exactly one | `<name>` |
| `argument` | one or more (`none` alone when empty) | `none`<br>`<name> <Type> <name> copy\|give\|lend\|lendMutable` |
| `result` | exactly one | `none`<br>`<name> <Type>` |
| `ownedBy` | exactly one | `none`<br>`<name>` |
| `cleanedBy` | exactly one | `none`<br>`<name>` |
| `borrows` | exactly one | `none`<br>`<name>` |
| `catch` | exactly one | `none`<br>`<name> <Type>` |
| `suppresses` | one or more (`none` alone when empty) | `none`<br>`<Enum.variant>` |

## `task`

| Predicate | Rows | Shape |
| --- | --- | --- |
| `in` | exactly one | `<name>` |
| `invokes` | exactly one | `<target>` |
| `invokesReference` | exactly one | `<name>` |
| `argument` | one or more (`none` alone when empty) | `none`<br>`<name> <Type> <name> copy\|give\|lend\|lendMutable` |
| `result` | exactly one | `none`<br>`<name> <Type>` |
| `ownedBy` | exactly one | `none`<br>`<name>` |
| `cleanedBy` | exactly one | `none`<br>`<name>` |
| `borrows` | exactly one | `none`<br>`<name>` |
| `catch` | exactly one | `none`<br>`<name> <Type>` |
| `suppresses` | one or more (`none` alone when empty) | `none`<br>`<Enum.variant>` |

## `cleanup`

| Predicate | Rows | Shape |
| --- | --- | --- |
| `in` | exactly one | `<name>` |
| `runs` | exactly one | `<name>` |
| `cleans` | exactly one | `<name>` |
| `onError` | exactly one | `suppress\|trap` |

## `region`

| Predicate | Rows | Shape |
| --- | --- | --- |
| `in` | exactly one | `<name>` |
| `strategy` | exactly one | `arena` |
| `maxBytes` | exactly one | `<integer>` |
| `released` | exactly one | `atProcessExit\|atReturn` |

## `taskGroup`

| Predicate | Rows | Shape |
| --- | --- | --- |
| `in` | exactly one | `<name>` |
| `maxTasks` | exactly one | `<integer>` |
| `catch` | exactly one | `none`<br>`<name> <Type>` |
| `suppresses` | one or more (`none` alone when empty) | `none`<br>`<Enum.variant>` |


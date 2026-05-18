# SemanticScript

> **SemanticScript**: a compiled application language for agent-authored software, competing with Node/Python at the app layer, but deploying more like Go. Its source is a flat, line-oriented, high-context semantic tape where every executable line is an atomic English-explicit semantic record.

The point is not to make code short. The point is to make code **locally understandable inside an agent attention window**.

SemanticScript is agent-first, not human-first. Human readability is useful, but it is not the design center.

A normal language compresses meaning into nesting, scope, syntax, conventions, and runtime behavior. SemanticScript should do the opposite:

> Expand meaning into named lines, explicit effects, explicit failure flow, explicit time behavior, explicit cleanup, and preserved comments.

---

# 1. Core thesis

SemanticScript is not a human-friendly scripting language.

It is an **agent-first application language**.

It is not prose.

It is not ordinary code with English-looking keywords.

It is a **controlled English command language** where every verb has a strict schema, every symbol carries contextual meaning, and every line is designed to be useful to an agent when retrieved as a local attention unit.

The surface uses high-context English words because LLMs have strong learned priors over English and code. The structure uses PascalCase, camelCase, and dot.paths so the compiler and tools still see stable machine symbols.

The primary reader is not a human scanning for terseness.

The primary reader is an LLM trying to preserve intent, effects, failure paths, time behavior, and cleanup behavior while editing code.

It should be good for:

```text
console apps
web servers
workers
CLI tools
API services
background jobs
data processing tasks
```

It should compete with:

```text
Node
Python
Go
Bun
Deno
FastAPI
Express
Flask
```

But it should not imitate their source style.

Node/Python are good because they are fast to write. SemanticScript should be good because it is **hard to misunderstand**.

The language exists because agentic coding changes the tradeoff:

```text
Humans prefer compressed syntax.
Agents benefit from expanded context.
```

So SemanticScript should be long, explicit, regular, and brutally inspectable.

Verbosity is not a failure mode here. Verbosity is the representation strategy.

SemanticScript practices **context-maxxing**: it spends tokens to keep local meaning alive.

The source should deliberately repeat names, types, effects, and branch targets when that repetition gives the agent more stable anchors.

```text
English verb
camelCase contextual symbol
PascalCase type or error category
dot.path dependency or namespace
```

Example:

```text
bindError accountBalanceLookupError AccountLookupError accountBalanceLookupCall
```

This line carries three layers at once:

```text
bindError says what semantic action is happening
accountBalanceLookupError says what local meaning the value has
AccountLookupError says what typed category the compiler checks
accountBalanceLookupCall says which call produced the value
```

That redundancy is intentional.

---

# 2. Constitutional laws

The deepest rule:

```text
SemanticScript does not minimize code.
SemanticScript maximizes recoverable context.
```

Everything else follows from this.

## Root laws

```text
1. SemanticScript maximizes recoverable context.
2. Every line does one semantic thing.
3. Hidden behavior is illegal by default.
4. Names must carry local intent.
5. Abstraction must increase context.
```

These are the root laws because they control the shape of every other feature.

If a feature makes source shorter but makes intent harder to recover, it is usually wrong.

If a feature lets meaning disappear into a helper, framework, import, callback, expression, or runtime convention, it violates the language.

## Full constitution

```text
1. Abstraction must increase context.
2. Repetition is acceptable when it preserves context.
3. Every line does one semantic thing.
4. Names must carry local intent.
5. Hidden behavior is illegal by default.
6. Failure is explicit dataflow.
7. Cleanup lives next to acquisition.
8. Async is structured bounded and cancellable.
9. Time is typed.
10. Types encode intent trust memory and layout.
11. Memory behavior is visible.
12. Comments are semantic context.
13. Control flow is graphable.
14. Dependencies expose contracts.
15. Humans review summaries; agents edit source.
16. Source optimizes for attention-local reasoning.
17. Cleverness is a defect.
18. Every meaningful element is name-addressable.
19. Trust boundaries are explicit.
20. Observability is semantic.
```

## Context laws

```text
Abstraction must increase context.
Repetition is acceptable when it preserves context.
Every line does one semantic thing.
Names must carry local intent.
Source optimizes for attention-local reasoning.
Cleverness is a defect.
Every meaningful element is name-addressable.
```

The source should be boring, explicit, and traceable.

Bad SemanticScript should look obviously bad.

Good SemanticScript should make the next correct edit easy.

## Operational laws

```text
Hidden behavior is illegal by default.
Failure is explicit dataflow.
Cleanup lives next to acquisition.
Async is structured bounded and cancellable.
Time is typed.
Memory behavior is visible.
Control flow is graphable.
Observability is semantic.
```

If something touches the outside world, time, memory, concurrency, storage, network, process state, logs, traces, or metrics, it must be visible in source.

## Boundary laws

```text
Types encode intent trust memory and layout.
Comments are semantic context.
Dependencies expose contracts.
Trust boundaries are explicit.
```

SemanticScript should make it obvious when data crosses from untrusted to trusted, raw to sanitized, internal to public, local to remote, or dependency-owned to application-owned.

Examples of boundary-signaling types:

```text
UntrustedJson
TrustedJson
RawSql
ParameterizedSql
RawHtml
SanitizedHtml
PublicErrorMessage
InternalErrorMessage
RawEmailAddress
NormalizedEmailAddress
UtcMilliseconds
MonotonicMilliseconds
DurationMilliseconds
```

## Workflow law

Humans review intent and impact. Agents edit source.

The raw source is optimized for agents and tools. The human-facing review surface should summarize behavior:

```text
effects changed
routes changed
errors changed
memory changed
async changed
dependencies changed
tests changed
risk summary
```

Example:

```text
Change summary:
  Added priority to Task.
  POST /tasks now accepts priority.
  Missing priority defaults to Normal.
  No new network effects.
  No new async calls.
  Task size increased by 1 byte.
  Added 2 tests.
```

## Checkability law

Context is not decoration.

Context is source-level data for compilers, linters, tracers, tests, and agents.

Declared context must be checked when possible.

```text
declared effects must match called effects
declared failures must cover branchable errors
declared async behavior must match start and await behavior
declared memory behavior must match allocation behavior
declared cleanup behavior must match acquired resources
declared dependency contracts must match imported calls
declared invariants should link to checks tests or warnings when possible
```

## Enforcement levels

Not every law blocks compilation, but every law must have a home in the system.

```text
compiler law   required for valid code
linter law     required for agent-safe code
tooling law    required for generated summaries indexes traces and reviews
```

Examples:

```text
failure is explicit dataflow                 compiler law
async work must be awaited or detached       compiler law
declared effects must match called effects   compiler law
names must carry local intent                linter law
comments are semantic context                linter law
humans review summaries agents edit source   tooling law
```

The constitution should be enforced by the parser, compiler, linter, semantic index, runtime trace system, and review tools together.

---

# 3. Abstraction law

Abstraction is only valid when it increases total context.

Not when it reduces typing.

Not when it makes code look cleaner.

Not when it satisfies DRY.

Only when the abstraction carries more semantic payload than the repeated lines alone.

```text
abstractionValue = explicitContract + strongerChecks + reusableContext + betterTraceability
```

An abstraction is allowed only if:

```text
abstractionValue > lostLocalDetail
```

So the question is not:

```text
Can we hide these repeated lines?
```

The question is:

```text
Can we wrap these lines in something that gives the agent and compiler more knowledge than the raw lines provided?
```

Traditional languages often treat abstraction as less code.

SemanticScript treats abstraction as more meaning per referenced node.

## Anti-DRY rule

Traditional DRY says:

```text
Do not repeat yourself.
```

SemanticScript says:

```text
Do not hide yourself.
```

Repeat when repetition preserves context.

Abstract only when the abstraction becomes a better context container than the repeated code.

```text
prefer repetition over context-losing abstraction
permit abstraction only when it creates a richer semantic node
```

## Bad abstraction

This is bad:

```text
returnBadRequest invalidJson
```

It hides:

```text
status code
response format
error code mapping
JSON encoding behavior
possible encoding failure
return behavior
memory use
effects
```

It saves lines, but destroys context.

That is a human-first abstraction.

## Good abstraction

This is better:

```text
operation buildStandardJsonErrorResponse
input buildStandardJsonErrorResponse status HttpStatus
input buildStandardJsonErrorResponse errorCode ErrorCode
input buildStandardJsonErrorResponse publicMessage PublicErrorMessage
output buildStandardJsonErrorResponse HttpResponse
effect buildStandardJsonErrorResponse write http.response
memory buildStandardJsonErrorResponse heap no
memory buildStandardJsonErrorResponse arena request 64KiB
purpose buildStandardJsonErrorResponse "Build a stable public JSON error envelope for HTTP handlers"
invariant buildStandardJsonErrorResponse "Response body must not include internal dependency error details"
invariant buildStandardJsonErrorResponse "Response JSON shape is stable across all handlers"
```

Then the call site still remains explicit:

```text
call invalidJsonResponseBuildCall buildStandardJsonErrorResponse
arg invalidJsonResponseBuildCall status HttpStatus.BadRequest
arg invalidJsonResponseBuildCall errorCode ErrorCode.InvalidJson
arg invalidJsonResponseBuildCall publicMessage PublicErrorMessage.InvalidJsonBody
run invalidJsonResponseBuildCall
bind invalidJsonResponse HttpResponse invalidJsonResponseBuildCall
returnValue invalidJsonResponse
```

This abstraction is acceptable because it adds:

```text
stable response envelope
security invariant
memory policy
effect declaration
typed public message
shared schema contract
traceable call identity
```

The sum is greater than the parts.

## Abstraction admission test

Every abstraction should pass this checklist:

```text
declares purpose
declares inputs and outputs
declares effects
declares memory behavior
declares failure behavior
declares time or async behavior when relevant
declares invariants
improves traceability
improves testability
reduces ambiguity more than it reduces visible detail
```

If not, reject it.

## Abstraction kinds

SemanticScript should not have casual helpers.

It should have contract-heavy semantic nodes:

```text
operation
policy
resource
codec
schema
validator
mapper
workflowStep
adapter
boundary
taskGroup
retryPolicy
timeoutBudget
errorPolicy
```

Each abstraction kind exists because it adds metadata.

Examples:

```text
validator createTaskRequestValidator
input createTaskRequestValidator JsonObject
output createTaskRequestValidator Result CreateTaskRequest CreateTaskRequestParseError
guarantee createTaskRequestValidator "title is trimmed and non-empty"
```

```text
codec createTaskResponseJsonCodec
schema createTaskResponseJsonCodec CreateTaskResponse
unknownFields createTaskResponseJsonCodec reject
guarantee createTaskResponseJsonCodec "Only public response fields are serialized"
```

```text
retryPolicy databaseReadRetryPolicy
maxAttempts databaseReadRetryPolicy 3
initialDelay databaseReadRetryPolicy DurationMilliseconds.50
maximumDelay databaseReadRetryPolicy DurationMilliseconds.500
jitter databaseReadRetryPolicy yes
```

These are good abstractions because they are declarative, inspectable, and policy-rich.

## Better summaries

A valid abstraction should produce a better agent summary.

Bad abstraction summary:

```text
Calls helper.
```

Good abstraction summary:

```text
Converts untrusted JSON into a validated CreateTaskRequest.
Guarantees title is trimmed and non-empty.
Can fail with InvalidJsonField or TitleRequired.
Allocates only from request arena.
Has no external effects.
```

That is the bar.

Final law:

```text
An abstraction is valid only when the named abstraction plus its contract gives the agent more actionable context than the expanded lines alone.
```

---

# 4. The shape of the language

Everything is one line.

No nested expressions.

No deep blocks.

No braces.

No semicolons.

No commas.

No hidden indentation semantics.

No arbitrary callback closures.

No implicit exception paths.

No floating promises.

No hidden async.

No unbounded goroutines.

A source file is a **linear tape**:

```text
verb subject object object object
verb subject object object object
verb subject object object object
```

A line is either:

```text
declaration line
context line
action line
control line
comment line
```

## Semantic line contract

Every executable line must be an atomic semantic record.

Atomic means:

```text
one line names one fact action control decision or metadata assertion
one line has one primary verb
one line has one primary subject
one line avoids hidden work
one line avoids nested computation
```

Contextual means:

```text
repeat the operation call resource branch or defer identity when useful
name the value role in the symbol itself
name the type or error category when the compiler can check it
name the effect timing cleanup or failure path instead of implying it
```

Bad:

```text
run it
bind result Customer
branch failed
return error
```

Good:

```text
run customerLookupCall
bindOk existingCustomer Customer customerLookupCall
branchIfError customerLookupCall customerLookupFailed
returnError customerLookupFailure
```

No line should rely on pronouns, unnamed previous results, implicit current state, or a reader remembering a hidden expression tree.

## Parser model

The parser should be intentionally simple.

```text
first token = verb
remaining tokens = arguments
newline = end of line
# = comment
```

The tokenizer still has to be exact. Strings, escapes, comments, paths, and malformed lines must have canonical rules. But the parser should not need to recover meaning from nesting, precedence, overloads, hidden scopes, or expression trees.

Every executable verb should have a fixed line schema.

Examples:

```text
call callName targetPath
arg callName argumentName valueName
run callName
start callName
await callName
bindOk valueName TypeName callName
bindError errorName ErrorTypeName callName
branchIfError callName labelName
returnValue valueName
returnError errorName
```

The goal is that a single retrieved line remains semantically useful even when an agent sees it outside the full operation.

```text
call accountBalanceLookupCall database.accounts.findBalance
arg accountBalanceLookupCall accountId accountId
timeout accountBalanceLookupCall accountLookupTimeout
cancelOn accountBalanceLookupCall requestCancellationToken
branchIfError accountBalanceLookupCall accountBalanceLookupFailed
```

Each line repeats the call identity because the line is an attention unit, not just a token-saving instruction inside a human-readable block.

## Lines as attention units

SemanticScript source is optimized for partial retrieval.

An agent should be able to retrieve a line or small group and still see:

```text
what operation or call the line belongs to
what value is being produced or consumed
what type category is involved
what effect or failure path exists
what cleanup or timing rule applies
```

This is why SemanticScript prefers explicit local repetition over distant inference.

The compiler can remove redundancy from the generated program. The source should preserve redundancy for the agent.

## No context collapse

Context collapse is when a line becomes short by pushing meaning somewhere else.

SemanticScript should reject or warn on context collapse:

```text
unnamed previous result
implicit current object
implicit current operation
implicit current cancellation token
implicit current timeout
implicit exception path
helper call with undeclared effects
cleanup hidden inside a dependency call
branch label that does not name the failure reason
symbol name that hides the domain role
```

The source should spend tokens at the place where the agent needs to reason.

This is the right fit for agents because transformers reason over token sequences. Give the model a sequence where every semantic unit is named, flat, local, and stable.

---

# 5. Syntax rules

## Allowed punctuation

Keep only punctuation that carries high semantic value:

```text
.    namespace and enum path
" "  string literals
#    comments
/    only inside strings like HTTP paths
```

Avoid normal language ceremony:

```text
no ;
no ,
no { }
no ( )
no [ ] in executable code
no generic angle brackets
no indentation dependency
```

## Controlled English only

English words are used as semantic priors, not as free-form programming.

Executable SemanticScript is not natural language.

```text
allowed: fixed verbs with fixed schemas
allowed: explicit symbol names made from English words
allowed: quoted metadata and comments for rationale
rejected: free-form instructions as executable code
rejected: ambiguous verbs whose arguments change meaning by context
rejected: sentences that require interpretation instead of parsing
```

Bad:

```text
look up the customer and return an error if it fails
```

Good:

```text
call customerLookupCall database.customers.findByEmail
arg customerLookupCall email normalizedEmail
run customerLookupCall
bindError customerLookupError DatabaseReadError customerLookupCall
branchIfError customerLookupCall customerLookupFailed
```

Instead of:

```text
Result<Customer, CreateCustomerError>
```

Use:

```text
Result Customer CreateCustomerError
```

Instead of:

```text
SmallString<254>
```

Use:

```text
SmallString 254
```

But in operation bodies, prefer aliases:

```text
type EmailAddress SmallString 254
type CreateCustomerResult Result Customer CreateCustomerError
```

Then use:

```text
output createCustomer CreateCustomerResult
```

---

# 6. Naming is part of the language

Names are not cosmetic. They are context storage.

Bad:

```text
e
err
tmp
r1
result
data
handler
process
value
out
```

Good:

```text
emailNormalizationCall
emailNormalizationError
normalizedEmail
customerLookupCall
customerLookupFailure
databaseConnectionCloseDefer
requestCancellationToken
accountBalanceJsonEncodingCall
```

Use:

```text
PascalCase for types
PascalCase for records
PascalCase for errors
PascalCase for enum variants
camelCase for values
camelCase for calls
camelCase for labels
camelCase for defers
dot.paths for namespaces
```

Examples:

```text
Customer
CustomerId
DatabaseConnection
CreateInvoiceError
InvoiceInsertFailed

customerLookupCall
existingCustomerOption
databaseReadFailure
invoiceCreatedEvent
transactionRollbackDefer
```

## Symbol role suffixes

Role suffixes are part of the context system.

They are not decoration. They tell the agent and tools what kind of semantic object a name represents.

```text
Call        named call object that can be run started awaited bound traced
Error       raw dependency or runtime error value
Failed      branch label reached after a failed operation
Failure     domain failure value returned or mapped from an error
Result      typed success or failure result shape
Option      optional value shape
Request     inbound request value
Response    outbound response value
Token       cancellation authority or capability value
Timeout     duration value used to bound time
Deadline    absolute time bound
Defer       cleanup action registered for operation exit
Group       structured task group select group or logical comment group
Policy      retry timeout memory or validation policy
Codec       encoding or decoding rule set
```

Example distinction:

```text
customerLookupCall       call object
customerLookupError      raw dependency error
customerLookupFailed     branch label
customerLookupFailure    domain failure value
customerLookupResult     typed result value
```

Tools should warn when a symbol role and suffix disagree.

Example diagnostic:

```text
warning roleSuffixMismatch
symbol customerLookupError
reason symbol is used as branch label
suggestion customerLookupFailed
```

The language tools should warn on vague names.

Example diagnostic:

```text
warning vagueName
symbol err
reason symbol binds error from customerLookupCall
suggestion customerLookupError
```

Another:

```text
warning genericCallName
symbol databaseCall
reason call target is database.customers.findByEmail
suggestion customerFindByEmailCall
```

---

# 7. Comments are first-class context

Comments should not be discarded as trivia. They should be preserved in the semantic index and attached to nearby lines or groups.

Supported variants:

```text
# rationale:
# invariant:
# warning:
# agent:
# memory:
# concurrency:
# timing:
# failure:
# security:
# dependency:
# observability:
# test:
# todo:
```

Example:

```text
# rationale: Normalize email before lookup because uniqueness is defined over canonical email values.
call emailNormalizationCall normalizeEmail
```

For multiple lines:

```text
# group customerLookup
# rationale: Customer lookup uses normalizedEmail so duplicate checks are stable across input formats.
# failure: customerLookupError maps to CreateCustomerError.CustomerLookupFailed.
call customerLookupCall database.customers.findByEmail
arg customerLookupCall connection databaseConnection
arg customerLookupCall email normalizedEmail
run customerLookupCall
bindOk existingCustomerOption OptionalCustomer customerLookupCall
bindError customerLookupError DatabaseReadError customerLookupCall
branchIfError customerLookupCall customerLookupFailed
# endGroup customerLookup
```

Groups are not scopes. They do not affect execution. They are attention anchors.

This matters because a future agent can see the reasoning next to the code it is about to modify.

---

# 8. Hard metadata lines

Comments are soft context. Some context should be hard, indexed metadata.

Example:

```text
purpose getAccountBalanceHandler "Return the current account balance as a JSON HTTP response"
invariant getAccountBalanceHandler "Every database await must use requestCancellationToken"
warning getAccountBalanceHandler "Do not expose database driver errors in HTTP response bodies"
```

This lets tools answer:

```text
What is this operation for?
What invariants must not be broken?
What warnings should an agent read before editing?
```

So each serious operation should have:

```text
purpose
invariant
warning
effect
memory
async
input
output
```

---

# 9. Operation structure

An operation should be flat but canonically ordered.

Canonical order for serious operations:

```text
operation declaration
inputs
output
effects
memory
async and timing rules
purpose and invariants
start label
cheap validation
resource acquisition
defer cleanup
core computation
persistence
event emission
success return
failure labels
```

The operation name should repeat in header lines because each header line is independently useful to an agent and independently checkable by tools.

```text
input createCustomer inputEmail EmailAddress
output createCustomer CreateCustomerResult
effect createCustomer write database.customers
memory createCustomer arena request 1MiB
async createCustomer no
```

There is no nesting. Control flow uses labels and branches.

Example shape:

```text
operation createCustomer
input createCustomer inputEmail EmailAddress
input createCustomer inputName DisplayName
output createCustomer CreateCustomerResult
effect createCustomer read database.customers
effect createCustomer write database.customers
effect createCustomer emit customer.created
memory createCustomer heap no
memory createCustomer arena request 1MiB
async createCustomer no

purpose createCustomer "Create one customer after validating email uniqueness"
invariant createCustomer "customer.created is emitted only after database insert succeeds"
warning createCustomer "Do not use raw inputEmail for uniqueness checks"

label startCreateCustomer

# action lines here

label emailIsInvalid
# failure lines here

label databaseWriteFailed
# failure lines here
```

---

# 10. Function calls

A call is not a nested expression. It is a named object.

The call object exists so the agent can inspect and patch each part of the operation without reconstructing a nested expression.

```text
call customerLookupCall database.customers.findByEmail
arg customerLookupCall connection databaseConnection
arg customerLookupCall email normalizedEmail
run customerLookupCall
bindOk existingCustomerOption OptionalCustomer customerLookupCall
bindError customerLookupError DatabaseReadError customerLookupCall
branchIfError customerLookupCall customerLookupFailed
```

This is longer than:

```js
const customer = await db.customers.findByEmail(email)
```

But the SemanticScript version exposes:

```text
call identity
target function
named arguments
execution point
success binding
error binding
error branch
```

Canonical call lifecycle:

```text
declare call identity and target
attach named arguments
attach timing and cancellation when applicable
execute with run or start
await if started
bind success value when available
bind error value when fallible
branch on failure when fallible
```

The call object is a semantic node. Tools can inspect it, trace it, patch it, and measure it.

---

# 11. Return styles

For result-returning operations:

```text
returnOk savedCustomer
returnError databaseWriteFailure
```

For plain-return operations:

```text
returnValue httpResponse
```

No `ret_err`.

Use full English.

Bad:

```text
ret_err err_db_read
```

Good:

```text
returnError databaseReadFailure
```

---

# 12. Failure flow

No exceptions.

No generic catch-all by default.

No hidden throws.

Every fallible call must bind and branch.

```text
bindError customerLookupError DatabaseReadError customerLookupCall
branchIfError customerLookupCall customerLookupFailed
```

Then later:

```text
label customerLookupFailed
makeError customerLookupFailure CreateCustomerError.CustomerLookupFailed customerLookupError
returnError customerLookupFailure
```

Use three different concepts:

```text
customerLookupError      raw dependency error
customerLookupFailed     branch label
customerLookupFailure    domain failure value
```

That distinction helps agents enormously.

---

# 13. Cleanup with defer

Cleanup belongs next to acquisition.

Cleanup is not hidden finally behavior. It is a named semantic record.

Every resource acquisition should be followed by an explicit cleanup line unless ownership is returned, moved, or intentionally leaked with a warning.

```text
call databaseOpenCall database.openConnection
arg databaseOpenCall database databaseClient
run databaseOpenCall
bindOk databaseConnection DatabaseConnection databaseOpenCall
bindError databaseOpenError DatabaseOpenError databaseOpenCall
branchIfError databaseOpenCall databaseOpenFailed

deferLog databaseConnectionCloseDefer database.closeConnection databaseConnection
```

For async cleanup:

```text
deferAwaitLog databaseConnectionCloseDefer database.closeConnection databaseConnection
```

Cleanup verbs should say what happens to cleanup failure:

```text
deferLog          run cleanup at exit and log cleanup failure
deferAwaitLog     await async cleanup at exit and log cleanup failure
deferWhenExitLog  run cleanup only when exit-time Bool is true and log cleanup failure
```

For transactions:

```text
var transactionShouldRollback Bool true
deferWhenExitLog transactionRollbackDefer transactionShouldRollback database.rollbackTransaction invoiceTransaction

# later, after commit succeeds
set transactionShouldRollback false
```

Important rule:

```text
deferWhenExitLog reads the Bool variable at operation exit time
```

So this is correct:

```text
var transactionShouldRollback Bool true
deferWhenExitLog transactionRollbackDefer transactionShouldRollback database.rollbackTransaction invoiceTransaction
set transactionShouldRollback false
```

This avoids stale computed conditions.

---

# 14. Project scaling

SemanticScript should be **monofile-first**, not monofile-only.

The canonical agent view is one linear project tape.

A project can be stored as:

```text
one large file
many files
generated canonical tape
vendored dependency interface tape
```

But the agent-facing view should be flattenable:

```text
project manifest
dependency contracts
module declarations
types
records
errors
resources
operations
tests
```

File boundaries should not be semantically important.

Modules are logical labels, not necessarily files.

Example:

```text
project AccountServer
target webServer
target console
runtime AgentRuntime 0.1

section project.dependencies
dependency standard.http version 0.1 source standard
dependency standard.json version 0.1 source standard
dependency standard.time version 0.1 source standard
dependency database.postgres version 0.3 source registry integrity "sha256:abc123"

section module.account.types
module account

section module.account.operations
operation getAccountBalanceHandler
```

The tooling can shard or merge files, but the agent can always ask for:

```text
canonicalTape AccountServer
sliceOperation getAccountBalanceHandler
sliceModule account
sliceDependency database.postgres
```

---

# 15. Dependencies and imports

Dependencies must not be black boxes.

A dependency should expose a **contract tape**: exported types, callable operations, effects, errors, async behavior, memory behavior.

Example:

```text
dependency database.postgres version 0.3 source registry integrity "sha256:abc123"
dependencyEffect database.postgres network.tcp
dependencyEffect database.postgres readWrite database
dependencyExports database.postgres DatabaseClient DatabaseConnection DatabaseTransaction DatabaseOpenError DatabaseReadError DatabaseWriteError
```

Importing should be explicit:

```text
importModule standard.http as http
importModule standard.json as json
importModule database.postgres as postgres
```

No wildcard import that silently dumps symbols into scope.

A dependency contract might include:

```text
dependencyFunction database.postgres database.openConnection
dependencyFunctionInput database.openConnection database DatabaseClient
dependencyFunctionOutput database.openConnection Result DatabaseConnection DatabaseOpenError
dependencyFunctionEffect database.openConnection network.tcp.connect
dependencyFunctionAsync database.openConnection yes
```

This lets an agent reason about package calls without reading the implementation.

Dependency contracts should preserve the same context-maxxing rule as source files.

They should not merely list exported names. They should expose the facts an agent needs before using or editing a call:

```text
input types
output type
error type
effects
async behavior
cancellation requirements
timeout expectations
resource ownership
cleanup requirements
```

For Node/Python-style ecosystems, this is critical. SemanticScript packages should ship both:

```text
compiled artifact
dependency contract tape
semantic index
effect manifest
```

---

# 16. Console app model

Console apps are explicit operations.

```text
entry console main

operation main
input main console Console
input main environment Environment
input main process Process
output main Result ExitCode MainError
effect main read console.stdin
effect main write console.stdout
effect main read process.arguments
effect main read environment.variables
memory main heap no
memory main arena process 4MiB
async main yes
```

Reading arguments:

```text
call commandLineReadCall process.arguments
arg commandLineReadCall process process
run commandLineReadCall
bind commandLineArguments CommandLineArguments commandLineReadCall
```

Writing output:

```text
call outputWriteCall console.writeLine
arg outputWriteCall console console
arg outputWriteCall text successMessage
run outputWriteCall
bindError outputWriteError ConsoleWriteError outputWriteCall
branchIfError outputWriteCall consoleWriteFailed
```

Even console I/O is explicit.

---

# 17. Web server model

A web server should be a set of declaration lines plus handler operations.

```text
webServer accountHttpServer
serverHost accountHttpServer "0.0.0.0"
serverPort accountHttpServer 8080
route accountHttpServer get "/accounts/:accountId/balance" getAccountBalanceHandler
route accountHttpServer post "/accounts/:accountId/deposit" depositFundsHandler
route accountHttpServer get "/health" healthCheckHandler
```

Handlers are ordinary operations:

```text
operation getAccountBalanceHandler
input getAccountBalanceHandler httpRequest HttpRequest
input getAccountBalanceHandler databaseClient DatabaseClient
input getAccountBalanceHandler clock Clock
output getAccountBalanceHandler HttpResponse
effect getAccountBalanceHandler read http.request.path
effect getAccountBalanceHandler write http.response
effect getAccountBalanceHandler read database.accounts
effect getAccountBalanceHandler read clock.monotonic
memory getAccountBalanceHandler heap no
memory getAccountBalanceHandler arena request 1MiB
async getAccountBalanceHandler yes
```

The route declaration does not hide anything. It just connects HTTP to an operation.

---

# 18. Async model

Async should be explicit and structured.

There are three execution verbs:

```text
run      execute now and bind result immediately
start    begin async work
await    wait for previously started async work
```

Example:

```text
call accountLookupCall database.accounts.findBalance
arg accountLookupCall database databaseClient
arg accountLookupCall accountId accountId
timeout accountLookupCall accountLookupTimeout
cancelOn accountLookupCall requestCancellationToken
start accountLookupCall
await accountLookupCall
bindOk accountBalance AccountBalance accountLookupCall
bindError accountLookupError AccountLookupError accountLookupCall
branchIfError accountLookupCall accountLookupFailed
```

Rules:

```text
A started call must be awaited cancelled or intentionally detached.
Detached async work is illegal by default.
Every web request await should have cancellation or timeout.
Every async failure path must be explicit.
No promise chains.
No anonymous async callbacks.
No implicit event loop behavior.
```

This is how SemanticScript avoids Node's worst debugging traps.

---

# 19. Cancellation and deadlines

Cancellation is a value, not magic.

```text
call requestCancellationTokenReadCall http.requestCancellationToken
arg requestCancellationTokenReadCall request httpRequest
run requestCancellationTokenReadCall
bind requestCancellationToken CancellationToken requestCancellationTokenReadCall
```

Timeouts are explicit values:

```text
const accountLookupTimeout DurationMilliseconds 2000
timeout accountLookupCall accountLookupTimeout
cancelOn accountLookupCall requestCancellationToken
```

Use separate time types:

```text
UtcMilliseconds
MonotonicMilliseconds
DurationMilliseconds
Deadline
```

Rules:

```text
Wall clock is for timestamps.
Monotonic clock is for timeouts and elapsed time.
Timeouts use Duration or Deadline.
No raw integer timeout arguments.
No unbounded await in web handlers unless explicitly allowed with warning comment.
```

Example warning:

```text
# warning: This await has no timeout because server shutdown must wait for all in-flight audit writes.
await auditFlushCall
```

---

# 20. Select and racing async work

For waiting on multiple things:

```text
select accountLookupRace
selectCase accountLookupRace accountLookupCall accountLookupCompleted
selectCase accountLookupRace requestCancellationToken requestWasCancelled
runSelect accountLookupRace
branchSelected accountLookupRace accountLookupCompleted accountLookupFinished
branchSelected accountLookupRace requestWasCancelled requestCancelled
```

No hidden race behavior.

No callback soup.

Every possible completion path has a named branch.

---

# 21. Task groups

Parallel async work should use structured task groups.

```text
taskGroup accountPageLoadTasks maxTasks 4 cancelOnFirstError yes

startInGroup customerLookupCall accountPageLoadTasks
startInGroup recentTransactionsLookupCall accountPageLoadTasks
startInGroup accountLimitsLookupCall accountPageLoadTasks

awaitGroup accountPageLoadTasks
bindGroupError accountPageLoadGroupError AccountPageLoadError accountPageLoadTasks
branchIfGroupError accountPageLoadTasks accountPageLoadFailed
```

Rules:

```text
All tasks in a group must finish cancel or fail before the operation returns.
Task groups can be configured to cancel on first error.
Task group errors must be explicitly mapped.
```

This gives Go-style concurrency power without goroutine leaks.

---

# 22. Multithreading model

Use async tasks for I/O.

Use worker pools for CPU-heavy work.

No anonymous thread spawning by default.

```text
workerPool jsonEncodingWorkerPool threadCount 4 queueCapacity 128
```

Submit named work:

```text
work jsonEncodingWork encodeLargeBalanceResponse
workArg jsonEncodingWork balanceResponse balanceResponse move
submitWork jsonEncodingWork jsonEncodingWorkerPool
awaitWork jsonEncodingWork
bindOk encodedResponseBody JsonBytes jsonEncodingWork
bindError jsonEncodingError JsonEncodingError jsonEncodingWork
branchIfError jsonEncodingWork jsonEncodingFailed
```

Rules:

```text
Work inputs must be copy move shareImmutable shareAtomic or protectedBy.
No shared mutable capture.
No anonymous closures.
No unbounded worker pools.
No implicit global thread pool unless explicitly imported.
```

Shared state must be declared:

```text
shared accountCache AccountCache protectedBy accountCacheMutex
mutex accountCacheMutex
```

Locking:

```text
call accountCacheLockCall mutex.lock
arg accountCacheLockCall mutex accountCacheMutex
run accountCacheLockCall
bindOk accountCacheGuard MutexGuard accountCacheLockCall
bindError accountCacheLockError MutexLockError accountCacheLockCall
branchIfError accountCacheLockCall accountCacheLockFailed

defer accountCacheUnlockDefer mutex.unlock accountCacheGuard
```

Channels are typed and bounded:

```text
channel accountWorkChannel AccountWorkItem capacity 1024
send accountWorkChannel nextWorkItem
receive receivedWorkItem AccountWorkItem accountWorkChannel
branchIfChannelClosed accountWorkChannel accountWorkChannelClosed
```

Unbounded channels should be illegal unless there is an explicit warning and memory budget.

---

# 23. Time-based concepts

Time should be explicit everywhere.

Retries:

```text
const databaseRetryInitialDelay DurationMilliseconds 50
const databaseRetryMaximumDelay DurationMilliseconds 500

retryPolicy databaseReadRetryPolicy maxAttempts 3 initialDelay databaseRetryInitialDelay maximumDelay databaseRetryMaximumDelay jitter yes
useRetry accountLookupCall databaseReadRetryPolicy
```

Sleep:

```text
call retrySleepCall time.sleep
arg retrySleepCall duration databaseRetryInitialDelay
arg retrySleepCall cancellation requestCancellationToken
start retrySleepCall
await retrySleepCall
bindError retrySleepError SleepError retrySleepCall
branchIfError retrySleepCall retrySleepFailed
```

Intervals:

```text
interval heartbeatInterval duration heartbeatDuration
startInterval heartbeatTimer heartbeatInterval
awaitIntervalTick heartbeatTimer
```

Rules:

```text
No raw sleep numbers.
No sleep without cancellation in async operations.
No retry without maxAttempts.
No interval without shutdown cancellation.
No request handler operation may ignore request cancellation.
```

This is where SemanticScript becomes much safer than Node/Python service code.

---

# 24. Example: web handler with async and timeout

A compact but realistic slice:

```text
project AccountServer
target webServer
runtime AgentRuntime 0.1

dependency standard.http version 0.1 source standard
dependency standard.json version 0.1 source standard
dependency standard.time version 0.1 source standard
dependency database.postgres version 0.3 source registry integrity "sha256:abc123"
dependencyEffect database.postgres network.tcp
dependencyEffect database.postgres readWrite database
dependencyExports database.postgres DatabaseClient DatabaseConnection DatabaseOpenError AccountLookupError

module account

type AccountId UuidV7
type MoneyCents I64
type DurationMilliseconds I64
type AccountBalanceResult Result AccountBalance AccountLookupError

record AccountBalance layout row align 16
field AccountBalance accountId AccountId
field AccountBalance availableCents MoneyCents
field AccountBalance pendingCents MoneyCents
field AccountBalance updatedAtUtc UtcMilliseconds

record AccountBalanceResponse layout row align 16
field AccountBalanceResponse accountId AccountId
field AccountBalanceResponse availableCents MoneyCents
field AccountBalanceResponse pendingCents MoneyCents

jsonCodec AccountBalanceResponse strict yes unknownFields reject

webServer accountHttpServer
serverHost accountHttpServer "0.0.0.0"
serverPort accountHttpServer 8080
route accountHttpServer get "/accounts/:accountId/balance" getAccountBalanceHandler

operation getAccountBalanceHandler
input getAccountBalanceHandler httpRequest HttpRequest
input getAccountBalanceHandler databaseClient DatabaseClient
input getAccountBalanceHandler clock Clock
output getAccountBalanceHandler HttpResponse
effect getAccountBalanceHandler read http.request.path
effect getAccountBalanceHandler write http.response
effect getAccountBalanceHandler read database.accounts
effect getAccountBalanceHandler read clock.monotonic
memory getAccountBalanceHandler heap no
memory getAccountBalanceHandler arena request 1MiB
async getAccountBalanceHandler yes

purpose getAccountBalanceHandler "Return the current account balance as a JSON HTTP response"
invariant getAccountBalanceHandler "Every database await must use requestCancellationToken"
warning getAccountBalanceHandler "Never expose raw database errors in the HTTP response body"

label startGetAccountBalanceHandler

# rationale: Read request cancellation first so every later async call can be tied to client disconnects.
call requestCancellationTokenReadCall http.requestCancellationToken
arg requestCancellationTokenReadCall request httpRequest
run requestCancellationTokenReadCall
bind requestCancellationToken CancellationToken requestCancellationTokenReadCall

# rationale: Parse accountId from the route path before any database work.
call accountIdParseCall http.pathParameterAsAccountId
arg accountIdParseCall request httpRequest
arg accountIdParseCall name "accountId"
run accountIdParseCall
bindOk accountId AccountId accountIdParseCall
bindError accountIdParseError AccountIdParseError accountIdParseCall
branchIfError accountIdParseCall accountIdParseFailed

# rationale: Database open is async and must respect request cancellation.
const databaseOpenTimeout DurationMilliseconds 1000
call databaseOpenCall database.openConnection
arg databaseOpenCall database databaseClient
timeout databaseOpenCall databaseOpenTimeout
cancelOn databaseOpenCall requestCancellationToken
start databaseOpenCall
await databaseOpenCall
bindOk databaseConnection DatabaseConnection databaseOpenCall
bindError databaseOpenError DatabaseOpenError databaseOpenCall
branchIfError databaseOpenCall databaseOpenFailed

deferAwaitLog databaseConnectionCloseDefer database.closeConnection databaseConnection

# group accountBalanceLookup
# rationale: Balance lookup is bounded by timeout so one slow database query cannot pin the request forever.
# timing: accountLookupTimeout should stay below the route-level timeout budget.
const accountLookupTimeout DurationMilliseconds 2000
call accountBalanceLookupCall database.accounts.findBalance
arg accountBalanceLookupCall connection databaseConnection
arg accountBalanceLookupCall accountId accountId
timeout accountBalanceLookupCall accountLookupTimeout
cancelOn accountBalanceLookupCall requestCancellationToken
start accountBalanceLookupCall
await accountBalanceLookupCall
bindOk accountBalance AccountBalance accountBalanceLookupCall
bindError accountBalanceLookupError AccountLookupError accountBalanceLookupCall
branchIfError accountBalanceLookupCall accountBalanceLookupFailed
# endGroup accountBalanceLookup

# rationale: Build an explicit response record before JSON encoding so schema changes are localized.
fieldGet availableCents MoneyCents accountBalance availableCents
fieldGet pendingCents MoneyCents accountBalance pendingCents

new accountBalanceResponse AccountBalanceResponse
fieldSet accountBalanceResponse accountId accountId
fieldSet accountBalanceResponse availableCents availableCents
fieldSet accountBalanceResponse pendingCents pendingCents

call jsonEncodingCall json.encodeAccountBalanceResponse
arg jsonEncodingCall value accountBalanceResponse
run jsonEncodingCall
bindOk responseBody JsonBytes jsonEncodingCall
bindError jsonEncodingError JsonEncodingError jsonEncodingCall
branchIfError jsonEncodingCall jsonEncodingFailed

call successResponseBuildCall http.responseJson
arg successResponseBuildCall status HttpStatus.Ok
arg successResponseBuildCall body responseBody
run successResponseBuildCall
bind successResponse HttpResponse successResponseBuildCall

returnValue successResponse

label accountIdParseFailed
call badRequestResponseBuildCall http.responseText
arg badRequestResponseBuildCall status HttpStatus.BadRequest
arg badRequestResponseBuildCall body "invalid account id"
run badRequestResponseBuildCall
bind badRequestResponse HttpResponse badRequestResponseBuildCall
returnValue badRequestResponse

label databaseOpenFailed
call serviceUnavailableResponseBuildCall http.responseText
arg serviceUnavailableResponseBuildCall status HttpStatus.ServiceUnavailable
arg serviceUnavailableResponseBuildCall body "database unavailable"
run serviceUnavailableResponseBuildCall
bind serviceUnavailableResponse HttpResponse serviceUnavailableResponseBuildCall
returnValue serviceUnavailableResponse

label accountBalanceLookupFailed
call accountLookupFailureResponseBuildCall http.responseText
arg accountLookupFailureResponseBuildCall status HttpStatus.InternalServerError
arg accountLookupFailureResponseBuildCall body "account balance lookup failed"
run accountLookupFailureResponseBuildCall
bind accountLookupFailureResponse HttpResponse accountLookupFailureResponseBuildCall
returnValue accountLookupFailureResponse

label jsonEncodingFailed
call jsonEncodingFailureResponseBuildCall http.responseText
arg jsonEncodingFailureResponseBuildCall status HttpStatus.InternalServerError
arg jsonEncodingFailureResponseBuildCall body "response encoding failed"
run jsonEncodingFailureResponseBuildCall
bind jsonEncodingFailureResponse HttpResponse jsonEncodingFailureResponseBuildCall
returnValue jsonEncodingFailureResponse
```

This is longer than JavaScript, but it has radically more local context.

An agent can inspect this and know:

```text
what route this handles
what effects it has
what memory policy applies
what async calls exist
what cancellation token is used
what timeouts exist
what errors are possible
what cleanup runs
what responses are returned
what comments explain placement
```

That is the win.

---

# 25. The language tools matter as much as syntax

SemanticScript should ship with tools designed around agent workflows.

## `agentFormat`

Canonicalizes spacing, line order, naming style, and section layout.

## `agentIndex`

Builds:

```text
symbol graph
call graph
effect graph
failure graph
defer graph
async graph
time graph
memory graph
dependency graph
comment graph
abstraction graph
law compliance graph
test coverage graph
```

## `agentSlice`

Produces a linear context slice for an operation.

Example:

```text
agentSlice operation getAccountBalanceHandler
```

Output should include:

```text
operation body
referenced types
referenced errors
resource declarations
dependency contracts
called operation signatures
related tests
attached comments
warnings and invariants
abstraction contract
```

## `agentLintNames`

Flags vague or non-contextual names.

## `agentCheckLaws`

Checks source against the SemanticScript constitution.

Flags:

```text
line does more than one semantic thing
hidden behavior not declared in effects
failure path hidden or unbound
cleanup not adjacent to acquisition
async work unbounded or uncancelled
raw time integer used where typed time is required
type hides trust or sanitization state
comment attached to no semantic node
control flow not graphable
dependency used without contract
clever compressed helper
meaningful element not name-addressable
trust boundary not explicit
observability emitted without declared effect
declared context not checkable
```

## `agentCheckAsync`

Flags:

```text
started call not awaited
await without timeout
await without cancellation in request operation
task group not closed
detached task without warning
sleep without cancellation
retry without maxAttempts
```

## `agentCheckDefer`

Flags:

```text
resource acquired without cleanup
cleanup registered before acquisition
async cleanup not awaited
transaction rollback condition not mutable
defer references invalid value
```

## `agentCheckAbstraction`

Flags:

```text
abstraction without purpose
abstraction without declared inputs or outputs
abstraction without declared effects
abstraction without declared failure behavior
abstraction without memory behavior
abstraction that hides return behavior
abstraction that hides JSON encoding behavior
abstraction that hides status or error mapping
abstraction that reduces local detail without adding stronger contract
casual helper with vague name
```

## `agentTrace`

Runtime traces should map directly to source call names:

```text
accountBalanceLookupCall started
accountBalanceLookupCall timedOut
databaseConnectionCloseDefer completed
```

This is much better than stack traces full of anonymous callbacks.

## `agentReviewSummary`

Produces the human-facing review surface from source and semantic indexes.

Output should include:

```text
effects changed
routes changed
errors changed
memory changed
async changed
dependencies changed
tests changed
risk summary
```

---

# 26. Anti-features

SemanticScript should deliberately reject many things that Node/Python allow.

```text
no exceptions as normal control flow
no anonymous async callbacks
no floating promises
no wildcard imports
no implicit globals
no top-level side effects
no hidden event listeners
no unbounded task spawning
no unbounded channels
no raw timeout integers
no stringly typed JSON in public handlers
no implicit field access in argument lines
no dynamic monkey patching
no import-time execution
no vague symbol names
no casual helpers
no context-losing abstractions
no abstraction whose contract is weaker than its expanded lines
no line that performs multiple semantic actions
no hidden trust boundary transition
no undeclared observability side effect
no clever compression that reduces recoverable context
```

The language should be opinionated because agents need guardrails.

---

# 27. Refined identity

SemanticScript should not be "a simpler programming language."

It should be:

> An agent-first application language where source code is a controlled English semantic tape made of atomic contextual lines.

The code is long because the context is in the code.

The rules are strict because strictness prevents agent guessing.

The format is flat because agents can modify linear tapes more reliably than nested syntax trees.

The abstractions are contract-heavy because abstraction is valid only when it increases total context.

The runtime targets console apps and web servers first because those are where Node/Python dominate and where async, I/O, errors, and timeouts cause the most debugging pain.

The strongest current description is:

> **SemanticScript is an agent-first, flat, controlled-English, line-oriented application language. Its source is a high-context semantic tape where every executable line is an atomic semantic record with explicit symbols, effects, failure paths, timing, cleanup, and dependency contracts. It competes with Node and Python for console apps and web servers, but uses Go-like deployment discipline, explicit error handling, checked defer cleanup, typed memory/effect declarations, structured async, bounded concurrency, contract-heavy abstractions, and first-class contextual comments so agents can reason linearly instead of guessing through hidden runtime behavior.**

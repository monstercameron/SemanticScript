# AgentScript Syntax Refinement For Transformer Attention

Date: 2026-05-17

This document is about one question:

```text
How should AgentScript syntax change so agent-generated source aligns better
with transformer attention and modern LLM tokenization?
```

This is a syntax and language-shape study.

The target reader and writer is an AI agent. Human readability matters only when
it supports agent correctness, review, and repair.

## Bottom Line

AgentScript should stay explicit, flat, and line-oriented. That is the correct
foundation for transformers.

The refinements needed are not "make it shorter" or "make it look more like
JavaScript/Python." The needed refinements are:

```text
make every relation easier to attend to
make every repeated symbol intentional
make every identifier subtoken-friendly
make every long region chunkable by syntax
make every syntax variant canonical
make every line useful when retrieved alone
```

The main syntax changes recommended:

```text
1. Use exactly one canonical spelling for every verb and primitive target.
2. Require shared stems across call/error/failed/failure lines.
3. Add non-executing group metadata for long or risky regions.
4. Expand variable-tail declarations only when the tail becomes ambiguous.
5. Treat split metadata verbs as future candidates, not default replacements.
6. Add canonical value-level boolean literals.
7. Use identifier segment counts as review heuristics.
8. Use dot-path depth and spelling as review heuristics.
9. Treat long literals as named payloads with metadata.
10. Make section lines real syntax.
11. Move inline comments to standalone typed comment lines in canonical source.
12. Deprecate two-target branch syntax.
13. Replace canonical const/var/set with a stable storage verb carrying scope and mutability fields.
```

The key principle:

```text
Spend tokens on semantic anchors, not syntax variation.
```

## Research Base

### Transformer Attention

The Transformer uses self-attention: each token position produces query, key,
and value vectors. Attention compares queries to keys, weights relevant value
vectors, and lets each token representation mix information from other tokens.
Multi-head attention repeats this through multiple learned relation spaces.

Reference:

```text
Vaswani et al., "Attention Is All You Need"
https://arxiv.org/abs/1706.03762
```

Design hypothesis for AgentScript syntax:

```text
Repeated exact symbols are useful anchors.
Stable role words are useful anchors.
Flat local records reduce hidden structure.
Canonical spelling reduces avoidable ambiguity.
```

When AgentScript writes:

```text
accountBalanceLookupCall
accountBalanceLookupError
accountBalanceLookupFailed
accountBalanceLookupFailure
```

it gives attention repeated lexical material that plausibly helps the model
connect the lifecycle. This is a design hypothesis motivated by self-attention,
not a claim that the Transformer paper proves this exact syntax.

### Subword Tokenization

LLMs do not usually see source as full words. They see subword tokens. Long
identifiers are split into pieces, and the quality of those pieces affects
sequence length and semantic recoverability.

References:

```text
Sennrich et al., "Neural Machine Translation of Rare Words with Subword Units"
https://arxiv.org/abs/1508.07909

Kudo and Richardson, "SentencePiece"
https://arxiv.org/abs/1808.06226

Chirkova and Troshin, "CodeBPE"
https://openreview.net/forum?id=htL4UZ344nF
```

Design hypothesis for AgentScript syntax:

```text
Use common English/code morphemes.
Prefer predictable camelCase and PascalCase boundaries.
Avoid rare abbreviations.
Avoid unbounded compound identifiers.
Use one canonical spelling per concept.
```

### Identifiers In Code Models

Identifier names are not decoration. Code models learn from names. CodeT5 is one
example of research showing that identifier-aware learning improves code
understanding and generation.

Reference:

```text
Wang et al., "CodeT5"
https://arxiv.org/abs/2109.00859
```

Design hypothesis for AgentScript syntax:

```text
AgentScript should treat names as syntax.
Role suffixes should be mandatory where roles exist.
Name stems should align across related records.
Vague names should be invalid or strongly discouraged.
```

### Structure-Aware Code Modeling

Research such as GraphCodeBERT shows that dataflow relationships help code
models. AgentScript should expose dataflow directly in syntax instead of hiding
it inside nested expressions or implicit conventions.

Reference:

```text
Guo et al., "GraphCodeBERT"
https://arxiv.org/abs/2009.08366
```

Design hypothesis for AgentScript syntax:

```text
call, arg, run, bind, branch, return should remain separate records.
The relation should be visible by repeated names.
Do not compress dataflow into expression syntax.
```

### Long Context Weakness

Long context windows do not guarantee reliable use of all tokens. Models can be
weaker when relevant facts sit in the middle of long prompts.

Reference:

```text
Liu et al., "Lost in the Middle"
https://arxiv.org/abs/2307.03172
```

Design hypothesis for AgentScript syntax:

```text
Long regions should have explicit local anchors.
Groups and sections are plausible syntax-level anchors.
Important facts should be repeated at the place where reasoning happens.
```

## What AgentScript Already Gets Right

AgentScript already has several transformer-native properties.

### Flat Line Records

Good:

```text
call customerLookupCall database.customers.findByEmail
arg customerLookupCall email normalizedEmail
run customerLookupCall
bindOk existingCustomer Customer customerLookupCall
bindError customerLookupError DatabaseReadError customerLookupCall
branchIfError customerLookupCall customerLookupFailed
```

This is much easier for attention than:

```text
const existingCustomer = await db.customers.findByEmail(normalizedEmail)
```

The AgentScript form exposes:

```text
call identity
target
argument name
argument value
execution point
success binding
error binding
failure branch
```

Do not compress this.

### Role Suffixes

These suffixes are valuable and should be kept:

```text
Call
Error
Failed
Failure
Result
Option
Request
Response
Token
Timeout
Deadline
Defer
Group
Policy
Codec
```

They give the model stable semantic categories.

### Explicit Failure Flow

Good:

```text
bindError customerLookupError DatabaseReadError customerLookupCall
branchIfError customerLookupCall customerLookupFailed

label customerLookupFailed
makeError customerLookupFailure CreateCustomerError.CustomerLookupFailed customerLookupError
returnError customerLookupFailure
```

This is excellent syntax for attention. It distinguishes:

```text
raw dependency error
control-flow failure label
domain failure value
returned error result
```

## Core Syntax Refinements

### 1. Canonical Surface Only

Every semantic operation should have one spelling.

Canonical:

```text
math.subtractI64
math.multiplyI64
math.divideI64
math.moduloI64
math.equalI64
math.notEqualI64
math.lessThanI64
math.lessThanOrEqualI64
math.greaterThanI64
math.greaterThanOrEqualI64
math.greaterThanOrEqualCByteCount
console.writeIntegerLine
```

Typed domain-width operations should keep the same long-form spelling pattern.
For byte counts, prefer:

```text
math.lessThanCByteCount
math.lessThanOrEqualCByteCount
math.greaterThanCByteCount
math.greaterThanOrEqualCByteCount
```

Do not mix `CByteCount` values with `I64` operation names in canonical examples,
even if both lower to the same machine width.

For C integer compatibility values, use the same type-specific pattern:

```text
math.equalCSignedInt32
math.notEqualCSignedInt32
math.lessThanCSignedInt32
math.greaterThanCSignedInt32
```

Do not compare `CSignedInt32` values through `math.equalI64`; the width and ABI
tokens should match the value type in the operation name.

Do not use new-source aliases:

```text
math.subI64
math.mulI64
math.divI64
math.modI64
math.eqI64
math.neI64
math.ltI64
math.leI64
math.gtI64
math.geI64
console.writeInteger
```

Why:

```text
Aliases split attention.
Aliases split examples.
Aliases split generated-code priors.
Aliases make agent repair less reliable.
```

Rule:

```text
One concept, one spelling.
```

### 2. Shared Stem Requirement

Related names should share an exact stem.

Good:

```text
accountBalanceLookupCall
accountBalanceLookupError
accountBalanceLookupFailed
accountBalanceLookupFailure
```

Bad:

```text
accountFetchCall
balanceReadError
lookupFailed
databaseFailure
```

Refined rule:

```text
If a call can fail, its Call, Error, Failed, and Failure names should share
the same semantic stem unless there is a declared reason not to.
```

Before:

```text
call accountFetchCall database.accounts.findBalance
bindError balanceReadError DatabaseReadError accountFetchCall
branchIfError accountFetchCall lookupFailed

label lookupFailed
makeError databaseFailure AccountError.LookupFailed balanceReadError
returnError databaseFailure
```

After:

```text
call accountBalanceLookupCall database.accounts.findBalance
bindError accountBalanceLookupError DatabaseReadError accountBalanceLookupCall
branchIfError accountBalanceLookupCall accountBalanceLookupFailed

label accountBalanceLookupFailed
makeError accountBalanceLookupFailure AccountError.LookupFailed accountBalanceLookupError
returnError accountBalanceLookupFailure
```

Why:

```text
The repeated stem forms an attention spine.
The role suffix tells the model what each name does.
The exact stem lets an agent patch all related lines together.
```

### 3. Non-Executing Group Metadata

Comment groups are useful, but important regions may need syntax-level group
metadata. This metadata must not create a scope, block, or hidden execution
rule. A group is an attention anchor keyed by name.

Proposed:

```text
group accountBalanceLookup
groupPurpose accountBalanceLookup "Lookup one account balance by normalized account id"
groupInput accountBalanceLookup normalizedAccountId
groupOutput accountBalanceLookup accountBalance
groupError accountBalanceLookup accountBalanceLookupError
groupFailure accountBalanceLookup accountBalanceLookupFailure
groupTiming accountBalanceLookup accountLookupTimeout

call accountBalanceLookupCall database.accounts.findBalance
arg accountBalanceLookupCall accountId normalizedAccountId
timeout accountBalanceLookupCall accountLookupTimeout
run accountBalanceLookupCall
bindOk accountBalance AccountBalance accountBalanceLookupCall
bindError accountBalanceLookupError AccountLookupError accountBalanceLookupCall
branchIfError accountBalanceLookupCall accountBalanceLookupFailed

label accountBalanceLookupFailed
makeError accountBalanceLookupFailure AccountLookupError.LookupFailed accountBalanceLookupError
returnError accountBalanceLookupFailure
```

Group records are non-executing facts:

```text
they do not open or close a block
they do not change name lookup
they do not change control flow
they do not make later lines depend on physical containment
they are useful because the repeated group name becomes a local retrieval anchor
```

Group records should be checkable when possible:

```text
groupInput should name a value consumed by the grouped stem
groupOutput should name a value produced by the grouped stem
groupError should name a raw error value produced by bindError
groupFailure should name a domain failure value produced by declareFailure or makeError
groupTiming should match a timeout, deadline, or timing comment
unchecked group metadata is advisory and should be treated as a warning-level
context claim, not as an executable fact
```

Use syntax-level group metadata for:

```text
multi-call workflows
security boundaries
resource acquisition and cleanup
async regions
retry regions
transaction regions
complex validation
failure-heavy code
long operations
```

Why:

```text
Group metadata creates local headers before detail.
It may reduce lost-in-the-middle risk by restating regional context nearby.
It lets agents retrieve a coherent region by name and stem.
It prevents long local symbols from carrying all regional context.
```

### 4. Section Lines

Make sections real syntax.

Proposed:

```text
section project.dependencies
section module.account.types
section module.account.operations
section operation.createCustomer.validation
section operation.createCustomer.persistence
section operation.createCustomer.failure
```

Rules:

```text
section is a non-executing metadata line
section may appear at top level or inside an operation
section does not create scope
section does not make later lines implicitly belong to it
section lines do not affect execution
section paths use lowerCamel dot paths
section names should be stable retrieval anchors
```

Why:

```text
Transformers may benefit from explicit position/context markers.
Agents need coarse landmarks before editing long files.
Sections let generated syntax carry document structure without nesting.
```

### 5. Selective One-Fact Expansion

Avoid variable-tail declarations when a line becomes a keyword bag whose later
tokens independently change meaning. Do not split every fixed-schema line. A
compact fixed-schema declaration is acceptable when the whole line is one
checkable policy assertion.

Good candidate for expansion:

```text
record Customer layout row align 8
```

Refined:

```text
record Customer
recordLayout Customer row
recordAlign Customer 8
```

Usually keep if the schema is fixed, short, and checkable:

```text
retryPolicy databaseReadRetryPolicy maxAttempts 3 initialDelay databaseReadInitialDelay maximumDelay databaseReadMaximumDelay jitter yes
```

Expand only when policy lines become long, optional-field-heavy, or hard to
review:

```text
retryPolicy databaseReadRetryPolicy
retryMaxAttempts databaseReadRetryPolicy 3
retryInitialDelay databaseReadRetryPolicy databaseReadInitialDelay
retryMaximumDelay databaseReadRetryPolicy databaseReadMaximumDelay
retryJitter databaseReadRetryPolicy yes
```

Usually keep compact type declarations when the arity is conventional:

```text
type EmailAddress SmallString 254
type CreateCustomerResult Result Customer CreateCustomerError
```

Use parameter lines only when the type constructor has many parameters or when
role names are needed to avoid ambiguity:

```text
type EmailAddress SmallString
typeParameter EmailAddress maxBytes 254

type CreateCustomerResult Result
typeParameter CreateCustomerResult success Customer
typeParameter CreateCustomerResult error CreateCustomerError
```

Why:

```text
Unbounded keyword tails make lines less attention-local.
Fixed schemas can remain compact when they preserve one semantic assertion.
Expansion is justified when it adds role names or removes tail ambiguity.
Do not grow surface area just to mechanically split every token.
```

### 6. Be Careful With Overloaded Metadata Verbs

Older memory syntax:

```text
memory main heap no
memory main stack max 16KiB
memory main arena request 1MiB
```

Refined memory syntax:

```text
memoryHeap main no
memoryStackLimit main 16KiB
memoryArena main arena.request
```

Current effect syntax:

```text
effect main write console.stdout
effect main read database.customers
effect main emit customer.created
```

Possible future split:

```text
effectWrite main console.stdout
effectRead main database.customers
effectEmit main customer.created
```

Conservative recommendation:

```text
Do not split memory or effect by default.
Keep the current forms when each line remains one policy assertion.
Consider split verbs only if generated code frequently confuses the tail kind.
If split verbs are introduced, make them canonical replacements, not synonyms.
```

Why:

```text
Specific verbs can improve attention when a tail is genuinely overloaded.
Extra verbs can also fragment the surface and create synonym risk.
The spec's current memory/effect forms are defensible because they are short,
regular, and semantically one assertion per line.
```

### 7. Boolean Literals

Use `true` and `false` only as value-level `Bool` literals. Do not treat this
as a reason to replace existing metadata flags such as `async main no` or policy
fields such as `jitter yes`.

Current:

```text
const trueValueForReport CSignedInt64 1
const falseValueForReport CSignedInt64 0
var foundResult Bool trueValueForReport
```

Refined:

```text
const foundResultInitial Bool true
const notFoundResultInitial Bool false
var foundResult Bool foundResultInitial
```

Why:

```text
The source should express boolean intent as boolean syntax.
Integer-backed representation should not leak into agent-facing code.
The existing yes/no surface can remain for declarative metadata flags.
```

### 8. Identifier Segment Heuristics

Long names are sometimes useful, but unbounded names create excessive subtoken
fragmentation.

Recommended review heuristic:

```text
local value/call/label: 2 to 5 semantic segments plus role suffix
operation names: 2 to 6 semantic segments
type/error/record names: 1 to 5 PascalCase segments
effect paths: 2 to 5 dot-separated segments
```

Good:

```text
customerLookupCall
databaseReadError
customerLookupFailed
normalizedEmail
requestDeadline
invoiceInsertPolicy
```

Needs review:

```text
writeStandardOutputLineConsoleWriteCall
doesOperationNthParamResolveToPointer
userOpCalleeSeventhParamIsPointerCall
```

Preferred repair pattern:

```text
group standardOutputWrite
groupPurpose standardOutputWrite "Write one prepared output line to standard output"
call consoleWriteCall console.writeLine
arg consoleWriteCall text outputLineText
run consoleWriteCall
```

Why:

```text
Move regional context into group syntax.
Keep local names meaningful but bounded.
Use repeated stems and suffixes instead of giant compounds.
Treat these counts as review thresholds until measured against the target model
tokenizer.
```

### 9. Dot-Path Discipline

Dot paths are good attention anchors when regular.

Good:

```text
database.customers.findByEmail
console.stdout
http.response
customer.created
```

Needs review:

```text
db.cust.find
company.platform.internal.service.v2.customer.lookup.by.email
```

Recommended review heuristic:

```text
dot paths use lowercase or lowerCamel segments
dot paths avoid abbreviations unless declared
dot paths usually have 2 to 5 segments
effect paths should name resource and access domain clearly
dependency paths may be longer only at declaration boundaries
```

Why:

```text
Very short abbreviations lose semantics.
Very deep paths create low-signal token chains.
Regular path depth keeps attention focused.
Treat the depth limits as heuristics, not universal syntax laws.
```

### 10. Standalone Comments In Canonical Source

Canonical comments should be their own lines.

Bad:

```text
call customerLookupCall database.customers.findByEmail # lookup normalized email
```

Good:

```text
# rationale: Lookup normalized email because uniqueness is canonicalized.
call customerLookupCall database.customers.findByEmail
```

Supported typed comment prefixes:

```text
# rationale:
# invariant:
# warning:
# failure:
# security:
# timing:
# memory:
# concurrency:
# dependency:
# observability:
# test:
# todo:
# agent:
```

Why:

```text
Comments become independent attention units.
The executable line remains a clean semantic record.
Typed comments are easier to retrieve than trailing prose.
This should be a canonical formatting rule, not necessarily a syntax ban on all
legacy inline comments.
```

### 11. Stricter String Syntax

Canonical string rules:

```text
strings are single-line
strings use double quotes
allowed escapes: \n \t \r \\ \" \0
unknown escapes are invalid
long strings require payload metadata
```

For long literals:

```text
literal serverBannerText String
literalBytes serverBannerText 1842
literalDigest serverBannerText sha256 0123456789abcdef
literalPreview serverBannerText "Server ready on"
literalSource serverBannerText "assets/serverBanner.txt"
```

If the payload is stored outside the main source line, the source reference
must use one canonical quoted source string:

```text
literalSource serverBannerText "assets/serverBanner.txt"
```

Why:

```text
Long literals are attention sinks.
Agents usually need the literal identity, purpose, size, and preview.
They do not always need the full payload in the reasoning window.
```

### 12. Deprecate Two-Target Branch Syntax

Canonical:

```text
branchIf requestIsValid parseRequestBody
branch requestValidationFailed
```

Deprecated:

```text
branchIf requestIsValid parseRequestBody requestValidationFailed
```

Why:

```text
One line should represent one control decision.
The false path should be explicit as a separate line or fallthrough.
This keeps branches graphable and attention-local.
```

### 13. Keep Call Syntax Verbose

Do not compress:

```text
call
arg
run
bind
bindOk
bindError
ignoreOk
branchIfError
```

Bad proposed direction:

```text
do accountBalanceLookupCall database.accounts.findBalance accountId normalizedAccountId -> accountBalance
```

Why this is bad:

```text
It hides argument roles.
It merges execution and binding.
It weakens failure flow.
It creates a mini-language.
It makes partial retrieval worse.
```

The current lifecycle syntax is intentionally verbose and should stay.

## Recommended Syntax Profile

The refined AgentScript profile should look like this.

```text
section module.account.operations

operation getAccountBalance
input getAccountBalance normalizedAccountId AccountId
output getAccountBalance AccountBalanceResult
effect getAccountBalance read database.accounts
effect getAccountBalance write console.stdout
memoryHeap getAccountBalance no
memoryStackLimit getAccountBalance 16KiB
async getAccountBalance no
purpose getAccountBalance "Print the current account balance for one normalized account id"
invariant getAccountBalance "Every database lookup failure maps to AccountBalanceError.LookupFailed"

label startGetAccountBalance

group accountBalanceLookup
groupPurpose accountBalanceLookup "Lookup one account balance by normalized account id"
groupInput accountBalanceLookup normalizedAccountId
groupOutput accountBalanceLookup accountBalance
groupError accountBalanceLookup accountBalanceLookupError
groupFailure accountBalanceLookup accountBalanceLookupFailure

call accountBalanceLookupCall database.accounts.findBalance
arg accountBalanceLookupCall accountId normalizedAccountId
run accountBalanceLookupCall
bindOk accountBalance AccountBalance accountBalanceLookupCall
bindError accountBalanceLookupError DatabaseReadError accountBalanceLookupCall
branchIfError accountBalanceLookupCall accountBalanceLookupFailed

group accountBalanceWrite
groupPurpose accountBalanceWrite "Write the account balance to standard output"
groupInput accountBalanceWrite accountBalance
groupError accountBalanceWrite accountBalanceWriteError
groupFailure accountBalanceWrite accountBalanceWriteFailure

call accountBalanceWriteCall console.writeIntegerLine
arg accountBalanceWriteCall console console
arg accountBalanceWriteCall value accountBalance
run accountBalanceWriteCall
ignoreOk accountBalanceWriteCall Void
bindError accountBalanceWriteError ConsoleWriteError accountBalanceWriteCall
branchIfError accountBalanceWriteCall accountBalanceWriteFailed

storage local immutable successExitCode ExitCode 0
returnOk successExitCode

label accountBalanceLookupFailed
makeError accountBalanceLookupFailure AccountBalanceError.LookupFailed accountBalanceLookupError
returnError accountBalanceLookupFailure

label accountBalanceWriteFailed
makeError accountBalanceWriteFailure AccountBalanceError.ConsoleWriteFailed accountBalanceWriteError
returnError accountBalanceWriteFailure
```

This profile is longer than mainstream code, but the important relations are
visible:

```text
operation contract
effect contract
memory contract
group anchors
call identity
argument roles
success binding
error binding
failure branch
failure mapping
return behavior
```

## Naming Laws

### Role Suffixes Are Syntax

These should be treated as syntax-level role markers:

```text
Call
Error
Failed
Failure
Result
Option
Request
Response
Token
Timeout
Deadline
Defer
Group
Policy
Codec
```

Examples:

```text
emailNormalizationCall
emailNormalizationError
emailNormalizationFailed
emailNormalizationFailure
createCustomerResult
requestCancellationToken
databaseReadTimeout
transactionRollbackDefer
```

### Avoid Weak Words

Do not use vague generic names:

```text
data
value
result
thing
item
obj
tmp
err
res
helper
handler
process
doThing
```

Allowed only when the type or surrounding syntax makes the role exact:

```text
arg accountBalanceWriteCall value accountBalance
```

Here `value` is an argument role required by the call target, not a vague local
symbol.

### Prefer Common Morphemes

Use words that are common in code and English:

```text
read
write
open
close
parse
encode
decode
validate
normalize
lookup
insert
update
delete
create
build
emit
send
receive
request
response
error
failure
timeout
deadline
token
policy
codec
schema
resource
memory
pointer
buffer
length
offset
```

Avoid private abbreviations:

```text
acctBalLkp
dbRd
custFmt
invCalc
```

Unless the abbreviation is a declared domain type or external standard.

## Syntax Anti-Patterns

### Context-Losing Compression

Bad:

```text
returnBadRequest invalidJson
```

Better:

```text
call invalidJsonResponseBuildCall buildStandardJsonErrorResponse
arg invalidJsonResponseBuildCall status badRequestStatus
arg invalidJsonResponseBuildCall errorCode invalidJsonErrorCode
arg invalidJsonResponseBuildCall publicMessage invalidJsonPublicMessage
run invalidJsonResponseBuildCall
bind invalidJsonResponse HttpResponse invalidJsonResponseBuildCall
returnValue invalidJsonResponse
```

### Mixed Stems

Bad:

```text
call saveCall database.customers.insert
bindError dbError DatabaseWriteError saveCall
branchIfError saveCall insertFailed
makeError customerCreateFailure CreateCustomerError.DatabaseFailed dbError
```

Better:

```text
call customerInsertCall database.customers.insert
bindError customerInsertError DatabaseWriteError customerInsertCall
branchIfError customerInsertCall customerInsertFailed
makeError customerInsertFailure CreateCustomerError.DatabaseFailed customerInsertError
```

### Overloaded Tail Syntax

Bad:

```text
policy customerRetry max 3 delay 50 jitter yes timeout 500
```

Better:

```text
retryPolicy customerLookupRetryPolicy
retryMaxAttempts customerLookupRetryPolicy 3
retryInitialDelay customerLookupRetryPolicy customerLookupRetryInitialDelay
retryJitter customerLookupRetryPolicy yes
retryTimeout customerLookupRetryPolicy customerLookupRetryTimeout
```

### Deep Dot Paths

Bad:

```text
company.internal.platform.service.v2.accounts.handlers.balance.lookup
```

Better:

```text
accountService.balance.lookup
```

If full provenance matters, put it in dependency metadata, not every call site.

## Current Syntax Audit Tables

This section audits the current AgentScript syntax surface against the research
claims above. The standard is not "shortest possible source." The standard is:

```text
Can an agent retrieve a small region and recover the relation, role, type,
failure path, and intent from stable repeated anchors?
```

### Core Syntax Audit

| Current syntax area | Current adherence | Attention/tokenization effect | Syntax change needed | Priority |
| --- | --- | --- | --- | --- |
| One physical line per record | Strong | A single line is already an attention-local fact with a stable verb at token 1. | Keep this as a hard language identity. Do not add expression nesting, block punctuation, or comma argument lists. | Keep |
| Verb-first records | Strong | `call`, `arg`, `run`, `bind`, `branch`, and `return` create stable first-token anchors. | Keep the current verb-first form and make canonical formatting stricter: one verb, one record, one space between fields. | Keep |
| `operation`, `input`, `output`, `effect`, `memory`, `async`, `purpose` | Strong | Repeating the operation name on each contract line gives attention a local owner anchor. | Keep owner repetition. Do not introduce implicit current operation syntax. | Keep |
| `call`, `arg`, `run` lifecycle | Strong with naming gaps | The lifecycle is attention-friendly only when the call name is stable and role-marked. | Require public canonical source to use `Call` suffix and a shared semantic stem, such as `accountBalanceLookupCall`. | P0 |
| `bind`, `bindOk`, `bindError`, `ignoreOk` | Strong with naming gaps | These lines expose dataflow directly, but vague result names weaken the relation. | Require success, error, and ignored-result names to share the call stem when practical: `customerInsertCall`, `customerInsertError`, `customerInsertResult`. | P0 |
| `branchIfError` | Strong | It creates an explicit failure edge tied to a call anchor. | Keep. Require failed labels to share the call stem: `customerInsertCall` to `customerInsertFailed`. | P0 |
| `branchIf` | Mixed | Single-target form is clear; two-target form compresses both outcomes into one line and weakens local branch reasoning. | Canonical source should use single-target `branchIf condition trueLabel` followed by explicit `branch falseLabel` when needed. Deprecate two-target form for agent-written source. | P0 |
| `branch` and `label` | Mixed | Labels are useful anchors when semantically named, weak when generic or short. | Require labels to name the state or outcome: `parseDigits`, `customerInsertFailed`, `returnCachedAccount`. Avoid `ok`, `retT`, `l1`, `start` outside trivial generated constants. | P1 |
| Boolean literals | Mixed | Metadata uses `yes` and `no`, while value-level Bool examples need clearer Bool tokens. | Use `yes` and `no` only for metadata fields. Use `true` and `false` only for value-level `Bool` literals. | P1 |
| `const`, `var`, `set` storage syntax | Mixed | The lines are short, but the keyword does not expose scope, lifetime, or shared-state risk. `const` is overloaded across languages, and `var` carries weak mutability meaning. | Replace canonical declarations with `storage <scope> <mutability> <name> <TypeName> <value>` and mutation with `set <scope> <name> <value>`. Do not make global mutable state a normal storage form. | P0 |
| Canonical primitive target names | Strong in current examples | Full targets like `math.lessThanI64` tokenize better than short aliases because the semantic role is visible. | Keep full English target spellings as canonical. Do not revive short primitive aliases such as `iadd`, `flt`, or `eq` for agent-written source. | P0 |
| Identifier naming laws | Mixed | Names are the main relation anchors. Short or rare abbreviations increase ambiguity and reduce stem matching. | Make role suffixes mandatory where roles exist: `Call`, `Error`, `Failed`, `Failure`, `Result`, `Value`, `Label` when needed for clarity. Use segment review heuristics. | P0 |
| Dot paths | Strong with depth risk | Dot paths expose domain hierarchy, but deep paths become long noisy token chains. | Keep dot paths, but review paths deeper than five segments. Put provenance in metadata instead of every target path. | P1 |
| `section` | Partly present but underspecified | Section lines are useful retrieval anchors for long files, but they must not imply hidden scope. | Make `section path.name` real canonical metadata syntax: non-executing, no implicit membership, lowerCamel dot path, stable retrieval anchor. | P1 |
| `group` metadata | Missing from current source | Long operations need local non-executing anchors so related call groups can be found in the middle of a file. | Add `group`, `groupPurpose`, `groupInput`, `groupOutput`, `groupError`, `groupFailure`, and `groupTiming` as advisory metadata. A group is not a block and does not create scope. | P1 |
| Comments | Mixed | Comments help context, but inline comments create noncanonical mixed records and banner comments are weak anchors. | Move inline comments to standalone typed comment lines in canonical source, such as `# rationale:` or `# invariant:`. Replace decorative banners with `section` lines. | P0 |
| `type ALIAS UNDERLYING extra` | Mixed | Compact type aliases are fine when obvious, but long tails overload positional meaning. | Keep compact aliases for simple arity. Add `typeParameter` only when a type has enough parameters to make the tail ambiguous. | P2 |
| `record NAME layout row align 8` | Mixed | The record name is strong, but layout and alignment are packed into a positional tail. | Prefer split metadata for canonical source: `record Name`, `recordLayout Name row`, `recordAlign Name 8`, followed by `field` lines. | P1 |
| `jsonCodec`, `retryPolicy`, `taskGroup`, `resource` tails | Mixed | These lines are checkable because the schema is fixed, but they become weak when more options are added. | Keep current one-line form only while the option set stays short and fixed. If an option family grows, split it into role-specific metadata lines. | P2 |
| `effect` and memory contracts | Strong after refinement | Effect lines remain short and high-signal. Memory lines become stronger when each memory policy has its own fixed schema. | Keep `effect <operation> <mode> <target>`. Prefer `memoryHeap` and `memoryStackLimit` over overloaded `memory` tails in canonical agent-facing source. | Keep |
| Long literals | Weak when inline | Long strings consume attention and can bury nearby syntax. | Treat long payloads as named resources: `literalBytes`, `literalDigest`, `literalPreview`, and quoted `literalSource`. Keep only short literals inline. | P1 |

### Storage And Mutability Analysis

Current source uses this storage surface:

```text
const NAME TYPE VALUE
var NAME TYPE INITIAL_VALUE
set NAME VALUE
```

The current corpus has:

```text
const lines: 3253
var lines: 474
set lines: 996
```

The existing syntax is compact and easy to scan, but it underspends tokens on
the exact facts agents need:

```text
is this value mutable?
is this binding local, module-level, or shared?
is this mutation local state or shared state?
is this value a literal, a cell, a configuration constant, or a shared slot?
```

The refined answer is not to create many first-token verbs such as
`localImmutable`, `mutableLocal`, or `globalMutable`. That over-fragments the
verb space. The better shape is one stable storage verb with scope and
mutability as near-front fields:

```text
storage local immutable <name> <TypeName> <valueNameOrLiteral>
storage local mutable <name> <TypeName> <initialValue>
set local <name> <valueNameOrLiteral>
```

This keeps the first-token anchor stable while still exposing the facts that
`const`, `var`, and `set` hide.

Module storage can use the same shape, but it should be a second-phase decision
after module ownership is fully specified:

```text
storage module immutable <name> <TypeName> <valueNameOrLiteral>
storage module mutable <name> <TypeName> <initialValue>
set module <name> <valueNameOrLiteral>
```

Global mutable state should not be a normal peer of local state. If shared
mutable process state is allowed at all, it should be visually exceptional and
guarded:

```text
sharedState process mutable <name> <TypeName> <initialValue>
sharedStateOwner <name> <ownerName>
sharedStateGuard <name> <guardName>
read sharedState <valueName> <TypeName> <name> protectedBy <guardToken>
set sharedState <name> <valueNameOrLiteral> protectedBy <guardToken>
```

The domain literal rule should move away from the word `const`. The refined
forms are:

```text
domainLiteral <name> <TypeName> <literal>
domainLiteralSource <name> <platform.path>
storage local immutable <name> <TypeName> <literal>
```

The preferred default is `storage local immutable` for local literals and
`domainLiteral` only when the value is part of a public domain vocabulary.

### Atomic Line Law

Every AgentScript line should be an atomic semantic record. A line is atomic
when it makes one checkable assertion with one stable verb, one owner anchor,
and no hidden secondary behavior.

```text
one line = one declaration, one metadata fact, one argument binding,
one control-flow edge, one effect, one failure mapping, or one value action
```

When a line needs `and`, `or`, `while`, `unless`, or a second role phrase to be
understood, split it unless the relation itself is a single domain predicate.

```text
prefer:
effect getAccountBalanceWithRetry read scheduler.clock
effect getAccountBalanceWithRetry write scheduler.timerQueue

avoid:
effect getAccountBalanceWithRetry readWrite scheduler.clockAndTimerQueue
```

Prose metadata such as `purpose`, `invariant`, `# rationale:`, and
`# safety:` may use natural language, but it must not introduce executable
facts that are absent from typed lines. If a prose line names two obligations,
each obligation should also have its own typed line or its own typed comment.

The ambiguity test for a line is:

```text
Can an agent retrieve this line alone and know exactly what fact it asserts?
Can a checker identify the created symbol, referenced symbol, or contract role?
Would removing this line remove exactly one semantic fact?
```

If the answer is no, the line is too packed or too ambiguous.

### Aggregate Syntax Law

Higher-level objects and arrays should be allowed only when they preserve the
same attention-local properties as calls and storage. The refined law is:

```text
Objects and arrays must not hide construction, mutation, indexing, allocation,
bounds behavior, trust transitions, or serialization shape. Aggregates are valid
only when their schema, layout, ownership, and access operations remain
line-addressable.
```

That means AgentScript should not add JavaScript-style object literals or array
expressions as the normal surface:

```text
avoid object user = { id: ..., name: ... }
avoid tasks.push(task)
avoid task = tasks[i]
```

The preferred syntax families are:

```text
record / field / fieldGet for object shape and field access
recordBuilder / recordSet / recordBuild for large record construction
listType / arrayType / sliceType / smallListType for typed collections
mapType plus key/value metadata for typed dictionaries
resource metadata for shared stores
jsonCodec metadata for public JSON shape
```

Collection signatures should keep structure and policy on separate lines when a
tail starts to carry multiple facts:

```text
listType TaskList Task
listAllocator TaskList arena.request
arrayType FixedTaskArray Task
arrayLength FixedTaskArray fixedTaskArrayLength
smallListType SmallTaskList Task
smallListInlineCapacity SmallTaskList smallTaskListInlineCapacity
smallListSpillAllocator SmallTaskList arena.request
mapType TaskMap
mapKey TaskMap TaskId
mapValue TaskMap Task
mapAllocator TaskMap arena.process
```

Collection behavior should still use the normal call lifecycle:

```text
call taskListAppendCall TaskList.append
arg taskListAppendCall list taskList
arg taskListAppendCall item createdTask
run taskListAppendCall
bindOk updatedTaskList TaskList taskListAppendCall
bindError taskListAppendError TaskListAppendError taskListAppendCall
branchIfError taskListAppendCall taskListAppendFailed
```

The default collection model should be immutable value updates. Mutable
collections should be visually explicit through type names such as
`TaskListBuffer`, not implied by a generic `append` call.

Literal collections should state their completeness rules:

```text
listLiteral defaultTaskTitles TaskTitleList
listLiteralLength defaultTaskTitles defaultTaskTitleCount
listLiteralIndexBase defaultTaskTitles zeroCount
listLiteralIndexPolicy defaultTaskTitles contiguousUniqueAscending
listLiteralItem defaultTaskTitles 0 setupTaskTitle
```

For canonical literal lists, item indices must be unique, sorted in ascending
order, and contiguous from the declared base to `listLiteralLength - 1`.

Collection operation contracts should make the behavior of common operations
queryable before any call site appears:

```text
collectionOperation TaskList.length
collectionOperationOutput TaskList.length I64
collectionOperationFailure TaskList.length none
collectionOperationEffect TaskList.length read list
collectionOperation TaskList.append
collectionOperationOutput TaskList.append Result TaskList TaskListAppendError
collectionOperationFailure TaskList.append TaskListAppendError.AllocationFailed
collectionOperationEffect TaskList.append read list
collectionOperationEffect TaskList.append read item
collectionOperationAllocation TaskList.append arena.request
collectionOperationMutation TaskList.append immutableUpdate
collectionOperation TaskList.get
collectionOperationOutput TaskList.get Result Task TaskListReadError
collectionOperationFailure TaskList.get TaskListReadError.IndexOutOfRange
collectionOperationEffect TaskList.get read list
collectionOperationEffect TaskList.get read index
```

This answers three questions that agents otherwise have to infer:

```text
is length infallible?
does append mutate or return a new list?
which allocator can append use?
```

Operations that allow dynamic allocation should distinguish heap allocation
from arena allocation and name the call that justifies the permission:

```text
memoryHeap appendAndReadTask no
memoryArena appendAndReadTask arena.request
memoryAllocationSource appendAndReadTask taskListAppendCall
```

For application data, use higher-level text types first and convert to C strings
only at explicit runtime boundaries:

```text
type RawUtf8Text Bytes
type ValidatedText Utf8Text
type TaskTitle ValidatedText
trustBoundary ValidatedText
trustBoundaryKind ValidatedText rawUtf8ToValidatedText
trustBoundaryInput ValidatedText RawUtf8Text
trustBoundaryOutput ValidatedText ValidatedText
trustBoundaryValidator ValidatedText validateUtf8Text
trustBoundarySource ValidatedText validatedRuntimeValue
trustBoundarySource ValidatedText trustedUtf8Literal
typeLiteralEncoding ValidatedText utf8
domainLiteral setupTaskTitle TaskTitle "setup project"
domainLiteralValidation setupTaskTitle trustedUtf8Literal
```

### Refined Core Signature Choices

Only weak or incomplete syntax areas get new signatures. Strong existing forms
such as `call`, `arg`, `run`, `bindOk`, `bindError`, `branchIfError`, and
single-target `branchIf` should keep their current verbs and be improved by
naming laws.

| Syntax area | Refined signature | Use when | Avoid |
| --- | --- | --- | --- |
| Local immutable storage | `storage local immutable <name> <TypeName> <valueNameOrLiteral>` | Replacing most operation-local `const` lines. | `localImmutable`, `immutableLocal`, `localValue`. |
| Local mutable storage | `storage local mutable <name> <TypeName> <initialValue>` | Replacing operation-local `var` lines. | `localMutable`, `mutableLocal`, `localCell`. |
| Local mutation | `set local <name> <valueNameOrLiteral>` | Replacing writes to local mutable storage. | `setLocal`, `mutateLocal`, `cellSet`. |
| Module storage | `storage module immutable <name> <TypeName> <value>`<br>`storage module mutable <name> <TypeName> <initialValue>`<br>`set module <name> <value> ownedBy <ownerName>` | Module-level constants or rare module-owned slots after module ownership is specified. | Treating module mutable storage as ordinary local state. |
| Shared state | `sharedState process mutable <name> <TypeName> <initialValue>`<br>`sharedStateOwner <name> <ownerName>`<br>`sharedStateGuard <name> <guardName>`<br>`read sharedState <valueName> <TypeName> <name> protectedBy <guardToken>`<br>`set sharedState <name> <value> protectedBy <guardToken>` | Exceptional process-shared mutable state. | `globalMutable`, unguarded shared reads or mutation. |
| Guarded shared read | `read sharedState <valueName> <TypeName> <name> protectedBy <guardToken>` | Reading shared mutable state after explicit guard acquisition. | Passing a shared-state slot as a normal value when the current value must be protected. |
| Guarded shared mutation | `set sharedState <name> <value> protectedBy <guardToken>` | Writing shared mutable state after explicit guard acquisition. | Relying on `sharedStateGuard` metadata alone as proof of safety. |
| Domain literals | `domainLiteral <name> <TypeName> <literal>`<br>`domainLiteralSource <name> <platform.path>` | Public domain vocabulary values, especially platform-specific constants. | Repeating raw literals at multiple use sites or hiding platform binding in prose. |
| Boolean literals | `storage local immutable <name> Bool true`<br>`storage local immutable <name> Bool false` | Value-level Bool literals. | Encoding Bool as `1` or `0` unless the operation is explicitly C-compatible. |
| Section anchors | `section <lowerCamel.dot.path>` | Long files, module areas, stdlib compatibility surfaces, test sections. | Decorative banner comments. |
| Group anchors | `group <groupName>`<br>`groupPurpose <groupName> "<text>"`<br>`groupInput <groupName> <valueName>`<br>`groupOutput <groupName> <valueName>`<br>`groupError <groupName> <errorName>`<br>`groupFailure <groupName> <failureName>`<br>`groupTiming <groupName> <timingName>` | Long operation regions that need local retrieval anchors. | Treating groups as scopes or blocks, or mixing raw errors and domain failures under one metadata verb. |
| Operation body source | `operationBody <operationName> <bodyKind>` | Every operation. Source-body operations use `sourceTape`; non-source operations use `runtimeBinding`, `recordConstructor`, `intrinsic`, `externalDependency`, or another explicit body source. | Letting metadata imply executable behavior or leaving normal source-body operations unclassified. |
| Failure values | `declareFailure <failureName> <ErrorTypeName>.<VariantName>`<br>`makeError <failureName> <ErrorTypeName>.<VariantName> <sourceErrorName>` | Creating an explicit value before `returnError`. | Assuming `groupFailure` creates a symbol. |
| Field extraction | `fieldGet <valueName> <TypeName> <recordValueName> <fieldName>` | Reading record fields for later `arg` lines. | Dotted runtime field values such as `accountBalance.accountId` in arguments. |
| Typed comments | `# rationale: <text>`<br>`# invariant: <text>`<br>`# safety: <text>`<br>`# timing: <text>` | Local reasoning hints next to risky code. | New `comment` or `note` verbs unless comments need to become queryable data. |
| Type parameters | `type <aliasName> <underlyingName>`<br>`typeParameter <aliasName> <roleName> <TypeName>` | Type aliases whose tail would otherwise be ambiguous. Use semantic roles such as `success`, `error`, `item`, or `key` when available. | Generic punctuation, overloaded positional tails, or numeric slots when a role name exists. |
| Record layout | `record <RecordName>`<br>`recordLayout <RecordName> <layoutKind>`<br>`recordAlign <RecordName> <byteAlignment>` | Records where layout and alignment matter. | Packing layout and alignment into the `record` line tail. |
| Record constructor contract | `recordConstructor <operationName> <RecordName>`<br>`recordConstructorFailure <operationName> <ErrorTypeName>.<VariantName>` | Generated or semantic record-construction operations that can fail. | Calling `record.create.RecordName` without a local contract. |
| Record builder construction | `recordBuilder <builderName> <RecordName>`<br>`recordSet <builderName> <fieldName> <valueName>`<br>`recordBuild <callName> <builderName>`<br>`recordBuildFailure <callName> <ErrorTypeName>.<VariantName>` | Large records where each field assignment should be separately addressable before the build call runs. | Object literals or packing many field assignments into one constructor expression. |
| Record copy update | `recordCopy <builderName> <recordValueName>`<br>`recordSet <builderName> <fieldName> <valueName>`<br>`recordBuild <callName> <builderName>` | Immutable record update after construction. | Hidden in-place object mutation, dotted assignment, or defaulting to `fieldUpdate` for app code. |
| Collection types | `listType <TypeName> <ElementType>`<br>`listAllocator <TypeName> <allocatorName>`<br>`arrayType <TypeName> <ElementType>`<br>`arrayLength <TypeName> <lengthName>`<br>`sliceType <TypeName> <ElementType>`<br>`smallListType <TypeName> <ElementType>`<br>`smallListInlineCapacity <TypeName> <countName>`<br>`smallListSpillAllocator <TypeName> <allocatorName>` | Typed arrays, lists, slices, and small-buffer collections whose storage behavior must remain visible. | Generic dynamic `Array` surfaces with hidden allocation or bounds behavior. |
| Collection operation contracts | `collectionOperation <TypeName.operationName>`<br>`collectionOperationArg <TypeName.operationName> <roleName> <TypeName>`<br>`collectionOperationOutput <TypeName.operationName> <OutputShape>`<br>`collectionOperationFailure <TypeName.operationName> <ErrorTypeName.VariantName\|none>`<br>`collectionOperationEffect <TypeName.operationName> <read\|write> <roleName>`<br>`collectionOperationAllocation <TypeName.operationName> <allocatorName>`<br>`collectionOperationMutation <TypeName.operationName> <mutationKind>` | Declaring required roles, result shape, failure shape, allocation, mutation, indexing, borrowing, or bounds behavior. | Inferring collection behavior from method names alone. |
| Typed maps | `mapType <TypeName>`<br>`mapKey <TypeName> <KeyType>`<br>`mapValue <TypeName> <ValueType>`<br>`mapAllocator <TypeName> <allocatorName>` | In-memory dictionaries with explicit key, value, and allocation policy. | Dynamic object bags used as maps. |
| Collection literals | `listLiteral <literalName> <ListType>`<br>`listLiteralLength <literalName> <countName>`<br>`listLiteralIndexBase <literalName> <baseIndexName>`<br>`listLiteralIndexPolicy <literalName> <policyName>`<br>`listLiteralItem <literalName> <index> <valueName>` | Small declared literal collections that should remain flat and addressable. | Inline array literals, packed comma-separated values, or list items with implicit completeness rules. |
| Codec metadata | `jsonCodec <RecordName>`<br>`jsonCodecStrict <RecordName> yes\|no`<br>`jsonCodecUnknownFields <RecordName> reject\|keep\|ignore`<br>`jsonCodecDecodeTarget <RecordName> <targetPath>`<br>`jsonCodecEncodeTarget <RecordName> <targetPath>`<br>`jsonCodecRequiredField <RecordName> <fieldName>`<br>`jsonCodecInput <RecordName> <decode\|encode> <roleName> <TypeName>`<br>`jsonCodecOutput <RecordName> <decode\|encode> <OutputShape>` | Codec declarations whose direction, generated target, required fields, input, output, failures, and limits need to stay independently checkable. | Packing multiple codec options into one long metadata tail. |
| Memory contracts | `memoryHeap <operationName> yes\|no`<br>`memoryArena <operationName> <arenaName>`<br>`memoryAllocationSource <operationName> <callName>`<br>`memoryStackLimit <operationName> <byteLimit>` | Declaring one operation's heap policy, arena allocation, allocation source, or stack bound. | Calling arena allocation heap allocation, mixing compact `memory` lines with split memory-family verbs, or allowing dynamic allocation without naming why. |
| Policy tails | `retryPolicy <policyName>`<br>`retryMaxAttempts <policyName> <count>`<br>`retryInitialDelay <policyName> <durationName>`<br>`retryMaximumDelay <policyName> <durationName>`<br>`retryJitter <policyName> yes\|no` | Policies whose option family is growing. | Generic `policy` key-value tails. |
| Call retry behavior | `useRetry <callName> <retryPolicyName>` | A call itself owns retry behavior. | Passing retry policy as a normal arg when it changes behavior. |
| Runtime binding metadata | `operationBody <operationName> runtimeBinding`<br>`runtimeBinding <operationName> <runtime.path>`<br>`runtimeBindingPrecondition <operationName> "<text>"`<br>`runtimeBindingFailure <operationName> <ErrorTypeName>.<VariantName>` | Agent-facing operation signatures whose executable body is supplied by a runtime, C, or platform primitive. `runtimeBinding` records the target; `operationBody` is the executable body contract. | Adding second-name relation verbs just to explain where a semantic signature binds, returning typed errors without saying where they come from, or letting metadata imply execution. |
| Trust-boundary type metadata | `trustBoundary <TypeName>`<br>`trustBoundaryKind <TypeName> <kindName>`<br>`trustBoundaryInput <TypeName> <RawTypeName>`<br>`trustBoundaryOutput <TypeName> <TrustedTypeName>`<br>`trustBoundaryValidator <TypeName> <operationName>`<br>`trustBoundarySource <TypeName> <sourceKind>` | Types whose safety depends on validation, provenance, or ownership. | Letting raw pointers and validated values share one name, or hiding multiple trusted sources in one prose line. |
| Trusted literal metadata | `typeLiteralEncoding <TypeName> <encodingName>`<br>`typeLiteralTerminator <TypeName> <terminatorName>`<br>`domainLiteralTrust <literalName> <sourceKind>`<br>`domainLiteralValidation <literalName> <sourceKind>`<br>`literalTrust <literalName> <sourceKind>` | Literals whose type carries trust, validation, or encoding assumptions. | Letting typed C string or validated text literals imply hidden trust rules. |
| Cleanup lifecycle | `deferLog <deferName> <targetPath> <valueName>`<br>`deferLogSink <deferName> <logPath>`<br>`deferAwaitLog <deferName> <targetPath> <valueName>`<br>`deferWhenExitLog <deferName> <conditionValue> <targetPath> <valueName>` | Releasing guards or resources on every return path after acquisition. | Acquiring a guard and relying on implicit release, or hiding cleanup log effects. |
| Long literals | `literal <literalName> <TypeName>`<br>`literalBytes <literalName> <byteCount>`<br>`literalDigest <literalName> <algorithm> <digest>`<br>`literalPreview <literalName> "<shortPreview>"`<br>`literalSource <literalName> "<path>"` | Long strings, embedded templates, generated payloads. | Large inline string constants. |

### Missing Edge Definitions

This section defines the remaining graph edges that were adequate in the
sample but still needed checker-grade syntax rules.

Research grounding:

| Source | Precedent | AgentScript rule |
| --- | --- | --- |
| [RFC 8259 JSON](https://datatracker.ietf.org/doc/html/rfc8259) | JSON is a text-based structured data format. JSON generators must produce grammar-conforming text. Parsers and generators may expose runtime limits. | Codec calls must expose direction, input type, output type, grammar failure, schema failure, and limit policy as separate edges. |
| [JSON Schema 2020-12](https://json-schema.org/draft/2020-12/json-schema-core) | JSON Schema defines structure, validation output, object keywords, array keywords, and vocabularies as explicit schema mechanisms. | Codecs should be typed record serialization, not dynamic object syntax. |
| [Rust borrowing](https://doc.rust-lang.org/book/ch04-02-references-and-borrowing.html) | Shared access and mutable access are constrained by explicit borrowing rules. | Shared-state reads and writes must require guard-token authority. |
| [Rust destructors](https://doc.rust-lang.org/reference/destructors.html) | Drop scopes are explicit, but process abort paths can skip destructors. | Cleanup edges must specify which exits run cleanup and must not imply cleanup after non-unwinding termination. |
| [Python with statement](https://docs.python.org/3/reference/compound_stmts.html#the-with-statement) | If context entry succeeds, exit is guaranteed for normal and exceptional exits. | `deferLog` should register cleanup after acquisition succeeds and run on every normal AgentScript return path. |
| [Swift API guidelines](https://www.swift.org/documentation/api-design-guidelines/) | Clarity at the point of use is more important than brevity. | Generated edge names should be semantic and role-labeled. |

#### Codec Edge Family

Codec declarations stay metadata. A codec declaration creates two canonical
call targets:

```text
json.decode.<RecordName>
json.encode.<RecordName>
```

Required codec contract lines:

```text
jsonCodec <RecordName>
jsonCodecStrict <RecordName> yes|no
jsonCodecUnknownFields <RecordName> reject|ignore|keep
jsonCodecDecodeTarget <RecordName> <targetPath>
jsonCodecEncodeTarget <RecordName> <targetPath>
jsonCodecRequiredField <RecordName> <fieldName>
jsonCodecInput <RecordName> <decode|encode> <roleName> <TypeName>
jsonCodecOutput <RecordName> <decode|encode> <OutputShape>
jsonCodecDecodeFailure <RecordName> <ErrorTypeName.VariantName>
jsonCodecEncodeFailure <RecordName> <ErrorTypeName.VariantName>
jsonCodecLimit <RecordName> <limitKind> <limitValueName>
```

Generated call target rules:

```text
call <callName> json.decode.<RecordName>
arg <callName> bytes <rawJsonValue>
run <callName>
bindOk <valueName> <RecordName> <callName>
bindError <errorName> <DecodeErrorTypeName> <callName>

call <callName> json.encode.<RecordName>
arg <callName> value <recordValue>
run <callName>
bindOk <valueName> <JsonBytesTypeName> <callName>
bindError <errorName> <EncodeErrorTypeName> <callName>
```

Checker rules:

```text
json.decode.<RecordName> is legal only when jsonCodec <RecordName> exists
json.encode.<RecordName> is legal only when jsonCodec <RecordName> exists
json.decode.<RecordName> must match jsonCodecDecodeTarget
json.encode.<RecordName> must match jsonCodecEncodeTarget
jsonCodecUnknownFields reject maps unknown fields to schema failure
jsonCodecStrict yes rejects type coercion
jsonCodecRequiredField declares one required schema field
jsonCodecLimit maximumBytes constrains input or output bytes
jsonCodecLimit maxDepth constrains nested JSON values
jsonCodecLimit maxStringBytes constrains decoded strings
```

#### Collection Edge Family

Collection declarations define storage shape. Collection operation declarations
define behavior. Do not infer allocation, mutation, index origin, borrow
lifetime, or failure from the operation name.

Required operation contract lines:

```text
collectionOperation <TypeName.operationName>
collectionOperationArg <TypeName.operationName> <roleName> <TypeName>
collectionOperationOutput <TypeName.operationName> <OutputShape>
collectionOperationFailure <TypeName.operationName> <ErrorTypeName.VariantName|none>
collectionOperationEffect <TypeName.operationName> <read|write> <roleName>
collectionOperationMutation <TypeName.operationName> <mutationKind>
```

Optional operation contract lines:

```text
collectionOperationAllocation <TypeName.operationName> <allocatorName>
collectionOperationIndexPolicy <TypeName.operationName> <policyName>
collectionOperationLengthSource <TypeName.operationName> <lengthNameOrOperation>
collectionOperationBorrowSource <TypeName.operationName> <sourceRoleName>
collectionOperationCapacitySource <TypeName.operationName> <capacityName>
collectionOperationSpillAllocator <TypeName.operationName> <allocatorName>
collectionOperationSpillFailure <TypeName.operationName> <ErrorTypeName.VariantName>
```

Core aggregate operations to standardize:

```text
TaskMap.get
TaskMap.insert
TaskMap.update
TaskMap.remove
TaskSlice.length
TaskSlice.get
FixedTaskArray.get
FixedTaskArray.set
SmallTaskList.append
SmallTaskList.spillState
```

Checker rules:

```text
Every call to TypeName.operationName must match collectionOperationArg roles
Every fallible collection operation must have at least one collectionOperationFailure
Every allocating collection operation must name collectionOperationAllocation or collectionOperationSpillAllocator
Every indexed operation must name collectionOperationIndexPolicy
Every fixed array operation must name collectionOperationLengthSource
Every borrowed view operation must name collectionOperationBorrowSource
```

#### Cleanup Edge Family

Cleanup is a lifecycle edge, not a comment. It must state when cleanup runs,
how failure is handled, and whether async cleanup is allowed.

Core forms:

```text
deferLog <deferName> <targetOperationName> <valueName>
deferLogSink <deferName> <logPath>
deferRunOn <deferName> returnOk
deferRunOn <deferName> returnError
deferOrder <deferName> reverseRegistration
deferFailurePolicy <deferName> logAndSuppress
deferConsumes <deferName> <valueName>

deferAwaitLog <deferName> <targetOperationName> <valueName>
deferAwaitLogSink <deferName> <logPath>
deferAwaitTimeout <deferName> <durationName>

deferWhenExitLog <deferName> <conditionValue> <targetOperationName> <valueName>
deferWhenExitLogSink <deferName> <logPath>
```

Checker rules:

```text
deferLog target operation must have async no
deferAwaitLog target operation must have async yes
deferLog requires an operation effect log <logPath> matching deferLogSink
deferAwaitLog requires an operation effect log <logPath> matching deferAwaitLogSink
deferRunOn returnOk makes cleanup run before returnOk exits
deferRunOn returnError makes cleanup run before returnError exits
deferFailurePolicy logAndSuppress prevents cleanup error from replacing the original return
deferConsumes marks a guard or resource token unavailable after cleanup
defer cleanup is not guaranteed on non-unwinding process termination
```

#### Operation Body Edge Family

`operationBody` must be a closed enum, not free prose.

Allowed body kinds:

```text
sourceTape
runtimeBinding
recordConstructor
codecDecode
codecEncode
collectionOperation
intrinsic
externalDependency
```

Rules:

```text
operationBody <operationName> sourceTape requires source lines after the operation contract
operationBody <operationName> runtimeBinding requires runtimeBinding <operationName> <runtime.path>
operationBody <operationName> recordConstructor requires recordConstructor <operationName> <RecordName>
operationBody <operationName> codecDecode requires jsonCodec <RecordName>
operationBody <operationName> codecEncode requires jsonCodec <RecordName>
operationBody <operationName> collectionOperation requires collectionOperation <TypeName.operationName>
operationBody <operationName> intrinsic requires intrinsicName <operationName> <intrinsicName>
operationBody <operationName> externalDependency requires dependencyPath <operationName> <dependency.path>
```

Generated call targets such as `json.decode.Task`, `TaskList.get`, and
`TaskMap.insert` do not need full operation declarations in examples when their
declaring metadata creates them. Public wrappers that contain normal call tape
should use `operationBody <wrapperName> sourceTape`. The `codecDecode`,
`codecEncode`, and `collectionOperation` body kinds are reserved for generated
operations whose whole body is supplied by the declared metadata.

Every non-generated call target must have one of these visible contracts:

```text
operation <targetName>
collectionOperation <TypeName.operationName>
jsonCodecDecodeTarget <RecordName> <targetPath>
jsonCodecEncodeTarget <RecordName> <targetPath>
dependencyPath <operationName> <dependency.path>
```

The effect contract of a caller must cover the declared effects of every call
target it runs, starts, or awaits.

#### Trust And Literal Promotion Edge Family

Trust-boundary types cannot be created by type annotation alone.

Required rules:

```text
domainLiteral <name> <TrustBoundaryType> <literal>
domainLiteralTrust <name> <sourceKind>

domainLiteral <name> <ValidatedTextType> <literal>
domainLiteralValidation <name> <sourceKind>

literal <name> <TrustBoundaryType>
literalSource <name> <path>
literalDigest <name> sha256 <digest>
literalTrust <name> <sourceKind>
```

Checker rules:

```text
sourceKind must appear in trustBoundarySource for the target type
domainLiteralTrust trustedStaticLiteral is legal only for inline domainLiteral values
literalTrust trustedExternalCNullTerminatedUtf8Source requires literalSource
literalTrust trustedExternalCNullTerminatedUtf8Source requires literalDigest
domainLiteralValidation trustedUtf8Literal requires typeLiteralEncoding <TypeName> utf8
CNullTerminatedByteString literals require typeLiteralTerminator CNullTerminatedByteString nullByte
Runtime values cross a trust boundary only through trustBoundaryValidator output
```

#### Guarded State Edge Family

Shared mutable state must be represented as an ownership and guard graph.

Required declaration edges:

```text
sharedState process mutable <name> <TypeName> <initialValue>
sharedStateOwner <name> <ownerName>
sharedStateGuard <name> <guardName>
```

Required access edges:

```text
read sharedState <valueName> <TypeName> <name> protectedBy <guardToken>
set sharedState <name> <valueName> protectedBy <guardToken>
```

Guard token provenance:

```text
guardTokenSource <guardToken> <acquireCallName>
guardTokenProtects <guardToken> <sharedStateName>
guardTokenOwner <guardToken> <ownerName>
guardTokenRelease <guardToken> <deferName>
```

Checker rules:

```text
bindOk <guardToken> GuardToken <acquireCallName> may satisfy guardTokenSource
guardTokenProtects must match the sharedState name used by read or set
guardTokenOwner must match sharedStateOwner
read sharedState creates a snapshot value
set sharedState writes exactly one slot
set sharedState does not release the guard token
every return path after guard acquisition must pass through a registered release defer
deferConsumes <deferName> <guardToken> makes later sharedState access with that token illegal
```

### Verb Schema Registry

Every new verb needs a fixed schema and a declared semantic category. This is
the guardrail that keeps controlled English from becoming ad hoc prose.

The full registry entry for each verb must state:

```text
category
fixed schema
creates symbol yes/no
requires symbol yes/no
runtime behavior yes/no
metadata only yes/no
checkable rule
allowed positions
```

Allowed positions should be explicit, for example:

```text
fileTop
sectionBody
operationContract
operationBody
afterCall
afterBind
beforeReturn
metadataOnly
```

| Verb | Category | Fixed schema | Creates symbol | Runtime behavior | Checkable rule |
| --- | --- | --- | --- | --- | --- |
| `section` | attention grouping | `section <lowerCamel.dot.path>` | no | no | Must not create scope or implicit membership. |
| `storage` | declaration | `storage <scope> <mutability> <name> <TypeName> <value>` | yes | allocates or names storage by scope | `scope = local | module`; `mutability = immutable | mutable`. |
| `set` | storage mutation | `set local <name> <value>`<br>`set module <name> <value> ownedBy <ownerName>`<br>`set sharedState <name> <value> protectedBy <guardToken>` | no | yes | Target must be mutable and scope must match. Module and shared writes must expose authority. |
| `read` | storage read | `read sharedState <valueName> <TypeName> <name> protectedBy <guardToken>` | yes | yes | Shared mutable reads must expose guard authority and create a value snapshot. |
| `sharedState` | declaration | `sharedState process mutable <name> <TypeName> <initialValue>` | yes | declares exceptional shared slot | Must have owner and guard lines before mutation. |
| `sharedStateOwner` | contract metadata | `sharedStateOwner <name> <ownerName>` | no | no | Shared state owner must exist before writes. |
| `sharedStateGuard` | contract metadata | `sharedStateGuard <name> <guardName>` | no | no | Guard metadata is not a guard token. |
| `guardTokenSource` | guard metadata | `guardTokenSource <guardToken> <acquireCallName>` | no | no | Connects one guard token to the acquisition call that produced it. |
| `guardTokenProtects` | guard metadata | `guardTokenProtects <guardToken> <sharedStateName>` | no | no | Names the shared-state slot protected by the token. |
| `guardTokenOwner` | guard metadata | `guardTokenOwner <guardToken> <ownerName>` | no | no | Must match `sharedStateOwner` for guarded reads or writes. |
| `guardTokenRelease` | guard metadata | `guardTokenRelease <guardToken> <deferName>` | no | no | Connects one guard token to its registered cleanup edge. |
| `domainLiteral` | declaration | `domainLiteral <name> <TypeName> <literal>` | yes | no | Used only for public domain vocabulary or reused typed literals. |
| `domainLiteralSource` | binding metadata | `domainLiteralSource <name> <platform.path>` | no | no | Required when a domain literal is platform-specific or copied from an external constant. |
| `operationBody` | operation contract | `operationBody <operationName> <bodyKind>` | no | yes | Required for every operation. `sourceTape` means ordinary explicit tape; every other kind must have matching metadata such as `runtimeBinding`, `recordConstructor`, `intrinsicName`, or `dependencyPath`. |
| `runtimeBinding` | binding metadata | `runtimeBinding <operationName> <runtime.path>` | no | no | Operation signature stays semantic; binding metadata records the underlying runtime target. |
| `runtimeBindingPrecondition` | binding contract | `runtimeBindingPrecondition <operationName> "<text>"` | no | no | Required when the runtime target is only safe under validated inputs, ownership, platform, or memory conditions. |
| `runtimeBindingFailure` | binding contract | `runtimeBindingFailure <operationName> <ErrorTypeName>.<VariantName>` | no | no | Every typed error surfaced by a runtime binding should have a named origin. |
| `intrinsicName` | binding metadata | `intrinsicName <operationName> <intrinsicName>` | no | no | Required when `operationBody` is `intrinsic`; keeps math and primitive operations declared instead of magic. |
| `dependencyPath` | dependency metadata | `dependencyPath <operationName> <dependency.path>` | no | no | Required when `operationBody` is `externalDependency`; records the dependency target without hiding it in a call site. |
| `dependencyFailure` | dependency contract | `dependencyFailure <operationName> <ErrorTypeName>.<VariantName>` | no | no | Names one dependency-level failure variant for an external dependency operation. |
| `trustBoundary` | type contract | `trustBoundary <TypeName>` | no | no | Marks a type that must not be created from raw data without validation or trusted provenance. |
| `trustBoundaryKind` | type contract | `trustBoundaryKind <TypeName> <kindName>` | no | no | Names the kind of trust transition. |
| `trustBoundaryInput` | type contract | `trustBoundaryInput <TypeName> <RawTypeName>` | no | no | Names the untrusted input type for the boundary. |
| `trustBoundaryOutput` | type contract | `trustBoundaryOutput <TypeName> <TrustedTypeName>` | no | no | Names the trusted output type for the boundary. |
| `trustBoundaryValidator` | type contract | `trustBoundaryValidator <TypeName> <operationName>` | no | no | Names the operation that can cross the boundary. |
| `trustBoundarySource` | type contract | `trustBoundarySource <TypeName> <sourceKind>` | no | no | Lists one allowed trusted source for a trust-boundary type. |
| `typeLiteralEncoding` | literal contract | `typeLiteralEncoding <TypeName> <encodingName>` | no | no | Defines the string encoding for literals of this type. |
| `typeLiteralTerminator` | literal contract | `typeLiteralTerminator <TypeName> <terminatorName>` | no | no | Defines the terminator rule for literals of this type. |
| `domainLiteralTrust` | literal contract | `domainLiteralTrust <literalName> <sourceKind>` | no | no | States why a domain literal may carry a trust-boundary type. |
| `domainLiteralValidation` | literal contract | `domainLiteralValidation <literalName> <sourceKind>` | no | no | States why a domain literal may carry a validated text or application-level validated type. |
| `literalTrust` | literal contract | `literalTrust <literalName> <sourceKind>` | no | no | States why a named long literal may carry a trust-boundary type. |
| `jsonCodecStrict` | codec metadata | `jsonCodecStrict <RecordName> yes\|no` | no | no | Splits strictness from the codec declaration. |
| `jsonCodecUnknownFields` | codec metadata | `jsonCodecUnknownFields <RecordName> reject\|keep\|ignore` | no | no | Splits unknown-field behavior from the codec declaration. |
| `jsonCodecDecodeTarget` | codec metadata | `jsonCodecDecodeTarget <RecordName> <targetPath>` | no | no | Names the generated decode call target. |
| `jsonCodecEncodeTarget` | codec metadata | `jsonCodecEncodeTarget <RecordName> <targetPath>` | no | no | Names the generated encode call target. |
| `jsonCodecRequiredField` | codec metadata | `jsonCodecRequiredField <RecordName> <fieldName>` | no | no | Names one field required by strict codec decoding. |
| `jsonCodecInput` | codec metadata | `jsonCodecInput <RecordName> <decode\|encode> <roleName> <TypeName>` | no | no | Names one input role accepted by a generated codec target. |
| `jsonCodecOutput` | codec metadata | `jsonCodecOutput <RecordName> <decode\|encode> <OutputShape>` | no | no | Names the output shape produced by a generated codec target. |
| `jsonCodecDecodeFailure` | codec metadata | `jsonCodecDecodeFailure <RecordName> <ErrorTypeName>.<VariantName>` | no | no | Names one possible generated decode failure. |
| `jsonCodecEncodeFailure` | codec metadata | `jsonCodecEncodeFailure <RecordName> <ErrorTypeName>.<VariantName>` | no | no | Names one possible generated encode failure. |
| `jsonCodecLimit` | codec metadata | `jsonCodecLimit <RecordName> <limitKind> <limitValueName>` | no | no | Names one codec limit such as `maxBytes`, `maxDepth`, or `maxStringBytes`. |
| `memoryHeap` | memory contract | `memoryHeap <operationName> yes\|no` | no | no | Declares one operation's heap policy. |
| `memoryArena` | memory contract | `memoryArena <operationName> <arenaName>` | no | no | Required when arena allocation is allowed and the arena is statically known. |
| `memoryAllocationSource` | memory contract | `memoryAllocationSource <operationName> <callName>` | no | no | Names the call that justifies allowing dynamic allocation. |
| `memoryStackLimit` | memory contract | `memoryStackLimit <operationName> <byteLimit>` | no | no | Declares one operation's stack bound. |
| `recordConstructor` | constructor metadata | `recordConstructor <operationName> <RecordName>` | no | no | Connects a semantic constructor operation to its record. |
| `recordConstructorFailure` | constructor metadata | `recordConstructorFailure <operationName> <ErrorTypeName>.<VariantName>` | no | no | Names one possible constructor failure variant. |
| `recordBuilder` | aggregate construction | `recordBuilder <builderName> <RecordName>` | yes | yes | Creates a named construction context for one record value. |
| `recordSet` | aggregate construction | `recordSet <builderName> <fieldName> <valueName>` | no | yes | Sets exactly one field in a named builder. |
| `recordCopy` | aggregate construction | `recordCopy <builderName> <recordValueName>` | yes | yes | Creates a builder initialized from an existing record for immutable update. |
| `recordBuild` | aggregate construction | `recordBuild <callName> <builderName>` | yes | yes | Creates a normal fallible build call that must be run and bound. |
| `recordBuildFailure` | constructor metadata | `recordBuildFailure <callName> <ErrorTypeName>.<VariantName>` | no | no | Names one possible builder failure variant. |
| `listType` | collection declaration | `listType <TypeName> <ElementType>` | yes | no | Declares a dynamic-length value collection. |
| `listAllocator` | collection metadata | `listAllocator <TypeName> <allocatorName>` | no | no | Names allocation policy without overloading the type line. |
| `arrayType` | collection declaration | `arrayType <TypeName> <ElementType>` | yes | no | Declares a fixed-length array type. |
| `arrayLength` | collection metadata | `arrayLength <TypeName> <lengthName>` | no | no | Names the fixed length value for an array type. |
| `sliceType` | collection declaration | `sliceType <TypeName> <ElementType>` | yes | no | Declares a borrowed view collection. |
| `smallListType` | collection declaration | `smallListType <TypeName> <ElementType>` | yes | no | Declares a small-buffer value collection. |
| `smallListInlineCapacity` | collection metadata | `smallListInlineCapacity <TypeName> <countName>` | no | no | Names the inline capacity without hiding spill behavior. |
| `smallListSpillAllocator` | collection metadata | `smallListSpillAllocator <TypeName> <allocatorName>` | no | no | Names the allocator used after inline capacity is exceeded. |
| `collectionOperation` | collection contract | `collectionOperation <TypeName.operationName>` | no | no | Declares one supported operation for a collection type. |
| `collectionOperationArg` | collection contract | `collectionOperationArg <TypeName.operationName> <roleName> <TypeName>` | no | no | Declares one required argument role for a collection operation. |
| `collectionOperationOutput` | collection contract | `collectionOperationOutput <TypeName.operationName> <OutputShape>` | no | no | Names the operation result shape. |
| `collectionOperationFailure` | collection contract | `collectionOperationFailure <TypeName.operationName> <ErrorTypeName.VariantName\|none>` | no | no | Names one possible failure or states that the operation is infallible. |
| `collectionOperationEffect` | collection contract | `collectionOperationEffect <TypeName.operationName> <read\|write> <roleName>` | no | no | Names one input or collection role read or written by the operation. |
| `collectionOperationAllocation` | collection contract | `collectionOperationAllocation <TypeName.operationName> <allocatorName>` | no | no | Names the allocator a collection operation may use. |
| `collectionOperationMutation` | collection contract | `collectionOperationMutation <TypeName.operationName> <mutationKind>` | no | no | Names mutation shape such as `immutableUpdate` or `bufferMutation`. |
| `collectionOperationIndexPolicy` | collection contract | `collectionOperationIndexPolicy <TypeName.operationName> <policyName>` | no | no | Makes index origin and bounds policy explicit for indexed operations. |
| `collectionOperationLengthSource` | collection contract | `collectionOperationLengthSource <TypeName.operationName> <lengthNameOrOperation>` | no | no | Connects indexed operations to a length constant or length operation. |
| `collectionOperationBorrowSource` | collection contract | `collectionOperationBorrowSource <TypeName.operationName> <sourceRoleName>` | no | no | Connects borrowed view outputs to the source collection role. |
| `collectionOperationCapacitySource` | collection contract | `collectionOperationCapacitySource <TypeName.operationName> <capacityName>` | no | no | Connects small-list operations to inline capacity metadata. |
| `collectionOperationSpillAllocator` | collection contract | `collectionOperationSpillAllocator <TypeName.operationName> <allocatorName>` | no | no | Names the allocator used after inline capacity is exceeded. |
| `collectionOperationSpillFailure` | collection contract | `collectionOperationSpillFailure <TypeName.operationName> <ErrorTypeName>.<VariantName>` | no | no | Names the failure produced by spill allocation. |
| `mapType` | collection declaration | `mapType <TypeName>` | yes | no | Declares a typed dictionary surface. |
| `mapKey` | collection metadata | `mapKey <TypeName> <KeyType>` | no | no | Names the key type. |
| `mapValue` | collection metadata | `mapValue <TypeName> <ValueType>` | no | no | Names the value type. |
| `mapAllocator` | collection metadata | `mapAllocator <TypeName> <allocatorName>` | no | no | Names allocation policy. |
| `listLiteral` | literal declaration | `listLiteral <literalName> <ListType>` | yes | no | Declares a named literal collection resource. |
| `listLiteralLength` | literal metadata | `listLiteralLength <literalName> <countName>` | no | no | Declares expected item count for completeness checking. |
| `listLiteralIndexBase` | literal metadata | `listLiteralIndexBase <literalName> <baseIndexName>` | no | no | Declares the first legal index for the literal list. |
| `listLiteralIndexPolicy` | literal metadata | `listLiteralIndexPolicy <literalName> <policyName>` | no | no | Declares index completeness rules such as `contiguousUniqueAscending`. |
| `listLiteralItem` | literal metadata | `listLiteralItem <literalName> <index> <valueName>` | no | no | Adds one addressable literal item. |
| `declareFailure` | declaration | `declareFailure <failureName> <ErrorTypeName>.<VariantName>` | yes | no | May be returned but has no payload. |
| `makeError` | executable action | `makeError <failureName> <ErrorTypeName>.<VariantName> <sourceErrorName>` | yes | yes | Source error must already exist. |
| `fieldGet` | executable action | `fieldGet <valueName> <TypeName> <recordValueName> <fieldName>` | yes | yes | Required before passing record fields as values. |
| `useRetry` | call contract | `useRetry <callName> <retryPolicyName>` | no | yes | Use only when retry is owned by that call. Manual loops should not also use it. |
| `deferLog` | cleanup lifecycle | `deferLog <deferName> <targetPath> <valueName>` | yes | yes at operation exit | Legal only when the cleanup target contract is `async no`; cleanup failures are logged. |
| `deferLogSink` | cleanup metadata | `deferLogSink <deferName> <logPath>` | no | no | Required for `deferLog` so cleanup logging is an explicit effect. |
| `deferRunOn` | cleanup metadata | `deferRunOn <deferName> returnOk\|returnError` | no | no | Declares which return classes execute the cleanup. |
| `deferOrder` | cleanup metadata | `deferOrder <deferName> reverseRegistration` | no | no | Makes cleanup ordering explicit. |
| `deferFailurePolicy` | cleanup metadata | `deferFailurePolicy <deferName> logAndSuppress` | no | no | Prevents cleanup failure from replacing the chosen return value. |
| `deferConsumes` | cleanup metadata | `deferConsumes <deferName> <valueName>` | no | yes at cleanup execution | Marks a resource or guard token unavailable after cleanup runs. |
| `deferAwaitLog` | cleanup lifecycle | `deferAwaitLog <deferName> <targetPath> <valueName>` | yes | yes at operation exit | Use when the cleanup target contract is `async yes`; cleanup failures are awaited and logged. |
| `deferAwaitLogSink` | cleanup metadata | `deferAwaitLogSink <deferName> <logPath>` | no | no | Required for `deferAwaitLog` so async cleanup logging is explicit. |
| `deferAwaitTimeout` | cleanup metadata | `deferAwaitTimeout <deferName> <durationName>` | no | no | Bounds async cleanup wait time. |
| `deferWhenExitLog` | cleanup lifecycle | `deferWhenExitLog <deferName> <conditionValue> <targetPath> <valueName>` | yes | yes at operation exit when condition is true | The condition is read at operation exit; use for rollback-style cleanup. |
| `deferWhenExitLogSink` | cleanup metadata | `deferWhenExitLogSink <deferName> <logPath>` | no | no | Required for conditional cleanup logging. |
| `groupError` | attention grouping | `groupError <groupName> <errorName>` | no | no | References a raw dependency or runtime error binding. |
| `groupFailure` | attention grouping | `groupFailure <groupName> <failureName>` | no | no | Must reference a domain failure value made by `declareFailure` or `makeError`. |

These rules create two important boundaries:

```text
metadata does not create runtime values
runtimeBinding is target metadata, not execution by itself
operationBody names the executable body source for every operation
agent-facing stdlib names are real signatures, not aliases over terse names
```

If a line creates a value, changes behavior, or changes a contract, it needs a
verb whose schema says so.

Cleanup lines have one additional lifecycle rule:

```text
deferLog is for synchronous cleanup targets with async no contracts.
deferAwaitLog is for asynchronous cleanup targets with async yes contracts.
registered defers run on every return path after their registration point.
deferred cleanup runs in reverse registration order.
deferred cleanup runs after the return value is chosen and before operation exit.
deferLog ignores successful cleanup values and logs cleanup errors.
deferLog expects a fallible cleanup result when cleanup failure must be logged.
authority values are consumed at cleanup execution only when the target contract consumes them.
the parent operation must declare the cleanup log effect.
```

Group error metadata has a strict value-role split:

```text
groupError references raw error values created by bindError.
groupFailure references domain failure values created by declareFailure or makeError.
direct returnError of a bindError value is valid only when the operation error type is the same raw error type.
```

Groups are symbolic metadata, not lexical blocks:

```text
group does not create scope.
group does not own the following lines.
group membership is determined by referenced symbols and shared stems.
groupEnd is unnecessary unless a future formatter needs purely visual ranges.
```

Index and bounds errors should keep a stable two-layer naming convention:

```text
IndexOutOfRange names a domain precheck failure.
ReadFailed <CollectionReadError> wraps a lower-level collection operation failure.
Precheck failures and operation failures should not be collapsed even when they describe the same unsafe index.
```

Record construction has a similar split:

```text
recordConstructorFailure belongs to operation-backed constructor signatures.
recordBuildFailure belongs to individual recordBuild calls created from builders.
per-call recordBuildFailure is preferred for showcases because it keeps failure context local.
record-level build defaults can be evaluated later if repeated builder failures become noisy.
```

Memory contracts use a strict dynamic allocation model:

```text
memoryHeap <operationName> no forbids general heap allocation.
memoryArena <operationName> <arenaName> allows allocation only from the named arena.
memoryAllocationSource <operationName> <callName> names the call that may allocate.
memoryStackLimit <operationName> <byteLimit> bounds stack use independently from arena allocation.
```

The checker should reject a dynamic allocation source unless:

```text
the callee operation declares collectionOperationAllocation or another allocation contract.
the caller operation declares a matching memoryArena line.
the caller operation names the allocating call with memoryAllocationSource.
```

For standard-library names, the stricter rule is simpler than an indirection
layer:

```text
If agents should call compareCString, declare operation compareCString.
If agents should call stringByteLength, declare operation stringByteLength.
If a C name matters only as provenance, put that fact in purpose text or section
placement, not in a relation verb.
```

### Verb Categories

The refined surface should classify every verb family before it is accepted:

| Verb family | Category | Creates symbols | Changes runtime behavior | Notes |
| --- | --- | --- | --- | --- |
| `operation`, `input`, `output`, `effect`, `memoryHeap`, `memoryArena`, `memoryAllocationSource`, `memoryStackLimit`, `async`, `operationBody`, `purpose`, `invariant` | contract | operation and contract entries | only `operationBody` changes executable body source | Defines operation boundary, body source, and obligations. |
| `type`, `typeParameter`, `record`, `recordLayout`, `recordAlign`, `field`, `recordConstructor`, `recordConstructorFailure`, `jsonCodec`, `jsonCodecStrict`, `jsonCodecUnknownFields` | declaration / metadata | types, records, fields | no | Must remain flat and line-addressable. |
| `recordBuilder`, `recordSet`, `recordCopy`, `recordBuild`, `recordBuildFailure` | aggregate construction | builders and build calls | yes | Construction and immutable update stay explicit without object literals. |
| `listType`, `listAllocator`, `arrayType`, `arrayLength`, `sliceType`, `smallListType`, `smallListInlineCapacity`, `smallListSpillAllocator`, `collectionOperation`, `collectionOperationOutput`, `collectionOperationFailure`, `collectionOperationEffect`, `collectionOperationAllocation`, `collectionOperationMutation`, `mapType`, `mapKey`, `mapValue`, `mapAllocator`, `listLiteral`, `listLiteralLength`, `listLiteralIndexBase`, `listLiteralIndexPolicy`, `listLiteralItem` | collection declaration / metadata | collection types and literals | no | Collection shape, operation contracts, allocation, mutation, completeness, and literal contents remain independently retrievable. |
| `memoryHeap`, `memoryArena`, `memoryAllocationSource`, `memoryStackLimit` | memory contract | no | no | Each line should state one memory policy, arena allocation, allocation source, or bound. |
| `domainLiteral`, `storage`, `sharedState` | storage declaration | values or storage slots | no by itself | `sharedState` is exceptional and requires owner/guard metadata. |
| `domainLiteralSource`, `domainLiteralTrust`, `domainLiteralValidation`, `literalTrust`, `runtimeBinding`, `runtimeBindingPrecondition`, `runtimeBindingFailure`, `trustBoundary`, `trustBoundaryKind`, `trustBoundaryInput`, `trustBoundaryOutput`, `trustBoundaryValidator`, `trustBoundarySource`, `typeLiteralEncoding`, `typeLiteralTerminator` | binding metadata / contracts | no | no | Records platform/runtime provenance, literal trust, literal validation, and trust requirements without creating rename or behavior-changing relations. |
| `read`, `set` | storage access / mutation | reads create values; writes do not | yes | Scope field must be explicit: `local`, `module`, or `sharedState`; shared-state access must expose guard authority. |
| `call`, `arg`, `timeout`, `cancelOn`, `run`, `start`, `await`, `bind`, `bindOk`, `bindError`, `ignoreOk` | executable action / dataflow | call and result symbols | yes | Existing strong lifecycle should keep its verbs; async work must be started, awaited, and cancellable where time or I/O is involved. |
| `fieldGet`, `makeError` | executable action / dataflow | extracted values or error values | yes | Prevents hidden field access and hidden failure construction. |
| `label`, `branch`, `branchIf`, `branchIfError`, `returnOk`, `returnError` | control flow | labels only | yes | Branching stays explicit and single-target. |
| `defer`, `deferLog`, `deferLogSink`, `deferAwaitLog`, `deferWhenExitLog` | cleanup lifecycle | defer symbol | yes at operation exit | Resource and guard cleanup must be visible after acquisition. |
| `declareFailure` | failure declaration | failure value | no | For static failure values without payload. |
| `section`, `group`, `groupPurpose`, `groupInput`, `groupOutput`, `groupError`, `groupFailure`, `groupTiming` | attention grouping | no | no | Metadata only; must not imply scope or data creation. |
| `literal`, `literalBytes`, `literalDigest`, `literalPreview`, `literalSource` | literal metadata | literal resource symbol | no | Keeps long payloads out of local code regions. |
| `retryPolicy`, `retryMaxAttempts`, `retryInitialDelay`, `retryMaximumDelay`, `retryJitter`, `useRetry` | policy / behavior | policy symbol | only `useRetry` | Policy metadata is inert until explicitly attached to a call or manual loop. |

### Standard Library Audit Evidence

The standard library currently has strong structural syntax, but weaker naming
than the recommended agent-facing profile:

```text
stdlib .as files: 28
call lines: 1240
call names missing Call suffix: 704
call names of three characters or fewer: 222
bind result names of three characters or fewer: 163
label names of five characters or fewer: 81
```

That does not mean the library is unusable. It means the library carries a C
compatibility shape and test-harness shorthand that should not be the canonical
agent-generated style.

### Standard Library Syntax Audit

| Stdlib area | Current examples | Attention/tokenization issue | Syntax change needed | Priority |
| --- | --- | --- | --- | --- |
| Module headers | `# ====`, `# Operations:` | Decorative comments are not stable syntax anchors and are hard to query consistently. | Add `section stdlib.string`, `section stdlib.math`, and operation catalog metadata. Keep prose only as typed comments. | P1 |
| Public operation names copied from C | `strlen`, `strcmp`, `strchr`, `strdup`, `imaxabs`, `fmaFloat` | C names are compact but semantically sparse for an agent that must infer intent from subtokens. | In the agent-facing surface, rename the operation signature itself: `stringByteLength`, `compareCString`, `findFirstCharacter`, `duplicateCString`, `absoluteMaxWidthInt`, `fusedMultiplyAddFloat`. Add `runtimeBinding` when a semantic signature binds to a runtime or C primitive. Keep exact C names only in explicit compatibility sections when exact names are needed. | P1 |
| Public argument names | `s`, `a`, `b`, `n`, `c`, `x`, `y`, `buf`, `src`, `dst`, `len`, `idx` | One-letter and C-abbreviated arguments break local recoverability when a line is retrieved alone. | In agent-facing APIs use semantic names: `inputText`, `left`, `right`, `candidateNumber`, `characterCode`, `sourceBuffer`, `destinationBuffer`, `byteCount`, `byteOffset`. | P1 |
| Internal call stems | `lt`, `gt`, `eq`, `h1`, `p1`, `m1`, `c1`, `s1` | Short stems lose the lifecycle relation between `call`, `arg`, `run`, and `bind`. | Rename canonical examples to role-marked stems: `leftLessThanRightCall`, `secondsToHoursCheckCall`, `parseDecimalPositiveCaseCall`, `signalKillReadCall`. | P0 |
| Internal bind names | `r`, `d`, `ok`, `p1`, `buf`, `st` | The value role is unclear without nearby context, which is exactly the case attention can lose in long files. | Use role names: `remainderValue`, `differenceValue`, `comparisonSucceeded`, `allocatedBuffer`, `randomStatePointer`. | P0 |
| Labels | `retT`, `retLt`, `retGt`, `c1Lbl`, `s1Lbl`, `start` | Labels are branch targets, so vague labels weaken control-flow recovery. | Use semantic branch labels: `returnTrue`, `returnLessThan`, `returnGreaterThan`, `firstComparisonPassed`, `startCompareInt`. | P1 |
| Predicate return surface | `isLessInt` and `isLeapYear` returning C integer result types | Names beginning with `is` read as Bool predicates, but integer return types create a split mental model. | Agent-facing predicates should return `Bool`. If C integer compatibility is needed, expose explicit names such as `isLeapYearAsInt` or `isLessIntAsCInt`. | P1 |
| C-style true and false constants | `t`, `f`, `trueL`, `falseL` as integer constants | The syntax makes boolean intent depend on naming instead of the value type. | Use value-level `true` and `false` for `Bool`. Use names like `trueIntValue` and `falseIntValue` only for explicit C integer APIs. | P1 |
| Stdlib smoke-test call naming | `p1`, `h1`, `m1`, `g1`, `cl1`, `ly1` | Numbered test calls are compact but hard to inspect or repair from a small region. | Add `section stdlib.module.smokeTest` and use semantic test stems such as `parseDecimalPositiveCaseCall` or `leapYearCenturyNegativeCaseCall`. | P1 |
| Direct C boundary calls | `c.putchar`, `c.malloc`, `c.free`, `c.time` | These are useful boundary markers, but repeated direct use can crowd out the semantic operation intent. | Keep direct C targets as low-level boundary syntax. Put common uses behind semantic stdlib operation signatures with declared effects and memory lines. | Keep |
| Effects and memory in stdlib | `effect op read memory.buffer`, `memory op heap no` | These are short, fixed, and high-signal. | Keep unchanged. They already align with the attention profile better than most alternatives. | Keep |
| Numeric aliases and C width names | `I64`, `CSignedInt32`, `CFloat64` | Width names are precise and generally token-stable, but C names can dominate public APIs. | Keep exact width names for type precision. Prefer semantic operation and argument names around them so type tokens are not the only meaning carriers. | Keep |
| Constants for errno and signals | `errEAGAIN`, `sigSIGKILL` | Exact C constants are correct but tokenization is noisy and acronym-heavy. | In the agent-facing surface, use semantic typed literals such as `domainLiteral signalKillNumber CSignedInt32 9` plus `domainLiteralSource signalKillNumber posix.SIGKILL`. Keep exact C names only in explicit compatibility sections when exact spelling is required. | P2 |
| Pointer and buffer helpers | `buffer`, `offset` are good; `buf`, `src`, `dst`, `len`, `idx` still appear | The clearer names already show the direction; abbreviations should not remain in public or teaching examples. | Standardize on `buffer`, `sourceBuffer`, `destinationBuffer`, `byteCount`, and `byteOffset` in public surfaces and key locals. | P1 |
| Algorithm notes | Prose comments inside math, string, and parse routines | Important invariants can sit in generic comments that do not have a stable role token. | Convert important notes to typed comment lines: `# invariant:`, `# rationale:`, `# timing:`, `# safety:`. | P1 |
| Compatibility surface versus canonical examples | Mixed C-shaped names and AgentScript-native helpers in the same files | The agent cannot always tell which form should be copied into new source. | Mark exact C compatibility and preferred agent-facing operations with syntax-level metadata, for example `section stdlib.string.cCompatibility` and `section stdlib.string.agentFacing`. Agent-facing signatures should be semantic directly. | P1 |

### Refined Standard Library Syntax Choices

The standard library should mostly change names and sectioning, not add a large
new stdlib-specific verb family. The refined surface is:

| Stdlib syntax area | Refined signature | Use when | Avoid |
| --- | --- | --- | --- |
| Compatibility section | `section stdlib.<moduleName>.cCompatibility` | Exact C-shaped names such as `strcmp` or `sigSIGKILL` when exact spelling is required. | Decorative banners as the only boundary marker. |
| Agent-facing section | `section stdlib.<moduleName>.agentFacing` | Preferred names agents should copy. | Mixing C-shaped names and preferred APIs with no section anchor. |
| Semantic operation signature | `operation compareCString`<br>`input compareCString left CNullTerminatedByteString`<br>`input compareCString right CNullTerminatedByteString` | Preferred stdlib surface for agents. The semantic name is the operation signature, not a second name over `strcmp`. | Defining a terse operation first and then adding a second relation verb to explain the real name. |
| Runtime binding | `runtimeBinding compareCString runtime.cstring.compare` | Recording that a semantic operation signature binds to a runtime primitive with a typed failure surface. | Binding a typed AgentScript result directly to a raw C function whose native contract does not expose those errors. |
| Runtime binding contract | `runtimeBindingPrecondition compareCString "left is a validated CNullTerminatedByteString value"`<br>`runtimeBindingPrecondition compareCString "right is a validated CNullTerminatedByteString value"`<br>`runtimeBindingFailure compareCString CStringCompareError.InvalidCStringInput` | Making runtime safety and typed error mapping checkable. | Returning `Result ... CStringCompareError` from a C binding without naming where those errors originate. |
| Trust-boundary type | `type RawCStringPointer COpaqueMemoryAddress`<br>`trustBoundary CNullTerminatedByteString`<br>`trustBoundaryKind CNullTerminatedByteString rawPointerToValidatedCString`<br>`trustBoundaryInput CNullTerminatedByteString RawCStringPointer`<br>`trustBoundaryValidator CNullTerminatedByteString validateCString`<br>`trustBoundarySource CNullTerminatedByteString validatedRuntimeValue` | Splitting untrusted raw pointers from values proven safe enough for C-string runtime bindings. | Passing raw pointer-shaped values into C-string operations under a trusted-looking type name. |
| C string literal contract | `typeLiteralEncoding CNullTerminatedByteString utf8`<br>`typeLiteralTerminator CNullTerminatedByteString nullByte`<br>`domainLiteralTrust smokeLeftText trustedStaticLiteral` | Making static C string literal safety and null-termination explicit. | Letting C string literal typing imply hidden null-byte behavior. |
| Semantic lock guard operation | `operation acquireMetricsLockGuard`<br>`runtimeBinding acquireMetricsLockGuard metricsLock.acquire` | Agent-facing guard acquisition that mirrors semantic guard release. | Calling raw `metricsLock.acquire` while release uses a semantic operation. |
| Cleanup logging | `effect getAccountBalanceWithRetry log cleanup.metricsLockRelease`<br>`deferLog metricsLockReleaseDefer releaseMetricsLockGuard metricsLockGuardToken`<br>`deferLogSink metricsLockReleaseDefer cleanup.metricsLockRelease` | Fallible cleanup whose error is logged instead of returned. | Hidden log effects inside `deferLog`. |
| Record constructor contract | `operation createAccountBalanceResponseRecord`<br>`output createAccountBalanceResponseRecord Result AccountBalanceResponse RecordCreateError`<br>`recordConstructor createAccountBalanceResponseRecord AccountBalanceResponse`<br>`recordConstructorFailure createAccountBalanceResponseRecord RecordCreateError.InvalidFieldValue` | Semantic record construction that can fail and can be wrapped by a domain-level response build error. | Calling `record.create.AccountBalanceResponse` without a local failure model. |
| Public semantic operation | `operation compareCString`<br>`input compareCString left CNullTerminatedByteString`<br>`input compareCString right CNullTerminatedByteString`<br>`output compareCString Result CSignedInt32 CStringCompareError` | Agent-facing stdlib operations that can surface semantic errors. | `Result ... Void` paired with `bindError`. |
| Bool predicate operation | `operation isLeapYear`<br>`output isLeapYear Result Bool TimePredicateError` | Agent-facing predicates with a semantic error surface. | Integer return types for `is*` names unless the name ends in `AsCInt`. |
| C integer predicate surface | `operation isLeapYearAsCInt`<br>`output isLeapYearAsCInt Result CSignedInt32 TimePredicateError` | Compatibility with C integer true/false APIs when failures are surfaced. | Returning `CSignedInt32` from plain `isLeapYear`. |
| Smoke test section | `section stdlib.<moduleName>.smokeTest` | Test bodies inside stdlib files. | Number-only call names with no local semantic anchor. |
| Smoke test call | `call <semanticTestCaseName>Call <operationName>` | Replacing `p1`, `h1`, `m1`, `ly1`. | `testCall` or `smokeCall` as new verbs. |
| Constants and signals | `domainLiteral signalKillNumber CSignedInt32 9`<br>`domainLiteralSource signalKillNumber posix.SIGKILL` | Giving agents a semantic typed value for a signal number while preserving platform provenance. | Requiring generated code to copy acronym-heavy C constants when exact C spelling is not needed, or leaving `9` as an unexplained universal-looking literal. |
| Buffer arguments and effects | `input <operationName> sourceBuffer COpaqueMemoryAddress`<br>`input <operationName> destinationBuffer COpaqueMemoryAddress`<br>`input <operationName> byteCount CByteCount`<br>`effect <operationName> read sourceBuffer`<br>`effect <operationName> write destinationBuffer` | Public memory-like APIs. | Public `buf`, `src`, `dst`, `len`, `idx`, or broad `memory.buffer` effects when argument-linked regions are known. |
| Algorithm notes | `# invariant: <text>`<br>`# rationale: <text>`<br>`# safety: <text>` | Important local reasoning beside loops or pointer code. | Adding new note verbs for ordinary comments. |

The standard library should therefore be treated as two surfaces:

```text
C compatibility surface:
  preserve exact C-shaped names only where exact spelling matters

agent-facing surface:
  declare semantic operation signatures, role suffixes, Bool predicates, and
  section anchors directly
```

The goal is not to erase C compatibility. The goal is to prevent C compatibility
from becoming the style that agents copy when generating ordinary AgentScript.

## What Not To Change

Do not add:

```text
infix operators
semicolons
braces
parentheses for calls
generic angle brackets
comma-separated argument lists
implicit current call
implicit current operation
implicit exception paths
implicit async behavior
indentation-sensitive blocks
```

These features help humans compress code, but they make the agent recover more
hidden structure from fewer explicit anchors.

Do not replace:

```text
call / arg / run / bind / branchIfError
```

with expression syntax. That lifecycle is the strongest part of AgentScript.

## Priority Order

### Immediate Syntax Rules

Adopt these first:

```text
canonical primitive target spelling
shared stem requirement
verb schema registry for every non-comment verb
standalone comments in canonical source
identifier segment review heuristic
single-target branchIf only
true/false for value-level Bool literals
storage local immutable / storage local mutable / set local replacing canonical const/var/set
long literal metadata
literal source metadata for external payloads
```

### Next Syntax Additions

Add:

```text
section
group
groupPurpose
groupInput
groupOutput
groupError
groupFailure
groupTiming
recordLayout
recordAlign
storage
domainLiteral
sharedState
sharedStateOwner
sharedStateGuard
guardTokenSource
guardTokenProtects
guardTokenOwner
guardTokenRelease
read
domainLiteralSource
runtimeBinding
runtimeBindingPrecondition
runtimeBindingFailure
operationBody
trustBoundary
trustBoundaryKind
trustBoundaryInput
trustBoundaryOutput
trustBoundaryValidator
trustBoundarySource
typeLiteralEncoding
typeLiteralTerminator
domainLiteralTrust
domainLiteralValidation
literalTrust
recordConstructor
recordConstructorFailure
jsonCodecStrict
jsonCodecUnknownFields
jsonCodecDecodeTarget
jsonCodecEncodeTarget
jsonCodecRequiredField
jsonCodecInput
jsonCodecOutput
jsonCodecDecodeFailure
jsonCodecEncodeFailure
jsonCodecLimit
intrinsicName
dependencyPath
dependencyFailure
memoryHeap
memoryArena
memoryAllocationSource
memoryStackLimit
declareFailure
fieldGet
useRetry
deferLog
deferLogSink
deferRunOn
deferOrder
deferFailurePolicy
deferConsumes
deferAwaitLog
deferAwaitLogSink
deferAwaitTimeout
deferWhenExitLog
deferWhenExitLogSink
literalBytes
literalDigest
literalPreview
literalSource
recordBuilder
recordSet
recordCopy
recordBuild
recordBuildFailure
listType
listAllocator
arrayType
arrayLength
sliceType
smallListType
smallListInlineCapacity
smallListSpillAllocator
collectionOperation
collectionOperationArg
collectionOperationOutput
collectionOperationFailure
collectionOperationEffect
collectionOperationAllocation
collectionOperationMutation
collectionOperationIndexPolicy
collectionOperationLengthSource
collectionOperationBorrowSource
collectionOperationCapacitySource
collectionOperationSpillAllocator
collectionOperationSpillFailure
mapType
mapKey
mapValue
mapAllocator
listLiteral
listLiteralLength
listLiteralIndexBase
listLiteralIndexPolicy
listLiteralItem
```

Evaluate selectively, not blanket-add:

```text
typeParameter
retryMaxAttempts
retryInitialDelay
retryMaximumDelay
retryJitter
```

### Later Syntax Evaluation

Evaluate:

```text
effectRead
effectWrite
effectEmit
effectNetwork
securityBoundary
resourceAcquire
resourceRelease
```

Only add these if they improve attention-local clarity more than they increase
surface area.

## Final Recommendation

AgentScript should be refined around this syntax identity:

```text
AgentScript is a transformer-native command tape where every line is an
attention-local semantic record, every important relation has a repeated
anchor, every role is named, long regions have explicit local anchors, and
every spelling is canonical.
```

The language should not become shorter. It should become more regular.

The win condition is that an agent can retrieve any line or small region and
immediately recover:

```text
what is happening
what value is involved
what call owns the value
what role the symbol plays
what can fail
where failure goes
what type or effect is involved
what region or operation this belongs to
```

That is how AgentScript takes better advantage of transformer attention:
not by hiding meaning in syntax, but by giving attention stable, repeated,
canonical anchors to lock onto.

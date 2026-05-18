# AgentScript 1.0 Enterprise Scope

This is the pruned 1.0 list after checking the current repo surface and asking
whether each missing feature is truly needed for complex enterprise
applications.

The filter is AgentScript's own style guide:

- One semantic edge per line.
- Every meaningful element is name-addressable.
- Hidden behavior is illegal by default.
- Failure, effects, memory, cleanup, trust, and dependency behavior are visible.
- Control flow remains graphable.
- Abstractions increase recoverable context.

Status labels:

- `current` means the repo has executable compiler support or a documented
  implemented surface.
- `metadata` means parsed, highlighted, documented, or available as syntax
  research, but not a real runtime/codegen feature yet.
- `missing` means the repo does not yet have a meaningful implementation.
- `1.0 core` means required for AgentScript 1.0 if 1.0 targets enterprise apps.
- `1.0 contract` means required as checkable syntax, stdlib contract, linter
  rule, or dependency contract, but not necessarily built into the compiler core.
- `post-1.0` means useful, but not a blocker for enterprise 1.0.
- `reject` means it conflicts with the AgentScript style guide.

## Verification Notes

Current executable AgentScript already has the important base tape: operations,
operation headers, call/arg/run/bind lifecycle, labels, branches, returns,
typed errors, C ABI types, many `c.*` calls, pointer primitives, and some record
and import test files.

The current repo also has refined syntax research and VS Code support for many
future verbs, including storage classes, runtime bindings, trust boundaries,
record builders, collection contracts, JSON codecs, cleanup, and guard-token
syntax.

The enterprise gap is not mostly "copy more C, JS, or Rust features." The real
gap is app infrastructure expressed in AgentScript's style: schemas, typed
collections, JSON, HTTP, resources, validation, config, secrets, observability,
timeouts, cleanup, and dependency contracts.

## Enterprise 1.0 Required

These are truly needed for complex enterprise applications.

| Capability | Repo status | 1.0 decision | Why enterprise apps need it |
|---|---|---|---|
| Flat operation tape | `current` | `1.0 core` | Gives agents stable program structure and graphable control flow. |
| Call lifecycle | `current` | `1.0 core` | Enterprise code needs auditable dependency calls, not hidden expressions. |
| Explicit error flow | `current` / `metadata` | `1.0 core` | Service code needs recoverable failure paths, not exceptions. |
| Effect declarations | `current` headers | `1.0 core` | Required for review of database, network, filesystem, logging, metrics, and process effects. |
| Effect coverage checks | `missing` / partial lint | `1.0 core` | Declared effects must match called dependency effects or the metadata cannot be trusted. |
| Storage classes | `metadata` / compatibility aliases | `1.0 core` | Enterprise apps need visible local, module, immutable, mutable, and shared-state boundaries. |
| Runtime binding contracts | `metadata` | `1.0 core` | Bodyless stdlib/FFI operations must declare preconditions and failures. |
| Dependency contract tapes | `metadata` | `1.0 core` | External systems cannot be black boxes in enterprise code. |
| Shallow records | `current` intent, not nested | `1.0 core` | Domain entities, DTOs, config records, responses, and events need schemas. |
| Record builders | `metadata` | `1.0 core` | Large records need atomic construction without object literals. |
| Typed lists | `metadata` | `1.0 core` | Enterprise apps need collections of records for queries, responses, jobs, events, and validation errors. |
| Typed maps | `metadata` | `1.0 core` | Required for headers, config, lookup tables, indexes, caches, and keyed domain state. |
| Optional values | `missing` / convention only | `1.0 contract` | Optional JSON fields, nullable DB columns, and absent config values need typed presence semantics. |
| Typed JSON codecs | `metadata` | `1.0 contract` | Enterprise APIs need schema-backed decode/encode with explicit unknown-field and validation behavior. |
| HTTP server/contracts | `metadata` | `1.0 core` | The spec targets Node/Python-style app servers; routes, handlers, request/response, timeout, and middleware contracts are required. |
| Database/resource contracts | `metadata` | `1.0 contract` | Real apps need resource operations, transactions, and failure contracts without baking a DB into the language. |
| Transactions | `missing` | `1.0 contract` | Enterprise write workflows need commit/rollback edges and failure mapping. |
| Validation contracts | `metadata` | `1.0 contract` | Inputs must cross explicit raw-to-validated boundaries. |
| Config and environment | `partial` opaque inputs | `1.0 contract` | Deployment-specific config must be typed, validated, and auditable. |
| Secrets | `missing` | `1.0 contract` | Enterprise apps must distinguish secret values from normal strings and logs. |
| Security/auth metadata | `metadata` | `1.0 contract` | Authn, authz, tenant boundaries, PII, and permission checks need visible source edges. |
| Observability | `metadata` | `1.0 contract` | Logs, metrics, traces, audit events, and correlation IDs must be declared effects. |
| Typed time and duration | `partial` | `1.0 contract` | Timeouts, retries, SLAs, scheduling, and audit timestamps must not be raw integers. |
| Minimal structured async | `partial` / mostly stubbed | `1.0 core` | HTTP/database/file/network work needs bounded, cancellable async. |
| Cleanup/defer lifecycle | `metadata` / reserved | `1.0 core` | Connections, files, transactions, locks, and spans require explicit cleanup on every exit path. |
| Linter/CI checks | `current` partial | `1.0 core` | Enterprise teams need enforceable style laws, not only conventions. |

## Enterprise 1.0 Minimum Runtime

This is the smallest runtime surface that makes the above credible without
turning AgentScript into JavaScript.

| Runtime area | 1.0 minimum |
|---|---|
| Console | Keep current console support. |
| HTTP | Route to named handler operations; typed request and response records; declared route timeout. |
| JSON | Decode and encode typed records through generated or stdlib-backed operations. |
| Database/resource | Dependency contract only in core; drivers can be external as long as contracts expose effects, failures, async, and cleanup. |
| Async | `start`, `await`, `cancelOn`, and `timeout` for dependency calls; detached async illegal by default. |
| Cleanup | `deferLog` and `deferAwaitLog` with declared failure policy and log/metric effects. |
| Observability | Named log/metric/trace/audit operations with declared effects. |
| Config/secrets | Typed config reads and secret reads through dependency contracts. |

## Current Pruning Corrections

These are the changes from the earlier broad C/JS/Rust list.

| Earlier disposition | Correction | Reason |
|---|---|---|
| Maps were `post-1.0` | Move typed maps to `1.0 core` | Complex enterprise apps need keyed lookup and headers/config/index data. |
| Full async runtime was `post-1.0` | Split it: minimal structured async is `1.0 core`; task groups/channels are `post-1.0` | Web/database apps need cancellable async, but not every concurrency primitive. |
| Fixed arrays and slices were `1.0 core` | Downgrade to `1.0 contract` unless needed by C interop/performance | Enterprise apps mostly need lists/maps; arrays/slices are lower-level. |
| JSON was only `1.0 contract` | Keep contract, but treat runtime codec ops as enterprise-required stdlib | APIs cannot be credible without JSON decode/encode. |
| Shared-state guards were close to 1.0 | Keep `post-1.0` unless mutable shared state is unavoidable | Resource-oriented enterprise apps can avoid in-process shared mutation for 1.0. |
| `Option<T>` was `post-1.0` | Move to `1.0 contract` | Optional fields and nullable DB values are unavoidable. |
| Package manager was considered | Keep `post-1.0` | Versioned dependency metadata is needed; a full package manager is not 1.0 language core. |

## Feature Decisions

| Feature | Repo status | Enterprise need | 1.0 decision |
|---|---|---|---|
| `section` | `metadata` | High | `1.0 contract`; needed for large-file indexing and agent retrieval anchors. |
| `operationBody` | `metadata` | High | `1.0 contract`; distinguishes source, intrinsic, runtime binding, codec, dependency, and constructor bodies. |
| `typeParameter` | `metadata` | High | `1.0 contract`; needed for `Result`, `Option`, and typed collections without angle syntax. |
| `storage local/module mutable/immutable` | `metadata` | High | `1.0 core`; replace or formally alias `const`/`var`. |
| `runtimeBinding*` | `metadata` | High | `1.0 core`; required for stdlib and FFI truthfulness. |
| `trustBoundary*` | `metadata` | High | `1.0 contract`; required for raw input, JSON, pointers, secrets, and PII. |
| `recordBuilder` family | `metadata` | High | `1.0 core`; object literals stay rejected. |
| `collectionOperation*` | `metadata` | High | `1.0 core`; lists/maps need declared output, failure, effect, allocation, and mutation behavior. |
| `jsonCodec*` | `metadata` | High | `1.0 contract`; codec runtime can live in stdlib. |
| `deferLog` / `deferAwaitLog` | `metadata` / reserved | High | `1.0 core`; cleanup semantics must be real. |
| `start` / `await` / `cancelOn` / `timeout` | `current` tokens, partial semantics | High | `1.0 core`; real dependency-level async needed. |
| `sharedState` / guards / locks | `metadata` | Medium | `post-1.0`; not required if 1.0 discourages shared in-process state. |
| Worker pools/channels/task groups | `metadata` / reserved | Medium | `post-1.0`; useful but not enterprise 1.0 minimum. |
| Nested records | xfail / incomplete | Medium | `post-1.0`; enterprise can survive with flat records and IDs initially. |
| Enums with representation | partial | Medium | `1.0 contract`; needed for statuses, roles, state machines, and wire codes. |
| Decimal/money types | missing | High | `1.0 contract`; stdlib/domain types are enough, but raw floats are not acceptable for money. |
| Date/time/calendar types | partial | High | `1.0 contract`; stdlib-backed, typed, no raw timestamp soup. |
| Test/mocking contracts | partial tooling | Medium | `1.0 contract`; enterprise adoption needs dependency stubs and effect assertions. |

## Proposed Enterprise 1.0 Syntax

These sketches use the intended AgentScript shape: one verb, one fixed schema,
one semantic edge per line. They are syntax proposals, not a claim that the
current compiler lowers every line today.

### Sections And Operation Body Kind

```text
section module.orders.types
section module.orders.resources
section module.orders.http

operation getOrderHandler
operationBody getOrderHandler sourceTape

operation compareCString
operationBody compareCString runtimeBinding

operation decodeCreateOrderRequest
operationBody decodeCreateOrderRequest codecBinding
```

### Storage Classes

```text
storage module immutable orderLookupTimeout DurationMilliseconds 250
storage module immutable orderServiceName ServiceName "orders"
storage module mutable lastOrderHealthCheck UtcMilliseconds zeroTimestamp

storage local immutable normalizedOrderId OrderId orderId
storage local mutable lookupAttemptIndex I64 zeroCount
storage local mutable currentOrderList OrderList emptyOrderList
```

### Result, Option, And Type Parameters

```text
type OrderLookupResult Result
typeParameter OrderLookupResult 1 Order
typeParameter OrderLookupResult 2 OrderLookupError

type OptionalOrderNote Option
typeParameter OptionalOrderNote 1 OrderNote

optionNone missingOrderNote OptionalOrderNote
optionSome presentOrderNote OptionalOrderNote validatedOrderNote

call orderNotePresentCall OptionalOrderNote.isSome
arg orderNotePresentCall value presentOrderNote
run orderNotePresentCall
bind orderNoteIsPresent Bool orderNotePresentCall
```

### Records And Builders

```text
record CreateOrderRequest
recordLayout CreateOrderRequest row
recordAlign CreateOrderRequest 16
field CreateOrderRequest customerId CustomerId
field CreateOrderRequest sku ProductSku
field CreateOrderRequest quantity OrderQuantity
fieldOptional CreateOrderRequest note OptionalOrderNote
fieldSecurity CreateOrderRequest customerId tenantScoped

recordBuilder createOrderRequestBuilder CreateOrderRequest
recordSet createOrderRequestBuilder customerId validatedCustomerId
recordSet createOrderRequestBuilder sku validatedProductSku
recordSet createOrderRequestBuilder quantity validatedOrderQuantity
recordSet createOrderRequestBuilder note missingOrderNote
recordBuild createOrderRequestBuildCall createOrderRequestBuilder
recordBuildFailure createOrderRequestBuildCall RecordBuildError.InvalidFieldValue
run createOrderRequestBuildCall
bindOk createOrderRequest CreateOrderRequest createOrderRequestBuildCall
bindError createOrderRequestBuildError RecordBuildError createOrderRequestBuildCall
branchIfError createOrderRequestBuildCall createOrderRequestBuildFailed
```

### Typed Lists

```text
listType OrderList Order
listAllocator OrderList arena.request
listMutation OrderList immutableUpdate

collectionOperation OrderList.length
collectionOperationInput OrderList.length list OrderList
collectionOperationOutput OrderList.length I64
collectionOperationFailure OrderList.length none
collectionOperationEffect OrderList.length read list

collectionOperation OrderList.append
collectionOperationInput OrderList.append list OrderList
collectionOperationInput OrderList.append item Order
collectionOperationOutput OrderList.append Result OrderList OrderListAppendError
collectionOperationFailure OrderList.append OrderListAppendError.AllocationFailed
collectionOperationEffect OrderList.append read list
collectionOperationEffect OrderList.append read item
collectionOperationAllocation OrderList.append arena.request
collectionOperationMutation OrderList.append immutableUpdate

collectionOperation OrderList.get
collectionOperationInput OrderList.get list OrderList
collectionOperationInput OrderList.get index I64
collectionOperationOutput OrderList.get Result Order OrderListReadError
collectionOperationFailure OrderList.get OrderListReadError.IndexOutOfRange
collectionOperationEffect OrderList.get read list
collectionOperationEffect OrderList.get read index

call appendOrderCall OrderList.append
arg appendOrderCall list existingOrderList
arg appendOrderCall item createdOrder
run appendOrderCall
bindOk updatedOrderList OrderList appendOrderCall
bindError appendOrderError OrderListAppendError appendOrderCall
branchIfError appendOrderCall appendOrderFailed
```

### Typed Maps

```text
mapType HeaderMap
mapKey HeaderMap HeaderName
mapValue HeaderMap HeaderValue
mapAllocator HeaderMap arena.request
mapMutation HeaderMap immutableUpdate

collectionOperation HeaderMap.get
collectionOperationInput HeaderMap.get map HeaderMap
collectionOperationInput HeaderMap.get key HeaderName
collectionOperationOutput HeaderMap.get Result HeaderValue HeaderMapReadError
collectionOperationFailure HeaderMap.get HeaderMapReadError.KeyNotFound
collectionOperationEffect HeaderMap.get read map
collectionOperationEffect HeaderMap.get read key

collectionOperation HeaderMap.insert
collectionOperationInput HeaderMap.insert map HeaderMap
collectionOperationInput HeaderMap.insert key HeaderName
collectionOperationInput HeaderMap.insert value HeaderValue
collectionOperationOutput HeaderMap.insert Result HeaderMap HeaderMapWriteError
collectionOperationFailure HeaderMap.insert HeaderMapWriteError.AllocationFailed
collectionOperationEffect HeaderMap.insert read map
collectionOperationEffect HeaderMap.insert read key
collectionOperationEffect HeaderMap.insert read value
collectionOperationAllocation HeaderMap.insert arena.request
collectionOperationMutation HeaderMap.insert immutableUpdate

call authorizationHeaderReadCall HeaderMap.get
arg authorizationHeaderReadCall map requestHeaders
arg authorizationHeaderReadCall key authorizationHeaderName
run authorizationHeaderReadCall
bindOk authorizationHeader HeaderValue authorizationHeaderReadCall
bindError authorizationHeaderReadError HeaderMapReadError authorizationHeaderReadCall
branchIfError authorizationHeaderReadCall authorizationHeaderMissing
```

### JSON Codecs

```text
jsonCodec CreateOrderRequest
jsonCodecRecord CreateOrderRequest CreateOrderRequest
jsonCodecStrict CreateOrderRequest yes
jsonCodecUnknownFields CreateOrderRequest reject
jsonCodecRequiredField CreateOrderRequest customerId
jsonCodecRequiredField CreateOrderRequest sku
jsonCodecRequiredField CreateOrderRequest quantity
jsonCodecOptionalField CreateOrderRequest note
jsonCodecInput CreateOrderRequest decode bytes RawJsonBytes
jsonCodecOutput CreateOrderRequest decode Result CreateOrderRequest JsonDecodeError
jsonCodecDecodeFailure CreateOrderRequest JsonDecodeError.InvalidJson
jsonCodecDecodeFailure CreateOrderRequest JsonDecodeError.SchemaMismatch
jsonCodecInput CreateOrderRequest encode value CreateOrderRequest
jsonCodecOutput CreateOrderRequest encode Result JsonBytes JsonEncodeError
jsonCodecEncodeFailure CreateOrderRequest JsonEncodeError.EncodeFailed
jsonCodecLimit CreateOrderRequest maximumBytes createOrderRequestJsonMaximumBytes

call createOrderRequestDecodeCall json.decode.CreateOrderRequest
arg createOrderRequestDecodeCall bytes requestBodyBytes
run createOrderRequestDecodeCall
bindOk createOrderRequest CreateOrderRequest createOrderRequestDecodeCall
bindError createOrderRequestDecodeError JsonDecodeError createOrderRequestDecodeCall
branchIfError createOrderRequestDecodeCall createOrderRequestDecodeFailed
```

### HTTP Server And Route Contracts

```text
webServer orderApi
serverHost orderApi configuredHttpHost
serverPort orderApi configuredHttpPort

route orderApi createOrderRoute POST "/orders" createOrderHandler
routeRequestBody createOrderRoute RawJsonBytes
routeRequestCodec createOrderRoute CreateOrderRequest
routeResponseCodec createOrderRoute CreateOrderResponse
routeTimeout createOrderRoute standardHttpRequestTimeout
routeCancellation createOrderRoute requestCancellationToken
routeAuthPolicy createOrderRoute requireAuthenticatedUser
routeEffect createOrderRoute read http.request.body
routeEffect createOrderRoute write http.response
routeEffect createOrderRoute read database.orders
routeEffect createOrderRoute write database.orders

operation createOrderHandler
operationBody createOrderHandler sourceTape
input createOrderHandler httpRequest HttpRequest
input createOrderHandler requestCancellationToken CancellationToken
output createOrderHandler Result HttpResponse CreateOrderHandlerError
effect createOrderHandler read http.request.body
effect createOrderHandler write http.response
effect createOrderHandler read database.orders
effect createOrderHandler write database.orders
effect createOrderHandler emit trace.createOrderHandler
memoryStackLimit createOrderHandler 16KiB
async createOrderHandler yes
```

### Dependency And Resource Contracts

```text
dependency postgres
dependencyVersion postgres "16"
dependencySource postgres registry
dependencyEffect postgres network.tcp
dependencyEffect postgres filesystem.socket
dependencyFailure postgres DatabaseConnectionError

resource orderStore
resourceKind orderStore postgresTable
resourceDependency orderStore postgres
resourceRecord orderStore Order
resourceKey orderStore OrderId
resourceEffect orderStore read database.orders
resourceEffect orderStore write database.orders

resourceOperation orderStore.findById
resourceOperationInput orderStore.findById orderId OrderId
resourceOperationOutput orderStore.findById Result Order OrderStoreReadError
resourceOperationFailure orderStore.findById OrderStoreReadError.NotFound
resourceOperationFailure orderStore.findById OrderStoreReadError.DatabaseUnavailable
resourceOperationEffect orderStore.findById read database.orders
resourceOperationAsync orderStore.findById yes

call orderLookupCall orderStore.findById
arg orderLookupCall orderId normalizedOrderId
timeout orderLookupCall orderLookupTimeout
cancelOn orderLookupCall requestCancellationToken
start orderLookupCall
await orderLookupCall
bindOk existingOrder Order orderLookupCall
bindError orderLookupError OrderStoreReadError orderLookupCall
branchIfError orderLookupCall orderLookupFailed
```

### Transactions

```text
transactionPolicy createOrderTransactionPolicy
transactionResource createOrderTransactionPolicy orderStore
transactionIsolation createOrderTransactionPolicy serializable
transactionTimeout createOrderTransactionPolicy createOrderTransactionTimeout
transactionFailure createOrderTransactionPolicy TransactionError.BeginFailed
transactionFailure createOrderTransactionPolicy TransactionError.CommitFailed
transactionFailure createOrderTransactionPolicy TransactionError.RollbackFailed

call beginCreateOrderTransactionCall transaction.begin
arg beginCreateOrderTransactionCall policy createOrderTransactionPolicy
timeout beginCreateOrderTransactionCall createOrderTransactionTimeout
cancelOn beginCreateOrderTransactionCall requestCancellationToken
start beginCreateOrderTransactionCall
await beginCreateOrderTransactionCall
bindOk createOrderTransaction TransactionHandle beginCreateOrderTransactionCall
bindError beginCreateOrderTransactionError TransactionError beginCreateOrderTransactionCall
branchIfError beginCreateOrderTransactionCall beginCreateOrderTransactionFailed

deferAwaitLog rollbackCreateOrderTransactionDefer transaction.rollback createOrderTransaction
deferRunOn rollbackCreateOrderTransactionDefer error
deferFailurePolicy rollbackCreateOrderTransactionDefer logAndContinue
deferLogSink rollbackCreateOrderTransactionDefer observability.transactionRollback

call commitCreateOrderTransactionCall transaction.commit
arg commitCreateOrderTransactionCall transaction createOrderTransaction
timeout commitCreateOrderTransactionCall createOrderTransactionTimeout
cancelOn commitCreateOrderTransactionCall requestCancellationToken
start commitCreateOrderTransactionCall
await commitCreateOrderTransactionCall
bindOk committedCreateOrderTransaction TransactionCommitStatus commitCreateOrderTransactionCall
bindError commitCreateOrderTransactionError TransactionError commitCreateOrderTransactionCall
branchIfError commitCreateOrderTransactionCall commitCreateOrderTransactionFailed
deferCancel rollbackCreateOrderTransactionDefer commitCreateOrderTransactionCall
```

### Minimal Structured Async

```text
call inventoryReserveCall inventoryService.reserveSku
arg inventoryReserveCall sku requestedProductSku
arg inventoryReserveCall quantity requestedOrderQuantity
timeout inventoryReserveCall inventoryReserveTimeout
cancelOn inventoryReserveCall requestCancellationToken
start inventoryReserveCall
await inventoryReserveCall
bindOk inventoryReservation InventoryReservation inventoryReserveCall
bindError inventoryReserveError InventoryReserveError inventoryReserveCall
branchIfError inventoryReserveCall inventoryReserveFailed
```

### Cleanup And Defer

```text
call databaseConnectionOpenCall database.openConnection
arg databaseConnectionOpenCall config databaseConnectionConfig
timeout databaseConnectionOpenCall databaseConnectTimeout
cancelOn databaseConnectionOpenCall requestCancellationToken
start databaseConnectionOpenCall
await databaseConnectionOpenCall
bindOk databaseConnection DatabaseConnection databaseConnectionOpenCall
bindError databaseConnectionOpenError DatabaseConnectionError databaseConnectionOpenCall
branchIfError databaseConnectionOpenCall databaseConnectionOpenFailed

deferAwaitLog databaseConnectionCloseDefer database.closeConnection databaseConnection
deferRunOn databaseConnectionCloseDefer anyExit
deferFailurePolicy databaseConnectionCloseDefer logAndContinue
deferLogSink databaseConnectionCloseDefer observability.databaseConnectionClose
effect createOrderHandler emit log.databaseConnectionCloseFailure
```

### Config And Secrets

```text
configKey configuredHttpPort
configKeyType configuredHttpPort HttpPort
configKeySource configuredHttpPort environment.HTTP_PORT
configKeyRequired configuredHttpPort yes
configKeyValidator configuredHttpPort validateHttpPort

secretKey databasePassword
secretKeyType databasePassword DatabasePassword
secretKeySource databasePassword secretStore.DATABASE_PASSWORD
secretKeyRequired databasePassword yes
secretKeyRedaction databasePassword always
secretKeyEffect databasePassword read secrets.database

call databasePasswordReadCall config.readSecret
arg databasePasswordReadCall key databasePassword
run databasePasswordReadCall
bindOk loadedDatabasePassword DatabasePassword databasePasswordReadCall
bindError databasePasswordReadError SecretReadError databasePasswordReadCall
branchIfError databasePasswordReadCall databasePasswordReadFailed
```

### Validation And Trust Boundaries

```text
type RawOrderIdText RawText
type OrderId ValidatedText
typeTrust OrderId trusted
typeRepresentation OrderId SmallString 64

trustBoundary OrderId
trustBoundaryKind OrderId rawTextToValidatedIdentifier
trustBoundaryInput OrderId RawOrderIdText
trustBoundaryOutput OrderId OrderId
trustBoundaryValidator OrderId validateOrderId
trustBoundarySource OrderId http.pathParameter
trustBoundarySource OrderId trustedStaticLiteral

validator validateOrderId
validatorInput validateOrderId rawOrderId RawOrderIdText
validatorOutput validateOrderId Result OrderId OrderIdValidationError
validatorGuarantee validateOrderId "OrderId is non-empty and contains only canonical identifier characters"
validatorFailure validateOrderId OrderIdValidationError.Empty
validatorFailure validateOrderId OrderIdValidationError.InvalidCharacter

call orderIdValidationCall validateOrderId
arg orderIdValidationCall rawOrderId rawOrderIdText
run orderIdValidationCall
bindOk normalizedOrderId OrderId orderIdValidationCall
bindError orderIdValidationError OrderIdValidationError orderIdValidationCall
branchIfError orderIdValidationCall orderIdValidationFailed
```

### Security, Auth, Tenant, And PII Metadata

```text
securityPolicy requireAuthenticatedUser
securityPolicyKind requireAuthenticatedUser authentication
securityPolicyInput requireAuthenticatedUser authorizationHeader HeaderValue
securityPolicyOutput requireAuthenticatedUser Result AuthenticatedUser AuthError
securityPolicyFailure requireAuthenticatedUser AuthError.MissingCredential
securityPolicyFailure requireAuthenticatedUser AuthError.InvalidCredential

authorizationPolicy requireOrderReadPermission
authorizationPolicySubject requireOrderReadPermission authenticatedUser
authorizationPolicyAction requireOrderReadPermission order.read
authorizationPolicyResource requireOrderReadPermission orderStore
authorizationPolicyOutput requireOrderReadPermission Result AuthorizationDecision AuthorizationError

operationSecurity createOrderHandler requireAuthenticatedUser
operationAuthorization createOrderHandler requireOrderReadPermission
operationTenantBoundary createOrderHandler tenantId

fieldSecurity CustomerRecord email pii
fieldSecurity CustomerRecord tenantId tenantScoped
fieldRedaction CustomerRecord email logs.masked
fieldRedaction CustomerRecord email traces.masked
```

### Observability

```text
traceSpan createOrderHandlerSpan
traceSpanOperation createOrderHandlerSpan createOrderHandler
traceSpanField createOrderHandlerSpan orderId OrderId
traceSpanField createOrderHandlerSpan tenantId TenantId

logEvent orderLookupFailedLog
logEventLevel orderLookupFailedLog error
logEventField orderLookupFailedLog orderId OrderId
logEventField orderLookupFailedLog failureCode OrderLookupFailureCode
logEventRedaction orderLookupFailedLog customerEmail masked

metric orderLookupLatency
metricKind orderLookupLatency histogram
metricUnit orderLookupLatency milliseconds
metricField orderLookupLatency routeName RouteName

auditEvent orderCreatedAudit
auditEventAction orderCreatedAudit order.created
auditEventSubject orderCreatedAudit authenticatedUserId
auditEventResource orderCreatedAudit createdOrderId

effect createOrderHandler emit trace.createOrderHandler
effect createOrderHandler emit log.orderLookupFailed
effect createOrderHandler emit metric.orderLookupLatency
effect createOrderHandler emit audit.orderCreated

call orderLookupFailedLogCall observability.log
arg orderLookupFailedLogCall event orderLookupFailedLog
arg orderLookupFailedLogCall orderId normalizedOrderId
arg orderLookupFailedLogCall failureCode orderLookupFailureCode
run orderLookupFailedLogCall
ignoreOk orderLookupFailedLogCall Void
bindError orderLookupFailedLogError ObservabilityWriteError orderLookupFailedLogCall
branchIfError orderLookupFailedLogCall orderLookupFailedLogWriteFailed
```

### Effect, Failure, Memory, And Trust Checks

```text
checkProfile enterprise1
checkRule enterprise1 lineAtomicity required
checkRule enterprise1 ownerNameMatchesLine required
checkRule enterprise1 dependencyContractCoverage required
checkRule enterprise1 effectCoverage required
checkRule enterprise1 failureCoverage required
checkRule enterprise1 asyncCoverage required
checkRule enterprise1 cleanupCoverage required
checkRule enterprise1 memoryAllocationCoverage required
checkRule enterprise1 trustBoundaryCoverage required
checkRule enterprise1 secretRedactionCoverage required
checkRule enterprise1 observabilityEffectCoverage required

checkScope enterprise1 allOperations
checkSeverity enterprise1 error
```

### Runtime Binding Contracts

```text
operation stringByteLength
operationBody stringByteLength runtimeBinding
input stringByteLength inputText CNullTerminatedByteString
output stringByteLength Result CByteCount CStringLengthError
effect stringByteLength read inputText
memoryHeap stringByteLength no
async stringByteLength no
runtimeBinding stringByteLength runtime.cstring.length
runtimeBindingPrecondition stringByteLength "inputText is a validated CNullTerminatedByteString value"
runtimeBindingFailure stringByteLength CStringLengthError.InvalidCStringInput
runtimeBindingFailure stringByteLength CStringLengthError.RuntimeLengthFailed
```

### Dependency Test And Mock Contracts

```text
testDouble orderStoreFake
testDoubleFor orderStoreFake orderStore
testDoubleOperation orderStoreFake orderStore.findById
testDoubleInput orderStoreFake orderId existingOrderId
testDoubleOutput orderStoreFake Result Order OrderStoreReadError
testDoubleBehavior orderStoreFake returnOk existingOrder

testCovers createOrderHandlerHappyPath createOrderHandler
testRequiresEffect createOrderHandlerHappyPath read database.orders
testRequiresEffect createOrderHandlerHappyPath write database.orders
testAssertsLog createOrderHandlerHappyPath orderCreatedAudit
testAssertsMetric createOrderHandlerHappyPath orderLookupLatency
```

## Not Needed For Enterprise 1.0

These are familiar from C, JavaScript, or Rust, but are not required for complex
enterprise apps in AgentScript 1.0.

| Feature | Decision | Reason |
|---|---|---|
| C preprocessor/macros | `reject` | Hidden behavior, source rewriting, and non-local meaning. |
| Header files/textual include | `reject` | Replaced by `importModule` and dependency contract tapes. |
| C expression deref/address syntax | `reject` | Use named pointer operations with effects and trust metadata. |
| C unions/bitfields | `post-1.0` | Only needed for deeper ABI interop, not enterprise app logic. |
| C function pointers/callbacks | `post-1.0` | Needs lifetime/callable contract story. |
| JS dynamic objects | `reject` | Hidden shape mutation violates recoverable context. |
| JS object literals | `reject` | Use record builders. |
| JS dynamic arrays | `reject` | Use typed lists/maps with operation contracts. |
| JS exceptions | `reject` | Use `Result` and explicit branchable failures. |
| JS classes/prototypes/`this` | `reject` | Hidden receiver state conflicts with local intent. |
| JS destructuring/spread/rest | `reject` | Hides field access, allocation, and iteration. |
| JS promises/event loop model | `reject` as a model | Use structured async, not JS promise semantics. |
| Rust lifetimes syntax | `post-1.0` | Useful safety idea, but dense syntax conflicts with AgentScript style. |
| Rust traits | `post-1.0` | Could become operation contract groups later. |
| Rust macros | `reject` | Same problem as C/JS macros. |
| Rust implicit `Drop`/RAII | `reject` | Cleanup must be explicit and adjacent to acquisition. |
| Cargo-like package manager | `post-1.0` | Useful tooling, not language core. |

## Final Enterprise 1.0 Checklist

AgentScript is not enterprise-ready at 1.0 unless nontrivial web/service samples
can answer all of these from source alone:

- What operation handles each route or job?
- What records define request, response, event, and database shapes?
- What fields are optional, validated, secret, tenant-scoped, or PII?
- What JSON codecs accept or reject unknown fields?
- What dependencies are called, and what effects do they declare?
- What failures can each dependency return?
- Where does each failure branch, wrap, retry, log, or return?
- What timeout and cancellation token bounds each async call?
- What cleanup runs after every acquired resource or transaction?
- What logs, metrics, traces, and audit events are emitted?
- What memory allocation policy applies to records, collections, and buffers?
- What trust boundary converts raw input into validated domain values?
- Does every line perform one semantic action?

## Bottom Line

The truly missing enterprise blockers are not classes, macros, inheritance,
closures, or Rust-level lifetime syntax.

The real 1.0 blockers are:

- typed list and map contracts;
- typed JSON codecs;
- HTTP handler/runtime contracts;
- resource/database/transaction contracts;
- minimal structured async with timeout and cancellation;
- explicit cleanup/defer semantics;
- config, secrets, validation, and security metadata;
- observability as declared effects;
- effect/failure/memory/trust checks that tooling can enforce.

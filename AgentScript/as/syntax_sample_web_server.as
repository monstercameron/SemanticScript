# syntax_sample_web_server.as
#
# This file exists to demonstrate the AgentScript syntax surface beyond
# the V0 console subset. It exercises records, fields, enums, codecs,
# validators, retry policies, type metadata, capabilities, structured
# concurrency (taskGroup), defer cleanup, and the webServer / route
# verbs.
#
# The current ascc compiler accepts and parses every line here (parse
# clean: `python compiler/ascc.py as/syntax_sample_web_server.as
# --parse-only --lint`). Codegen does not yet lower webServer, route,
# taskGroup, codec, or defer to runnable LLVM IR — those verbs are
# reserved at the AST level and live in the indexable AST for tooling.

project AccountServer
target webServer
runtime AgentRuntime 0.1

importModule standard.http as http
importModule standard.json as json
importModule standard.time as time
importModule database.postgres as postgres

dependency standard.http version 0.1 source standard
dependency standard.json version 0.1 source standard
dependency standard.time version 0.1 source standard
dependency database.postgres version 0.3 source registry integrity "sha256:abc123"
dependencyEffect database.postgres network.tcp
dependencyEffect database.postgres readWrite database
dependencyExports database.postgres DatabaseClient DatabaseConnection DatabaseTransaction AccountLookupError
dependencyFunction database.postgres database.openConnection
dependencyFunctionInput database.openConnection database DatabaseClient
dependencyFunctionOutput database.openConnection Result DatabaseConnection DatabaseOpenError
dependencyFunctionEffect database.openConnection network.tcp.connect
dependencyFunctionAsync database.openConnection yes

module account

# ----- type universe -----

type AccountId UuidV7
type MoneyCents I64
type AccountBalanceResult Result AccountBalance AccountLookupError

typeInvariant AccountId "value is a v7 UUID encoded as a 128-bit big-endian integer"
typeRepresentation AccountId UuidV7
typeMemory AccountId inline
typeTrust AccountId trusted

typeInvariant MoneyCents "value fits in I64 and is non-negative for stored balances"
typeMemory MoneyCents inline

# ----- records -----

record AccountBalance layout row align 16
purpose AccountBalance "Internal account-balance snapshot read from the database, including the last update timestamp"
field AccountBalance accountId AccountId
field AccountBalance availableCents MoneyCents
field AccountBalance pendingCents MoneyCents
field AccountBalance updatedAtUtc UtcMilliseconds

record AccountBalanceResponse layout row align 16
purpose AccountBalanceResponse "Public account-balance shape returned by the HTTP API; drops internal timestamp metadata before serialization"
field AccountBalanceResponse accountId AccountId
field AccountBalanceResponse availableCents MoneyCents
field AccountBalanceResponse pendingCents MoneyCents

# ----- enums -----

enum AccountStatus repr I32
enumCase AccountStatus Active 0
enumCase AccountStatus Frozen 1
enumCase AccountStatus Closed 2

# ----- errors -----

error MainError
errorCase MainError AccountIdParseFailed AccountIdParseError
errorCase MainError DatabaseOpenFailed DatabaseOpenError
errorCase MainError AccountBalanceLookupFailed AccountLookupError
errorCase MainError JsonEncodingFailed JsonEncodingError

# ----- codec -----

jsonCodec AccountBalanceResponseJsonCodec strict yes unknownFields reject
schema AccountBalanceResponseJsonCodec AccountBalanceResponse
purpose AccountBalanceResponseJsonCodec "Serialize an AccountBalanceResponse record into a strict JSON envelope safe to ship in an HTTP response body"
guarantee AccountBalanceResponseJsonCodec "Only fields declared on AccountBalanceResponse are serialized"

# ----- validator -----

validator accountIdPathValidator
input accountIdPathValidator http.PathParameter
output accountIdPathValidator Result AccountId AccountIdParseError
purpose accountIdPathValidator "Parse an HTTP path parameter into a typed AccountId or surface a typed AccountIdParseError"
guarantee accountIdPathValidator "AccountId is a syntactically valid v7 UUID"

# ----- retry policy -----

const databaseRetryInitialDelay DurationMilliseconds 50
const databaseRetryMaximumDelay DurationMilliseconds 500

retryPolicy databaseReadRetryPolicy maxAttempts 3 initialDelay databaseRetryInitialDelay maximumDelay databaseRetryMaximumDelay jitter yes
purpose databaseReadRetryPolicy "Bound transient database-read retries to at most three attempts with exponential backoff and jitter"

timeoutBudget accountLookupTimeoutBudget DurationMilliseconds 2000
purpose accountLookupTimeoutBudget "Cap the total time spent on a single account balance lookup so a slow query cannot pin a request handler"

# ----- capabilities (explicit authority grants) -----

capability stdoutWrite console.stdout write
purpose stdoutWrite "Authority to write a stream of lines to the process's standard output device"

capability databaseReadWrite database readWrite
purpose databaseReadWrite "Authority to read from and write to the application's database tier"

capability clockRead clock.utc read
purpose clockRead "Authority to read the UTC wall clock for timestamp generation"

# ----- web server -----

webServer accountHttpServer
purpose accountHttpServer "Host the AccountServer HTTP interface; bind to all interfaces on port 8080 and route account balance reads to getAccountBalanceHandler"
serverHost accountHttpServer "0.0.0.0"
serverPort accountHttpServer 8080
route accountHttpServer get "/accounts/:accountId/balance" getAccountBalanceHandler

# ----- handler operation -----

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

useCapability getAccountBalanceHandler databaseReadWrite
useCapability getAccountBalanceHandler clockRead

purpose getAccountBalanceHandler "Return the current account balance as a JSON HTTP response"
invariant getAccountBalanceHandler "Every database await must use requestCancellationToken"
guarantee getAccountBalanceHandler "Response body never includes raw database driver error details"
warning getAccountBalanceHandler "Never expose raw database errors in the HTTP response body"
timing getAccountBalanceHandler "Total handler latency budget is accountLookupTimeoutBudget"
observability getAccountBalanceHandler "Emit account.balance.lookup.latency histogram and account.balance.lookup.errors counter"
security getAccountBalanceHandler "accountId is parsed through accountIdPathValidator before any database call"

label startGetAccountBalanceHandler

# rationale: Read the cancellation token first so every later async call can be tied to client disconnects.
call requestCancellationTokenReadCall http.requestCancellationToken
arg requestCancellationTokenReadCall request httpRequest
run requestCancellationTokenReadCall
bind requestCancellationToken CancellationToken requestCancellationTokenReadCall

# rationale: Parse the accountId path parameter through the dedicated validator.
call accountIdParseCall accountIdPathValidator.validate
arg accountIdParseCall request httpRequest
arg accountIdParseCall name "accountId"
run accountIdParseCall
bindOk accountId AccountId accountIdParseCall
bindError accountIdParseError AccountIdParseError accountIdParseCall
branchIfError accountIdParseCall accountIdParseFailed

# rationale: Open the database connection with a bounded timeout.
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

# rationale: Balance lookup uses the request cancellation token and the configured timeout budget.
call accountBalanceLookupCall database.accounts.findBalance
arg accountBalanceLookupCall connection databaseConnection
arg accountBalanceLookupCall accountId accountId
timeout accountBalanceLookupCall accountLookupTimeoutBudget
cancelOn accountBalanceLookupCall requestCancellationToken
useRetry accountBalanceLookupCall databaseReadRetryPolicy
start accountBalanceLookupCall
await accountBalanceLookupCall
bindOk accountBalance AccountBalance accountBalanceLookupCall
bindError accountBalanceLookupError AccountLookupError accountBalanceLookupCall
branchIfError accountBalanceLookupCall accountBalanceLookupFailed

# rationale: Build the response record explicitly so JSON encoding sees a stable schema.
new accountBalanceResponse AccountBalanceResponse
fieldSet accountBalanceResponse accountId accountId
fieldGet accountBalanceAvailableCents MoneyCents accountBalance availableCents
fieldGet accountBalancePendingCents MoneyCents accountBalance pendingCents
fieldSet accountBalanceResponse availableCents accountBalanceAvailableCents
fieldSet accountBalanceResponse pendingCents accountBalancePendingCents

# rationale: Encode the response record using the typed codec.
call jsonEncodingCall AccountBalanceResponseJsonCodec.encode
arg jsonEncodingCall value accountBalanceResponse
run jsonEncodingCall
bindOk responseBody JsonBytes jsonEncodingCall
bindError jsonEncodingError JsonEncodingError jsonEncodingCall
branchIfError jsonEncodingCall jsonEncodingFailed

# rationale: Build the success response envelope.
call successResponseBuildCall http.responseJson
arg successResponseBuildCall status HttpStatus.Ok
arg successResponseBuildCall body responseBody
run successResponseBuildCall
bind successResponse HttpResponse successResponseBuildCall
returnValue successResponse

label accountIdParseFailed
call accountIdParseFailureResponseBuildCall http.responseText
arg accountIdParseFailureResponseBuildCall status HttpStatus.BadRequest
arg accountIdParseFailureResponseBuildCall body "invalid account id"
run accountIdParseFailureResponseBuildCall
bind accountIdParseFailureResponse HttpResponse accountIdParseFailureResponseBuildCall
returnValue accountIdParseFailureResponse

label databaseOpenFailed
call databaseOpenFailureResponseBuildCall http.responseText
arg databaseOpenFailureResponseBuildCall status HttpStatus.ServiceUnavailable
arg databaseOpenFailureResponseBuildCall body "database unavailable"
run databaseOpenFailureResponseBuildCall
bind databaseOpenFailureResponse HttpResponse databaseOpenFailureResponseBuildCall
returnValue databaseOpenFailureResponse

label accountBalanceLookupFailed
call accountBalanceLookupFailureResponseBuildCall http.responseText
arg accountBalanceLookupFailureResponseBuildCall status HttpStatus.InternalServerError
arg accountBalanceLookupFailureResponseBuildCall body "account balance lookup failed"
run accountBalanceLookupFailureResponseBuildCall
bind accountBalanceLookupFailureResponse HttpResponse accountBalanceLookupFailureResponseBuildCall
returnValue accountBalanceLookupFailureResponse

label jsonEncodingFailed
call jsonEncodingFailureResponseBuildCall http.responseText
arg jsonEncodingFailureResponseBuildCall status HttpStatus.InternalServerError
arg jsonEncodingFailureResponseBuildCall body "response encoding failed"
run jsonEncodingFailureResponseBuildCall
bind jsonEncodingFailureResponse HttpResponse jsonEncodingFailureResponseBuildCall
returnValue jsonEncodingFailureResponse

# ===== a second handler demonstrating structured concurrency =====

operation getAccountPageHandler
input getAccountPageHandler httpRequest HttpRequest
input getAccountPageHandler databaseClient DatabaseClient
input getAccountPageHandler clock Clock
output getAccountPageHandler HttpResponse
effect getAccountPageHandler write http.response
effect getAccountPageHandler read database.accounts
memory getAccountPageHandler heap no
memory getAccountPageHandler arena request 1MiB
async getAccountPageHandler yes

purpose getAccountPageHandler "Load all per-account widgets in parallel under a single structured task group"
invariant getAccountPageHandler "All tasks complete or cancel before the response is built"

label startGetAccountPageHandler

# rationale: Read request cancellation up front so the task group can be wired into client disconnects.
call requestCancellationTokenReadCall http.requestCancellationToken
arg requestCancellationTokenReadCall request httpRequest
run requestCancellationTokenReadCall
bind requestCancellationToken CancellationToken requestCancellationTokenReadCall

# rationale: Bounded task group; first error cancels the rest.
taskGroup accountPageLoadTasks maxTasks 4 cancelOnFirstError yes

startInGroup customerLookupCall accountPageLoadTasks
startInGroup recentTransactionsLookupCall accountPageLoadTasks
startInGroup accountLimitsLookupCall accountPageLoadTasks

awaitGroup accountPageLoadTasks
bindGroupError accountPageLoadGroupError AccountPageLoadError accountPageLoadTasks
branchIfGroupError accountPageLoadTasks accountPageLoadFailed

# rationale: All three lookups succeeded; build the page response.
call accountPageResponseBuildCall http.responseJson
arg accountPageResponseBuildCall status HttpStatus.Ok
arg accountPageResponseBuildCall body "{}"
run accountPageResponseBuildCall
bind accountPageResponse HttpResponse accountPageResponseBuildCall
returnValue accountPageResponse

label accountPageLoadFailed
call accountPageLoadFailureResponseBuildCall http.responseText
arg accountPageLoadFailureResponseBuildCall status HttpStatus.InternalServerError
arg accountPageLoadFailureResponseBuildCall body "page load failed"
run accountPageLoadFailureResponseBuildCall
bind accountPageLoadFailureResponse HttpResponse accountPageLoadFailureResponseBuildCall
returnValue accountPageLoadFailureResponse

# ----- tests cross-link the operation by name -----

testCovers getAccountBalanceHandlerHappyPathTest getAccountBalanceHandler
testCovers getAccountBalanceHandlerInvalidIdTest getAccountBalanceHandler
testCovers getAccountBalanceHandlerDatabaseTimeoutTest getAccountBalanceHandler
testCovers getAccountPageHandlerAllSucceedTest getAccountPageHandler
testCovers getAccountPageHandlerFirstFailureCancelsRestTest getAccountPageHandler

# JSON CRUD API

`standard.json` is the public contract module for JSON values. Import it with:

```semanticscript
importModule json standard.json
```

The current executable implementation includes the legacy builder and flat
finder calls, the `standard.json` type/error/enum contracts, JsonText-backed
`jsonBody` literals, and primitive `json.stringify` / `json.parse` aliases
that rewrite to the legacy primitive encode/decode lowering. Full document
CRUD lowering, Result-shaped stringify/parse errors, and record-typed
`jsonBody`/codec generation remain pending unless `SYNTAX.md` marks a specific
row `Impl'd`.

## Types

`JsonDocument` is an opaque mutable document handle. It is created by
`json.createDocument` from existing `JsonText` or by `json.createEmptyDocument`
from a root `JsonValueKind`, then released with `defer json.destroyDocument`.
Every document has a `capacityBytes` bound. Mutations that would grow past that
bound must fail with `JsonAccessError.CapacityExceeded` and leave the document
unchanged.

`JsonCursor` is a signed node index inside one `JsonDocument`. Cursor `0` is
the root. Cursors are stable across non-structural value replacements, but
structural edits invalidate affected descendant cursors:

- `removeObjectField`
- `removeArrayElementAt`
- `clearObject`
- `clearArray`
- `setObjectFieldObject`
- `setObjectFieldArray`
- `insertArrayElement*`
- `replaceArrayElement*` when the replacement is a container

`JsonPath` is a null-terminated string containing zero or more path steps.
Object steps are `.fieldName`; array steps are `[index]`. Any other segment
shape fails with `JsonAccessError.MalformedPath`.

`JsonValueKind` is a `CSignedInt32` enum:

| Case | Value |
| --- | ---: |
| `objectJsonValueKind` | 0 |
| `arrayJsonValueKind` | 1 |
| `stringJsonValueKind` | 2 |
| `integerJsonValueKind` | 3 |
| `doubleJsonValueKind` | 4 |
| `booleanJsonValueKind` | 5 |
| `nullJsonValueKind` | 6 |

## Error Domains

`JsonAccessError` is used by document navigation, cursor readers that can fail,
serialization, and mutators:

```semanticscript
error JsonAccessError
errorCase JsonAccessError PathNotFound CSignedInt32
errorCase JsonAccessError WrongType CSignedInt32
errorCase JsonAccessError IndexOutOfRange CSignedInt32
errorCase JsonAccessError FieldNameTooLong CSignedInt32
errorCase JsonAccessError DocumentNotMutable CSignedInt32
errorCase JsonAccessError CapacityExceeded CSignedInt32
errorCase JsonAccessError MalformedPath CSignedInt32
errorCase JsonAccessError ScratchTooSmall CSignedInt32
```

`JsonEncodeError` is reserved for `json.stringify.<TypeName>`:
`CapacityExceeded`, `WrongType`, and `OutputBufferTooSmall`.

`JsonDecodeError` is reserved for `json.parse.<TypeName>` and `jsonBody`
record validation: `UnexpectedToken`, `MissingRequired`, `WrongType`,
`Oversize`, `Truncated`, and `EscapeMalformed`.

## Lifecycle

Document lifecycle calls use ordinary call rows:

```semanticscript
call createDocCall json.createDocument
argument createDocCall jsonText JsonText requestBody
argument createDocCall capacityBytes JsonCapacityBytes maxJsonBytes
run createDocCall
bind ok document JsonDocument createDocCall
bind error accessError JsonAccessError createDocCall
branch error source createDocCall target badJson
defer releaseDoc json.destroyDocument document
```

`json.createEmptyDocument` creates either an object or array root from
`objectJsonValueKind` or `arrayJsonValueKind`. `json.serializeDocument` writes
serialized JSON into caller-owned scratch and returns `Result JsonText
JsonAccessError`. `json.documentLength` returns the byte count that the next
serialize will emit, and `json.documentRoot` returns cursor `0`.

## Navigation And Readers

Navigation returns cursors through `Result JsonCursor JsonAccessError`:

- `json.objectFieldAt`
- `json.arrayElementAt`
- `json.cursorParent`
- `json.cursorAtPath`

Cursor readers expose the current node:

- `json.cursorKind` returns `JsonValueKind`.
- `json.cursorIsNull` returns `Bool`.
- `json.cursorInt64`, `json.cursorDouble`, and `json.cursorBool` return the
  supplied `missingDefault` when the cursor is missing or not the requested
  scalar kind.
- `json.cursorString` copies the unescaped string into caller-owned scratch and
  can fail with `WrongType` or `ScratchTooSmall`.
- `json.cursorArrayLength` and `json.cursorObjectFieldCount` return counts for
  matching containers.
- `json.cursorObjectFieldNameAt` copies a field name into caller-owned scratch.
- `json.cursorObjectFieldValueAt` returns the value cursor for a field index.

## Mutators

Object mutators set or replace one field:

- `json.setObjectFieldString`
- `json.setObjectFieldInt64`
- `json.setObjectFieldDouble`
- `json.setObjectFieldBool`
- `json.setObjectFieldNull`
- `json.setObjectFieldObject`
- `json.setObjectFieldArray`
- `json.setObjectFieldJsonText`

Array mutators append, insert, or replace one element for the same scalar,
container, and raw-JSON variants:

- `json.appendArrayElement*`
- `json.insertArrayElement*`
- `json.replaceArrayElement*`

Delete and clear calls are:

- `json.removeObjectField`
- `json.removeArrayElementAt`
- `json.clearObject`
- `json.clearArray`

Mutators return a status compatible with `ignore ok`, `bind error`, and
`branch error`. Structural mutators must follow the cursor invalidation
contract above.

## jsonBody

`jsonBody NAME` is the JSON counterpart to `html body template`: a column-0 row
followed by an indented JSON island. It binds to a matching storage row with no
inline value:

```semanticscript
storage module immutable healthBody JsonText
jsonBody healthBody
  {"ok":true}
```

Compiler support validates JsonText islands with Python's JSON parser, rejects
non-standard constants, canonicalizes the value as compact JSON, and binds it
as a null-terminated constant. Record-typed targets are type-checked at compile
time: required fields must be present, unknown fields are rejected, field JSON
name overrides are honored, nested records recurse through the same checks, and
`recordFieldJsonOmitWhen` supplies the configured omitted-field defaults. The
current emitted representation is the compiler's flattened record-slot model.

## Stringify And Parse

`json.stringify.<TypeName>` and `json.parse.<TypeName>` are the high-level
typed entry points. They are intended to wrap the native document/builder
surface instead of requiring handlers to assemble JSON with `c.snprintf`.

Primitive stringify/parse aliases use compiler glue only to allocate scratch
and call native JSON helpers. `json.stringify.String` and
`json.stringify.CNullTerminatedByteString` escape through native_json and fail
with `JsonEncodeError.OutputBufferTooSmall` when the bounded scratch cannot
hold the quoted value. Primitive `json.parse` targets reject malformed input
and trailing junk with `JsonDecodeError.UnexpectedToken`; they no longer mark
success unconditionally after libc default parsing. `JsonText` stringify copies
through bounded scratch and `JsonText` parse validates syntax through the
native document parser. Record stringify/parse walks record metadata and the
native document runtime field by field, honoring `recordFieldJsonName`,
`recordFieldJsonOmitWhen`, required fields, nested records, and wrong-type
errors while exposing `JsonEncodeError` / `JsonDecodeError` at the call site.

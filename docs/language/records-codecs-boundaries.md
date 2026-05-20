# Records, Codecs, and Boundaries

Records, codecs, validators, and trust boundaries describe data shape and
cross-boundary guarantees. Some forms already lower to LLVM field operations;
many refined forms are metadata that linters and editor hovers can inspect.

## Records

```semanticscript
record Task
recordLayout Task packed
recordAlign Task 8
field Task taskId TaskId
field Task title ValidatedText
field Task completed Bool
```

Schemas:

```text
record NAME
field RECORD FIELD TYPE
recordLayout RECORD KIND
recordAlign RECORD N
```

`field` currently requires the record to have been declared first.
`recordAlign` should be a power of two; `semlint.py` checks that rule.

## Field Operations

```semanticscript
new taskValue Task
fieldSet taskValue title validatedTaskTitle
fieldSet taskValue completed false
fieldGet taskTitle ValidatedText taskValue title
```

Schemas:

```text
new VALUE RECORD
fieldSet RECORD_VALUE FIELD VALUE
fieldGet OUT TYPE RECORD_VALUE FIELD
```

Current lowering supports record paths used by feature tests. For
record-typed params, field reads can alias flattened parameter SSA values.

## Builders

Builders keep large record construction explicit and named.

```semanticscript
recordBuilder taskBuilder Task
recordSet taskBuilder title validatedTaskTitle
recordSet taskBuilder completed false
recordBuild buildTaskCall taskBuilder
recordBuildFailure buildTaskCall TaskError.InvalidTitle
```

Schemas:

```text
recordBuilder BUILDER RECORD
recordSet BUILDER FIELD VALUE
recordBuild CALL BUILDER
recordBuildFailure CALL ERROR.VARIANT
```

`recordBuild` registers a synthetic call so downstream binding and failure
patterns stay consistent with normal call flow.

## JSON Codecs

```semanticscript
jsonCodec taskJsonCodec
jsonCodecStrict taskJsonCodec yes
jsonCodecUnknownFields taskJsonCodec reject
jsonCodecInput taskJsonCodec RawJson
jsonCodecOutput taskJsonCodec Task
jsonCodecDecodeTarget taskJsonCodec json.parse.Task
jsonCodecEncodeTarget taskJsonCodec json.stringify.Task
jsonCodecRequiredField taskJsonCodec title
jsonCodecDecodeFailure taskJsonCodec TaskDecodeError.MissingTitle
jsonCodecLimit taskJsonCodec maximumBytes 65536
```

JSON codec declarations are parsed and indexed. Primitive generated targets such
as `json.stringify.Bool`, `json.parse.Bool`, and selected scalar codec targets
have direct compiler support. Record-level generated codecs use the
`json.stringify.<RecordType>` / `json.parse.<RecordType>` surface and the
native JSON document runtime when the record metadata is present.

`semlint.py` checks incomplete JSON codecs. It also flags record-level
legacy targets such as `json.decode.Task` or `json.encode.Task` as deprecated
runtime gaps. Use the high-level stringify/parse spellings for executable
record codecs.

## Generic Codecs

```semanticscript
codec taskBinaryCodec binary
schema taskBinaryCodec Task
unknownFields taskBinaryCodec reject
```

Generic codecs are contract metadata. Use them when a runtime-specific codec
backend is not part of the source yet. Calls such as `taskBinaryCodec.encode`
or `taskBinaryCodec.decode` do not become executable from the `codec` line
alone; provide a named operation/runtime binding or keep the codec as metadata.

## Typed Collection Runtime Status

Collection declarations and `collectionOperation` rows describe list, map,
slice, array, and small-list contracts. They do not yet allocate collection
storage or implement methods such as `TaskList.append`, `TaskMap.get`, or
`TaskList.length`.

Until the collection runtime is wired, use explicit operations for executable
behavior. `semlint.py` flags typed collection calls whose current compiler path
would fall through to the zero-stub external fallback.

## Validators, Mappers, Adapters, Boundaries

```semanticscript
validator taskTitleValidator
mapper taskRowToResponseMapper
adapter postgresTaskRowAdapter
boundary publicHttpBoundary
```

These declarations name transformation and validation concepts. Attach purpose,
input, output, failure, and trust metadata so they are not empty labels.

## Trust Boundaries

```semanticscript
trustBoundary ValidatedText
trustBoundaryKind ValidatedText rawUtf8ToValidatedText
trustBoundaryInput ValidatedText RawText
trustBoundaryOutput ValidatedText TrustedText
trustBoundaryValidator ValidatedText validateTaskTitle
trustBoundarySource ValidatedText httpRequest.body
```

Trust-boundary declarations should answer:

- What raw type enters?
- What trusted type leaves?
- Which validator proves the transition?
- Which source is permitted?

`semlint.py` checks partial trust boundaries. Treat that diagnostic as design
pressure: a partial boundary is usually worse than no boundary because it
implies safety without enough evidence.

# EAV-Steps — EBNF grammar (v0.3)

Normative reference for the `eavc` front end. The four row classes (§1) and the
lexical rules (§2) below are what `tokenize_line` and `parse` implement; the
`invalid_corpus/` fixtures (one per hard-error rule) are the negative tests
(`test_invalid_corpus_all_reject`).

## Lexical (§2)

```ebnf
file        = { line } ;
line        = [ row ] [ comment ] LF ;
comment     = "#" { any-char-except-LF } ;
row         = token { WS token } ;            (* WS-separated; leading WS = island *)
token       = string | bare ;
string      = '"' { char | escape } '"' ;
escape      = "\\" ( '"' | "\\" | "n" | "t" | "x" hex hex ) ;   (* \r \0 \u{} rejected *)
bare        = (* run of non-WS, non-'"', non-'#'; must not contain '=' *) ;

identifier  = letter { letter | digit } ;     (* camelCase; no _ - or leading digit *)
intLit      = decInt | "0x" hex {["_"] hex} | "0b" bin {["_"] bin} ;
decInt      = "0" | nonzero { ["_"] digit } ;          (* no octal / 0-prefix *)
negInt      = "-" decInt ;                              (* no space after '-' *)
floatLit    = digit{digit} "." digit{digit} ;          (* no leading/trailing dot *)
negFloat    = "-" floatLit ;
durationLit = intLit ("ns"|"us"|"ms"|"s"|"m"|"h") ;     (* reserved; unused in v0.3 *)
boolLit     = "true" | "false" ;
repoPath    = pseg { "/" pseg } ;                       (* manifest positions only *)
semver      = "v" num "." num "." num [ "-" pre ] [ "+" build ] ;
digest      = "sha256" WS hex{64} ;
```

## Row classes (§1)

```ebnf
entityRow   = name WS "is" WS kind ;
factRow     = name WS predicate { WS payload } ;
stepRow     = op   WS stepPred  { WS payload } ;
labelStep   = op   WS "at" WS label WS stepPred { WS payload } ;
```

* Column 1 = subject; column 2 = predicate (or `at`); column 3+ = payload.
* Every entity's first row is its `is` row (§17 #1).
* `kind` ∈ the §5 entity-kind set; a predicate must be in the kind's §5
  structural/step set or be a universal metadata predicate (§6).

## Hard-error rules (negative corpus)

Each `invalid_corpus/NN_*.sem` fixture violates exactly one rule and must be
rejected at parse time: missing/duplicate `is`, unknown kind, bad identifier,
reserved-word name, illegal predicate for kind, `at` on a non-operation,
duplicate field/variant, mixed enum `repr`, `Result` arity, octal/leading-dot/
space-after-`-` literals, `=` usage, duration literal in a value position.

See `README.md` §1, §2, §5, §10, §17 for the normative prose.

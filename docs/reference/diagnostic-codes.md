# Diagnostic Codes

Stable diagnostic-code URLs live in this file. The detailed machine payload is
still `sem explain CODE --json`; this page gives docs and release notes a stable
anchor to point at.

## ss3104

`SS3104` reports a declared effect that is not covered by a matching capability,
`useCapability`, or inline `authority` row. See `sem explain SS3104 --json` and
`sem reference SS3104 --json`.

## ss4001

`SS4001` reports a call binding without the `Call` role suffix. `sem fix --plan`
can emit local rename edits for the call and its attachment rows.

## ss3619

`SS3619` reports a `http.responseHeader` run after a response body/file/redirect
writer has already run in the same operation. Move the header run before the
body writer so staged headers are latched into the outgoing response.

## ss4002

`SS4002` reports a `bind error` value without the `Error` role suffix. `sem fix
--plan` can emit local rename edits for the binding and same-operation uses.

## ss4003

`SS4003` reports a constructed failure value without the `Failure` role suffix.
`sem fix --plan` can emit local rename edits for the failure value and
same-operation uses.

## Policy

Do not reuse a retired code for a different rule. If a rule is superseded, keep
the old code explainable for at least one release and point it at the
replacement.

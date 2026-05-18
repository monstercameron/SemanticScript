# expect.stdout: hello from external literal\n
# expect.exit: 0
# expect.xfail: feature_coverage.py runs through bootstrap_general.as which does not yet inline the bytes of a `literalSource` path into a `literal` const. Direct ascc.py compilation works correctly (`python compiler/ascc.py THIS_FILE --emit-exe /tmp/x.exe && /tmp/x.exe` prints the contents of _modules/external_greeting_literal.txt). Closing means teaching bootstrap_general to read literalSource paths at compile time and embed the bytes as the literal's const value.
project LiteralSourceLoader
target console
runtime AgentRuntime 0.1
entry console main
error MainError
errorCase MainError ConsoleWriteFailed ConsoleWriteError
literal externalGreetingLiteral CNullTerminatedByteString
literalSource externalGreetingLiteral "_modules/external_greeting_literal.txt"
literalBytes externalGreetingLiteral 27
literalTrust externalGreetingLiteral trustedStaticAsset
operation main
input main console Console
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "literal + literalSource: bytes loaded from disk at compile time replace the stub const value."
invariant main "Output is the file's literal content, not the empty stub."
label startMain
call writeExternalCall console.writeLine
arg writeExternalCall console console
arg writeExternalCall text externalGreetingLiteral
run writeExternalCall
ignoreOk writeExternalCall Void
const successfulExitCode ExitCode 0
returnOk successfulExitCode

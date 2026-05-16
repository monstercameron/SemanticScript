# input4.as -- consumed by bootstrap4.exe.
#
# bootstrap4 is the third self-hosted compiler. It reads this file,
# finds the first greeting-string declaration and the first integer
# exit-code declaration, then emits LLVM IR for a program that prints
# the greeting with puts and returns the exit code from main.
#
# Supported subset (bootstrap4):
#   - everything bootstrap3 supports
#   - one greeting string constant (the first declaration of byte-string
#     type in the source body)
#   - one call to write that greeting to stdout
#
# Header comments do not contain the same lexical marker the parser
# scans for, so the FIRST real declaration in the body is unambiguous.

project Tiny4
target console
runtime AgentRuntime 0.1
entry console main

operation main
output main Result ExitCode MainError
effect main write console.stdout
memory main heap no
async main no
purpose main "Print one greeting line and exit with the literal exit code below."

label startMain

const greetingText CNullTerminatedByteString "Hello from a self-hosted AgentScript stage 4 compiler!"

call greetCall console.writeLine
arg greetCall text greetingText
run greetCall

const exitCodeValue ExitCode 7
returnOk exitCodeValue

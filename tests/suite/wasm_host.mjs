// A small WebAssembly host for programs built with `refined build --kind wasm`.
//
//   node tests/suite/wasm_host.mjs PROGRAM.wasm ENTRY
//
// It supplies the module's imports from `env`: linear memory, the stack pointer, and the runtime
// functions a computing program uses (writing lines and numbers, traps, the call stack, and regions
// with a bump allocator). It calls ENTRY (for example `sum.main`), prints what the program writes, and
// exits with the program's exit code; a trap exits with 70, as the native runtime does.
import fs from "fs";

const [file, entry] = process.argv.slice(2);
const bytes = fs.readFileSync(file);
const module = await WebAssembly.compile(bytes);
const memory = new WebAssembly.Memory({ initial: 64 });
const stackPointer = new WebAssembly.Global({ value: "i32", mutable: true }, 64 * 65536 - 16);
const text = (ptr, len) => Buffer.from(memory.buffer, Number(ptr), Number(len)).toString("utf8");
let heap = 1 << 20; // regions: a bump allocator above the program's data
const frames = [];
const out = [];
const flush = () => { if (out.length) { process.stdout.write(out.join("")); out.length = 0; } };

const env = {
  __linear_memory: memory,
  __stack_pointer: stackPointer,
  refined_write: (fd, ptr, len, newline) => { (fd === 2 ? process.stderr : { write: (s) => out.push(s) }).write(text(ptr, len) + (newline ? "\n" : "")); return 0; },
  refined_write_int: (fd, value, newline) => { out.push(`${value}${newline ? "\n" : ""}`); return 0; },
  refined_trap: (ptr, len) => {
    flush();
    process.stderr.write(`trap: ${text(ptr, len)}\n` + frames.slice().reverse().map((f) => `  in ${f}\n`).join(""));
    process.exit(70);
  },
  refined_frame_push: (ptr, len) => { frames.push(text(ptr, len)); },
  refined_frame_pop: () => { frames.pop(); },
  refined_region_new: (capacity) => { const at = heap; heap += Number(capacity) + 16; return at; },
  refined_region_alloc: (region, size) => { const at = heap; heap += (Number(size) + 7) & ~7; return at; },
  refined_region_free: () => {},
  // compiler-rt's 128-bit multiply, which LLVM calls for overflow-checked 64-bit multiplication on wasm32
  __multi3: (ret, aLo, aHi, bLo, bHi) => {
    const mask = (1n << 64n) - 1n;
    const a = ((BigInt.asUintN(64, aHi) << 64n) | BigInt.asUintN(64, aLo));
    const b = ((BigInt.asUintN(64, bHi) << 64n) | BigInt.asUintN(64, bLo));
    const p = (a * b) & ((1n << 128n) - 1n);
    const view = new DataView(memory.buffer);
    view.setBigUint64(ret, p & mask, true);
    view.setBigUint64(ret + 8, p >> 64n, true);
  },
  refined_recursion_enter: () => 0,
  refined_recursion_leave: () => {},
};
const imports = { env: {} };
for (const imp of WebAssembly.Module.imports(module)) {
  if (!(imp.name in env)) {
    console.error(`this host does not provide \`${imp.name}\`; the program needs the native runtime`);
    process.exit(2);
  }
  imports.env[imp.name] = env[imp.name];
}
const instance = await WebAssembly.instantiate(module, imports);
const code = instance.exports[entry]();
flush();
process.exit(Number(code));

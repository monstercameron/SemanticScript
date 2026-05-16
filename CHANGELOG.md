# Changelog

## 2026-05-16

- `a3c90973c1b1d20f040fa05a1138d10a26db59a4` - `chore: add repository ignore rules`
  - Added repository ignores for generated Python bytecode, native build outputs, VSIX packages, and OS metadata.
- `5b95e35c8a45d46afc2a03f192288021c4385feb` - `docs: define AgentScript language and AST`
  - Added the root AgentScript specification, AST reference, and implementation README.
- `b9bcbee5c2d5c21e06b6e4856eaad69d365e3a82` - `compiler: add LLVM compiler and validation tooling`
  - Added the LLVM compiler, libc registry, linter, tests, benchmark sources, bootstrap chain, and reference IR artifacts.
- `d102a8634d3bd372569e2c61ee8b3b1437ccc002` - `examples: add AgentScript programs and language oracles`
  - Added AgentScript sample programs plus JavaScript and Python comparison/oracle programs.
- `8a787f55cefd451ab329242941c0997a57d2147d` - `tooling: add VS Code AgentScript extension`
  - Added the VS Code extension source for AgentScript syntax highlighting and language configuration.
- `2096ab398caac802a8becb9b0eeaa05a4120ffab` - `tooling: polish compiler and linter CLIs`
  - Added version reporting, clearer success and failure messages, quiet mode, and stable CLI exit codes for the compiler and linter.
- `698719dcf3f16a27cd790f50052854d707500ef2` - `bootstrap: add input-scaled AS compiler stages`
  - Added bootstrap stage 6, the general AS-written compiler, stage 6 input and reference IR, and extended the bootstrap-chain runner and docs.
- `51e5d6e0db4db48c029a9ac4b30dae65d17de3d8` - `tests: add AS compiler parity coverage`
  - Added compiler unit tests, AS-written compiler parity checks, and ignored generated parity build outputs.
- `de281cd6274ddce624e7267ac241bd87d6f5539f` - `docs: document AgentScript 1.0 toolchain`
  - Refreshed the implementation README and added AgentScript-specific release notes for the 1.0 toolchain.

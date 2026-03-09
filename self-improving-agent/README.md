# Self-Improving Agent Scaffold

A minimal, composable, self-improving agent framework built on the Anthropic SDK.

## Setup
```bash
pip install anthropic
export ANTHROPIC_API_KEY=sk-ant-...
```

## Run a task
```bash
python run.py --task "List all Python files in this project and summarize what each one does"
```

## Run self-improvement cycle
```bash
python run.py --self-improve --next-version v0.2.0
```

This will cause the agent to:
1. Read its own source files
2. Critique its architecture
3. Propose improvements
4. Write the improved version to `./agents/v0_2_0/`

## Philosophy
- Minimalism + composability over magic
- Every abstraction should be debuggable
- Safety guardrails are explicit and whitelisted
```

---

## CHANGELOG — v0.1.0
```
## [0.1.0] — 2026-03-06

### Added
- ReAct loop with XML tool calling (Thought → Action → Observation → Answer)
- 4 core tools: read_file, write_file, list_dir, self_critique
- Path-restricted file I/O (safety whitelist via config.ALLOWED_*_ROOT)
- Self-improvement entry point (self_improve() reads own source → proposes vNEXT → writes to disk)
- Verbose colored step-by-step logging
- CLI entrypoint (run.py) with --task and --self-improve flags
- Clean module separation: config / prompts / tools / agent

### Known Limitations (targets for v0.2.0)
- Context strategy is naive (all messages kept — will hit limits on long runs)
- No persistent memory between separate run.py invocations
- self_critique tool returns a template rather than AI-filled content
- No structured output validation on tool parameters
- No retry/backoff on API errors
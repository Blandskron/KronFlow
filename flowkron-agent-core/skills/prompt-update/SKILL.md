# prompt-update

Use this skill when updating prompts, runtime instructions or agent behavior in `flowkron-agent-core`.

Steps:

1. Read `AGENTS.md`, `docs/agent/SECURITY.md` and `docs/agent/DISCOVERY.md`.
2. Identify the contract affected by the prompt.
3. Keep tenant isolation and safe fallback behavior.
4. Add or update tests for low-context, low-confidence and source-backed responses.
5. Update `docs/agent/DATA_SCHEMA.md` or `README.md` if the prompt changes persisted traces or response fields.

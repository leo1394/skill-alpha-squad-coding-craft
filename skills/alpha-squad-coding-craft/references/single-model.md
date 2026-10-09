# Single-model role workflow

Use when native subagents or verifiable model/reasoning controls are missing,
including web AI chats and other limited hosts. ChatGPT, Grok, DeepSeek and
Gemini are examples, not an allowlist or claims of verified integrations.
Select this mode by actual conversation capabilities, not provider or brand.
This is a workflow adaptation, not an emulator that creates agents or switches models.

## Entry and execution

Start each task with a concise disclosure in the conversation's language:
"Squad mode: single-model sequential roles; current session unchanged;
subagent/model controls unavailable." State the specific missing capability.
Include an exact model or effort only if the host verifies it. Do not present
unverified model-assignment lines or a model-selection popup. Proceed with the
requested task; no separate fallback approval is needed unless the user's task
explicitly requires genuine agents, independent review, or a new permission.

Use the same conversation for the necessary passes:

1. Orchestrator: define objective, constraints and acceptance checks.
2. Explorer/researcher: gather only the evidence needed for the task.
3. Worker: implement or produce the requested deliverable.
4. Tester: run available checks; distinguish executed tests from suggested tests.
5. Reviewer: re-examine the deliverable against the acceptance checks, challenge
   assumptions and identify risks. Label this self-review, not independent review.
6. Orchestrator: resolve findings and deliver the result with remaining limits.

Skip unnecessary passes for simple tasks. Role headings may show a brief result
or handoff when useful; do not print pretend conversations or internal reasoning.
One model shares one context, so role changes provide neither context isolation
nor independent opinions. Do not claim parallelism or guaranteed token savings.

Unavailable browsing, filesystem access, execution or external tools remain
unavailable. Request the minimum missing source material or describe unverified
steps; never claim files were edited or tests passed without execution evidence.
Do not run local Codex bootstrap or read local Codex metadata from a web host.

## Optional Laya and evidence

Laya is not required. If an accessible native `laya_tell_me` tool is present,
bounded `questions` may inform complexity/risk assessment. Do not invoke role
model routing, construct an invented catalog, or mutate advisor preferences
to enable this mode. Local MCP installation does not prove web accessibility.

With separately established recording consent, a returned decision ID and a
compatible `laya_feedback`, retain the genuine decision and verification
evidence. Follow its live schema and the feedback reference. Identify the
actual producer as the orchestrator and state "single-model self-review" in
review summaries; do not manufacture child assignments, dispatch receipts,
agent IDs, effective model observations or role-specific usage. Missing Laya
or failed feedback does not block the requested task.

## Completion

Use the skill's completion-statistics line. For a task that stayed entirely in
this mode, report zero created subagents; role passes are not agents. If a task
already created real children, retain their ledger and usage rather than reset
it on fallback. Use only authoritative task-scoped usage and timestamps. If the
host exposes neither, report each metric unavailable with its reason; never
estimate tokens by role count, text length or assumed model settings.

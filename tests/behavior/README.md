# Behavioral checks

These synthetic inputs are maintainer evaluation data, not installed skills.
Package tests validate structure, not model judgment.

Combined case JSON containing a request and acceptance criteria is evaluator-only.
Supply just the request and the complete work-to-skill package to a fresh model
context. Keep acceptance criteria with the evaluator, not the author. Record
model, host, skill digest, allowed tools, input, output, and verdict. For text-only
runs, collect file contents and state that installation/tool execution did not occur.

Evaluate authoring (A), then run generated skills (B) on new inputs in fresh contexts.
B gets only its generated skill and task inputs, without work-to-skill, authoring
history, or answer hints. Evaluators may use an answer key; executors may not.
When portability is in scope, cross-execute relevant examples between the hosts
named for that claim in the validation record.

Test native discovery with other creators present before claiming automatic
invocation compatibility. Prompt-level selection is not native discovery evidence.
Keep private inputs out of the repository. Record failures and corrections.
Reused cases are regression checks, not fresh held-out tests.

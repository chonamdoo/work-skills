# Behavioral checks

These synthetic inputs are maintainer evaluation data, not installed skills.
Package tests validate structure, not model judgment.

Supply each case request and the complete work-to-skill package to a fresh model
context. Keep acceptance criteria with the evaluator, not the author. Record
model, host, skill digest, allowed tools, input, output, and verdict. For text-only
runs, collect file contents and state that installation/tool execution did not occur.

Evaluate authoring (A), then run generated skills (B) on new inputs in fresh contexts.
B gets only its generated skill and task inputs, without work-to-skill, authoring
history, or answer hints. Evaluators may use an answer key; executors may not.
Cross-execute core examples between hosts named in the validation record.

Test native discovery with other creators present before claiming automatic
invocation compatibility. Prompt-level selection is not native discovery evidence.
Keep private inputs out of the repository. Record failures and corrections.
Reused cases are regression checks, not fresh held-out tests.

---
name: review
description: Perform a thorough code review of the specified files or changes
allowed-tools:
  - read
  - glob
  - grep
  - shell
effort: high
---

Review the code changes specified by the user. Focus on:

1. **Correctness**: Logic errors, edge cases, off-by-one bugs
2. **Security**: Input validation, injection, secrets exposure
3. **Performance**: N+1 queries, unnecessary allocations, blocking calls
4. **Readability**: Naming, complexity, documentation

Output a structured review with severity levels: critical, warning, suggestion.

$ARGUMENTS

"""Built-in workflow definitions."""

from octopus.workflow.schema import PhaseDefinition, PhaseStrategy, WorkflowDefinition


def _bug_finder_phase() -> PhaseDefinition:
    return PhaseDefinition(
        title="Find bugs",
        description="Scan codebase for bugs, errors, and quality issues",
        prompt_template=(
            "Task: {task}\n\n"
            "Previous phases:\n{previous_results}\n\n"
            "Scan the codebase for bugs, errors, and code quality issues. "
            "Focus on logic errors, type errors, unhandled edge cases, "
            "security vulnerabilities, and performance issues. "
            "Output a structured list of findings with severity: critical, high, medium, low. "
            "For each finding include: file, line, description, severity, and suggested fix."
        ),
        max_retries=1,
    )


def _code_review_phase() -> PhaseDefinition:
    return PhaseDefinition(
        title="Code review",
        description="Review code for correctness, style, and security",
        prompt_template=(
            "Task: {task}\n\n"
            "Previous phases:\n{previous_results}\n\n"
            "Perform a thorough code review. Check for:\n"
            "1. Correctness: logic errors, edge cases\n"
            "2. Style: naming, complexity, duplication\n"
            "3. Security: injection, validation, secrets\n"
            "4. Performance: N+1 queries, unnecessary allocations\n"
            "Output findings with severity and suggested fixes."
        ),
        max_retries=1,
    )


def _test_generator_phase() -> PhaseDefinition:
    return PhaseDefinition(
        title="Generate tests",
        description="Generate comprehensive unit tests",
        prompt_template=(
            "Task: {task}\n\n"
            "Previous phases:\n{previous_results}\n\n"
            "Generate comprehensive unit tests using pytest. "
            "Cover happy path, edge cases, error conditions, and boundary values. "
            "Run the tests and report results. Fix any failing tests."
        ),
        max_retries=2,
    )


def _refactor_phase() -> PhaseDefinition:
    return PhaseDefinition(
        title="Refactor",
        description="Refactor for improved structure and readability",
        prompt_template=(
            "Task: {task}\n\n"
            "Previous phases:\n{previous_results}\n\n"
            "Refactor the code to improve structure and readability. "
            "Extract reusable functions, reduce nesting, improve naming. "
            "Do NOT change behavior — only structure. "
            "Verify all existing tests still pass after refactoring."
        ),
        max_retries=1,
    )


def _verify_phase() -> PhaseDefinition:
    return PhaseDefinition(
        title="Verify",
        description="Verify fixes and ensure no regressions",
        prompt_template=(
            "Task: {task}\n\n"
            "Previous phases:\n{previous_results}\n\n"
            "Verify all fixes and changes. Ensure:\n"
            "1. All tests pass\n"
            "2. No regressions introduced\n"
            "3. Code quality maintained\n"
            "Report verification results."
        ),
        max_retries=1,
    )


# ---------------------------------------------------------------------------
# Built-in workflows
# ---------------------------------------------------------------------------

CODE_REVIEW = WorkflowDefinition(
    name="code-review",
    description="Scan for bugs, review code, suggest improvements",
    version="1.0",
    phases=[_bug_finder_phase(), _code_review_phase()],
)

FIX_AND_VERIFY = WorkflowDefinition(
    name="fix-and-verify",
    description="Find bugs, fix them, generate tests, verify",
    version="1.0",
    phases=[
        _bug_finder_phase(),
        _code_review_phase(),
        _test_generator_phase(),
        _verify_phase(),
    ],
)

REFACTOR = WorkflowDefinition(
    name="refactor",
    description="Refactor code and verify tests pass",
    version="1.0",
    phases=[_refactor_phase(), _verify_phase()],
)

PARALLEL_AUDIT = WorkflowDefinition(
    name="parallel-audit",
    description="Parallel code audit from multiple perspectives (security, correctness, performance)",
    version="1.0",
    phases=[
        PhaseDefinition(
            title="Multi-angle audit",
            description="Audit from security, correctness, and performance angles in parallel",
            prompt_template=(
                "Task: {task}\n\n"
                "Focus area: {item}\n\n"
                "Audit the codebase from the {item} perspective. "
                "Output findings with severity and suggested fixes."
            ),
            strategy=PhaseStrategy.PARALLEL,
            parallel_items=["security", "correctness", "performance"],
            max_retries=1,
        ),
        _verify_phase(),
    ],
)

BUILTIN_WORKFLOWS: dict[str, WorkflowDefinition] = {
    w.name: w
    for w in [CODE_REVIEW, FIX_AND_VERIFY, REFACTOR, PARALLEL_AUDIT]
}

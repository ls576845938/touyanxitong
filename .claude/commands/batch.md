# /batch

Batch-process multiple small tasks. Must be controllable and reversible.

## Trigger

```
/batch <task description>
```

## Behavior

1. Break the task into multiple sub-tasks.
2. For each sub-task, annotate:
   - Target file(s)
   - Risk level (low/medium/high)
   - Whether tests are needed
   - Whether it can run automatically
3. Output the batch plan first.
4. Execute only low-risk tasks.
5. Pause on medium/high-risk tasks and wait for confirmation.
6. After each batch completes, output a change summary.
7. Generate a batch report when all tasks are done.

## Constraints

- Do NOT make sweeping project-wide changes at once.
- Do NOT modify across multiple architecture layers casually.
- Do NOT modify database, auth, trading, capital, or core business logic without confirmation.
- Do NOT modify too many unrelated modules simultaneously.
- Do NOT make changes silently without a report.

## Output Format

### Batch Plan

| # | Sub-task | File Scope | Risk | Auto? |
|---|---|---|---|---|

### Batch Report

```markdown
### Completed
### Skipped
### Needs Confirmation
### Files Modified
### Test Results
### Rollback Advice
```

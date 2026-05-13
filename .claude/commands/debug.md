# /debug

Systematically diagnose bugs. Locate root cause first, then apply the minimal fix.

## Trigger

```
/debug <error description, log, file path, or symptom>
```

## Behavior

1. Collect context:
   - Error logs
   - Related files
   - Recent changes (git diff / git log)
   - Commands that trigger the error
   - Test results
2. Do NOT change code immediately.
3. Propose 3 most likely causes, ranked by probability.
4. For each cause, provide a verification method.
5. Use the smallest possible verification to pinpoint the issue.
6. After locating root cause, apply the minimal fix.
7. Run related tests after the fix.
8. Output debug report.

## Constraints

- Do NOT do large-scale changes upfront.
- Do NOT "guess-fix" without verification.
- Do NOT delete tests to make them pass.
- Do NOT work around the error.
- Do NOT swallow exceptions silently.
- Do NOT lower type constraints to mask problems.

## Output Format

```markdown
## Debug Report

### Symptom
### Relevant Logs
### Initial Assessment
### Possible Causes (ranked)
### Verification Process
### Root Cause
### Minimal Fix
### Test Results
### Residual Risk
```

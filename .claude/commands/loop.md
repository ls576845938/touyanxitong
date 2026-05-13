# /loop

Run a closed loop of Plan → Act → Test → Review → Fix → Record for iterative refinement.

## Trigger

```
/loop <target task>
```

## Behavior

Run up to 5 rounds. Each round:

1. **Plan**: Define this round's specific goal.
2. **Act**: Make the minimal necessary change.
3. **Test**: Run relevant tests or verification commands.
4. **Review**: Check if the goal is met.
5. **Fix**: If failed, apply the minimal fix.
6. **Record**: Record this round's results.

## Stop Conditions

- Task completed
- 2 consecutive rounds with no progress
- High-risk change encountered
- Test environment missing
- Needs user confirmation
- 5-round limit reached

## Constraints

- Do NOT loop indefinitely.
- Do NOT expand scope to complete the task.
- Do NOT blindly rewrite after failure.
- Do NOT modify unrelated files.
- Do NOT mask test failures.

## Output Format

```markdown
## Loop Report

### Overall Goal

#### Round 1
- Plan:
- Act:
- Test:
- Review:
- Result:

#### Round 2
...

### Final Result
### Incomplete Reason
### Items Needing Manual Confirmation
### Next Steps
```

# /simplify

Simplify code, docs, architecture, components, or repeated logic without breaking business behavior.

## Trigger

```
/simplify <target file or module>
```

## Behavior

1. Read the target file/module.
2. Summarize current complexity sources.
3. Judge whether simplification is actually needed (don't fix what isn't broken).
4. Output a simplification plan.
5. Execute low-risk simplifications first:
   - Remove dead code
   - Merge duplicated functions
   - Rename unclear variables
   - Split overly long functions
   - Extract shared logic
   - Reduce unnecessary abstraction layers
   - Keep external interfaces unchanged
6. Run existing tests after simplification.
7. Output a change report.

## Constraints

- Do NOT break business logic for the sake of "cleaner look".
- Do NOT do large-scale refactoring.
- Do NOT change public APIs unless explicitly authorized.
- Do NOT delete important features without confirmation.
- Do NOT hide business logic inside harder-to-understand abstractions.

## Output Format

```markdown
## Simplify Report

### Target
### Current Problems
### Simplification Strategy
### Changes Made
### Why Not Changed
### Risk Points
### Test Results
### Next Steps
```

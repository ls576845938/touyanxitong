# /claude-api

Integrate Claude API / Anthropic SDK into the project. Design minimal, safe wrappers.

## Trigger

```
/claude-api <requirement description>
```

## Behavior

1. Determine project tech stack.
2. Check if an LLM provider / AI client / API wrapper already exists.
3. Do NOT reinvent existing wheels.
4. Design the smallest usable wrapper.
5. Prefer environment variables, never hardcode keys.
6. Support:
   - `ANTHROPIC_API_KEY`
   - `ANTHROPIC_BASE_URL` (optional)
   - `CLAUDE_MODEL` (optional)
7. Implement:
   - Client initialization
   - `sendMessage` / `generateText`
   - Timeout
   - Retry
   - Error handling
   - Basic logging
   - Mock for testing
8. Generate usage documentation.
9. Do NOT commit real API keys.

## Safety Constraints

- Do NOT write API keys into source code.
- Do NOT read or print sensitive values from `.env`.
- Do NOT log API keys.
- Do NOT upload API keys.
- Do NOT call paid real APIs in tests unless explicitly authorized.
- Default to mock for tests.

## Target File Structure

**TypeScript project:**
```
src/lib/ai/claudeClient.ts
src/lib/ai/types.ts
src/lib/ai/index.ts
tests/ai/claudeClient.test.ts
```

**Python project:**
```
src/ai/claude_client.py
src/ai/types.py
tests/test_claude_client.py
```

## Output Format

```markdown
## Claude API Integration Report

### Current Tech Stack
### Existing AI Client?
### Design Plan
### New Files
### Modified Files
### Environment Variables
### Usage Example
### Test Approach
### Security Notes
### Next Steps
```

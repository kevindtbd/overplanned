# M-007: Prompt Bar

## Description
Natural language input for mid-trip changes with injection prevention.

## Task
1. Haiku parsing: user text → structured JSON { classification, confidence, entities }
2. Latency: 1.5s Haiku timeout, fallback to keyword matching
3. Input cap: 200 characters
4. Injection prevention: NO ActivityNode data or user persona in prompt context
5. [USER_DATA_START]/[USER_DATA_END] delimiters on user text
6. Log all inputs + responses for security audit
7. Classification maps to PivotTrigger types

## Output
apps/web/components/prompt/PromptBar.tsx

## Zone
prompt-bar

## Dependencies
- M-003

## Priority
45

## Target Files
- apps/web/components/prompt/PromptBar.tsx
- services/api/routers/prompt.py
- services/api/pivot/prompt_parser.py

## Files
- docs/plans/vertical-plans-v2.md

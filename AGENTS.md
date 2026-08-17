# JARVIS Development Instructions

## General rules

- Inspect relevant files before making changes.
- Before editing, briefly explain the intended changes and affected files.
- Preserve currently working behavior unless explicitly instructed otherwise.
- Make small, reviewable changes.
- Do not refactor unrelated code.
- Do not modify `.env`.
- Do not expose or commit API keys, credentials, or tokens.
- Do not commit or push unless explicitly instructed.
- Do not delete files, reset Git state, clear persistent data, or run destructive commands without approval.

## Testing

- Run relevant automated tests after changes.
- If no relevant automated tests exist, state that clearly and run the most appropriate available checks.
- Clearly report which tests and checks were run.
- Do not claim hardware or audio behavior is verified unless it was manually tested.
- Provide manual verification steps for microphone, speaker, tray, window, and wake-word behavior when relevant.

## Documentation

- Read relevant files under `docs/` before implementing.
- Update relevant documentation when user-visible behavior, configuration, interfaces, or architecture changes.

## Communication

After implementation or attempted implementation, explain:

- Files changed
- Processing flow
- Reasons for the design
- Automated test and check results
- Manual verification steps
- Remaining risks or incomplete items
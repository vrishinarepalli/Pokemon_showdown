# 08 — Working Conventions (on this project)

These are standing rules. They override default behavior.

## Ponytail by default
Laziest-working-solution style. Climb the ladder and stop at the first rung that
holds: YAGNI → stdlib → native platform → existing dep → one line → minimal code.
No unrequested abstractions, no scaffolding "for later". Shortest working diff
wins. Mark deliberate simplifications with a `# ponytail:` comment naming the
ceiling + upgrade path. Non-trivial logic leaves one runnable check behind.

## Archive, never hard-delete
Unused/dead code goes to a **git archive branch** (e.g.
`archive/pre-ponytail-cleanup`), pushed, so it's referenceable forever. Never
permanently delete code.

## Never delete folders or files
Only add. Modifications need explicit approval first. (Stronger than archive-not-
delete: applies to *any* file/folder removal.)

## Never delete database data without permission
No Firestore/DB deletes unless explicitly instructed. (Carried over from the
user's other projects; applies generally.)

## Commit/push only when asked
Don't commit or push unless the user requests it. Current state: decision-cache
work is intentionally **uncommitted**.

## Secrets
API keys live in gitignored `.env`, never in code. The Groq key was exposed in
chat → it should be regenerated.

## Commit message footer (when we do commit)
End commit messages with:
`Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`

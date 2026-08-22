# Entire — setup for the team

Entire captures each agent session and links it to the commit it produced.
**It is mandatory for the hackathon submission**: without linked checkpoints the
submission is not accepted.

The repo is already configured (`.entire/`, plus hooks for Claude Code, Codex,
Cursor, Copilot CLI and Gemini). You only need to do the two machine-local steps.

## One-time, per person

```bash
curl -fsSL https://entire.io/install.sh | bash   # 1. install the CLI
entire login                                     # 2. log in with your own account
```

That's it. Do **not** run `entire enable` — it is already enabled in this repo and
the settings are committed. Verify with:

```bash
entire status        # -> "Enabled · branch main"
```

## Working

Use your coding agent as usual **with this repo as your editor's workspace root**.
Hooks are per-project: if you open the editor on a parent folder, nothing is captured.

On push you should see:

```
[entire] Pushing N checkpoint ref(s) to origin...... done
```

That line is the confirmation the submission requires.

## If a session wasn't captured

Happens when you started the agent before installing, or opened the wrong folder:

```bash
entire session attach <session-id> --agent claude-code
```

Session ids live in `~/.claude/projects/<encoded-repo-path>/<session-id>.jsonl`
(Codex/Cursor/Gemini have their own paths — `entire session list` also shows them).

## Useful

```bash
entire session current      # active session in this worktree
entire checkpoint list      # checkpoints on this branch
entire checkpoint search "…" # search code + agent reasoning
```

## Why refs, not a branch

Checkpoints are stored one git ref per checkpoint (`refs/entire/checkpoints/…`).
With the `branch` backend all four of us would push to the same
`entire/checkpoints/v1` branch and collide. Refs never conflict — leave it as is.

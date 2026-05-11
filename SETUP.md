# Slim Claude Code CLI — Deployment Guide

## Environment Setup

Add these export commands to your shell profile (`~/.bashrc`, `~/.zshrc`, or `~/.config/claude/shell-aliases`):

```bash
# Slim Orchestration — Model Version Pinning
# These MUST be set BEFORE launching Claude Code so subagent aliases resolve correctly

export ANTHROPIC_DEFAULT_HAIKU_MODEL="claude-haiku-4-5-20251001"
export ANTHROPIC_DEFAULT_SONNET_MODEL="claude-sonnet-4-6"
export ANTHROPIC_DEFAULT_OPUS_MODEL="claude-opus-4-5-20251101"

# Convenience aliases for direct model invocation
alias opus="claude --model claude-opus-4-5-20251101"
alias sonnet="claude --model claude-sonnet-4-6"
alias haiku="claude --model claude-haiku-4-5-20251001"
```

**IMPORTANT**: The `ANTHROPIC_DEFAULT_*` variables are what make subagent model selection work.
Without them, agents configured with `model: haiku` or `model: sonnet` may resolve to
unexpected versions. The agent YAML frontmatter only accepts aliases (`haiku`, `sonnet`, `opus`),
not full model IDs — the pinning happens via these environment variables.

After adding, run `source ~/.bashrc` (or equivalent) to apply.

## Project Structure

```
your-project/
├── CLAUDE.md                    # Orchestration protocol (Opus planner rules)
├── .claude/
│   ├── agents/
│   │   ├── explorer.md          # Haiku 4.5 — read-only codebase mapper
│   │   ├── librarian.md         # Sonnet 4.6 — docs + memory research
│   │   └── reviewer.md          # Sonnet 4.6 — validation + code review
│   ├── settings.json            # Project settings + hooks
│   └── settings.local.json      # Personal overrides (git-ignored)
└── SETUP.md                     # This file
```

## Quick Start

1. **Copy these files** into your project root.
2. **Set up the environment aliases** (see above).
3. **Start Claude Code** with the Opus model: `claude --model claude-opus-4-5-20251101`
4. **Verify agents are loaded**: Run `claude agents` — you should see `explorer`, `librarian`, and `reviewer`.
5. **Run a test plan**: Type "explore this codebase" and confirm the explorer agent handles it.

## Model Tiering Rationale

| Tier | Model | Cost vs Sonnet | Use Case |
|------|-------|---------------|----------|
| **Planner** | Opus 4.5 | ~5x cheaper than Opus 4.7 | High-reasoning plan design |
| **Seniors** | Sonnet 4.6 | Baseline | Verification, memory, research |
| **Workers** | Haiku 4.5 | ~92% cheaper | Mechanical tasks (search, read, simple edits) |

## Token Budget Management

The `CLAUDE.md` protocol enforces token budget awareness:
- **Green (<60%)**: Normal operation
- **Yellow (60-80%)**: Summarize, prefer delegation
- **Red (>80%)**: Offload everything to subagents

## Customization

- **Adjust agent tools**: Edit the `tools` field in each agent's YAML frontmatter
- **Change models per agent**: Update the `model` field (e.g., use Sonnet for explorer if you have quota)
- **Add personal settings**: Create `.claude/settings.local.json` (not committed to git)
- **Add more agents**: Create new `.md` files in `.claude/agents/` with the same YAML frontmatter format

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Agent not discovered | Check file is in `.claude/agents/` with `.md` extension and valid YAML frontmatter |
| Model not found | Verify model ID with `claude models list` — ensure version matches |
| Hooks not firing | Check JSON syntax in `.claude/settings.json` — must be valid JSON |
| Token budget warnings | Reduce context: delegate more, read fewer files directly |

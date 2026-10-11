# Hokm × Jev
⚠️ I'm working on it and project is not finished

Play Hokm (Persian trick-taking card game) against bots driven by Jev, TypeSafe's System One decision model, and study how they decide.

- 2-player and 4-player partnership; any seat human or bot
- Bots see only what a human in their seat would see
- Every decision is recorded: what the bot saw, what Jev answered, and the hidden truth


## Quick start (after Phase 0)
```bash
uv sync
cp .env.example .env        # fill in TYPESAFE_API_KEY and JEV_MODEL
uv run pytest
docker compose up -d db     # Phase 3+
```

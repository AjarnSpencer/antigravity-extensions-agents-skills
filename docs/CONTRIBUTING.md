# Contributing to Antigravity CLI Extensions, Agents & Skills

We welcome contributions from the global AI development community!

---

## How to Add a New Extension

1. Create a directory under `extensions/<extension_name>/`.
2. Include a `gemini-extension.json` manifest.
3. Place `.toml` slash commands in `commands/`.
4. Implement tool logic in `scripts/`.
5. Add `requirements.txt` and a comprehensive `README.md`.
6. Ensure no private API keys or hardcoded personal credentials exist.

## How to Add a New Skill

1. Create a directory under `skills/<skill_name>/`.
2. Add a `SKILL.md` with standard YAML frontmatter (`name`, `description`).
3. Document workflows, edge cases, and code templates.

## How to Add an Agent Blueprint

1. Create a directory under `agents/<agent_name>/`.
2. Add an `AGENT.md` defining the agent's role, core competencies, and system prompt.

---

## Code Standards
- Python 3.10+ compatible.
- All dependencies must be specified in `requirements.txt`.
- Non-blocking asynchronous design (`asyncio`) for network and I/O operations.
- Clean zero-API-key fallbacks wherever applicable.

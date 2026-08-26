# Antigravity CLI Metapackage Architecture

This repository defines an open standard for **Antigravity CLI** and **Gemini CLI** extensions, skills, and agent blueprints.

---

## 1. Extension Anatomy

Each extension in `extensions/<name>` follows a standardized structure:

```
extensions/<name>/
├── gemini-extension.json      # Extension metadata and entry point
├── requirements.txt           # Python dependencies
├── README.md                  # Extension documentation and command examples
├── commands/                  # Slash command definitions (.toml)
│   ├── command1.toml
│   └── command2.toml
├── scripts/                   # Executable tools and worker engines
│   └── tool.py
└── skills/                    # Associated progressive disclosure skills
    └── <skill-name>/
        └── SKILL.md
```

### Slash Command Manifest Format (`commands/*.toml`):
```toml
description = "Clear human-readable description of slash command"
prompt = """
Instructions for the model:

!{${extensionPath}/venv/bin/python ${extensionPath}/scripts/tool.py action "{{args}}"}
"""
```

The `${extensionPath}` variable is dynamically expanded by the CLI at runtime to the absolute directory path of the installed extension, guaranteeing portability across Linux, macOS, and Windows.

---

## 2. Dynamic TTS Model Resolution & Failover Matrix

```
[Audio Synthesis Request]
           │
           ▼
[Check GEMINI_API_KEY] ──(Present & Probed Functional)──► [Tier 1: Google GenAI Preview TTS]
           │                                                         │
       (Missing / Deprecated / 404 / 429)                            │ (Audio Generated)
           │                                                         │
           ▼                                                         ▼
[Tier 2: Universal Edge-TTS Voice Matrix] ───────────────► [Raw Audio Stream]
           │
           ▼
[Broadcast DSP Processing]
 ├── High-pass / Low-pass Telephony Equalization (300Hz-3400Hz)
 ├── Analog Background Line Noise (-48dB)
 ├── Procedural Pentatonic Synth Jingles
 └── Broadcast Studio Room Tone Bed (-50dB)
           │
           ▼
[Master MP3 Export]
```

---

## 3. Progressive Skill Disclosure

Skills located in `skills/` or `.agents/skills/` are dynamically indexed by Antigravity CLI. Only their names and descriptions are exposed in the root context. The full markdown instructions are dynamically injected only when an agent or user invokes that capability, maintaining high context window efficiency.

---
name: youtube-analyzer
description: >-
  Extracts YouTube transcripts, analyzes narrative structures, creates structured executive summaries,
  translates content into 75+ languages, generates Mermaid infographics, and converts videos into two-host podcasts and talk radio shows.
---

# YouTube Analyzer & Multimedia Transformer Skill

This skill equips agents with end-to-end capabilities for transforming unstructured YouTube video content into structured intelligence, diagrams, and studio-grade podcasts.

---

## Capabilities & Workflows

1. **Transcript Extraction & Normalization:**
   - Query YouTube API / `youtube-transcript-api` for official or auto-generated captions.
   - Fallback to `yt-dlp` subtitle extraction if API access is restricted.
   - Clean timestamps, format paragraphs, and strip repetitive filler.

2. **Multilingual Translation Matrix:**
   - Translates video transcripts into 75+ global languages preserving semantic tone and technical nuance.

3. **Executive Summaries & Takeaways:**
   - **Brief:** 3 bullet executive summary for rapid consumption.
   - **Standard:** Thematic breakdown with key quotes and core conclusions.
   - **Detailed:** Comprehensive timestamped chapter-by-chapter analysis.

4. **Visual Diagram & Infographic Generation:**
   - Translates video arguments into **Mermaid** mindmaps, timelines, and flowcharts.
   - Formats visual design prompts compatible with `nanobanana` multi-modal image generators.

5. **Audio Conversion (Podcasts & Radio Shows):**
   - Directs two-host conversational scripts (`Host` and `Co-host`) with natural banter.
   - Directs late-night radio caller-in broadcasts with host monologue, caller debates, and broadcast DSP sound design.

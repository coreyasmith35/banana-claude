# Fork notes — Vertex AI support

This fork of [AgriciDaniel/banana-claude](https://github.com/AgriciDaniel/banana-claude)
adds **Vertex AI** as the default image-generation backend while **keeping the
original AI Studio API-key path intact**, and removes the upstream "community
footer" promo.

## What changed

**Added (new files — never conflict on upstream merge):**
- `skills/banana/scripts/generate_vertex.py` — SDK-based generation. Dual backend:
  Vertex (default) or AI Studio key. PEP 723 inline deps (`google-genai`), run via `uv`.
- `skills/banana/scripts/edit_vertex.py` — same, for image editing.

**Edited (small, predictable conflicts possible on merge):**
- `skills/banana/SKILL.md` — added an "Execution Backend (Vertex AI)" section,
  pointed the primary generate/edit path at the new scripts, added Nano Banana Pro
  (`gemini-3-pro-image`) to model routing, and **removed the community footer**.
- `skills/banana/references/gemini-models.md` — corrected the Nano Banana Pro
  section (it is active on Vertex, contrary to upstream's "shut down" note, which
  applies to the AI Studio preview id only).

**Untouched (clean merges):** `prompt-engineering.md`, presets, cost tracking,
batch, the original `generate.py` / `edit.py` (still usable, API-key only).

## Usage

```bash
# Vertex (default — uses gcloud ADC, no API key)
uv run skills/banana/scripts/generate_vertex.py \
  --prompt "..." --aspect-ratio 4:5 --resolution 2K --model gemini-3.1-flash-image-preview

# Nano Banana Pro (highest fidelity / text)
uv run skills/banana/scripts/generate_vertex.py --prompt "..." --model gemini-3-pro-image

# AI Studio key instead of Vertex
uv run skills/banana/scripts/generate_vertex.py --prompt "..." --backend api --api-key "$GEMINI_API_KEY"

# Edit an existing image
uv run skills/banana/scripts/edit_vertex.py --image in.png --prompt "..."
```

**Auth / project resolution (Vertex):** project is resolved from `--project`,
then `GOOGLE_CLOUD_PROJECT`, then ADC, then `gcloud config`. Location defaults to
`global` (override with `--location` / `GOOGLE_CLOUD_LOCATION`). No project ID is
hardcoded, so this fork is safe to keep public.

Models verified working on Vertex: `gemini-3.1-flash-image-preview` (Nano Banana 2)
and `gemini-3-pro-image` (Nano Banana Pro).

## Syncing upstream

```bash
git fetch upstream
git merge upstream/main   # resolve small conflicts in SKILL.md / gemini-models.md if any
```
The valuable prompt-craft updates live in untouched files and merge cleanly.

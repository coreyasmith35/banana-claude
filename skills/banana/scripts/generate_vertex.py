# /// script
# requires-python = ">=3.10"
# dependencies = ["google-genai>=1.40"]
# ///
"""Banana Claude -- SDK backend: image generation.

Supports two auth backends (Vertex API key support is preserved alongside Vertex AI):
  - vertex  (default): Vertex AI via ADC (gcloud application-default creds).
            Project resolved from --project / GOOGLE_CLOUD_PROJECT / ADC / gcloud.
            Location from --location / GOOGLE_CLOUD_LOCATION (default "global").
  - api:    Google AI Studio key from --api-key / GEMINI_API_KEY / GOOGLE_API_KEY.
            Selected automatically when --api-key is passed, or with --backend api.

Run with uv so the dependency is auto-provisioned (no venv needed):
    uv run generate_vertex.py --prompt "..." [--aspect-ratio 4:5] [--resolution 2K]
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

DEFAULT_MODEL = "gemini-3.1-flash-image-preview"
DEFAULT_RESOLUTION = "2K"  # uppercase required -- lowercase is silently ignored
DEFAULT_RATIO = "1:1"
DEFAULT_LOCATION = "global"
OUTPUT_DIR = Path.home() / "Documents" / "nanobanana_generated"

VALID_RATIOS = {"1:1", "16:9", "9:16", "4:3", "3:4", "2:3", "3:2",
                "4:5", "5:4", "1:4", "4:1", "1:8", "8:1", "21:9"}
VALID_RESOLUTIONS = {"512", "1K", "2K", "4K"}


def fail(message, **extra):
    print(json.dumps({"error": True, "message": message, **extra}))
    sys.exit(1)


def resolve_project(explicit):
    if explicit:
        return explicit
    for var in ("GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_PROJECT_ID", "GCLOUD_PROJECT"):
        if os.environ.get(var):
            return os.environ[var]
    try:
        import google.auth

        _, adc_project = google.auth.default()
        if adc_project:
            return adc_project
    except Exception:
        pass
    try:
        import subprocess

        out = subprocess.run(
            ["gcloud", "config", "get-value", "project"],
            capture_output=True, text=True, timeout=10,
        ).stdout.strip()
        if out and out != "(unset)":
            return out
    except Exception:
        pass
    return None


def make_client(args):
    from google import genai

    key = (args.api_key or os.environ.get("GEMINI_API_KEY")
           or os.environ.get("GOOGLE_AI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))

    backend = args.backend
    if args.api_key:
        backend = "api"
    if backend == "auto":
        backend = "api" if key else "vertex"

    if backend == "api":
        if not key:
            fail("backend 'api' selected but no key. Set GEMINI_API_KEY or pass --api-key.")
        return genai.Client(api_key=key), "api", None, None

    project = resolve_project(args.project)
    if not project:
        fail("No GCP project for Vertex. Pass --project or set GOOGLE_CLOUD_PROJECT "
             "(or run 'gcloud config set project ...').")
    location = args.location or os.environ.get("GOOGLE_CLOUD_LOCATION") or DEFAULT_LOCATION
    return genai.Client(vertexai=True, project=project, location=location), "vertex", project, location


def build_config(aspect_ratio, resolution, image_only, thinking_level):
    from google.genai import types

    modalities = ["IMAGE"] if image_only else ["TEXT", "IMAGE"]
    try:
        image_cfg = types.ImageConfig(aspect_ratio=aspect_ratio, image_size=resolution)
    except TypeError:
        image_cfg = types.ImageConfig(aspect_ratio=aspect_ratio)

    kwargs = {"response_modalities": modalities, "image_config": image_cfg}
    if thinking_level:
        try:
            return types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(thinking_level=thinking_level), **kwargs
            )
        except TypeError:
            pass
    return types.GenerateContentConfig(**kwargs)


def main():
    parser = argparse.ArgumentParser(description="Generate images via google-genai (Vertex or API key)")
    parser.add_argument("--prompt", required=True, help="Image generation prompt")
    parser.add_argument("--aspect-ratio", default=DEFAULT_RATIO)
    parser.add_argument("--resolution", default=DEFAULT_RESOLUTION, help="512, 1K, 2K, 4K")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--backend", default="vertex", choices=["vertex", "api", "auto"])
    parser.add_argument("--project", default=None, help="GCP project (Vertex). Default: ADC/gcloud.")
    parser.add_argument("--location", default=None, help="Vertex location (default: global)")
    parser.add_argument("--api-key", default=None, help="AI Studio key (forces api backend)")
    parser.add_argument("--thinking", default=None, choices=["minimal", "low", "medium", "high"])
    parser.add_argument("--image-only", action="store_true")
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    args = parser.parse_args()

    if args.aspect_ratio not in VALID_RATIOS:
        fail(f"Invalid aspect ratio '{args.aspect_ratio}'. Valid: {sorted(VALID_RATIOS)}")
    if args.resolution not in VALID_RESOLUTIONS:
        fail(f"Invalid resolution '{args.resolution}'. Valid: {sorted(VALID_RESOLUTIONS)}")

    client, backend, project, location = make_client(args)
    config = build_config(args.aspect_ratio, args.resolution, args.image_only, args.thinking)

    try:
        resp = client.models.generate_content(model=args.model, contents=args.prompt, config=config)
    except Exception as e:  # noqa: BLE001
        fail(f"{type(e).__name__}: {str(e)[:400]}", backend=backend)

    candidates = resp.candidates or []
    if not candidates:
        fb = getattr(resp, "prompt_feedback", None)
        fail(f"No candidates returned. Feedback: {fb}", backend=backend)

    cand = candidates[0]
    parts = (cand.content.parts if cand.content and cand.content.parts else []) or []
    image_bytes = None
    text_response = ""
    for part in parts:
        inline = getattr(part, "inline_data", None)
        if inline and inline.data:
            image_bytes = inline.data
        elif getattr(part, "text", None):
            text_response = part.text

    if not image_bytes:
        fail(f"No image in response. finishReason: {getattr(cand, 'finish_reason', None)}", backend=backend)

    out_dir = Path(args.output_dir).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    output_path = (out_dir / f"banana_{timestamp}.png").resolve()
    with open(output_path, "wb") as f:
        f.write(image_bytes)

    print(json.dumps({
        "path": str(output_path),
        "model": args.model,
        "backend": backend,
        "project": project,
        "location": location,
        "aspect_ratio": args.aspect_ratio,
        "resolution": args.resolution,
        "text": text_response,
    }, indent=2))


if __name__ == "__main__":
    main()

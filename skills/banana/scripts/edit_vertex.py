# /// script
# requires-python = ">=3.10"
# dependencies = ["google-genai>=1.40"]
# ///
"""Banana Claude -- SDK backend: image editing.

Same dual-backend auth as generate_vertex.py (Vertex AI default, AI Studio key
preserved). Edits an existing image with a text instruction.

Run with uv:
    uv run edit_vertex.py --image in.png --prompt "remove the background"
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

DEFAULT_MODEL = "gemini-3.1-flash-image-preview"
DEFAULT_LOCATION = "global"
OUTPUT_DIR = Path.home() / "Documents" / "nanobanana_generated"
MIME_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
              ".webp": "image/webp", ".gif": "image/gif"}


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
        fail("No GCP project for Vertex. Pass --project or set GOOGLE_CLOUD_PROJECT.")
    location = args.location or os.environ.get("GOOGLE_CLOUD_LOCATION") or DEFAULT_LOCATION
    return genai.Client(vertexai=True, project=project, location=location), "vertex", project, location


def main():
    parser = argparse.ArgumentParser(description="Edit images via google-genai (Vertex or API key)")
    parser.add_argument("--image", required=True, help="Path to input image")
    parser.add_argument("--prompt", required=True, help="Edit instruction")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--backend", default="vertex", choices=["vertex", "api", "auto"])
    parser.add_argument("--project", default=None)
    parser.add_argument("--location", default=None)
    parser.add_argument("--api-key", default=None)
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    args = parser.parse_args()

    from google.genai import types

    image_path = Path(args.image).expanduser().resolve()
    if not image_path.exists():
        fail(f"Image not found: {image_path}")
    mime_type = MIME_TYPES.get(image_path.suffix.lower(), "image/png")
    image_bytes_in = image_path.read_bytes()

    client, backend, project, location = make_client(args)

    contents = [types.Content(role="user", parts=[
        types.Part.from_text(text=args.prompt),
        types.Part.from_bytes(data=image_bytes_in, mime_type=mime_type),
    ])]
    config = types.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"])

    try:
        resp = client.models.generate_content(model=args.model, contents=contents, config=config)
    except Exception as e:  # noqa: BLE001
        fail(f"{type(e).__name__}: {str(e)[:400]}", backend=backend)

    candidates = resp.candidates or []
    if not candidates:
        fb = getattr(resp, "prompt_feedback", None)
        fail(f"No candidates returned. Feedback: {fb}", backend=backend)

    cand = candidates[0]
    parts = (cand.content.parts if cand.content and cand.content.parts else []) or []
    image_out = None
    text_response = ""
    for part in parts:
        inline = getattr(part, "inline_data", None)
        if inline and inline.data:
            image_out = inline.data
        elif getattr(part, "text", None):
            text_response = part.text

    if not image_out:
        fail(f"No image in response. finishReason: {getattr(cand, 'finish_reason', None)}", backend=backend)

    out_dir = Path(args.output_dir).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    output_path = (out_dir / f"banana_edit_{timestamp}.png").resolve()
    with open(output_path, "wb") as f:
        f.write(image_out)

    print(json.dumps({
        "path": str(output_path),
        "model": args.model,
        "backend": backend,
        "project": project,
        "location": location,
        "source": str(image_path),
        "text": text_response,
    }, indent=2))


if __name__ == "__main__":
    main()

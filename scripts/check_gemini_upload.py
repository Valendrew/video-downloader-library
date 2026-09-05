"""Manually validate Gemini upload/use/delete with the synthetic video fixture."""

import argparse
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

from check_provider_apis import credentials, request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--video", required=True)
    args = parser.parse_args()
    keys = credentials(args.env_file)
    video = Path(args.video).read_bytes()
    headers = {"x-goog-api-key": keys["GEMINI_API_KEY"]}
    start = urllib.request.Request(
        "https://generativelanguage.googleapis.com/upload/v1beta/files",
        data=json.dumps(
            {"file": {"display_name": "vcp-validation-transitions"}}
        ).encode(),
        headers={
            **headers,
            "Content-Type": "application/json",
            "X-Goog-Upload-Protocol": "resumable",
            "X-Goog-Upload-Command": "start",
            "X-Goog-Upload-Header-Content-Length": str(len(video)),
            "X-Goog-Upload-Header-Content-Type": "video/mp4",
        },
    )
    with urllib.request.urlopen(start, timeout=30) as result:
        upload_url = result.headers["X-Goog-Upload-URL"]
        print("Upload initialization HTTP", result.status, flush=True)
    parsed = urllib.parse.urlsplit(upload_url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "generativelanguage.googleapis.com"
    ):
        raise SystemExit("Unexpected upload host; stopped")
    upload = urllib.request.Request(
        upload_url,
        data=video,
        headers={
            "X-Goog-Upload-Offset": "0",
            "X-Goog-Upload-Command": "upload, finalize",
            "Content-Type": "video/mp4",
        },
    )
    with urllib.request.urlopen(upload, timeout=60) as result:
        file = json.load(result)["file"]
        print("Upload HTTP", result.status, flush=True)
    try:
        deadline = time.monotonic() + 60
        while file.get("state") == "PROCESSING" and time.monotonic() < deadline:
            time.sleep(1)
            _, file = request(
                "https://generativelanguage.googleapis.com/v1beta/" + file["name"],
                headers,
            )
        print("File state", file.get("state"), flush=True)
        if file.get("state") != "ACTIVE":
            raise SystemExit("File not ACTIVE")
        report = []
        for model, temporal in [
            ("gemini-3.8-flash", "none"),
            ("gemini-3.5-flash-lite", "windows"),
        ]:
            properties = {"description": {"type": "string"}}
            prompt = "Describe each distinct color and visible label in this silent clip, concisely."
            if temporal == "windows":
                properties["window_id"] = {
                    "type": "string",
                    "enum": ["red_window", "green_window", "blue_window"],
                }
                prompt += " Assign each observation to its window: red_window=[0,2), green_window=[2,4), blue_window=[4,6]."
            body = {
                "model": model,
                "store": False,
                "input": [
                    {
                        "type": "video",
                        "uri": file["uri"],
                        "mime_type": "video/mp4",
                        "resolution": "low",
                        "processing": {"type": "static", "fps": 1},
                    },
                    {"type": "text", "text": prompt},
                ],
                "generation_config": {"thinking_level": "low"},
                "response_format": {
                    "type": "object",
                    "properties": {
                        "events": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": properties,
                                "required": list(properties),
                                "additionalProperties": False,
                            },
                        }
                    },
                    "required": ["events"],
                    "additionalProperties": False,
                },
            }
            status, data = request(
                "https://generativelanguage.googleapis.com/v1beta/interactions",
                {**headers, "Content-Type": "application/json"},
                body,
            )
            report.append(
                {
                    "model": model,
                    "temporal": temporal,
                    "http_status": status,
                    "response": data,
                }
            )
            print(
                json.dumps(
                    {
                        "model": model,
                        "temporal": temporal,
                        "http_status": status,
                        "status": data.get("status"),
                    }
                ),
                flush=True,
            )
        safe = json.dumps(report, indent=2)
        for key in keys.values():
            if key:
                safe = safe.replace(key, "[REDACTED]")
        Path(".validation/gemini-upload.json").write_text(safe)
    finally:
        delete = urllib.request.Request(
            "https://generativelanguage.googleapis.com/v1beta/" + file["name"],
            headers=headers,
            method="DELETE",
        )
        with urllib.request.urlopen(delete, timeout=30) as result:
            print("Remote file deletion HTTP", result.status, flush=True)


if __name__ == "__main__":
    main()

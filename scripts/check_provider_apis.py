"""Manual API checks; explicitly reads a private env file and makes real requests.

This script is independent of the library. Never run it in routine CI.
Raw responses are stored only under the ignored .validation directory.
"""

import argparse
import base64
import json
import shlex
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def credentials(path):
    values = {}
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if line.startswith("export "):
            line = line[7:].lstrip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        parts = shlex.split(value, comments=True)
        values[key.strip()] = parts[0] if parts else ""
    for name in ("GEMINI_API_KEY", "SUPADATA_API_KEY"):
        if not values.get(name):
            raise SystemExit("Missing " + name)
    return values


def request(url, headers, body=None):
    req = urllib.request.Request(
        url, headers=headers, data=None if body is None else json.dumps(body).encode()
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        try:
            return error.code, json.load(error)
        except ValueError:
            return error.code, {"error": "non_json_response"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--provider", choices=("gemini", "supadata"), required=True)
    parser.add_argument("--video")
    parser.add_argument("--url")
    parser.add_argument("--matrix", action="store_true")
    parser.add_argument(
        "--model", choices=("gemini-3.8-flash", "gemini-3.5-flash-lite")
    )
    parser.add_argument(
        "--platform", choices=("youtube", "instagram", "tiktok"), default="youtube"
    )
    args = parser.parse_args()
    keys = credentials(args.env_file)
    destination = Path(".validation")
    destination.mkdir(exist_ok=True)
    if args.provider == "supadata":
        if not args.url:
            parser.error("--url is required for Supadata")
        headers = {"x-api-key": keys["SUPADATA_API_KEY"]}
        url = "https://api.supadata.ai/v1/transcript?" + urllib.parse.urlencode(
            {"url": args.url, "mode": "generate", "text": "false"}
        )
        status, data = request(url, headers)
        history = [{"http_status": status, "response": data}]
        print(
            json.dumps(
                {"provider": "supadata", "http_status": status, "keys": list(data)}
            ),
            flush=True,
        )
        deadline = time.monotonic() + 180
        job_id = data.get("jobId")
        while status in (200, 202) and job_id and time.monotonic() < deadline:
            time.sleep(1)
            status, data = request(
                "https://api.supadata.ai/v1/transcript/"
                + urllib.parse.quote(job_id, safe=""),
                headers,
            )
            history.append({"http_status": status, "response": data})
            if (
                data.get("status") in ("completed", "failed")
                or "content" in data
                or status >= 400
            ):
                break
        for key in keys.values():
            if key:
                history = json.loads(json.dumps(history).replace(key, "[REDACTED]"))
        (destination / ("supadata-" + args.platform + ".json")).write_text(
            json.dumps(history, indent=2)
        )
        print(
            json.dumps(
                {
                    "provider": "supadata",
                    "http_status": status,
                    "job_status": data.get("status"),
                    "keys": list(data),
                    "segment_count": len(data["content"])
                    if isinstance(data.get("content"), list)
                    else None,
                }
            ),
            flush=True,
        )
        return
    if not args.video:
        parser.error("--video is required for Gemini")
    video = base64.b64encode(Path(args.video).read_bytes()).decode()
    runs = [("static", "low", "low", 2)]
    if args.matrix:
        runs += [
            ("static", "medium", "medium", 1),
            ("static", "high", "high", 0.5),
            ("agentic", "low", "low", None),
            ("agentic", "medium", "medium", None),
            ("agentic", "high", "high", None),
        ]
    for model in (
        [args.model] if args.model else ("gemini-3.8-flash", "gemini-3.5-flash-lite")
    ):
        model_runs = list(runs)
        if args.matrix and model.endswith("lite"):
            model_runs.append(("static", "low", "minimal", 2))
        for mode, resolution, thinking, fps in model_runs:
            label = f"{model}-{mode}-{resolution}-{thinking}"
            result_path = destination / (label + ".json")
            if (
                result_path.exists()
                and json.loads(result_path.read_text()).get("status") == "completed"
            ):
                print(
                    json.dumps(
                        {"case": label, "result": "already observed; not repeated"}
                    ),
                    flush=True,
                )
                continue
            body = {
                "model": model,
                "store": False,
                "input": [
                    {
                        "type": "video",
                        "data": video,
                        "mime_type": "video/mp4",
                        "resolution": resolution,
                        "processing": {"type": "static", "fps": fps}
                        if mode == "static"
                        else "agentic",
                    },
                    {
                        "type": "text",
                        "text": "Describe each distinct background color and visible label in this silent video, with its approximate start time in seconds. Do not invent audio.",
                    },
                ],
                "generation_config": {"thinking_level": thinking},
                "response_format": {
                    "type": "object",
                    "properties": {
                        "events": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "start_seconds": {"type": "number"},
                                    "description": {"type": "string"},
                                },
                                "required": ["start_seconds", "description"],
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
                {
                    "x-goog-api-key": keys["GEMINI_API_KEY"],
                    "Content-Type": "application/json",
                },
                body,
            )
            safe = json.dumps(data)
            for key in keys.values():
                if key:
                    safe = safe.replace(key, "[REDACTED]")
            (destination / (label + ".json")).write_text(safe)
            data = json.loads(safe)
            print(
                json.dumps(
                    {
                        "case": label,
                        "fps": fps,
                        "http_status": status,
                        "status": data.get("status"),
                        "keys": list(data),
                        "error": data.get("error"),
                        "usage": data.get("usage"),
                    }
                ),
                flush=True,
            )
            if status >= 400:
                return
            time.sleep(20)


if __name__ == "__main__":
    main()

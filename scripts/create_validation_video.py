"""Create a six-second, silent local fixture with known transitions and labels."""

import argparse
import subprocess
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ffmpeg", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    command = [args.ffmpeg, "-hide_banner", "-loglevel", "error", "-n"]
    for color in ("red", "green", "blue"):
        command += ["-f", "lavfi", "-i", f"color=c={color}:s=640x360:r=24:d=2"]
    filters = (
        "[0:v]drawtext=text='RED 100':fontsize=44:fontcolor=white:x=180:y=150[r];"
        "[1:v]drawtext=text='GREEN 200':fontsize=44:fontcolor=white:x=160:y=150[g];"
        "[2:v]drawtext=text='BLUE 300':fontsize=44:fontcolor=white:x=170:y=150[b];"
        "[r][g][b]concat=n=3:v=1:a=0[out]"
    )
    command += [
        "-filter_complex",
        filters,
        "-map",
        "[out]",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(args.output),
    ]
    subprocess.run(command, check=True)


if __name__ == "__main__":
    main()

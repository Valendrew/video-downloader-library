# Video in. Useful context out.

<div class="vcp-intro" markdown>

Inspect a video, read what was said, or understand what happened on screen.
Use the Python components independently, or combine them in one asynchronous pipeline.

</div>

[Get started](install.md){ .md-button .md-button--primary }
[Make your first request](quickstart.md){ .md-button }
[Try the browser demo](demo.md){ .md-button }

## Pick the job you need

<div class="grid cards" markdown>

- **Download & inspect**

    Get formats, title, description, and duration. Choose a format and keep a local file.

    [Work with public videos →](components/downloads.md)

- **Transcribe speech**

    Send a public URL to Supadata. Receive readable text or segments with timing.

    [Build a transcript →](components/transcription.md)

- **Understand visuals**

    Send a local video to Gemini. Receive visible observations with your chosen timing policy.

    [Analyze a video →](components/visual.md)

- **Process local media**

    Measure a file, extract audio, convert it, or write a tagged copy with FFmpeg.

    [Use media tools →](components/media-tools.md)

</div>

## How the pieces fit

**Settings** describe how a service should run: credentials, timeouts, and processing
choices. A **request** selects the output you want. A **provider** performs the work
and returns a typed **output** containing data and its status.

The optional [pipeline](components/pipeline.md) coordinates providers for one public
video URL. It returns only after all requested stages succeed. Empty content is a
successful result; a provider failure raises an error.

## Supported inputs

URL components accept public HTTP(S) URLs on YouTube (`youtube.com`, `youtu.be`),
Instagram (`instagram.com`, `instagr.am`), and TikTok (`tiktok.com`), including their
subdomains. Local or internal URLs, embedded credentials, and other schemes are rejected.
Availability still depends on the source and provider; see [validation coverage](provider-validation.md).

Gemini and FFmpeg work with local files. A `MediaArtifact` records the path, media
type, duration when known, and ownership. Caller-owned files are preserved. Returned
library-owned media can be released with `cleanup()` or a context manager.

## Continue from here

Set up [service configuration](configuration.md), compare [providers](providers/index.md),
or look up [request fields and result shapes](schemas.md).

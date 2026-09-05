# Video Context Pipeline

Video Context Pipeline is a typed asynchronous Python library for four independent
jobs: inspect or download a supported public video, transcribe its public URL,
understand visible content in a local video artifact, and run selected jobs as one
pipeline.

A supported input URL is public `http` or `https` on YouTube (`youtube.com` or
`youtu.be`), Instagram (`instagram.com` or `instagr.am`), or TikTok (`tiktok.com`),
including subdomains. The pipeline rejects other hosts, local paths, credentials in
URLs, and non-HTTP schemes.

Choose a component by the data you have and the output you need:

| Input and desired output | Canonical component page |
| --- | --- |
| Public video URL → metadata or downloaded video/audio | [Download and metadata](components/downloads.md) |
| Public video URL → transcript text or timed segments | [Transcription](components/transcription.md) |
| Local video `MediaArtifact` → visible observations or events | [Visual understanding](components/visual.md) |
| Local media file → measured facts, extracted/converted audio, or tagged copy | [Local media tools](components/media-tools.md) |
| Public video URL → several requested outputs together | [Pipeline](components/pipeline.md) |

`MediaArtifact` describes a local file. An artifact returned by the downloader is
owned by the library and can be released with `cleanup()`; caller paths are not
deleted. A pipeline-only download used for visual analysis is an internal artifact
and is cleaned after successful visual processing. Request `media` when the caller
needs the downloaded artifact returned.

Start with [installation](install.md), then provide explicit settings through
[configuration](configuration.md). Read the recorded [provider-validation](provider-validation.md)
before relying on a provider combination in production.

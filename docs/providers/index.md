# Providers

Providers connect the library's typed requests to a service or tool. Install the
matching extra, supply settings, and call the provider directly or inject it into
`Pipeline`. You only need the providers for the outputs you request.

| Provider | Input | Output | Extra |
| --- | --- | --- | --- |
| [Supadata](supadata.md) | Public video URL | Transcript text or segments | `supadata` |
| [Gemini](gemini.md) | Local video artifact | Visual text or events | `gemini` |
| [yt-dlp](ytdlp.md) | Public video URL | Metadata, formats, downloaded media | `download` |

[FFmpeg media tools](../components/media-tools.md) are independent local operations,
with separately installed executables.

## Pick by workflow

For **transcription only**, use Supadata; downloading audio is unnecessary.
For **visual analysis of a local video**, use Gemini directly.
For **visual analysis of a public URL**, combine yt-dlp and Gemini through the pipeline.
For **metadata or downloads**, yt-dlp works by itself.

## Understand the boundary

Upstream providers offer more features than these adapters expose. Each provider page
links to the original documentation for deeper exploration and states the behavior
implemented here. Check [live validation coverage](../provider-validation.md) for the
specific combinations exercised by this project.

## Supply your own implementation

`Pipeline` accepts objects implementing the public `MetadataProvider`,
`TranscriptProvider`, `MediaProvider`, and `VisualProvider` protocols. Their methods are
asynchronous and return `ProviderOutput` values. See the
[request and output reference](../schemas.md) for the shared data contract.

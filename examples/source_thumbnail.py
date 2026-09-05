"""Download explicitly selected compatible audio and embed its source cover art."""

from pathlib import Path

from video_context_pipeline import MediaArtifact, MediaRequest
from video_context_pipeline.media import FFmpegMediaTools
from video_context_pipeline.providers.ytdlp import YtDlpMediaProvider


async def download_with_cover(
    url: str,
    *,
    provider: YtDlpMediaProvider,
    request: MediaRequest,
    tools: FFmpegMediaTools,
    destination: Path,
    title: str,
) -> MediaArtifact:
    """Use an inspected MP3/M4A audio format and a new matching destination suffix.

    Convert incompatible audio separately before enrichment. The returned artifact
    belongs to the caller; cleanup removes the newly created destination.
    """
    downloaded = await provider.download(url, request)
    with downloaded.data as audio:
        cover = await provider.download_thumbnail(url, request.settings)
        with cover.data as thumbnail:
            return await tools.enrich_metadata(
                audio,
                destination=destination,
                metadata={"title": title},
                thumbnail=thumbnail.path,
            )

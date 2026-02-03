"""
channel_video_meta.py
- YouTube 채널에서 최근 영상 ID 목록 가져오기
- 영상 메타데이터 추출
"""

import yt_dlp

try:
    from yt_dlp.utils import DownloadError, ExtractorError
except Exception:
    DownloadError = Exception
    ExtractorError = Exception


def get_recent_video_ids(channel_url: str, count: int = 50, mode: str = "regular") -> list[str]:
    """
    채널에서 최근 영상 ID 목록을 가져옵니다.

    Args:
        channel_url: YouTube 채널 URL
        count: 가져올 영상 개수
        mode: "regular" (롱폼) 또는 "shorts"

    Returns:
        영상 ID 리스트
    """
    if mode == "shorts":
        if "/shorts" not in channel_url:
            if channel_url.endswith("/"):
                channel_url = channel_url + "shorts"
            else:
                channel_url = channel_url + "/shorts"
    else:
        if "/videos" not in channel_url:
            if channel_url.endswith("/"):
                channel_url = channel_url + "videos"
            else:
                channel_url = channel_url + "/videos"

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "ignoreerrors": True,
        "playlistend": count,
    }

    video_ids = []

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(channel_url, download=False)

        if not info:
            return []

        entries = info.get("entries") or []

        for entry in entries:
            if entry and entry.get("id"):
                video_ids.append(entry["id"])
                if len(video_ids) >= count:
                    break

    return video_ids


def extract_metadata(video_id: str) -> dict:
    """
    영상 메타데이터를 추출합니다.

    Args:
        video_id: YouTube 영상 ID

    Returns:
        메타데이터 딕셔너리
    """
    video_url = f"https://www.youtube.com/watch?v={video_id}"

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "ignoreerrors": False,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_url, download=False)

        if not info:
            raise ValueError(f"Could not extract metadata for {video_id}")

        return {
            "id": info.get("id"),
            "title": info.get("title"),
            "description": info.get("description"),
            "view_count": info.get("view_count"),
            "like_count": info.get("like_count"),
            "comment_count": info.get("comment_count"),
            "upload_date": info.get("upload_date"),
            "duration": info.get("duration"),
            "channel": info.get("channel"),
            "channel_id": info.get("channel_id"),
            "thumbnail": info.get("thumbnail"),
            "thumbnails": info.get("thumbnails"),
            "tags": info.get("tags"),
            "categories": info.get("categories"),
        }

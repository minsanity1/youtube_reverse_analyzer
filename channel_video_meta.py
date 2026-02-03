#!/usr/bin/env python3
# channel_video_meta.py — fetch recent YouTube video metadata
from __future__ import annotations

"""
Updated 2025-06-19
──────────────────
• Added **--mode** flag with choices: all / regular / shorts  (v2)
• **NEW**: Each video now includes its full YouTube URL under the key ``url``.

Example usages:
    python channel_video_meta.py https://www.youtube.com/@OpenAI        # all uploads
    python channel_video_meta.py https://www.youtube.com/@OpenAI -m regular
    python channel_video_meta.py https://www.youtube.com/@OpenAI -m shorts -n 50 -o data.json
"""

import argparse
import json
import sys
import time
import traceback
import datetime as dt
from pathlib import Path
from typing import List, Dict, Any

from yt_dlp import YoutubeDL


# ────────────────────────────────────────────────────────────

def get_recent_video_ids(
    channel_url: str,
    count: int = 30,
    mode: str = "all",  # 'all' | 'regular' | 'shorts'
) -> List[str]:
    """Return the most recent **video IDs** from a YouTube channel.

    Parameters
    ----------
    channel_url : str
        Full channel URL or @handle.
    count : int, optional
        Maximum number of IDs to return (default 30).
    mode : str, optional
        Select which uploads to include:
            * "all"      → regular uploads **and** Shorts (default)
            * "regular"  → only regular uploads (no Shorts)
            * "shorts"   → only Shorts uploads
    """

    tabs: List[str] = []
    if mode in ("all", "regular"):
        tabs.append("videos")
    if mode in ("all", "shorts"):
        tabs.append("shorts")

    urls = [f"{channel_url}/{tab}" for tab in tabs]

    vids: List[str] = []
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": "in_playlist",
        "skip_download": True,
    }

    with YoutubeDL(ydl_opts) as ydl:
        for url in urls:
            info = ydl.extract_info(url, download=False)
            vids.extend(e["id"] for e in info.get("entries", []))

    # Deduplicate while preserving order (Python ≥3.7 maintains dict order)
    vids = list(dict.fromkeys(vids))
    return vids[:count]


# ────────────────────────────────────────────────────────────

def extract_metadata(video_id: str) -> Dict[str, Any]:
    """Extract lightweight metadata for a single YouTube video via **yt-dlp**."""

    ydl_opts = {"quiet": True, "no_warnings": True, "skip_download": True}
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(video_id, download=False)

    # Convert "YYYYMMDD" → "YYYY-MM-DD" if possible
    raw_date = info.get("upload_date")
    date_iso = (
        dt.datetime.strptime(raw_date, "%Y%m%d").strftime("%Y-%m-%d")
        if raw_date and raw_date.isdigit() and len(raw_date) == 8
        else None
    )

    return {
        "id": info["id"],
        "url": info.get("webpage_url") or f"https://www.youtube.com/watch?v={info['id']}",
        "title": info.get("title"),
        "uploader": info.get("uploader"),
        "upload_date": date_iso,
        "duration": info.get("duration"),  # seconds
        "view_count": info.get("view_count"),
        "comment_count": info.get("comment_count"),
        "description": info.get("description"),
    }


# ────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser("Channel recent videos → JSON")
    parser.add_argument("channel_url", help="YouTube channel URL or @handle")
    parser.add_argument(
        "-n", "--num", type=int, default=30,
        help="Number of videos to fetch (default 30)",
    )
    parser.add_argument(
        "-m", "--mode",
        choices=["all", "regular", "shorts"], default="all",
        help="Select uploads to include: all (default), regular, shorts",
    )
    parser.add_argument(
        "-o", "--out",
        help="Output filepath (writes to stdout if omitted)",
    )

    args = parser.parse_args()

    try:
        vids = get_recent_video_ids(args.channel_url, args.num, mode=args.mode)

        data: Dict[str, Any] = {
            "channel_url": args.channel_url,
            "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "mode": args.mode,
            "total": len(vids),
            "videos": [],
        }

        for i, vid in enumerate(vids, 1):
            print(f"[{i}/{len(vids)}] {vid}", file=sys.stderr)
            data["videos"].append(extract_metadata(vid))

        json_text = json.dumps(data, ensure_ascii=False, indent=2)
        if args.out:
            Path(args.out).write_text(json_text, encoding="utf-8")
            print(f"✅ saved → {args.out}", file=sys.stderr)
        else:
            print(json_text)

    except Exception as exc:
        traceback.print_exc()
        sys.exit(f"❌ Error: {exc}")


if __name__ == "__main__":
    main()

"""
download_thumbnails_gui.py
- PyQt6 GUI for downloading YouTube thumbnails and subtitles
- 채널의 최근 영상 N개를 가져와서
- 메타데이터 + 썸네일(선택) + 자막(선택)을 저장

필요:
  pip install PyQt6 requests yt-dlp
"""

import os
import re
import json
import time
import random
import sys
from datetime import datetime
from pathlib import Path

import requests
import yt_dlp
from channel_video_meta import get_recent_video_ids, extract_metadata

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QCheckBox,
    QPushButton, QProgressBar, QTextEdit, QGroupBox, QFileDialog,
    QMessageBox, QTabWidget, QFormLayout, QSplitter
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QTextCursor

try:
    from yt_dlp.utils import DownloadError, ExtractorError
except Exception:
    DownloadError = Exception
    ExtractorError = Exception


# ────────────────────────────────────────────────────────────────
# Helper Functions
# ────────────────────────────────────────────────────────────────

def is_membership_only_error(exc: Exception) -> bool:
    s = (str(exc) or "").lower()
    markers = [
        "members-only", "members only",
        "available to this channel's members",
        "join this channel to get access to members-only",
        "requires purchase", "paid content", "premium content", "rental",
        "멤버십", "멤버 전용", "채널 멤버십", "구매가 필요한 동영상",
    ]
    return any(m in s for m in markers)


def is_rate_limit_error(exc: Exception) -> bool:
    s = (str(exc) or "").lower()
    return "429" in s or "too many requests" in s


def sanitize_filename(name: str, max_len: int = 80) -> str:
    name = (name or "").strip()
    name = re.sub(r"[\\/:*?\"<>|]+", "_", name)
    name = re.sub(r"\s+", " ", name)
    return name[:max_len].strip() or "untitled"


def safe_ext_from_url(url: str, default="jpg") -> str:
    u = (url or "").split("?")[0].lower()
    m = re.search(r"\.(jpg|jpeg|png|webp)$", u)
    if m:
        ext = m.group(1)
        return "jpg" if ext == "jpeg" else ext
    return default


def ytimg_fallback_urls(video_id: str):
    return [
        f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg",
        f"https://i.ytimg.com/vi/{video_id}/maxresdefault.webp",
        f"https://i.ytimg.com/vi/{video_id}/sddefault.jpg",
        f"https://i.ytimg.com/vi/{video_id}/sddefault.webp",
        f"https://i.ytimg.com/vi/{video_id}/hq720.jpg",
        f"https://i.ytimg.com/vi/{video_id}/hq720.webp",
        f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
        f"https://i.ytimg.com/vi/{video_id}/hqdefault.webp",
        f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg",
        f"https://i.ytimg.com/vi/{video_id}/mqdefault.webp",
        f"https://i.ytimg.com/vi/{video_id}/default.jpg",
        f"https://i.ytimg.com/vi/{video_id}/default.webp",
    ]


def pick_best_thumbnail_url(meta: dict) -> str | None:
    thumbs = meta.get("thumbnails") or []
    best_url = None
    best_score = -1

    for t in thumbs:
        url = t.get("url")
        if not url:
            continue

        w = t.get("width") or 0
        h = t.get("height") or 0
        score = (w * h) if (w and h) else 0

        u = url.lower()
        if "maxres" in u:
            score += 10_000_000
        elif "sddefault" in u:
            score += 1_000_000
        elif "hq720" in u:
            score += 900_000
        elif "hqdefault" in u:
            score += 800_000

        if score > best_score:
            best_score = score
            best_url = url

    if best_url:
        return best_url
    if meta.get("thumbnail"):
        return meta["thumbnail"]
    return None


def format_upload_date(date_str: str | None) -> str | None:
    """YYYYMMDD -> YYYY-MM-DD"""
    if not date_str or len(date_str) != 8:
        return date_str
    return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"


# ────────────────────────────────────────────────────────────────
# Download Worker Thread
# ────────────────────────────────────────────────────────────────

class DownloadWorker(QThread):
    progress = pyqtSignal(int, int)  # current, total
    log = pyqtSignal(str)
    finished_signal = pyqtSignal(dict)

    def __init__(self, config: dict):
        super().__init__()
        self.config = config
        self._stop_requested = False

    def stop(self):
        self._stop_requested = True

    def download_image(self, url: str, out_path: Path) -> bool:
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
            "Referer": "https://www.youtube.com/",
        }

        try:
            with requests.get(url, stream=True, timeout=self.config["timeout_sec"], headers=headers) as r:
                if r.status_code != 200:
                    return False

                clen = r.headers.get("Content-Length")
                if clen and int(clen) < 5000:
                    return False

                out_path.parent.mkdir(parents=True, exist_ok=True)
                with open(out_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1024 * 256):
                        if chunk:
                            f.write(chunk)

            if out_path.stat().st_size < 5000:
                out_path.unlink(missing_ok=True)
                return False

            return True
        except Exception:
            return False

    def random_delay(self):
        delay = random.uniform(self.config["delay_min"], self.config["delay_max"])
        time.sleep(delay)

    def extract_transcript_text(self, video_id: str) -> dict:
        """자막 텍스트 추출"""
        ydl_opts = {
            "skip_download": True,
            "writesubtitles": True,
            "writeautomaticsub": self.config["include_auto_subs"],
            "subtitleslangs": [self.config["sub_lang"]],
            "subtitlesformat": "json3",
            "quiet": True,
            "no_warnings": True,
            "ignoreerrors": False,
            "sleep_interval": 1,
            "max_sleep_interval": 3,
            "sleep_interval_subtitles": 2,
        }

        video_url = f"https://www.youtube.com/watch?v={video_id}"

        for attempt in range(self.config["max_retries"]):
            if self._stop_requested:
                return {"ok": False, "transcript": None, "reason": "stopped"}

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(video_url, download=False)

                    transcript_text = None
                    subtitles = info.get("subtitles") or {}
                    auto_subs = info.get("automatic_captions") or {}

                    sub_data = None
                    is_auto = False
                    sub_lang = self.config["sub_lang"]

                    if sub_lang in subtitles:
                        sub_data = subtitles[sub_lang]
                    elif self.config["include_auto_subs"] and sub_lang in auto_subs:
                        sub_data = auto_subs[sub_lang]
                        is_auto = True

                    if sub_data:
                        json3_url = None
                        for fmt in sub_data:
                            if fmt.get("ext") == "json3":
                                json3_url = fmt.get("url")
                                break

                        if json3_url:
                            resp = requests.get(json3_url, timeout=30)
                            if resp.status_code == 200:
                                sub_json = resp.json()

                                texts = []
                                events = sub_json.get("events") or []
                                for event in events:
                                    segs = event.get("segs") or []
                                    for seg in segs:
                                        text = seg.get("utf8", "").strip()
                                        if text and text != "\n":
                                            texts.append(text)

                                transcript_text = " ".join(texts)
                                transcript_text = re.sub(r'\s+', ' ', transcript_text).strip()

                    if transcript_text:
                        return {"ok": True, "transcript": transcript_text, "is_auto": is_auto}
                    else:
                        return {"ok": False, "transcript": None, "reason": "no-subtitles-available"}

            except (DownloadError, ExtractorError) as e:
                if is_rate_limit_error(e) and self.config["retry_on_429"] and attempt < self.config["max_retries"] - 1:
                    self.log.emit(f"   429 에러, {self.config['retry_delay']}초 대기 후 재시도 ({attempt + 1}/{self.config['max_retries']})...")
                    time.sleep(self.config["retry_delay"])
                    continue
                if is_membership_only_error(e):
                    return {"ok": False, "transcript": None, "reason": "members-only"}
                return {"ok": False, "transcript": None, "reason": "download-error"}
            except Exception as e:
                return {"ok": False, "transcript": None, "reason": f"error: {str(e)}"}

        return {"ok": False, "transcript": None, "reason": "max-retries-exceeded"}

    def download_thumbnail(self, video_id: str, title: str, thumb_url: str | None) -> dict:
        """썸네일 다운로드"""
        title_safe = sanitize_filename(title or "", max_len=80)
        out_dir = self.config["out_dir"]
        skip_exists = self.config["skip_exists"]

        def make_thumb_path(url: str) -> Path:
            ext = safe_ext_from_url(url, default="jpg")
            base = f"{video_id}__{title_safe}" if title_safe else video_id
            return Path(out_dir) / f"{base}.{ext}"

        if thumb_url:
            out_path = make_thumb_path(thumb_url)
            if skip_exists and out_path.exists() and out_path.stat().st_size > 5000:
                return {"ok": True, "path": str(out_path), "cached": True}
            if self.download_image(thumb_url, out_path):
                return {"ok": True, "path": str(out_path), "cached": False}

        for url in ytimg_fallback_urls(video_id):
            if self._stop_requested:
                return {"ok": False, "path": None, "cached": False}
            out_path = make_thumb_path(url)
            if skip_exists and out_path.exists() and out_path.stat().st_size > 5000:
                return {"ok": True, "path": str(out_path), "cached": True}
            if self.download_image(url, out_path):
                return {"ok": True, "path": str(out_path), "cached": False}

        return {"ok": False, "path": None, "cached": False}

    def process_video(self, video_id: str) -> dict:
        """영상 메타데이터 추출 + (선택) 썸네일 다운로드 + (선택) 자막 추출"""
        download_thumbs = self.config["download_thumbs"]
        download_subs = self.config["download_subs"]
        data_dir = self.config["data_dir"]
        skip_exists = self.config["skip_exists"]

        if download_subs:
            json_path = Path(data_dir) / f"{video_id}.json"
            if skip_exists and json_path.exists():
                try:
                    with open(json_path, "r", encoding="utf-8") as f:
                        existing = json.load(f)
                        return {"cached": True, "data": existing}
                except:
                    pass

        try:
            meta = extract_metadata(video_id)
        except (DownloadError, ExtractorError) as e:
            reason = "members-only" if is_membership_only_error(e) else "metadata-error"
            return {"error": True, "reason": reason}

        title = meta.get("title")
        thumb_url = pick_best_thumbnail_url(meta)

        thumb_result = {"ok": False, "path": None, "cached": False}
        if download_thumbs:
            thumb_result = self.download_thumbnail(video_id, title, thumb_url)

        if download_subs:
            result = {
                "id": video_id,
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "title": title,
                "view_count": meta.get("view_count"),
                "upload_date": format_upload_date(meta.get("upload_date")),
                "duration": meta.get("duration"),
                "thumbnail_url": thumb_url,
                "thumbnail_local_path": thumb_result.get("path") if download_thumbs else None,
                "transcript": None,
            }

            sub_result = self.extract_transcript_text(video_id)
            if sub_result.get("ok"):
                result["transcript"] = sub_result["transcript"]

            Path(data_dir).mkdir(parents=True, exist_ok=True)
            json_path = Path(data_dir) / f"{video_id}.json"
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
        else:
            result = {
                "id": video_id,
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "title": title,
                "view_count": meta.get("view_count"),
                "upload_date": format_upload_date(meta.get("upload_date")),
            }

        return {
            "cached": False,
            "data": result,
            "thumb_ok": thumb_result.get("ok", False),
            "thumb_cached": thumb_result.get("cached", False),
            "has_transcript": result.get("transcript") is not None if download_subs else False,
        }

    def run(self):
        channel_url = self.config["channel_url"]
        num_videos = self.config["num_videos"]
        mode = self.config["mode"]
        download_thumbs = self.config["download_thumbs"]
        download_subs = self.config["download_subs"]
        out_dir = self.config["out_dir"]
        data_dir = self.config["data_dir"]
        manifest = self.config["manifest"]

        if download_thumbs:
            Path(out_dir).mkdir(parents=True, exist_ok=True)
        if download_subs:
            Path(data_dir).mkdir(parents=True, exist_ok=True)

        self.log.emit(f"채널에서 영상 목록 가져오는 중...")

        try:
            video_ids = get_recent_video_ids(channel_url, count=num_videos, mode=mode)
        except Exception as e:
            self.log.emit(f"오류: 영상 목록을 가져올 수 없습니다. {str(e)}")
            self.finished_signal.emit({"error": str(e)})
            return

        self.log.emit(f"총 {len(video_ids)}개 영상 발견")
        self.log.emit(f"옵션: 썸네일={'O' if download_thumbs else 'X'}, 자막={'O' if download_subs else 'X'}")

        all_data = []
        skipped = []
        ok_count = 0
        cached_count = 0
        thumb_count = 0
        transcript_count = 0

        for i, vid in enumerate(video_ids, start=1):
            if self._stop_requested:
                self.log.emit("중지됨")
                break

            self.progress.emit(i, len(video_ids))
            result = self.process_video(vid)

            if result.get("error"):
                self.log.emit(f"[{i}/{len(video_ids)}] FAIL: {vid} ({result.get('reason')})")
                skipped.append({"id": vid, "reason": result.get("reason")})
                continue

            data = result["data"]
            all_data.append(data)
            ok_count += 1

            if result.get("cached"):
                cached_count += 1
                status_parts = [f"CACHED: {vid}"]
                if download_thumbs and data.get("thumbnail_local_path"):
                    thumb_count += 1
                if data.get("transcript"):
                    transcript_count += 1
                    status_parts.append("자막: O")
                else:
                    status_parts.append("자막: X")
                self.log.emit(f"[{i}/{len(video_ids)}] {' | '.join(status_parts)}")
            else:
                status_parts = [f"OK: {vid}"]

                if download_thumbs:
                    if result.get("thumb_ok"):
                        thumb_count += 1
                        if result.get("thumb_cached"):
                            status_parts.append("썸네일: cached")
                        else:
                            status_parts.append("썸네일: O")
                    else:
                        status_parts.append("썸네일: X")

                if download_subs:
                    if result.get("has_transcript"):
                        transcript_count += 1
                        status_parts.append("자막: O")
                    else:
                        status_parts.append("자막: X")
                    self.random_delay()

                self.log.emit(f"[{i}/{len(video_ids)}] {' | '.join(status_parts)}")

        self.log.emit("")
        self.log.emit("=" * 50)
        self.log.emit(f"완료: {ok_count}/{len(video_ids)}")
        if download_subs:
            self.log.emit(f"캐시됨: {cached_count}")
        if download_thumbs:
            self.log.emit(f"썸네일: {thumb_count}/{ok_count}")
        if download_subs:
            self.log.emit(f"자막: {transcript_count}/{ok_count}")
            self.log.emit(f"데이터 폴더: {data_dir}/")

        if not download_subs:
            channel_name = channel_url.split("@")[-1] if "@" in channel_url else channel_url

            manifest_data = {
                "channel": f"www.youtube.com/@{channel_name}",
                "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "mode": mode,
                "total": ok_count,
                "videos": all_data,
                "skipped": skipped,
            }

            with open(manifest, "w", encoding="utf-8") as f:
                json.dump(manifest_data, f, ensure_ascii=False, indent=2)
            self.log.emit(f"저장됨: {manifest}")

        self.finished_signal.emit({
            "ok_count": ok_count,
            "total": len(video_ids),
            "thumb_count": thumb_count,
            "transcript_count": transcript_count,
            "cached_count": cached_count,
        })


# ────────────────────────────────────────────────────────────────
# Main Window
# ────────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.worker = None
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("YouTube Thumbnail & Subtitle Downloader")
        self.setMinimumSize(700, 600)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        # Tab widget
        tabs = QTabWidget()
        main_layout.addWidget(tabs)

        # ─── 기본 설정 탭 ───
        basic_tab = QWidget()
        basic_layout = QVBoxLayout(basic_tab)

        # 채널 URL
        url_group = QGroupBox("채널 설정")
        url_layout = QFormLayout(url_group)

        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://www.youtube.com/@채널명")
        url_layout.addRow("채널 URL:", self.url_input)

        self.num_videos_spin = QSpinBox()
        self.num_videos_spin.setRange(1, 1000)
        self.num_videos_spin.setValue(100)
        url_layout.addRow("영상 개수:", self.num_videos_spin)

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["regular", "shorts"])
        url_layout.addRow("모드:", self.mode_combo)

        basic_layout.addWidget(url_group)

        # 다운로드 옵션
        dl_group = QGroupBox("다운로드 옵션")
        dl_layout = QVBoxLayout(dl_group)

        self.thumbs_check = QCheckBox("썸네일 다운로드")
        self.thumbs_check.setChecked(False)
        dl_layout.addWidget(self.thumbs_check)

        self.subs_check = QCheckBox("자막 다운로드")
        self.subs_check.setChecked(True)
        dl_layout.addWidget(self.subs_check)

        self.skip_exists_check = QCheckBox("이미 존재하는 파일 건너뛰기")
        self.skip_exists_check.setChecked(True)
        dl_layout.addWidget(self.skip_exists_check)

        basic_layout.addWidget(dl_group)

        # 폴더 설정
        folder_group = QGroupBox("폴더/파일 설정")
        folder_layout = QFormLayout(folder_group)

        self.out_dir_input = QLineEdit("thumbnails")
        out_dir_row = QHBoxLayout()
        out_dir_row.addWidget(self.out_dir_input)
        out_dir_btn = QPushButton("...")
        out_dir_btn.setMaximumWidth(30)
        out_dir_btn.clicked.connect(lambda: self.browse_folder(self.out_dir_input))
        out_dir_row.addWidget(out_dir_btn)
        folder_layout.addRow("썸네일 폴더:", out_dir_row)

        self.data_dir_input = QLineEdit("data")
        data_dir_row = QHBoxLayout()
        data_dir_row.addWidget(self.data_dir_input)
        data_dir_btn = QPushButton("...")
        data_dir_btn.setMaximumWidth(30)
        data_dir_btn.clicked.connect(lambda: self.browse_folder(self.data_dir_input))
        data_dir_row.addWidget(data_dir_btn)
        folder_layout.addRow("데이터 폴더:", data_dir_row)

        self.manifest_input = QLineEdit("manifest.json")
        folder_layout.addRow("매니페스트 파일:", self.manifest_input)

        basic_layout.addWidget(folder_group)
        basic_layout.addStretch()

        tabs.addTab(basic_tab, "기본 설정")

        # ─── 고급 설정 탭 ───
        advanced_tab = QWidget()
        advanced_layout = QVBoxLayout(advanced_tab)

        # 자막 설정
        sub_group = QGroupBox("자막 설정")
        sub_layout = QFormLayout(sub_group)

        self.sub_lang_input = QLineEdit("ko")
        sub_layout.addRow("자막 언어:", self.sub_lang_input)

        self.auto_subs_check = QCheckBox("자동 생성 자막 포함")
        self.auto_subs_check.setChecked(True)
        sub_layout.addRow("", self.auto_subs_check)

        advanced_layout.addWidget(sub_group)

        # Rate limit 설정
        rate_group = QGroupBox("Rate Limit 설정")
        rate_layout = QFormLayout(rate_group)

        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(5, 120)
        self.timeout_spin.setValue(20)
        rate_layout.addRow("타임아웃 (초):", self.timeout_spin)

        self.delay_min_spin = QDoubleSpinBox()
        self.delay_min_spin.setRange(0, 60)
        self.delay_min_spin.setValue(3.0)
        self.delay_min_spin.setSingleStep(0.5)
        rate_layout.addRow("최소 딜레이 (초):", self.delay_min_spin)

        self.delay_max_spin = QDoubleSpinBox()
        self.delay_max_spin.setRange(0, 120)
        self.delay_max_spin.setValue(6.0)
        self.delay_max_spin.setSingleStep(0.5)
        rate_layout.addRow("최대 딜레이 (초):", self.delay_max_spin)

        self.retry_429_check = QCheckBox("429 에러 시 재시도")
        self.retry_429_check.setChecked(True)
        rate_layout.addRow("", self.retry_429_check)

        self.retry_delay_spin = QSpinBox()
        self.retry_delay_spin.setRange(1, 300)
        self.retry_delay_spin.setValue(30)
        rate_layout.addRow("재시도 대기 (초):", self.retry_delay_spin)

        self.max_retries_spin = QSpinBox()
        self.max_retries_spin.setRange(1, 10)
        self.max_retries_spin.setValue(3)
        rate_layout.addRow("최대 재시도 횟수:", self.max_retries_spin)

        advanced_layout.addWidget(rate_group)
        advanced_layout.addStretch()

        tabs.addTab(advanced_tab, "고급 설정")

        # ─── 진행 상황 ───
        progress_group = QGroupBox("진행 상황")
        progress_layout = QVBoxLayout(progress_group)

        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        progress_layout.addWidget(self.progress_bar)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 9))
        progress_layout.addWidget(self.log_text)

        main_layout.addWidget(progress_group)

        # ─── 버튼 ───
        btn_layout = QHBoxLayout()

        self.start_btn = QPushButton("시작")
        self.start_btn.setMinimumHeight(40)
        self.start_btn.clicked.connect(self.start_download)
        btn_layout.addWidget(self.start_btn)

        self.stop_btn = QPushButton("중지")
        self.stop_btn.setMinimumHeight(40)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_download)
        btn_layout.addWidget(self.stop_btn)

        main_layout.addLayout(btn_layout)

    def browse_folder(self, line_edit: QLineEdit):
        folder = QFileDialog.getExistingDirectory(self, "폴더 선택")
        if folder:
            line_edit.setText(folder)

    def get_config(self) -> dict:
        return {
            "channel_url": self.url_input.text().strip(),
            "num_videos": self.num_videos_spin.value(),
            "mode": self.mode_combo.currentText(),
            "timeout_sec": self.timeout_spin.value(),
            "skip_exists": self.skip_exists_check.isChecked(),
            "download_thumbs": self.thumbs_check.isChecked(),
            "download_subs": self.subs_check.isChecked(),
            "out_dir": self.out_dir_input.text().strip() or "thumbnails",
            "data_dir": self.data_dir_input.text().strip() or "data",
            "manifest": self.manifest_input.text().strip() or "manifest.json",
            "sub_lang": self.sub_lang_input.text().strip() or "ko",
            "include_auto_subs": self.auto_subs_check.isChecked(),
            "delay_min": self.delay_min_spin.value(),
            "delay_max": self.delay_max_spin.value(),
            "retry_on_429": self.retry_429_check.isChecked(),
            "retry_delay": self.retry_delay_spin.value(),
            "max_retries": self.max_retries_spin.value(),
        }

    def start_download(self):
        config = self.get_config()

        if not config["channel_url"]:
            QMessageBox.warning(self, "경고", "채널 URL을 입력하세요.")
            return

        if not config["download_thumbs"] and not config["download_subs"]:
            QMessageBox.warning(self, "경고", "썸네일 또는 자막 중 하나 이상을 선택하세요.")
            return

        self.log_text.clear()
        self.progress_bar.setValue(0)
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)

        self.worker = DownloadWorker(config)
        self.worker.progress.connect(self.on_progress)
        self.worker.log.connect(self.on_log)
        self.worker.finished_signal.connect(self.on_finished)
        self.worker.start()

    def stop_download(self):
        if self.worker:
            self.worker.stop()
            self.stop_btn.setEnabled(False)

    def on_progress(self, current: int, total: int):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.progress_bar.setFormat(f"{current}/{total}")

    def on_log(self, msg: str):
        self.log_text.append(msg)
        self.log_text.moveCursor(QTextCursor.MoveOperation.End)

    def on_finished(self, result: dict):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)

        if "error" in result:
            QMessageBox.critical(self, "오류", f"다운로드 실패: {result['error']}")
        else:
            QMessageBox.information(
                self, "완료",
                f"다운로드 완료!\n\n"
                f"성공: {result.get('ok_count', 0)}/{result.get('total', 0)}\n"
                f"썸네일: {result.get('thumb_count', 0)}\n"
                f"자막: {result.get('transcript_count', 0)}"
            )


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

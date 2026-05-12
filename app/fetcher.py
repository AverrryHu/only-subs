"""
YouTube 频道抓取
"""
import subprocess
import json
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional


class YouTubeFetcher:
    def __init__(self):
        pass

    def _run_yt_dlp(self, args: List[str]) -> str:
        cmd = ["yt-dlp", "--no-warnings", "--no-download"] + args
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )
            return result.stdout
        except subprocess.TimeoutExpired:
            print("yt-dlp timed out")
            return ""
        except Exception as e:
            print(f"yt-dlp error: {e}")
            return ""

    def _parse_date(self, date_str: str) -> str:
        """解析日期格式"""
        if not date_str:
            return ""
        try:
            if len(date_str) == 8:  # YYYYMMDD
                dt = datetime.strptime(date_str, "%Y%m%d")
                return dt.strftime("%Y-%m-%d")
        except:
            pass
        return date_str

    def get_channel_info(self, channel_url: str) -> Dict:
        """获取频道信息"""
        args = [
            "--dump-json",
            "--playlist-end", "1",
            channel_url
        ]
        try:
            output = self._run_yt_dlp(args)
            if not output.strip():
                return {"channel_id": "", "channel_name": "未知频道", "channel_url": channel_url}
            data = json.loads(output.strip().split('\n')[0])
            channel_id = data.get("channel_id", "")
            channel_name = data.get("channel", data.get("uploader", ""))
            if not channel_id:
                # 尝试从URL提取
                if "@" in channel_url:
                    channel_id = channel_url.split("@")[-1].split("/")[0]
                else:
                    channel_id = channel_url
            return {
                "channel_id": channel_id,
                "channel_name": channel_name,
                "channel_url": channel_url
            }
        except Exception as e:
            return {"channel_id": "", "channel_name": "未知频道", "channel_url": channel_url}

    def get_latest_videos(self, channel_url: str, days: int = 60) -> List[Dict]:
        """获取频道近days天的视频 - 简化为获取最新5个"""
        args = [
            "--dump-json",
            "--playlist-end", "10",
            "--no-download",
            channel_url
        ]
        try:
            output = self._run_yt_dlp(args)
            if not output.strip():
                return []

            results = []
            for line in output.strip().split('\n'):
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    results.append({
                        "video_id": data.get("id", ""),
                        "title": data.get("title", ""),
                        "url": data.get("webpage_url", ""),
                        "thumbnail": data.get("thumbnail"),
                        "published_at": self._parse_date(data.get("upload_date")),
                        "duration": data.get("duration")
                    })
                except:
                    continue

            return results
        except Exception as e:
            print(f"Error getting videos: {e}")
            return []

    def get_latest_video(self, channel_url: str) -> Optional[Dict]:
        """Get latest video from a channel (兼容旧接口)"""
        videos = self.get_latest_videos(channel_url, days=30)
        return videos[0] if videos else None

    def get_subtitles(self, video_url: str) -> Optional[str]:
        """Get subtitles for a video"""
        video_id = None
        if "v=" in video_url:
            video_id = video_url.split("v=")[-1].split("&")[0]
        elif "youtu.be/" in video_url:
            video_id = video_url.split("youtu.be/")[-1].split("?")[0]

        if not video_id:
            return None

        try:
            return self._get_subtitles_api(video_id)
        except Exception as e:
            print(f"Error getting subtitles: {e}")
            return None

    def _get_subtitles_api(self, video_id: str) -> Optional[str]:
        """使用YouTube API获取字幕"""
        import requests

        # 优先英文自动字幕
        url = f"https://subtitle.jadejk.com/api/subtitle/{video_id}"
        try:
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                # 找英文字幕
                for sub in data.get("subtitles", []):
                    if sub.get("lang_code", "").startswith("en"):
                        return sub.get("data", "")
                # 没有就返回第一个
                if data.get("subtitles"):
                    return data["subtitles"][0].get("data", "")
        except:
            pass
        return None


# 全局实例
_yt_fetcher: Optional[YouTubeFetcher] = None

def get_yt_fetcher() -> YouTubeFetcher:
    global _yt_fetcher
    if _yt_fetcher is None:
        _yt_fetcher = YouTubeFetcher()
    return _yt_fetcher
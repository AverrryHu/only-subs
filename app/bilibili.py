import json
import re
import subprocess
from datetime import datetime
from typing import Optional, Dict
from bilibili_api import video, Credential

_cached_credential = None

def get_credential(user_id: str = None):
    global _cached_credential
    if user_id:
        from .supabase_client import get_user_settings
        settings = get_user_settings(user_id)
        if settings and settings.get('sessdata'):
            import urllib.parse
            sessdata = urllib.parse.unquote(settings.get('sessdata'))
            _cached_credential = Credential(
                sessdata=sessdata,
                bili_jct=settings.get('bili_jct'),
                buvid3=settings.get('buvid3')
            )
    return _cached_credential


class BilibiliFetcher:
    def __init__(self):
        pass

    def _extract_uid(self, url: str) -> Optional[str]:
        match = re.search(r'bilibili\.com/(\d+)', url)
        return match.group(1) if match else None

    def _extract_bvid(self, url: str) -> Optional[str]:
        match = re.search(r'BV\w+', url)
        return match.group(0) if match else None

    def _run_yt_dlp(self, url: str) -> Optional[Dict]:
        cmd = [
            "yt-dlp", "--no-download", "--playlist-end", "1", "--dump-json", url
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0 and result.stdout.strip():
                # 解析多行JSON，取最后一个（最新）
                lines = result.stdout.strip().split('\n')
                for line in reversed(lines):
                    line = line.strip()
                    if line and line.startswith('{'):
                        return json.loads(line)
        except Exception as e:
            print(f"yt-dlp error: {e}")
        return None

    def _get_space_name(self, uid: str) -> Optional[str]:
        """从B站用户空间页面获取用户名"""
        import requests
        import urllib.parse
        import re

        url = f"https://space.bilibili.com/{uid}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://www.bilibili.com/",
        }
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code != 200:
                return None

            text = resp.text

            # 从page title提取用户名，格式通常是 "用户名 的个人空间"
            title_match = re.search(r'<title>([^<]+)</title>', text, re.IGNORECASE)
            if title_match:
                title = title_match.group(1)
                # 格式: "用户名 的个人空间-bishi个人主页-哔哩哔哩视频"
                if "的个人空间" in title:
                    return title.split("的个人空间")[0].strip()
                # 其他格式
                if "-b站" in title or "-哔哩" in title:
                    return title.split("-")[0].strip()

        except Exception as e:
            print(f"Space fetch error: {e}")
        return None

    def get_channel_info(self, channel_url: str, user_id: str = None) -> Dict:
        uid = self._extract_uid(channel_url)
        if not uid:
            raise Exception("Invalid Bilibili URL")

        # 优先尝试从视频获取UP主名称
        video_data = self.get_latest_video(channel_url, user_id)
        if video_data:
            uploader = video_data.get('uploader')
            if uploader:
                return {
                    "channel_id": f"bilibili_{uid}",
                    "channel_name": uploader,
                    "channel_url": channel_url
                }

        # 备选：从空间页面获取名称
        name = self._get_space_name(uid)
        if name:
            return {
                "channel_id": f"bilibili_{uid}",
                "channel_name": name,
                "channel_url": channel_url
            }

        return {"channel_id": f"bilibili_{uid}", "channel_name": f"UP{uid}", "channel_url": channel_url}

    def get_latest_video(self, channel_url: str, user_id: str = None) -> Optional[Dict]:
        uid = self._extract_uid(channel_url)
        if not uid:
            return None

        # 用yt-dlp获取频道最新视频
        data = self._run_yt_dlp(f"https://space.bilibili.com/{uid}/video")
        if data:
            video_id = data.get('id', '')
            if video_id:
                # duration可能是float，转为int
                duration = data.get('duration')
                if duration:
                    duration = int(duration) if isinstance(duration, int) else int(float(duration))
                else:
                    duration = 0
                return {
                    "video_id": video_id.upper().replace('BV', 'BV') if video_id.upper().startswith('BV') else video_id,
                    "title": data.get('title'),
                    "url": data.get('webpage_url'),
                    "thumbnail": data.get('thumbnail'),
                    "published_at": self._parse_date(data.get('upload_date')),
                    "duration": duration,
                    "uploader": data.get('uploader')
                }
        return None

    def _parse_date(self, date_str) -> Optional[datetime]:
        if not date_str:
            return None
        try:
            return datetime.strptime(str(date_str), "%Y%m%d")
        except:
            return None

    def get_video_info(self, video_url: str, user_id: str = None) -> Optional[Dict]:
        bvid = self._extract_bvid(video_url)
        if not bvid:
            return None

        data = self._run_yt_dlp(video_url)
        if data:
            duration = data.get('duration')
            if duration:
                duration = int(duration) if isinstance(duration, int) else int(float(duration))
            else:
                duration = 0
            # 清理description中的HTML标签
            description = data.get('description', '') or ''
            if description:
                description = re.sub(r'<[^>]+>', '', description)[:500]
            return {
                "video_id": bvid,
                "title": data.get('title'),
                "url": video_url,
                "thumbnail": data.get('thumbnail'),
                "published_at": self._parse_date(data.get('upload_date')),
                "duration": duration,
                "description": description
            }
        return None

    def get_subtitles(self, video_url: str, user_id: str = None) -> Optional[str]:
        bvid = self._extract_bvid(video_url)
        if not bvid:
            return None

        cred = get_credential(user_id)
        if not cred:
            return None

        import asyncio
        loop = asyncio.new_event_loop()
        try:
            v = video.Video(bvid=bvid, credential=cred)
            info = loop.run_until_complete(v.get_info())
            cid = info['pages'][0]['cid']
            sub_list = loop.run_until_complete(v.get_subtitle(cid=cid))
            subtitles = sub_list.get('subtitles', [])

            if subtitles:
                for s in subtitles:
                    if s.get('lan') == 'ai-zh':
                        sub_info = s
                        break
                else:
                    sub_info = subtitles[0] if subtitles else None

                if sub_info:
                    sub_url = sub_info.get('subtitle_url')
                    if sub_url:
                        import requests
                        full_url = f"https:{sub_url}" if sub_url.startswith('//') else sub_url
                        resp = requests.get(full_url)
                        if resp.status_code == 200:
                            data = resp.json()
                            body = data.get('body', [])
                            if body:
                                lines = []
                                for item in body:
                                    from_t = item.get('from', 0)
                                    to_t = item.get('to', 0)
                                    content = item.get('content', '')
                                    start = self._format_time(from_t)
                                    end = self._format_time(to_t)
                                    lines.append(f"{start} --> {end}\n{content}")
                                return '\n\n'.join(lines)

            dynamic = info.get('dynamic', '')
            if dynamic:
                return f"[视频描述]\n{dynamic}"
        except Exception as e:
            print(f"Error getting subtitles: {e}")
        finally:
            loop.close()
        return None

    def _format_time(self, seconds: float) -> str:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"
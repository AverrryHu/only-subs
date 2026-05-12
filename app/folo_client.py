"""
Folo API 客户端 - 获取B站视频订阅
"""
import os
import requests
from typing import Optional, List, Dict, Tuple

FOLO_API_URL = "https://api.folo.is"


class FoloClient:
    def __init__(self, token: str):
        self.token = token
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

    def add_bilibili_subscription(self, uid: str) -> Tuple[bool, str]:
        """添加B站用户视频订阅"""
        url = f"https://rsshub.app/bilibili/user/video/{uid}"

        try:
            # 调用 Folo 添加订阅
            resp = requests.post(
                f"{FOLO_API_URL}/subscriptions",
                headers=self.headers,
                json={"url": url},
                timeout=30
            )
            if resp.status_code in (200, 201):
                return True, "订阅成功"
            elif resp.status_code == 409:
                return True, "已订阅"
            else:
                return False, f"订阅失败: {resp.status_code}"
        except Exception as e:
            return False, f"订阅失败: {str(e)}"

    def get_timeline(self, feed_url: str = None, limit: int = 20) -> List[Dict]:
        """获取timeline视频列表"""
        url = f"{FOLO_API_URL}/timeline"
        params = {"limit": limit}
        if feed_url:
            params["feed"] = feed_url

        resp = requests.get(url, headers=self.headers, params=params, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("entries", [])
        elif resp.status_code == 401:
            raise Exception("Token无效，请重新登录Folo")
        else:
            raise Exception(f"Folo API错误: {resp.status_code}")

    def get_bilibili_videos(self, uid: str, limit: int = 10) -> List[Dict]:
        """获取指定B站用户的最新视频"""
        feed_url = f"https://rsshub.app/bilibili/user/video/{uid}"

        try:
            entries = self.get_timeline(feed_url=feed_url, limit=limit)
            videos = []
            for entry in entries:
                video_url = entry.get("url", "")
                if "bilibili.com/video/" in video_url:
                    # 提取BV号
                    import re
                    bvid_match = re.search(r'BV\w+', video_url)
                    bvid = bvid_match.group(0) if bvid_match else ""

                    videos.append({
                        "video_id": bvid,
                        "title": entry.get("title", ""),
                        "url": video_url,
                        "thumbnail": entry.get("thumbnail") or entry.get("enclosure"),
                        "published_at": entry.get("published"),
                        "author": entry.get("author", ""),
                        "entry_id": entry.get("id")
                    })
            return videos
        except Exception as e:
            print(f"获取视频失败: {e}")
            return []

    def get_all_bilibili_videos(self, limit: int = 50) -> List[Dict]:
        """获取所有B站订阅的最新视频"""
        try:
            entries = self.get_timeline(limit=limit)
            videos = []
            for entry in entries:
                video_url = entry.get("url", "")
                if "bilibili.com/video/" in video_url:
                    import re
                    bvid_match = re.search(r'BV\w+', video_url)
                    bvid = bvid_match.group(0) if bvid_match else ""

                    videos.append({
                        "video_id": bvid,
                        "title": entry.get("title", ""),
                        "url": video_url,
                        "thumbnail": entry.get("thumbnail") or entry.get("enclosure"),
                        "published_at": entry.get("published"),
                        "author": entry.get("author", ""),
                        "entry_id": entry.get("id")
                    })
            return videos
        except Exception as e:
            print(f"获取视频失败: {e}")
            return []
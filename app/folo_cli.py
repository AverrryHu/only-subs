"""
Folo CLI 客户端 - 使用CLI方式获取数据
"""
import subprocess
import json
import os
from typing import List, Dict

# 找到npx路径
def find_npx():
    """查找npx路径"""
    paths = [
        "/Users/hushizhe/.nvm/versions/node/v20.20.0/bin/npx",
        "/Users/hushizhe/.nvm/current/bin/npx",
        "/usr/local/bin/npx",
        "/opt/homebrew/bin/npx"
    ]
    for p in paths:
        if os.path.exists(p):
            return p
    return "npx"  # fallback

NPX_PATH = find_npx()

# 添加PATH环境变量
def get_env():
    env = os.environ.copy()
    node_path = "/Users/hushizhe/.nvm/versions/node/v20.20.0/bin"
    if node_path not in env.get("PATH", ""):
        env["PATH"] = node_path + ":" + env.get("PATH", "")
    return env


class FoloClient:
    def __init__(self, token: str):
        self.token = token
        self._use_cli = True

    def add_bilibili_subscription(self, uid: str) -> tuple:
        """添加B站用户视频订阅"""
        feed_url = f"https://rsshub.app/bilibili/user/video/{uid}"

        try:
            result = subprocess.run(
                [NPX_PATH, "--yes", "folocli@latest", "subscription", "add", "--feed", feed_url],
                capture_output=True,
                text=True,
                timeout=60,
                env=get_env()
            )

            output = result.stdout
            try:
                data = json.loads(output)
                if data.get("ok"):
                    return True, "订阅成功"
                else:
                    error = data.get("error", {})
                    return False, f"订阅失败: {error.get('message', 'Unknown')}"
            except:
                return False, f"订阅失败: {output}"
        except Exception as e:
            return False, f"订阅失败: {str(e)}"

    def get_all_bilibili_videos(self, limit: int = 20) -> List[Dict]:
        """获取所有B站订阅的最新视频"""
        try:
            result = subprocess.run(
                [NPX_PATH, "--yes", "folocli@latest", "timeline", "--limit", str(limit)],
                capture_output=True,
                text=True,
                timeout=60,
                env=get_env()
            )

            output = result.stdout
            try:
                data = json.loads(output)
                if data.get("ok"):
                    entries = data.get("data", {}).get("entries", [])
                    return self._parse_video_entries(entries)
            except Exception as e:
                print(f"Parse error: {e}")
                return []
        except Exception as e:
            print(f"Get videos error: {e}")
            return []

    def get_bilibili_videos(self, uid: str, limit: int = 10) -> List[Dict]:
        """获取指定B站用户的最新视频"""
        # 先添加订阅
        self.add_bilibili_subscription(uid)

        # 获取timeline，然后过滤
        all_videos = self.get_all_bilibili_videos(limit=limit + 20)

        # 过滤出该用户的视频
        user_videos = [v for v in all_videos if uid in v.get("url", "")]
        return user_videos[:limit]

    def _parse_video_entries(self, entries: List) -> List[Dict]:
        """解析视频条目"""
        videos = []
        import re

        for entry in entries:
            # 处理嵌套结构
            if isinstance(entry, dict) and "entries" in entry:
                inner_entries = entry.get("entries", {})
                # entries可能是dict或list
                if isinstance(inner_entries, dict):
                    inner_entries = inner_entries.values()
                if isinstance(inner_entries, list):
                    for inner in inner_entries:
                        if isinstance(inner, dict):
                            videos.extend(self._parse_single_entry(inner))
                continue

            videos.extend(self._parse_single_entry(entry))

        # 只保留B站视频
        bilibili_videos = [v for v in videos if "bilibili.com/video/" in v.get("url", "")]
        return bilibili_videos

    def _parse_single_entry(self, entry: Dict) -> List[Dict]:
        """解析单个条目"""
        videos = []
        if not isinstance(entry, dict):
            return videos

        video_url = entry.get("url", "")
        if "bilibili.com/video/" in video_url:
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
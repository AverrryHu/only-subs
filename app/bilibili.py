# B站功能暂时禁用
from typing import Optional, Dict

class BilibiliFetcher:
    def __init__(self):
        pass

    async def get_latest_videos(self, channel_url: str, limit: int = 10):
        return []

    def _extract_uid(self, url: str) -> Optional[str]:
        return None

    def get_channel_info(self, channel_url: str, user_id: str = None) -> Dict:
        return {"channel_id": "", "channel_name": "B站功能禁用", "channel_url": channel_url}

    def get_latest_video(self, channel_url: str, user_id: str = None) -> Optional[Dict]:
        return None

    def get_video_info(self, video_url: str, user_id: str = None) -> Optional[Dict]:
        return None

    def get_subtitles(self, video_url: str, user_id: str = None) -> Optional[str]:
        return None
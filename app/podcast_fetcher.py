"""
播客 RSS 客户端 + YouTube RSS
"""
import requests
import feedparser
from datetime import datetime
from typing import List, Dict, Optional


class PodcastFetcher:
    def is_youtube_rss(self, url: str) -> bool:
        """检查是否是YouTube RSS"""
        return 'youtube.com/feeds/videos.xml' in url

    def _get_youtube_episodes(self, rss_url: str, limit: int = 10) -> List[Dict]:
        """获取YouTube RSS视频"""
        try:
            feed = feedparser.parse(rss_url)
            if not feed.entries:
                return []

            results = []
            for entry in feed.entries[:limit]:
                # 统一用 entry.id 作为 video_id
                video_id = entry.get('id', '')

                # 发布时间
                published = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    try:
                        published = datetime(*entry.published_parsed[:6]).strftime("%Y-%m-%d")
                    except:
                        pass

                # 获取description - 尝试多个可能的字段
                description = ''
                for key in ['media_description', 'description']:
                    if hasattr(entry, key):
                        val = str(getattr(entry, key, ''))
                        if val:
                            description = val[:500]
                            break

                results.append({
                    "video_id": video_id,
                    "title": entry.get('title', ''),
                    "url": entry.get('link') or f"https://www.youtube.com/watch?v={video_id}",
                    "thumbnail": entry.get('media_thumbnail', [{}])[0].get('url', '') if hasattr(entry, 'media_thumbnail') else '',
                    "duration": 0,
                    "published_at": published,
                    "description": description,
                    "channel_title": feed.feed.get('title', 'YouTube'),
                })

            return results
        except Exception as e:
            print(f"YouTube RSS获取失败: {e}")
            return []

    def get_channel_info(self, rss_url: str) -> Optional[Dict]:
        """获取播客/YouTube频道信息"""
        try:
            # YouTube RSS
            if self.is_youtube_rss(rss_url):
                channel_id = ""
                if "channel_id=" in rss_url:
                    channel_id = rss_url.split("channel_id=")[1].split("&")[0]
                return {
                    "channel_id": channel_id,
                    "channel_name": "YouTube Channel",
                    "channel_url": rss_url,
                }

            feed = feedparser.parse(rss_url)
            if not feed.feed:
                return None

            # 提取封面图 - itunes:image
            thumbnail = ""
            if hasattr(feed.feed, 'image') and feed.feed.image:
                thumbnail = feed.feed.image.get('href', '')
            elif hasattr(feed.feed, 'itunes_image'):
                thumbnail = feed.feed.itunes_image.get('href', '')

            return {
                "channel_id": rss_url,
                "channel_name": feed.feed.get("title", "未知播客"),
                "channel_url": rss_url,
                "thumbnail": thumbnail,
            }
        except Exception as e:
            print(f"获取播客信息失败: {e}")
            return None

    def get_latest_episodes(self, rss_url: str, limit: int = 10) -> List[Dict]:
        """获取最新单集"""
        try:
            # YouTube RSS
            if self.is_youtube_rss(rss_url):
                return self._get_youtube_episodes(rss_url, limit)

            feed = feedparser.parse(rss_url)
            if not feed.entries:
                return []

            channel_title = feed.feed.get("title", "未知播客")

            # 获取频道默认封面
            channel_thumbnail = ""
            if hasattr(feed.feed, 'image') and feed.feed.image:
                channel_thumbnail = feed.feed.image.get('href', '')
            elif hasattr(feed.feed, 'itunes_image'):
                channel_thumbnail = feed.feed.itunes_image.get('href', '')

            results = []

            for entry in feed.entries[:limit]:
                # 解析发布时间 - 优先用published_parsed
                published = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    try:
                        published = datetime(*entry.published_parsed[:6]).strftime("%Y-%m-%d")
                    except:
                        pass
                elif hasattr(entry, "published"):
                    # Tue, 05 May 2026 16:00:00 GMT -> 2026-05-05
                    published = entry.published[:10] if len(entry.published) >= 10 else None

                # 解析时长 itunes:duration (格式: 00:47:45 或 2865 秒)
                duration = 0
                if hasattr(entry, "itunes_duration") and entry.itunes_duration:
                    duration_str = str(entry.itunes_duration)
                    try:
                        if ':' in duration_str:
                            # 格式: HH:MM:SS
                            parts = duration_str.split(':')
                            if len(parts) == 3:
                                duration = int(parts[0])*3600 + int(parts[1])*60 + int(parts[2])
                            elif len(parts) == 2:
                                duration = int(parts[0])*60 + int(parts[1])
                        else:
                            # 秒数
                            duration = int(duration_str)
                    except:
                        duration = 0

                # 获取音频URL和播放页URL
                audio_url = ""
                episode_url = ""
                if hasattr(entry, "enclosure") and entry.enclosure:
                    audio_url = entry.enclosure.get("url", "")
                elif hasattr(entry, "links") and entry.links:
                    for link in entry.links:
                        if link.get("rel") == "enclosure":
                            audio_url = link.get("href", "")
                        elif link.get("rel") == "alternate":
                            episode_url = link.get("href", "")

                # 如果没有episode_url，尝试从link获取
                if not episode_url and hasattr(entry, "link"):
                    episode_url = entry.link

                # 获取单集封面 - 优先用itunes:image，否则用频道封面
                thumbnail = channel_thumbnail
                if hasattr(entry, 'itunes_image') and entry.itunes_image:
                    thumbnail = entry.itunes_image.get('href', '')

                # 获取单集简介
                description = ""
                if hasattr(entry, "description"):
                    import re
                    # 去除HTML标签
                    description = re.sub(r'<[^>]+>', '', entry.description)
                    description = description.strip()[:500] if description else ""

                results.append({
                    "video_id": entry.get("id", ""),  # 统一用 entry.id
                    "title": entry.get("title", ""),
                    "url": episode_url or audio_url,
                    "audio_url": audio_url,
                    "thumbnail": thumbnail,
                    "duration": duration,
                    "published_at": published,
                    "description": description,
                    "channel_title": channel_title,
                })

            return results

        except Exception as e:
            print(f"获取播客单集失败: {e}")
            return []


# 全局实例
_podcast_fetcher: Optional[PodcastFetcher] = None


def get_podcast_fetcher() -> PodcastFetcher:
    global _podcast_fetcher
    if _podcast_fetcher is None:
        _podcast_fetcher = PodcastFetcher()
    return _podcast_fetcher
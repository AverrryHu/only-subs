from fastapi import FastAPI, HTTPException, Header, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List
import feedparser
import time

from .fetcher import YouTubeFetcher
from .bilibili import BilibiliFetcher
from .podcast_fetcher import get_podcast_fetcher
from .youtube_rss import convert_youtube_to_rss
from .supabase_client import (
    get_channels, add_channel, delete_channel, get_channel_by_channel_id, get_channel_by_id,
    get_videos, add_video, get_video_by_video_id, get_video_by_url, update_subtitles, mark_as_read, delete_video,
    get_user_settings, save_user_settings, cleanup_old_videos,
    get_user_video_state, create_user_video_state, get_new_videos_count, get_user_new_videos
)

app = FastAPI(title="Only Subs")

# 内存中的任务历史记录
transcription_tasks = {}  # {job_id: {video_id, status, created_at, user_id, error}}

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

yt_fetcher = YouTubeFetcher()
bi_fetcher = BilibiliFetcher()
podcast_fetcher = get_podcast_fetcher()


@app.get("/")
def root():
    """健康检查"""
    print("Root endpoint called")
    return {"status": "ok"}


@app.on_event("startup")
async def startup_event():
    """启动事件"""
    pass


# 从请求头获取用户ID
def get_user_id(authorization: Optional[str] = None) -> str:
    """从Authorization头获取用户ID"""
    if authorization and authorization != 'undefined':
        return authorization[:50]
    return 'guest'


class ChannelIn(BaseModel):
    channel_url: str
    custom_name: Optional[str] = None


class VideoOut(BaseModel):
    id: int
    video_id: str
    channel_id: str
    channel_name: str
    title: str
    url: str
    audio_url: Optional[str] = None
    thumbnail: Optional[str]
    published_at: Optional[str]
    duration: Optional[int]
    subtitles: Optional[str] = None
    api_subtitles: Optional[str] = None
    description: Optional[str] = None
    has_new: bool
    platform: Optional[str] = None
    job_id: Optional[str] = None
    status: Optional[str] = None


class ChannelOut(BaseModel):
    id: int
    channel_id: str
    channel_name: str
    channel_url: str
    custom_name: Optional[str]
    user_id: Optional[str] = None
    message: Optional[str] = None
    platform: Optional[str] = 'youtube'


class UserSettings(BaseModel):
    folo_token: Optional[str] = None
    sessdata: Optional[str] = None
    bili_jct: Optional[str] = None
    buvid3: Optional[str] = None
    youtube_api_key: Optional[str] = None


class UserInfo(BaseModel):
    user_email: Optional[str] = None
    user_name: Optional[str] = None


# ===== 用户同步API =====
@app.post("/sync_user")
def sync_user(user_info: UserInfo, authorization: Optional[str] = Header(None)):
    """同步用户信息到数据库"""
    user_id = get_user_id(authorization)
    save_user_settings(
        user_id,
        user_email=user_info.user_email,
        user_name=user_info.user_name
    )
    return {"status": "ok"}


# ===== 频道API =====
@app.post("/channels", response_model=ChannelOut)
def add_channel_api(channel: ChannelIn, authorization: Optional[str] = Header(None)):
    """添加频道"""
    user_id = get_user_id(authorization)
    message = None

    # B站已暂时移除支持
    if "bilibili.com" in channel.channel_url:
        raise HTTPException(status_code=400, detail="暂不支持B站，后续可能重新加入")

    if "xyzfm" in channel.channel_url or channel.channel_url.endswith(".xml") or "feed." in channel.channel_url:
        # 播客RSS订阅
        info = podcast_fetcher.get_channel_info(channel.channel_url)
        if not info:
            raise HTTPException(status_code=400, detail="无法获取播客信息")

        existing = get_channel_by_channel_id(info["channel_id"])
        if existing:
            # 检查是否属于当前用户
            if existing.get('user_id') == user_id:
                return ChannelOut(
                    id=existing['id'],
                    channel_id=existing['channel_id'],
                    channel_name=existing['channel_name'],
                    channel_url=existing['channel_url'],
                    custom_name=existing.get('custom_name')
                )
            # 频道不属于当前用户，需要添加自己的副本

        result = add_channel(
            channel_id=info["channel_id"],
            channel_name=info["channel_name"],
            channel_url=info["channel_url"],
            custom_name=channel.custom_name,
            user_id=user_id
        )
        new_channel = result.data[0]

        # 检查是否已有该频道的视频（复用已有视频，为新用户创建阅读状态）
        existing_videos = get_videos(channel_id=info["channel_id"])
        if existing_videos:
            for v in existing_videos:
                create_user_video_state(user_id, v['video_id'])
            message = f"复用已有{len(existing_videos)}个视频"
        else:
            # 获取最新单集
            try:
                episodes = podcast_fetcher.get_latest_episodes(channel.channel_url, limit=10)
                for ep in episodes:
                    if get_video_by_url(ep.get("url", ""), user_id):
                        continue
                    add_video(
                        video_id=ep["video_id"],
                        channel_id=info["channel_id"],
                        title=ep["title"],
                        url=ep["url"],
                        thumbnail=ep.get("thumbnail") or "",
                        published_at=ep.get("published_at") or None,
                        duration=ep.get("duration", 0),
                        audio_url=ep.get("audio_url"),
                        description=ep.get("description"),
                        user_id=user_id
                    )
                    if new_video and new_video.data:
                        create_user_video_state(user_id, ep["video_id"])
                if episodes:
                    message = f"通过RSS获取{len(episodes)}个视频"
            except Exception as e:
                print(f"获取播客失败: {e}")
                message = "获取播客失败"

        return ChannelOut(
            id=new_channel['id'],
            channel_id=new_channel['channel_id'],
            channel_name=new_channel['channel_name'],
            channel_url=new_channel['channel_url'],
            custom_name=new_channel.get('custom_name'),
            message=message
        )

    else:
        # YouTube频道 - 尝试RSS
        rss_url = convert_youtube_to_rss(channel.channel_url)

        if rss_url:
            # RSS方式
            import re
            channel_id_match = re.search(r'channel_id=([^&]+)', rss_url)
            channel_id = channel_id_match.group(1) if channel_id_match else channel.channel_url

            # 从RSS获取频道名
            try:
                feed = feedparser.parse(rss_url)
                channel_name = feed.feed.get('title', channel.channel_url) if feed.feed else channel.channel_url
            except:
                channel_name = channel.channel_url
        else:
            # 回退yt-dlp
            info = yt_fetcher.get_channel_info(channel.channel_url)
            if not info.get("channel_id"):
                raise HTTPException(status_code=400, detail="无法识别该链接")
            channel_id = info["channel_id"]
            channel_name = info["channel_name"]

        existing = get_channel_by_channel_id(channel_id)
        if existing:
            # 检查是否属于当前用户
            if existing.get('user_id') == user_id:
                return ChannelOut(
                    id=existing['id'],
                    channel_id=existing['channel_id'],
                    channel_name=existing['channel_name'],
                    channel_url=existing['channel_url'],
                    custom_name=existing.get('custom_name')
                )
            # 频道属于其他用户，当前用户需要添加自己的副本

        result = add_channel(
            channel_id=channel_id,
            channel_name=channel_name,
            channel_url=channel.channel_url,
            custom_name=channel.custom_name,
            user_id=user_id
        )
        new_channel = result.data[0]

        # 检查是否已有该频道的视频（复用已有视频，为新用户创建阅读状态）
        existing_videos = get_videos(channel_id=channel_id)
        if existing_videos:
            for v in existing_videos:
                # 为当前用户创建阅读状态记录
                create_user_video_state(user_id, v['video_id'])
            message = f"复用已有{len(existing_videos)}个视频"
        else:
            # 用RSS获取视频
            if rss_url:
                try:
                    episodes = podcast_fetcher.get_latest_episodes(rss_url, limit=10)
                    for ep in episodes:
                        # 用URL检查重复（按用户检查）
                        if get_video_by_url(ep.get("url", ""), user_id):
                            continue
                        add_video(
                            video_id=ep["video_id"],
                            channel_id=channel_id,  # 传 YouTube channel_id
                            title=ep["title"],
                            url=ep["url"],
                            thumbnail=ep.get("thumbnail", ""),
                            published_at=ep.get("published_at"),
                            duration=ep.get("duration", 0),
                            description=ep.get("description"),
                            user_id=user_id
                        )
                    if episodes:
                        message = f"通过RSS获取{len(episodes)}个视频"
                except Exception as e:
                    print(f"RSS获取失败: {e}")

    return ChannelOut(
        id=new_channel['id'],
        channel_id=new_channel['channel_id'],
        channel_name=new_channel['channel_name'],
        channel_url=new_channel['channel_url'],
        custom_name=new_channel.get('custom_name'),
        message=message
    )


@app.get("/channels", response_model=List[ChannelOut])
@app.get("/channels", response_model=List[ChannelOut])
def get_channels_api(authorization: Optional[str] = Header(None)):
    """获取所有频道"""
    user_id = get_user_id(authorization)
    channels = get_channels(user_id)
    return [
        ChannelOut(
            id=c['id'],
            channel_id=c['channel_id'],
            channel_name=c['channel_name'],
            channel_url=c['channel_url'],
            custom_name=c.get('custom_name'),
            user_id=c.get('user_id')
        )
        for c in channels
    ]


@app.delete("/channels/{channel_id}")
def delete_channel_api(channel_id: int):
    """删除频道"""
    delete_channel(channel_id)
    return {"message": "Channel deleted"}


# ===== 视频API =====
# 简单内存缓存
_videos_cache = {}
_cache_ttl = 60  # 1分钟缓存

@app.get("/videos", response_model=List[VideoOut])
def get_videos_api(channel_id: Optional[str] = None, authorization: Optional[str] = Header(None)):
    """获取所有视频"""
    user_id = get_user_id(authorization)

    # 如果用户指定了 channel_id，直接用；否则获取用户所有频道的 channel_id
    if channel_id:
        source_channel_ids = [channel_id]
    else:
        user_channels = get_channels(user_id)
        source_channel_ids = [c['channel_id'] for c in user_channels]

    cache_key = f"videos:{user_id}:{','.join(source_channel_ids)}"

    # 检查缓存
    if cache_key in _videos_cache:
        cached_time, cached_data = _videos_cache[cache_key]
        if time.time() - cached_time < _cache_ttl:
            return cached_data

    videos = get_videos(user_id=user_id)

    # 获取用户的未读视频ID列表
    new_video_ids = get_user_new_videos(user_id)

    # 按用户频道过滤视频
    result = []
    for v in videos:
        if v['channel_id'] not in source_channel_ids:
            continue
        # 获取频道名称
        channel = get_channel_by_channel_id(v['channel_id'])
        channel_name = channel['channel_name'] if channel else ""
        platform = channel.get('platform') if channel else None
        # has_new 从用户状态表获取
        has_new = v['video_id'] in new_video_ids
        result.append(VideoOut(
            id=v['id'],
            video_id=v['video_id'],
            channel_id=v['channel_id'],
            channel_name=channel_name,
            title=v['title'],
            url=v['url'],
            audio_url=v.get('audio_url'),
            thumbnail=v.get('thumbnail'),
            published_at=v['published_at'][:10] if v.get('published_at') else None,
            duration=v.get('duration'),
            subtitles=v.get('subtitles'),
            api_subtitles=v.get('api_subtitles'),
            description=v.get('description'),
            has_new=has_new,
            platform=platform,
            job_id=v.get('job_id'),
            status=v.get('status')
        ))

    # 保存到缓存
    _videos_cache[cache_key] = (time.time(), result)
    return result


@app.get("/videos/by/{video_id}")
def get_video_by_id_api(video_id: str, authorization: Optional[str] = Header(None)):
    """获取视频详情"""
    user_id = get_user_id(authorization)
    video = get_video_by_video_id(video_id)
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    # 获取用户的has_new状态
    state = get_user_video_state(user_id, video_id)
    has_new = state.get('has_new', False) if state else False

    # 获取字幕（如果还没有）
    if not video.get('subtitles'):
        try:
            if 'bilibili' in video['url']:
                subtitles = bi_fetcher.get_subtitles(video['url'], user_id)
            elif 'xyzfm' in video['url'] or 'xiaoyuzhou' in video['url']:
                # 播客：从RSS获取description
                channel = get_channel_by_channel_id(video['channel_id'])
                if channel and 'xyzfm' in channel.get('channel_url', ''):
                    episodes = podcast_fetcher.get_latest_episodes(channel['channel_url'], limit=20)
                    for ep in episodes:
                        if ep.get('title') == video.get('title'):
                            description = ep.get('description')
                            break
                subtitles = None
            else:
                subtitles = yt_fetcher.get_subtitles(video['url'])
            if subtitles:
                update_subtitles(video_id, subtitles)
                video['subtitles'] = subtitles
        except Exception as e:
            print(f"获取字幕失败: {e}")

    channel = get_channel_by_channel_id(video['channel_id'])
    channel_name = channel['channel_name'] if channel else ""
    platform = channel.get('platform') if channel else None

    return VideoOut(
        id=video['id'],
        video_id=video['video_id'],
        channel_id=video['channel_id'],
        channel_name=channel_name,
        title=video['title'],
        url=video['url'],
        audio_url=video.get('audio_url'),
        thumbnail=video.get('thumbnail'),
        published_at=video['published_at'][:10] if video.get('published_at') else None,
        duration=video.get('duration'),
        subtitles=video.get('subtitles'),
        api_subtitles=video.get('api_subtitles'),
        description=video.get('description'),
        has_new=has_new,
        platform=platform,
        job_id=video.get('job_id'),
        status=video.get('status')
    )


# 添加单个B站视频
class VideoIn(BaseModel):
    video_url: str
    channel_id: int


@app.post("/videos/add", response_model=VideoOut)
def add_video_api(video: VideoIn):
    """手动添加B站视频"""
    user_id = get_user_id()
    video_info = bi_fetcher.get_video_info(video.video_url, user_id)
    if not video_info:
        raise HTTPException(status_code=400, detail="Failed to get video info")

    # 检查是否已存在
    existing = get_video_by_video_id(video_info["video_id"])
    if existing:
        return existing

    result = add_video(
        video_id=video_info["video_id"],
        channel_id=video.channel_id,
        title=video_info["title"],
        url=video_info["url"],
        thumbnail=video_info.get("thumbnail"),
        published_at=str(video_info.get("published_at", "")),
        duration=video_info.get("duration"),
        description=video_info.get("description"),
        user_id=user_id
    )
    new_video = result.data[0]

    channel = get_channel_by_id(video.channel_id)
    channel_name = channel['channel_name'] if channel else ""

    return VideoOut(
        id=new_video['id'],
        video_id=new_video['video_id'],
        channel_id=new_video['channel_id'],
        channel_name=channel_name,
        title=new_video['title'],
        url=new_video.get('url'),
        thumbnail=new_video.get('thumbnail'),
        published_at=new_video['published_at'][:10] if new_video.get('published_at') else None,
        duration=new_video.get('duration'),
        subtitles=new_video.get('subtitles'),
        api_subtitles=new_video.get('api_subtitles'),
        has_new=new_video.get('has_new', True),
        audio_url=new_video.get('audio_url'),
        platform=channel.get('platform') if channel else None,
        job_id=new_video.get('job_id'),
        status=new_video.get('status')
    )


@app.post("/videos/{video_id}/read")
def mark_as_read_api(video_id: str, authorization: Optional[str] = Header(None)):
    """标记已读"""
    user_id = get_user_id(authorization)
    mark_as_read(user_id, video_id)
    return {"message": "Video marked as read"}


@app.get("/new-count")
def get_new_count_api(authorization: Optional[str] = Header(None)):
    """获取未读视频数量"""
    user_id = get_user_id(authorization)
    count = get_new_videos_count(user_id)
    return {"count": count}


@app.delete("/videos/{video_id}")
def delete_video_api(video_id: int):
    """删除视频"""
    delete_video(video_id)
    return {"message": "Video deleted"}


# ===== 检查更新 =====
@app.post("/check")
def check_now(authorization: Optional[str] = Header(None)):
    """手动检查更新"""
    import re
    user_id = get_user_id(authorization)
    results = []

    # 获取所有订阅的频道
    channels = get_channels(user_id)

    # 检查YouTube频道
    for channel in channels:
        if "bilibili" in channel['channel_id'] or "xyzfm" in channel['channel_id']:
            continue
        if "youtube.com" in channel['channel_url']:
            # YouTube频道 - 尝试RSS
            rss_url = convert_youtube_to_rss(channel['channel_url'])
            if rss_url:
                try:
                    print(f"YouTube RSS: {channel['channel_name']}")
                    episodes = podcast_fetcher.get_latest_episodes(rss_url, limit=10)
                    for ep in episodes:
                        if get_video_by_url(ep.get("url", "")):
                            continue
                        new_video = add_video(
                            video_id=ep["video_id"],
                            channel_id=channel['id'],
                            title=ep["title"],
                            url=ep["url"],
                            thumbnail=ep.get("thumbnail", ""),
                            published_at=ep.get("published_at"),
                            duration=ep.get("duration", 0),
                            description=ep.get("description"),
                            user_id=user_id
                        )
                        # 为当前用户创建视频状态记录
                        if new_video and new_video.data:
                            create_user_video_state(user_id, ep["video_id"])
                except Exception as e:
                    print(f"YouTube RSS失败: {e}")
            continue

    # 检查播客频道
    for channel in channels:
        if "xyzfm" not in channel['channel_url'] and not channel['channel_url'].endswith(".xml"):
            continue

        try:
            episodes = podcast_fetcher.get_latest_episodes(channel['channel_url'], limit=30)
            print(f"播客 {channel['channel_name']}: 获取{len(episodes)}个单集")
            for ep in episodes:
                existing = get_video_by_video_id(ep.get("video_id", ""))
                if not existing:
                    new_video = add_video(
                        video_id=ep["video_id"],
                        channel_id=channel['id'],
                        title=ep["title"],
                        url=ep["url"],
                        thumbnail=ep.get("thumbnail"),
                        published_at=ep.get("published_at"),
                        duration=ep.get("duration", 0),
                        audio_url=ep.get("audio_url"),
                        description=ep.get("description"),
                        user_id=user_id
                    )
                    # 为当前用户创建视频状态记录
                    if new_video and new_video.data:
                        create_user_video_state(user_id, ep["video_id"])
                    results.append(new_video.data[0])
        except Exception as e:
            print(f"检查播客频道失败: {e}")

    # 清理2个月前的视频
    try:
        deleted = cleanup_old_videos(days=60)
        results.append({"cleanup": f"删除{deleted}个旧视频"})
    except Exception as e:
        print(f"清理旧视频失败: {e}")

    return {"new_videos": len(results), "details": results}


# ===== 用户设置 =====
@app.get("/settings")
def get_settings(authorization: Optional[str] = Header(None)):
    """获取设置"""
    user_id = get_user_id(authorization)
    settings = get_user_settings(user_id)
    if not settings:
        # 尝试获取guest的设置
        settings = get_user_settings('guest')
    return {
        "has_credential": bool(settings['sessdata']) if settings else False,
        "sessdata": settings.get('sessdata', '') if settings else '',
        "youtube_api_key": settings.get('youtube_api_key', '') if settings else ''
    }


@app.post("/settings")
def save_settings(settings: UserSettings, authorization: Optional[str] = Header(None)):
    """保存设置"""
    user_id = get_user_id(authorization)
    save_user_settings(
        user_id,
        None,  # folo_token - 不再使用
        settings.sessdata,
        settings.bili_jct,
        settings.buvid3,
        youtube_api_key=settings.youtube_api_key
    )

    return {"message": "设置已保存"}


# ===== OPML导入 =====
@app.post("/import/opml")
def import_opml(file: UploadFile = File(...), authorization: Optional[str] = Header(None)):
    """导入OPML批量订阅"""
    import xml.etree.ElementTree as ET

    user_id = get_user_id(authorization)
    print(f"OPML导入 user_id: {user_id}, auth: {authorization}")
    content = file.file.read().decode("utf-8")

    added_channels = []
    errors = []

    try:
        root = ET.fromstring(content)
        # OPML格式: body/outline[@xmlUrl]
        for outline in root.findall(".//outline[@xmlUrl]"):
            xml_url = outline.get("xmlUrl", "")
            title = outline.get("title", "") or outline.get("text", "")

            if not xml_url:
                continue

            try:
                # 获取频道信息
                info = podcast_fetcher.get_channel_info(xml_url)
                if not info:
                    errors.append(f"无法获取: {title}")
                    continue

                # 检查是否已存在
                existing = get_channel_by_channel_id(info["channel_id"])
                if existing and existing.get('user_id') == user_id:
                    added_channels.append(existing)
                    continue
                # 如果属于其他用户，为当前用户创建新频道

                # 添加频道
                result = add_channel(
                    channel_id=info["channel_id"],
                    channel_name=info["channel_name"],
                    channel_url=info["channel_url"],
                    custom_name=title or None,
                    user_id=user_id
                )
                new_channel = result.data[0]

                # 检查是否已有该频道的视频（复用已有视频）
                existing_videos = get_videos(channel_id=info["channel_id"])
                if existing_videos:
                    # 为当前用户创建阅读状态（忽略已存在）
                    for v in existing_videos:
                        try:
                            create_user_video_state(user_id, v['video_id'])
                        except Exception as e:
                            if 'duplicate' not in str(e).lower():
                                print(f"创建状态失败: {e}")
                else:
                    # 获取单集
                    try:
                        episodes = podcast_fetcher.get_latest_episodes(xml_url, limit=10)
                        for ep in episodes:
                            # 检查是否已存在
                            if get_video_by_url(ep.get("url", ""), user_id):
                                continue
                            new_video = add_video(
                                video_id=ep["video_id"],
                                channel_id=info["channel_id"],  # 用字符串 channel_id
                                title=ep["title"],
                                url=ep["url"],
                                thumbnail=ep.get("thumbnail"),
                                published_at=ep.get("published_at", ""),
                                duration=ep.get("duration", 0),
                                audio_url=ep.get("audio_url"),
                                description=ep.get("description"),
                                user_id=user_id
                            )
                            if new_video and new_video.data:
                                try:
                                    create_user_video_state(user_id, ep["video_id"])
                                except Exception as se:
                                    if 'duplicate' not in str(se).lower():
                                        print(f"创建状态失败: {se}")
                    except Exception as e:
                        print(f"获取单集失败: {e}")

                added_channels.append(new_channel)

            except Exception as e:
                errors.append(f"{title}: {str(e)}")

        return {
            "added": len(added_channels),
            "channels": added_channels,
            "errors": errors
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"解析OPML失败: {str(e)}")


# ===== 提取字幕 =====
class SubtitleIn(BaseModel):
    video_id: str
    audio_url: Optional[str] = None


@app.post("/subtitles/extract", response_model=dict)
def extract_subtitles(sub: SubtitleIn, authorization: Optional[str] = Header(None)):
    """提取YouTube/音频字幕"""
    from .supabase_client import get_supabase, get_user_settings
    import requests

    video_id = sub.video_id
    audio_url = sub.audio_url  # podcast的audio_url
    user_id = get_user_id(authorization)

    # 获取用户的YouTube API Key（也用于supadata）
    settings = get_user_settings(user_id)
    api_key = settings.get('youtube_api_key') if settings else None

    if not api_key:
        return {"error": "请先在设置中添加API Key (supadata.ai)"}

    # podcast使用audio_url，YouTube使用video_id
    if audio_url:
        video_url = audio_url
        # 小宇宙URL需要提取真实的CDN重定向地址
        if 'dts-api.xiaoyuzhoufm.com' in video_url:
            try:
                resp = requests.head(video_url, allow_redirects=True, timeout=10)
                if resp.status_code == 200 and resp.url:
                    video_url = resp.url
                    # 去掉查询参数
                    if '?' in video_url:
                        video_url = video_url.split('?')[0]
            except Exception as e:
                print(f"获取CDN URL失败: {e}")
        if 'xiaoyuzhoufm' in video_url or 'xyzcdn' in video_url:
            api_url = f"https://api.supadata.ai/v1/transcript?url={video_url}&lang=zh&text=true&mode=auto&referer=https://xiaoyuzhoufm.com"
        else:
            api_url = f"https://api.supadata.ai/v1/transcript?url={video_url}&lang=zh&text=true&mode=auto"
    elif video_id.startswith('http'):
        video_url = video_id
        api_url = f"https://api.supadata.ai/v1/transcript?url={video_url}&lang=zh&text=true&mode=auto"
    else:
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        api_url = f"https://api.supadata.ai/v1/transcript?url={video_url}&lang=zh&text=true&mode=auto"

    headers = {
        "x-api-key": api_key,
    }

    try:
        resp = requests.get(api_url, headers=headers, timeout=30)
        if resp.status_code == 202:
            # 返回job ID，需要轮询
            result = resp.json()
            job_id = result.get('jobId')
            # 记录任务到数据库
            try:
                client = get_supabase()
                client.table('videos').update({'job_id': job_id}).eq('video_id', video_id).execute()
            except Exception as e:
                print(f"保存job_id失败: {e}")
            # 记录任务到内存
            transcription_tasks[job_id] = {
                'video_id': video_id,
                'audio_url': audio_url,
                'status': 'processing',
                'created_at': time.time(),
                'user_id': user_id
            }
            return {"status": "processing", "jobId": job_id, "video_id": video_id}
        elif resp.status_code != 200:
            # 过滤HTML错误内容
            error_msg = resp.text if resp.text and not resp.text.startswith('<!') else f"HTTP {resp.status_code}"
            return {"error": f"API错误: {resp.status_code}", "detail": error_msg[:50]}

        result = resp.json()
        if 'content' in result:
            content = result['content']
            if isinstance(content, list):
                text = '\n'.join([c.get('text', '') for c in content])
            else:
                text = content
            lang = result.get('lang', 'unknown')

            # 保存清洗后的字幕
            import re
            cleaned_text = re.sub(r'\n+', '', text)  # 去掉换行
            cleaned_text = cleaned_text.replace(' ', '')  # 移除所有空格
            # 英文/数字和中文之间加空格
            cleaned_text = re.sub(r'([a-zA-Z0-9])([一-龥])', r'\1 \2', cleaned_text)
            cleaned_text = re.sub(r'([一-龥])([a-zA-Z0-9])', r'\1 \2', cleaned_text)
            cleaned_text = cleaned_text.strip()

            # 保存到数据库
            try:
                client = get_supabase()
                # YouTube视频需要用完整video_id保存
                db_video_id = video_id if video_id.startswith('yt:video:') else f'yt:video:{video_id}'
                # 检查是否存在
                existing = client.table('videos').select('id').eq('video_id', db_video_id).execute()
                if existing.data:
                    # 更新已有记录
                    client.table('videos').update({
                        'subtitles': cleaned_text,
                        'api_subtitles': text  # 保存原始字幕
                    }).eq('video_id', db_video_id).execute()
                else:
                    # 创建新记录
                    client.table('videos').insert({
                        'video_id': db_video_id,
                        'title': f'YouTube Video {video_id}',
                        'url': f'https://www.youtube.com/watch?v={video_id}',
                        'subtitles': cleaned_text,
                        'api_subtitles': text,
                        'user_id': user_id,
                        'channel_id': ''
                    }).execute()
            except Exception as e:
                print(f"保存字幕到数据库失败: {e}")

            return {"subtitles": cleaned_text, "language": lang}
        else:
            return {"error": "未找到字幕"}

    except Exception as e:
        return {"error": str(e)}


@app.get("/subtitles/poll/{job_id}")
def poll_subtitles(job_id: str, video_id: str, authorization: Optional[str] = Header(None)):
    """轮询异步字幕任务状态"""
    from .supabase_client import get_supabase, get_user_settings
    import requests

    user_id = get_user_id(authorization)
    settings = get_user_settings(user_id)
    api_key = settings.get('youtube_api_key') if settings else None

    if not api_key:
        return {"error": "请先在设置中添加API Key (supadata.ai)"}

    if not video_id:
        return {"error": "缺少video_id参数"}

    headers = {"x-api-key": api_key}

    try:
        resp = requests.get(f"https://api.supadata.ai/v1/transcript/{job_id}", headers=headers, timeout=30)
        if resp.status_code != 200:
            # 可能是502错误，服务端问题
            if resp.text and resp.text.startswith('<!'):
                return {"status": "error", "message": "服务端繁忙，请稍后重试"}
            return {"status": "error", "message": resp.text[:100]}

        # 检查响应是否是JSON
        content_type = resp.headers.get('content-type', '')
        if 'application/json' not in content_type:
            return {"status": "error", "message": "响应格式错误"}

        result = resp.json()
        status = result.get('status')

        if status == 'active':
            return {"status": "processing"}
        elif status == 'failed':
            error_msg = result.get('message', '任务失败')
            # 记录失败任务
            if job_id in transcription_tasks:
                transcription_tasks[job_id]['status'] = 'failed'
                transcription_tasks[job_id]['error'] = error_msg
            return {"status": "failed", "message": error_msg}
        elif status == 'completed':
            content = result.get('content', [])
            if isinstance(content, list):
                text = '\n'.join([c.get('text', '') for c in content])
            else:
                text = content

            # 清洗字幕
            import re
            text = re.sub(r'\n+', '', text)  # 去掉换行
            # 先去掉所有空格
            text = text.replace(' ', '')
            # 然后在英文/数字和中文之间加空格
            text = re.sub(r'([a-zA-Z0-9])([一-龥])', r'\1 \2', text)
            text = re.sub(r'([一-龥])([a-zA-Z0-9])', r'\1 \2', text)
            text = text.strip()

            # 保存到数据库
            if video_id:
                try:
                    client = get_supabase()
                    client.table('videos').update({
                        'subtitles': text,
                        'job_id': job_id
                    }).eq('video_id', video_id).execute()
                except Exception as e:
                    print(f"保存字幕失败: {e}")

            return {"status": "completed", "subtitles": text}
        else:
            return {"status": status}

    except Exception as e:
        return {"error": str(e)}


@app.get("/subtitles/tasks")
def list_tasks(authorization: Optional[str] = Header(None)):
    """列出用户的转录任务历史（从数据库获取job_id）"""
    user_id = get_user_id(authorization)
    from .supabase_client import get_supabase

    try:
        client = get_supabase()
        # 获取有job_id的视频
        videos_resp = client.table('videos').select('id,video_id,title,subtitles,job_id').execute()
        tasks = []
        for v in videos_resp.data:
            if v.get('job_id'):
                tasks.append({
                    "job_id": v.get('job_id'),
                    "video_id": v.get('video_id'),
                    "title": v.get('title', '')[:50] if v.get('title') else '',
                    "status": "completed" if v.get('subtitles') else "processing",
                    "saved": bool(v.get('subtitles'))
                })
        # 按job_id排序（最近的在前面）
        tasks.sort(key=lambda x: x['job_id'], reverse=True)
        return tasks[:50]
    except Exception as e:
        return {"error": str(e)}


# ===== 图片代理 =====
image_cache = {}


@app.get("/proxy/image")
def proxy_image(url: str):
    """代理图片请求"""
    import requests

    if url in image_cache:
        cached = image_cache[url]
        return StreamingResponse(
            iter([cached['data']]),
            media_type=cached['content_type']
        )

    headers = {
        'User-Agent': 'Mozilla/5.0',
        'Referer': 'https://www.bilibili.com',
    }
    resp = requests.get(url, headers=headers)
    content_type = resp.headers.get('Content-Type', 'image/jpeg')
    image_data = resp.content

    if len(image_data) < 1024 * 1024:
        image_cache[url] = {'data': image_data, 'content_type': content_type}

    return StreamingResponse(iter([image_data]), media_type=content_type)


@app.get("/")
def root():
    return {"message": "Only Subs API"}
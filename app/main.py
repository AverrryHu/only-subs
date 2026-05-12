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
    print("Application starting up")
    import time
    time.sleep(1)
    print("Startup complete")


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
    subtitles: Optional[str]
    description: Optional[str] = None
    has_new: bool
    platform: Optional[str] = None


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
            description=v.get('description'),
            has_new=has_new,
            platform=platform
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
        description=video.get('description'),
        has_new=has_new,
        platform=platform
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
        url=new_video['url'],
        thumbnail=new_video.get('thumbnail'),
        published_at=new_video['published_at'][:10] if new_video.get('published_at') else None,
        duration=new_video.get('duration'),
        subtitles=new_video.get('subtitles'),
        has_new=new_video.get('has_new', True)
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
        "sessdata": settings.get('sessdata', '') if settings else ''
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
        settings.buvid3
    )

    return {"message": "设置已保存（bilibili已暂时移除支持）"}


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


@app.post("/subtitles/extract", response_model=dict)
def extract_subtitles(sub: SubtitleIn, authorization: Optional[str] = Header(None)):
    """提取YouTube字幕"""
    from youtube_transcript_api import YouTubeTranscriptApi
    import dataclasses
    from .supabase_client import get_supabase

    video_id = sub.video_id
    user_id = get_user_id(authorization)

    try:
        api = YouTubeTranscriptApi()
        # 优先中文
        transcript = api.fetch(video_id, languages=['zh', 'en'])
        data = dataclasses.asdict(transcript)

        snippets = data['snippets']
        texts = [s.get('text', '') for s in snippets]
        subtitles = '\n'.join(texts)

        # 保存到数据库
        # 尝试用完整video_id更新
        client = get_supabase()
        client.table('videos').update({'subtitles': subtitles}).eq('video_id', f'yt:video:{video_id}').execute()

        return {'subtitles': subtitles, 'language': data['language']}
    except Exception as e:
        print(f'提取字幕失败: {e}')
        raise HTTPException(status_code=500, detail=str(e))


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
"""
Supabase客户端 - 带表创建
"""
import os
from supabase import create_client, Client
from typing import Optional

# 读取配置
from dotenv import load_dotenv
env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
load_dotenv(env_path)

SUPABASE_URL = os.environ.get('SUPABASE_URL', 'https://oguxjqmhsctolgzbkegy.supabase.co')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY', 'sb_publishable_XhAMOQXhYLVlvVywa59zDw_lXCKfNhc')

_supabase_client: Optional[Client] = None

def get_supabase() -> Client:
    global _supabase_client
    if _supabase_client is None:
        _supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _supabase_client


# 表已通过Supabase Dashboard创建
# 这里只做连接测试

def test_connection():
    """测试数据库连接"""
    client = get_supabase()
    try:
        client.table('channels').select('id').limit(1).execute()
        print("数据库连接正常")
        return True
    except Exception as e:
        print(f"数据库连接失败: {e}")
        return False

test_connection()


# 频道操作
def get_channels(user_id: str = None):
    client = get_supabase()
    query = client.table('channels').select('*')
    if user_id and user_id != 'guest' and user_id != 'undefined':
        query = query.eq('user_id', user_id)
    # guest用户和undefined返回所有（方便开发调试）
    return query.execute().data

def get_platform_from_url(url: str) -> str:
    """从URL推断平台"""
    if not url:
        return 'youtube'
    if 'bilibili.com' in url:
        return 'bilibili'
    if 'xyzfm' in url or 'xiaoyuzhou' in url or '.xml' in url or 'feed.' in url or 'fireside.fm' in url:
        return 'podcast'
    return 'youtube'

def add_channel(channel_id: str, channel_name: str, channel_url: str, custom_name: str = None, user_id: str = None, platform: str = None):
    client = get_supabase()
    # 自动从URL推断平台
    if platform is None:
        platform = get_platform_from_url(channel_url)
    return client.table('channels').insert({
        'channel_id': channel_id,
        'channel_name': channel_name,
        'channel_url': channel_url,
        'custom_name': custom_name,
        'user_id': user_id,
        'platform': platform
    }).execute()

def delete_channel(channel_id: int):
    client = get_supabase()
    client.table('videos').delete().eq('channel_id', channel_id).execute()
    client.table('channels').delete().eq('id', channel_id).execute()

def get_channel_by_channel_id(channel_id: str):
    client = get_supabase()
    result = client.table('channels').select('*').eq('channel_id', channel_id).execute()
    return result.data[0] if result.data else None

def get_channel_by_id(channel_id: int):
    client = get_supabase()
    result = client.table('channels').select('*').eq('id', channel_id).execute()
    return result.data[0] if result.data else None


# 视频操作
def get_videos(channel_id: str = None, has_new: bool = None, user_id: str = None):
    client = get_supabase()
    query = client.table('videos').select('*')
    if channel_id:
        query = query.eq('channel_id', channel_id)
    if has_new is not None:
        query = query.eq('has_new', has_new)
    # user_id 过滤移到这里，不再默认过滤
    # 按发布时间降序（最新在前）
    return query.order('published_at', desc=True).execute().data

def add_video(video_id: str, channel_id: str, title: str, url: str,
            thumbnail: str = None, published_at: str = None, duration: int = None,
            audio_url: str = None, description: str = None, user_id: str = None):
    client = get_supabase()
    data = {
        'video_id': video_id,
        'channel_id': channel_id,
        'title': title,
        'url': url,
        'thumbnail': thumbnail,
        'published_at': published_at,
        'duration': duration,
        'user_id': user_id
    }
    if audio_url:
        data['audio_url'] = audio_url
    if description:
        data['description'] = description
    return client.table('videos').insert(data).execute()

def get_video_by_video_id(video_id: str):
    client = get_supabase()
    result = client.table('videos').select('*').eq('video_id', video_id).execute()
    return result.data[0] if result.data else None

def get_video_by_url(url: str, user_id: str = None):
    """通过URL检查视频是否已存在"""
    client = get_supabase()
    query = client.table('videos').select('*').eq('url', url)
    if user_id and user_id != 'guest' and user_id != 'undefined':
        query = query.eq('user_id', user_id)
    result = query.execute()
    return result.data[0] if result.data else None

def update_subtitles(video_id: str, subtitles: str):
    client = get_supabase()
    client.table('videos').update({'subtitles': subtitles}).eq('video_id', video_id).execute()

# User Video States
def get_user_video_state(user_id: str, video_id: str):
    """获取用户对单个视频的状态"""
    client = get_supabase()
    result = client.table('user_video_states').select('*').eq('user_id', user_id).eq('video_id', video_id).execute()
    return result.data[0] if result.data else None

def create_user_video_state(user_id: str, video_id: str):
    """创建用户视频状态记录"""
    client = get_supabase()
    return client.table('user_video_states').insert({
        'user_id': user_id,
        'video_id': video_id,
        'has_new': True
    }).execute()

def mark_as_read(user_id: str, video_id: str):
    """标记视频为已读"""
    client = get_supabase()
    client.table('user_video_states').update({
        'has_new': False,
        'read_at': datetime.now().isoformat()
    }).eq('user_id', user_id).eq('video_id', video_id).execute()

def get_new_videos_count(user_id: str):
    """获取用户未读视频数量"""
    client = get_supabase()
    result = client.table('user_video_states').select('id', count='exact').eq('user_id', user_id).eq('has_new', True).execute()
    return result.count or 0

def get_user_new_videos(user_id: str):
    """获取用户未读视频的video_id列表"""
    client = get_supabase()
    result = client.table('user_video_states').select('video_id').eq('user_id', user_id).eq('has_new', True).execute()
    return [r['video_id'] for r in result.data]

def delete_video(video_id: int):
    client = get_supabase()
    client.table('videos').delete().eq('id', video_id).execute()

def cleanup_old_videos(days: int = 60):
    """删除days天之前的视频"""
    from datetime import datetime, timedelta
    import dateutil.parser

    client = get_supabase()
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    # 获取需要删除的视频
    videos = client.table('videos').select('id, published_at').execute().data
    deleted = 0
    for v in videos:
        if v.get('published_at'):
            try:
                pub_date = v['published_at'][:10]
                if pub_date < cutoff:
                    client.table('videos').delete().eq('id', v['id']).execute()
                    deleted += 1
            except:
                pass
    return deleted


# 用户设置操作
def get_user_settings(user_id: str):
    client = get_supabase()
    result = client.table('user_settings').select('*').eq('user_id', user_id).execute()
    return result.data[0] if result.data else None

def save_user_settings(user_id: str, folo_token: str = None, sessdata: str = None, bili_jct: str = None, buvid3: str = None, user_email: str = None, user_name: str = None):
    client = get_supabase()
    existing = get_user_settings(user_id)
    try:
        if existing:
            update_data = {}
            if folo_token is not None:
                update_data['folo_token'] = folo_token
            if sessdata is not None:
                update_data['sessdata'] = sessdata
            if bili_jct is not None:
                update_data['bili_jct'] = bili_jct
            if buvid3 is not None:
                update_data['buvid3'] = buvid3
            if user_email is not None:
                update_data['user_email'] = user_email
            if user_name is not None:
                update_data['user_name'] = user_name
            if update_data:
                client.table('user_settings').update(update_data).eq('user_id', user_id).execute()
        else:
            insert_data = {'user_id': user_id}
            if folo_token:
                insert_data['folo_token'] = folo_token
            if sessdata:
                insert_data['sessdata'] = sessdata
            if bili_jct:
                insert_data['bili_jct'] = bili_jct
            if buvid3:
                insert_data['buvid3'] = buvid3
            if user_email:
                insert_data['user_email'] = user_email
            if user_name:
                insert_data['user_name'] = user_name
            client.table('user_settings').insert(insert_data).execute()
    except Exception as e:
        # 如果folo_token列不存在，只保存其他字段
        if 'folo_token' in str(e) and existing:
            update_data = {}
            if sessdata is not None:
                update_data['sessdata'] = sessdata
            if bili_jct is not None:
                update_data['bili_jct'] = bili_jct
            if buvid3 is not None:
                update_data['buvid3'] = buvid3
            if update_data:
                client.table('user_settings').update(update_data).eq('user_id', user_id).execute()
        elif 'folo_token' in str(e):
            insert_data = {'user_id': user_id}
            if sessdata:
                insert_data['sessdata'] = sessdata
            if bili_jct:
                insert_data['bili_jct'] = bili_jct
            if buvid3:
                insert_data['buvid3'] = buvid3
            client.table('user_settings').insert(insert_data).execute()
        else:
            raise
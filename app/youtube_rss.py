"""
YouTube RSS 工具
"""
import requests
import re


def get_youtube_channel_id_from_url(channel_url: str) -> str:
    """从YouTube频道URL提取channel_id"""
    # 直接是 channel URL
    match = re.search(r'youtube\.com/channel/([^/?]+)', channel_url)
    if match:
        return match.group(1)

    # @username 格式
    match = re.search(r'youtube\.com/@([^/?]+)', channel_url)
    if match:
        return f"@{match.group(1)}"

    # c/customname 格式
    match = re.search(r'youtube\.com/c/([^/?]+)', channel_url)
    if match:
        return f"c/{match.group(1)}"

    return ""


def convert_youtube_to_rss(channel_url: str) -> str:
    """将YouTube频道URL转换为RSS地址"""
    channel_id = get_youtube_channel_id_from_url(channel_url)
    if not channel_id:
        return ""

    # 如果是 @username 或 c/xxx 格式，需要先获取真正的 channel_id（通过页面）
    if channel_id.startswith('@') or channel_id.startswith('c/'):
        try:
            # 获取页面，增加User-Agent
            headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}
            resp = requests.get(channel_url, timeout=10, headers=headers)
            html = resp.text

            # 尝试从 externalId 提取（YouTube新格式）
            match = re.search(r'"externalId":"([^"]+)"', html)
            if match:
                channel_id = match.group(1)
            else:
                # 尝试从 meta 提取
                match = re.search(r'<meta itemprop="channelId" content="([^"]+)"', html)
                if match:
                    channel_id = match.group(1)
                else:
                    return ""
        except:
            return ""

    return f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"


# 测试
if __name__ == "__main__":
    urls = [
        "https://www.youtube.com/@TerryChen",
        "https://www.youtube.com/channel/UC_whOg3XES3Fihic53fvo4Q"
    ]
    for url in urls:
        rss = convert_youtube_to_rss(url)
        print(f"{url} -> {rss}")
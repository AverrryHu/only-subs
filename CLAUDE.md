# Only Subs 项目

## 快速启动

### 后端重启
```bash
cd /Users/hushizhe/Desktop/vibe-coding/ytb
pkill -f run_server
nohup /Users/hushizhe/opt/anaconda3/bin/python run_server.py > /tmp/backend.log 2>&1 &
```
验证: `curl localhost:8000/channels`

### 前端重启
```bash
cd /Users/hushizhe/Desktop/vibe-coding/ytb/frontend
npm run dev
```

## 技术栈

- 后端: FastAPI + Supabase
- 前端: React + Tailwind CSS
- RSS: feedparser
- 视频: yt-dlp, bilibili_api

## 关键文件

- `app/main.py` - FastAPI 入口
- `app/supabase_client.py` - 数据库操作
- `app/podcast_fetcher.py` - Podcast/YouTube RSS 解析
- `app/bilibili.py` - B站视频获取
- `frontend/src/App.jsx` - 前端主组件

## 数据库

- 使用 Supabase 云端 (本地 .env 配置)
- videos 表包含: video_id, title, url, thumbnail, duration, published_at, description, subtitles, audio_url
import { useState, useEffect, useRef } from 'react'
import './App.css'
import { signInWithGoogle, signOut, getCurrentUser, getSession, onAuthStateChange, signUpWithEmail, signInWithEmail } from './auth'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

function App() {
  const [channels, setChannels] = useState([])
  const [videos, setVideos] = useState([])
  const [newUrl, setNewUrl] = useState('')
  const [checking, setChecking] = useState(false)
  const [selectedVideo, setSelectedVideo] = useState(null)
  const [modalTab, setModalTab] = useState('overview')
  const [subtitlesLoading, setSubtitlesLoading] = useState(false)
  const [extracting, setExtracting] = useState(false)
  const [menuOpen, setMenuOpen] = useState(null)
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const [authHeader, setAuthHeader] = useState({})
  const [videosLoading, setVideosLoading] = useState(false)
  const [channelsLoading, setChannelsLoading] = useState(true)
  const [showChannelInput, setShowChannelInput] = useState(false)  // 显示频道输入框
  const [showAddChannelModal, setShowAddChannelModal] = useState(false)  // 添加频道弹窗
  const [channelError, setChannelError] = useState('')  // 频道添加错误提示
  const [showEmailLogin, setShowEmailLogin] = useState(false)  // 邮箱登录弹窗
  const [loginMode, setLoginMode] = useState('login')  // login 或 signup
  const [loginEmail, setLoginEmail] = useState('')
  const [loginPassword, setLoginPassword] = useState('')
  const [emailLoginError, setEmailLoginError] = useState('')
  const abortControllerRef = useRef(null)  // 取消请求用

  // 辅助函数
  const getThumbnail = (url) => {
    if (!url || typeof url !== 'string') return ''
    // Remove @params (e.g., @100w_100h_1c.png) to get full-size image
    let cleaned = url.split('@')[0]
    if (!cleaned.endsWith('.jpg') && !cleaned.endsWith('.png') && !cleaned.endsWith('.webp')) {
      cleaned = url  // keep original if no @params
    }
    // Convert http:// to https://
    if (cleaned.startsWith('http://')) {
      cleaned = cleaned.replace('http://', 'https://')
    }
    // Add https: prefix for protocol-relative URLs (//)
    if (cleaned.startsWith('//')) return 'https:' + cleaned
    // Handle relative paths
    if (cleaned.startsWith('/')) return 'https://i0.hdslb.com' + cleaned
    // Use proxy for Bilibili images to bypass Referer restriction
    if (cleaned.includes('hdslb.com')) {
      return `${API_URL}/proxy/image?url=${encodeURIComponent(cleaned)}`
    }
    return cleaned
  }

  const getChannelPlatform = (video) => {
    // 优先使用 channel 的 platform 字段
    if (video?.platform && video.platform !== '-') return video.platform
    // 通过URL判断平台
    const url = video?.url || video?.channel_name || ''
    if (url.includes('bilibili.com')) return 'bilibili'
    if (url.includes('xyzfm') || url.includes('xiaoyuzhou') || url.includes('.xml') || url.includes('feed.')) return 'podcast'
    if (url.includes('youtube.com') || url.includes('youtu.be')) return 'youtube'
    // 尝试从channel判断
    const chUrl = video?.channel_url || video?.channel_id || ''
    if (chUrl.includes('xyzfm') || chUrl.includes('xiaoyuzhou') || chUrl.includes('.xml') || chUrl.includes('feed.')) return 'podcast'
    return 'youtube'
  }

  const fetchChannels = async (auth) => {
    setChannelsLoading(true)
    const header = auth || authHeader
    const res = await fetch(`${API_URL}/channels`, { headers: header })
    const data = await res.json()
    setChannels(data)
    setChannelsLoading(false)
  }

  const fetchVideos = async (auth) => {
    setVideosLoading(true)
    const header = auth || authHeader
    console.log('Fetching videos, header:', header)
    try {
      const res = await fetch(`${API_URL}/videos`, { headers: header })
      if (!res.ok) {
        console.error('Fetch failed:', res.status)
        setVideos([])
      } else {
        const data = await res.json()
        console.log('Videos fetched:', data.length)
        setVideos(data)
      }
    } catch (err) {
      console.error('Fetch error:', err)
      setVideos([])
    }
    setVideosLoading(false)
  }

  const addChannel = async (e) => {
    e.preventDefault()
    if (!newUrl) return
    setChecking(true)
    setChannelError('')
    try {
      const res = await fetch(`${API_URL}/channels`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeader },
        body: JSON.stringify({ channel_url: newUrl })
      })
      const data = await res.json()
      if (!res.ok) {
        setChannelError(data.detail || '添加失败，请检查链接是否正确')
        setChecking(false)
        return
      }
      setNewUrl('')
      setShowAddChannelModal(false)
      fetchChannels()
      fetchVideos()  // 刷新视频列表
    } catch (err) {
      setChannelError('添加失败，请稍后重试')
    }
    setChecking(false)
  }

  const deleteChannel = async (id, name) => {
    if (!confirm(`确定删除频道"${name}"及其所有视频？`)) return
    await fetch(`${API_URL}/channels/${id}`, { method: 'DELETE', headers: authHeader })
    fetchChannels()
  }

  const deleteVideo = async (id, title, e) => {
    e.stopPropagation()
    if (!confirm(`确定删除视频"${title}"？`)) return
    await fetch(`${API_URL}/videos/${id}`, { method: 'DELETE', headers: authHeader })
    fetchVideos()
    setMenuOpen(null)
  }

  const importOpml = async (e) => {
    e.preventDefault()
    const file = e.target.files?.[0]
    if (!file) return
    setImporting(true)
    setImportResult(null)
    try {
      const formData = new FormData()
      formData.append('file', file)
      const res = await fetch(`${API_URL}/import/opml`, {
        method: 'POST',
        headers: authHeader,
        body: formData
      })
      const result = await res.json()
      setImportResult(result)
      if (result.added > 0) {
        fetchChannels()
        fetchVideos()
      }
    } catch (err) {
      alert('导入失败')
    }
    setImporting(false)
  }

  const [addingVideo, setAddingVideo] = useState(null)
  const [videoUrl, setVideoUrl] = useState('')

  const addBilibiliVideo = async (e) => {
    e.preventDefault()
    if (!videoUrl || !addingVideo) return
    try {
      await fetch(`${API_URL}/videos/add`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeader },
        body: JSON.stringify({ video_url: videoUrl, channel_id: addingVideo })
      })
      setVideoUrl('')
      setAddingVideo(null)
      fetchVideos()
    } catch (err) {
      alert('添加失败')
    }
  }

  const selectVideo = async (video) => {
    // 取消之前的请求
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }
    abortControllerRef.current = new AbortController()

    // 保留传入的video对象自带的subtitles（而非当前modal的）
    const existingSubtitles = video.subtitles
    setSelectedVideo({ ...video, subtitles: existingSubtitles, loading: true })
    setSubtitlesLoading(true)

    // 标记已读（异步，不阻塞）
    if (video.has_new) {
      fetch(`${API_URL}/videos/${video.video_id}/read`, { method: 'POST', headers: authHeader })
      // 同步更新本地状态
      setVideos(videos.map(v => v.id === video.id ? { ...v, has_new: false } : v))
    }

    try {
      const res = await fetch(`${API_URL}/videos/by/${video.video_id}`, { headers: authHeader, signal: abortControllerRef.current.signal })
      const data = await res.json()
      // 使用函数式更新，确保保留已有的字幕
      setSelectedVideo(prev => ({
        ...video,
        ...data,
        subtitles: data.subtitles || existingSubtitles || (prev?.subtitles || ''),
        loading: false
      }))
    } catch (err) {
      if (err.name !== 'AbortError') {
        console.error(err)
      }
    }
    setSubtitlesLoading(false)
  }

  const closeModal = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      abortControllerRef.current = null
    }
    setSelectedVideo(null)
  }

  // 提取字幕
  const extractSubtitles = async () => {
    if (!selectedVideo || extracting) return
    setExtracting(true)

    try {
      const platform = getChannelPlatform(selectedVideo)

      // 获取video_id - 支持YouTube和podcast
      let videoId = selectedVideo.video_id || ''
      if (videoId.includes('yt:video:')) {
        videoId = videoId.replace('yt:video:', '')
      } else if (selectedVideo.url && platform === 'youtube') {
        const match = selectedVideo.url.match(/[?&]v=([^&]+)/)
        if (match) videoId = match[1]
      } else if (platform === 'podcast') {
        // podcast: 用video_id用于数据库匹配
        // audio_url从数据库获取传给API
      }

      const res = await fetch(`${API_URL}/subtitles/extract`, {
        method: 'POST',
        headers: { ...authHeader, 'Content-Type': 'application/json' },
        body: JSON.stringify({ video_id: videoId, audio_url: selectedVideo.audio_url || '' })
      })

      if (res.ok) {
        const data = await res.json()
        if (data.subtitles) {
          setSelectedVideo(prev => {
            if (!prev) return null
            return {
              ...prev,
              subtitles: data.subtitles || prev.subtitles || ''
            }
          })
        } else if (data.jobId) {
          // 异步任务，轮询结果
          pollJob(data.jobId, videoId)
        } else if (data.status === 'processing') {
          pollJob(data.jobId || data.jobId, videoId)
        } else if (data.error) {
          alert(data.error)
        }
      } else {
        const data = await res.json().catch(() => ({}))
        const msg = data?.detail || data?.error || '提取失败'
        if (msg.includes('Subtitles are disabled')) {
          alert('该视频未启用字幕，无法提取')
        } else if (msg.includes('no transcripts')) {
          alert('该视频没有可用字幕')
        } else {
          alert('提取失败: ' + msg)
        }
      }
    } catch (err) {
      console.error(err)
      alert('提取失败')
    }
    setExtracting(false)
  }

  // 轮询异步任务
  const pollJob = async (jobId, videoId) => {
    if (!videoId) videoId = selectedVideo?.video_id || ''
    // 持续轮询直到完成
    for (let i = 0; i < 60; i++) {  // 最多5分钟
      await new Promise(r => setTimeout(r, 5000))
      try {
        const res = await fetch(`${API_URL}/subtitles/poll/${jobId}?video_id=${encodeURIComponent(videoId)}`, { headers: authHeader })
        if (!res.ok) {
          const text = await res.text()
          if (text.includes('<!DOCTYPE html>')) {
            // 服务端错误，继续等待
            continue
          }
          setExtracting(false)
          alert('提取失败，请稍后重试')
          return
        }
        const data = await res.json()
        if (data.status === 'completed') {
          setSelectedVideo(prev => {
            if (!prev) return null
            return {
              ...prev,
              subtitles: data.subtitles || prev.subtitles || '',
              api_subtitles: data.api_subtitles || data.subtitles || ''
            }
          })
          setExtracting(false)
          alert('字幕提取完成')
          return
        } else if (data.status === 'error') {
          setExtracting(false)
          alert('提取失败: ' + (data.message || '未知错误'))
          return
        } else if (data.status === 'failed') {
          setExtracting(false)
          alert('提取失败：音频文件不可用，可能已失效或需要登录')
          return
        }
        // status === 'active' 继续等待
      } catch (e) {
        // 网络错误继续等待
      }
    }
    setExtracting(false)
    alert('字幕提取超时，请稍后重试')
  }

  const checkNow = async () => {
    setChecking(true)
    await fetch(`${API_URL}/check`, { method: 'POST', headers: authHeader })
    fetchVideos()
    setChecking(false)
  }

  const [showSettings, setShowSettings] = useState(false)
  const [youtubeApiKey, setYoutubeApiKey] = useState('')
  const [showImport, setShowImport] = useState(false)
  const [importing, setImporting] = useState(false)
  const [importResult, setImportResult] = useState(null)
  const [initialFetched, setInitialFetched] = useState(false)

  // 筛选状态
  const [filterDateFrom, setFilterDateFrom] = useState('')
  const [filterDateTo, setFilterDateTo] = useState('')
  const [filterChannel, setFilterChannel] = useState('')
  const [filterPlatform, setFilterPlatform] = useState('')
  const [subtitleTab, setSubtitleTab] = useState('cleaned')  // cleaned 或 raw

  // 筛选后的视频
  const filteredVideos = videos.filter(v => {
    // 日期筛选
    if (filterDateFrom && v.published_at && v.published_at < filterDateFrom) return false
    if (filterDateTo && v.published_at && v.published_at > filterDateTo) return false
    // 频道名筛选
    if (filterChannel && !v.channel_name?.toLowerCase().includes(filterChannel.toLowerCase())) return false
    // 平台筛选
    if (filterPlatform) {
      const platform = getChannelPlatform(v)
      if (platform !== filterPlatform) return false
    }
    return true
  })

  useEffect(() => {
    const initUser = async () => {
      console.log('Initializing user...')

      // Supabase需要恢复session，可能需要等待
      let u = await getCurrentUser()
      let retries = 0
      while (!u && retries < 5) {
        await new Promise(r => setTimeout(r, 500))
        u = await getCurrentUser()
        retries++
        console.log('Retry', retries, 'user:', u?.id)
      }

      console.log('User loaded:', u?.id)
      setUser(u)
      setLoading(false)

      if (u) {
        const header = { 'Authorization': u.id }
        setAuthHeader(header)
        console.log('Setting authHeader:', header)
        // 同步用户信息到数据库
        await fetch(`${API_URL}/sync_user`, {
          method: 'POST',
          headers: { ...header, 'Content-Type': 'application/json' },
          body: JSON.stringify({
            user_email: u.email,
            user_name: u.user_metadata?.full_name
          })
        })
        await fetchChannels(header)
        await fetchVideos(header)
        await fetch(`${API_URL}/settings`, { headers: header }).then(r => r.json()).then(d => {
          if (d.youtube_api_key) setYoutubeApiKey(d.youtube_api_key)
        })
        setInitialFetched(true)
      }
    }

    initUser()
  }, [])

  const handleLogin = async () => {
    const { error } = await signInWithGoogle()
    if (error) alert('登录失败: ' + error.message)
  }

  const handleLogout = async () => {
    await signOut()
    setUser(null)
    setChannels([])
    setVideos([])
    setInitialFetched(false)
    setAuthHeader({})
  }

  const saveSettings = async () => {
    try {
      const res = await fetch(`${API_URL}/settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...authHeader },
        body: JSON.stringify({
          youtube_api_key: youtubeApiKey.trim() || null
        })
      })
      if (res.ok) {
        setShowSettings(false)
        alert('设置已保存')
      } else {
        alert('保存失败')
      }
    } catch (err) {
      console.error(err)
      alert('保存失败: ' + err.message)
    }
  }

  const newVideosCount = videos.filter(v => v.has_new).length

  if (loading) {
    return (
      <div className="app" style={{display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh', background: '#ffffff'}}>
        <div style={{display: 'flex', alignItems: 'center', gap: 4}}>
          <span style={{fontSize: 24, color: '#1a1a1a'}}>▶</span>
          <h1 style={{fontFamily: 'Inter, sans-serif', fontSize: 24, fontWeight: 600, color: '#1a1a1a', letterSpacing: '0.02em'}}>Only Subs</h1>
        </div>
        <div style={{display: 'flex', gap: 8, marginLeft: 16}}>
          <span style={{width: 8, height: 8, borderRadius: '50%', background: '#d1d1d1', animation: 'dot 0.6s infinite'}} />
          <span style={{width: 8, height: 8, borderRadius: '50%', background: '#d1d1d1', animation: 'dot 0.6s infinite 0.2s'}} />
          <span style={{width: 8, height: 8, borderRadius: '50%', background: '#d1d1d1', animation: 'dot 0.6s infinite 0.4s'}} />
        </div>
        <style>{`@keyframes dot { 0%, 100% { opacity: 0; } 50% { opacity: 1; } }`}</style>
      </div>
    )
  }

  if (!user) {
    return (
      <div className="login-screen">
        <div className="login-box">
          <h1>Only Subs</h1>
          {!showEmailLogin ? (
            <>
              <p>登录您的账号以同步您的订阅数据</p>
              <button onClick={handleLogin} className="login-btn">
                使用Google登录
              </button>
              <button onClick={() => setShowEmailLogin(true)} className="login-btn">
                使用邮箱登录
              </button>
              <button onClick={() => setUser({ id: 'guest' })} className="guest-btn">
                游客入口
              </button>
            </>
          ) : (
            <>
              <p>{loginMode === 'login' ? '登录您的邮箱账号' : '注册新账号'}</p>
              <div className="add-form">
                <input
                  type="email"
                  placeholder="邮箱"
                  value={loginEmail}
                  onChange={e => setLoginEmail(e.target.value)}
                />
                <input
                  type="password"
                  placeholder="密码"
                  value={loginPassword}
                  onChange={e => setLoginPassword(e.target.value)}
                />
                {emailLoginError && <p className="error-message">{emailLoginError}</p>}
                <button
                  onClick={async () => {
                    setEmailLoginError('')
                    if (!loginEmail || !loginPassword) {
                      setEmailLoginError('请输入邮箱和密码')
                      return
                    }
                    try {
                      const result = loginMode === 'signup'
                        ? await signUpWithEmail(loginEmail, loginPassword)
                        : await signInWithEmail(loginEmail, loginPassword)
                      if (result.error) {
                        setEmailLoginError(result.error.message)
                      } else if (loginMode === 'signup' && result.data?.user?.email) {
                        setEmailLoginError('注册成功！请查收邮箱验证链接')
                      } else if (loginMode === 'login' && result.data?.user) {
                        // 登录成功，刷新页面让 Supabase 自动恢复 session
                        window.location.reload()
                      }
                    } catch (e) {
                      setEmailLoginError(e.message)
                    }
                  }}
                >
                  {loginMode === 'login' ? '登录' : '注册'}
                </button>
                <button
                  onClick={() => setLoginMode(loginMode === 'login' ? 'signup' : 'login')}
                  className="guest-btn"
                >
                  {loginMode === 'login' ? '没有账号？去注册' : '已有账号？去登录'}
                </button>
                <button onClick={() => setShowEmailLogin(false)} className="guest-btn">
                  返回
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="app">
      {/* 顶部导航条 */}
      <div className="top-nav">
        <div className="nav-left">
          <span className="logo-icon">▶</span>
          <span className="nav-logo">Only Subs</span>
        </div>
        <div className="nav-right">
          <button className="logout-btn" onClick={() => setShowSettings(true)} title="设置">⚙</button>
          <img src={user.user_metadata?.avatar_url || 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 40"><rect width="40" height="40" rx="8" fill="%23F7F7F5"/><text x="20" y="28" font-size="22" text-anchor="middle">🙂</text></svg>'} alt="" className="user-avatar" />
          <span className="user-id" title={user.email}>{user.user_metadata?.full_name || user.email?.split('@')[0]}</span>
          <button className="logout-btn" onClick={handleLogout} title="退出登录">退出</button>
        </div>
      </div>

      {/* 侧边栏内容 */}
      <div className="sidebar">
        {/* 新增订阅区域 */}
        <div className="add-subscribe-section">
          <button
            className="add-channel-btn youtube"
            onClick={() => { setShowAddChannelModal(true); setNewUrl(''); setChannelError(''); }}
          >
            + YouTube 频道
          </button>
          <button
            className="add-channel-btn podcast"
            onClick={() => { setShowImport(true); }}
          >
            + 小宇宙播客
          </button>
        </div>

        {/* 检查更新按钮 */}
        <button className="refresh-btn" onClick={checkNow} disabled={checking}>
          {checking ? (
            <>
              <span className="btn-spinner"></span>
              检查中
            </>
          ) : (
            <>
              <span>↻</span> 检查更新
            </>
          )}
        </button>

        <div className="section-title">订阅的频道</div>

        {channelsLoading ? (
          <div style={{display: 'flex', justifyContent: 'center', padding: 20}}>
            <div style={{display: 'flex', gap: 4}}>
              <span style={{width: 6, height: 6, borderRadius: '50%', background: '#d1d1d1', animation: 'dot 0.6s infinite'}} />
              <span style={{width: 6, height: 6, borderRadius: '50%', background: '#d1d1d1', animation: 'dot 0.6s infinite 0.2s'}} />
              <span style={{width: 6, height: 6, borderRadius: '50%', background: '#d1d1d1', animation: 'dot 0.6s infinite 0.4s'}} />
            </div>
          </div>
        ) : (
        <ul className="channel-list">
          {channels.map((ch) => {
            const platform = ch.channel_url?.includes('bilibili') ? 'bilibili' :
                        ch.channel_url?.includes('xyzfm') || ch.channel_url?.includes('feed.') ? 'podcast' : 'youtube'
            return (
            <li key={ch.id} className="channel-item">
              <div
                className="channel-avatar"
              >
                {((ch.custom_name || ch.channel_name || '?')[0]).toUpperCase()}
              </div>
              <div className="channel-info">
                <span className="channel-name">
                  {(ch.custom_name || ch.channel_name || '?')}
                </span>
                {ch.message && (
                  <span className="channel-hint">{ch.message}</span>
                )}
              </div>
              {platform === 'bilibili' && (
                <button
                  className="add-video-btn"
                  onClick={(e) => { e.stopPropagation(); setAddingVideo(ch.id) }}
                  title="添加B站视频"
                >
                  +
                </button>
              )}
              <button className="delete-btn" onClick={() => deleteChannel(ch.id, ch.channel_name || ch.custom_name || '?')}>×</button>
            </li>
          )})}
          {channels.length === 0 && (
            <li className="empty-tip">暂无订阅，点击上方添加</li>
          )}
        </ul>
        )}

        {addingVideo && (
          <form className="add-video-form" onSubmit={addBilibiliVideo}>
            <input
              type="text"
              placeholder="输入 B站视频链接..."
              value={videoUrl}
              onChange={(e) => setVideoUrl(e.target.value)}
            />
            <button type="submit">添加</button>
            <button type="button" onClick={() => setAddingVideo(null)}>×</button>
          </form>
        )}
      </div>

      <div className="main">
        {/* 筛选栏 */}
        <div className="filter-bar">
          <input
            type="date"
            placeholder="从"
            value={filterDateFrom}
            onChange={(e) => setFilterDateFrom(e.target.value)}
            className="filter-input"
          />
          <span className="filter-separator">至</span>
          <input
            type="date"
            placeholder="至"
            value={filterDateTo}
            onChange={(e) => setFilterDateTo(e.target.value)}
            className="filter-input"
          />
          <select
            value={filterChannel}
            onChange={(e) => setFilterChannel(e.target.value)}
            className="filter-input"
          >
            <option value="">全部频道</option>
            {channels.map(ch => (
              <option key={ch.id} value={ch.channel_name}>{ch.channel_name}</option>
            ))}
          </select>
          <select
            value={filterPlatform}
            onChange={(e) => setFilterPlatform(e.target.value)}
            className="filter-input"
          >
            <option value="">全部平台</option>
            <option value="youtube">YouTube</option>
            <option value="podcast">播客</option>
          </select>
          {(filterDateFrom || filterDateTo || filterChannel || filterPlatform) && (
            <button className="filter-clear" onClick={() => {
              setFilterDateFrom('')
              setFilterDateTo('')
              setFilterChannel('')
              setFilterPlatform('')
            }}>
              清除筛选
            </button>
          )}
        </div>

        <div className="video-grid">
          {videosLoading ? (
            <div className="empty-state">
              <div className="loading-spinner"></div>
              <div>加载中...</div>
            </div>
          ) : filteredVideos.length === 0 ? (
            <div className="empty-state">
              <div className="empty-icon">📺</div>
              <div>{videos.length === 0 ? '暂无视频' : '无筛选结果'}</div>
              <div className="empty-sub">{videos.length === 0 ? '添加频道后会显示最新视频' : '调整筛选条件'}</div>
            </div>
          ) : (
            filteredVideos.map((video) => {
            const platform = getChannelPlatform(video)
            const duration = video.duration || 0
            const showDuration = (platform === 'youtube' || platform === 'bilibili' || platform === 'podcast') && duration > 0
            return (
              <div
                key={video.id}
                className="video-card"
                onClick={() => selectVideo(video)}
              >
                <div className="thumbnail-wrapper">
                  {video.thumbnail && (
                    <img src={getThumbnail(video.thumbnail)} alt={video.title} />
                  )}
                  {showDuration && <div className="duration">{Math.floor(duration / 60)}:{String(duration % 60).padStart(2, '0')}</div>}
                  <button
                    className="video-menu-btn"
                    onClick={(e) => { e.stopPropagation(); setMenuOpen(menuOpen === video.id ? null : video.id) }}
                  >...</button>
                  {menuOpen === video.id && (
                    <div className="video-menu" onClick={(e) => e.stopPropagation()}>
                      <button onClick={(e) => deleteVideo(video.id, video.title, e)}>删除</button>
                    </div>
                  )}
                </div>
                <div className="video-content">
                  <div className="video-title">{video.title}</div>
                  <div style={{ flex: 1 }} />
                  <div className="video-meta">
                    <span className="channel-tag" title={video.channel_name}>
                      {(video.channel_name || '')[0]?.toUpperCase() || '?'}
                    </span>
                    <span className="video-date">{platform === 'podcast' ? (video.published_at || '最新') : video.published_at?.split('T')[0]}</span>
                  </div>
                </div>
              </div>
            )})
          )}
        </div>
      </div>

      {selectedVideo && (
        <div className="modal-overlay" onClick={closeModal}>
          <div className="modal video-modal" onClick={(e) => e.stopPropagation()}>
            <button className="close-btn" onClick={closeModal}>×</button>

            <div className="modal-header">
              <h2>{selectedVideo.title}</h2>
              {getChannelPlatform(selectedVideo) === 'podcast' ? (
                selectedVideo.url ? (
                  <a href={selectedVideo.url} target="_blank" rel="noopener noreferrer" className="yt-link">
                    播放 ↗
                  </a>
                ) : (
                  <span className="yt-link" style={{opacity: 0.5}}>无音频</span>
                )
              ) : (
                <a href={selectedVideo.url} target="_blank" rel="noopener noreferrer" className="yt-link">
                  {getChannelPlatform(selectedVideo) === 'bilibili' ? '在B站打开 ↗' : ' 在YouTube打开 ↗'}
                </a>
              )}
            </div>

            <div className="modal-tabs">
              <button
                className={`tab-btn ${modalTab === 'overview' ? 'active' : ''}`}
                onClick={() => setModalTab('overview')}
              >
                概览
              </button>
              <button
                className={`tab-btn ${modalTab === 'content' ? 'active' : ''}`}
                onClick={() => setModalTab('content')}
              >
                内容
              </button>
            </div>

            <div className="modal-content">
              {modalTab === 'overview' ? (
                <div className="overview-panel">
                  <div className="detail-row">
                    <span className="detail-label">频道</span>
                    <span>{selectedVideo.channel_name || '-'}</span>
                  </div>
                  <div className="detail-row">
                    <span className="detail-label">发布</span>
                    <span>{selectedVideo.published_at || '-'}</span>
                  </div>
                  {selectedVideo.description && (
                    <div className="detail-row">
                      <span className="detail-label">简介</span>
                      <p className="detail-desc">{selectedVideo.description}</p>
                    </div>
                  )}
                </div>
              ) : (
                <div className="content-panel">
                  {getChannelPlatform(selectedVideo) === 'podcast' ? (
                    selectedVideo.audio_url ? (
                      <div className="detail-row audio-row">
                        <audio controls src={selectedVideo.audio_url} className="audio-player" />
                      </div>
                    ) : null
                  ) : null}
                  {selectedVideo.subtitles || selectedVideo.api_subtitles ? (
                    <div>
                      {selectedVideo.job_id && (
                        <div style={{fontSize: 11, color: '#888', marginBottom: 4}}>
                          job: {selectedVideo.job_id} {selectedVideo.status && ` (${selectedVideo.status})`}
                        </div>
                      )}
                      <div className="subtitle-tabs">
                        <button
                          className={`subtitle-tab ${subtitleTab === 'cleaned' ? 'active' : ''}`}
                          onClick={() => setSubtitleTab('cleaned')}
                        >
                          清洗后
                        </button>
                        <button
                          className={`subtitle-tab ${subtitleTab === 'raw' ? 'active' : ''}`}
                          onClick={() => setSubtitleTab('raw')}
                        >
                          原始
                        </button>
                      </div>
                      <pre className="transcript-text">
                        {subtitleTab === 'raw' ? selectedVideo.api_subtitles : selectedVideo.subtitles}
                      </pre>
                    </div>
                  ) : (
                    <div className="no-content">
                      <div>暂无文字内容</div>
                      <button
                        className="extract-btn"
                        onClick={extractSubtitles}
                        disabled={extracting || !['youtube', 'podcast'].includes(getChannelPlatform(selectedVideo))}
                      >
                        {extracting ? '提取中...' : '提取文字内容'}
                      </button>
                      {extracting && <div style={{fontSize: 12, color: '#888', marginTop: 4}}>正在提取播客音频，请稍候...</div>}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {showSettings && (
        <div className="modal-overlay" onClick={() => setShowSettings(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <button className="close-btn" onClick={() => setShowSettings(false)}>×</button>
            <h2>设置</h2>
            <p className="settings-tip">
              API Key (用于获取YouTube字幕，推荐 supadata.ai)<br/>
              注册: https://supadata.ai
            </p>
            <input
              type="text"
              placeholder="粘贴YouTube API Key（可选）..."
              value={youtubeApiKey}
              onChange={(e) => setYoutubeApiKey(e.target.value)}
              className="settings-input"
            />
            <button onClick={saveSettings} className="settings-save-btn">保存</button>
          </div>
        </div>
      )}

      {showImport && (
        <div className="modal-overlay" onClick={() => setShowImport(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <button className="close-btn" onClick={() => setShowImport(false)}>×</button>
            <h2>导入播客订阅</h2>
            <p className="settings-tip">
              选择小宇宙导出的 OPML 文件批量添加播客订阅
            </p>
            <input
              type="file"
              accept=".opml,.xml"
              onChange={importOpml}
              disabled={importing}
              className="settings-input"
            />
            {importing && <div className="loading-spinner" style={{marginTop: 8}} />}
            {importResult && (
              <div className="import-result">
                {importResult.channels?.length > 0 && (
                  <p>成功导入 {importResult.channels.length} 个播客：
                    {importResult.channels.map(c => c.channel_name).join('、')}</p>
                )}
                {importResult.errors?.length > 0 && (
                  <p className="error">失败 {importResult.errors.length} 个：
                    {importResult.errors.map(e => e.split(':')[0]).join('、')}</p>
                )}
                <button
                  onClick={() => {
                    setShowImport(false)
                    fetchChannels()
                    fetchVideos()
                  }}
                  className="settings-save-btn"
                >
                  确定
                </button>
              </div>
            )}
          </div>
        </div>
      )}
      {showAddChannelModal && (
        <div className="modal-overlay" onClick={() => { setShowAddChannelModal(false); setChannelError(''); }}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <button className="close-btn" onClick={() => setShowAddChannelModal(false)}>×</button>
            <h2>添加 YouTube 频道</h2>
            <p className="settings-tip">
              请粘贴想订阅的YouTube频道主页链接
            </p>
            {channelError && <p className="error-message">{channelError}</p>}
            <form onSubmit={addChannel} className="add-form">
              <input
                type="text"
                placeholder="粘贴链接..."
                value={newUrl}
                onChange={(e) => setNewUrl(e.target.value)}
                disabled={checking}
                className="settings-input"
              />
              <button type="submit" disabled={checking || !newUrl} className="settings-save-btn">
                {checking ? '添加中...' : '添加'}
              </button>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}

export default App
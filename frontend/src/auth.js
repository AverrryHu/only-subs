import { createClient } from '@supabase/supabase-js'

const supabaseUrl = 'https://oguxjqmhsctolgzbkegy.supabase.co'
const supabaseKey = 'sb_publishable_XhAMOQXhYLVlvVywa59zDw_lXCKfNhc'

export const supabase = createClient(supabaseUrl, supabaseKey)

export const signInWithGoogle = async () => {
  const { data, error } = await supabase.auth.signInWithOAuth({
    provider: 'google',
    options: {
      redirectTo: window.location.origin,
      prompt: 'select_account'  // 强制选择账户
    }
  })
  return { data, error }
}

export const signUpWithEmail = async (email, password) => {
  const { data, error } = await supabase.auth.signUp({
    email,
    password,
    options: {
      emailRedirectTo: window.location.origin
    }
  })
  return { data, error }
}

export const signInWithEmail = async (email, password) => {
  const { data, error } = await supabase.auth.signInWithPassword({
    email,
    password
  })
  return { data, error }
}

export const signOut = async () => {
  // 清除所有可能存储的session
  sessionStorage.clear()
  localStorage.removeItem('supabase.auth.token')
  localStorage.removeItem('supabase-refresh-token')
  localStorage.removeItem('supabase-access-token')

  // 清除其他可能的key
  for (let key in localStorage) {
    if (key.includes('supabase') || key.includes('auth')) {
      localStorage.removeItem(key)
    }
  }

  // 清除所有cookie
  document.cookie.split(';').forEach(c => {
    document.cookie = c.replace(/^ +/, '').replace(/=.*/, '=;expires=Thu, 01 Jan 1970 00:00:00 UTC;path=/')
  })

  const { error } = await supabase.auth.signOut()
  return { error }
}

export const getCurrentUser = async () => {
  const { data: { user } } = await supabase.auth.getUser()
  return user
}

export const getSession = async () => {
  const { data: { session } } = await supabase.auth.getSession()
  return session
}

export const onAuthStateChange = (callback) => {
  return supabase.auth.onAuthStateChange(callback)
}
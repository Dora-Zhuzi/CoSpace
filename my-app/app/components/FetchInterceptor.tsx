'use client'

import { useEffect } from 'react'

/**
 * 全局拦截 fetch：任何 API 请求返回 401（token 失效/用户不存在）时，
 * 清除 token 并跳转登录页。排除登录/注册接口本身，避免吞掉其错误提示。
 */
export default function FetchInterceptor() {
  useEffect(() => {
    const orig = window.fetch
    window.fetch = async (...args) => {
      const res = await orig(...args)
      try {
        const input = args[0]
        const url =
          typeof input === 'string'
            ? input
            : input instanceof Request
            ? input.url
            : String(input)
        const isAuthEndpoint =
          url.includes('/auth/login') || url.includes('/auth/register')
        if (
          res.status === 401 &&
          !isAuthEndpoint &&
          !window.location.pathname.startsWith('/login')
        ) {
          document.cookie = 'token=; path=/; max-age=0'
          const from = encodeURIComponent(
            window.location.pathname + window.location.search,
          )
          window.location.href = `/login?from=${from}`
        }
      } catch {
        /* 忽略，原样返回响应 */
      }
      return res
    }
    return () => {
      window.fetch = orig
    }
  }, [])

  return null
}

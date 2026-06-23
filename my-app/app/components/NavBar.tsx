'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'

const NAV_ITEMS = [
  { label: '工作台', href: '/workspace' },
  { label: '素材库', href: '/materials' },
]

export default function NavBar() {
  const pathname = usePathname()

  return (
    <nav className="h-12 flex items-center px-6 gap-6 shrink-0" style={{ backgroundColor: '#D1EEEE' }}>
      <span className="font-semibold text-sm text-gray-900 mr-4">CoSpace</span>
      {NAV_ITEMS.map(({ label, href }) => {
        const active = pathname === href || (href !== '/' && pathname.startsWith(href))
        return (
          <Link
            key={href}
            href={href}
            className={`text-sm transition-colors ${
              active
                ? 'text-blue-600 font-medium'
                : 'text-gray-500 hover:text-gray-900'
            }`}
          >
            {label}
          </Link>
        )
      })}
    </nav>
  )
}

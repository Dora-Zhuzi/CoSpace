'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import RenameModal from '@/app/components/RenameModal'
import ConfirmModal from '@/app/components/ConfirmModal'

const API = process.env.NEXT_PUBLIC_API_URL

interface Project {
  id: string
  name: string
  folder_id: string
  created_at: string
}

interface Folder {
  id: string
  name: string
}

function getToken() {
  if (typeof document === 'undefined') return ''
  const match = document.cookie.match(/(?:^|;\s*)token=([^;]*)/)
  return match ? match[1] : ''
}

function authHeaders() {
  return { Authorization: `Bearer ${getToken()}` }
}

function AddCard({ onClick }: { onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="group aspect-square w-full rounded-2xl border-2 border-dashed border-gray-200 hover:border-teal-300 hover:bg-teal-50/40 transition-all flex flex-col items-center justify-center gap-3 text-gray-400 hover:text-teal-500"
    >
      <div className="w-12 h-12 rounded-full bg-gray-100 group-hover:bg-teal-100 flex items-center justify-center transition-colors">
        <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 5v14m-7-7h14" />
        </svg>
      </div>
      <span className="text-sm font-medium">新建项目</span>
    </button>
  )
}

export default function WorkspacePage() {
  const router = useRouter()
  const [projects, setProjects] = useState<Project[]>([])
  const [creating, setCreating] = useState(false)
  const [folders, setFolders] = useState<Folder[]>([])
  const [form, setForm] = useState({ name: '', folder_id: '' })
  const [renaming, setRenaming] = useState<Project | null>(null)
  const [deleting, setDeleting] = useState<Project | null>(null)

  async function fetchProjects() {
    const res = await fetch(`${API}/projects`, { headers: authHeaders() })
    if (res.ok) setProjects(await res.json())
  }

  async function openCreateDialog() {
    const fRes = await fetch(`${API}/projects/available-folders`, { headers: authHeaders() })
    if (fRes.ok) setFolders(await fRes.json())
    setForm({ name: '', folder_id: '' })
    setCreating(true)
  }

  async function handleCreate() {
    if (!form.name.trim() || !form.folder_id) return
    const res = await fetch(`${API}/projects`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify(form),
    })
    if (res.ok) {
      setCreating(false)
      fetchProjects()
    }
  }

  async function handleDelete(id: string) {
    await fetch(`${API}/projects/${id}`, { method: 'DELETE', headers: authHeaders() })
    fetchProjects()
  }

  async function handleRename(id: string, name: string) {
    const res = await fetch(`${API}/projects/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', ...authHeaders() },
      body: JSON.stringify({ name }),
    })
    if (res.ok) {
      setRenaming(null)
      fetchProjects()
    }
  }

  useEffect(() => { fetchProjects() }, [])

  return (
    <div className="min-h-[calc(100vh-48px)]" style={{ backgroundColor: '#D1EEEE' }}>
      <div className="pl-28 pr-6 pt-16 pb-8">
      {projects.length === 0 && !creating ? (
        <div className="min-h-[55vh] flex items-center justify-center">
          <div className="w-[150px]">
            <AddCard onClick={openCreateDialog} />
          </div>
        </div>
      ) : (
        <div
          className="grid gap-5"
          style={{ gridTemplateColumns: 'repeat(auto-fill, 150px)' }}
        >
          {projects.map((project) => {
            return (
              <div
                key={project.id}
                onClick={() => router.push(`/workspace/${project.id}`)}
                className="group relative aspect-square rounded-2xl bg-white border border-gray-100 shadow-sm hover:shadow-xl hover:-translate-y-1 transition-all flex flex-col items-center justify-center gap-3 p-4 cursor-pointer select-none"
              >
                <div
                  className="w-16 h-16 rounded-2xl flex items-center justify-center shadow-sm group-hover:scale-105 transition-transform"
                  style={{ background: 'linear-gradient(135deg,#34D399,#0D9488)' }}
                >
                  <svg className="w-8 h-8" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round">
                    <rect x="9" y="3" width="6" height="4" rx="1" />
                    <rect x="2.5" y="16" width="6" height="4" rx="1" />
                    <rect x="15.5" y="16" width="6" height="4" rx="1" />
                    <path d="M12 7V13M5.5 16V13H18.5V16" />
                  </svg>
                </div>
                <span className="text-sm font-medium text-gray-700 truncate w-full text-center">
                  {project.name}
                </span>

                <div className="absolute top-2 right-2 flex gap-1 opacity-0 group-hover:opacity-100 transition-all">
                  <button
                    onClick={(e) => { e.stopPropagation(); setRenaming(project) }}
                    title="重命名"
                    className="w-7 h-7 rounded-full flex items-center justify-center text-gray-300 hover:text-teal-600 hover:bg-teal-50 transition-colors"
                  >
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931z" />
                    </svg>
                  </button>
                  <button
                    onClick={(e) => { e.stopPropagation(); setDeleting(project) }}
                    title="删除"
                    className="w-7 h-7 rounded-full flex items-center justify-center text-gray-300 hover:text-red-500 hover:bg-red-50 transition-colors"
                  >
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M7 7h10l-1 12a1 1 0 01-1 1H9a1 1 0 01-1-1L7 7z" />
                    </svg>
                  </button>
                </div>
              </div>
            )
          })}

          <AddCard onClick={openCreateDialog} />
        </div>
      )}

      {/* 新建项目弹窗 */}
      {creating && (
        <div
          className="fixed inset-0 bg-black/40 backdrop-blur-sm flex items-center justify-center z-50 p-4"
          onClick={() => setCreating(false)}
        >
          <div
            className="bg-white rounded-3xl shadow-2xl p-7 w-full max-w-md"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center gap-3 mb-5">
              <div
                className="w-10 h-10 rounded-xl flex items-center justify-center shadow-sm"
                style={{ background: 'linear-gradient(135deg,#34D399,#0D9488)' }}
              >
                <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round">
                  <rect x="9" y="3" width="6" height="4" rx="1" />
                  <rect x="2.5" y="16" width="6" height="4" rx="1" />
                  <rect x="15.5" y="16" width="6" height="4" rx="1" />
                  <path d="M12 7V13M5.5 16V13H18.5V16" />
                </svg>
              </div>
              <h2 className="text-base font-semibold text-gray-800">新建项目</h2>
            </div>

            <div className="space-y-3">
              <div>
                <label className="block text-sm text-gray-600 mb-1">项目名称</label>
                <input
                  autoFocus
                  type="text"
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm outline-none focus:ring-2 focus:ring-teal-400 focus:border-transparent"
                />
              </div>
              <div>
                <label className="block text-sm text-gray-600 mb-1">选择素材库</label>
                <select
                  value={form.folder_id}
                  onChange={(e) => setForm({ ...form, folder_id: e.target.value })}
                  className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm outline-none focus:ring-2 focus:ring-teal-400 focus:border-transparent bg-white"
                >
                  <option value="">请选择</option>
                  {folders.map((f) => (
                    <option key={f.id} value={f.id}>{f.name}</option>
                  ))}
                </select>
                {folders.length === 0 && (
                  <p className="text-xs text-gray-400 mt-1">暂无可用素材库（需所有文件入库完成）</p>
                )}
              </div>
            </div>

            <div className="flex justify-end gap-2 mt-6">
              <button
                onClick={() => setCreating(false)}
                className="px-4 py-2 text-sm text-gray-500 hover:text-gray-700 rounded-lg hover:bg-gray-100 transition-colors"
              >
                取消
              </button>
              <button
                onClick={handleCreate}
                disabled={!form.name.trim() || !form.folder_id}
                className="px-5 py-2 text-sm bg-teal-600 text-white rounded-lg hover:bg-teal-700 disabled:opacity-50 shadow-sm transition-colors"
              >
                创建
              </button>
            </div>
          </div>
        </div>
      )}

      {renaming && (
        <RenameModal
          title="重命名项目"
          initial={renaming.name}
          onCancel={() => setRenaming(null)}
          onSubmit={(name) => handleRename(renaming.id, name)}
        />
      )}

      {deleting && (
        <ConfirmModal
          title="删除项目"
          message={`确定删除项目"${deleting.name}"？该项目的讨论、写作方案、结构树和已生成文章将一并删除，且不可恢复。`}
          onCancel={() => setDeleting(null)}
          onConfirm={() => { handleDelete(deleting.id); setDeleting(null) }}
        />
      )}
      </div>
    </div>
  )
}

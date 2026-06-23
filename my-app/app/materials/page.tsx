'use client'

import { useEffect, useState } from 'react'
import FolderModal from '@/app/components/FolderModal'
import RenameModal from '@/app/components/RenameModal'
import ConfirmModal from '@/app/components/ConfirmModal'

const API = process.env.NEXT_PUBLIC_API_URL

interface Material {
  id: string
  filename: string
  status: 'uploading' | 'upload_failed' | 'upload_success' | 'indexing' | 'indexed' | 'index_failed'
  created_at: string
}

interface Folder {
  id: string
  name: string
  created_at: string
}

interface FolderDetail extends Folder {
  materials: Material[]
}

function getToken() {
  if (typeof document === 'undefined') return ''
  const match = document.cookie.match(/(?:^|;\s*)token=([^;]*)/)
  return match ? match[1] : ''
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
      <span className="text-sm font-medium">新建文件夹</span>
    </button>
  )
}

export default function MaterialsPage() {
  const [folders, setFolders] = useState<Folder[]>([])
  const [selectedFolder, setSelectedFolder] = useState<FolderDetail | null>(null)
  const [creating, setCreating] = useState(false)
  const [newName, setNewName] = useState('')
  const [renaming, setRenaming] = useState<Folder | null>(null)
  const [deleting, setDeleting] = useState<Folder | null>(null)

  async function fetchFolders() {
    const res = await fetch(`${API}/materials/folders`, {
      headers: { Authorization: `Bearer ${getToken()}` },
    })
    if (res.ok) setFolders(await res.json())
  }

  useEffect(() => { fetchFolders() }, [])

  async function handleCreate() {
    if (!newName.trim()) return
    const res = await fetch(`${API}/materials/folders`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${getToken()}`,
      },
      body: JSON.stringify({ name: newName.trim() }),
    })
    if (res.ok) {
      setNewName('')
      setCreating(false)
      fetchFolders()
    }
  }

  async function openFolder(id: string) {
    const res = await fetch(`${API}/materials/folders/${id}`, {
      headers: { Authorization: `Bearer ${getToken()}` },
    })
    if (res.ok) setSelectedFolder(await res.json())
  }

  async function handleRename(id: string, name: string) {
    const res = await fetch(`${API}/materials/folders/${id}`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${getToken()}`,
      },
      body: JSON.stringify({ name }),
    })
    if (res.ok) {
      setRenaming(null)
      fetchFolders()
    }
  }

  async function handleDeleteFolder(id: string) {
    const res = await fetch(`${API}/materials/folders/${id}`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${getToken()}` },
    })
    setDeleting(null)
    if (res.ok) {
      fetchFolders()
    } else {
      const data = await res.json().catch(() => ({}))
      alert(data.detail ?? '删除失败')
    }
  }

  return (
    <div className="min-h-[calc(100vh-48px)]" style={{ backgroundColor: '#D1EEEE' }}>
      <div className="pl-28 pr-6 pt-16 pb-8">
      {folders.length === 0 && !creating ? (
        <div className="min-h-[55vh] flex items-center justify-center">
          <div className="w-[150px]">
            <AddCard onClick={() => setCreating(true)} />
          </div>
        </div>
      ) : (
        <div
          className="grid gap-5"
          style={{ gridTemplateColumns: 'repeat(auto-fill, 150px)' }}
        >
          {folders.map((folder) => (
            <div
              key={folder.id}
              onClick={() => openFolder(folder.id)}
              className="group relative aspect-square rounded-2xl bg-white border border-gray-100 shadow-sm hover:shadow-xl hover:-translate-y-1 transition-all flex flex-col items-center justify-center gap-3 p-4 cursor-pointer select-none"
            >
              <div
                className="w-16 h-16 rounded-2xl flex items-center justify-center shadow-sm group-hover:scale-105 transition-transform"
                style={{ background: 'linear-gradient(135deg,#FEF3C7,#FBBF24)' }}
              >
                <svg className="w-8 h-8" viewBox="0 0 24 24" fill="white">
                  <rect x="8" y="3" width="9" height="6" rx="1" fill="white" opacity="0.55" /><path d="M3 8a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V8z" fill="white" />
                </svg>
              </div>
              <span className="text-sm font-medium text-gray-700 truncate w-full text-center">
                {folder.name}
              </span>

              <div className="absolute top-2 right-2 flex gap-1 opacity-0 group-hover:opacity-100 transition-all">
                <button
                  onClick={(e) => { e.stopPropagation(); setRenaming(folder) }}
                  title="重命名"
                  className="w-7 h-7 rounded-full flex items-center justify-center text-gray-300 hover:text-teal-600 hover:bg-teal-50 transition-colors"
                >
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931z" />
                  </svg>
                </button>
                <button
                  onClick={(e) => { e.stopPropagation(); setDeleting(folder) }}
                  title="删除"
                  className="w-7 h-7 rounded-full flex items-center justify-center text-gray-300 hover:text-red-500 hover:bg-red-50 transition-colors"
                >
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M7 7h10l-1 12a1 1 0 01-1 1H9a1 1 0 01-1-1L7 7z" />
                  </svg>
                </button>
              </div>
            </div>
          ))}

          <AddCard onClick={() => setCreating(true)} />
        </div>
      )}

      {/* 新建文件夹弹窗 */}
      {creating && (
        <div
          className="fixed inset-0 bg-black/40 backdrop-blur-sm flex items-center justify-center z-50 p-4"
          onClick={() => { setCreating(false); setNewName('') }}
        >
          <div
            className="bg-white rounded-3xl shadow-2xl p-7 w-full max-w-sm"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center gap-3 mb-5">
              <div
                className="w-10 h-10 rounded-xl flex items-center justify-center shadow-sm"
                style={{ background: 'linear-gradient(135deg,#FEF3C7,#FBBF24)' }}
              >
                <svg className="w-5 h-5" viewBox="0 0 24 24" fill="white">
                  <rect x="8" y="3" width="9" height="6" rx="1" fill="white" opacity="0.55" /><path d="M3 8a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V8z" fill="white" />
                </svg>
              </div>
              <h2 className="text-base font-semibold text-gray-800">新建文件夹</h2>
            </div>
            <input
              autoFocus
              type="text"
              placeholder="文件夹名称"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
              className="w-full border border-gray-200 rounded-xl px-3 py-2.5 text-sm outline-none focus:ring-2 focus:ring-teal-400 focus:border-transparent mb-5"
            />
            <div className="flex justify-end gap-2">
              <button
                onClick={() => { setCreating(false); setNewName('') }}
                className="px-4 py-2 text-sm text-gray-500 hover:text-gray-700 rounded-lg hover:bg-gray-100 transition-colors"
              >
                取消
              </button>
              <button
                onClick={handleCreate}
                disabled={!newName.trim()}
                className="px-5 py-2 text-sm bg-teal-600 text-white rounded-lg hover:bg-teal-700 disabled:opacity-50 shadow-sm transition-colors"
              >
                创建
              </button>
            </div>
          </div>
        </div>
      )}

      {selectedFolder && (
        <FolderModal
          folder={selectedFolder}
          onClose={() => setSelectedFolder(null)}
          onRefresh={() => openFolder(selectedFolder.id)}
          getToken={getToken}
        />
      )}

      {renaming && (
        <RenameModal
          title="重命名文件夹"
          initial={renaming.name}
          onCancel={() => setRenaming(null)}
          onSubmit={(name) => handleRename(renaming.id, name)}
        />
      )}

      {deleting && (
        <ConfirmModal
          title="删除素材库"
          message={`确定删除素材库"${deleting.name}"？其中的所有文件将一并删除，且不可恢复。`}
          onCancel={() => setDeleting(null)}
          onConfirm={() => handleDeleteFolder(deleting.id)}
        />
      )}
      </div>
    </div>
  )
}

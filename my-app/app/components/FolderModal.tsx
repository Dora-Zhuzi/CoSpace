'use client'

import { useEffect, useRef, useState } from 'react'
import ConfirmModal from '@/app/components/ConfirmModal'

const API = process.env.NEXT_PUBLIC_API_URL

interface Material {
  id: string
  filename: string
  status: 'uploading' | 'upload_failed' | 'upload_success' | 'indexing' | 'indexed' | 'index_failed'
  created_at: string
}

interface FolderDetail {
  id: string
  name: string
  materials: Material[]
}

interface Props {
  folder: FolderDetail
  onClose: () => void
  onRefresh: () => void
  getToken: () => string
}

const STATUS_BADGE: Record<Material['status'], { label: string; dot: string; cls: string }> = {
  uploading: { label: '上传中', dot: 'bg-amber-400', cls: 'bg-amber-50 text-amber-600' },
  upload_failed: { label: '上传失败', dot: 'bg-red-400', cls: 'bg-red-50 text-red-600' },
  upload_success: { label: '上传成功', dot: 'bg-blue-400', cls: 'bg-blue-50 text-blue-600' },
  indexing: { label: '入库中', dot: 'bg-amber-400', cls: 'bg-amber-50 text-amber-600' },
  indexed: { label: '入库完成', dot: 'bg-emerald-400', cls: 'bg-emerald-50 text-emerald-600' },
  index_failed: { label: '入库失败', dot: 'bg-red-400', cls: 'bg-red-50 text-red-600' },
}

export default function FolderModal({ folder, onClose, onRefresh, getToken }: Props) {
  const [uploading, setUploading] = useState(false)
  const [dragOver, setDragOver] = useState(false)
  const [deleting, setDeleting] = useState<Material | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // 有处理中的文件时轮询刷新，实时反映「入库中 → 入库完成」
  useEffect(() => {
    const inProgress = folder.materials.some(
      (m) => m.status === 'uploading' || m.status === 'indexing'
    )
    if (!inProgress) return
    const timer = setInterval(() => onRefresh(), 2500)
    return () => clearInterval(timer)
  }, [folder.materials, onRefresh])

  async function uploadFiles(files: FileList | File[]) {
    const list = Array.from(files)
    if (!list.length) return
    setUploading(true)
    for (const file of list) {
      const form = new FormData()
      form.append('file', file)
      await fetch(`${API}/materials/folders/${folder.id}/upload`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${getToken()}` },
        body: form,
      })
    }
    setUploading(false)
    onRefresh()
  }

  function handleInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    if (e.target.files) uploadFiles(e.target.files)
    e.target.value = ''
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault()
    setDragOver(false)
    if (e.dataTransfer.files) uploadFiles(e.dataTransfer.files)
  }

  async function handleDelete(id: string) {
    await fetch(`${API}/materials/${id}`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${getToken()}` },
    })
    onRefresh()
  }

  return (
    <div
      className="fixed inset-0 bg-black/40 backdrop-blur-sm flex items-center justify-center z-50 p-4"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-3xl shadow-2xl w-full max-w-lg flex flex-col overflow-hidden"
        style={{ height: '70vh' }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* 头部 */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100 shrink-0">
          <div className="flex items-center gap-3">
            <div
              className="w-9 h-9 rounded-xl flex items-center justify-center shadow-sm"
              style={{ background: 'linear-gradient(135deg,#FDE68A,#FBBF24)' }}
            >
              <svg className="w-5 h-5" viewBox="0 0 24 24" fill="white">
                <rect x="8" y="3" width="9" height="6" rx="1" fill="white" opacity="0.55" /><path d="M3 8a2 2 0 012-2h4l2 2h8a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V8z" fill="white" />
              </svg>
            </div>
            <div>
              <h2 className="text-base font-semibold text-gray-800 leading-tight">{folder.name}</h2>
              <p className="text-xs text-gray-400">{folder.materials.length} 个文件</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-full flex items-center justify-center text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors text-lg leading-none"
          >
            ✕
          </button>
        </div>

        {/* 拖拽上传区 */}
        <div className="px-6 pt-4 shrink-0">
          <div
            onClick={() => fileInputRef.current?.click()}
            onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            className={`rounded-2xl border-2 border-dashed flex flex-col items-center justify-center gap-2 py-7 cursor-pointer transition-all ${
              dragOver
                ? 'border-teal-400 bg-teal-50 scale-[1.01]'
                : 'border-gray-200 hover:border-teal-300 hover:bg-gray-50'
            }`}
          >
            <div className="w-11 h-11 rounded-full bg-teal-50 flex items-center justify-center">
              <svg className="w-5 h-5 text-teal-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 16V4m0 0L8 8m4-4l4 4M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2" />
              </svg>
            </div>
            <p className="text-sm text-gray-600">
              {uploading ? '上传中…' : '拖拽文件到此处，或点击上传'}
            </p>
            <p className="text-xs text-gray-400">支持 PDF、TXT、Markdown 等</p>
          </div>
        </div>

        {/* 文件列表 */}
        <div className="flex-1 overflow-y-auto px-6 py-4">
          {folder.materials.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-gray-300 gap-2">
              <svg className="w-10 h-10" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              <p className="text-sm">还没有文件，上传一个开始吧</p>
            </div>
          ) : (
            <ul className="space-y-2">
              {folder.materials.map((m) => {
                const badge = STATUS_BADGE[m.status]
                const busy = m.status === 'uploading' || m.status === 'indexing'
                return (
                  <li
                    key={m.id}
                    className="group flex items-center gap-3 px-3 py-2.5 rounded-xl border border-gray-100 bg-white hover:shadow-sm hover:border-gray-200 transition-all"
                  >
                    <div className="w-8 h-8 rounded-lg bg-gray-50 flex items-center justify-center shrink-0">
                      <svg className="w-4 h-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.6}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
                      </svg>
                    </div>
                    <span className="flex-1 text-sm text-gray-700 truncate">{m.filename}</span>
                    <span className={`flex items-center gap-1.5 text-xs px-2 py-1 rounded-full shrink-0 ${badge.cls}`}>
                      <span className={`w-1.5 h-1.5 rounded-full ${badge.dot} ${busy ? 'animate-pulse' : ''}`} />
                      {badge.label}
                    </span>
                    {!busy ? (
                      <button
                        onClick={() => setDeleting(m)}
                        title="删除"
                        className="w-6 flex justify-center text-gray-300 hover:text-red-500 opacity-0 group-hover:opacity-100 transition-opacity shrink-0"
                      >
                        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M7 7h10l-1 12a1 1 0 01-1 1H9a1 1 0 01-1-1L7 7z" />
                        </svg>
                      </button>
                    ) : (
                      <span className="w-6 shrink-0" />
                    )}
                  </li>
                )
              })}
            </ul>
          )}
        </div>

        <input ref={fileInputRef} type="file" multiple className="hidden" onChange={handleInputChange} />

        {deleting && (
          <ConfirmModal
            title="删除文件"
            message={`确定删除"${deleting.filename}"？删除后不可恢复。`}
            onCancel={() => setDeleting(null)}
            onConfirm={() => { handleDelete(deleting.id); setDeleting(null) }}
          />
        )}
      </div>
    </div>
  )
}

'use client'

import { useState, useEffect, useCallback, useRef } from 'react'
import { useParams, useRouter } from 'next/navigation'
import RenameModal from '@/app/components/RenameModal'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

const API = process.env.NEXT_PUBLIC_API_URL

function getToken() {
  if (typeof document === 'undefined') return ''
  const match = document.cookie.match(/(?:^|;\s*)token=([^;]*)/)
  return match ? match[1] : ''
}
function authHeaders() {
  return { Authorization: `Bearer ${getToken()}` }
}
function jsonHeaders() {
  return { 'Content-Type': 'application/json', ...authHeaders() }
}
function genId() {
  return 'n-' + Math.random().toString(36).slice(2, 10)
}

interface Project { id: string; name: string; folder_id: string }
interface ConvMeta { id: string; topic: string; created_at: string }
interface Message { id: string; role: string; content: string; created_at?: string }
interface TreeNode { id: string; label: string; chunk_ids: string[]; children: TreeNode[] }
interface Tree { id: string; name: string; nodes: TreeNode; status?: string; created_at: string }
interface Chunk { chunk_id: string; content: string; summary: string | null; chunk_index: number; file_name: string }
interface DocRecord { id: string; status: string; file_key: string | null; created_at: string }
interface Card { id: string; type: string; title: string | null; content: string; is_default?: boolean; created_at: string }

const CARD_META: Record<string, { label: string; cls: string; dot: string; head: string }> = {
  plan: { label: '方案', cls: 'bg-emerald-50 text-emerald-700 border-emerald-200', dot: 'bg-emerald-500', head: 'bg-emerald-100' },
  viewpoint: { label: '观点', cls: 'bg-blue-50 text-blue-700 border-blue-200', dot: 'bg-blue-500', head: 'bg-blue-100' },
  case: { label: '案例', cls: 'bg-purple-50 text-purple-700 border-purple-200', dot: 'bg-purple-500', head: 'bg-purple-100' },
}

type Tab = 'discuss' | 'plan' | 'tree' | 'article'

// ---------- 不可变节点操作 ----------
function updateNode(root: TreeNode, id: string, fn: (n: TreeNode) => TreeNode): TreeNode {
  if (root.id === id) return fn(root)
  return { ...root, children: root.children.map((c) => updateNode(c, id, fn)) }
}
function removeNode(root: TreeNode, id: string): TreeNode {
  return { ...root, children: root.children.filter((c) => c.id !== id).map((c) => removeNode(c, id)) }
}

export default function ProjectDetailPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const router = useRouter()
  const [project, setProject] = useState<Project | null>(null)
  const [tab, setTab] = useState<Tab>('discuss')

  const fetchProject = useCallback(async () => {
    const res = await fetch(`${API}/projects/${projectId}`, { headers: authHeaders() })
    if (res.ok) setProject(await res.json())
  }, [projectId])

  useEffect(() => { fetchProject() }, [fetchProject])

  if (!project) return <div className="p-8 text-sm text-gray-400">加载中...</div>

  const TABS: { key: Tab; label: string }[] = [
    { key: 'discuss', label: '共创讨论' },
    { key: 'plan', label: '写作方案' },
    { key: 'tree', label: '结构树' },
    { key: 'article', label: '文章' },
  ]

  return (
    <div className="flex flex-col h-[calc(100vh-48px)]" style={{ backgroundColor: '#D1EEEE' }}>
      {/* 顶部：返回 + 标签 */}
      <div className="relative flex items-center justify-center py-3 shrink-0">
        <button
          onClick={() => router.push('/workspace')}
          title="返回工作台"
          className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-600 hover:text-gray-900 transition-colors"
        >
          <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M10 19l-7-7m0 0l7-7m-7 7h18" />
          </svg>
        </button>

        <div className="flex items-center gap-1 bg-white/60 rounded-full p-1">
          {TABS.map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`px-4 py-1.5 rounded-full text-sm font-medium transition-colors ${
                tab === t.key ? 'bg-emerald-600 text-white shadow-sm' : 'text-gray-600 hover:text-teal-700'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 overflow-hidden px-4 pb-4">
        {tab === 'discuss' && (
          <DiscussTab
            projectId={projectId}
            onPlanGenerated={() => { fetchProject(); setTab('plan') }}
          />
        )}
        {tab === 'plan' && (
          <PlanTab projectId={projectId} onTreeCreated={() => setTab('tree')} />
        )}
        {tab === 'tree' && (
          <TreeTab
            projectId={projectId}
            project={project}
            onGoArticle={() => setTab('article')}
          />
        )}
        {tab === 'article' && (
          <ArticleTab projectId={projectId} />
        )}
      </div>
    </div>
  )
}

// ============ 共创讨论（左对话 / 右草稿卡片）============
function DiscussTab({ projectId, onPlanGenerated }: { projectId: string; onPlanGenerated: () => void }) {
  const [convs, setConvs] = useState<ConvMeta[]>([])
  const [activeId, setActiveId] = useState<string>('')
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [planning, setPlanning] = useState(false)
  const [creating, setCreating] = useState(false)
  const [cards, setCards] = useState<Card[]>([])
  const [selectedCardId, setSelectedCardId] = useState('')
  const scrollRef = useRef<HTMLDivElement>(null)

  const loadConvs = useCallback(async () => {
    const res = await fetch(`${API}/projects/${projectId}/conversations`, { headers: authHeaders() })
    if (res.ok) {
      const list: ConvMeta[] = await res.json()
      setConvs(list)
      if (list.length && !activeId) setActiveId(list[0].id)
    }
  }, [projectId, activeId])

  const loadCards = useCallback(async () => {
    if (!activeId) { setCards([]); return }
    const res = await fetch(`${API}/projects/${projectId}/cards?conversation_id=${activeId}`, { headers: authHeaders() })
    if (res.ok) setCards(await res.json())
  }, [projectId, activeId])

  useEffect(() => { loadConvs() }, [loadConvs])
  useEffect(() => { loadCards() }, [loadCards])

  useEffect(() => {
    if (!activeId) { setMessages([]); return }
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | undefined
    let tries = 0
    const load = async () => {
      try {
        const r = await fetch(`${API}/projects/${projectId}/conversations/${activeId}`, { headers: authHeaders() })
        if (cancelled || !r.ok) return
        const d = await r.json()
        if (cancelled) return
        setMessages(d.messages)
        // 开场白由后台生成，未就绪时轮询等待
        if (d.messages.length === 0 && tries < 20) {
          tries++
          timer = setTimeout(load, 1500)
        }
      } catch {
        if (!cancelled && tries < 20) { tries++; timer = setTimeout(load, 1500) }
      }
    }
    load()
    return () => { cancelled = true; if (timer) clearTimeout(timer) }
  }, [activeId, projectId])

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages])

  async function createConv(name: string) {
    setCreating(false)
    try {
      const res = await fetch(`${API}/projects/${projectId}/conversations`, {
        method: 'POST', headers: jsonHeaders(), body: JSON.stringify({ topic: name }),
      })
      if (!res.ok) { alert('创建讨论失败，请重试'); return }
      const conv = await res.json()
      await loadConvs()
      setActiveId(conv.id) // 固定开场白随创建返回，effect 直接加载
    } catch {
      alert('创建讨论失败，请检查网络或后端是否运行')
    }
  }

  async function send() {
    const content = input.trim()
    if (!content || !activeId || sending) return
    setInput('')
    setMessages((m) => [...m, { id: 'tmp-' + Date.now(), role: 'user', content }])
    setSending(true)
    try {
      const res = await fetch(`${API}/projects/${projectId}/conversations/${activeId}/messages`, {
        method: 'POST', headers: jsonHeaders(), body: JSON.stringify({ content }),
      })
      if (res.ok) {
        const reply: Message = await res.json()
        setMessages((m) => [...m, reply])
        loadConvs() // 首条消息后刷新讨论标题
      }
    } catch {
      setMessages((m) => [...m, { id: 'err-' + Date.now(), role: 'assistant', content: '（回复失败，请重试）' }])
    } finally {
      setSending(false)
    }
  }

  async function createPlan(content = '') {
    if (!activeId) return
    const r = await fetch(`${API}/projects/${projectId}/cards`, {
      method: 'POST', headers: jsonHeaders(),
      body: JSON.stringify({ conversation_id: activeId, type: 'plan', title: '', content }),
    })
    if (r.ok) { const c = await r.json(); setSelectedCardId(c.id) }
    loadCards()
  }

  // 保存某张卡片的内容（虚拟卡片则先创建）
  async function saveContent(card: Card, content: string): Promise<string | undefined> {
    if (!activeId) return card.id || undefined
    let id = card.id || undefined
    if (card.id) {
      await fetch(`${API}/projects/${projectId}/cards/${card.id}`, {
        method: 'PATCH', headers: jsonHeaders(), body: JSON.stringify({ content }),
      })
    } else {
      const r = await fetch(`${API}/projects/${projectId}/cards`, {
        method: 'POST', headers: jsonHeaders(),
        body: JSON.stringify({ conversation_id: activeId, type: card.type, content }),
      })
      if (r.ok) { const c = await r.json(); id = c.id; setSelectedCardId(c.id) }
    }
    loadCards()
    return id
  }

  async function renameCard(id: string, title: string) {
    await fetch(`${API}/projects/${projectId}/cards/${id}`, {
      method: 'PATCH', headers: jsonHeaders(), body: JSON.stringify({ title }),
    })
    loadCards()
  }

  // 把观点/案例卡片内容保存进素材库
  async function saveMaterial(cardId: string) {
    try {
      const r = await fetch(`${API}/projects/${projectId}/cards/${cardId}/save-material`, {
        method: 'POST', headers: authHeaders(),
      })
      if (r.ok) alert('已保存到素材库，正在入库…')
      else { const d = await r.json().catch(() => ({})); alert(d.detail ?? '保存失败') }
    } catch {
      alert('保存失败，请检查网络')
    }
  }

  // 把消息内容加入「当前打开的草稿卡片」
  async function addToCurrentCard(text: string) {
    if (!activeId) return
    const plans = cards.filter((c) => c.type === 'plan')
    const vp = cards.find((c) => c.type === 'viewpoint')
    const ce = cards.find((c) => c.type === 'case')
    const items: Card[] = [
      vp ?? { id: '', type: 'viewpoint', title: null, content: '', created_at: '' },
      ce ?? { id: '', type: 'case', title: null, content: '', created_at: '' },
      ...plans,
    ]
    const keyOf = (c: Card) => c.id || `v-${c.type}`
    const current = items.find((c) => keyOf(c) === selectedCardId) ?? items[0]
    if (current.id) {
      const merged = current.content ? `${current.content}\n\n${text}` : text
      await fetch(`${API}/projects/${projectId}/cards/${current.id}`, {
        method: 'PATCH', headers: jsonHeaders(), body: JSON.stringify({ content: merged }),
      })
      setSelectedCardId(current.id)
    } else {
      const r = await fetch(`${API}/projects/${projectId}/cards`, {
        method: 'POST', headers: jsonHeaders(),
        body: JSON.stringify({ conversation_id: activeId, type: current.type, content: text }),
      })
      if (r.ok) { const c = await r.json(); setSelectedCardId(c.id) }
    }
    loadCards()
  }

  async function deleteCard(id: string) {
    await fetch(`${API}/projects/${projectId}/cards/${id}`, { method: 'DELETE', headers: authHeaders() })
    loadCards()
  }

  async function makePlan() {
    if (planning || !activeId) return
    if (cards.length === 0) { alert('请先把讨论中有价值的信息沉淀为草稿便签'); return }
    setPlanning(true)
    const res = await fetch(`${API}/projects/${projectId}/plan`, {
      method: 'POST', headers: jsonHeaders(), body: JSON.stringify({ conversation_id: activeId }),
    })
    setPlanning(false)
    if (res.ok) onPlanGenerated()
    else {
      const d = await res.json().catch(() => ({}))
      alert(d.detail ?? '生成失败')
    }
  }

  async function deleteConv(id: string) {
    await fetch(`${API}/projects/${projectId}/conversations/${id}`, { method: 'DELETE', headers: authHeaders() })
    if (activeId === id) setActiveId('')
    loadConvs()
  }

  return (
    <div className="h-full flex gap-3">
      {/* 会话列表 */}
      <div className="w-44 shrink-0 flex flex-col rounded-2xl p-2 overflow-hidden" style={{ backgroundColor: '#FFFDF5' }}>
        <div className="flex-1 overflow-y-auto flex flex-col gap-1">
          {convs.length === 0 && <p className="text-xs text-gray-400 text-center mt-4">还没有讨论</p>}
          {convs.map((c) => (
            <div
              key={c.id}
              onClick={() => setActiveId(c.id)}
              className={`group px-3 py-2 rounded-lg cursor-pointer text-sm flex items-center justify-between transition-colors ${
                c.id === activeId ? 'bg-teal-100 text-teal-900' : 'hover:bg-gray-100 text-gray-700'
              }`}
            >
              <span className="truncate">{c.topic || '新讨论'}</span>
              <button
                onClick={(e) => { e.stopPropagation(); deleteConv(c.id) }}
                className="ml-1 shrink-0 opacity-0 group-hover:opacity-100 text-gray-300 hover:text-red-500 transition-all text-xs"
              >✕</button>
            </div>
          ))}
        </div>
        <button
          onClick={() => setCreating(true)}
          className="mt-2 px-3 py-2 rounded-lg text-sm font-medium bg-emerald-600 text-white hover:bg-emerald-700 transition-colors"
        >
          + 新建讨论
        </button>
      </div>

      {/* 左：对话窗口 */}
      <div className="flex-1 flex flex-col rounded-2xl overflow-hidden" style={{ backgroundColor: '#FFFDF5' }}>
        {!activeId ? (
          <div className="flex-1 flex items-center justify-center text-sm text-gray-400">
            新建或选择一个讨论开始共创
          </div>
        ) : (
          <>
            <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
              {messages.map((m) => (
                <div key={m.id} className={`group flex flex-col ${m.role === 'user' ? 'items-end' : 'items-start'}`}>
                  <div
                    className={`max-w-[80%] px-3.5 py-2 rounded-2xl text-sm leading-relaxed ${
                      m.role === 'user'
                        ? 'bg-emerald-600 text-white whitespace-pre-wrap'
                        : 'bg-white border border-gray-100 text-gray-700'
                    }`}
                  >
                    {m.role === 'user' ? (
                      m.content
                    ) : (
                      <div className="markdown">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown>
                      </div>
                    )}
                  </div>
                  <button
                    onClick={() => addToCurrentCard(m.content)}
                    title="加入当前草稿卡片"
                    className="mt-1 text-sm leading-none text-gray-400 hover:text-emerald-600 opacity-0 group-hover:opacity-100 transition-opacity"
                  >
                    ＋
                  </button>
                </div>
              ))}
              {activeId && messages.length === 0 && !sending && (
                <div className="text-xs text-gray-400">AI 正在准备开场…</div>
              )}
              {sending && <div className="text-xs text-gray-400">AI 正在思考…</div>}
            </div>
            <div className="shrink-0 p-3 border-t border-gray-100 flex gap-2">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
                rows={1}
                placeholder="输入你的想法，Enter 发送…"
                className="flex-1 resize-none border border-gray-200 rounded-xl px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-teal-400"
              />
              <button
                onClick={send}
                disabled={sending || !input.trim()}
                className="px-4 rounded-xl text-sm font-medium bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50 transition-colors"
              >
                发送
              </button>
            </div>
          </>
        )}
      </div>

      {activeId && (
        <DraftCardsPanel
          cards={cards}
          selectedCardId={selectedCardId}
          setSelectedCardId={setSelectedCardId}
          planning={planning}
          onCreatePlan={() => createPlan('')}
          onSaveContent={saveContent}
          onSaveMaterial={saveMaterial}
          onRename={renameCard}
          onDelete={deleteCard}
          onMakePlan={makePlan}
        />
      )}

      {creating && (
        <RenameModal
          title="给讨论起个名字"
          initial=""
          onCancel={() => setCreating(false)}
          onSubmit={createConv}
        />
      )}
    </div>
  )
}

// 便签底色：浅色=未选中，深色=选中
const NOTE_BG: Record<string, string> = {
  plan: '#D1FAE5',
  viewpoint: '#DBEAFE',
  case: '#EDE9FE',
}
const NOTE_BG_ACTIVE: Record<string, string> = {
  plan: '#6EE7B7',
  viewpoint: '#93C5FD',
  case: '#C4B5FD',
}

// 双栏：左侧分类卡片列表（观点 / 案例 / 方案 + 新建），右侧空白内容编辑区
function DraftCardsPanel({ cards, selectedCardId, setSelectedCardId, planning, onCreatePlan, onSaveContent, onSaveMaterial, onRename, onDelete, onMakePlan }: {
  cards: Card[]
  selectedCardId: string
  setSelectedCardId: (id: string) => void
  planning: boolean
  onCreatePlan: () => void
  onSaveContent: (card: Card, content: string) => Promise<string | undefined> | void
  onSaveMaterial: (cardId: string) => Promise<void> | void
  onRename: (id: string, title: string) => void
  onDelete: (id: string) => void
  onMakePlan: () => void
}) {
  const plans = cards.filter((c) => c.type === 'plan')
  const vp: Card = cards.find((c) => c.type === 'viewpoint') ?? { id: '', type: 'viewpoint', title: null, content: '', created_at: '' }
  const ce: Card = cards.find((c) => c.type === 'case') ?? { id: '', type: 'case', title: null, content: '', created_at: '' }
  const items: Card[] = [vp, ce, ...plans]
  const keyOf = (c: Card) => c.id || `v-${c.type}`
  const activeKey = selectedCardId || keyOf(items[0])
  const active = items.find((c) => keyOf(c) === activeKey) ?? items[0]

  const [draft, setDraft] = useState(active.content)
  const [renamingId, setRenamingId] = useState('')
  const [renameVal, setRenameVal] = useState('')
  const [savingMat, setSavingMat] = useState(false)

  // 切换卡片、或卡片内容被外部更新（如从消息「＋」追加）时，同步编辑区
  useEffect(() => { setDraft(active.content) }, [activeKey, active.content]) // eslint-disable-line react-hooks/exhaustive-deps

  function selectItem(c: Card) {
    if (keyOf(c) === activeKey) return
    if (draft !== active.content) onSaveContent(active, draft) // 切换前保存
    setSelectedCardId(keyOf(c))
  }

  const label = (c: Card) => (c.type === 'plan' ? (c.title || '未命名草稿') : CARD_META[c.type].label)

  async function handleSaveMaterial() {
    if (savingMat) return
    setSavingMat(true)
    // 先确保内容已落库（虚拟卡片会被创建并拿到 id），再保存为素材
    let id = active.id
    if (!id || draft !== active.content) {
      id = (await onSaveContent(active, draft)) || id
    }
    if (id) await onSaveMaterial(id)
    setSavingMat(false)
  }

  return (
    <div className="flex-1 min-w-0 flex flex-col rounded-2xl overflow-hidden" style={{ backgroundColor: '#FFFDF5' }}>
      <div className="flex-1 min-h-0 flex">
        {/* 左：分类卡片列表（整体滚动，「+」跟在最后一张后面） */}
        <div className="w-36 shrink-0 border-r border-gray-100 overflow-y-auto p-2 flex flex-col gap-1">
          {items.map((c) => {
              const on = keyOf(c) === activeKey
              const isPlan = c.type === 'plan'
              const renaming = isPlan && renamingId === c.id
              return (
                <div
                  key={keyOf(c)}
                  onClick={() => selectItem(c)}
                  className={`group rounded-lg px-2.5 py-2 cursor-pointer text-sm flex items-center justify-between transition-all hover:brightness-95 ${on ? 'shadow-sm font-medium' : ''}`}
                  style={{ backgroundColor: on ? NOTE_BG_ACTIVE[c.type] : NOTE_BG[c.type] }}
                >
                  {renaming ? (
                    <input
                      autoFocus
                      value={renameVal}
                      onChange={(e) => setRenameVal(e.target.value)}
                      onClick={(e) => e.stopPropagation()}
                      onBlur={() => { if (renameVal.trim()) onRename(c.id, renameVal.trim()); setRenamingId('') }}
                      onKeyDown={(e) => { if (e.key === 'Enter') { if (renameVal.trim()) onRename(c.id, renameVal.trim()); setRenamingId('') } }}
                      className="w-full text-sm px-1 py-0.5 border border-teal-300 rounded outline-none"
                    />
                  ) : (
                    <>
                      <span className="truncate text-gray-700">{label(c)}</span>
                      {isPlan && (
                        <span className="flex gap-1 shrink-0 ml-1 opacity-0 group-hover:opacity-100 text-gray-400 text-xs">
                          <span role="button" onClick={(e) => { e.stopPropagation(); setRenamingId(c.id); setRenameVal(c.title || '') }} className="hover:text-teal-600 cursor-pointer">✎</span>
                          {!c.is_default && (
                            <span role="button" onClick={(e) => { e.stopPropagation(); onDelete(c.id) }} className="hover:text-red-500 cursor-pointer">✕</span>
                          )}
                        </span>
                      )}
                    </>
                  )}
                </div>
              )
            })}
          <button
            onClick={onCreatePlan}
            title="新建草稿"
            className="shrink-0 px-2 py-1.5 rounded-lg text-base border border-dashed border-gray-300 text-gray-500 hover:border-emerald-300 hover:text-emerald-600 transition-colors"
          >
            ＋
          </button>
        </div>

        {/* 右：内容编辑区（空白，无提示）+ 仅草稿卡片显示「生成方案」 */}
        <div className="flex-1 min-w-0 flex flex-col">
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={() => { if (draft !== active.content) onSaveContent(active, draft) }}
            className="flex-1 min-w-0 resize-none p-4 text-sm leading-relaxed outline-none bg-transparent"
          />
          {active.type === 'plan' ? (
            <div className="shrink-0 px-3 py-2 flex justify-end">
              <button
                onClick={onMakePlan}
                disabled={planning}
                className="px-4 py-1.5 rounded-lg text-sm font-medium bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50 transition-colors"
              >
                {planning ? '生成中…' : '生成方案 →'}
              </button>
            </div>
          ) : (
            <div className="shrink-0 px-3 py-2 flex justify-end">
              <button
                onClick={handleSaveMaterial}
                disabled={savingMat}
                className="px-4 py-1.5 rounded-lg text-sm font-medium bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50 transition-colors"
              >
                {savingMat ? '保存中…' : '保存素材'}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ============ 写作方案 ============
interface PlanItem { id: string; name: string; content: string; created_at: string }

function PlanTab({ projectId, onTreeCreated }: { projectId: string; onTreeCreated: () => void }) {
  const [plans, setPlans] = useState<PlanItem[]>([])
  const [selectedId, setSelectedId] = useState('')
  const [content, setContent] = useState('')
  const [mode, setMode] = useState<'preview' | 'edit'>('preview')
  const [saving, setSaving] = useState(false)
  const [building, setBuilding] = useState(false)

  const loadPlans = useCallback(async () => {
    const r = await fetch(`${API}/projects/${projectId}/plans`, { headers: authHeaders() })
    if (r.ok) setPlans(await r.json())
  }, [projectId])

  useEffect(() => { loadPlans() }, [loadPlans])

  // 默认选中最新一份
  useEffect(() => {
    if (plans.length === 0) { setSelectedId(''); setContent(''); return }
    if (!plans.some((p) => p.id === selectedId)) {
      const latest = plans[plans.length - 1]
      setSelectedId(latest.id); setContent(latest.content)
    }
  }, [plans]) // eslint-disable-line react-hooks/exhaustive-deps

  function openPlan(p: PlanItem) { setSelectedId(p.id); setContent(p.content); setMode('preview') }

  async function save() {
    if (!selectedId) return
    setSaving(true)
    await fetch(`${API}/projects/${projectId}/plans/${selectedId}`, {
      method: 'PATCH', headers: jsonHeaders(), body: JSON.stringify({ content }),
    })
    setSaving(false)
    loadPlans()
  }
  async function deletePlan(id: string) {
    await fetch(`${API}/projects/${projectId}/plans/${id}`, { method: 'DELETE', headers: authHeaders() })
    if (selectedId === id) { setSelectedId(''); setContent('') }
    loadPlans()
  }
  async function buildTree() {
    if (!selectedId || building) return
    setBuilding(true)
    const res = await fetch(`${API}/projects/${projectId}/trees`, {
      method: 'POST', headers: jsonHeaders(), body: JSON.stringify({ plan_id: selectedId }),
    })
    setBuilding(false)
    if (res.ok) onTreeCreated()
  }

  if (plans.length === 0) {
    return (
      <div className="h-full flex items-center justify-center">
        <p className="text-sm text-gray-500">还没有写作方案，请先在「共创讨论」中点击「生成方案」。</p>
      </div>
    )
  }

  return (
    <div className="h-full flex gap-3 mx-auto max-w-5xl">
      {/* 左：方案列表 */}
      <div className="w-44 shrink-0 flex flex-col rounded-2xl overflow-y-auto p-2 gap-1" style={{ backgroundColor: '#FFFDF5' }}>
        {plans.map((p) => (
          <div
            key={p.id}
            onClick={() => openPlan(p)}
            className={`group px-3 py-2 rounded-lg cursor-pointer text-sm flex items-center justify-between transition-colors ${selectedId === p.id ? 'bg-emerald-100 text-emerald-900' : 'hover:bg-gray-100 text-gray-700'}`}
          >
            <span className="truncate">{p.name}</span>
            <button
              onClick={(e) => { e.stopPropagation(); deletePlan(p.id) }}
              className="ml-1 shrink-0 opacity-0 group-hover:opacity-100 text-gray-300 hover:text-red-500 transition-all text-xs"
            >✕</button>
          </div>
        ))}
      </div>

      {/* 右：编辑 / 预览 */}
      <div className="flex-1 min-w-0 flex flex-col rounded-2xl overflow-hidden" style={{ backgroundColor: '#FFFDF5' }}>
        <div className="shrink-0 flex items-center justify-between px-4 py-2.5 border-b border-gray-100">
          <span className="text-sm font-medium text-gray-700 truncate">
            {plans.find((p) => p.id === selectedId)?.name ?? '写作方案'}
          </span>
          <div className="flex gap-2 shrink-0">
            <button
              onClick={() => setMode(mode === 'edit' ? 'preview' : 'edit')}
              className="px-3 py-1.5 rounded-lg text-sm text-gray-600 border border-gray-200 hover:bg-gray-50 transition-colors"
            >
              {mode === 'edit' ? '预览' : '编辑'}
            </button>
            <button
              onClick={save}
              disabled={saving}
              className="px-3 py-1.5 rounded-lg text-sm text-gray-600 border border-gray-200 hover:bg-gray-50 disabled:opacity-50 transition-colors"
            >
              {saving ? '保存中…' : '保存'}
            </button>
            <button
              onClick={buildTree}
              disabled={building}
              className="px-3 py-1.5 rounded-lg text-sm font-medium bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50 transition-colors"
            >
              {building ? '生成中…' : '生成结构树 →'}
            </button>
          </div>
        </div>
        {mode === 'edit' ? (
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            className="flex-1 resize-none px-5 py-4 text-sm leading-relaxed outline-none bg-transparent font-mono"
          />
        ) : (
          <div className="markdown flex-1 overflow-y-auto px-6 py-4">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
          </div>
        )}
      </div>
    </div>
  )
}

// ============ 结构树 ============
function TreeTab({ projectId, project, onGoArticle }: {
  projectId: string
  project: Project
  onGoArticle: () => void
}) {
  const [trees, setTrees] = useState<Tree[]>([])
  const [selectedId, setSelectedId] = useState('')
  const [nodes, setNodes] = useState<TreeNode | null>(null)
  const [dirty, setDirty] = useState(false)
  const [editingId, setEditingId] = useState('')
  const [editingVal, setEditingVal] = useState('')
  const [mountNode, setMountNode] = useState<TreeNode | null>(null)
  const [viewChunk, setViewChunk] = useState<string | null>(null)
  const [chunkMap, setChunkMap] = useState<Record<string, { content: string; file_name: string }>>({})
  const [generating, setGenerating] = useState(false)
  const [articles, setArticles] = useState<ArticleItem[]>([])

  const loadArticles = useCallback(async () => {
    const r = await fetch(`${API}/projects/${projectId}/articles`, { headers: authHeaders() })
    if (r.ok) setArticles(await r.json())
  }, [projectId])

  useEffect(() => { loadArticles() }, [loadArticles])
  const latestArticle = articles.length ? articles[articles.length - 1] : null

  const selected = trees.find((t) => t.id === selectedId) ?? trees[trees.length - 1]

  const loadTrees = useCallback(async () => {
    const res = await fetch(`${API}/projects/${projectId}/trees`, { headers: authHeaders() })
    if (res.ok) setTrees(await res.json())
  }, [projectId])

  useEffect(() => { loadTrees() }, [loadTrees])

  // 加载素材片段映射，用于在节点下内联展示已挂载素材内容
  useEffect(() => {
    fetch(`${API}/projects/${projectId}/chunks`, { headers: authHeaders() })
      .then((r) => (r.ok ? r.json() : []))
      .then((cs: Chunk[]) => {
        const m: Record<string, { content: string; file_name: string }> = {}
        cs.forEach((c) => { m[c.chunk_id] = { content: c.content, file_name: c.file_name } })
        setChunkMap(m)
      })
  }, [projectId])

  // 有结构树在生成中时轮询，直到 ready
  useEffect(() => {
    if (!trees.some((t) => t.status === 'generating')) return
    const timer = setInterval(loadTrees, 3000)
    return () => clearInterval(timer)
  }, [trees, loadTrees])

  // 切换结构树、或当前树由 generating 变 ready 时，载入其结构
  useEffect(() => {
    if (selected) {
      setNodes(selected.nodes && Object.keys(selected.nodes).length ? JSON.parse(JSON.stringify(selected.nodes)) : null)
      setDirty(false)
    } else {
      setNodes(null)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected?.id, selected?.status])

  // 生成文章时轮询，完成后刷新项目以取得 project.article
  useEffect(() => {
    if (!generating || !selected) return
    const tid = selected.id
    const timer = setInterval(async () => {
      const r = await fetch(`${API}/projects/${projectId}/trees/${tid}/documents`, { headers: authHeaders() })
      if (!r.ok) return
      const d: DocRecord[] = await r.json()
      const latest = d[0]
      if (latest && latest.status === 'done') { setGenerating(false); loadArticles() }
      else if (latest && latest.status === 'failed') { setGenerating(false); alert('文章生成失败，请重试') }
    }, 3000)
    return () => clearInterval(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [generating, selected?.id])

  function mutate(fn: (root: TreeNode) => TreeNode) {
    setNodes((n) => (n ? fn(n) : n))
    setDirty(true)
  }

  async function save() {
    if (!nodes || !selected) return
    const res = await fetch(`${API}/projects/${projectId}/trees/${selected.id}`, {
      method: 'PATCH', headers: jsonHeaders(), body: JSON.stringify({ nodes }),
    })
    if (res.ok) { setDirty(false); loadTrees() }
  }

  async function deleteTree(id: string) {
    await fetch(`${API}/projects/${projectId}/trees/${id}`, { method: 'DELETE', headers: authHeaders() })
    if (selectedId === id) setSelectedId('')
    loadTrees()
  }

  async function generate() {
    if (!selected || generating || selected.status !== 'ready') return
    setGenerating(true)
    const r = await fetch(`${API}/projects/${projectId}/trees/${selected.id}/documents`, {
      method: 'POST', headers: authHeaders(),
    })
    if (!r.ok) setGenerating(false)
  }

  function downloadArticle() {
    if (!latestArticle) return
    const blob = new Blob([latestArticle.content], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${latestArticle.name || project.name || 'article'}.md`
    a.click()
    URL.revokeObjectURL(url)
  }

  if (trees.length === 0) {
    return (
      <div className="h-full flex items-center justify-center">
        <p className="text-sm text-gray-500">还没有结构树，请先在「写作方案」中点击「生成结构树」。</p>
      </div>
    )
  }

  return (
    <div className="h-full flex gap-3">
      {/* 树列表 */}
      <div className="w-44 shrink-0 flex flex-col gap-1 p-2 rounded-2xl overflow-y-auto" style={{ backgroundColor: '#FFFDF5' }}>
        {trees.map((t) => (
          <div
            key={t.id}
            onClick={() => setSelectedId(t.id)}
            className={`group px-3 py-2 rounded-lg cursor-pointer text-sm flex items-center justify-between transition-colors ${
              t.id === (selected?.id) ? 'bg-teal-100 text-teal-900' : 'hover:bg-gray-100 text-gray-700'
            }`}
          >
            <span className="truncate">{t.name}</span>
            <button
              onClick={(e) => { e.stopPropagation(); deleteTree(t.id) }}
              className="ml-1 shrink-0 opacity-0 group-hover:opacity-100 text-gray-300 hover:text-red-500 transition-all text-xs"
            >✕</button>
          </div>
        ))}
      </div>

      {/* 中间：结构树 + 素材（单卡片，细分隔线留出上下按钮区）*/}
      <div className="flex-1 flex flex-col rounded-2xl overflow-hidden" style={{ backgroundColor: '#FFFDF5' }}>
        {selected?.status === 'generating' ? (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center text-sm text-gray-500">
              <div className="w-6 h-6 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin mx-auto mb-2" />
              结构生成中…正在筛选并挂载素材
            </div>
          </div>
        ) : selected?.status === 'failed' ? (
          <div className="flex-1 flex items-center justify-center text-sm text-red-400">结构生成失败，请删除后重试</div>
        ) : (
          <div className="flex-1 min-h-0 flex">
            <div className="flex-1 overflow-auto p-4">
            {nodes && (
              <NodeView
                node={nodes}
                depth={0}
                isRoot
                chunkMap={chunkMap}
                editingId={editingId}
                editingVal={editingVal}
                onViewChunk={(id) => setViewChunk(id)}
                onStartEdit={(n) => { setEditingId(n.id); setEditingVal(n.label) }}
                onEditVal={setEditingVal}
                onCommitEdit={(id) => { mutate((r) => updateNode(r, id, (n) => ({ ...n, label: editingVal.trim() || n.label }))); setEditingId('') }}
                onAddChild={(id) => mutate((r) => updateNode(r, id, (n) => ({ ...n, children: [...n.children, { id: genId(), label: '新章节', chunk_ids: [], children: [] }] })))}
                onDelete={(id) => mutate((r) => removeNode(r, id))}
                onMount={(n) => setMountNode(n)}
              />
            )}
            </div>
            {/* 右：素材展示（嵌入，细分隔线）*/}
            <div className="w-64 shrink-0 border-l border-gray-100 p-3 flex flex-col">
              {viewChunk && chunkMap[viewChunk] ? (
                <div className="rounded-xl p-3 flex-1 min-h-0 flex flex-col" style={{ backgroundColor: '#E8F6F6' }}>
                  <div className="flex justify-end mb-1 shrink-0">
                    <button onClick={() => setViewChunk(null)} className="text-gray-400 hover:text-gray-600 text-sm leading-none">✕</button>
                  </div>
                  <p className="flex-1 min-h-0 overflow-y-auto text-xs text-gray-700 leading-relaxed whitespace-pre-wrap">{chunkMap[viewChunk].content}</p>
                  <p className="mt-3 text-xs text-gray-400 shrink-0">—— {chunkMap[viewChunk].file_name}</p>
                </div>
              ) : (
                <div className="rounded-xl flex-1 flex items-center justify-center text-xs text-gray-400 text-center px-2" style={{ backgroundColor: '#E8F6F6' }}>
                  点击节点下的素材查看内容
                </div>
              )}
            </div>
          </div>
        )}
        {/* 底部操作栏：保存修改 + 生成文章 */}
        <div className="shrink-0 border-t border-gray-100 min-h-[48px] flex items-center justify-end gap-2 px-4">
          <button
            onClick={save}
            disabled={!dirty || selected?.status !== 'ready'}
            className="px-3 py-1.5 rounded-lg text-sm font-medium text-gray-600 border border-gray-200 hover:bg-gray-50 disabled:opacity-50 transition-colors"
          >
            保存修改
          </button>
          <button
            onClick={generate}
            disabled={generating || selected?.status !== 'ready'}
            className="px-3 py-1.5 rounded-lg text-sm font-medium bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50 transition-colors"
          >
            {generating ? '生成中…' : '生成文章'}
          </button>
        </div>
      </div>

      {/* 文章预览：展示最近生成的文章 */}
      <div className="w-96 shrink-0 flex flex-col rounded-2xl overflow-hidden" style={{ backgroundColor: '#FFFDF5' }}>
        <div className="shrink-0 px-4 border-b border-gray-100 flex items-center min-h-[48px]">
          <span className="text-sm font-medium text-gray-700">文章预览</span>
        </div>
        <div className="flex-1 overflow-y-auto p-3">
          {generating ? (
            <div className="h-full flex items-center justify-center text-xs text-gray-500 text-center">
              <div>
                <div className="w-5 h-5 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin mx-auto mb-2" />
                文章生成中…
              </div>
            </div>
          ) : latestArticle ? (
            <div className="markdown text-xs">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{latestArticle.content}</ReactMarkdown>
            </div>
          ) : (
            <p className="text-xs text-gray-400 text-center mt-4">暂无文章，点「生成文章」</p>
          )}
        </div>
        {latestArticle && !generating && (
          <div className="shrink-0 px-3 py-2 border-t border-gray-100 flex items-center justify-end gap-2">
            <button onClick={downloadArticle} title="下载" className="text-teal-600 hover:text-teal-800">
              <svg className="w-4 h-4" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M3 17a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm3.293-7.707a1 1 0 011.414 0L9 10.586V3a1 1 0 112 0v7.586l1.293-1.293a1 1 0 111.414 1.414l-3 3a1 1 0 01-1.414 0l-3-3a1 1 0 010-1.414z" clipRule="evenodd" />
              </svg>
            </button>
            <button onClick={onGoArticle} className="px-3 py-1.5 rounded-lg text-sm text-gray-600 border border-gray-200 hover:bg-gray-50 transition-colors">编辑 →</button>
          </div>
        )}
      </div>

      {mountNode && (
        <ChunkPicker
          projectId={projectId}
          initial={mountNode.chunk_ids}
          onClose={() => setMountNode(null)}
          onSave={(ids) => { mutate((r) => updateNode(r, mountNode.id, (n) => ({ ...n, chunk_ids: ids }))); setMountNode(null) }}
        />
      )}

    </div>
  )
}

// ============ 文章 ============
interface ArticleItem { id: string; name: string; content: string; created_at: string }

function ArticleTab({ projectId }: { projectId: string }) {
  const [articles, setArticles] = useState<ArticleItem[]>([])
  const [selectedId, setSelectedId] = useState('')
  const [content, setContent] = useState('')
  const [mode, setMode] = useState<'preview' | 'edit'>('preview')
  const [saving, setSaving] = useState(false)

  const loadArticles = useCallback(async () => {
    const r = await fetch(`${API}/projects/${projectId}/articles`, { headers: authHeaders() })
    if (r.ok) setArticles(await r.json())
  }, [projectId])

  useEffect(() => { loadArticles() }, [loadArticles])

  // 默认选中最新一份
  useEffect(() => {
    if (articles.length === 0) { setSelectedId(''); setContent(''); return }
    if (!articles.some((a) => a.id === selectedId)) {
      const latest = articles[articles.length - 1]
      setSelectedId(latest.id); setContent(latest.content)
    }
  }, [articles]) // eslint-disable-line react-hooks/exhaustive-deps

  function openArticle(a: ArticleItem) { setSelectedId(a.id); setContent(a.content); setMode('preview') }

  async function save() {
    if (!selectedId) return
    setSaving(true)
    await fetch(`${API}/projects/${projectId}/articles/${selectedId}`, {
      method: 'PATCH', headers: jsonHeaders(), body: JSON.stringify({ content }),
    })
    setSaving(false)
    loadArticles()
  }
  async function deleteArticle(id: string) {
    await fetch(`${API}/projects/${projectId}/articles/${id}`, { method: 'DELETE', headers: authHeaders() })
    if (selectedId === id) { setSelectedId(''); setContent('') }
    loadArticles()
  }
  function download() {
    const blob = new Blob([content], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${articles.find((x) => x.id === selectedId)?.name || '文章'}.md`
    a.click()
    URL.revokeObjectURL(url)
  }

  if (articles.length === 0) {
    return (
      <div className="h-full flex items-center justify-center">
        <p className="text-sm text-gray-500">还没有文章，请先在「结构树」页生成文章。</p>
      </div>
    )
  }

  return (
    <div className="h-full flex gap-3 mx-auto w-fit max-w-full">
      <div className="w-44 shrink-0 flex flex-col rounded-2xl overflow-y-auto p-2 gap-1" style={{ backgroundColor: '#FFFDF5' }}>
        {articles.map((a) => (
          <div
            key={a.id}
            onClick={() => openArticle(a)}
            className={`group px-3 py-2 rounded-lg cursor-pointer text-sm flex items-center justify-between transition-colors ${selectedId === a.id ? 'bg-emerald-100 text-emerald-900' : 'hover:bg-gray-100 text-gray-700'}`}
          >
            <span className="truncate">{a.name}</span>
            <button
              onClick={(e) => { e.stopPropagation(); deleteArticle(a.id) }}
              className="ml-1 shrink-0 opacity-0 group-hover:opacity-100 text-gray-300 hover:text-red-500 transition-all text-xs"
            >✕</button>
          </div>
        ))}
      </div>

      <div className="w-[56rem] max-w-full flex flex-col rounded-2xl overflow-hidden" style={{ backgroundColor: '#FFFDF5' }}>
        <div className="shrink-0 flex items-center justify-between px-4 py-2.5 border-b border-gray-100">
          <span className="text-sm font-medium text-gray-700 truncate">
            {articles.find((a) => a.id === selectedId)?.name ?? '文章'}
          </span>
          <div className="flex gap-2 shrink-0">
            <button
              onClick={() => setMode(mode === 'edit' ? 'preview' : 'edit')}
              className="px-3 py-1.5 rounded-lg text-sm text-gray-600 border border-gray-200 hover:bg-gray-50 transition-colors"
            >
              {mode === 'edit' ? '预览' : '编辑'}
            </button>
            <button
              onClick={save}
              disabled={saving}
              className="px-3 py-1.5 rounded-lg text-sm text-gray-600 border border-gray-200 hover:bg-gray-50 disabled:opacity-50 transition-colors"
            >
              {saving ? '保存中…' : '保存'}
            </button>
            <button onClick={download} title="下载" className="text-teal-600 hover:text-teal-800 px-1">
              <svg className="w-5 h-5" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M3 17a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm3.293-7.707a1 1 0 011.414 0L9 10.586V3a1 1 0 112 0v7.586l1.293-1.293a1 1 0 111.414 1.414l-3 3a1 1 0 01-1.414 0l-3-3a1 1 0 010-1.414z" clipRule="evenodd" />
              </svg>
            </button>
          </div>
        </div>
        {mode === 'edit' ? (
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            className="flex-1 resize-none px-5 py-4 text-sm leading-relaxed outline-none bg-transparent font-mono"
          />
        ) : (
          <div className="markdown flex-1 overflow-y-auto px-6 py-4">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
          </div>
        )}
      </div>
    </div>
  )
}

// 递归节点
function NodeView(props: {
  node: TreeNode
  depth: number
  isRoot?: boolean
  chunkMap: Record<string, { content: string; file_name: string }>
  editingId: string
  editingVal: string
  onViewChunk: (id: string) => void
  onStartEdit: (n: TreeNode) => void
  onEditVal: (v: string) => void
  onCommitEdit: (id: string) => void
  onAddChild: (id: string) => void
  onDelete: (id: string) => void
  onMount: (n: TreeNode) => void
}) {
  const { node, depth, isRoot, chunkMap, editingId, editingVal, onViewChunk, onStartEdit, onEditVal, onCommitEdit, onAddChild, onDelete, onMount } = props
  const editing = editingId === node.id
  return (
    <div style={{ marginLeft: depth === 0 ? 0 : 16 }}>
      <div className="group flex items-center gap-1.5 py-1">
        {editing ? (
          <input
            autoFocus
            value={editingVal}
            onChange={(e) => onEditVal(e.target.value)}
            onBlur={() => onCommitEdit(node.id)}
            onKeyDown={(e) => { if (e.key === 'Enter') onCommitEdit(node.id) }}
            className="px-2 py-1 text-sm border border-teal-300 rounded outline-none focus:ring-2 focus:ring-teal-400"
          />
        ) : (
          <span
            className={`px-3 py-1.5 rounded-lg text-sm font-medium shadow-sm ${
              isRoot ? 'bg-blue-200 text-blue-900' : depth === 1 ? 'bg-amber-100 text-amber-900' : 'bg-teal-100 text-teal-900'
            }`}
          >
            {node.label}
          </span>
        )}
        {!isRoot && node.chunk_ids.length > 0 && (
          <span className="text-xs px-1.5 py-0.5 rounded-full bg-emerald-50 text-emerald-600">挂载 {node.chunk_ids.length}</span>
        )}

        <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity text-gray-400">
          <IconBtn title="重命名" onClick={() => onStartEdit(node)} d="M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931z" />
          <IconBtn title="添加子节点" onClick={() => onAddChild(node.id)} d="M12 5v14m-7-7h14" />
          {!isRoot && (
            <button onClick={() => onMount(node)} title="挂载素材" className="px-1.5 py-0.5 text-xs rounded hover:bg-emerald-50 hover:text-emerald-600">挂载</button>
          )}
          {!isRoot && (
            <IconBtn title="删除" onClick={() => onDelete(node.id)} d="M7 7h10l-1 12a1 1 0 01-1 1H9a1 1 0 01-1-1L7 7z" danger />
          )}
        </div>
      </div>

      {/* 已挂载的素材片段（点击查看内容）*/}
      {!isRoot && node.chunk_ids.length > 0 && (
        <div className="ml-5 mb-1 flex flex-col gap-1">
          {node.chunk_ids.map((cid) => {
            const ch = chunkMap[cid]
            return (
              <button
                key={cid}
                onClick={() => onViewChunk(cid)}
                className="text-left text-xs text-gray-500 hover:text-emerald-700 bg-white border border-gray-100 rounded-md px-2 py-1 max-w-md truncate"
              >
                {ch ? `${ch.content.slice(0, 28)}…` : '（素材已删除）'}
              </button>
            )
          })}
        </div>
      )}

      {node.children.map((c) => (
        <NodeView key={c.id} {...props} node={c} depth={depth + 1} isRoot={false} />
      ))}
    </div>
  )
}

function IconBtn({ title, onClick, d, danger }: { title: string; onClick: () => void; d: string; danger?: boolean }) {
  return (
    <button onClick={onClick} title={title} className={`p-1 rounded transition-colors ${danger ? 'hover:text-red-500 hover:bg-red-50' : 'hover:text-teal-600 hover:bg-teal-50'}`}>
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
        <path strokeLinecap="round" strokeLinejoin="round" d={d} />
      </svg>
    </button>
  )
}

// 素材片段选择器
function ChunkPicker({ projectId, initial, onClose, onSave }: {
  projectId: string; initial: string[]; onClose: () => void; onSave: (ids: string[]) => void
}) {
  const [chunks, setChunks] = useState<Chunk[]>([])
  const [selected, setSelected] = useState<Set<string>>(new Set(initial))

  useEffect(() => {
    fetch(`${API}/projects/${projectId}/chunks`, { headers: authHeaders() })
      .then((r) => (r.ok ? r.json() : []))
      .then(setChunks)
  }, [projectId])

  function toggle(id: string) {
    setSelected((s) => {
      const n = new Set(s)
      if (n.has(id)) n.delete(id); else n.add(id)
      return n
    })
  }

  return (
    <div className="fixed inset-0 bg-black/40 backdrop-blur-sm flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div className="bg-white rounded-3xl shadow-2xl w-full max-w-2xl flex flex-col" style={{ height: '72vh' }} onClick={(e) => e.stopPropagation()}>
        <div className="shrink-0 flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <h2 className="text-base font-semibold text-gray-800">挂载素材片段（已选 {selected.size}）</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 text-lg">✕</button>
        </div>
        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-2">
          {chunks.length === 0 && <p className="text-sm text-gray-400 text-center mt-6">素材库暂无片段</p>}
          {chunks.map((c) => {
            const on = selected.has(c.chunk_id)
            return (
              <div
                key={c.chunk_id}
                onClick={() => toggle(c.chunk_id)}
                className={`rounded-xl border p-3 cursor-pointer transition-colors ${on ? 'border-teal-400 bg-teal-50' : 'border-gray-100 hover:border-gray-200'}`}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs text-gray-400">{c.file_name} · 第 {c.chunk_index + 1} 段</span>
                  <span className={`w-4 h-4 rounded flex items-center justify-center text-xs ${on ? 'bg-emerald-600 text-white' : 'border border-gray-300'}`}>{on ? '✓' : ''}</span>
                </div>
                <p className="text-sm text-gray-700 line-clamp-2">{c.content}</p>
              </div>
            )
          })}
        </div>
        <div className="shrink-0 flex justify-end gap-2 px-6 py-4 border-t border-gray-100">
          <button onClick={onClose} className="px-4 py-2 text-sm text-gray-500 hover:text-gray-700 rounded-lg hover:bg-gray-100">取消</button>
          <button onClick={() => onSave([...selected])} className="px-5 py-2 text-sm bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 shadow-sm">确定</button>
        </div>
      </div>
    </div>
  )
}

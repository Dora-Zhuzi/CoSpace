'use client'

interface Props {
  title: string
  message?: string
  confirmText?: string
  onCancel: () => void
  onConfirm: () => void
}

export default function ConfirmModal({
  title,
  message,
  confirmText = '删除',
  onCancel,
  onConfirm,
}: Props) {
  return (
    <div
      className="fixed inset-0 bg-black/40 backdrop-blur-sm flex items-center justify-center z-[60] p-4"
      onClick={onCancel}
    >
      <div
        className="bg-white rounded-3xl shadow-2xl p-7 w-full max-w-sm"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start gap-3 mb-6">
          <div className="w-10 h-10 rounded-full bg-red-50 flex items-center justify-center shrink-0">
            <svg className="w-5 h-5 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m0 3.75h.008M10.34 3.94l-7.6 13.16A1.5 1.5 0 004.04 19.5h15.92a1.5 1.5 0 001.3-2.4L13.66 3.94a1.5 1.5 0 00-2.6 0z" />
            </svg>
          </div>
          <div className="min-w-0">
            <h2 className="text-base font-semibold text-gray-800">{title}</h2>
            {message && (
              <p className="text-sm text-gray-500 mt-1 leading-relaxed">{message}</p>
            )}
          </div>
        </div>
        <div className="flex justify-end gap-2">
          <button
            onClick={onCancel}
            className="px-4 py-2 text-sm text-gray-500 hover:text-gray-700 rounded-lg hover:bg-gray-100 transition-colors"
          >
            取消
          </button>
          <button
            onClick={onConfirm}
            className="px-5 py-2 text-sm bg-red-600 text-white rounded-lg hover:bg-red-700 shadow-sm transition-colors"
          >
            {confirmText}
          </button>
        </div>
      </div>
    </div>
  )
}

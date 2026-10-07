import { FC, useEffect, MouseEvent } from 'react';

export interface ConfirmModalProps {
  isOpen: boolean;
  title: string;
  prompt?: string;
  message?: string;
  confirmLabel?: string;
  confirmText?: string;
  cancelLabel?: string;
  cancelText?: string;
  isDanger?: boolean;
  isLoading?: boolean;
  onConfirm: () => void | Promise<void>;
  onCancel: () => void;
}

export const ConfirmModal: FC<ConfirmModalProps> = ({
  isOpen,
  title,
  prompt,
  message,
  confirmLabel,
  confirmText,
  cancelLabel,
  cancelText,
  isDanger = false,
  isLoading = false,
  onConfirm,
  onCancel,
}) => {
  const displayPrompt = prompt || message || '';
  const confirmBtnText = confirmText || confirmLabel || (isDanger ? 'Yes, Confirm' : 'Confirm');
  const cancelBtnText = cancelText || cancelLabel || 'Cancel';

  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !isLoading) {
        onCancel();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, isLoading, onCancel]);

  if (!isOpen) return null;

  const handleBackdropClick = (e: MouseEvent<HTMLDivElement>) => {
    if (e.target === e.currentTarget && !isLoading) {
      onCancel();
    }
  };

  return (
    <div
      data-testid="confirm-modal-backdrop"
      onClick={handleBackdropClick}
      className="fixed inset-0 z-50 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4"
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-modal-title"
        data-testid="confirm-modal"
        className={`bg-zinc-900 border ${
          isDanger ? 'border-rose-600/70 shadow-rose-950/40' : 'border-zinc-700 shadow-black/50'
        } rounded-lg max-w-md w-full p-6 shadow-2xl flex flex-col gap-4 text-zinc-100 animate-in fade-in zoom-in-95 duration-150`}
      >
        <div className="flex items-start justify-between gap-3">
          <h2
            id="confirm-modal-title"
            data-testid="confirm-modal-title"
            className={`text-lg font-bold tracking-tight ${isDanger ? 'text-rose-400' : 'text-zinc-100'}`}
          >
            {title}
          </h2>
          <button
            type="button"
            data-testid="confirm-modal-close"
            onClick={onCancel}
            disabled={isLoading}
            aria-label="Close dialog"
            className="text-zinc-400 hover:text-zinc-200 transition-colors p-1 rounded hover:bg-zinc-800 disabled:opacity-50"
          >
            &times;
          </button>
        </div>

        {displayPrompt && (
          <p
            data-testid="confirm-modal-prompt"
            className="text-sm text-zinc-300 leading-relaxed"
          >
            {displayPrompt}
          </p>
        )}

        <div className="flex items-center justify-end gap-3 mt-2 pt-2 border-t border-zinc-800">
          <button
            type="button"
            data-testid="confirm-modal-cancel"
            onClick={onCancel}
            disabled={isLoading}
            className="px-4 py-2 text-sm font-medium rounded-md bg-zinc-800 hover:bg-zinc-700 text-zinc-300 transition-colors disabled:opacity-50 cursor-pointer"
          >
            {cancelBtnText}
          </button>
          <button
            type="button"
            data-testid="confirm-modal-confirm"
            onClick={onConfirm}
            disabled={isLoading}
            className={`px-4 py-2 text-sm font-semibold rounded-md transition-colors disabled:opacity-50 cursor-pointer ${
              isDanger
                ? 'bg-rose-600 hover:bg-rose-500 text-white shadow-lg shadow-rose-900/30'
                : 'bg-emerald-600 hover:bg-emerald-500 text-white shadow-lg shadow-emerald-900/30'
            }`}
          >
            {isLoading ? 'Processing...' : confirmBtnText}
          </button>
        </div>
      </div>
    </div>
  );
};

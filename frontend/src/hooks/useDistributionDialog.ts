import { useEffect, useRef } from 'react'

export function useDistributionDialog(isOpen: boolean) {
  const dialog = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    if (!isOpen || !dialog.current) return
    const element = dialog.current, previous = document.activeElement
    if (!element.open) element.showModal()
    return () => {
      if (element.open) element.close()
      if (previous instanceof HTMLElement && previous.isConnected) previous.focus()
    }
  }, [isOpen])
  return dialog
}

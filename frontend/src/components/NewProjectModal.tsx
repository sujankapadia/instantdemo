import { useRef, useState } from 'react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import {
  NewProjectForm,
  type NewProjectInputs,
} from './NewProjectForm'

interface NewProjectModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  willOverwrite: boolean
  /** Title shown in the dialog header. Defaults to "New project";
   *  Layout flips it to "Regenerate demo" when a project already
   *  exists, since the modal serves both cold-start and re-generate
   *  via prefilled values. */
  title?: string
  defaultValues?: Partial<NewProjectInputs>
  onSubmit: (values: NewProjectInputs) => void
  /** Current-voice summary + opener for the Voice dialog (M3),
   *  threaded through to the form's voice row. */
  voiceSummary?: string
  onOpenVoiceSettings?: () => void
}

export function NewProjectModal({
  open,
  onOpenChange,
  willOverwrite,
  title = 'New project',
  defaultValues,
  onSubmit,
  voiceSummary,
  onOpenVoiceSettings,
}: NewProjectModalProps) {
  const [confirmOpen, setConfirmOpen] = useState(false)
  const resolverRef = useRef<((value: boolean) => void) | null>(null)

  const confirmOverwrite = (): Promise<boolean> =>
    new Promise<boolean>((resolve) => {
      resolverRef.current = resolve
      setConfirmOpen(true)
    })

  const resolveConfirm = (value: boolean) => {
    setConfirmOpen(false)
    const resolve = resolverRef.current
    resolverRef.current = null
    if (resolve) resolve(value)
  }

  const handleFormSubmit = (values: NewProjectInputs) => {
    onOpenChange(false)
    onSubmit(values)
  }

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{title}</DialogTitle>
            <DialogDescription>
              The studio watches your app, proposes a plan, and you review
              the storyboard before anything is recorded.
            </DialogDescription>
          </DialogHeader>
          <NewProjectForm
            defaultValues={defaultValues}
            onSubmit={handleFormSubmit}
            onCancel={() => onOpenChange(false)}
            confirmOverwrite={willOverwrite ? confirmOverwrite : undefined}
            voiceSummary={voiceSummary}
            onOpenVoiceSettings={onOpenVoiceSettings}
          />
        </DialogContent>
      </Dialog>

      <AlertDialog
        open={confirmOpen}
        onOpenChange={(next) => {
          // If the alert dialog is being closed (e.g. via Esc) without an
          // explicit Cancel/Overwrite click, treat it as Cancel.
          if (!next && resolverRef.current) {
            resolveConfirm(false)
          } else {
            setConfirmOpen(next)
          }
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Plan a new version of this demo?</AlertDialogTitle>
            <AlertDialogDescription>
              The studio re-explores your app and proposes a fresh plan —
              you'll confirm it and review the new storyboard before
              anything is re-recorded. Your current film is kept as a
              version you can flip back to.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={() => resolveConfirm(false)}>
              Cancel
            </AlertDialogCancel>
            <AlertDialogAction onClick={() => resolveConfirm(true)}>
              Plan the new version
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}

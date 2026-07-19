import { CheckCircle2 } from "lucide-react";
import { Dialog } from "./Dialog";
import { Button } from "./Button";

export interface SuccessDialogProps {
  open: boolean;
  onClose: () => void;
  title?: string;
  description?: string;
  actionLabel?: string;
}

export function SuccessDialog({
  open,
  onClose,
  title = "All set!",
  description = "Your changes have been saved successfully.",
  actionLabel = "Done",
}: SuccessDialogProps) {
  return (
    <Dialog open={open} onClose={onClose}>
      <div className="flex flex-col items-center text-center">
        <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-emerald-50 text-emerald-600">
          <CheckCircle2 className="h-6 w-6" />
        </div>
        <h2 className="text-lg font-semibold text-slate-900">{title}</h2>
        <p className="mt-1 text-sm text-slate-500">{description}</p>
        <Button className="mt-6 w-full" onClick={onClose}>
          {actionLabel}
        </Button>
      </div>
    </Dialog>
  );
}

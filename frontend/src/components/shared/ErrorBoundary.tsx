import * as React from "react";
import { TriangleAlert } from "lucide-react";
import { Button } from "@/components/ui/Button";

interface ErrorBoundaryState {
  hasError: boolean;
}

/**
 * Catches render-time exceptions anywhere below it so one broken
 * page (e.g. a bad API response feeding a chart) shows a recovery
 * screen instead of an unrecoverable blank white app.
 */
export class ErrorBoundary extends React.Component<React.PropsWithChildren, ErrorBoundaryState> {
  state: ErrorBoundaryState = { hasError: false };

  static getDerivedStateFromError(): ErrorBoundaryState {
    return { hasError: true };
  }

  componentDidCatch(error: unknown, info: React.ErrorInfo) {
    console.error("Unhandled render error caught by ErrorBoundary", error, info.componentStack);
  }

  render() {
    if (!this.state.hasError) return this.props.children;

    return (
      <div className="flex min-h-screen items-center justify-center bg-cream-100 px-4">
        <div className="flex max-w-sm flex-col items-center rounded-xl border border-dashed border-slate-200 bg-white px-6 py-16 text-center">
          <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-red-50 text-red-500">
            <TriangleAlert className="h-5 w-5" />
          </div>
          <p className="text-sm font-semibold text-slate-800">Something went wrong</p>
          <p className="mt-1 text-sm text-slate-500">
            This page hit an unexpected error. Reloading usually fixes it.
          </p>
          <Button className="mt-5" onClick={() => window.location.reload()}>
            Reload page
          </Button>
        </div>
      </div>
    );
  }
}

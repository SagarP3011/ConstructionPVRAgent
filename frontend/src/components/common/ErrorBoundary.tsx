import { Component, type ErrorInfo, type ReactNode } from "react";

interface ErrorBoundaryProps {
  children: ReactNode;
  onReset: () => void;
}

interface ErrorBoundaryState {
  error: Error | null;
}

/** Keeps a display error from blanking the page: shows what happened and a way back. */
export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("PVR Agent Room display error", error, info.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <main className="flex flex-1 items-center justify-center bg-surface p-8">
        <div className="max-w-lg rounded-card border border-alert bg-bg p-6 text-sm" role="alert">
          <h2 className="mb-2 text-base">Something went wrong while showing this run</h2>
          <p className="mb-4 text-text-muted">{this.state.error.message}</p>
          <button
            type="button"
            onClick={() => {
              this.setState({ error: null });
              this.props.onReset();
            }}
            className="rounded-full bg-accent px-4 py-2 font-semibold text-white"
          >
            Back to the change selector
          </button>
        </div>
      </main>
    );
  }
}

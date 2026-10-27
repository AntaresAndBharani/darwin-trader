import { Component, ErrorInfo, ReactNode } from 'react';

export interface ErrorBoundaryProps {
  children: ReactNode;
  fallbackTitle?: string;
  onReset?: () => void;
}

export interface ErrorBoundaryState {
  hasError: boolean;
  errorMessage: string;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = {
      hasError: false,
      errorMessage: '',
    };
  }

  static getDerivedStateFromError(error: unknown): ErrorBoundaryState {
    const errorMessage =
      error instanceof Error ? error.message : 'An unexpected rendering error occurred.';
    return {
      hasError: true,
      errorMessage,
    };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    console.error('[WorkspaceErrorBoundary] Caught rendering error:', error, errorInfo);
  }

  handleReset = (): void => {
    this.setState({ hasError: false, errorMessage: '' });
    if (this.props.onReset) {
      this.props.onReset();
    }
  };

  render(): ReactNode {
    if (this.state.hasError) {
      return (
        <div
          data-testid="workspace-error-boundary"
          role="alert"
          className="bg-rose-950/60 border border-rose-800 rounded-lg p-6 flex flex-col items-start gap-3 text-rose-100"
        >
          <div className="flex items-center gap-2">
            <span className="text-sm font-bold text-rose-300">
              {this.props.fallbackTitle || 'Workspace Rendering Error'}
            </span>
          </div>
          <p className="text-xs text-rose-200/90 font-mono">
            {this.state.errorMessage || 'An unexpected rendering error occurred in this workspace.'}
          </p>
          <button
            type="button"
            data-testid="workspace-error-reset-btn"
            onClick={this.handleReset}
            className="px-3.5 py-1.5 rounded text-xs font-semibold bg-rose-800 hover:bg-rose-700 text-white border border-rose-600 transition-colors cursor-pointer"
          >
            Reset Workspace
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;

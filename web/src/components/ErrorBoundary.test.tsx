import { FC, useState } from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ErrorBoundary } from './ErrorBoundary';

const CrashingChild: FC<{ shouldThrow: boolean }> = ({ shouldThrow }) => {
  if (shouldThrow) {
    throw new TypeError("Cannot read properties of undefined (reading 'toFixed')");
  }
  return <div data-testid="healthy-child">Workspace Healthy</div>;
};

describe('ErrorBoundary', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('catches child rendering exceptions, renders the recovery fallback card, and resets cleanly', () => {
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    const onResetSpy = vi.fn();

    const Wrapper: FC = () => {
      const [shouldThrow, setShouldThrow] = useState(true);
      return (
        <ErrorBoundary
          fallbackTitle="Strategy Lifecycle & Backtesting Encountered a Rendering Error"
          onReset={() => {
            onResetSpy();
            setShouldThrow(false);
          }}
        >
          <CrashingChild shouldThrow={shouldThrow} />
        </ErrorBoundary>
      );
    };

    render(<Wrapper />);

    const boundaryCard = screen.getByTestId('workspace-error-boundary');
    expect(boundaryCard).toBeInTheDocument();
    expect(boundaryCard).toHaveTextContent(
      'Strategy Lifecycle & Backtesting Encountered a Rendering Error',
    );
    expect(boundaryCard).toHaveTextContent(
      "Cannot read properties of undefined (reading 'toFixed')",
    );

    // Click Reset Workspace button
    fireEvent.click(screen.getByTestId('workspace-error-reset-btn'));

    expect(onResetSpy).toHaveBeenCalledTimes(1);
    expect(screen.queryByTestId('workspace-error-boundary')).not.toBeInTheDocument();
    expect(screen.getByTestId('healthy-child')).toHaveTextContent('Workspace Healthy');

    consoleSpy.mockRestore();
  });
});

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ConfirmModal } from './ConfirmModal';

describe('ConfirmModal Component', () => {
  it('does not render when isOpen is false', () => {
    const { container } = render(
      <ConfirmModal
        isOpen={false}
        title="Test Modal"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders modal dialog with title, prompt, and action buttons when open', () => {
    render(
      <ConfirmModal
        isOpen={true}
        title="Confirm Deletion"
        prompt="Are you sure you want to proceed?"
        confirmText="Proceed"
        cancelText="Dismiss"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />
    );

    expect(screen.getByTestId('confirm-modal')).toBeInTheDocument();
    expect(screen.getByTestId('confirm-modal-title')).toHaveTextContent('Confirm Deletion');
    expect(screen.getByTestId('confirm-modal-prompt')).toHaveTextContent('Are you sure you want to proceed?');
    expect(screen.getByTestId('confirm-modal-confirm')).toHaveTextContent('Proceed');
    expect(screen.getByTestId('confirm-modal-cancel')).toHaveTextContent('Dismiss');
  });

  it('invokes onConfirm when confirm button is clicked', () => {
    const handleConfirm = vi.fn();
    render(
      <ConfirmModal
        isOpen={true}
        title="Action Required"
        onConfirm={handleConfirm}
        onCancel={vi.fn()}
      />
    );

    fireEvent.click(screen.getByTestId('confirm-modal-confirm'));
    expect(handleConfirm).toHaveBeenCalledTimes(1);
  });

  it('invokes onCancel when cancel button is clicked (Scenario 4)', () => {
    const handleCancel = vi.fn();
    render(
      <ConfirmModal
        isOpen={true}
        title="Action Required"
        onConfirm={vi.fn()}
        onCancel={handleCancel}
      />
    );

    fireEvent.click(screen.getByTestId('confirm-modal-cancel'));
    expect(handleCancel).toHaveBeenCalledTimes(1);
  });

  it('invokes onCancel when close (X) button is clicked (Scenario 4)', () => {
    const handleCancel = vi.fn();
    render(
      <ConfirmModal
        isOpen={true}
        title="Action Required"
        onConfirm={vi.fn()}
        onCancel={handleCancel}
      />
    );

    fireEvent.click(screen.getByTestId('confirm-modal-close'));
    expect(handleCancel).toHaveBeenCalledTimes(1);
  });

  it('invokes onCancel when backdrop overlay is clicked (Scenario 4)', () => {
    const handleCancel = vi.fn();
    render(
      <ConfirmModal
        isOpen={true}
        title="Action Required"
        onConfirm={vi.fn()}
        onCancel={handleCancel}
      />
    );

    fireEvent.click(screen.getByTestId('confirm-modal-backdrop'));
    expect(handleCancel).toHaveBeenCalledTimes(1);
  });

  it('does NOT invoke onCancel when clicking inside the dialog content', () => {
    const handleCancel = vi.fn();
    render(
      <ConfirmModal
        isOpen={true}
        title="Action Required"
        prompt="Safe content"
        onConfirm={vi.fn()}
        onCancel={handleCancel}
      />
    );

    fireEvent.click(screen.getByTestId('confirm-modal'));
    expect(handleCancel).not.toHaveBeenCalled();
  });

  it('invokes onCancel when Escape key is pressed', () => {
    const handleCancel = vi.fn();
    render(
      <ConfirmModal
        isOpen={true}
        title="Action Required"
        onConfirm={vi.fn()}
        onCancel={handleCancel}
      />
    );

    fireEvent.keyDown(window, { key: 'Escape' });
    expect(handleCancel).toHaveBeenCalledTimes(1);
  });

  it('applies danger styling when isDanger is true', () => {
    render(
      <ConfirmModal
        isOpen={true}
        title="EMERGENCY KILL SWITCH"
        isDanger={true}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />
    );

    expect(screen.getByTestId('confirm-modal-title')).toHaveClass('text-rose-400');
    expect(screen.getByTestId('confirm-modal-confirm')).toHaveClass('bg-rose-600');
  });

  it('disables buttons when isLoading is true', () => {
    render(
      <ConfirmModal
        isOpen={true}
        title="Processing"
        isLoading={true}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />
    );

    expect(screen.getByTestId('confirm-modal-confirm')).toBeDisabled();
    expect(screen.getByTestId('confirm-modal-cancel')).toBeDisabled();
    expect(screen.getByTestId('confirm-modal-close')).toBeDisabled();
  });
});

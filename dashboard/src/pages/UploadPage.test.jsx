import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import UploadPage from './UploadPage';

// Mock PhotoUpload to isolate UploadPage tests
vi.mock('../components/shared/PhotoUpload', () => ({
  default: (props) => (
    <div data-testid="photo-upload">
      {props.contractId && <span>contractId={props.contractId}</span>}
      {props.claimId && <span>claimId={props.claimId}</span>}
    </div>
  ),
}));

describe('UploadPage', () => {
  it('renders page heading', () => {
    render(
      <MemoryRouter>
        <UploadPage />
      </MemoryRouter>
    );
    expect(screen.getByText('Upload')).toBeInTheDocument();
  });

  it('renders description text', () => {
    render(
      <MemoryRouter>
        <UploadPage />
      </MemoryRouter>
    );
    expect(screen.getByText(/Upload claim photos for fraud analysis/)).toBeInTheDocument();
  });

  it('renders PhotoUpload component without pre-filled IDs', () => {
    render(
      <MemoryRouter>
        <UploadPage />
      </MemoryRouter>
    );
    const upload = screen.getByTestId('photo-upload');
    expect(upload).toBeInTheDocument();
    // Should NOT have pre-filled IDs
    expect(screen.queryByText(/contractId=/)).not.toBeInTheDocument();
    expect(screen.queryByText(/claimId=/)).not.toBeInTheDocument();
  });
});

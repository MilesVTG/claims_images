import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import PhotoUpload from './PhotoUpload';

// Mock the api client
vi.mock('../../api/client', () => ({
  default: {
    upload: vi.fn(),
    get: vi.fn(),
  },
}));

import api from '../../api/client';

function createFile(name = 'test.jpg', size = 1024, type = 'image/jpeg') {
  const content = new Uint8Array(size);
  return new File([content], name, { type });
}

describe('PhotoUpload', () => {
  const user = userEvent.setup();

  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders with terminal header', () => {
    render(<PhotoUpload />);
    expect(screen.getByText('> upload_photo')).toBeInTheDocument();
  });

  it('shows contract/claim ID inputs when not pre-filled', () => {
    render(<PhotoUpload />);
    expect(screen.getByPlaceholderText('e.g. CNT-001')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('e.g. CLM-001')).toBeInTheDocument();
  });

  it('hides ID inputs when contractId and claimId are provided', () => {
    render(<PhotoUpload contractId="CNT-001" claimId="CLM-001" />);
    expect(screen.queryByPlaceholderText('e.g. CNT-001')).not.toBeInTheDocument();
    expect(screen.queryByPlaceholderText('e.g. CLM-001')).not.toBeInTheDocument();
  });

  it('upload button is disabled with no file', () => {
    render(<PhotoUpload contractId="CNT-001" claimId="CLM-001" />);
    expect(screen.getByText('[upload]')).toBeDisabled();
  });

  it('shows file name and size after selecting a file', async () => {
    render(<PhotoUpload contractId="CNT-001" claimId="CLM-001" />);

    const fileInput = document.querySelector('input[type="file"]');
    const file = createFile('photo.jpg', 2048);
    await user.upload(fileInput, file);

    expect(screen.getByText(/photo\.jpg/)).toBeInTheDocument();
    expect(screen.getByText(/2 KB/)).toBeInTheDocument();
  });

  it('rejects files over 20 MB', async () => {
    render(<PhotoUpload contractId="CNT-001" claimId="CLM-001" />);

    const fileInput = document.querySelector('input[type="file"]');
    const bigFile = createFile('huge.jpg', 21 * 1024 * 1024);
    await user.upload(fileInput, bigFile);

    expect(screen.getByText(/exceeds 20 MB/)).toBeInTheDocument();
    expect(screen.getByText('[upload]')).toBeDisabled();
  });

  it('enables upload button when file + IDs are present', async () => {
    render(<PhotoUpload contractId="CNT-001" claimId="CLM-001" />);

    const fileInput = document.querySelector('input[type="file"]');
    await user.upload(fileInput, createFile());

    expect(screen.getByText('[upload]')).not.toBeDisabled();
  });

  it('upload button disabled when manual IDs are empty', async () => {
    render(<PhotoUpload />);

    const fileInput = document.querySelector('input[type="file"]');
    await user.upload(fileInput, createFile());

    // IDs are empty, button should be disabled
    expect(screen.getByText('[upload]')).toBeDisabled();
  });

  it('calls api.upload with FormData on submit', async () => {
    api.upload.mockResolvedValue({ storage_key: 'CNT-001/CLM-001/photo_001.jpg', status: 'uploaded' });
    api.get.mockResolvedValue({ storage_key: 'CNT-001/CLM-001/photo_001.jpg', status: 'pending' });

    render(<PhotoUpload contractId="CNT-001" claimId="CLM-001" />);

    const fileInput = document.querySelector('input[type="file"]');
    await user.upload(fileInput, createFile('claim_photo.jpg'));
    await user.click(screen.getByText('[upload]'));

    expect(api.upload).toHaveBeenCalledTimes(1);
    const [path, formData] = api.upload.mock.calls[0];
    expect(path).toBe('/photos/upload');
    expect(formData).toBeInstanceOf(FormData);
    expect(formData.get('contract_id')).toBe('CNT-001');
    expect(formData.get('claim_id')).toBe('CLM-001');
    expect(formData.get('file')).toBeInstanceOf(File);
  });

  it('shows uploading status during upload', async () => {
    let resolveUpload;
    api.upload.mockReturnValue(new Promise((r) => { resolveUpload = r; }));

    render(<PhotoUpload contractId="CNT-001" claimId="CLM-001" />);

    const fileInput = document.querySelector('input[type="file"]');
    await user.upload(fileInput, createFile());
    await user.click(screen.getByText('[upload]'));

    expect(screen.getByText(/Uploading/)).toBeInTheDocument();

    // Resolve to avoid unhandled promise
    resolveUpload({ storage_key: 'x', status: 'uploaded' });
  });

  it('polls status after successful upload', async () => {
    api.upload.mockResolvedValue({ storage_key: 'CNT/CLM/photo_001.jpg', status: 'uploaded' });
    api.get.mockResolvedValue({ storage_key: 'CNT/CLM/photo_001.jpg', status: 'pending' });

    render(<PhotoUpload contractId="CNT" claimId="CLM" />);

    const fileInput = document.querySelector('input[type="file"]');
    await user.upload(fileInput, createFile());
    await user.click(screen.getByText('[upload]'));

    // Wait for upload to complete and polling to start
    await waitFor(() => {
      expect(screen.getByText(/Processing|waiting/i)).toBeInTheDocument();
    });

    // Advance timer to trigger poll
    await vi.advanceTimersByTimeAsync(5000);

    expect(api.get).toHaveBeenCalledWith('/photos/status/CNT/CLM/photo_001.jpg');
  });

  it('shows done status when pipeline completes', async () => {
    api.upload.mockResolvedValue({ storage_key: 'CNT/CLM/photo_001.jpg', status: 'uploaded' });
    api.get.mockResolvedValueOnce({ status: 'pending' });
    api.get.mockResolvedValueOnce({ status: 'completed' });

    const onComplete = vi.fn();
    render(<PhotoUpload contractId="CNT" claimId="CLM" onUploadComplete={onComplete} />);

    const fileInput = document.querySelector('input[type="file"]');
    await user.upload(fileInput, createFile());
    await user.click(screen.getByText('[upload]'));

    // First poll — still pending
    await vi.advanceTimersByTimeAsync(5000);
    // Second poll — completed
    await vi.advanceTimersByTimeAsync(5000);

    await waitFor(() => {
      expect(screen.getByText(/complete/i)).toBeInTheDocument();
    });
    expect(onComplete).toHaveBeenCalledTimes(1);
  });

  it('shows error status when upload fails', async () => {
    api.upload.mockRejectedValue(new Error('File type not allowed'));

    render(<PhotoUpload contractId="CNT" claimId="CLM" />);

    const fileInput = document.querySelector('input[type="file"]');
    await user.upload(fileInput, createFile());
    await user.click(screen.getByText('[upload]'));

    await waitFor(() => {
      expect(screen.getByText(/File type not allowed/)).toBeInTheDocument();
    });
  });

  it('shows error when pipeline processing fails', async () => {
    api.upload.mockResolvedValue({ storage_key: 'x', status: 'uploaded' });
    api.get.mockResolvedValue({ status: 'failed' });

    render(<PhotoUpload contractId="CNT" claimId="CLM" />);

    const fileInput = document.querySelector('input[type="file"]');
    await user.upload(fileInput, createFile());
    await user.click(screen.getByText('[upload]'));

    await vi.advanceTimersByTimeAsync(5000);

    await waitFor(() => {
      expect(screen.getByText(/failed/i)).toBeInTheDocument();
    });
  });

  it('reset button clears state', async () => {
    api.upload.mockRejectedValue(new Error('Oops'));

    render(<PhotoUpload contractId="CNT" claimId="CLM" />);

    const fileInput = document.querySelector('input[type="file"]');
    await user.upload(fileInput, createFile());
    await user.click(screen.getByText('[upload]'));

    await waitFor(() => {
      expect(screen.getByText('[reset]')).toBeInTheDocument();
    });

    await user.click(screen.getByText('[reset]'));

    expect(screen.queryByText(/Oops/)).not.toBeInTheDocument();
    expect(screen.queryByText('[reset]')).not.toBeInTheDocument();
    expect(screen.getByText('[upload]')).toBeDisabled();
  });

  it('uses manual IDs when not pre-filled', async () => {
    api.upload.mockResolvedValue({ storage_key: 'X/Y/photo_001.jpg', status: 'uploaded' });
    api.get.mockResolvedValue({ status: 'pending' });

    render(<PhotoUpload />);

    const contractInput = screen.getByPlaceholderText('e.g. CNT-001');
    const claimInput = screen.getByPlaceholderText('e.g. CLM-001');

    await user.type(contractInput, 'X');
    await user.type(claimInput, 'Y');

    const fileInput = document.querySelector('input[type="file"]');
    await user.upload(fileInput, createFile());
    await user.click(screen.getByText('[upload]'));

    const [, formData] = api.upload.mock.calls[0];
    expect(formData.get('contract_id')).toBe('X');
    expect(formData.get('claim_id')).toBe('Y');
  });
});

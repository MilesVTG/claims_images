import { useState, useRef, useEffect } from 'react';
import api from '../../api/client';

const SPINNER_FRAMES = ['|', '/', '-', '\\'];
const ACCEPTED_TYPES = '.jpg,.jpeg,.png,.webp';
const MAX_SIZE = 20 * 1024 * 1024; // 20 MB
const POLL_INTERVAL = 5000;

function TerminalSpinner({ text }) {
  const [frame, setFrame] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setFrame((f) => (f + 1) % SPINNER_FRAMES.length), 120);
    return () => clearInterval(id);
  }, []);
  return <span className="terminal-spinner">{SPINNER_FRAMES[frame]} {text}</span>;
}

function PhotoUpload({ contractId, claimId, onUploadComplete }) {
  const [file, setFile] = useState(null);
  const [contractInput, setContractInput] = useState(contractId || '');
  const [claimInput, setClaimInput] = useState(claimId || '');
  const [status, setStatus] = useState('idle'); // idle | uploading | polling | done | error
  const [message, setMessage] = useState('');
  const fileRef = useRef(null);
  const pollRef = useRef(null);

  // Clean up polling on unmount
  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  function handleFileChange(e) {
    const selected = e.target.files[0];
    if (!selected) return;

    if (selected.size > MAX_SIZE) {
      setMessage('File exceeds 20 MB limit');
      setFile(null);
      return;
    }

    setFile(selected);
    setMessage('');
  }

  function pollStatus(storageKey) {
    setStatus('polling');
    setMessage('Processing...');

    pollRef.current = setInterval(async () => {
      try {
        const data = await api.get(`/photos/status/${storageKey}`);
        if (data.status === 'completed' || data.status === 'processed') {
          clearInterval(pollRef.current);
          pollRef.current = null;
          setStatus('done');
          setMessage('Upload complete — pipeline finished');
          if (onUploadComplete) onUploadComplete();
        } else if (data.status === 'error' || data.status === 'failed') {
          clearInterval(pollRef.current);
          pollRef.current = null;
          setStatus('error');
          setMessage('Pipeline processing failed');
        }
      } catch {
        // Keep polling on transient errors
      }
    }, POLL_INTERVAL);
  }

  async function handleUpload() {
    if (!file || !contractInput.trim() || !claimInput.trim()) return;

    setStatus('uploading');
    setMessage('Uploading...');

    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('contract_id', contractInput.trim());
      formData.append('claim_id', claimInput.trim());

      const result = await api.upload('/photos/upload', formData);
      setMessage('Uploaded — waiting for pipeline...');
      pollStatus(result.storage_key);
    } catch (err) {
      setStatus('error');
      setMessage(err.message || 'Upload failed');
    }
  }

  function handleReset() {
    if (pollRef.current) clearInterval(pollRef.current);
    setFile(null);
    setStatus('idle');
    setMessage('');
    if (fileRef.current) fileRef.current.value = '';
  }

  const isPreFilled = Boolean(contractId && claimId);
  const canUpload = file && contractInput.trim() && claimInput.trim() && status !== 'uploading' && status !== 'polling';

  return (
    <div className="photo-upload">
      <div className="photo-upload__header">// UPLOAD PHOTO</div>

      <div className="photo-upload__fields">
        {!isPreFilled && (
          <>
            <label className="photo-upload__label">
              contract_id:
              <input
                type="text"
                value={contractInput}
                onChange={(e) => setContractInput(e.target.value)}
                disabled={status === 'uploading' || status === 'polling'}
                className="photo-upload__input"
                placeholder="e.g. CNT-001"
              />
            </label>
            <label className="photo-upload__label">
              claim_id:
              <input
                type="text"
                value={claimInput}
                onChange={(e) => setClaimInput(e.target.value)}
                disabled={status === 'uploading' || status === 'polling'}
                className="photo-upload__input"
                placeholder="e.g. CLM-001"
              />
            </label>
          </>
        )}
        <div className="photo-upload__file-row">
          <input
            ref={fileRef}
            type="file"
            accept={ACCEPTED_TYPES}
            onChange={handleFileChange}
            disabled={status === 'uploading' || status === 'polling'}
            className="photo-upload__file-input"
          />
          {file && <span className="photo-upload__filename">{file.name} ({(file.size / 1024).toFixed(0)} KB)</span>}
        </div>
      </div>

      <div className="photo-upload__actions">
        <button
          className="photo-upload__btn photo-upload__btn--submit"
          onClick={handleUpload}
          disabled={!canUpload}
        >
          [upload]
        </button>
        {status !== 'idle' && (
          <button
            className="photo-upload__btn photo-upload__btn--reset"
            onClick={handleReset}
          >
            [reset]
          </button>
        )}
      </div>

      {message && (
        <div className={`photo-upload__status photo-upload__status--${status}`}>
          {(status === 'uploading' || status === 'polling') ? (
            <TerminalSpinner text={message} />
          ) : (
            <span>{status === 'done' ? '✓' : status === 'error' ? '✗' : '>'} {message}</span>
          )}
        </div>
      )}
    </div>
  );
}

export default PhotoUpload;

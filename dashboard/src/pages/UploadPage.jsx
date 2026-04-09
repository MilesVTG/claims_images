import { useState } from 'react';
import PhotoUpload from '../components/shared/PhotoUpload';

function UploadPage() {
  const [key, setKey] = useState(0);

  function handleComplete() {
    // Reset form for another upload
    setKey((k) => k + 1);
  }

  return (
    <div className="page upload-page">
      <h1>Upload</h1>
      <p className="page-desc">Upload claim photos for fraud analysis. The pipeline processes automatically after upload.</p>
      <div className="detail-card detail-card--full">
        <PhotoUpload key={key} onUploadComplete={handleComplete} />
      </div>
    </div>
  );
}

export default UploadPage;

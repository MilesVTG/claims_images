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
      <h1>&gt; upload</h1>
      <p className="upload-page__desc">
        Upload claim photos for fraud analysis. The pipeline processes automatically after upload.
      </p>
      <PhotoUpload key={key} onUploadComplete={handleComplete} />
    </div>
  );
}

export default UploadPage;

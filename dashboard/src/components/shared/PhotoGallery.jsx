import { useState } from 'react';

function PhotoGallery({ photos }) {
  const [selected, setSelected] = useState(null);

  if (!photos || photos.length === 0) {
    return <p className="empty-state">No photos available.</p>;
  }

  return (
    <>
      <div className="photo-gallery">
        {photos.map((photo, i) => (
          <div
            key={photo.storage_key || i}
            className="photo-thumb"
            onClick={() => setSelected(photo)}
          >
            <img
              src={photo.presigned_url || photo.url}
              alt={`Claim photo ${i + 1}`}
              loading="lazy"
            />
          </div>
        ))}
      </div>

      {selected && (
        <div className="lightbox-overlay" onClick={() => setSelected(null)}>
          <div className="lightbox-content" onClick={(e) => e.stopPropagation()}>
            <button
              className="lightbox-close"
              onClick={() => setSelected(null)}
              aria-label="Close"
            >
              x
            </button>
            <img
              className="lightbox-image"
              src={selected.presigned_url || selected.url}
              alt="Enlarged claim photo"
            />
            <div className="lightbox-meta">
              <h3>EXIF Data</h3>
              <ExifDetails exif={selected.extracted_metadata || selected.exif} />
            </div>
          </div>
        </div>
      )}
    </>
  );
}

function ExifDetails({ exif }) {
  if (!exif || Object.keys(exif).length === 0) {
    return <p>No EXIF data available.</p>;
  }

  const fields = [
    { key: 'camera_make', label: 'Camera Make' },
    { key: 'camera_model', label: 'Camera Model' },
    { key: 'datetime_original', label: 'Date Taken' },
    { key: 'gps_latitude', label: 'GPS Lat' },
    { key: 'gps_longitude', label: 'GPS Lon' },
    { key: 'software', label: 'Software' },
    { key: 'image_width', label: 'Width' },
    { key: 'image_height', label: 'Height' },
  ];

  return (
    <dl>
      {fields.map(({ key, label }) => {
        const val = exif[key];
        if (val == null || val === '') return null;
        return (
          <span key={key}>
            <dt>{label}</dt>
            <dd>{String(val)}</dd>
          </span>
        );
      })}
    </dl>
  );
}

export default PhotoGallery;

import { useState, useEffect, useRef } from 'react';

const STAR_CHARS = ['-', '|', '\\', '/', '─', '│', '╲', '╱', '·', '•', '+', '×'];

function AsciiStars({ count = 6, className = '', delay = 0, duration = 1500 }) {
  const [stars, setStars] = useState([]);
  const [active, setActive] = useState(false);
  const intervalRef = useRef(null);

  useEffect(() => {
    // Wait for delay (e.g. after matrix text finishes), then start
    const startTimeout = setTimeout(() => {
      // Initialize stars spread across the full area
      setStars(
        Array.from({ length: count }, (_, i) => ({
          id: i,
          char: STAR_CHARS[Math.floor(Math.random() * STAR_CHARS.length)],
          top: Math.random() * 100,
          left: Math.random() * 100,
          opacity: 0.5 + Math.random() * 0.5,
        }))
      );
      setActive(true);

      // Rapid cycling — fast spangle
      intervalRef.current = setInterval(() => {
        setStars((prev) =>
          prev.map((s) => ({
            ...s,
            char: STAR_CHARS[Math.floor(Math.random() * STAR_CHARS.length)],
            top: s.top + (Math.random() - 0.5) * 8,
            left: s.left + (Math.random() - 0.5) * 8,
            opacity: 0.4 + Math.random() * 0.6,
          }))
        );
      }, 60);

      // Stop after duration
      setTimeout(() => {
        clearInterval(intervalRef.current);
        setActive(false);
        setStars([]);
      }, duration);
    }, delay);

    return () => {
      clearTimeout(startTimeout);
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [count, delay, duration]);

  if (!active || stars.length === 0) return null;

  return (
    <span className={`ascii-stars ${className}`}>
      {stars.map((s) => (
        <span
          key={s.id}
          className="ascii-star"
          style={{
            position: 'absolute',
            top: `${s.top}%`,
            left: `${s.left}%`,
            opacity: s.opacity,
          }}
        >
          {s.char}
        </span>
      ))}
    </span>
  );
}

export default AsciiStars;

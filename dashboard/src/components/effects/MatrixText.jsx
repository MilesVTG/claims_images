import { useState, useEffect, useRef } from 'react';

const GLYPHS = '▓▒░╬╠╣╦╩█▄▀┼┤├┬┴─│╪╫◆◇○●◎▲△▼▽★☆♦♢⌘⌥⎔⎕⏣⏢∎∷≡≢⊞⊟⧫⬡⬢';

function MatrixText({ text, className = '', delay = 0 }) {
  const [display, setDisplay] = useState(() => text.split('').map(() => ''));
  const [revealed, setRevealed] = useState(() => text.split('').map(() => false));
  const startedRef = useRef(false);

  useEffect(() => {
    const timeout = setTimeout(() => {
      startedRef.current = true;

      // Randomize the order letters reveal
      const indices = text.split('').map((_, i) => i);
      for (let i = indices.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [indices[i], indices[j]] = [indices[j], indices[i]];
      }

      // Each letter: scramble for a bit, then reveal
      indices.forEach((charIdx, order) => {
        const ch = text[charIdx];
        if (ch === ' ') {
          setDisplay((d) => { const n = [...d]; n[charIdx] = ' '; return n; });
          setRevealed((r) => { const n = [...r]; n[charIdx] = true; return n; });
          return;
        }

        const scrambleStart = order * 60;
        const scrambleTicks = 6 + Math.floor(Math.random() * 8);

        for (let t = 0; t < scrambleTicks; t++) {
          setTimeout(() => {
            const g = GLYPHS[Math.floor(Math.random() * GLYPHS.length)];
            setDisplay((d) => { const n = [...d]; n[charIdx] = g; return n; });
          }, scrambleStart + t * 35);
        }

        // Reveal the real letter
        setTimeout(() => {
          setDisplay((d) => { const n = [...d]; n[charIdx] = ch; return n; });
          setRevealed((r) => { const n = [...r]; n[charIdx] = true; return n; });
        }, scrambleStart + scrambleTicks * 35);
      });
    }, delay);

    return () => clearTimeout(timeout);
  }, [text, delay]);

  return (
    <span className={`matrix-text ${className}`}>
      {display.map((ch, i) => (
        <span
          key={i}
          className={revealed[i] ? 'matrix-char matrix-char--revealed' : 'matrix-char matrix-char--scrambling'}
        >
          {ch || '\u00A0'}
        </span>
      ))}
    </span>
  );
}

export default MatrixText;

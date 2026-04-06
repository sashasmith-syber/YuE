/**
 * Engine mode toggle: Quick (MusicGen) vs Studio (YuE).
 * Prompt 004 — extension UI.
 */
import React, { useState } from 'react';

export type EngineMode = 'quick' | 'studio';

interface EngineToggleProps {
  value?: EngineMode;
  onChange?: (mode: EngineMode) => void;
  disabled?: boolean;
  className?: string;
}

export const EngineToggle: React.FC<EngineToggleProps> = ({
  value = 'quick',
  onChange,
  disabled = false,
  className = '',
}) => {
  const [mode, setMode] = useState<EngineMode>(value);

  const handleClick = (m: EngineMode) => {
    if (disabled) return;
    setMode(m);
    onChange?.(m);
  };

  return (
    <div className={`engine-toggle ${className}`} role="group" aria-label="Engine mode">
      <button
        type="button"
        className={mode === 'quick' ? 'active' : ''}
        onClick={() => handleClick('quick')}
        disabled={disabled}
        aria-pressed={mode === 'quick'}
      >
        ⚡ Quick (MusicGen)
      </button>
      <button
        type="button"
        className={mode === 'studio' ? 'active' : ''}
        onClick={() => handleClick('studio')}
        disabled={disabled}
        aria-pressed={mode === 'studio'}
      >
        🎚️ Studio (YuE)
      </button>
    </div>
  );
};

export default EngineToggle;

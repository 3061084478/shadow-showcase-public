import { useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { ChevronRight } from 'lucide-react';

type Option<T extends string> = {
  label: string;
  value: T;
};

type DarkSelectProps<T extends string> = {
  value: T;
  options: Option<T>[];
  onChange: (val: T) => void;
  placeholder?: string;
  className?: string;
  label?: string;
};

export function DarkSelect<T extends string>({
  value,
  options,
  onChange,
  placeholder = 'Select...',
  className = '',
  label,
}: DarkSelectProps<T>) {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const currentLabel = options.find((o) => o.value === value)?.label || placeholder;

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  return (
    <div ref={containerRef} className={`relative flex items-center gap-3 ${className}`}>
      {label && <span className="text-[10px] font-bold text-white/20 uppercase tracking-widest whitespace-nowrap">{label}</span>}
      <div className="relative flex-1">
        <button onClick={() => setIsOpen(!isOpen)} className={`dark-select-trigger w-full ${isOpen ? 'active' : ''}`}>
          <span className="text-[11px] font-bold text-white/90 truncate">{currentLabel}</span>
          <motion.div animate={{ rotate: isOpen ? 90 : 0 }}>
            <ChevronRight size={14} className="text-white/30" />
          </motion.div>
        </button>

        <AnimatePresence>
          {isOpen && (
            <motion.div
              initial={{ opacity: 0, y: 10, scale: 0.95 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 5, scale: 0.95 }}
              transition={{ duration: 0.2, ease: 'easeOut' }}
              className="dark-select-panel"
              style={{ minWidth: '100%' }}
            >
              {options.map((opt) => (
                <div
                  key={opt.value}
                  onClick={() => {
                    onChange(opt.value);
                    setIsOpen(false);
                  }}
                  className={`dark-select-option ${opt.value === value ? 'selected' : ''}`}
                >
                  {opt.label}
                </div>
              ))}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}

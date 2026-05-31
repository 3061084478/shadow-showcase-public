import { useEffect, useMemo, useRef, useState } from 'react';
import { Calendar, ChevronLeft, ChevronRight } from 'lucide-react';

type DateFieldProps = {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  activeDates?: string[];
  minDate?: string;
};

const WEEKDAY_LABELS = ['一', '二', '三', '四', '五', '六', '日'];

function toMonthKey(date: Date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`;
}

function parseDateString(value: string) {
  if (!value) return null;
  const [yearRaw, monthRaw, dayRaw] = value.split('-');
  const year = Number(yearRaw);
  const month = Number(monthRaw);
  const day = Number(dayRaw);
  if (!year || !month || !day) return null;
  return new Date(year, month - 1, day);
}

function formatDateString(date: Date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}

function monthStart(date: Date) {
  return new Date(date.getFullYear(), date.getMonth(), 1);
}

function shiftMonth(date: Date, offset: number) {
  return new Date(date.getFullYear(), date.getMonth() + offset, 1);
}

function isSameMonth(left: Date, right: Date) {
  return left.getFullYear() === right.getFullYear() && left.getMonth() === right.getMonth();
}

export function DateField({ value, onChange, placeholder = '年/月/日', activeDates = [], minDate = '' }: DateFieldProps) {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const [open, setOpen] = useState(false);

  const minDateString = minDate.trim();
  const sortedActiveDates = useMemo(
    () =>
      [...activeDates]
        .filter(Boolean)
        .filter((item) => (!minDateString ? true : item >= minDateString))
        .sort((left, right) => left.localeCompare(right)),
    [activeDates, minDateString],
  );
  const activeDateSet = useMemo(() => new Set(sortedActiveDates), [sortedActiveDates]);

  const minMonth = useMemo(() => {
    const first = sortedActiveDates[0];
    return first ? monthStart(parseDateString(first) ?? new Date()) : monthStart(new Date());
  }, [sortedActiveDates]);
  const maxMonth = useMemo(() => {
    const last = sortedActiveDates[sortedActiveDates.length - 1];
    return last ? monthStart(parseDateString(last) ?? new Date()) : monthStart(new Date());
  }, [sortedActiveDates]);

  const selectedDate = useMemo(() => parseDateString(value), [value]);
  const [visibleMonth, setVisibleMonth] = useState<Date>(() => monthStart(selectedDate ?? maxMonth));

  useEffect(() => {
    setVisibleMonth(monthStart(selectedDate ?? maxMonth));
  }, [selectedDate, maxMonth]);

  useEffect(() => {
    if (!open) return;
    const handlePointerDown = (event: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    window.addEventListener('mousedown', handlePointerDown);
    window.addEventListener('keydown', handleEscape);
    return () => {
      window.removeEventListener('mousedown', handlePointerDown);
      window.removeEventListener('keydown', handleEscape);
    };
  }, [open]);

  const canGoPrev = visibleMonth.getTime() > minMonth.getTime();
  const canGoNext = visibleMonth.getTime() < maxMonth.getTime();
  const firstWeekday = (() => {
    const jsDay = visibleMonth.getDay();
    return jsDay === 0 ? 6 : jsDay - 1;
  })();
  const daysInMonth = new Date(visibleMonth.getFullYear(), visibleMonth.getMonth() + 1, 0).getDate();
  const calendarCells = Array.from({ length: 42 }, (_, index) => {
    const dayNumber = index - firstWeekday + 1;
    if (dayNumber < 1 || dayNumber > daysInMonth) {
      return null;
    }
    const date = new Date(visibleMonth.getFullYear(), visibleMonth.getMonth(), dayNumber);
    const dateString = formatDateString(date);
    return {
      dateString,
      dayNumber,
      isActive: activeDateSet.has(dateString),
      isSelected: value === dateString,
    };
  });

  return (
    <div ref={rootRef} className="relative">
      <input
        value={value ? value.replace(/-/g, '/') : ''}
        placeholder={placeholder}
        className="search-input-field !h-10 !text-[11px] !pl-3 !pr-12 bg-transparent font-sans"
        onChange={(event) => {
          const normalized = event.target.value.replace(/\//g, '-').trim();
          if (!normalized) {
            onChange('');
            return;
          }
          if (/^\d{4}-\d{2}-\d{2}$/.test(normalized)) {
            if (minDateString && normalized < minDateString) return;
            if (activeDateSet.has(normalized)) {
              onChange(normalized);
            }
          }
        }}
      />
      <button
        type="button"
        onClick={() => {
          if (!sortedActiveDates.length) return;
          setVisibleMonth(monthStart(selectedDate ?? maxMonth));
          setOpen((current) => !current);
        }}
        className="absolute right-1 top-1/2 flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-lg text-white/40 transition hover:bg-white/5 hover:text-white/75"
        aria-label="打开日期选择器"
        disabled={!sortedActiveDates.length}
      >
        <Calendar size={14} />
      </button>
      {open && (
        <div className="active-date-calendar">
          <div className="calendar-header">
            <button
              type="button"
              className="calendar-nav-btn"
              onClick={() => canGoPrev && setVisibleMonth((current) => shiftMonth(current, -1))}
              disabled={!canGoPrev}
            >
              <ChevronLeft size={14} />
            </button>
            <div className="calendar-title">
              {visibleMonth.getFullYear()} 年 {String(visibleMonth.getMonth() + 1).padStart(2, '0')} 月
            </div>
            <button
              type="button"
              className="calendar-nav-btn"
              onClick={() => canGoNext && setVisibleMonth((current) => shiftMonth(current, 1))}
              disabled={!canGoNext}
            >
              <ChevronRight size={14} />
            </button>
          </div>

          <div className="calendar-weekdays">
            {WEEKDAY_LABELS.map((label) => (
              <span key={label}>{label}</span>
            ))}
          </div>

          <div className="calendar-grid">
            {calendarCells.map((cell, index) =>
              cell ? (
                <button
                  key={cell.dateString}
                  type="button"
                  className={`calendar-day ${cell.isActive ? 'active' : 'inactive'} ${cell.isSelected ? 'selected' : ''}`}
                  onClick={() => {
                    onChange(cell.dateString);
                    setOpen(false);
                  }}
                  disabled={!cell.isActive}
                >
                  {cell.dayNumber}
                </button>
              ) : (
                <span key={`empty-${index}`} className="calendar-day-empty" />
              ),
            )}
          </div>

          <div className="calendar-footer">
            <span>
              范围 {toMonthKey(minMonth)} ~ {toMonthKey(maxMonth)}
            </span>
            {selectedDate && isSameMonth(selectedDate, visibleMonth) ? <span>当前已选 {value.replace(/-/g, '/')}</span> : null}
          </div>
        </div>
      )}
    </div>
  );
}

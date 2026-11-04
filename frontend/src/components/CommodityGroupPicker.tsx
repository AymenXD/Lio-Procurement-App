'use client';

import { useMemo, useState } from 'react';
import { useCommodityGroups } from '@/lib/hooks/useCommodityGroups';
import { cn } from '@/lib/utils';

const MAX_RESULTS = 50; // the list has 2,000 groups; show only the best few matches

const label = (g: { id: number; category: string; name: string }) =>
  `${g.id} - ${g.category} - ${g.name}`;

interface Props {
  value: number | null;
  onChange: (id: number | null) => void;
  disabled?: boolean;
  error?: boolean;
  required?: boolean;
}

/** Searchable commodity group picker: type to filter by id, category or name. */
export function CommodityGroupPicker({ value, onChange, disabled, error, required }: Props) {
  const { data: groups } = useCommodityGroups();
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);

  const selected = groups?.find((g) => g.id === value) ?? null;

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    const all = groups ?? [];
    const found = q ? all.filter((g) => label(g).toLowerCase().includes(q)) : all;
    return found.slice(0, MAX_RESULTS);
  }, [groups, query]);

  const pick = (id: number) => {
    onChange(id);
    setQuery('');
    setOpen(false);
  };

  return (
    <div className="relative">
      <input
        type="text"
        value={open ? query : selected ? label(selected) : ''}
        placeholder={groups ? 'Search commodity groups…' : 'Loading...'}
        onFocus={() => setOpen(true)}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
        }}
        // Delay so a click on a result registers before the list closes.
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') {
            e.preventDefault();
            if (matches[0]) pick(matches[0].id);
          } else if (e.key === 'Escape') {
            setOpen(false);
          }
        }}
        disabled={disabled}
        required={required && !value}
        className={cn(
          'w-full px-3 py-2 border rounded-lg text-gray-900 focus:ring-2 focus:ring-accent-deep/60 focus:border-accent-deep/40',
          'disabled:cursor-not-allowed disabled:bg-gray-50',
          error ? 'border-red-500' : 'border-gray-300'
        )}
      />
      {open && !disabled && (
        <ul className="absolute z-20 mt-1 max-h-64 w-full overflow-auto rounded-lg border border-gray-200 bg-white shadow-lg">
          {matches.length === 0 ? (
            <li className="px-3 py-2 text-sm text-gray-500">No matching group</li>
          ) : (
            matches.map((g) => (
              <li key={g.id}>
                <button
                  type="button"
                  onMouseDown={(e) => e.preventDefault()} // keep focus until the pick
                  onClick={() => pick(g.id)}
                  className={cn(
                    'w-full px-3 py-2 text-left text-sm hover:bg-accent-soft/20',
                    g.id === value && 'bg-accent-soft/30 font-medium'
                  )}
                >
                  {label(g)}
                </button>
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  );
}

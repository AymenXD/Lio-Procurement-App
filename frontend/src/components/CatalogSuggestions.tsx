import { useEffect, useState } from 'react';
import type { ArticleSuggestion } from '@/lib/api';
import { Button } from '@/components/base';

// Common ways quotes and the catalog write the same unit.
const UNIT_SYNONYMS: Record<string, string[]> = {
  piece: ['piece', 'pieces', 'pc', 'pcs', 'ea', 'each', 'unit', 'units', 'item', 'items'],
  'sq ft': ['sq ft', 'sqft', 'sq. ft', 'ft²', 'ft2', 'square foot', 'square feet'],
  'lin ft': ['lin ft', 'lin. ft', 'linear foot', 'linear feet', 'lf'],
  license: ['license', 'licenses', 'licence', 'licences', 'lic', 'seat', 'seats'],
  month: ['month', 'months', 'mo'],
  year: ['year', 'years', 'yr', 'annual'],
  hour: ['hour', 'hours', 'hr', 'hrs', 'h'],
  day: ['day', 'days', 'd'],
};

function canonicalUnit(unit: string): string {
  const u = unit.trim().toLowerCase().replace(/\s+/g, ' ').replace(/\.$/, '');
  for (const [canonical, variants] of Object.entries(UNIT_SYNONYMS)) {
    if (variants.includes(u)) return canonical;
  }
  return u.replace(/s$/, '');
}

/** A price difference only makes sense per same unit ("ea." = "piece", "sqft" = "sq ft"). */
export function sameUnit(a: string, b: string): boolean {
  return canonicalUnit(a) !== '' && canonicalUnit(a) === canonicalUnit(b);
}

function money(value: number): string {
  return value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

interface Props {
  suggestions: ArticleSuggestion[];
  lineUnit: string;
  lineAmount: number;
  onStartRequest: (suggestion: ArticleSuggestion) => void;
}

/** Catalog articles similar to one order line: best one first, the rest on demand. */
export function CatalogSuggestions({ suggestions, lineUnit, lineAmount, onStartRequest }: Props) {
  const [dismissed, setDismissed] = useState(false);
  const [showAll, setShowAll] = useState(false);
  // New suggestions (e.g. after "Check catalog prices") are shown again.
  useEffect(() => {
    setDismissed(false);
    setShowAll(false);
  }, [suggestions]);

  if (suggestions.length === 0 || dismissed) return null;
  const visible = showAll ? suggestions : suggestions.slice(0, 1);
  const more = suggestions.length - 1;

  return (
    <div className="mt-3 rounded-xl border border-accent/30 bg-accent-soft/10 p-4">
      <div className="flex items-center justify-between mb-3">
        <p className="text-sm font-medium text-accent-deep">💡 Catalog price available</p>
        <button
          type="button"
          onClick={() => setDismissed(true)}
          className="text-gray-400 hover:text-gray-600 text-sm"
          aria-label="Hide catalog suggestions for this line"
        >
          ✕
        </button>
      </div>

      <div className="space-y-3">
        {visible.map((s) => (
          <SuggestionRow
            key={s.article_id}
            suggestion={s}
            lineUnit={lineUnit}
            lineAmount={lineAmount}
            onStartRequest={onStartRequest}
          />
        ))}
      </div>

      {more > 0 && (
        <button
          type="button"
          onClick={() => setShowAll(!showAll)}
          className="mt-3 text-xs font-medium text-accent-deep hover:underline"
        >
          {showAll ? 'Show less' : `+ ${more} more option${more > 1 ? 's' : ''}`}
        </button>
      )}
    </div>
  );
}

function SuggestionRow({
  suggestion: s,
  lineUnit,
  lineAmount,
  onStartRequest,
}: {
  suggestion: ArticleSuggestion;
  lineUnit: string;
  lineAmount: number;
  onStartRequest: (suggestion: ArticleSuggestion) => void;
}) {
  const diff = s.price_difference === null ? null : Number(s.price_difference);
  const comparable = diff !== null && sameUnit(s.unit, lineUnit);

  return (
    <div className="space-y-2">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-ink">{s.description}</p>
          <p className="text-xs text-gray-500">
            {s.supplier_name ?? 'Unknown supplier'} · negotiated price
          </p>
        </div>
        <p className="shrink-0 text-sm font-semibold text-ink">
          ${money(Number(s.unit_price))}
          <span className="font-normal text-gray-500"> / {s.unit}</span>
        </p>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2">
        {!comparable ? (
          <span className="text-xs text-gray-500">
            {diff === null ? 'No quoted price to compare' : 'Different unit: not directly comparable'}
          </span>
        ) : diff > 0 ? (
          <span className="rounded-full bg-green-100 px-2.5 py-1 text-xs font-medium text-green-800">
            Save ${money(diff)} / {s.unit}
            {lineAmount > 0 && <> · ${money(diff * lineAmount)} on this line</>}
          </span>
        ) : diff === 0 ? (
          <span className="text-xs text-gray-500">Same price as quoted</span>
        ) : (
          <span className="rounded-full bg-gray-100 px-2.5 py-1 text-xs text-gray-600">
            ${money(-diff)} more / {s.unit} than quoted
          </span>
        )}
        <Button type="button" variant="outline" size="sm" onClick={() => onStartRequest(s)}>
          Start request ↗
        </Button>
      </div>
    </div>
  );
}

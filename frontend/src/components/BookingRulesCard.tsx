'use client';

import { useEffect, useState, type KeyboardEvent } from 'react';
import * as api from '@/lib/api';
import type { AppliedBookingRule, BookingRule } from '@/lib/api';
import { Button, Input } from '@/components/base';
import { CommodityGroupPicker } from '@/components/CommodityGroupPicker';
import { useCommodityGroups } from '@/lib/hooks/useCommodityGroups';

interface Props {
  rules: BookingRule[];
  busy: boolean;
  /** Persists the full list; resolves true on success (the page shows the alert). */
  onSave: (next: BookingRule[], message: string) => Promise<boolean>;
}

type Form = {
  label: string;
  keywords: string[];
  groupId: number | null;
  limited: boolean;
  maxTotal: string;
};
const EMPTY: Form = { label: '', keywords: [], groupId: null, limited: false, maxTotal: '2000' };
const MAX_KEYWORDS = 20; // same limit as the backend schema

const money = (n: number) => `$${n.toLocaleString('en-US')}`;

/** "a", "a or b", "a, b or c" */
const orList = (items: string[]) =>
  items.length <= 1
    ? items.join('')
    : `${items.slice(0, -1).join(', ')} or ${items[items.length - 1]}`;

function Chip({ text, onRemove }: { text: string; onRemove?: () => void }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-accent-soft/40 px-2.5 py-0.5 text-xs font-medium text-accent-deep">
      {text}
      {onRemove && (
        <button
          type="button"
          onClick={onRemove}
          aria-label={`Remove ${text}`}
          className="-mr-1 rounded-full px-1 text-accent-deep/60 hover:bg-accent-deep/10 hover:text-accent-deep"
        >
          ×
        </button>
      )}
    </span>
  );
}

/** Keywords as chips: Enter or comma adds one, Backspace on an empty field removes the last. */
function KeywordInput({ value, onChange }: { value: string[]; onChange: (v: string[]) => void }) {
  const [draft, setDraft] = useState('');

  const add = () => {
    const word = draft.trim().replace(/,+$/, '').toLowerCase();
    if (word && !value.includes(word) && value.length < MAX_KEYWORDS) onChange([...value, word]);
    setDraft('');
  };

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault();
      add();
    } else if (e.key === 'Backspace' && !draft && value.length) {
      onChange(value.slice(0, -1));
    }
  };

  return (
    <div className="flex min-h-11 w-full flex-wrap items-center gap-1.5 rounded-xl border border-line bg-white px-2.5 py-2 focus-within:ring-2 focus-within:ring-accent-deep/60">
      {value.map((k) => (
        <Chip key={k} text={k} onRemove={() => onChange(value.filter((x) => x !== k))} />
      ))}
      <input
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={onKeyDown}
        onBlur={add}
        placeholder={value.length ? 'Add another…' : 'Type a word and press Enter, e.g. toner'}
        className="min-w-[10rem] flex-1 bg-transparent px-1 text-sm text-ink placeholder:text-ink/35 focus:outline-none"
      />
    </div>
  );
}

/** Lets admins try their saved rules on an item before a requester does. */
function RuleTester({ rules }: { rules: BookingRule[] }) {
  const [description, setDescription] = useState('');
  const [amount, setAmount] = useState('');
  const [result, setResult] = useState<AppliedBookingRule | null | undefined>(undefined);

  useEffect(() => {
    if (!description.trim()) {
      setResult(undefined);
      return;
    }
    const timer = setTimeout(async () => {
      try {
        const { rule } = await api.requests.bookingRulePreview([
          { description, total_price: Number(amount) || 0 },
        ]);
        setResult(rule);
      } catch {
        setResult(undefined);
      }
    }, 400);
    return () => clearTimeout(timer);
  }, [description, amount, rules]);

  return (
    <div className="mt-6 rounded-xl bg-ink-800/[0.03] p-4">
      <p className="text-sm font-medium text-ink">Test your rules</p>
      <p className="mt-0.5 text-xs text-ink/50">
        Type an item as it would appear on a quote to see where it gets booked.
      </p>
      <div className="mt-3 flex flex-col gap-2 sm:flex-row">
        <Input
          aria-label="Item description"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="HP 305 black toner"
        />
        <div className="relative sm:w-40">
          <span className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-sm text-ink/40">
            $
          </span>
          <Input
            aria-label="Request total"
            type="number"
            min="0"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            placeholder="Total"
            className="pl-7"
          />
        </div>
      </div>
      {result !== undefined && (
        <p
          className={`mt-3 rounded-lg px-3 py-2 text-sm ${
            result ? 'bg-green-50 text-green-800' : 'bg-white text-ink/60 border border-line'
          }`}
        >
          {result ? (
            <>
              ✓ Booked to <strong>{result.commodity_group_name}</strong> by the rule &ldquo;
              {result.label}&rdquo;.
            </>
          ) : (
            'No rule applies. The AI suggestion or the requester’s choice stays.'
          )}
        </p>
      )}
    </div>
  );
}

/** Admin card: the tenant's booking rules (list, add, edit, delete, test). */
export function BookingRulesCard({ rules, busy, onSave }: Props) {
  const { data: groups } = useCommodityGroups();
  const [editing, setEditing] = useState<string | null>(null); // rule id, 'new', or closed
  const [deleting, setDeleting] = useState<string | null>(null);
  const [form, setForm] = useState<Form>(EMPTY);
  const [formError, setFormError] = useState('');

  const group = (id: number | null) => groups?.find((g) => g.id === id);

  const openForm = (rule: BookingRule | null) => {
    setFormError('');
    setDeleting(null);
    setEditing(rule ? rule.id : 'new');
    setForm(
      rule
        ? {
            label: rule.label,
            keywords: rule.keywords,
            groupId: rule.commodity_group_id,
            limited: rule.max_total !== null,
            maxTotal: rule.max_total === null ? '2000' : String(rule.max_total),
          }
        : EMPTY
    );
  };

  const save = async () => {
    const limit = Number(form.maxTotal);
    if (!form.label.trim()) return setFormError('Give the rule a name.');
    if (form.keywords.length === 0) return setFormError('Add at least one keyword.');
    if (!form.groupId) return setFormError('Choose the commodity group to book to.');
    if (form.limited && !(limit > 0)) return setFormError('Enter an amount above $0.');

    const rule: BookingRule = {
      id: editing === 'new' || !editing ? crypto.randomUUID() : editing,
      label: form.label.trim(),
      keywords: form.keywords,
      commodity_group_id: form.groupId,
      max_total: form.limited ? limit : null,
    };
    const next =
      editing === 'new' ? [...rules, rule] : rules.map((r) => (r.id === rule.id ? rule : r));
    if (await onSave(next, editing === 'new' ? 'Rule added' : 'Rule updated')) setEditing(null);
  };

  const remove = async (rule: BookingRule) => {
    if (await onSave(rules.filter((r) => r.id !== rule.id), 'Rule deleted')) setDeleting(null);
  };

  const target = group(form.groupId);
  const summary =
    form.keywords.length && target
      ? `Lines mentioning “${orList(form.keywords)}” will be booked to ${target.name}` +
        (form.limited && Number(form.maxTotal) > 0
          ? `, only when the request total is under ${money(Number(form.maxTotal))}.`
          : '.')
      : 'Add keywords and a commodity group to see what this rule will do.';

  const ruleForm = (
    <div className="space-y-4 rounded-xl border border-accent/40 bg-accent-soft/10 p-4">
      <p className="text-sm font-semibold text-ink">{editing === 'new' ? 'New rule' : 'Edit rule'}</p>
      <Input
        label="Name"
        value={form.label}
        onChange={(e) => setForm({ ...form, label: e.target.value })}
        placeholder="Printer toner"
      />
      <div>
        <label className="mb-1.5 block text-sm font-medium text-ink/70">
          If a line mentions any of these words
        </label>
        <KeywordInput value={form.keywords} onChange={(keywords) => setForm({ ...form, keywords })} />
      </div>
      <div>
        <label className="mb-1.5 block text-sm font-medium text-ink/70">Book it to</label>
        <CommodityGroupPicker value={form.groupId} onChange={(id) => setForm({ ...form, groupId: id })} />
      </div>
      <div>
        <label className="flex cursor-pointer items-center gap-3 text-sm text-ink">
          <input
            type="checkbox"
            checked={form.limited}
            onChange={(e) => setForm({ ...form, limited: e.target.checked })}
            className="h-4 w-4 accent-accent-deep"
          />
          Only for small requests
        </label>
        {form.limited && (
          <div className="mt-2 flex items-center gap-2 pl-7 text-sm text-ink/70">
            Request total under
            <div className="relative w-36">
              <span className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-ink/40">
                $
              </span>
              <Input
                aria-label="Maximum request total"
                type="number"
                min="0"
                step="0.01"
                value={form.maxTotal}
                onChange={(e) => setForm({ ...form, maxTotal: e.target.value })}
                className="pl-7"
              />
            </div>
          </div>
        )}
      </div>
      <p className="rounded-lg bg-white px-3 py-2 text-sm text-ink/70 border border-line">{summary}</p>
      {formError && <p className="text-sm text-red-600">{formError}</p>}
      <div className="flex justify-end gap-2">
        <Button size="sm" variant="ghost" onClick={() => setEditing(null)} disabled={busy}>
          Cancel
        </Button>
        <Button size="sm" onClick={save} loading={busy}>
          Save rule
        </Button>
      </div>
    </div>
  );

  return (
    <div className="lio-card mt-6 p-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold tracking-tight text-ink">Booking Rules</h2>
          <p className="mt-1 text-sm text-ink/55">
            Items that match a rule are always booked to its commodity group, whatever the AI
            suggests or the requester picks.
          </p>
        </div>
        {editing === null && rules.length > 0 && (
          <Button
            size="sm"
            variant="outline"
            onClick={() => openForm(null)}
            disabled={busy}
            className="shrink-0 whitespace-nowrap px-5"
          >
            + Add rule
          </Button>
        )}
      </div>

      <div className="mt-4 space-y-3">
        {rules.length === 0 && editing === null && (
          <div className="rounded-xl border border-dashed border-line p-8 text-center">
            <p className="text-sm font-medium text-ink">No booking rules yet</p>
            <p className="mx-auto mt-1 max-w-sm text-sm text-ink/50">
              Rules make sure items like printer toner always land in the right commodity group.
            </p>
            <Button size="sm" className="mt-4" onClick={() => openForm(null)} disabled={busy}>
              Add your first rule
            </Button>
          </div>
        )}

        {rules.map((rule) =>
          editing === rule.id ? (
            <div key={rule.id}>{ruleForm}</div>
          ) : (
            <div
              key={rule.id}
              className="rounded-xl border border-line p-4 transition-colors hover:bg-ink-800/[0.015]"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="text-sm font-semibold text-ink">{rule.label}</p>
                  {rule.max_total !== null && (
                    <span className="rounded-full bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-800">
                      Only under {money(rule.max_total)}
                    </span>
                  )}
                </div>
                {deleting === rule.id ? (
                  <div className="flex shrink-0 items-center gap-2 text-sm">
                    <span className="text-ink/60">Delete this rule?</span>
                    <Button size="sm" variant="danger" onClick={() => remove(rule)} loading={busy}>
                      Delete
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => setDeleting(null)} disabled={busy}>
                      Keep
                    </Button>
                  </div>
                ) : (
                  <div className="flex shrink-0 gap-1">
                    <Button size="sm" variant="ghost" onClick={() => openForm(rule)} disabled={busy || editing !== null}>
                      Edit
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => setDeleting(rule.id)}
                      disabled={busy || editing !== null}
                      className="hover:text-red-600"
                    >
                      Delete
                    </Button>
                  </div>
                )}
              </div>
              <div className="mt-2 grid gap-2 text-sm sm:grid-cols-[7rem_1fr] sm:items-center">
                <span className="text-ink/50">If a line mentions</span>
                <div className="flex flex-wrap gap-1.5">
                  {rule.keywords.map((k) => (
                    <Chip key={k} text={k} />
                  ))}
                </div>
                <span className="text-ink/50">Book it to</span>
                <span className="text-ink">
                  <strong className="font-medium">
                    {group(rule.commodity_group_id)?.name ?? `Group ${rule.commodity_group_id}`}
                  </strong>
                  {group(rule.commodity_group_id) && (
                    <span className="text-ink/45"> · {group(rule.commodity_group_id)?.category}</span>
                  )}
                </span>
              </div>
            </div>
          )
        )}

        {editing === 'new' && ruleForm}
      </div>

      {rules.length > 0 && <RuleTester rules={rules} />}
    </div>
  );
}

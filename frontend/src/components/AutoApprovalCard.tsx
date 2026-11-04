'use client';

import { useEffect, useState } from 'react';
import type { AutoApprovalPolicy } from '@/lib/api';
import { Button, Input } from '@/components/base';

interface Props {
  policy: AutoApprovalPolicy;
  busy: boolean;
  /** Persists the policy; resolves true on success (the page shows the alert). */
  onSave: (next: AutoApprovalPolicy) => Promise<boolean>;
}

const money = (n: number) => `$${n.toLocaleString('en-US')}`;

/** Admin card: approve small requests without a buyer. */
export function AutoApprovalCard({ policy, busy, onSave }: Props) {
  const [enabled, setEnabled] = useState(policy.enabled);
  const [amount, setAmount] = useState(String(policy.below_amount));
  const [formError, setFormError] = useState('');

  // Follow the server state after a save or reload.
  useEffect(() => {
    setEnabled(policy.enabled);
    setAmount(String(policy.below_amount));
  }, [policy]);

  const limit = Number(amount);
  const dirty = enabled !== policy.enabled || limit !== policy.below_amount;

  const save = async () => {
    if (!(limit > 0)) return setFormError('Enter an amount above $0.');
    setFormError('');
    await onSave({ enabled, below_amount: limit });
  };

  return (
    <div className="lio-card mt-6 p-6">
      <h2 className="text-xl font-semibold tracking-tight text-ink">Auto-approval</h2>
      <p className="mt-1 text-sm text-ink/55">
        Small requests skip the buyer: they are approved as soon as they are created.
      </p>

      <div className="mt-4 space-y-3 rounded-xl border border-line p-4">
        <label className="flex cursor-pointer items-center gap-3 text-sm text-ink">
          <input
            type="checkbox"
            checked={enabled}
            disabled={busy}
            onChange={(e) => setEnabled(e.target.checked)}
            className="h-4 w-4 accent-accent-deep"
          />
          Approve requests automatically when the total is under
        </label>
        <div className="flex items-center gap-2 pl-7">
          <div className="relative w-40">
            <span className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-sm text-ink/40">
              $
            </span>
            <Input
              aria-label="Auto-approval limit"
              type="number"
              min="0"
              step="0.01"
              value={amount}
              disabled={busy || !enabled}
              onChange={(e) => setAmount(e.target.value)}
              className="pl-7"
            />
          </div>
          <span className="text-xs text-ink/45">incl. tax, shipping and fees</span>
        </div>
      </div>

      <p
        className={`mt-3 rounded-lg px-3 py-2 text-sm ${
          enabled ? 'bg-green-50 text-green-800' : 'border border-line bg-white text-ink/60'
        }`}
      >
        {enabled && limit > 0
          ? `Requests under ${money(limit)} are approved without a buyer. Editing the vendor, tax ID, lines or tax sends a request back for approval.`
          : 'Every request needs a buyer’s approval.'}
      </p>

      {formError && <p className="mt-2 text-sm text-red-600">{formError}</p>}
      <div className="mt-4 flex justify-end">
        <Button size="sm" onClick={save} loading={busy} disabled={!dirty}>
          Save
        </Button>
      </div>
    </div>
  );
}

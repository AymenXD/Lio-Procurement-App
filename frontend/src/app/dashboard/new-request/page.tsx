'use client';

import { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useMutation } from '@tanstack/react-query';
import * as api from '@/lib/api';
import { Button, Input, Alert, Loader } from '@/components/base';
import { CatalogSuggestions } from '@/components/CatalogSuggestions';
import { CommodityGroupPicker } from '@/components/CommodityGroupPicker';

const MAX_PDF_BYTES = 10 * 1024 * 1024; // same limit as the backend

const round2 = (n: number) => Math.round(n * 100) / 100;
// Same formula as the server, which ignores totals sent by the browser.
const lineTotal = (l: { unitPrice: number; amount: number }) => round2(l.unitPrice * l.amount);
const usd = (n: number) => `$${n.toLocaleString('en-US')}`;
const NOT_FOUND = 'Not found or unclear on the quote. Please fill in or check.';

interface OrderLine {
  positionDescription: string;
  unitPrice: number;
  amount: number;
  unit: string;
  totalPrice: number;
  articleId?: string | null; // set when the line uses a catalog article (negotiated price)
  quotedUnitPrice?: number | null; // the original quote's price it replaced
}

export default function NewRequestPage() {
  const router = useRouter();

  // Form state
  const [requestorName, setRequestorName] = useState('');
  const [title, setTitle] = useState('');
  const [vendorName, setVendorName] = useState('');
  const [vatId, setVatId] = useState('');
  const [department, setDepartment] = useState('');
  const [profileDepartment, setProfileDepartment] = useState('');

  // The requestor is the logged-in user: their name and department aren't on the quote.
  useEffect(() => {
    api.auth
      .me()
      .then(({ profile }) => {
        setRequestorName((name) => name || profile.full_name || '');
        setProfileDepartment(profile.department || '');
        setDepartment((dept) => dept || profile.department || '');
      })
      .catch(() => {}); // not critical: the fields stay editable
  }, []);
  const [commodityGroupId, setCommodityGroupId] = useState<number | null>(null);
  const [orderLines, setOrderLines] = useState<OrderLine[]>([]);
  const [taxAmount, setTaxAmount] = useState<number>(0);
  const subtotal = round2(orderLines.reduce((sum, l) => sum + lineTotal(l), 0));
  const totalCost = round2(subtotal + taxAmount);

  // The org's auto-approval policy, to tell the requester before submitting.
  const [autoApproval, setAutoApproval] = useState<api.AutoApprovalPolicy | null>(null);
  useEffect(() => {
    api.organizations
      .getSettings()
      .then((s) => setAutoApproval(s.auto_approval ?? null))
      .catch(() => {}); // only a hint; the server decides
  }, []);

  // UI state
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [warning, setWarning] = useState('');
  const [extracting, setExtracting] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  // Fields the extraction flagged; each highlight clears once the user edits that field.
  const [missing, setMissing] = useState<string[]>([]);
  const flag = (field: string) => (missing.includes(field) ? NOT_FOUND : undefined);
  const unflag = (field: string) => setMissing((m) => m.filter((f) => f !== field));

  // Catalog suggestions: one list per order line, same order as orderLines.
  const [suggestions, setSuggestions] = useState<api.ArticleSuggestion[][]>([]);
  const [checkingCatalog, setCheckingCatalog] = useState(false);

  const loadSuggestions = async (
    lines: { positionDescription: string; unitPrice: number }[],
    groupId: number | null
  ) => {
    if (lines.length === 0) {
      setSuggestions([]);
      return;
    }
    setCheckingCatalog(true);
    try {
      const result = await api.articles.suggest(
        lines.map((l) => ({ description: l.positionDescription, unit_price: l.unitPrice || null })),
        groupId
      );
      setSuggestions(result.lines);
    } catch {
      setSuggestions([]); // suggestions are optional; the form works without them
    } finally {
      setCheckingCatalog(false);
    }
  };

  // The negotiated price belongs to another supplier, so it goes into a separate request.
  const startRequestWith = (s: api.ArticleSuggestion, line: OrderLine) => {
    const q = new URLSearchParams({
      vendor: s.supplier_name ?? '',
      description: s.description,
      unitPrice: s.unit_price,
      unit: s.unit,
      amount: String(line.amount || 1),
      articleId: s.article_id,
    });
    if (line.unitPrice > 0) q.set('quotedUnitPrice', String(line.unitPrice));
    if (commodityGroupId) q.set('commodityGroupId', String(commodityGroupId));
    window.open(`/dashboard/new-request?${q.toString()}`, '_blank');
  };

  // Prefill from "Start request with this article" (URL parameters), once on open.
  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    const description = q.get('description');
    if (!description) return;
    const unitPrice = Number(q.get('unitPrice')) || 0;
    const amount = Number(q.get('amount')) || 1;
    setVendorName(q.get('vendor') ?? '');
    setTitle(description);
    const quoted = Number(q.get('quotedUnitPrice'));
    setOrderLines([
      { positionDescription: description, unitPrice, amount, unit: q.get('unit') ?? '',
        totalPrice: unitPrice * amount, articleId: q.get('articleId'),
        quotedUnitPrice: quoted > 0 ? quoted : null },
    ]);
    const groupId = Number(q.get('commodityGroupId'));
    if (groupId) setCommodityGroupId(groupId);
    setSuccess('Prefilled from the catalog with the negotiated price. Review and submit.');
  }, []);

  // Booking rules: ask the server which rule (if any) applies to the current lines.
  // A matching rule fixes and locks the commodity group (the server enforces it on save too).
  const [appliedRule, setAppliedRule] = useState<api.AppliedBookingRule | null>(null);
  const groupRef = useRef(commodityGroupId);
  groupRef.current = commodityGroupId;
  const linesKey = orderLines.map((l) => `${l.positionDescription}|${lineTotal(l)}`).join('\n');

  useEffect(() => {
    if (orderLines.length === 0) {
      setAppliedRule(null);
      return;
    }
    const timer = setTimeout(async () => {
      try {
        const { rule } = await api.requests.bookingRulePreview(
          orderLines.map((l) => ({ description: l.positionDescription, total_price: lineTotal(l) }))
        );
        setAppliedRule(rule);
        if (rule) {
          unflag('Commodity Group');
          if (groupRef.current !== rule.commodity_group_id) {
            setCommodityGroupId(rule.commodity_group_id);
            void loadSuggestions(orderLines, rule.commodity_group_id); // filter uses the group
          }
        }
      } catch {
        // Preview is optional: the server applies the rule on save anyway.
      }
    }, 600);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [linesKey]);

  // PDF parsing mutation
  const parsePDFMutation = useMutation({
    mutationFn: async (file: File) => {
      const result = await api.pdf.parse(file);
      if (!result.text) {
        throw new Error('Failed to parse PDF');
      }
      return result.text;
    },
  });

  // Handle file upload and extraction
  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const uploadedFile = e.target.files?.[0];
    // Reset the input so re-selecting the same file (e.g. after an error) triggers again.
    e.target.value = '';
    if (!uploadedFile) return;

    if (uploadedFile.type !== 'application/pdf') {
      setError('Please upload a PDF file');
      return;
    }

    if (uploadedFile.size > MAX_PDF_BYTES) {
      setError('This PDF is larger than 10 MB. Please upload a smaller file.');
      return;
    }

    setFile(null);
    setMissing([]);
    setError('');
    setSuccess('');
    setWarning('');
    setExtracting(true);

    try {
      // Step 1: Parse PDF
      const pdfText = await parsePDFMutation.mutateAsync(uploadedFile);
      // Valid PDF: keep it for attaching, even if the AI step below fails.
      setFile(uploadedFile);

      // Step 2: Extract structured data AND classify commodity group in one AI call
      const extractionResult = await api.extraction.extract(pdfText);
      
      if (!extractionResult.success || !extractionResult.data) {
        throw new Error(extractionResult.error || 'Failed to extract data');
      }

      const extracted = extractionResult.data;

      // Step 3: Auto-fill form (including commodity group from extraction)
      setTitle(extracted.title || '');
      setVendorName(extracted.vendorName || '');
      setVatId(extracted.vatId || '');
      // Department: the user's own first, then the one printed on the quote.
      const dept = profileDepartment || extracted.department || '';
      setDepartment(dept);
      setOrderLines(extracted.orderLines || []);
      setTaxAmount(extracted.taxAmount || 0);
      
      // Set commodity group (now included in extraction)
      if (extracted.commodityGroupId) {
        setCommodityGroupId(extracted.commodityGroupId);
      }

      // Look up negotiated catalog prices for the extracted lines (in the background).
      void loadSuggestions(extracted.orderLines || [], extracted.commodityGroupId ?? null);

      // Department isn't missing if the profile filled it.
      const missingFields = (extractionResult.missingFields ?? []).filter(
        (f) => !(f === 'Department' && dept)
      );
      setMissing(missingFields);

      // Show warnings for missing fields and for numbers that don't add up
      const notes: string[] = [];
      if (missingFields.length > 0) {
        notes.push(
          `⚠️ Could not extract: ${missingFields.join(', ')}. Please fill in these fields manually.`
        );
      }
      for (const note of extractionResult.warnings ?? []) {
        notes.push(`⚠️ Please check: ${note}.`);
      }
      if (notes.length > 0) {
        setWarning(notes.join('\n'));
      }

      setSuccess('✓ PDF extracted successfully! Review and submit.');
      window.scrollTo({ top: 0, behavior: 'smooth' });
    } catch (err) {
      console.error('Extraction error:', err);
      setError(err instanceof Error ? err.message : 'Failed to extract data from PDF');
      window.scrollTo({ top: 0, behavior: 'smooth' });
    } finally {
      setExtracting(false);
    }
  };

  // Add order line manually
  const addOrderLine = () => {
    setSuggestions([]); // positions change; "Check catalog prices" reloads them
    setOrderLines([
      ...orderLines,
      {
        positionDescription: '',
        unitPrice: 0,
        amount: 1,
        unit: '',
        totalPrice: 0,
      },
    ]);
  };

  // Update order line
  const updateOrderLine = (index: number, field: keyof OrderLine, value: string | number) => {
    const updated = [...orderLines];
    updated[index] = { ...updated[index], [field]: value };
    
    // Auto-calculate total price
    if (field === 'unitPrice' || field === 'amount') {
      updated[index].totalPrice = updated[index].unitPrice * updated[index].amount;
    }
    
    setOrderLines(updated);
  };

  // Remove order line
  const removeOrderLine = (index: number) => {
    setSuggestions([]); // positions change; "Check catalog prices" reloads them
    setOrderLines(orderLines.filter((_, i) => i !== index));
  };

  // Submit form
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setSuccess('');
    setWarning('');

    // Validation with scroll to top on error
    if (!commodityGroupId) {
      setError('Please select a commodity group');
      window.scrollTo({ top: 0, behavior: 'smooth' });
      return;
    }

    if (orderLines.length === 0) {
      setError('Please add at least one order line');
      window.scrollTo({ top: 0, behavior: 'smooth' });
      return;
    }

    setSubmitting(true); // blocks double-clicks from creating duplicate requests
    try {
      const created = await api.requests.create({
        requestorName,
        titleShortDescription: title,
        vendorName,
        vatId,
        commodityGroupId: commodityGroupId,
        totalCost,
        taxAmount,
        department,
        orderLines: orderLines.map((l) => ({ ...l, totalPrice: lineTotal(l) })),
      });

      // Attach the original PDF (if one was uploaded) so it shows on the detail page.
      if (file) {
        try {
          await api.requests.uploadDocument(created.id, file);
        } catch {
          // Non-fatal — the request itself was created.
        }
      }

      setSuccess('Request created successfully! Redirecting...');
      window.scrollTo({ top: 0, behavior: 'smooth' });
      setTimeout(() => {
        router.push('/dashboard/requests');
        router.refresh();
      }, 1500);
    } catch (err) {
      setSubmitting(false); // on success it stays disabled until the redirect
      setError(err instanceof Error ? err.message : 'Failed to create request');
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }
  };

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-semibold tracking-tight text-ink">New Procurement Request</h1>
        <p className="text-gray-600 mt-2">
          Upload a vendor offer PDF or fill in the details manually
        </p>
      </div>

      {error && <Alert variant="error" className="mb-6">{error}</Alert>}
      {warning && <Alert variant="warning" className="mb-6 whitespace-pre-line">{warning}</Alert>}
      {success && <Alert variant="success" className="mb-6">{success}</Alert>}

      <form onSubmit={handleSubmit} className="space-y-8">
        {/* PDF Upload Section */}
        <div className="lio-card p-6">
          <h2 className="text-xl font-semibold tracking-tight text-ink mb-4">Upload Vendor Offer (Optional)</h2>
          <p className="text-sm text-gray-600 mb-4">
            Upload a PDF to automatically extract vendor details and order items
          </p>

          <div className="border-2 border-dashed border-gray-300 rounded-lg p-8 text-center hover:border-accent-deep/50 transition-colors">
            <input
              type="file"
              accept="application/pdf"
              onChange={handleFileChange}
              className="hidden"
              id="pdf-upload"
              disabled={extracting}
            />
            <label htmlFor="pdf-upload" className="cursor-pointer">
              {extracting ? (
                <div className="flex flex-col items-center">
                  <Loader size="lg" />
                  <p className="mt-4 text-sm text-gray-600">Extracting data from PDF...</p>
                </div>
              ) : file ? (
                <div>
                  <svg
                    className="mx-auto h-12 w-12 text-green-500"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M5 13l4 4L19 7"
                    />
                  </svg>
                  <p className="mt-2 text-sm font-medium text-gray-900">{file.name}</p>
                  <p className="mt-1 text-xs text-gray-500">Click to upload a different file</p>
                </div>
              ) : (
                <div>
                  <svg
                    className="mx-auto h-12 w-12 text-gray-400"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
                    />
                  </svg>
                  <p className="mt-2 text-sm text-gray-600">
                    Click to upload or drag and drop
                  </p>
                  <p className="mt-1 text-xs text-gray-500">PDF up to 10MB</p>
                </div>
              )}
            </label>
          </div>
        </div>

        {/* Request Details */}
        <div className="lio-card p-6 space-y-4">
          <h2 className="text-xl font-semibold tracking-tight text-ink mb-4">Request Details</h2>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Input
              label="Requestor Name *"
              value={requestorName}
              onChange={(e) => setRequestorName(e.target.value)}
              required
              placeholder="John Doe"
            />

            <Input
              label="Department"
              value={department}
              onChange={(e) => { setDepartment(e.target.value); unflag('Department'); }}
              error={flag('Department')}
              placeholder="IT Department"
            />
          </div>

          <Input
            label="Title / Short Description *"
            value={title}
            onChange={(e) => { setTitle(e.target.value); unflag('Title/Short Description'); }}
            error={flag('Title/Short Description')}
            required
            placeholder="Adobe Creative Cloud Subscription"
          />
        </div>

        {/* Vendor Information */}
        <div className="lio-card p-6 space-y-4">
          <h2 className="text-xl font-semibold tracking-tight text-ink mb-4">Vendor Information</h2>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Input
              label="Vendor Name *"
              value={vendorName}
              onChange={(e) => { setVendorName(e.target.value); unflag('Vendor Name'); }}
              error={flag('Vendor Name')}
              required
              placeholder="Adobe Systems"
            />

            <Input
              label="Tax ID"
              value={vatId}
              onChange={(e) => { setVatId(e.target.value); unflag('Tax ID'); }}
              error={flag('Tax ID')}
              placeholder="12-3456789"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Commodity Group *
            </label>
            <CommodityGroupPicker
              value={commodityGroupId}
              onChange={(groupId) => {
                setCommodityGroupId(groupId);
                unflag('Commodity Group');
                // Suggestions are filtered by the group's category, so refresh them.
                if (orderLines.length > 0) void loadSuggestions(orderLines, groupId);
              }}
              disabled={appliedRule !== null} // a booking rule decides the group
              error={!!flag('Commodity Group')}
              required
            />
            {appliedRule && (
              <p className="mt-2 inline-flex items-center gap-1.5 rounded-full bg-accent-soft/30 px-3 py-1 text-xs font-medium text-accent-deep">
                🔒 Booked to {appliedRule.commodity_group_name} by the rule &ldquo;{appliedRule.label}&rdquo;
              </p>
            )}
          </div>
        </div>

        {/* Order Lines */}
        <div className="lio-card p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-xl font-semibold tracking-tight text-ink">Order Lines *</h2>
            <div className="flex gap-2">
              <Button
                type="button"
                onClick={() => loadSuggestions(orderLines, commodityGroupId)}
                variant="outline"
                size="sm"
                loading={checkingCatalog}
                disabled={orderLines.length === 0}
              >
                Check catalog prices
              </Button>
              <Button type="button" onClick={addOrderLine} variant="outline" size="sm">
                + Add Line
              </Button>
            </div>
          </div>

          {orderLines.length === 0 ? (
            <div className="text-center py-8 text-gray-500">
              No order lines yet. Add one to get started.
            </div>
          ) : (
            <div className="space-y-4">
              {orderLines.map((line, index) => (
                <div key={index} className="border border-gray-200 rounded-lg p-4">
                  <div className="flex items-start justify-between mb-4">
                    <h3 className="text-sm font-medium text-gray-700">Line {index + 1}</h3>
                    <button
                      type="button"
                      onClick={() => removeOrderLine(index)}
                      className="text-red-600 hover:text-red-700 text-sm"
                    >
                      Remove
                    </button>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
                    <div className="lg:col-span-2">
                      <Input
                        label="Description"
                        value={line.positionDescription}
                        onChange={(e) =>
                          updateOrderLine(index, 'positionDescription', e.target.value)
                        }
                        required
                        placeholder="Item description"
                      />
                    </div>

                    <Input
                      label="Unit Price ($)"
                      type="number"
                      step="0.01"
                      value={line.unitPrice}
                      onChange={(e) =>
                        updateOrderLine(index, 'unitPrice', parseFloat(e.target.value) || 0)
                      }
                      required
                      readOnly={!!line.articleId} // the server applies the catalog price anyway
                      helperText={line.articleId ? 'Negotiated catalog price' : undefined}
                    />

                    <Input
                      label="Amount"
                      type="number"
                      step="0.01"
                      value={line.amount}
                      onChange={(e) =>
                        updateOrderLine(index, 'amount', parseFloat(e.target.value) || 1)
                      }
                      required
                    />

                    <Input
                      label="Unit"
                      value={line.unit}
                      onChange={(e) => updateOrderLine(index, 'unit', e.target.value)}
                      required
                      placeholder="pcs, licenses, etc."
                      readOnly={!!line.articleId}
                    />
                  </div>

                  <div className="mt-2 text-right">
                    <span className="text-sm text-gray-600">Total: </span>
                    <span className="text-lg font-semibold tracking-tight text-ink">
                      ${lineTotal(line).toFixed(2)}
                    </span>
                  </div>

                  <CatalogSuggestions
                    suggestions={suggestions[index] ?? []}
                    lineUnit={line.unit}
                    lineAmount={line.amount}
                    onStartRequest={(s) => startRequestWith(s, line)}
                  />
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Total Cost: lines + tax, computed (the server recomputes it the same way) */}
        <div className="bg-accent-soft/20 border-2 border-accent/40 rounded-lg p-6 space-y-3">
          <div className="flex items-center justify-between text-sm text-gray-700">
            <span>Order lines</span>
            <span className="font-medium">${subtotal.toFixed(2)}</span>
          </div>
          <div className="flex items-center justify-between gap-4 text-sm text-gray-700">
            <label htmlFor="tax-amount">Tax ($)</label>
            <div className="w-40">
              <Input
                id="tax-amount"
                type="number"
                step="0.01"
                min="0"
                value={taxAmount}
                onChange={(e) => setTaxAmount(Math.max(0, parseFloat(e.target.value) || 0))}
                className="text-right bg-white"
              />
            </div>
          </div>
          <div className="flex items-center justify-between border-t border-accent/30 pt-3">
            <span className="text-lg font-medium text-gray-900">Total Cost</span>
            <span className="text-3xl font-bold text-accent-deep">
              ${totalCost.toFixed(2)}
            </span>
          </div>
          {autoApproval?.enabled && orderLines.length > 0 && (
            <p
              className={`rounded-lg px-3 py-2 text-sm ${
                totalCost < autoApproval.below_amount
                  ? 'bg-green-50 text-green-800'
                  : 'border border-line bg-white text-gray-700'
              }`}
            >
              {totalCost < autoApproval.below_amount
                ? `✓ Under ${usd(autoApproval.below_amount)}: this request will be approved automatically.`
                : `Needs a buyer's approval: the total is ${usd(autoApproval.below_amount)} or more.`}
            </p>
          )}
        </div>

        {/* Submit */}
        <div className="flex items-center justify-end space-x-4">
          <Button
            type="button"
            variant="outline"
            onClick={() => router.back()}
          >
            Cancel
          </Button>
          <Button type="submit" size="lg" loading={submitting}>
            {submitting ? 'Creating…' : 'Create Request'}
          </Button>
        </div>
      </form>
    </div>
  );
}


"use client";

import React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckCircle2,
  Download,
  FileJson,
  Loader2,
  ScanSearch,
  Sigma,
  XCircle,
} from "lucide-react";
import { api } from "@/lib/api";
import type {
  EquationCandidate,
  EquationCategory,
  EquationEligibility,
  EquationInventory,
  EquationReportItem,
} from "@/lib/types";

const ELIGIBILITY_STYLE: Record<EquationEligibility, string> = {
  eligible: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
  already_mathtype: "bg-sky-500/15 text-sky-300 border-sky-500/30",
  needs_review: "bg-amber-500/15 text-amber-300 border-amber-500/30",
  pending: "bg-slate-500/15 text-slate-300 border-slate-500/30",
};

const ELIGIBILITY_LABEL: Record<EquationEligibility, string> = {
  eligible: "Eligible",
  already_mathtype: "Already MathType",
  needs_review: "Needs review",
  pending: "Pending",
};

const STATUS_STYLE: Record<EquationReportItem["status"], string> = {
  converted: "text-emerald-300",
  failed: "text-red-300",
  skipped: "text-sky-300",
  needs_review: "text-amber-300",
};

function CountTable({
  labels,
  before,
  after,
}: {
  labels: Record<string, string>;
  before: Partial<Record<EquationCategory, number>>;
  after?: Partial<Record<EquationCategory, number>>;
}) {
  const keys = Array.from(new Set([...Object.keys(before), ...Object.keys(after || {})])) as EquationCategory[];
  if (keys.length === 0) return <p className="text-sm text-slate-400">No equations detected.</p>;
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="text-left text-slate-400 border-b border-white/10">
          <th className="py-2 font-medium">Type</th>
          <th className="py-2 font-medium text-right">Before</th>
          {after && <th className="py-2 font-medium text-right">After</th>}
        </tr>
      </thead>
      <tbody>
        {keys.map((k) => (
          <tr key={k} className="border-b border-white/5">
            <td className="py-2 text-slate-200">{labels[k] || k}</td>
            <td className="py-2 text-right font-mono text-slate-200">{before[k] ?? 0}</td>
            {after && <td className="py-2 text-right font-mono text-slate-200">{after[k] ?? 0}</td>}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function EquationRow({ eq, labels }: { eq: EquationCandidate; labels: Record<string, string> }) {
  return (
    <div className="flex flex-col gap-1 py-3 border-b border-white/5 last:border-0">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-sm text-white break-all">{eq.text || eq.shape_name}</span>
        <span className={`text-[11px] px-2 py-0.5 rounded-full border ${ELIGIBILITY_STYLE[eq.eligibility]}`}>
          {ELIGIBILITY_LABEL[eq.eligibility]}
        </span>
      </div>
      <div className="text-xs text-slate-400">
        {labels[eq.category] || eq.category} · {eq.shape_name}
        {eq.group_path.length > 0 && ` · in group ${eq.group_path.join(" › ")}`}
        {eq.constructs.length > 0 && ` · ${eq.constructs.join(", ")}`}
      </div>
      <div className="text-xs text-slate-300">{eq.reason}</div>
    </div>
  );
}

export default function EquationsPanel({ presentationId }: { presentationId: string }) {
  const queryClient = useQueryClient();

  const { data: integration, isLoading: integrationLoading } = useQuery({
    queryKey: ["mathtype-integration"],
    queryFn: () => api.getMathTypeIntegration(),
  });

  const { data: state } = useQuery({
    queryKey: ["equations", presentationId],
    queryFn: () => api.getEquationState(presentationId),
    refetchInterval: (q) => {
      const s = q.state.data?.status;
      return s === "queued" || s === "running" ? 2000 : false;
    },
  });

  const scanMutation = useMutation({
    mutationFn: () => api.scanEquations(presentationId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["equations", presentationId] }),
  });

  const convertMutation = useMutation({
    mutationFn: () => api.convertEquations(presentationId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["equations", presentationId] }),
  });

  const inventory: EquationInventory | undefined = scanMutation.data || state?.scan;
  const report = state?.report;
  const busy = state?.status === "queued" || state?.status === "running";
  const eligibleCount = inventory?.by_eligibility.eligible ?? 0;
  const canConvert = !!integration?.available && !!inventory && eligibleCount > 0 && !busy;

  return (
    <div className="space-y-6">
      <div className="glass-panel rounded-2xl p-6 border border-white/10">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h2 className="text-2xl font-bold text-white flex items-center gap-2">
              <Sigma className="w-6 h-6 text-brand-300" />
              Equation to MathType
            </h2>
            <p className="text-xs text-slate-300 mt-1">
              Scans every slide for equations and replaces eligible native Office equations with editable MathType
              objects. The uploaded file is never modified; a new file is produced and validated before download.
            </p>
          </div>
          <div className="flex gap-2 shrink-0">
            <button
              onClick={() => scanMutation.mutate()}
              disabled={scanMutation.isPending || busy}
              className="px-4 py-2 rounded-xl bg-white/10 hover:bg-white/15 text-white text-sm font-semibold flex items-center gap-2 disabled:opacity-50"
            >
              {scanMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <ScanSearch className="w-4 h-4" />}
              Scan Equations
            </button>
            <button
              onClick={() => convertMutation.mutate()}
              disabled={!canConvert || convertMutation.isPending}
              title={!integration?.available ? "MathType integration is not available" : undefined}
              className="px-4 py-2 rounded-xl bg-brand-500 hover:bg-brand-400 text-white text-sm font-semibold flex items-center gap-2 disabled:opacity-50"
            >
              {busy || convertMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sigma className="w-4 h-4" />}
              Convert to MathType
            </button>
          </div>
        </div>
      </div>

      {!integrationLoading && integration && !integration.available && (
        <div className="rounded-2xl p-5 border border-amber-500/40 bg-amber-500/10" role="alert">
          <div className="flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 text-amber-300 shrink-0 mt-0.5" />
            <div className="text-sm text-amber-100 space-y-2">
              <p className="font-semibold">MathType is not available on this server, so equations can be scanned but not converted.</p>
              <p className="text-amber-200/80">{integration.details}</p>
              <ul className="list-disc ml-5 space-y-1 text-amber-200/90">
                {integration.guidance.map((g) => (
                  <li key={g}>{g}</li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      )}
      {integration?.available && (
        <div className="rounded-2xl p-4 border border-emerald-500/30 bg-emerald-500/5 text-sm text-emerald-200 flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4" />
          MathType {integration.mathtype_version} available via {integration.conversion_method || integration.adapter}.
        </div>
      )}

      {(scanMutation.error || convertMutation.error || state?.error) && (
        <div className="rounded-2xl p-4 border border-red-500/40 bg-red-500/10 text-sm text-red-200 flex items-start gap-2" role="alert">
          <XCircle className="w-4 h-4 shrink-0 mt-0.5" />
          <span>{(scanMutation.error as Error)?.message || (convertMutation.error as Error)?.message || state?.error}</span>
        </div>
      )}

      {busy && (
        <div className="glass-panel rounded-2xl p-5 border border-white/10">
          <div className="flex justify-between text-sm text-slate-300 mb-2">
            <span>{state?.current_step || "Working..."}</span>
            <span className="font-mono">{state?.progress ?? 0}%</span>
          </div>
          <div className="h-2 rounded-full bg-white/10 overflow-hidden">
            <div className="h-full bg-brand-400 transition-all" style={{ width: `${state?.progress ?? 0}%` }} />
          </div>
        </div>
      )}

      {report && (
        <div className="glass-panel rounded-2xl p-6 border border-white/10 space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <h3 className="text-lg font-semibold text-white">Conversion report</h3>
            <div className="flex gap-2">
              {state?.converted_available && (
                <button
                  onClick={() => api.downloadConvertedEquations(presentationId)}
                  className="px-4 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-white text-sm font-semibold flex items-center gap-2"
                >
                  <Download className="w-4 h-4" /> Download converted PPTX
                </button>
              )}
              <button
                onClick={() => api.downloadEquationReport(presentationId)}
                className="px-4 py-2 rounded-xl bg-white/10 hover:bg-white/15 text-white text-sm font-semibold flex items-center gap-2"
              >
                <FileJson className="w-4 h-4" /> Report (JSON)
              </button>
            </div>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-center">
            {(["converted", "skipped", "needs_review", "failed"] as const).map((k) => (
              <div key={k} className="rounded-xl bg-white/5 p-3">
                <div className={`text-2xl font-bold ${STATUS_STYLE[k]}`}>{report.summary[k]}</div>
                <div className="text-xs text-slate-400 capitalize">{k.replace("_", " ")}</div>
              </div>
            ))}
          </div>
          <CountTable labels={inventory?.category_labels || {}} before={report.summary.before} after={report.summary.after} />
          <div>
            <h4 className="text-sm font-semibold text-white mb-2">
              Validation {report.validation.passed ? "passed" : "failed"}
            </h4>
            <ul className="space-y-1 text-xs">
              {report.validation.checks.map((c) => (
                <li key={c.name} className="flex items-start gap-2">
                  {c.passed ? (
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0 mt-0.5" />
                  ) : (
                    <XCircle className="w-3.5 h-3.5 text-red-400 shrink-0 mt-0.5" />
                  )}
                  <span className="text-slate-300">
                    {c.name.replace(/_/g, " ")}
                    {c.detail && <span className="text-slate-500"> — {c.detail}</span>}
                  </span>
                </li>
              ))}
            </ul>
          </div>
          <div className="divide-y divide-white/5">
            {report.items.map((i) => (
              <div key={i.id} className="py-2 text-sm flex flex-col sm:flex-row sm:gap-3">
                <span className="text-slate-400 w-16 shrink-0">Slide {i.slide_number}</span>
                <span className="font-mono text-white break-all sm:w-64 shrink-0">{i.text || i.shape_name}</span>
                <span className={`w-28 shrink-0 font-semibold ${STATUS_STYLE[i.status]}`}>{i.status.replace("_", " ")}</span>
                <span className="text-slate-300 text-xs">{i.reason}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {inventory && (
        <div className="grid lg:grid-cols-3 gap-6">
          <div className="glass-panel rounded-2xl p-6 border border-white/10">
            <h3 className="text-lg font-semibold text-white mb-1">Inventory</h3>
            <p className="text-xs text-slate-400 mb-3">
              {inventory.total} candidate(s) on {inventory.slides.length} of {inventory.slide_count} slides ·{" "}
              {eligibleCount} eligible for conversion
            </p>
            <CountTable labels={inventory.category_labels} before={inventory.by_category} />
          </div>
          <div className="glass-panel rounded-2xl p-6 border border-white/10 lg:col-span-2 max-h-[640px] overflow-y-auto">
            <h3 className="text-lg font-semibold text-white mb-3">Slide-by-slide</h3>
            {inventory.slides.length === 0 && <p className="text-sm text-slate-400">No equations found.</p>}
            {inventory.slides.map((s) => (
              <div key={s.slide_number} className="mb-4">
                <div className="text-xs uppercase tracking-widest text-slate-500 font-mono mb-1">Slide {s.slide_number}</div>
                {s.equations.map((eq) => (
                  <EquationRow key={eq.id} eq={eq} labels={inventory.category_labels} />
                ))}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

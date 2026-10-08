"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import UploadModal from "@/components/UploadModal";
import {
  FileSpreadsheet,
  CheckCircle2,
  AlertTriangle,
  HelpCircle,
  FileCheck,
  Plus,
  ArrowRight,
  ShieldCheck,
  Search,
  Sparkles,
  Layers,
  Clock,
  Download,
} from "lucide-react";
import { formatBytes, formatDate, getScoreColor, formatScore } from "@/lib/utils";

export default function DashboardPage() {
  const [isUploadOpen, setIsUploadOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");

  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ["dashboardStats"],
    queryFn: () => api.getDashboardStats(),
  });

  const { data: presData, isLoading: presLoading } = useQuery({
    queryKey: ["presentations"],
    queryFn: () => api.getPresentations(),
  });

  const presentations = presData?.presentations || stats?.recent_presentations || [];
  const filteredPresentations = presentations.filter((p) =>
    p.filename.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-10">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-8 border-b border-white/10">
        <div>
          <h1 className="text-3xl font-extrabold text-white tracking-tight flex items-center gap-3">
            <ShieldCheck className="w-8 h-8 text-brand-400" />
            Presentation Accessibility Dashboard
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            Monitor WCAG 2.1 AA compliance across your enterprise decks and apply non-destructive fixes.
          </p>
        </div>

        <button
          onClick={() => setIsUploadOpen(true)}
          className="px-5 py-2.5 rounded-xl bg-gradient-to-r from-brand-600 via-indigo-600 to-cyan-600 hover:from-brand-500 hover:to-cyan-500 text-white font-semibold text-sm shadow-lg shadow-brand-500/25 transition-all flex items-center justify-center gap-2"
        >
          <Plus className="w-4 h-4" />
          <span>Upload Presentation</span>
        </button>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 my-8">
        {/* Card 1: Presentations */}
        <div className="glass-card rounded-2xl p-5 border border-white/10 flex items-center justify-between">
          <div>
            <p className="text-xs font-medium text-slate-400">Total Presentations</p>
            <p className="text-3xl font-extrabold text-white mt-1">
              {stats?.total_presentations ?? "—"}
            </p>
            <p className="text-[11px] text-slate-500 mt-1">All processed decks</p>
          </div>
          <div className="w-12 h-12 rounded-xl bg-brand-500/10 border border-brand-500/20 flex items-center justify-center text-brand-400">
            <FileSpreadsheet className="w-6 h-6" />
          </div>
        </div>

        {/* Card 2: Slides */}
        <div className="glass-card rounded-2xl p-5 border border-white/10 flex items-center justify-between">
          <div>
            <p className="text-xs font-medium text-slate-400">Slides Analyzed</p>
            <p className="text-3xl font-extrabold text-white mt-1">
              {stats?.total_slides_analyzed ?? "—"}
            </p>
            <p className="text-[11px] text-slate-500 mt-1">Full XML trees parsed</p>
          </div>
          <div className="w-12 h-12 rounded-xl bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center text-cyan-400">
            <Layers className="w-6 h-6" />
          </div>
        </div>

        {/* Card 3: Avg Score */}
        <div className="glass-card rounded-2xl p-5 border border-white/10 flex items-center justify-between">
          <div>
            <p className="text-xs font-medium text-slate-400">Mean Health Score</p>
            <p className="text-3xl font-extrabold text-emerald-400 mt-1">
              {stats?.avg_accessibility_score ? `${Math.round(stats.avg_accessibility_score)}%` : "—"}
            </p>
            <p className="text-[11px] text-emerald-400/70 mt-1">WCAG 2.1 AA compliant</p>
          </div>
          <div className="w-12 h-12 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400">
            <CheckCircle2 className="w-6 h-6" />
          </div>
        </div>

        {/* Card 4: Open Issues */}
        <div className="glass-card rounded-2xl p-5 border border-white/10 flex items-center justify-between">
          <div>
            <p className="text-xs font-medium text-slate-400">Critical Violations</p>
            <p className="text-3xl font-extrabold text-rose-400 mt-1">
              {stats?.issues_by_severity?.error ?? 0}
            </p>
            <p className="text-[11px] text-rose-400/70 mt-1">
              {stats?.issues_by_severity?.warning ?? 0} warnings queued
            </p>
          </div>
          <div className="w-12 h-12 rounded-xl bg-rose-500/10 border border-rose-500/20 flex items-center justify-center text-rose-400">
            <AlertTriangle className="w-6 h-6" />
          </div>
        </div>
      </div>

      {/* Presentations Section */}
      <div className="mt-10">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
          <div>
            <h2 className="text-xl font-bold text-white flex items-center gap-2">
              <FileCheck className="w-5 h-5 text-brand-400" />
              Audited Presentations
            </h2>
            <p className="text-xs text-slate-400 mt-0.5">
              Select any presentation to view slide-by-slide issues, AI suggestions, and remediation proofs.
            </p>
          </div>

          {/* Search box */}
          <div className="relative w-full sm:w-72">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search presentations..."
              className="w-full pl-9 pr-4 py-2 bg-slate-900 border border-white/10 rounded-xl text-sm text-white placeholder-slate-500 focus:border-brand-400 focus:ring-1 focus:ring-brand-400 transition-colors"
            />
          </div>
        </div>

        {/* Presentation Cards List */}
        {filteredPresentations.length === 0 ? (
          <div className="glass-panel rounded-2xl p-12 text-center border border-white/10">
            <FileSpreadsheet className="w-12 h-12 text-slate-500 mx-auto mb-3" />
            <h3 className="text-lg font-bold text-white">No presentations found</h3>
            <p className="text-xs text-slate-400 mt-1 max-w-sm mx-auto">
              Upload a .pptx presentation to initiate automated accessibility auditing and safe remediation.
            </p>
            <button
              onClick={() => setIsUploadOpen(true)}
              className="mt-6 px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-white font-semibold text-xs transition-colors inline-flex items-center gap-2"
            >
              <Plus className="w-4 h-4" />
              <span>Upload Presentation</span>
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4">
            {filteredPresentations.map((pres) => {
              const scoreColors = getScoreColor(pres.accessibility_score);

              return (
                <div
                  key={pres.id}
                  className="glass-card rounded-2xl p-5 border border-white/10 hover:border-brand-500/40 transition-all flex flex-col md:flex-row md:items-center justify-between gap-4 group"
                >
                  {/* Left: Presentation Info */}
                  <div className="flex items-start space-x-4 overflow-hidden">
                    <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-rose-500/20 to-orange-500/20 border border-rose-500/30 flex items-center justify-center text-rose-400 shrink-0">
                      <FileSpreadsheet className="w-6 h-6" />
                    </div>

                    <div className="overflow-hidden">
                      <div className="flex items-center gap-2">
                        <Link
                          href={`/presentations/${pres.id}`}
                          className="text-base font-bold text-white hover:text-brand-300 transition-colors truncate"
                        >
                          {pres.filename}
                        </Link>
                        <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                          {pres.status}
                        </span>
                      </div>

                      <div className="flex flex-wrap items-center gap-4 text-xs text-slate-400 mt-2">
                        <span>{pres.slide_count ?? 0} slides</span>
                        <span>&bull;</span>
                        <span>{formatBytes(pres.file_size)}</span>
                        <span>&bull;</span>
                        <span className="flex items-center gap-1">
                          <Clock className="w-3.5 h-3.5 text-slate-500" />
                          {formatDate(pres.created_at)}
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Middle: Score & Issue Badges */}
                  <div className="flex items-center gap-6">
                    {/* Score */}
                    <div className="text-right">
                      <span className="text-[11px] uppercase tracking-wider text-slate-400 font-semibold block">
                        Accessibility Score
                      </span>
                      <span className={`text-2xl font-black ${scoreColors.text}`}>
                        {formatScore(pres.accessibility_score)}
                      </span>
                    </div>

                    {/* Violations Count */}
                    <div className="flex items-center gap-2">
                      <span className="px-2.5 py-1 rounded-lg text-xs font-bold bg-rose-500/15 text-rose-300 border border-rose-500/30">
                        {pres.error_count} Errors
                      </span>
                      <span className="px-2.5 py-1 rounded-lg text-xs font-bold bg-amber-500/15 text-amber-300 border border-amber-500/30">
                        {pres.warning_count} Warnings
                      </span>
                    </div>

                    {/* View Button */}
                    <Link
                      href={`/presentations/${pres.id}`}
                      className="px-4 py-2 rounded-xl bg-white/5 hover:bg-brand-500/20 text-slate-200 hover:text-white border border-white/10 hover:border-brand-500/40 font-semibold text-xs transition-all flex items-center gap-1.5"
                    >
                      <span>Open Workspace</span>
                      <ArrowRight className="w-3.5 h-3.5 text-brand-400 group-hover:translate-x-1 transition-transform" />
                    </Link>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      <UploadModal isOpen={isUploadOpen} onClose={() => setIsUploadOpen(false)} />
    </div>
  );
}

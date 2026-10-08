"use client";

import React, { useState } from "react";
import Link from "next/link";
import UploadModal from "@/components/UploadModal";
import {
  ShieldCheck,
  Sparkles,
  FileCheck,
  Eye,
  Sliders,
  Layers,
  ArrowRight,
  CheckCircle2,
  FileSpreadsheet,
  AlertTriangle,
  Lock,
  ChevronRight,
  Zap,
  Globe2,
} from "lucide-react";

export default function HomePage() {
  const [isUploadOpen, setIsUploadOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<"before" | "after">("after");

  return (
    <div className="flex flex-col items-center">
      {/* ─── Hero Section ─────────────────────────────── */}
      <section className="relative w-full max-w-7xl mx-auto pt-20 pb-28 px-4 sm:px-6 lg:px-8 text-center">
        {/* Badge */}
        <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full text-xs font-semibold bg-brand-500/10 text-brand-300 border border-brand-500/20 mb-8 backdrop-blur-sm shadow-sm animate-pulse-slow">
          <Sparkles className="w-3.5 h-3.5 text-brand-400" />
          <span>Next-Generation Accessibility Intelligence for PowerPoint</span>
        </div>

        {/* Main Headline */}
        <h1 className="text-4xl sm:text-6xl lg:text-7xl font-extrabold tracking-tight text-white max-w-5xl mx-auto leading-[1.1]">
          Make PowerPoint accessible — <br />
          <span className="bg-gradient-to-r from-brand-400 via-indigo-300 to-cyan-400 bg-clip-text text-transparent">
            without changing your presentation.
          </span>
        </h1>

        {/* Subhead */}
        <p className="mt-6 text-lg sm:text-xl text-slate-300 max-w-3xl mx-auto leading-relaxed">
          AccessPPT analyzes your <code className="text-brand-300 font-mono text-sm px-1.5 py-0.5 bg-brand-500/10 rounded">.pptx</code> slides, detects WCAG 2.1 AA violations, generates AI-powered alt text, and performs safe remediation with a{" "}
          <strong className="text-white font-semibold">100% verified zero visual change guarantee</strong>.
        </p>

        {/* CTA Buttons */}
        <div className="mt-10 flex flex-col sm:flex-row items-center justify-center gap-4">
          <button
            onClick={() => setIsUploadOpen(true)}
            className="w-full sm:w-auto px-8 py-4 rounded-xl bg-gradient-to-r from-brand-600 via-indigo-600 to-cyan-600 hover:from-brand-500 hover:to-cyan-500 text-white font-bold text-base shadow-xl shadow-brand-500/25 hover:shadow-brand-500/40 transition-all transform hover:-translate-y-0.5 active:translate-y-0 flex items-center justify-center gap-2.5"
          >
            <Sparkles className="w-5 h-5" />
            <span>Audit Your Presentation Free</span>
            <ArrowRight className="w-4 h-4 ml-1" />
          </button>

          <Link
            href="/dashboard"
            className="w-full sm:w-auto px-7 py-4 rounded-xl glass-card hover:bg-white/10 text-slate-200 hover:text-white font-semibold text-base transition-all flex items-center justify-center gap-2 border border-white/10 hover:border-brand-500/40"
          >
            <Eye className="w-5 h-5 text-cyan-400" />
            <span>Open Dashboard</span>
          </Link>
        </div>

        {/* Guarantee Banner */}
        <div className="mt-12 max-w-2xl mx-auto p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-300 text-xs sm:text-sm flex items-center justify-center gap-2 font-medium">
          <ShieldCheck className="w-4 h-4 text-emerald-400 shrink-0" />
          <span>
            Non-Destructive Promise: Slide geometry, fonts, layouts, animations, and branding remain completely untouched.
          </span>
        </div>
      </section>

      {/* ─── Interactive Comparison Showcase ────────────── */}
      <section className="w-full max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 pb-28">
        <div className="glass-panel rounded-2xl p-6 sm:p-10 border border-white/10 shadow-2xl overflow-hidden relative">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-6 border-b border-white/10 gap-4">
            <div>
              <h2 className="text-2xl font-bold text-white flex items-center gap-2">
                <FileCheck className="w-6 h-6 text-brand-400" />
                Live Verification: Visual Integrity vs. Accessibility Layer
              </h2>
              <p className="text-sm text-slate-400 mt-1">
                Toggle between the raw visual presentation and the assistive screen-reader metadata layer.
              </p>
            </div>

            {/* Toggle */}
            <div className="inline-flex p-1 rounded-xl bg-slate-900 border border-white/10">
              <button
                onClick={() => setActiveTab("before")}
                className={`px-4 py-1.5 text-xs font-semibold rounded-lg transition-all ${
                  activeTab === "before"
                    ? "bg-rose-500/20 text-rose-300 border border-rose-500/30"
                    : "text-slate-400 hover:text-white"
                }`}
              >
                Inaccessible Original
              </button>
              <button
                onClick={() => setActiveTab("after")}
                className={`px-4 py-1.5 text-xs font-semibold rounded-lg transition-all ${
                  activeTab === "after"
                    ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                    : "text-slate-400 hover:text-white"
                }`}
              >
                AccessPPT Remediated
              </button>
            </div>
          </div>

          {/* Slide Mockup Window */}
          <div className="mt-8 rounded-xl bg-slate-900/90 border border-white/10 p-6 sm:p-8 aspect-[16/9] relative overflow-hidden flex flex-col justify-between">
            {/* Slide Header */}
            <div className="flex justify-between items-start">
              <div>
                <span className="text-xs uppercase font-mono tracking-widest text-brand-400 font-bold">
                  Slide 02 &bull; Enterprise Strategy
                </span>
                <h3 className="text-2xl sm:text-3xl font-bold text-white mt-1">
                  Global Cloud Architecture & Revenue Stream
                </h3>
              </div>
              <div className="px-3 py-1 rounded-full text-xs font-bold border border-white/10 bg-slate-800 text-slate-300">
                16:9 HD Canvas
              </div>
            </div>

            {/* Slide Graphic Simulation */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 my-auto">
              <div className="p-4 rounded-xl bg-slate-800/80 border border-white/5 relative">
                <span className="text-xs text-slate-400 font-medium">Q1 Growth</span>
                <p className="text-2xl font-black text-cyan-400 mt-1">+34.8%</p>
                <div className="h-2 w-full bg-slate-700 rounded-full mt-3 overflow-hidden">
                  <div className="h-full bg-cyan-400 w-3/4 rounded-full" />
                </div>
                {activeTab === "after" && (
                  <div className="mt-2 text-[10px] text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20 font-mono">
                    ✓ Alt: "Bar indicating 75% quarterly quota achievement"
                  </div>
                )}
              </div>

              <div className="p-4 rounded-xl bg-slate-800/80 border border-white/5 relative">
                <span className="text-xs text-slate-400 font-medium">Cloud Infrastructure</span>
                <p className="text-2xl font-black text-indigo-400 mt-1">99.99%</p>
                <div className="h-2 w-full bg-slate-700 rounded-full mt-3 overflow-hidden">
                  <div className="h-full bg-indigo-400 w-full rounded-full" />
                </div>
                {activeTab === "after" && (
                  <div className="mt-2 text-[10px] text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20 font-mono">
                    ✓ Tab Order: #2 (Follows Header)
                  </div>
                )}
              </div>

              <div className="p-4 rounded-xl bg-slate-800/80 border border-white/5 relative">
                <span className="text-xs text-slate-400 font-medium">Net Retention</span>
                <p className="text-2xl font-black text-emerald-400 mt-1">128%</p>
                <div className="h-2 w-full bg-slate-700 rounded-full mt-3 overflow-hidden">
                  <div className="h-full bg-emerald-400 w-4/5 rounded-full" />
                </div>
                {activeTab === "after" && (
                  <div className="mt-2 text-[10px] text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20 font-mono">
                    ✓ Contrast: 9.2:1 (Exceeds WCAG AAA)
                  </div>
                )}
              </div>
            </div>

            {/* Bottom Status bar */}
            <div className="flex flex-col sm:flex-row items-center justify-between pt-4 border-t border-white/10 text-xs text-slate-400 gap-2">
              <div className="flex items-center gap-2">
                <Lock className="w-3.5 h-3.5 text-slate-400" />
                <span>Pixel Geometry SHA-256 Hash: <code className="text-slate-300 font-mono">a8f9...32c1 (Unchanged)</code></span>
              </div>
              <div>
                {activeTab === "after" ? (
                  <span className="text-emerald-400 font-semibold flex items-center gap-1">
                    <CheckCircle2 className="w-3.5 h-3.5" /> 100% WCAG 2.1 AA Compliant &bull; Zero Visual Shift
                  </span>
                ) : (
                  <span className="text-rose-400 font-semibold flex items-center gap-1">
                    <AlertTriangle className="w-3.5 h-3.5" /> 3 Accessibility Violations Detected
                  </span>
                )}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ─── Core Features ───────────────────────────── */}
      <section id="features" className="w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-20 border-t border-white/10">
        <div className="text-center max-w-3xl mx-auto mb-16">
          <span className="text-xs uppercase font-mono tracking-widest text-brand-400 font-bold">
            Uncompromising Engineering
          </span>
          <h2 className="text-3xl sm:text-4xl font-extrabold text-white mt-2">
            Engineered for Accessibility Experts and Presentation Designers Alike
          </h2>
          <p className="text-slate-400 mt-4 text-base">
            No compromises between stunning presentations and 100% inclusive compliance.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
          {/* Card 1 */}
          <div className="glass-card rounded-2xl p-6 sm:p-8 flex flex-col justify-between">
            <div>
              <div className="w-12 h-12 rounded-xl bg-brand-500/10 border border-brand-500/20 flex items-center justify-center text-brand-400 mb-6">
                <Sparkles className="w-6 h-6" />
              </div>
              <h3 className="text-xl font-bold text-white">Gemini Multimodal AI Alt Text</h3>
              <p className="text-sm text-slate-400 mt-2 leading-relaxed">
                Understands the slide context to generate accurate, succinct descriptions for charts, diagrams, and complex graphics.
              </p>
            </div>
            <ul className="mt-6 space-y-2 text-xs text-slate-300">
              <li className="flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-400" /> Confidence scoring on every suggestion
              </li>
              <li className="flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-400" /> Automatic decorative detection
              </li>
            </ul>
          </div>

          {/* Card 2 */}
          <div className="glass-card rounded-2xl p-6 sm:p-8 flex flex-col justify-between">
            <div>
              <div className="w-12 h-12 rounded-xl bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center text-cyan-400 mb-6">
                <Sliders className="w-6 h-6" />
              </div>
              <h3 className="text-xl font-bold text-white">Color Contrast Inspector</h3>
              <p className="text-sm text-slate-400 mt-2 leading-relaxed">
                Calculates precise WCAG luminance ratios (4.5:1 for standard text, 3:1 for large text) across text, tables, and shapes.
              </p>
            </div>
            <ul className="mt-6 space-y-2 text-xs text-slate-300">
              <li className="flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-400" /> AA & AAA thresholds evaluated
              </li>
              <li className="flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-400" /> AI suggestions for contrast enhancement
              </li>
            </ul>
          </div>

          {/* Card 3 */}
          <div className="glass-card rounded-2xl p-6 sm:p-8 flex flex-col justify-between">
            <div>
              <div className="w-12 h-12 rounded-xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400 mb-6">
                <Layers className="w-6 h-6" />
              </div>
              <h3 className="text-xl font-bold text-white">Reading Order Visualizer</h3>
              <p className="text-sm text-slate-400 mt-2 leading-relaxed">
                Visualizes screen reader traversal sequence, catches inverted tab sequences, and permits reordering with one click.
              </p>
            </div>
            <ul className="mt-6 space-y-2 text-xs text-slate-300">
              <li className="flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-400" /> Interactive drag and up/down reorder
              </li>
              <li className="flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-400" /> Natural Left-to-Right layout alignment
              </li>
            </ul>
          </div>

          {/* Card 4 */}
          <div className="glass-card rounded-2xl p-6 sm:p-8 flex flex-col justify-between">
            <div>
              <div className="w-12 h-12 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400 mb-6">
                <Zap className="w-6 h-6" />
              </div>
              <h3 className="text-xl font-bold text-white">One-Click Safe Remediation</h3>
              <p className="text-sm text-slate-400 mt-2 leading-relaxed">
                Safely injects alt text, table header flags, slide titles, and presentation language directly into the PPTX package.
              </p>
            </div>
            <ul className="mt-6 space-y-2 text-xs text-slate-300">
              <li className="flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-400" /> Non-destructive OpenXML manipulation
              </li>
              <li className="flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-400" /> Fully reversible at any time
              </li>
            </ul>
          </div>

          {/* Card 5 */}
          <div className="glass-card rounded-2xl p-6 sm:p-8 flex flex-col justify-between">
            <div>
              <div className="w-12 h-12 rounded-xl bg-rose-500/10 border border-rose-500/20 flex items-center justify-center text-rose-400 mb-6">
                <ShieldCheck className="w-6 h-6" />
              </div>
              <h3 className="text-xl font-bold text-white">Originality Verification Guard</h3>
              <p className="text-sm text-slate-400 mt-2 leading-relaxed">
                Automated regression testing that diffs the remediated file against the original to ensure 0 layout shifts.
              </p>
            </div>
            <ul className="mt-6 space-y-2 text-xs text-slate-300">
              <li className="flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-400" /> 0 coordinate shifts certified
              </li>
              <li className="flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-400" /> 0 font size or typeface changes
              </li>
            </ul>
          </div>

          {/* Card 6 */}
          <div className="glass-card rounded-2xl p-6 sm:p-8 flex flex-col justify-between">
            <div>
              <div className="w-12 h-12 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-400 mb-6">
                <FileSpreadsheet className="w-6 h-6" />
              </div>
              <h3 className="text-xl font-bold text-white">Certified Audit Reports</h3>
              <p className="text-sm text-slate-400 mt-2 leading-relaxed">
                Export comprehensive compliance audits in interactive HTML, PDF/UA format, raw JSON, or CSV for compliance teams.
              </p>
            </div>
            <ul className="mt-6 space-y-2 text-xs text-slate-300">
              <li className="flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-400" /> Executive summary score card
              </li>
              <li className="flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-400" /> Itemized WCAG rule traceability
              </li>
            </ul>
          </div>
        </div>
      </section>

      {/* ─── Standards & Frameworks ──────────────────── */}
      <section id="standards" className="w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-20 border-t border-white/10">
        <div className="text-center max-w-3xl mx-auto mb-12">
          <span className="text-xs uppercase font-mono tracking-widest text-cyan-400 font-bold">
            Regulatory Compliance
          </span>
          <h2 className="text-3xl font-extrabold text-white mt-2">
            Benchmarked Against Global Accessibility Laws
          </h2>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-center">
          <div className="p-6 rounded-2xl glass-card">
            <p className="text-xl font-bold text-white">WCAG 2.1 AA</p>
            <p className="text-xs text-slate-400 mt-1">W3C International Standard</p>
          </div>
          <div className="p-6 rounded-2xl glass-card">
            <p className="text-xl font-bold text-white">Section 508</p>
            <p className="text-xs text-slate-400 mt-1">US Federal Procurement</p>
          </div>
          <div className="p-6 rounded-2xl glass-card">
            <p className="text-xl font-bold text-white">ADA Title II/III</p>
            <p className="text-xs text-slate-400 mt-1">Americans with Disabilities Act</p>
          </div>
          <div className="p-6 rounded-2xl glass-card">
            <p className="text-xl font-bold text-white">EN 301 549</p>
            <p className="text-xs text-slate-400 mt-1">European Union Standard</p>
          </div>
        </div>
      </section>

      {/* ─── CTA Banner ─────────────────────────────── */}
      <section className="w-full max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 pb-28">
        <div className="rounded-3xl bg-gradient-to-r from-brand-900/60 via-indigo-950/80 to-slate-900 p-8 sm:p-14 border border-brand-500/30 text-center relative overflow-hidden shadow-2xl">
          <div className="max-w-2xl mx-auto relative z-10">
            <h2 className="text-3xl sm:text-4xl font-extrabold text-white">
              Ready to verify and remediate your presentation?
            </h2>
            <p className="text-slate-300 mt-4 text-base">
              Upload any PowerPoint deck now to see detailed rule violations, Gemini AI alt text recommendations, and certified non-destructive fixes.
            </p>
            <div className="mt-8 flex justify-center">
              <button
                onClick={() => setIsUploadOpen(true)}
                className="px-8 py-4 rounded-xl bg-gradient-to-r from-brand-500 to-cyan-500 hover:from-brand-400 hover:to-cyan-400 text-white font-bold text-base shadow-xl shadow-brand-500/30 transition-all flex items-center gap-2"
              >
                <Sparkles className="w-5 h-5" />
                <span>Upload Presentation Deck</span>
              </button>
            </div>
          </div>
        </div>
      </section>

      {/* Upload Modal */}
      <UploadModal isOpen={isUploadOpen} onClose={() => setIsUploadOpen(false)} />
    </div>
  );
}

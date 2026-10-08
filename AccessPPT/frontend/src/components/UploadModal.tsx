"use client";

import React, { useState, useRef, useEffect } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import {
  X,
  UploadCloud,
  FileSpreadsheet,
  CheckCircle2,
  AlertCircle,
  Loader2,
  Sparkles,
  Shield,
  Eye,
  ArrowRight,
  Activity,
} from "lucide-react";
import { formatBytes } from "@/lib/utils";

interface UploadModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const STAGES = [
  { id: 1, title: "Uploading presentation to secure cloud...", icon: UploadCloud },
  { id: 2, title: "Parsing slide hierarchy & shape XML trees...", icon: FileSpreadsheet },
  { id: 3, title: "Evaluating WCAG 2.1 AA & Section 508 deterministic rules...", icon: Shield },
  { id: 4, title: "Engaging Gemini AI for multimodal semantic analysis...", icon: Sparkles },
  { id: 5, title: "Computing accessibility health score & zero-shift baseline...", icon: Eye },
];

export default function UploadModal({ isOpen, onClose }: UploadModalProps) {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [dragOver, setDragOver] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [currentStage, setCurrentStage] = useState(1);
  const [progressPercent, setProgressPercent] = useState(10);
  const [liveStepText, setLiveStepText] = useState("Preparing upload...");
  const [createdPresId, setCreatedPresId] = useState<string | null>(null);
  const [isFinished, setIsFinished] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Close on Escape
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen && !isProcessing) {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, isProcessing, onClose]);

  if (!isOpen) return null;

  const handleFile = (file: File) => {
    if (!file.name.toLowerCase().endsWith(".pptx")) {
      setErrorMessage("Please upload a valid Microsoft PowerPoint presentation (.pptx)");
      return;
    }
    if (file.size > 100 * 1024 * 1024) {
      setErrorMessage("File size exceeds 100MB limit.");
      return;
    }
    setErrorMessage(null);
    setSelectedFile(file);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFile(e.dataTransfer.files[0]);
    }
  };

  const navigateToPresentation = (id: string) => {
    onClose();
    router.push(`/presentations/${id}`);
  };

  const handleStartAnalysis = async () => {
    if (!selectedFile) return;

    setIsProcessing(true);
    setErrorMessage(null);
    setCurrentStage(1);
    setProgressPercent(15);
    setLiveStepText("Uploading presentation to server...");
    setIsFinished(false);

    try {
      // Step 1: Upload presentation
      const pres = await api.uploadPresentation(selectedFile);
      setCreatedPresId(pres.id);
      setCurrentStage(2);
      setProgressPercent(25);
      setLiveStepText("Presentation uploaded. Initializing OpenXML parser...");

      // Step 2: Trigger accessibility analysis & AI engine
      await api.triggerAnalysis(pres.id, true);
      setCurrentStage(2);
      setProgressPercent(30);
      setLiveStepText("Parsing slide shapes and text elements...");

      // Step 3: Real-time progress polling loop
      let isDone = false;
      let attempts = 0;
      const maxAttempts = 150; // Up to 2.5 minutes for very large decks

      while (!isDone && attempts < maxAttempts) {
        await new Promise((r) => setTimeout(r, 1000));
        attempts++;

        try {
          const run = await api.getAnalysisStatus(pres.id);
          const presData = await api.getPresentation(pres.id);

          if (run) {
            const rawProgress = run.progress || 30;
            setProgressPercent((prev) => Math.max(prev, rawProgress));

            if (run.current_step) {
              setLiveStepText(run.current_step);
            }

            // Map progress percentage to active STAGE (1 to 5)
            if (rawProgress < 25) {
              setCurrentStage(2);
            } else if (rawProgress < 50) {
              setCurrentStage(3);
            } else if (rawProgress < 85) {
              setCurrentStage(4);
            } else {
              setCurrentStage(5);
            }

            if (run.status === "complete" || rawProgress >= 100) {
              isDone = true;
            } else if (run.status === "failed") {
              throw new Error(run.error_message || "Accessibility audit encountered an error.");
            }
          } else if (presData) {
            if (presData.status === "complete") {
              isDone = true;
            } else if (presData.status === "failed") {
              throw new Error(presData.error_message || "Analysis failed.");
            }
          }
        } catch (pollErr: any) {
          // If polling momentarily blips, don't abort immediately unless fatal
          if (pollErr.message && pollErr.message.includes("Accessibility audit")) {
            throw pollErr;
          }
        }
      }

      // Finalize
      setProgressPercent(100);
      setCurrentStage(6); // All 5 stages checked
      setIsFinished(true);
      setLiveStepText("Audit completed successfully! Opening Accessibility Studio...");

      await new Promise((r) => setTimeout(r, 600));
      navigateToPresentation(pres.id);
    } catch (err: any) {
      setErrorMessage(err.message || "Failed to analyze presentation. Please try again.");
      setIsProcessing(false);
      setIsFinished(false);
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="upload-modal-title"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-md animate-in fade-in"
    >
      <div className="relative w-full max-w-xl glass-panel rounded-2xl p-6 sm:p-8 shadow-2xl border border-white/10 overflow-hidden">
        {/* Glowing aura */}
        <div className="absolute -top-24 -left-24 w-60 h-60 bg-brand-500/20 rounded-full blur-3xl pointer-events-none" />
        <div className="absolute -bottom-24 -right-24 w-60 h-60 bg-cyan-500/15 rounded-full blur-3xl pointer-events-none" />

        {/* Header */}
        <div className="flex items-center justify-between pb-4 border-b border-white/10">
          <div>
            <h2 id="upload-modal-title" className="text-xl font-bold text-white flex items-center gap-2">
              <UploadCloud className="w-5 h-5 text-brand-400" />
              Upload PowerPoint Presentation
            </h2>
            <p className="text-xs text-slate-400 mt-1">
              Supports .pptx up to 100MB &bull; 100% Zero Visual Modification Guarantee
            </p>
          </div>
          {!isProcessing && (
            <button
              onClick={onClose}
              className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          )}
        </div>

        {/* Content */}
        <div className="mt-6">
          {errorMessage && (
            <div className="mb-4 p-3 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-300 text-sm flex items-center gap-2">
              <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
              <span>{errorMessage}</span>
            </div>
          )}

          {!isProcessing ? (
            <>
              {/* Dropzone */}
              <div
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragOver(true);
                }}
                onDragLeave={() => setDragOver(false)}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
                className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all ${
                  dragOver
                    ? "border-brand-400 bg-brand-500/10 scale-[1.01]"
                    : "border-white/15 hover:border-brand-500/50 hover:bg-white/5"
                }`}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".pptx"
                  className="hidden"
                  onChange={(e) => {
                    if (e.target.files && e.target.files[0]) {
                      handleFile(e.target.files[0]);
                    }
                  }}
                />

                <div className="w-14 h-14 mx-auto rounded-2xl bg-brand-500/10 border border-brand-500/20 flex items-center justify-center text-brand-400 mb-4 group-hover:scale-110 transition-transform">
                  <UploadCloud className="w-7 h-7" />
                </div>

                <p className="text-sm font-semibold text-slate-200">
                  Click to browse or drag and drop your PowerPoint deck here
                </p>
                <p className="text-xs text-slate-400 mt-1">
                  Only .pptx presentations (Standard OpenXML format)
                </p>
              </div>

              {/* Selected File Card */}
              {selectedFile && (
                <div className="mt-4 p-3 rounded-xl bg-white/5 border border-white/10 flex items-center justify-between">
                  <div className="flex items-center space-x-3 overflow-hidden">
                    <div className="w-9 h-9 rounded-lg bg-rose-500/20 border border-rose-500/30 flex items-center justify-center text-rose-400 shrink-0">
                      <FileSpreadsheet className="w-5 h-5" />
                    </div>
                    <div className="truncate text-left">
                      <p className="text-sm font-medium text-slate-200 truncate">
                        {selectedFile.name}
                      </p>
                      <p className="text-xs text-slate-400">{formatBytes(selectedFile.size)}</p>
                    </div>
                  </div>
                  <button
                    onClick={() => setSelectedFile(null)}
                    className="p-1 text-slate-400 hover:text-white"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
              )}

              {/* Action Buttons */}
              <div className="mt-6 flex justify-end gap-3">
                <button
                  type="button"
                  onClick={onClose}
                  className="px-4 py-2 text-sm font-medium text-slate-300 hover:text-white rounded-lg hover:bg-white/5 transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  disabled={!selectedFile}
                  onClick={handleStartAnalysis}
                  className="px-5 py-2 text-sm font-semibold rounded-lg bg-gradient-to-r from-brand-600 to-indigo-600 hover:from-brand-500 hover:to-indigo-500 text-white shadow-lg shadow-brand-500/25 disabled:opacity-50 disabled:cursor-not-allowed transition-all flex items-center gap-2"
                >
                  <Sparkles className="w-4 h-4" />
                  <span>Start Accessibility Audit</span>
                </button>
              </div>
            </>
          ) : (
            /* Live Analysis Pipeline Tracker with Real-time Progress */
            <div className="py-2 space-y-5">
              <div className="text-center">
                <div className="relative inline-flex mb-3">
                  <div className="p-4 rounded-2xl bg-brand-500/10 border border-brand-500/30 text-brand-400">
                    {isFinished ? (
                      <CheckCircle2 className="w-8 h-8 text-emerald-400 animate-in zoom-in" />
                    ) : (
                      <Loader2 className="w-8 h-8 animate-spin text-brand-400" />
                    )}
                  </div>
                  <span className="absolute -top-1 -right-1 flex h-3.5 w-3.5">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-3.5 w-3.5 bg-cyan-500"></span>
                  </span>
                </div>

                <h3 className="text-lg font-bold text-white flex items-center justify-center gap-2">
                  <span>{isFinished ? "Audit Completed" : "Analyzing Presentation"}</span>
                  <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-brand-500/20 text-brand-300 border border-brand-500/30">
                    {progressPercent}%
                  </span>
                </h3>

                {/* Live Step Tracker Pill */}
                <div className="mt-2 inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-900/90 border border-cyan-500/30 text-cyan-300 text-xs shadow-inner max-w-full">
                  <Activity className="w-3.5 h-3.5 animate-pulse shrink-0 text-cyan-400" />
                  <span className="truncate font-medium">{liveStepText}</span>
                </div>
              </div>

              {/* Progress Bar */}
              <div className="w-full bg-white/5 rounded-full h-2.5 overflow-hidden border border-white/10 p-0.5">
                <div
                  className="bg-gradient-to-r from-brand-500 via-indigo-500 to-cyan-400 h-full rounded-full transition-all duration-500 ease-out shadow-lg shadow-cyan-500/50"
                  style={{ width: `${Math.min(100, Math.max(8, progressPercent))}%` }}
                />
              </div>

              {/* Stages List */}
              <div className="space-y-2.5 pt-1">
                {STAGES.map((s) => {
                  const Icon = s.icon;
                  const isDone = s.id < currentStage || isFinished;
                  const isCurrent = s.id === currentStage && !isFinished;

                  return (
                    <div
                      key={s.id}
                      className={`flex items-center space-x-3 p-2.5 rounded-xl transition-all ${
                        isCurrent
                          ? "bg-brand-500/15 border border-brand-500/40 text-white shadow-md shadow-brand-500/10"
                          : isDone
                          ? "bg-emerald-500/10 border border-emerald-500/20 text-emerald-300"
                          : "opacity-40 text-slate-400 border border-transparent"
                      }`}
                    >
                      <div className="shrink-0">
                        {isDone ? (
                          <CheckCircle2 className="w-5 h-5 text-emerald-400" />
                        ) : isCurrent ? (
                          <Loader2 className="w-5 h-5 animate-spin text-brand-400" />
                        ) : (
                          <Icon className="w-5 h-5" />
                        )}
                      </div>
                      <span className="text-xs sm:text-sm font-medium">{s.title}</span>
                    </div>
                  );
                })}
              </div>

              {/* Emergency fallback button so user is never stuck */}
              {createdPresId && (
                <div className="pt-2 flex justify-between items-center text-xs text-slate-400 border-t border-white/10">
                  <span>Audit continues safely in background.</span>
                  <button
                    type="button"
                    onClick={() => navigateToPresentation(createdPresId)}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-white font-medium transition-colors"
                  >
                    <span>Open Presentation</span>
                    <ArrowRight className="w-3.5 h-3.5" />
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

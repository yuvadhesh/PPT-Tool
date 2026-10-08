"use client";

import React, { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import UploadModal from "./UploadModal";
import {
  ShieldCheck,
  FileUp,
  LayoutDashboard,
  Sparkles,
  BookOpen,
  LogOut,
  User as UserIcon,
  ChevronRight,
} from "lucide-react";

export default function Navbar() {
  const pathname = usePathname();
  const { user, logout, demoLogin } = useAuth();
  const [isUploadOpen, setIsUploadOpen] = useState(false);

  return (
    <>
      <header className="sticky top-0 z-40 w-full border-b border-white/10 glass-panel">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          {/* Logo & Brand */}
          <div className="flex items-center space-x-6">
            <Link
              href="/"
              className="flex items-center space-x-3 group focus:outline-none focus:ring-2 focus:ring-brand-400 rounded-lg p-1"
            >
              <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-brand-600 via-indigo-500 to-cyan-400 flex items-center justify-center shadow-lg shadow-indigo-500/25 group-hover:scale-105 transition-transform">
                <ShieldCheck className="w-6 h-6 text-white" />
              </div>
              <div>
                <span className="text-xl font-bold tracking-tight bg-gradient-to-r from-white via-slate-100 to-slate-400 bg-clip-text text-transparent">
                  Access<span className="text-brand-400">PPT</span>
                </span>
                <span className="hidden sm:inline-block ml-2 px-2 py-0.5 text-[10px] uppercase tracking-wider font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 rounded-full">
                  AI v2.4
                </span>
              </div>
            </Link>

            {/* Nav links */}
            <nav className="hidden md:flex items-center space-x-1" aria-label="Main Navigation">
              <Link
                href="/dashboard"
                className={`px-3 py-1.5 text-sm font-medium rounded-lg transition-colors flex items-center space-x-1.5 ${
                  pathname === "/dashboard"
                    ? "bg-white/10 text-white"
                    : "text-slate-400 hover:text-white hover:bg-white/5"
                }`}
              >
                <LayoutDashboard className="w-4 h-4" />
                <span>Dashboard</span>
              </Link>
              <Link
                href="/#features"
                className="px-3 py-1.5 text-sm font-medium text-slate-400 hover:text-white hover:bg-white/5 rounded-lg transition-colors flex items-center space-x-1.5"
              >
                <Sparkles className="w-4 h-4" />
                <span>Features</span>
              </Link>
              <Link
                href="/#standards"
                className="px-3 py-1.5 text-sm font-medium text-slate-400 hover:text-white hover:bg-white/5 rounded-lg transition-colors flex items-center space-x-1.5"
              >
                <BookOpen className="w-4 h-4" />
                <span>Standards</span>
              </Link>
            </nav>
          </div>

          {/* Right Action buttons */}
          <div className="flex items-center space-x-3">
            <button
              onClick={() => setIsUploadOpen(true)}
              className="px-4 py-2 text-sm font-semibold rounded-lg bg-gradient-to-r from-brand-600 to-indigo-600 hover:from-brand-500 hover:to-indigo-500 text-white shadow-md shadow-brand-500/20 hover:shadow-brand-500/40 transition-all flex items-center space-x-2 active:scale-95"
            >
              <FileUp className="w-4 h-4" />
              <span className="hidden sm:inline">Upload Presentation</span>
              <span className="sm:hidden">Upload</span>
            </button>

            {user ? (
              <div className="flex items-center space-x-3 pl-2 border-l border-white/10">
                <div className="hidden lg:flex flex-col text-right text-xs">
                  <span className="font-medium text-slate-200">{user.full_name}</span>
                  <span className="text-slate-400">{user.email}</span>
                </div>
                <button
                  onClick={logout}
                  title="Sign out"
                  className="p-2 rounded-lg text-slate-400 hover:text-rose-400 hover:bg-rose-500/10 transition-colors"
                >
                  <LogOut className="w-4 h-4" />
                </button>
              </div>
            ) : (
              <div className="flex items-center space-x-2">
                <button
                  onClick={demoLogin}
                  className="px-3 py-1.5 text-xs font-medium rounded-lg border border-cyan-500/30 bg-cyan-500/10 text-cyan-300 hover:bg-cyan-500/20 transition-all flex items-center space-x-1"
                >
                  <span>Quick Demo</span>
                  <ChevronRight className="w-3 h-3" />
                </button>
                <Link
                  href="/login"
                  className="px-3 py-1.5 text-sm font-medium text-slate-300 hover:text-white rounded-lg hover:bg-white/5 transition-colors"
                >
                  Sign In
                </Link>
              </div>
            )}
          </div>
        </div>
      </header>

      {/* Upload PPTX Modal */}
      <UploadModal isOpen={isUploadOpen} onClose={() => setIsUploadOpen(false)} />
    </>
  );
}

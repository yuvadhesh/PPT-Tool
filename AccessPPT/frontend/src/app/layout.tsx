import type { Metadata, Viewport } from "next";
import "./globals.css";
import Providers from "./providers";
import Navbar from "@/components/Navbar";
import Footer from "@/components/Footer";

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

export const metadata: Metadata = {
  title: "AccessPPT — AI-Powered PowerPoint Accessibility Checker",
  description:
    "Make PowerPoint accessible — without changing your original presentation. Automated WCAG 2.1 AA auditing, Gemini AI semantic remediation, and 100% visual layout preservation.",
  keywords: [
    "PowerPoint Accessibility",
    "PPTX WCAG Checker",
    "Section 508 Presentation Tool",
    "AI Alt Text",
    "Accessible Slides",
    "ADA Presentation Compliance",
  ],
  authors: [{ name: "AccessPPT Team" }],
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen flex flex-col bg-slate-950 text-slate-100 bg-grid-pattern relative">
        <a href="#main-content" className="skip-to-content">
          Skip to main content
        </a>
        <div className="absolute inset-0 glow-gradient pointer-events-none" />
        <Providers>
          <Navbar />
          <main id="main-content" className="flex-1 z-10">
            {children}
          </main>
          <Footer />
        </Providers>
      </body>
    </html>
  );
}

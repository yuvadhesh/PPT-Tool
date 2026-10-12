import {
  User,
  Presentation,
  Slide,
  AccessibilityIssue,
  DashboardStats,
  VerificationResult,
  AnalysisRun,
  ReadingOrderReport,
  ReadingOrderFixResult,
  EquationInventory,
  EquationState,
  MathTypeIntegrationStatus,
} from "./types";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ||
  (typeof window !== "undefined" ? "/api/v1" : "http://127.0.0.1:8000/api/v1");

class ApiClient {
  private getToken(): string | null {
    if (typeof window === "undefined") return null;
    return localStorage.getItem("accessppt_token");
  }

  private setToken(token: string) {
    if (typeof window !== "undefined") {
      localStorage.setItem("accessppt_token", token);
    }
  }

  private clearToken() {
    if (typeof window !== "undefined") {
      localStorage.removeItem("accessppt_token");
    }
  }

  /**
   * Transparently log in demo user if no token exists yet
   */
  private async ensureAuth(): Promise<string | null> {
    let token = this.getToken();
    if (token) return token;

    if (typeof window === "undefined") return null;

    try {
      const res = await fetch(`${API_BASE_URL}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: "demo@accessppt.com",
          password: "Password123!",
        }),
      });
      if (res.ok) {
        const data = await res.json();
        if (data.access_token) {
          this.setToken(data.access_token);
          return data.access_token;
        }
      }
    } catch {
      // Offline or network error
    }
    return null;
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {},
    retryAuth = true
  ): Promise<T> {
    let token = this.getToken();
    if (!token && !endpoint.startsWith("/auth/")) {
      token = await this.ensureAuth();
    }

    const headers: Record<string, string> = {
      ...(options.headers as Record<string, string>),
    };

    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    if (!(options.body instanceof FormData)) {
      headers["Content-Type"] = "application/json";
    }

    try {
      const response = await fetch(`${API_BASE_URL}${endpoint}`, {
        ...options,
        headers,
      });

      if (response.status === 401 && retryAuth && !endpoint.startsWith("/auth/")) {
        this.clearToken();
        const freshToken = await this.ensureAuth();
        if (freshToken) {
          headers["Authorization"] = `Bearer ${freshToken}`;
          const retryRes = await fetch(`${API_BASE_URL}${endpoint}`, {
            ...options,
            headers,
          });
          if (retryRes.ok) {
            return await retryRes.json();
          }
        }
      }

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Request failed with status ${response.status}`);
      }

      return await response.json();
    } catch (err) {
      console.warn(`API call failed for ${endpoint}:`, err);
      throw err;
    }
  }

  // Auth
  async login(formData: FormData): Promise<{ access_token: string }> {
    const email = (formData.get("username") as string) || (formData.get("email") as string);
    const password = formData.get("password") as string;
    const res = await this.request<{ access_token: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }, false);
    this.setToken(res.access_token);
    return res;
  }

  async register(data: { email: string; full_name: string; password: string }): Promise<User> {
    return await this.request<User>("/auth/register", {
      method: "POST",
      body: JSON.stringify(data),
    }, false);
  }

  async getMe(): Promise<User | null> {
    try {
      return await this.request<User>("/auth/me");
    } catch {
      return null;
    }
  }

  logout() {
    this.clearToken();
  }

  // Dashboard Stats
  async getDashboardStats(): Promise<DashboardStats> {
    try {
      const data = await this.request<any>("/dashboard/stats");
      return {
        total_presentations: data.total_presentations ?? 0,
        total_slides_analyzed: data.total_slides_analyzed ?? 0,
        avg_accessibility_score: data.avg_accessibility_score ?? 0,
        total_issues_fixed: data.total_issues_fixed ?? 0,
        presentations_above_90: data.presentations_above_90 ?? 0,
        issues_by_severity: data.issues_by_severity ?? {
          error: 0,
          warning: 0,
          review: 0,
          pass: 0,
        },
        issues_summary: data.issues_summary ?? {},
        recent_presentations: data.recent_presentations ?? [],
      };
    } catch {
      return {
        total_presentations: 0,
        total_slides_analyzed: 0,
        avg_accessibility_score: 0,
        total_issues_fixed: 0,
        presentations_above_90: 0,
        issues_by_severity: {
          error: 0,
          warning: 0,
          review: 0,
          pass: 0,
        },
        issues_summary: {},
        recent_presentations: [],
      };
    }
  }

  // Presentations
  async getPresentations(): Promise<{ presentations: Presentation[]; total: number }> {
    try {
      const res = await this.request<any>("/presentations");
      const list = res.items || res.presentations || (Array.isArray(res) ? res : []);
      return { presentations: list, total: res.total ?? list.length };
    } catch {
      return { presentations: [], total: 0 };
    }
  }

  async getPresentation(id: string): Promise<Presentation | null> {
    try {
      return await this.request<Presentation>(`/presentations/${id}`);
    } catch {
      return null;
    }
  }

  async uploadPresentation(file: File): Promise<Presentation> {
    const formData = new FormData();
    formData.append("file", file);

    return await this.request<Presentation>("/presentations/upload", {
      method: "POST",
      body: formData,
    });
  }

  async triggerAnalysis(presentationId: string, runAi = true): Promise<any> {
    return await this.request(`/presentations/${presentationId}/analyze?run_ai=${runAi}`, {
      method: "POST",
    });
  }

  async getAnalysisStatus(presentationId: string): Promise<AnalysisRun | null> {
    try {
      return await this.request<AnalysisRun>(`/presentations/${presentationId}/analysis`);
    } catch {
      return null;
    }
  }

  async getSlides(presentationId: string): Promise<Slide[]> {
    try {
      const res = await this.request<Slide[]>(`/presentations/${presentationId}/slides`);
      return Array.isArray(res) ? res : [];
    } catch {
      return [];
    }
  }

  async getIssues(
    presentationId: string,
    filters?: { severity?: string; slide_id?: string; category?: string }
  ): Promise<{ issues: AccessibilityIssue[]; total: number }> {
    try {
      const params = new URLSearchParams();
      if (filters?.severity) params.set("severity", filters.severity);
      if (filters?.slide_id) params.set("slide_id", filters.slide_id);
      if (filters?.category) params.set("category", filters.category);
      const queryString = params.toString() ? `?${params.toString()}` : "";
      const res = await this.request<any>(`/presentations/${presentationId}/issues${queryString}`);
      const list = res.issues || res.items || (Array.isArray(res) ? res : []);
      return { issues: list, total: res.total ?? list.length };
    } catch {
      return { issues: [], total: 0 };
    }
  }

  async applySafeFixes(presentationId: string): Promise<{ task_id: string; fixes_queued: number }> {
    return await this.request(`/presentations/${presentationId}/fix-safe`, {
      method: "POST",
    });
  }

  async getOutline(presentationId: string): Promise<{ presentation_id: string; slides_count: number; outline: any[] }> {
    try {
      return await this.request<{ presentation_id: string; slides_count: number; outline: any[] }>(`/presentations/${presentationId}/outline`);
    } catch {
      return { presentation_id: presentationId, slides_count: 0, outline: [] };
    }
  }

  async syncReadingOrder(presentationId: string): Promise<{ message: string; task_id: string; slides_count: number }> {
    return await this.request(`/presentations/${presentationId}/sync-reading-order`, {
      method: "POST",
    });
  }

  async verifyOriginality(presentationId: string): Promise<VerificationResult> {
    return await this.request<VerificationResult>(`/presentations/${presentationId}/verify`);
  }

  async updateIssueStatus(issueId: string, status: string): Promise<any> {
    return await this.request(`/issues/${issueId}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    });
  }

  async updateAltText(issueId: string, altText: string, isDecorative = false): Promise<any> {
    return await this.request(`/issues/${issueId}/alt-text`, {
      method: "PUT",
      body: JSON.stringify({ alt_text: altText, is_decorative: isDecorative }),
    });
  }

  async checkReadingOrder(presentationId: string, useAi = true): Promise<ReadingOrderReport> {
    return await this.request<ReadingOrderReport>(
      `/presentations/${presentationId}/check-reading-order?use_ai=${useAi}`,
      { method: "POST" }
    );
  }

  async fixReadingOrder(presentationId: string, useAi = true): Promise<ReadingOrderFixResult> {
    return await this.request<ReadingOrderFixResult>(
      `/presentations/${presentationId}/fix-reading-order?use_ai=${useAi}`,
      { method: "POST" }
    );
  }

  async getReadingOrder(presentationId: string): Promise<ReadingOrderReport> {
    return await this.request<ReadingOrderReport>(
      `/presentations/${presentationId}/reading-order`
    );
  }

  async downloadReadingOrderDebugReport(presentationId: string, filename?: string): Promise<void> {
    return await this.downloadFile(
      `/presentations/${presentationId}/reading-order/debug-report`,
      filename || "reading_order_debug.json"
    );
  }

  async getMathTypeIntegration(): Promise<MathTypeIntegrationStatus> {
    return await this.request<MathTypeIntegrationStatus>(`/equations/integration`);
  }

  async scanEquations(presentationId: string): Promise<EquationInventory> {
    return await this.request<EquationInventory>(`/presentations/${presentationId}/equations/scan`, {
      method: "POST",
    });
  }

  async convertEquations(presentationId: string): Promise<{ task_id: string; status: string }> {
    return await this.request(`/presentations/${presentationId}/equations/convert`, { method: "POST" });
  }

  async getEquationState(presentationId: string): Promise<EquationState> {
    return await this.request<EquationState>(`/presentations/${presentationId}/equations`);
  }

  async downloadConvertedEquations(presentationId: string, filename = "mathtype_presentation.pptx"): Promise<void> {
    return await this.downloadFile(`/presentations/${presentationId}/equations/download`, filename);
  }

  async downloadEquationReport(presentationId: string): Promise<void> {
    return await this.downloadFile(
      `/presentations/${presentationId}/equations/report`,
      `equation_report_${presentationId}.json`
    );
  }

  async downloadFile(endpoint: string, fallbackFilename: string): Promise<void> {
    let token = this.getToken();
    if (!token) {
      token = await this.ensureAuth();
    }
    const headers: Record<string, string> = {};
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }

    const response = await fetch(`${API_BASE_URL}${endpoint}`, {
      method: "GET",
      headers,
    });

    if (!response.ok) {
      throw new Error(`Failed to download: ${response.statusText}`);
    }

    const blob = await response.blob();
    let filename = fallbackFilename;
    const disposition = response.headers.get("content-disposition");
    if (disposition && disposition.includes("filename=")) {
      const match = disposition.match(/filename=["']?([^"';]+)["']?/);
      if (match && match[1]) {
        filename = match[1];
      }
    }

    const blobUrl = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = blobUrl;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(blobUrl);
  }
}

export const api = new ApiClient();

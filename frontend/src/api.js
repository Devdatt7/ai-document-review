import { describeHttpError } from "./lib.js";

// Set VITE_API_URL to override the backend for a deployment.
export const API_URL = (
  import.meta.env?.VITE_API_URL ||
  (import.meta.env?.PROD
    ? "https://ai-document-review-1.onrender.com"
    : "http://localhost:8000")
).replace(/\/+$/, "");

export const ANALYSIS_TIMEOUT_MS = 60_000;

export async function analyzeDocument(documentText, sourceText) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), ANALYSIS_TIMEOUT_MS);
  try {
    const response = await fetch(`${API_URL}/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ document_text: documentText, source_text: sourceText }),
      signal: controller.signal,
    });

    if (!response.ok) {
      let detail = "";
      try {
        detail = (await response.json()).detail;
      } catch (error) {
        if (controller.signal.aborted) throw error;
        // body was not JSON; the status code is enough
      }
      throw new Error(describeHttpError(response.status, detail));
    }
    return await response.json();
  } catch (error) {
    if (controller.signal.aborted) {
      throw new Error(
        "Analysis timed out after 1 minute. No completed report was received. " +
        "Try a shorter document or check the backend logs before retrying."
      );
    }
    if (error instanceof TypeError) {
      throw new Error("Cannot reach the review service. Check that the backend is running and try again.");
    }
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

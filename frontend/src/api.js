import { describeHttpError } from "./lib.js";

// Set VITE_API_URL to override the backend for a deployment.
export const API_URL = (
  import.meta.env?.VITE_API_URL ||
  (import.meta.env?.PROD
    ? "https://ai-document-review-1.onrender.com"
    : "http://localhost:8000")
).replace(/\/+$/, "");

export async function analyzeDocument(documentText, sourceText) {
  let response;
  try {
    response = await fetch(`${API_URL}/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ document_text: documentText, source_text: sourceText }),
    });
  } catch {
    throw new Error("Cannot reach the review service. Check that the backend is running and try again.");
  }

  if (!response.ok) {
    let detail = "";
    try {
      detail = (await response.json()).detail;
    } catch {
      // body was not JSON; the status code is enough
    }
    throw new Error(describeHttpError(response.status, detail));
  }
  return response.json();
}

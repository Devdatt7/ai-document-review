import { describeHttpError } from "./lib.js";

// Set VITE_API_URL in frontend/.env to point at another backend.
export const API_URL = import.meta.env?.VITE_API_URL || "http://localhost:8000";

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

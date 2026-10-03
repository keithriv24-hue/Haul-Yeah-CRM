import { bookLeadApi } from "@/lib/api";

// Server-authoritative "Book as job" (Prompt 2). The backend is the ONE place that
// creates/links the canonical Project. A deposit (or an owner override) is what actually
// marks a lead Booked — clicking this only starts the job as "pending deposit".
export async function bookLeadAsJob(_helpers, lead) {
  return bookLeadApi(lead.id);
}

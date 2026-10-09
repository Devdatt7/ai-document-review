// Synthetic documents and policy text for local, offline demonstrations only.
export const GOOD_DOCUMENT = `Refunds are available within 30 days of purchase.
Customized products are not eligible for a refund.
Reimbursement is capped at ₹25,000 per claim.
Reimbursement is paid within 10 working days.
This policy is effective from 1 January 2026.
Monthly service availability is targeted at 99.5%.
Parking is available for visitors on the ground floor at a daily charge.`;

export const FLAWED_DOCUMENT = `The maximum reimbursement is ₹50,000.
The policy is effective from 1 April 2026.
The service guarantees 100% uptime.
The office has free parking.
Premium roadside assistance is included with every purchase.
Customer PAN: ABCDE1234F.`;

export const DEMO_SOURCE = `SYNTHETIC DEMO SOURCE (made-up text, not a real policy)

Refunds are available within 30 days of purchase. Customized products are not eligible for a refund.

Reimbursement is capped at ₹25,000 per claim and is paid within 10 working days.

This policy is effective from 1 January 2026.

Service availability is targeted at 99.5% per month. This is a target, not a guarantee.

Parking is available for visitors on the ground floor at a daily charge.`;

export const GOOD_PRESET = { document: GOOD_DOCUMENT, source: DEMO_SOURCE };
export const FLAWED_PRESET = { document: FLAWED_DOCUMENT, source: DEMO_SOURCE };

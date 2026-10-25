import { db } from "../db";

function pad(n: number): string {
  return n < 10 ? `0${n}` : String(n);
}

function formatDate(ms: number): string {
  const d = new Date(ms);
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}`;
}

const NET_TERMS_DAYS = 30;

export async function createInvoice(accountId: string, amountCents: number) {
  const issuedAt = Date.now();
  const dueAt = issuedAt + NET_TERMS_DAYS * 24 * 60 * 60 * 1000;
  const invoice = { accountId, amountCents, issued: formatDate(issuedAt), due: formatDate(dueAt) };
  await db.invoices.insert(invoice);
  return invoice;
}

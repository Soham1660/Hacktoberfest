import { db } from "../db";
import { addDays, formatDate } from "../utils/time";

const NET_TERMS_DAYS = 30;

export async function createInvoice(accountId: string, amountCents: number) {
  const issuedAt = Date.now();
  const dueAt = addDays(issuedAt, NET_TERMS_DAYS);
  const invoice = { accountId, amountCents, issued: formatDate(issuedAt), due: formatDate(dueAt) };
  await db.invoices.insert(invoice);
  return invoice;
}

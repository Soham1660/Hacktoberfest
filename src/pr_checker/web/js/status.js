/** Where a change stands against the PR's claims. Shared so the UI can show provisional status while a review streams in. */
export function changeStatus(c) {
  if (c.selfCheck?.outcome === "withdrawn") return "retracted";
  if (c.contradicts.length) return "contradicts";
  if (c.claims.length) return "explained";
  if (c.effect === "none" || c.effect === "cosmetic") return "incidental";
  return "unexplained";
}

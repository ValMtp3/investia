import { describe, expect, it } from "vitest";
import { isAbortError } from "../lib/errors";
import { formatMoney } from "../lib/format";

describe("formatMoney", () => {
  it("formate en français avec la virgule et le symbole de la devise", () => {
    expect(formatMoney(12.5, "EUR")).toMatch(/^12,50\s€$/);
    expect(formatMoney(9983.4, "EUR")).toMatch(/9\s983,40\s€/);
  });

  it("garde deux décimales même pour un nombre entier", () => {
    expect(formatMoney(3, "EUR")).toMatch(/^3,00\s€$/);
  });
});

describe("isAbortError", () => {
  it("reconnaît une annulation volontaire (AbortController)", () => {
    expect(isAbortError(new DOMException("annulé", "AbortError"))).toBe(true);
  });

  it("refuse les autres erreurs et les valeurs qui ne sont pas des erreurs", () => {
    expect(isAbortError(new Error("réseau"))).toBe(false);
    expect(isAbortError("AbortError")).toBe(false);
    expect(isAbortError(null)).toBe(false);
    expect(isAbortError(undefined)).toBe(false);
  });
});

import { describe, expect, it } from "vitest";
import { isAbortError } from "../lib/errors";
import { formatDateTime, formatMoney, formatPercent } from "../lib/format";

describe("formatMoney", () => {
  it("formate en français avec la virgule et le symbole de la devise", () => {
    expect(formatMoney(12.5, "EUR")).toMatch(/^12,50\s€$/);
    expect(formatMoney(9983.4, "EUR")).toMatch(/9\s983,40\s€/);
  });

  it("garde deux décimales même pour un nombre entier", () => {
    expect(formatMoney(3, "EUR")).toMatch(/^3,00\s€$/);
  });
});

describe("formatDateTime", () => {
  it("formate une date ISO en français (JJ/MM/AAAA, HH:MM)", () => {
    const formatted = formatDateTime("2026-11-05T10:30:00+00:00");
    expect(formatted).toMatch(/05\/11\/2026/);
    expect(formatted).toMatch(/\d{2}:\d{2}/);
  });

  it("renvoie la chaîne telle quelle si la date est illisible", () => {
    expect(formatDateTime("pas une date")).toBe("pas une date");
  });
});

describe("formatPercent", () => {
  it("ajoute le signe + aux hausses et garde le - des baisses", () => {
    expect(formatPercent(1.331)).toBe("+1,33 %");
    expect(formatPercent(-0.5)).toBe("-0,50 %");
  });

  it("formate zéro avec un +", () => {
    expect(formatPercent(0)).toBe("+0,00 %");
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

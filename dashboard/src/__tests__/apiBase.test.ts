import { afterEach, describe, expect, it, vi } from "vitest";

// En ligne (4 bis, D49) le dashboard est construit avec VITE_API_URL=/api :
// les appels restent sur la même origine et le nginx du dashboard les aiguille vers le backend.
describe("adresse de base de l'API", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    vi.resetModules();
  });

  it("utilise VITE_API_URL=/api comme préfixe relatif (jamais 127.0.0.1)", async () => {
    vi.stubEnv("VITE_API_URL", "/api");
    vi.resetModules();
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({ cash: 0, positions: [], positions_value: 0, total_value: 0, currency: "EUR" }),
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    const { fetchPortfolio } = await import("../api");
    await fetchPortfolio();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/portfolio");
  });

  it("garde 127.0.0.1:8000 par défaut pour le développement local", async () => {
    vi.stubEnv("VITE_API_URL", undefined);
    vi.resetModules();
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({ cash: 0, positions: [], positions_value: 0, total_value: 0, currency: "EUR" }),
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    const { fetchPortfolio } = await import("../api");
    await fetchPortfolio();

    expect(fetchMock.mock.calls[0][0]).toBe("http://127.0.0.1:8000/portfolio");
  });
});

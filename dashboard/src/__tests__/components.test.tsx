import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import Badge from "../components/Badge";
import EmptyState from "../components/EmptyState";
import Loading from "../components/Loading";
import PageHeader from "../components/PageHeader";
import Sparkline from "../components/Sparkline";
import Stat from "../components/Stat";

describe("PageHeader", () => {
  it("rend un titre de niveau 1 avec l'id fourni, le sous-titre et les actions", () => {
    render(
      <PageHeader
        id="page-title"
        title="Marché"
        subtitle="Prix en direct"
        actions={<button type="button">Action</button>}
      />,
    );
    expect(screen.getByRole("heading", { level: 1, name: "Marché" })).toHaveAttribute(
      "id",
      "page-title",
    );
    expect(screen.getByText("Prix en direct")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Action" })).toBeInTheDocument();
  });

  it("fonctionne sans sous-titre ni actions", () => {
    render(<PageHeader id="t" title="Seul" />);
    expect(screen.getByRole("heading", { level: 1, name: "Seul" })).toBeInTheDocument();
  });
});

describe("Badge", () => {
  it("rend son texte avec le ton demandé", () => {
    render(<Badge tone="gain">+1,2 %</Badge>);
    expect(screen.getByText("+1,2 %")).toBeInTheDocument();
  });

  it("accepte le ton neutre par défaut", () => {
    render(<Badge>différé</Badge>);
    expect(screen.getByText("différé")).toBeInTheDocument();
  });
});

describe("Stat", () => {
  it("affiche libellé, valeur, variation et source", () => {
    render(
      <Stat
        label="Valeur totale"
        value="9 983,40 €"
        delta="+0,5 %"
        deltaTone="gain"
        source="source : finnhub"
      />,
    );
    expect(screen.getByText("Valeur totale")).toBeInTheDocument();
    expect(screen.getByText("9 983,40 €")).toBeInTheDocument();
    expect(screen.getByText("+0,5 %")).toBeInTheDocument();
    expect(screen.getByText(/finnhub/)).toBeInTheDocument();
  });

  it("affiche une variation négative avec le ton signal", () => {
    render(<Stat label="Perf" value="9 500 €" delta="-5,0 %" deltaTone="signal" />);
    expect(screen.getByText("-5,0 %")).toBeInTheDocument();
  });

  it("sans variation ni source, n'affiche que libellé et valeur", () => {
    render(<Stat label="Cash" value="6 900,00 €" />);
    expect(screen.getByText("Cash")).toBeInTheDocument();
    expect(screen.getByText("6 900,00 €")).toBeInTheDocument();
  });
});

describe("EmptyState", () => {
  it("affiche titre, indice et action", () => {
    render(
      <EmptyState
        title="Aucune position pour l'instant."
        hint="Passe un ordre simulé depuis la page Agent."
        action={<button type="button">Voir l'agent</button>}
      />,
    );
    expect(screen.getByText("Aucune position pour l'instant.")).toBeInTheDocument();
    expect(screen.getByText(/ordre simulé/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Voir l'agent" })).toBeInTheDocument();
  });

  it("fonctionne avec seulement un titre", () => {
    render(<EmptyState title="Rien ici." />);
    expect(screen.getByText("Rien ici.")).toBeInTheDocument();
  });
});

describe("Loading", () => {
  it("a le rôle status et le libellé donné", () => {
    render(<Loading label="Chargement du portefeuille…" />);
    expect(screen.getByRole("status")).toHaveTextContent("Chargement du portefeuille…");
  });
});

describe("Sparkline", () => {
  it("rend un svg role=img avec le libellé et un tracé polyline", () => {
    const { container } = render(<Sparkline points={[1, 3, 2, 4]} label="tendance AAPL" />);
    expect(screen.getByRole("img", { name: "tendance AAPL" }).tagName.toLowerCase()).toBe("svg");
    expect(container.querySelector("polyline")).not.toBeNull();
  });

  it("trace une ligne plate quand tous les points sont égaux", () => {
    const { container } = render(<Sparkline points={[5, 5, 5]} label="plate" />);
    expect(container.querySelector("polyline")).not.toBeNull();
  });

  it("ne rend rien avec moins de 2 points", () => {
    render(<Sparkline points={[7]} label="un seul point" />);
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("ignore les points non finis", () => {
    render(<Sparkline points={[1, Number.NaN]} label="invalide" />);
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });
});

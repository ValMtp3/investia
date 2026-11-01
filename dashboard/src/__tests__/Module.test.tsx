import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import ErrorNotice from "../components/ErrorNotice";
import Module from "../components/Module";

describe("Module", () => {
  it("expose son titre comme un titre de niveau 2 et nomme sa région", () => {
    render(
      <Module title="Positions">
        <p>contenu</p>
      </Module>,
    );
    expect(screen.getByRole("heading", { level: 2, name: "Positions" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Positions" })).toHaveTextContent("contenu");
  });

  it("donne un identifiant distinct à chaque module", () => {
    render(
      <>
        <Module title="Valeur">a</Module>
        <Module title="Positions">b</Module>
      </>,
    );
    expect(screen.getByRole("region", { name: "Valeur" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Positions" })).toBeInTheDocument();
  });
});

describe("ErrorNotice", () => {
  it("annonce l'erreur avec le rôle alert", () => {
    render(<ErrorNotice>API indisponible</ErrorNotice>);
    expect(screen.getByRole("alert")).toHaveTextContent("API indisponible");
  });
});

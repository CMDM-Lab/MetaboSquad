import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import Kicker from "../Kicker";

describe("Kicker", () => {
  it("renders its label", () => {
    render(<Kicker>ANALYSIS</Kicker>);
    expect(screen.getByText("ANALYSIS")).toBeInTheDocument();
  });

  // The kicker is the only place allowed below 12px, and only because it is an
  // uppercase mono label. If it ever renders lowercase the size becomes a
  // legibility bug rather than a deliberate exception.
  it("is uppercased by CSS, not by the caller", () => {
    render(<Kicker>analysis result</Kicker>);
    const el = screen.getByText("analysis result");
    expect(el).toHaveStyle({ textTransform: "uppercase" });
  });
});

import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { LocaleProvider } from "@/src/i18n/LocaleContext";
import ErrorCard from "../ErrorCard";

function renderCard(props: React.ComponentProps<typeof ErrorCard>) {
  return render(
    <LocaleProvider>
      <ErrorCard {...props} />
    </LocaleProvider>,
  );
}

describe("ErrorCard", () => {
  // Omitting `tone` must keep exactly today's behaviour: every existing
  // caller passes only `detail` (plus optionally onRetry),
  // never `tone`, and must keep working unchanged.
  it("defaults to the error tone: alert role, kicker, detail text, and a retry button", () => {
    const onRetry = vi.fn();
    renderCard({ detail: "無法連線到伺服器", onRetry });

    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText("錯誤")).toBeInTheDocument();
    expect(screen.getByText("無法連線到伺服器")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重試" })).toBeInTheDocument();
  });

  // The two tests above/below only check for the retry button's presence or
  // absence. An implementation that always renders the accent error surface
  // — bg-accent-100/border-accent-300 and an accent kicker — while merely
  // hiding retry for tone="notice" would pass every test written so far.
  // These pin the actual tone-conditional appearance so that defect class is
  // caught.
  it("tone='error' (default) uses the accent surface and an accent kicker", () => {
    renderCard({ detail: "無法連線到伺服器" });

    const alert = screen.getByRole("alert");
    expect(alert).toHaveClass("border-accent-300", "bg-accent-100");
    expect(alert).not.toHaveClass("border-divider", "bg-neutral-100");

    const kicker = screen.getByText("錯誤");
    expect(kicker).toHaveClass("text-accent-700");
    expect(kicker).not.toHaveClass("text-neutral-500");
  });

  it("tone='notice' uses the divider/neutral surface and a faint kicker, not the accent error surface", () => {
    renderCard({ detail: "連線中斷，已完成的步驟保留", tone: "notice" });

    const alert = screen.getByRole("alert");
    expect(alert).toHaveClass("border-divider", "bg-neutral-100");
    expect(alert).not.toHaveClass("border-accent-300", "bg-accent-100");

    const kicker = screen.getByText("錯誤");
    expect(kicker).toHaveClass("text-neutral-500");
    expect(kicker).not.toHaveClass("text-accent-700");
  });

  // error.streamAborted and error.duplicateRequest are neutral notices, not
  // failures: tone="notice" must never render a retry control, even when the
  // caller still passes onRetry.
  it("tone='notice' has no retry button even when onRetry is provided", () => {
    const onRetry = vi.fn();
    renderCard({ detail: "連線中斷，已完成的步驟保留", onRetry, tone: "notice" });

    expect(screen.queryByRole("button", { name: "重試" })).not.toBeInTheDocument();
  });

  it("renders no action row when onRetry is not provided", () => {
    renderCard({ detail: "無法連線到伺服器" });

    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});

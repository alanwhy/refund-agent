import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StatusPill } from "../components/StatusPill";

describe("StatusPill", () => {
  it("renders a customer-facing status label", () => {
    render(<StatusPill status="WAITING_APPROVAL" />);
    expect(screen.getByText("等待审批")).toBeInTheDocument();
  });

  it("renders the user-input wait state", () => {
    render(<StatusPill status="WAITING_USER" />);
    expect(screen.getByText("待补充信息")).toBeInTheDocument();
  });
});

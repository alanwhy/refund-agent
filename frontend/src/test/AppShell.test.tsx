import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { AppShell } from "../components/AppShell";

let role: "CUSTOMER" | "APPROVER" | "ADMIN" = "CUSTOMER";

vi.mock("../auth", () => ({
  useAuth: () => ({
    user: { id: "user", email: "user@example.com", role, display_name: "测试用户" },
    logout: vi.fn(),
  }),
}));

describe("AppShell", () => {
  it("shows customer navigation", () => {
    role = "CUSTOMER";
    render(<MemoryRouter><AppShell><div>content</div></AppShell></MemoryRouter>);
    expect(screen.getByRole("link", { name: "售后对话" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "我的订单" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "异常处理" })).not.toBeInTheDocument();
  });

  it("shows administrator navigation", () => {
    role = "ADMIN";
    render(<MemoryRouter><AppShell><div>content</div></AppShell></MemoryRouter>);
    expect(screen.getByRole("link", { name: "退款审批" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "全部订单" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "异常处理" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "审计记录" })).toBeInTheDocument();
  });
});

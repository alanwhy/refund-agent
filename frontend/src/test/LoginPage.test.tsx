import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { LoginPage } from "../pages/LoginPage";

const login = vi.fn();

vi.mock("../auth", () => ({ useAuth: () => ({ login }) }));

beforeEach(() => {
  login.mockReset();
  login.mockResolvedValue({ role: "CUSTOMER" });
});

afterEach(cleanup);

it("logs in with an existing customer email", async () => {
  const user = userEvent.setup();
  render(<MemoryRouter><LoginPage /></MemoryRouter>);
  const email = screen.getByLabelText(/^客户邮箱/);
  expect(email).toHaveValue("customer@example.com");
  await user.clear(email);
  await user.type(email, "other@example.com");
  await user.click(screen.getByRole("button", { name: "进入客户入口" }));
  expect(login).toHaveBeenCalledWith("other@example.com", "Demo123!");
});

it("uses the fixed administrator email outside the customer entry", async () => {
  login.mockResolvedValue({ role: "ADMIN" });
  const user = userEvent.setup();
  render(<MemoryRouter><LoginPage /></MemoryRouter>);
  await user.click(screen.getByRole("button", { name: /管理入口.*查看审批/ }));
  expect(screen.queryByLabelText(/^客户邮箱/)).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "进入管理入口" }));
  expect(login).toHaveBeenCalledWith("admin@example.com", "Demo123!");
});

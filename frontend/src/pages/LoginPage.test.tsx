import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "../shared/ui/Toast";
import { LoginPage } from "./LoginPage";

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const error = (code: string, message: string, fields: unknown[] = []) => ({ error: { code, message, fields, ctx: {} } });

function renderLogin(responses: Record<string, Response>) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => responses[url] ?? json(404, error("not_found", "Not found"))),
  );
  const router = createMemoryRouter(
    [
      { path: "/login", element: <LoginPage /> },
      { path: "/day", element: <p>Дневник водителя</p> },
    ],
    { initialEntries: ["/login"] },
  );
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <ToastProvider>
        <RouterProvider router={router} />
      </ToastProvider>
    </QueryClientProvider>,
  );
}

describe("LoginPage", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("checks the form before sending anything", async () => {
    renderLogin({ "/api/me": json(401, error("not_authenticated", "Log in first")) });
    await userEvent.click(await screen.findByRole("button", { name: "Войти" }));
    expect(await screen.findByText("Введите e-mail")).toBeTruthy();
    expect(screen.getByText("Введите пароль")).toBeTruthy();
  });

  it("shows a wrong password as one message", async () => {
    renderLogin({
      "/api/me": json(401, error("not_authenticated", "Log in first")),
      "/api/auth/login": json(401, error("invalid_credentials", "Invalid email or password")),
    });
    await userEvent.type(await screen.findByLabelText("E-mail"), "demo@example.com");
    await userEvent.type(screen.getByLabelText("Пароль"), "wrong-pass");
    await userEvent.click(screen.getByRole("button", { name: "Войти" }));
    expect((await screen.findByRole("alert")).textContent).toBe("Неверный e-mail или пароль");
  });

  it("goes to the diary after logging in", async () => {
    const profile = { id: 2, email: "demo@example.com", role: "driver", name: "Демо", default_tz: "Asia/Almaty" };
    renderLogin({
      "/api/me": json(401, error("not_authenticated", "Log in first")),
      "/api/auth/login": json(200, profile),
    });
    await userEvent.type(await screen.findByLabelText("E-mail"), "demo@example.com");
    await userEvent.type(screen.getByLabelText("Пароль"), "demo12345");
    await userEvent.click(screen.getByRole("button", { name: "Войти" }));
    expect(await screen.findByText("Дневник водителя")).toBeTruthy();
  });
});

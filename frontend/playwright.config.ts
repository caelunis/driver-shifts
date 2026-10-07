import { defineConfig, devices } from "@playwright/test";

// End-to-end tests run against the whole stack: `docker compose up -d --build` first.
// They create their own drivers with unique emails and delete them afterwards,
// so they work on a database with demo data and can be run repeatedly.
export default defineConfig({
  testDir: "e2e",
  timeout: 30_000,
  fullyParallel: false,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://127.0.0.1:8080",
    locale: "ru-RU",
    trace: "retain-on-failure",
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    { name: "phone", use: { ...devices["Pixel 7"] } },
  ],
});

import { createBrowserRouter, Navigate } from "react-router";

import { DiaryPage } from "@/pages/DiaryPage";
import { LoginPage } from "@/pages/LoginPage";
import { NotFoundPage } from "@/pages/NotFoundPage";
import { ProfilePage } from "@/pages/ProfilePage";
import { Home, RequireRole } from "@/app/guards";
import { Layout } from "@/app/Layout";

const driverDiary = async () => ({ Component: (await import("@/pages/DriverDiaryPage")).DriverDiaryPage });

export const router = createBrowserRouter([
  {
    element: <Layout />,
    children: [
      { path: "/login", element: <LoginPage /> },
      { path: "/", element: <Home /> },
      {
        element: <RequireRole role="driver" />,
        children: [
          { path: "/day/:date", element: <DiaryPage /> },
          { path: "/day", element: <DiaryPage /> },
          { path: "/profile", element: <ProfilePage /> },
        ],
      },
      {
        element: <RequireRole role="admin" />,
        children: [
          { path: "/admin", element: <Navigate to="/admin/drivers" replace /> },
          // Admin pages are loaded on demand: a driver never downloads them
          { path: "/admin/drivers", lazy: async () => ({ Component: (await import("@/pages/DriversPage")).DriversPage }) },
          { path: "/admin/drivers/:id", lazy: driverDiary },
          { path: "/admin/drivers/:id/day/:date", lazy: driverDiary },
        ],
      },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
]);

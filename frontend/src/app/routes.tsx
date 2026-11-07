import type { RouteObject } from "react-router-dom";

import { AppShell } from "@/components/AppShell";
import { adminRoutes } from "@/features/admin/routes";
import { commonRoutes } from "@/features/common/routes";
import { gradingRoutes } from "@/features/grading/routes";
import { teacherRoutes } from "@/features/teacher/routes";

// Central route table: areas export their own routes; the catch-all (404) must stay last.
const [home, ...rest] = commonRoutes;
const notFound = rest[rest.length - 1];

export const routes: RouteObject[] = [
  {
    path: "/",
    element: <AppShell />,
    children: [home, ...teacherRoutes, ...adminRoutes, ...gradingRoutes, ...rest.slice(0, -1), notFound],
  },
];

import { createBrowserRouter, Navigate } from "react-router";
import ZoroLayout from "./layouts/ZoroLayout";
import DashboardOverview from "./pages/DashboardOverview";
import SyllabusUpload from "./pages/SyllabusUpload";
import StudentEnrollment from "./pages/StudentEnrollment";
import AttendanceRecords from "./pages/AttendanceRecords";
import QueryTranscripts from "./pages/QueryTranscripts";
import Settings from "./pages/Settings";

import Login from "./pages/Login";

export const router = createBrowserRouter([
  {
    path: "/login",
    Component: Login,
  },
  {
    path: "/",
    element: <Navigate to="/dashboard" replace />,
  },
  {
    path: "/",
    Component: ZoroLayout,
    children: [
      { path: "dashboard", Component: DashboardOverview },
      { path: "syllabus", Component: SyllabusUpload },
      { path: "enrollment", Component: StudentEnrollment },
      { path: "attendance", Component: AttendanceRecords },
      { path: "queries", Component: QueryTranscripts },
      { path: "settings", Component: Settings },
    ],
  },
]);

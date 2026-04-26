import { Wifi, Bluetooth, Bell, Moon, Sun, Trash2, Edit } from "lucide-react";
import { useState } from "react";

const teachers = [
  { name: "Dr. Sarah Mitchell", email: "sarah.mitchell@school.edu", role: "Admin" },
  { name: "Prof. John Davis", email: "john.davis@school.edu", role: "Teacher" },
  { name: "Ms. Emily Chen", email: "emily.chen@school.edu", role: "Teacher" },
];

export default function Settings() {
  const [connectionMode, setConnectionMode] = useState("wifi");
  const [attendanceAlerts, setAttendanceAlerts] = useState(true);
  const [batteryAlerts, setBatteryAlerts] = useState(true);
  const [queryAlerts, setQueryAlerts] = useState(false);
  const [theme, setTheme] = useState("dark");

  return (
    <div className="space-y-6">
      {/* Notification Preferences */}
      <div className="bg-[#131827]/60 backdrop-blur-sm border border-white/10 rounded-xl p-6">
        <h3 className="text-lg mb-4">Notification Preferences</h3>
        <div className="space-y-4">
          <div className="flex items-center justify-between p-4 bg-white/5 rounded-lg">
            <div className="flex items-center gap-3">
              <Bell className="w-5 h-5 text-[#00D4FF]" />
              <div>
                <p className="text-sm">Attendance Alerts</p>
                <p className="text-xs text-[#8A9BB5]">
                  Get notified when students are absent
                </p>
              </div>
            </div>
            <button
              onClick={() => setAttendanceAlerts(!attendanceAlerts)}
              className={`relative w-14 h-7 rounded-full transition-colors ${
                attendanceAlerts ? "bg-[#1E6BFF]" : "bg-white/20"
              }`}
            >
              <div
                className={`absolute w-5 h-5 bg-white rounded-full top-1 transition-transform ${
                  attendanceAlerts ? "translate-x-8" : "translate-x-1"
                }`}
              />
            </button>
          </div>

          <div className="flex items-center justify-between p-4 bg-white/5 rounded-lg">
            <div className="flex items-center gap-3">
              <Bell className="w-5 h-5 text-[#00D4FF]" />
              <div>
                <p className="text-sm">Low Battery Alert</p>
                <p className="text-xs text-[#8A9BB5]">
                  Alert when battery falls below 20%
                </p>
              </div>
            </div>
            <button
              onClick={() => setBatteryAlerts(!batteryAlerts)}
              className={`relative w-14 h-7 rounded-full transition-colors ${
                batteryAlerts ? "bg-[#1E6BFF]" : "bg-white/20"
              }`}
            >
              <div
                className={`absolute w-5 h-5 bg-white rounded-full top-1 transition-transform ${
                  batteryAlerts ? "translate-x-8" : "translate-x-1"
                }`}
              />
            </button>
          </div>

          <div className="flex items-center justify-between p-4 bg-white/5 rounded-lg">
            <div className="flex items-center gap-3">
              <Bell className="w-5 h-5 text-[#00D4FF]" />
              <div>
                <p className="text-sm">New Query Alerts</p>
                <p className="text-xs text-[#8A9BB5]">
                  Notify for each student question
                </p>
              </div>
            </div>
            <button
              onClick={() => setQueryAlerts(!queryAlerts)}
              className={`relative w-14 h-7 rounded-full transition-colors ${
                queryAlerts ? "bg-[#1E6BFF]" : "bg-white/20"
              }`}
            >
              <div
                className={`absolute w-5 h-5 bg-white rounded-full top-1 transition-transform ${
                  queryAlerts ? "translate-x-8" : "translate-x-1"
                }`}
              />
            </button>
          </div>
        </div>
      </div>

      {/* User Management */}
      <div className="bg-[#131827]/60 backdrop-blur-sm border border-white/10 rounded-xl p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg">User Management</h3>
          <button className="px-4 py-2 bg-[#1E6BFF] hover:bg-[#1E6BFF]/80 rounded-lg text-sm transition-colors">
            Add Teacher
          </button>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-white/10">
                <th className="text-left py-3 px-3 text-sm text-[#8A9BB5]">Name</th>
                <th className="text-left py-3 px-3 text-sm text-[#8A9BB5]">Email</th>
                <th className="text-left py-3 px-3 text-sm text-[#8A9BB5]">Role</th>
                <th className="text-left py-3 px-3 text-sm text-[#8A9BB5]">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody>
              {teachers.map((teacher, index) => (
                <tr
                  key={index}
                  className={`border-b border-white/5 ${
                    index % 2 === 0 ? "bg-white/5" : ""
                  }`}
                >
                  <td className="py-3 px-3 text-sm">{teacher.name}</td>
                  <td className="py-3 px-3 text-sm text-[#8A9BB5]">
                    {teacher.email}
                  </td>
                  <td className="py-3 px-3">
                    <span
                      className={`text-xs px-3 py-1 rounded-full ${
                        teacher.role === "Admin"
                          ? "bg-[#1E6BFF]/20 text-[#00D4FF]"
                          : "bg-white/10 text-[#8A9BB5]"
                      }`}
                    >
                      {teacher.role}
                    </span>
                  </td>
                  <td className="py-3 px-3">
                    <div className="flex gap-2">
                      <button className="p-1.5 hover:bg-white/5 rounded transition-colors">
                        <Edit className="w-4 h-4 text-[#00D4FF]" />
                      </button>
                      <button className="p-1.5 hover:bg-white/5 rounded transition-colors">
                        <Trash2 className="w-4 h-4 text-[#EF4444]" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Theme and System Info */}
      <div className="grid grid-cols-2 gap-6">
        <div className="bg-[#131827]/60 backdrop-blur-sm border border-white/10 rounded-xl p-6">
          <h3 className="text-lg mb-4">Theme</h3>
          <div className="flex gap-4">
            <button
              onClick={() => setTheme("dark")}
              className={`flex-1 flex items-center justify-center gap-3 px-6 py-4 rounded-lg border transition-all ${
                theme === "dark"
                  ? "bg-[#1E6BFF]/20 border-[#1E6BFF] text-[#00D4FF]"
                  : "bg-white/5 border-white/10 text-[#8A9BB5] hover:bg-white/10"
              }`}
            >
              <Moon className="w-5 h-5" />
              <span>Dark</span>
            </button>
            <button
              onClick={() => setTheme("light")}
              className={`flex-1 flex items-center justify-center gap-3 px-6 py-4 rounded-lg border transition-all ${
                theme === "light"
                  ? "bg-[#1E6BFF]/20 border-[#1E6BFF] text-[#00D4FF]"
                  : "bg-white/5 border-white/10 text-[#8A9BB5] hover:bg-white/10"
              }`}
            >
              <Sun className="w-5 h-5" />
              <span>Light</span>
            </button>
          </div>
        </div>

        <div className="bg-[#131827]/60 backdrop-blur-sm border border-white/10 rounded-xl p-6">
          <h3 className="text-lg mb-4">System Information</h3>
          <div className="space-y-3">
            <div className="flex justify-between">
              <span className="text-sm text-[#8A9BB5]">Firmware Version</span>
              <span className="text-sm">v2.4.1</span>
            </div>
            <div className="flex justify-between">
              <span className="text-sm text-[#8A9BB5]">Last Sync</span>
              <span className="text-sm">Today, 2:30 PM</span>
            </div>
            <div className="flex justify-between">
              <span className="text-sm text-[#8A9BB5]">Model ID</span>
              <span className="text-sm text-[#00D4FF]">ZORO-EDU-v1</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

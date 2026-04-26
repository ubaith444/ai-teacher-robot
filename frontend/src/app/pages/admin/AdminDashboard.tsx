import StatCard from "../../components/StatCard";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { Users, Phone, Clock, TrendingUp, Zap } from "lucide-react";
import { LineChart, Line, BarChart, Bar, PieChart, Pie, Cell, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from "recharts";

const demoRequestsData = [
  { date: "Mar 1", requests: 12 },
  { date: "Mar 2", requests: 19 },
  { date: "Mar 3", requests: 15 },
  { date: "Mar 4", requests: 25 },
  { date: "Mar 5", requests: 22 },
  { date: "Mar 6", requests: 30 },
];

const leadDistributionData = [
  { name: "Hot Leads", value: 45, color: "#10b981" },
  { name: "Warm Leads", value: 30, color: "#f59e0b" },
  { name: "Cold Leads", value: 25, color: "#6b7280" },
];

export default function AdminDashboard() {
  return (
    <div className="p-8 space-y-8">
      <div>
        <h1 className="text-3xl mb-2">Admin Dashboard</h1>
        <p className="text-muted-foreground">Overview of your AI voice agent platform</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-6">
        <StatCard
          title="Total Demo Requests"
          value="247"
          icon={Users}
          trend="+12% from last month"
          trendUp={true}
        />
        <StatCard
          title="Active Demo Users"
          value="86"
          icon={Zap}
          trend="+8% from last week"
          trendUp={true}
        />
        <StatCard
          title="Total Demo Calls"
          value="1,432"
          icon={Phone}
          trend="+23% from last month"
          trendUp={true}
        />
        <StatCard
          title="Avg Demo Duration"
          value="2:15"
          icon={Clock}
          trend="Optimal range"
          trendUp={true}
        />
        <StatCard
          title="Hot Leads Generated"
          value="112"
          icon={TrendingUp}
          trend="+15% conversion"
          trendUp={true}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle>Demo Requests Over Time</CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={demoRequestsData}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" />
                <YAxis />
                <Tooltip />
                <Legend />
                <Line type="monotone" dataKey="requests" stroke="#1e3a8a" strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Lead Classification Distribution</CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={300}>
              <PieChart>
                <Pie
                  data={leadDistributionData}
                  cx="50%"
                  cy="50%"
                  labelLine={false}
                  label={(entry) => `${entry.name}: ${entry.value}%`}
                  outerRadius={100}
                  fill="#8884d8"
                  dataKey="value"
                >
                  {leadDistributionData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Recent Activity</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {[
              { action: "New demo request from Acme Corp", time: "5 minutes ago", type: "request" },
              { action: "Demo access generated for TechStart Inc", time: "1 hour ago", type: "access" },
              { action: "Hot lead identified: John Doe from BigCo", time: "2 hours ago", type: "lead" },
              { action: "AI configuration updated", time: "3 hours ago", type: "config" },
              { action: "New client onboarded: StartupXYZ", time: "5 hours ago", type: "client" },
            ].map((activity, index) => (
              <div key={index} className="flex items-center justify-between py-3 border-b last:border-0">
                <div>
                  <p className="text-sm">{activity.action}</p>
                  <p className="text-xs text-muted-foreground">{activity.time}</p>
                </div>
                <span className={`text-xs px-3 py-1 rounded-full ${
                  activity.type === 'lead' ? 'bg-green-100 text-green-700' :
                  activity.type === 'request' ? 'bg-blue-100 text-blue-700' :
                  activity.type === 'access' ? 'bg-purple-100 text-purple-700' :
                  'bg-gray-100 text-gray-700'
                }`}>
                  {activity.type}
                </span>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

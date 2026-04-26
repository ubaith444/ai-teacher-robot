import StatCard from "../../components/StatCard";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { Phone, Clock, TrendingUp, Flame, Wind } from "lucide-react";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from "recharts";

const callsData = [
  { time: "9 AM", calls: 3 },
  { time: "10 AM", calls: 5 },
  { time: "11 AM", calls: 7 },
  { time: "12 PM", calls: 4 },
  { time: "1 PM", calls: 6 },
  { time: "2 PM", calls: 8 },
  { time: "3 PM", calls: 5 },
];

export default function ClientDashboard() {
  return (
    <div className="p-8 space-y-8">
      <div>
        <h1 className="text-3xl mb-2">Dashboard</h1>
        <p className="text-muted-foreground">Your AI voice agent performance overview</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-6">
        <StatCard
          title="Total Calls Handled"
          value="142"
          icon={Phone}
          trend="+18% from yesterday"
          trendUp={true}
        />
        <StatCard
          title="Avg Call Duration"
          value="2:45"
          icon={Clock}
        />
        <StatCard
          title="Hot Leads"
          value="34"
          icon={Flame}
          trend="23.9% conversion"
          trendUp={true}
        />
        <StatCard
          title="Warm Leads"
          value="52"
          icon={TrendingUp}
          trend="36.6% of total"
          trendUp={true}
        />
        <StatCard
          title="Cold Leads"
          value="56"
          icon={Wind}
          trend="39.4% of total"
        />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Calls Handled Today</CardTitle>
        </CardHeader>
        <CardContent>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={callsData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="time" />
              <YAxis />
              <Tooltip />
              <Legend />
              <Bar dataKey="calls" fill="#1e3a8a" />
            </BarChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle>Recent Calls</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {[
                { caller: "+1 (555) 234-5678", duration: "3:20", lead: "Hot", time: "10 mins ago" },
                { caller: "+1 (555) 876-5432", duration: "2:15", lead: "Warm", time: "25 mins ago" },
                { caller: "+1 (555) 345-6789", duration: "1:45", lead: "Cold", time: "40 mins ago" },
                { caller: "+1 (555) 987-6543", duration: "4:10", lead: "Hot", time: "1 hour ago" },
                { caller: "+1 (555) 456-7890", duration: "2:30", lead: "Warm", time: "2 hours ago" },
              ].map((call, index) => (
                <div key={index} className="flex items-center justify-between py-3 border-b last:border-0">
                  <div>
                    <p className="text-sm font-mono">{call.caller}</p>
                    <p className="text-xs text-muted-foreground">{call.time}</p>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="text-sm text-muted-foreground">{call.duration}</span>
                    <span className={`text-xs px-3 py-1 rounded-full ${
                      call.lead === 'Hot' ? 'bg-green-100 text-green-700' :
                      call.lead === 'Warm' ? 'bg-yellow-100 text-yellow-700' :
                      'bg-gray-100 text-gray-700'
                    }`}>
                      {call.lead}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Performance Insights</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              <div className="p-4 bg-green-50 border border-green-200 rounded-lg">
                <h4 className="text-sm mb-1">High Engagement</h4>
                <p className="text-xs text-muted-foreground">Your AI agent is performing exceptionally well with a 23.9% hot lead conversion rate.</p>
              </div>
              <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg">
                <h4 className="text-sm mb-1">Peak Hours</h4>
                <p className="text-xs text-muted-foreground">Most active calling hours are between 2 PM - 4 PM. Consider optimizing for these times.</p>
              </div>
              <div className="p-4 bg-purple-50 border border-purple-200 rounded-lg">
                <h4 className="text-sm mb-1">Response Quality</h4>
                <p className="text-xs text-muted-foreground">Average customer satisfaction score: 4.7/5.0 based on conversation analysis.</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

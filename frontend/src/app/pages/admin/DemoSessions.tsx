import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { Badge } from "../../components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../../components/ui/table";

const mockSessions = [
  { id: "1", client: "Acme Corp", user: "demo_acme_1a2b", startTime: "2026-03-06 14:30", duration: "3:45", status: "Completed", callsMade: 5 },
  { id: "2", client: "TechStart Inc", user: "demo_techstart_9z8x", startTime: "2026-03-06 11:15", duration: "2:15", status: "Completed", callsMade: 3 },
  { id: "3", client: "RetailHub", user: "demo_retailhub_5c4d", startTime: "2026-03-06 09:00", duration: "1:30", status: "Completed", callsMade: 2 },
  { id: "4", client: "HealthCare Plus", user: "demo_health_7e8f", startTime: "2026-03-05 16:20", duration: "4:10", status: "Completed", callsMade: 7 },
  { id: "5", client: "BigCo", user: "demo_bigco_3g4h", startTime: "2026-03-06 15:00", duration: "Ongoing", status: "Active", callsMade: 2 },
];

export default function DemoSessions() {
  return (
    <div className="p-8 space-y-6">
      <div>
        <h1 className="text-3xl mb-2">Demo Sessions</h1>
        <p className="text-muted-foreground">Monitor active and completed demo sessions</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm text-muted-foreground">Active Sessions</p>
            <h3 className="text-3xl mt-2">1</h3>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm text-muted-foreground">Completed Today</p>
            <h3 className="text-3xl mt-2">4</h3>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm text-muted-foreground">Avg Session Duration</p>
            <h3 className="text-3xl mt-2">2:50</h3>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Demo Sessions</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Client</TableHead>
                <TableHead>Demo User</TableHead>
                <TableHead>Start Time</TableHead>
                <TableHead>Duration</TableHead>
                <TableHead>Calls Made</TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {mockSessions.map((session) => (
                <TableRow key={session.id}>
                  <TableCell>{session.client}</TableCell>
                  <TableCell className="font-mono text-sm">{session.user}</TableCell>
                  <TableCell>{session.startTime}</TableCell>
                  <TableCell>{session.duration}</TableCell>
                  <TableCell>{session.callsMade}</TableCell>
                  <TableCell>
                    <Badge className={session.status === "Active" ? "bg-green-100 text-green-700" : "bg-blue-100 text-blue-700"}>
                      {session.status}
                    </Badge>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}

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

const mockClients = [
  { id: "1", name: "Acme Corp", industry: "Technology", demoUsers: 3, totalCalls: 45, status: "Active", joinedDate: "2026-02-15" },
  { id: "2", name: "TechStart Inc", industry: "SaaS", demoUsers: 2, totalCalls: 28, status: "Active", joinedDate: "2026-02-20" },
  { id: "3", name: "RetailHub", industry: "E-commerce", demoUsers: 1, totalCalls: 12, status: "Active", joinedDate: "2026-03-01" },
  { id: "4", name: "HealthCare Plus", industry: "Healthcare", demoUsers: 4, totalCalls: 67, status: "Active", joinedDate: "2026-01-10" },
  { id: "5", name: "FinanceNow", industry: "Finance", demoUsers: 2, totalCalls: 31, status: "Inactive", joinedDate: "2026-02-01" },
];

export default function Clients() {
  return (
    <div className="p-8 space-y-6">
      <div>
        <h1 className="text-3xl mb-2">Clients</h1>
        <p className="text-muted-foreground">Manage your client accounts</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm text-muted-foreground">Total Clients</p>
            <h3 className="text-3xl mt-2">5</h3>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm text-muted-foreground">Active Clients</p>
            <h3 className="text-3xl mt-2">4</h3>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm text-muted-foreground">Total Demo Users</p>
            <h3 className="text-3xl mt-2">12</h3>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm text-muted-foreground">Total Calls</p>
            <h3 className="text-3xl mt-2">183</h3>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Client List</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Company Name</TableHead>
                <TableHead>Industry</TableHead>
                <TableHead>Demo Users</TableHead>
                <TableHead>Total Calls</TableHead>
                <TableHead>Joined Date</TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {mockClients.map((client) => (
                <TableRow key={client.id}>
                  <TableCell>{client.name}</TableCell>
                  <TableCell>{client.industry}</TableCell>
                  <TableCell>{client.demoUsers}</TableCell>
                  <TableCell>{client.totalCalls}</TableCell>
                  <TableCell>{client.joinedDate}</TableCell>
                  <TableCell>
                    <Badge className={client.status === "Active" ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-700"}>
                      {client.status}
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

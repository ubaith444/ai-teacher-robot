import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { Button } from "../../components/ui/button";
import { Badge } from "../../components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../../components/ui/table";
import { FileText } from "lucide-react";
import { useNavigate } from "react-router";

const mockCallLogs = [
  { id: "1", callerId: "+1 (555) 234-5678", duration: "3:20", leadType: "Hot", date: "2026-03-06 14:30", notes: "Interested in enterprise plan" },
  { id: "2", callerId: "+1 (555) 876-5432", duration: "2:15", leadType: "Warm", date: "2026-03-06 13:45", notes: "Requested more information" },
  { id: "3", callerId: "+1 (555) 345-6789", duration: "1:45", leadType: "Cold", date: "2026-03-06 12:00", notes: "General inquiry" },
  { id: "4", callerId: "+1 (555) 987-6543", duration: "4:10", leadType: "Hot", date: "2026-03-06 11:30", notes: "Ready to schedule demo" },
  { id: "5", callerId: "+1 (555) 456-7890", duration: "2:30", leadType: "Warm", date: "2026-03-06 10:15", notes: "Budget concerns" },
  { id: "6", callerId: "+1 (555) 654-3210", duration: "1:20", leadType: "Cold", date: "2026-03-06 09:45", notes: "Wrong number" },
  { id: "7", callerId: "+1 (555) 321-0987", duration: "3:50", leadType: "Hot", date: "2026-03-05 16:20", notes: "Very interested, follow up needed" },
  { id: "8", callerId: "+1 (555) 789-0123", duration: "2:00", leadType: "Warm", date: "2026-03-05 15:00", notes: "Asked about pricing" },
];

export default function CallLogs() {
  const navigate = useNavigate();

  const getLeadColor = (leadType: string) => {
    switch (leadType) {
      case "Hot":
        return "bg-green-100 text-green-700";
      case "Warm":
        return "bg-yellow-100 text-yellow-700";
      case "Cold":
        return "bg-gray-100 text-gray-700";
      default:
        return "bg-gray-100 text-gray-700";
    }
  };

  return (
    <div className="p-8 space-y-6">
      <div>
        <h1 className="text-3xl mb-2">Call Logs</h1>
        <p className="text-muted-foreground">View detailed records of all calls handled by your AI agent</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm text-muted-foreground">Total Calls</p>
            <h3 className="text-3xl mt-2">142</h3>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm text-muted-foreground">Hot Leads</p>
            <h3 className="text-3xl mt-2 text-green-600">34</h3>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm text-muted-foreground">Warm Leads</p>
            <h3 className="text-3xl mt-2 text-yellow-600">52</h3>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm text-muted-foreground">Cold Leads</p>
            <h3 className="text-3xl mt-2 text-gray-600">56</h3>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Recent Calls</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Caller ID</TableHead>
                <TableHead>Call Duration</TableHead>
                <TableHead>Lead Type</TableHead>
                <TableHead>Date & Time</TableHead>
                <TableHead>Notes</TableHead>
                <TableHead>Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {mockCallLogs.map((log) => (
                <TableRow key={log.id}>
                  <TableCell className="font-mono">{log.callerId}</TableCell>
                  <TableCell>{log.duration}</TableCell>
                  <TableCell>
                    <Badge className={getLeadColor(log.leadType)}>
                      {log.leadType}
                    </Badge>
                  </TableCell>
                  <TableCell>{log.date}</TableCell>
                  <TableCell className="max-w-xs truncate">{log.notes}</TableCell>
                  <TableCell>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => navigate("/client/transcripts")}
                    >
                      <FileText className="h-4 w-4 mr-2" />
                      Transcript
                    </Button>
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

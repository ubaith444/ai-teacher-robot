import { useState } from "react";
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
import { Check, X, Link as LinkIcon } from "lucide-react";
import { useNavigate } from "react-router";

interface Request {
  id: string;
  name: string;
  company: string;
  industry: string;
  useCase: string;
  requestedDate: string;
  status: "Pending" | "Approved" | "Rejected";
}

const mockRequests: Request[] = [
  {
    id: "1",
    name: "John Smith",
    company: "Acme Corp",
    industry: "Technology",
    useCase: "Customer support automation",
    requestedDate: "2026-03-05",
    status: "Pending",
  },
  {
    id: "2",
    name: "Sarah Johnson",
    company: "TechStart Inc",
    industry: "SaaS",
    useCase: "Sales qualification",
    requestedDate: "2026-03-04",
    status: "Approved",
  },
  {
    id: "3",
    name: "Mike Chen",
    company: "RetailHub",
    industry: "E-commerce",
    useCase: "Order tracking assistant",
    requestedDate: "2026-03-04",
    status: "Pending",
  },
  {
    id: "4",
    name: "Emily Davis",
    company: "HealthCare Plus",
    industry: "Healthcare",
    useCase: "Appointment scheduling",
    requestedDate: "2026-03-03",
    status: "Approved",
  },
  {
    id: "5",
    name: "Robert Wilson",
    company: "FinanceNow",
    industry: "Finance",
    useCase: "Account inquiries",
    requestedDate: "2026-03-02",
    status: "Rejected",
  },
];

export default function UserRequests() {
  const [requests, setRequests] = useState<Request[]>(mockRequests);
  const navigate = useNavigate();

  const handleStatusChange = (id: string, newStatus: "Approved" | "Rejected") => {
    setRequests(requests.map(req => 
      req.id === id ? { ...req, status: newStatus } : req
    ));
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case "Approved":
        return "bg-green-100 text-green-700";
      case "Rejected":
        return "bg-red-100 text-red-700";
      default:
        return "bg-yellow-100 text-yellow-700";
    }
  };

  return (
    <div className="p-8 space-y-6">
      <div>
        <h1 className="text-3xl mb-2">User Requests</h1>
        <p className="text-muted-foreground">Manage demo access requests from potential clients</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Demo Access Requests</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Company</TableHead>
                <TableHead>Industry</TableHead>
                <TableHead>Use Case</TableHead>
                <TableHead>Requested Date</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {requests.map((request) => (
                <TableRow key={request.id}>
                  <TableCell>{request.name}</TableCell>
                  <TableCell>{request.company}</TableCell>
                  <TableCell>{request.industry}</TableCell>
                  <TableCell className="max-w-xs truncate">{request.useCase}</TableCell>
                  <TableCell>{request.requestedDate}</TableCell>
                  <TableCell>
                    <Badge className={getStatusColor(request.status)}>
                      {request.status}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <div className="flex gap-2">
                      {request.status === "Pending" && (
                        <>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => handleStatusChange(request.id, "Approved")}
                          >
                            <Check className="h-4 w-4" />
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => handleStatusChange(request.id, "Rejected")}
                          >
                            <X className="h-4 w-4" />
                          </Button>
                        </>
                      )}
                      {request.status === "Approved" && (
                        <Button
                          size="sm"
                          onClick={() => navigate("/admin/generate-demo")}
                        >
                          <LinkIcon className="h-4 w-4 mr-2" />
                          Generate Access
                        </Button>
                      )}
                    </div>
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

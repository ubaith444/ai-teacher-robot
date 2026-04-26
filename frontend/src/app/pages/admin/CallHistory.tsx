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
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "../../components/ui/dialog";
import { FileText } from "lucide-react";

interface Call {
  id: string;
  clientName: string;
  demoUser: string;
  duration: string;
  leadClassification: "Hot" | "Warm" | "Cold";
  date: string;
  status: string;
  transcript: string;
}

const mockCalls: Call[] = [
  {
    id: "1",
    clientName: "Acme Corp",
    demoUser: "demo_acme_1a2b",
    duration: "3:45",
    leadClassification: "Hot",
    date: "2026-03-06 14:30",
    status: "Completed",
    transcript: "AI: Hello! Welcome to Tetrax AI. How can I assist you today?\n\nCustomer: Hi, I'm interested in your AI voice agent solution.\n\nAI: Excellent! Our AI voice agents can help automate customer interactions. What specific use case are you looking to solve?\n\nCustomer: We need to handle high call volumes in our support center.\n\nAI: Perfect! Our solution can handle unlimited concurrent calls with 24/7 availability. Would you like to schedule a detailed demo?",
  },
  {
    id: "2",
    clientName: "TechStart Inc",
    demoUser: "demo_techstart_9z8x",
    duration: "2:15",
    leadClassification: "Warm",
    date: "2026-03-06 11:15",
    status: "Completed",
    transcript: "AI: Hello! Thank you for trying Tetrax AI. What brings you here today?\n\nCustomer: Just exploring options for our sales team.\n\nAI: Great! Our AI can help qualify leads and schedule appointments. What's your current process?\n\nCustomer: We have a manual system. I need to discuss with my team first.\n\nAI: Absolutely! I can send you some materials to share. Would that be helpful?",
  },
  {
    id: "3",
    clientName: "RetailHub",
    demoUser: "demo_retailhub_5c4d",
    duration: "1:30",
    leadClassification: "Cold",
    date: "2026-03-06 09:00",
    status: "Completed",
    transcript: "AI: Hello! Welcome to Tetrax AI demo.\n\nCustomer: Hi, just testing this out.\n\nAI: Feel free to ask any questions about our AI voice agents.\n\nCustomer: Okay, thanks. Just looking around.\n\nAI: No problem! If you have questions later, feel free to reach out.",
  },
];

export default function CallHistory() {
  const [calls] = useState<Call[]>(mockCalls);
  const [selectedTranscript, setSelectedTranscript] = useState<string>("");

  const getLeadColor = (classification: string) => {
    switch (classification) {
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
        <h1 className="text-3xl mb-2">Call History</h1>
        <p className="text-muted-foreground">View all demo session calls and recordings</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Recent Demo Calls</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Client Name</TableHead>
                <TableHead>Demo User</TableHead>
                <TableHead>Duration</TableHead>
                <TableHead>Lead Classification</TableHead>
                <TableHead>Date</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {calls.map((call) => (
                <TableRow key={call.id}>
                  <TableCell>{call.clientName}</TableCell>
                  <TableCell className="font-mono text-sm">{call.demoUser}</TableCell>
                  <TableCell>{call.duration}</TableCell>
                  <TableCell>
                    <Badge className={getLeadColor(call.leadClassification)}>
                      {call.leadClassification}
                    </Badge>
                  </TableCell>
                  <TableCell>{call.date}</TableCell>
                  <TableCell>{call.status}</TableCell>
                  <TableCell>
                    <Dialog>
                      <DialogTrigger asChild>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => setSelectedTranscript(call.transcript)}
                        >
                          <FileText className="h-4 w-4 mr-2" />
                          View Transcript
                        </Button>
                      </DialogTrigger>
                      <DialogContent className="max-w-2xl max-h-[600px] overflow-y-auto">
                        <DialogHeader>
                          <DialogTitle>Call Transcript - {call.clientName}</DialogTitle>
                        </DialogHeader>
                        <div className="space-y-4">
                          <div className="grid grid-cols-3 gap-4 text-sm">
                            <div>
                              <p className="text-muted-foreground">Duration</p>
                              <p>{call.duration}</p>
                            </div>
                            <div>
                              <p className="text-muted-foreground">Date</p>
                              <p>{call.date}</p>
                            </div>
                            <div>
                              <p className="text-muted-foreground">Lead Score</p>
                              <Badge className={getLeadColor(call.leadClassification)}>
                                {call.leadClassification}
                              </Badge>
                            </div>
                          </div>
                          <div className="border-t pt-4">
                            <div className="whitespace-pre-wrap text-sm leading-relaxed">
                              {selectedTranscript.split('\n').map((line, index) => (
                                <p key={index} className={line.startsWith('AI:') ? 'text-primary mb-2' : 'mb-2'}>
                                  {line}
                                </p>
                              ))}
                            </div>
                          </div>
                        </div>
                      </DialogContent>
                    </Dialog>
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

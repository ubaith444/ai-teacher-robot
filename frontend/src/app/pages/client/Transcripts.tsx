import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Bot, User } from "lucide-react";

interface Message {
  speaker: "AI" | "Customer";
  text: string;
  timestamp: string;
}

interface Transcript {
  id: string;
  callerId: string;
  date: string;
  duration: string;
  leadType: "Hot" | "Warm" | "Cold";
  messages: Message[];
}

const mockTranscripts: Transcript[] = [
  {
    id: "1",
    callerId: "+1 (555) 234-5678",
    date: "2026-03-06 14:30",
    duration: "3:20",
    leadType: "Hot",
    messages: [
      { speaker: "AI", text: "Hello! Welcome to Tetrax AI. I'm your AI assistant. How can I help you today?", timestamp: "00:00" },
      { speaker: "Customer", text: "Hi, I'm interested in learning more about your AI voice agent solution.", timestamp: "00:08" },
      { speaker: "AI", text: "Excellent! I'd be happy to tell you about our AI voice agents. They can help automate customer interactions with natural, intelligent conversations. What specific use case are you looking to solve?", timestamp: "00:15" },
      { speaker: "Customer", text: "We have a high volume of customer support calls and need to scale our operations without hiring more staff.", timestamp: "00:30" },
      { speaker: "AI", text: "That's a perfect use case for our solution. Our AI voice agents can handle unlimited concurrent calls, providing 24/7 availability with consistent quality. We typically see companies reduce their support costs by 60% while improving response times. Would you like to know more about the implementation process?", timestamp: "00:45" },
      { speaker: "Customer", text: "Yes, that sounds great! How long does it take to get set up?", timestamp: "01:05" },
      { speaker: "AI", text: "The setup process is quite straightforward. Most clients are up and running within 2-3 weeks. This includes customizing the AI to understand your specific products, services, and common customer questions. We provide full training and ongoing support. Would you like to schedule a detailed demo with our team?", timestamp: "01:15" },
      { speaker: "Customer", text: "Absolutely! Can you send me pricing information as well?", timestamp: "01:40" },
      { speaker: "AI", text: "Perfect! I'll make sure our team sends you detailed pricing information and schedules a demo at a time that works for you. Can I get your email address?", timestamp: "01:48" },
      { speaker: "Customer", text: "Sure, it's john@acmecorp.com", timestamp: "02:00" },
      { speaker: "AI", text: "Great! I've recorded that. You should receive an email within the next hour with pricing details and available demo times. Is there anything else you'd like to know right now?", timestamp: "02:08" },
      { speaker: "Customer", text: "No, that covers everything. Thank you!", timestamp: "02:25" },
      { speaker: "AI", text: "You're welcome! We're excited to show you what Tetrax AI can do for your business. Have a great day!", timestamp: "02:30" },
    ],
  },
  {
    id: "2",
    callerId: "+1 (555) 876-5432",
    date: "2026-03-06 13:45",
    duration: "2:15",
    leadType: "Warm",
    messages: [
      { speaker: "AI", text: "Hello! Thank you for calling Tetrax AI. How may I assist you today?", timestamp: "00:00" },
      { speaker: "Customer", text: "Hi, I'm just exploring different options for automating our sales process.", timestamp: "00:05" },
      { speaker: "AI", text: "Great! Our AI voice agents excel at sales automation. They can qualify leads, answer product questions, and schedule appointments with your sales team. What does your current sales process look like?", timestamp: "00:15" },
      { speaker: "Customer", text: "Right now everything is manual. We have a small team that makes outbound calls and handles incoming inquiries.", timestamp: "00:30" },
      { speaker: "AI", text: "I understand. Our solution can complement your team by handling initial lead qualification and routine inquiries, allowing your sales team to focus on high-value conversations. This typically increases conversion rates by 25-40%. Would you like to learn more about how it works?", timestamp: "00:45" },
      { speaker: "Customer", text: "It sounds interesting, but I need to discuss this with my team first before moving forward.", timestamp: "01:05" },
      { speaker: "AI", text: "Absolutely, that makes perfect sense. I can send you some materials that you can share with your team, including case studies and ROI calculations. Would that be helpful?", timestamp: "01:15" },
      { speaker: "Customer", text: "Yes, that would be great. Send it to sarah@company.com", timestamp: "01:30" },
      { speaker: "AI", text: "Perfect! I'll send that information right away. Feel free to reach out when you're ready to discuss further. Is there anything else I can help you with today?", timestamp: "01:40" },
      { speaker: "Customer", text: "No, that's all for now. Thank you!", timestamp: "02:00" },
      { speaker: "AI", text: "You're welcome! Have a wonderful day!", timestamp: "02:05" },
    ],
  },
];

export default function Transcripts() {
  const [selectedTranscript, setSelectedTranscript] = useState<Transcript | null>(mockTranscripts[0]);

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
        <h1 className="text-3xl mb-2">Transcripts</h1>
        <p className="text-muted-foreground">View detailed conversation transcripts</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Recent Conversations</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {mockTranscripts.map((transcript) => (
              <Button
                key={transcript.id}
                variant={selectedTranscript?.id === transcript.id ? "default" : "outline"}
                className="w-full justify-start h-auto py-3"
                onClick={() => setSelectedTranscript(transcript)}
              >
                <div className="text-left w-full">
                  <div className="flex items-center justify-between mb-1">
                    <span className="font-mono text-sm">{transcript.callerId}</span>
                    <Badge className={getLeadColor(transcript.leadType)} style={{ fontSize: '10px', padding: '2px 6px' }}>
                      {transcript.leadType}
                    </Badge>
                  </div>
                  <p className="text-xs text-muted-foreground">{transcript.date}</p>
                  <p className="text-xs text-muted-foreground">Duration: {transcript.duration}</p>
                </div>
              </Button>
            ))}
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle>Conversation Transcript</CardTitle>
                {selectedTranscript && (
                  <p className="text-sm text-muted-foreground mt-1">
                    {selectedTranscript.callerId} • {selectedTranscript.date}
                  </p>
                )}
              </div>
              {selectedTranscript && (
                <div className="flex items-center gap-2">
                  <Badge className={getLeadColor(selectedTranscript.leadType)}>
                    {selectedTranscript.leadType} Lead
                  </Badge>
                  <span className="text-sm text-muted-foreground">{selectedTranscript.duration}</span>
                </div>
              )}
            </div>
          </CardHeader>
          <CardContent>
            {selectedTranscript ? (
              <div className="space-y-4 max-h-[600px] overflow-y-auto pr-4">
                {selectedTranscript.messages.map((message, index) => (
                  <div
                    key={index}
                    className={`flex gap-3 ${message.speaker === "Customer" ? "flex-row-reverse" : ""}`}
                  >
                    <div className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center ${
                      message.speaker === "AI" ? "bg-primary/10" : "bg-accent/30"
                    }`}>
                      {message.speaker === "AI" ? (
                        <Bot className="h-4 w-4 text-primary" />
                      ) : (
                        <User className="h-4 w-4 text-accent-foreground" />
                      )}
                    </div>
                    <div className={`flex-1 ${message.speaker === "Customer" ? "text-right" : ""}`}>
                      <div className="flex items-center gap-2 mb-1">
                        {message.speaker === "Customer" && <span className="text-xs text-muted-foreground">{message.timestamp}</span>}
                        <span className="text-sm">{message.speaker}</span>
                        {message.speaker === "AI" && <span className="text-xs text-muted-foreground">{message.timestamp}</span>}
                      </div>
                      <div className={`inline-block max-w-[85%] p-3 rounded-lg ${
                        message.speaker === "AI"
                          ? "bg-primary/5 text-left"
                          : "bg-accent/20 text-left"
                      }`}>
                        <p className="text-sm leading-relaxed">{message.text}</p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-12 text-muted-foreground">
                <p>Select a conversation to view the transcript</p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

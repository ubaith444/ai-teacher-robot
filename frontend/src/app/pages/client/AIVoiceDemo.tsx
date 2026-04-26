import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { Button } from "../../components/ui/button";
import { Badge } from "../../components/ui/badge";
import { Play, Square, Phone, TrendingUp, MessageSquare, Clock } from "lucide-react";
import { Progress } from "../../components/ui/progress";

export default function AIVoiceDemo() {
  const [demoActive, setDemoActive] = useState(false);
  const [callActive, setCallActive] = useState(false);
  const [callDuration, setCallDuration] = useState(0);
  const [currentLead, setCurrentLead] = useState<"Hot" | "Warm" | "Cold" | null>(null);
  const [customerIntent, setCustomerIntent] = useState("");
  const [conversationSummary, setConversationSummary] = useState("");

  useEffect(() => {
    let interval: NodeJS.Timeout;
    if (callActive) {
      interval = setInterval(() => {
        setCallDuration((prev) => prev + 1);
      }, 1000);
    }
    return () => clearInterval(interval);
  }, [callActive]);

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, "0")}`;
  };

  const handleStartDemo = () => {
    setDemoActive(true);
  };

  const handleEndDemo = () => {
    setDemoActive(false);
    setCallActive(false);
    setCallDuration(0);
    setCurrentLead(null);
    setCustomerIntent("");
    setConversationSummary("");
  };

  const simulateIncomingCall = () => {
    setCallActive(true);
    setCallDuration(0);
    
    // Simulate AI analysis after a few seconds
    setTimeout(() => {
      const leads: ("Hot" | "Warm" | "Cold")[] = ["Hot", "Warm", "Cold"];
      setCurrentLead(leads[Math.floor(Math.random() * leads.length)]);
      
      const intents = [
        "Interested in product demo",
        "Price inquiry",
        "Technical support needed",
        "General information",
        "Partnership opportunity"
      ];
      setCustomerIntent(intents[Math.floor(Math.random() * intents.length)]);
      
      setConversationSummary("Customer is asking about AI voice agent capabilities and pricing options. Showing strong interest in automation features.");
    }, 3000);
  };

  const endCall = () => {
    setCallActive(false);
    setCallDuration(0);
  };

  return (
    <div className="p-8 space-y-6">
      <div>
        <h1 className="text-3xl mb-2">AI Voice Demo</h1>
        <p className="text-muted-foreground">Test and interact with your AI voice agent</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Demo Control Panel</CardTitle>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="flex items-center justify-between p-6 bg-muted/30 rounded-lg">
              <div>
                <p className="text-sm text-muted-foreground mb-1">AI Agent Status</p>
                <div className="flex items-center gap-2">
                  <div className={`w-3 h-3 rounded-full ${demoActive ? 'bg-green-500 animate-pulse' : 'bg-gray-400'}`} />
                  <span className="text-lg">{demoActive ? "Online" : "Offline"}</span>
                </div>
              </div>
              <div className="flex gap-3">
                {!demoActive ? (
                  <Button onClick={handleStartDemo} size="lg" className="gap-2">
                    <Play className="h-5 w-5" />
                    Start Demo
                  </Button>
                ) : (
                  <Button onClick={handleEndDemo} size="lg" variant="destructive" className="gap-2">
                    <Square className="h-5 w-5" />
                    End Demo
                  </Button>
                )}
              </div>
            </div>

            {demoActive && (
              <div className="space-y-4">
                <div className="border-2 border-dashed border-primary/30 rounded-lg p-8 text-center">
                  {!callActive ? (
                    <div className="space-y-4">
                      <Phone className="h-12 w-12 mx-auto text-muted-foreground" />
                      <div>
                        <h3 className="text-lg mb-2">Waiting for incoming call...</h3>
                        <p className="text-sm text-muted-foreground mb-4">
                          The AI agent is ready to handle customer calls
                        </p>
                        <Button onClick={simulateIncomingCall} variant="outline">
                          Simulate Incoming Call
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <div className="space-y-4">
                      <div className="flex items-center justify-center gap-2">
                        <div className="w-4 h-4 rounded-full bg-green-500 animate-pulse" />
                        <h3 className="text-lg">Call In Progress</h3>
                      </div>
                      <div className="flex items-center justify-center gap-2 text-3xl">
                        <Clock className="h-8 w-8" />
                        {formatTime(callDuration)}
                      </div>
                      <Button onClick={endCall} variant="destructive">
                        End Call
                      </Button>
                    </div>
                  )}
                </div>

                {callActive && (
                  <Card className="bg-accent/10">
                    <CardHeader>
                      <CardTitle className="text-lg">Live Call Information</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <p className="text-sm text-muted-foreground mb-1">Call Status</p>
                          <Badge className="bg-green-100 text-green-700">Connected</Badge>
                        </div>
                        <div>
                          <p className="text-sm text-muted-foreground mb-1">Caller ID</p>
                          <p className="font-mono text-sm">+1 (555) 123-4567</p>
                        </div>
                      </div>
                      <div>
                        <p className="text-sm text-muted-foreground mb-2">Conversation Progress</p>
                        <Progress value={Math.min((callDuration / 120) * 100, 100)} />
                      </div>
                    </CardContent>
                  </Card>
                )}
              </div>
            )}
          </CardContent>
        </Card>

        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Live Call Insights</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <div className="flex items-center gap-2 mb-2">
                  <TrendingUp className="h-4 w-4 text-muted-foreground" />
                  <p className="text-sm">Lead Classification</p>
                </div>
                {currentLead ? (
                  <Badge className={
                    currentLead === 'Hot' ? 'bg-green-100 text-green-700' :
                    currentLead === 'Warm' ? 'bg-yellow-100 text-yellow-700' :
                    'bg-gray-100 text-gray-700'
                  }>
                    {currentLead} Lead
                  </Badge>
                ) : (
                  <p className="text-sm text-muted-foreground">No active call</p>
                )}
              </div>

              <div>
                <div className="flex items-center gap-2 mb-2">
                  <MessageSquare className="h-4 w-4 text-muted-foreground" />
                  <p className="text-sm">Customer Intent</p>
                </div>
                {customerIntent ? (
                  <p className="text-sm">{customerIntent}</p>
                ) : (
                  <p className="text-sm text-muted-foreground">Analyzing...</p>
                )}
              </div>

              <div>
                <div className="flex items-center gap-2 mb-2">
                  <Phone className="h-4 w-4 text-muted-foreground" />
                  <p className="text-sm">Conversation Summary</p>
                </div>
                {conversationSummary ? (
                  <p className="text-sm">{conversationSummary}</p>
                ) : (
                  <p className="text-sm text-muted-foreground">No data available</p>
                )}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-lg">Demo Statistics</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex justify-between">
                <span className="text-sm text-muted-foreground">Calls Today</span>
                <span className="text-sm">12</span>
              </div>
              <div className="flex justify-between">
                <span className="text-sm text-muted-foreground">Avg Duration</span>
                <span className="text-sm">2:35</span>
              </div>
              <div className="flex justify-between">
                <span className="text-sm text-muted-foreground">Hot Leads</span>
                <span className="text-sm">4</span>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

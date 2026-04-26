import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";
import { Button } from "../../components/ui/button";
import { Textarea } from "../../components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../../components/ui/select";
import { Copy, RefreshCw } from "lucide-react";
import { toast } from "sonner";

export default function GenerateDemoAccess() {
  const [formData, setFormData] = useState({
    clientName: "",
    companyName: "",
    industry: "",
    agentBehavior: "",
    productDescription: "",
    salesPoints: "",
    targetCustomers: "",
    demoDuration: "2",
  });

  const [generatedAccess, setGeneratedAccess] = useState({
    username: "",
    password: "",
    demoLink: "",
  });

  const generateRandomString = (length: number) => {
    const chars = "abcdefghijklmnopqrstuvwxyz0123456789";
    let result = "";
    for (let i = 0; i < length; i++) {
      result += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    return result;
  };

  const handleGenerateUsername = () => {
    const username = `demo_${formData.companyName.toLowerCase().replace(/\s+/g, "_")}_${generateRandomString(4)}`;
    setGeneratedAccess({ ...generatedAccess, username });
  };

  const handleGeneratePassword = () => {
    const password = generateRandomString(12);
    setGeneratedAccess({ ...generatedAccess, password });
  };

  const handleGenerateDemoLink = () => {
    if (!generatedAccess.username || !generatedAccess.password) {
      toast.error("Please generate username and password first");
      return;
    }
    const demoLink = `https://demo.tetrax.ai/client?token=${generateRandomString(32)}`;
    setGeneratedAccess({ ...generatedAccess, demoLink });
    toast.success("Demo access generated successfully!");
  };

  const copyToClipboard = (text: string, label: string) => {
    navigator.clipboard.writeText(text);
    toast.success(`${label} copied to clipboard!`);
  };

  return (
    <div className="p-8 space-y-6">
      <div>
        <h1 className="text-3xl mb-2">Generate Demo Access</h1>
        <p className="text-muted-foreground">Create demo credentials and access links for clients</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle>Client Information</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="clientName">Client Name</Label>
              <Input
                id="clientName"
                value={formData.clientName}
                onChange={(e) => setFormData({ ...formData, clientName: e.target.value })}
                placeholder="John Doe"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="companyName">Company Name</Label>
              <Input
                id="companyName"
                value={formData.companyName}
                onChange={(e) => setFormData({ ...formData, companyName: e.target.value })}
                placeholder="Acme Corp"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="industry">Industry</Label>
              <Select value={formData.industry} onValueChange={(value) => setFormData({ ...formData, industry: value })}>
                <SelectTrigger>
                  <SelectValue placeholder="Select industry" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="technology">Technology</SelectItem>
                  <SelectItem value="saas">SaaS</SelectItem>
                  <SelectItem value="ecommerce">E-commerce</SelectItem>
                  <SelectItem value="healthcare">Healthcare</SelectItem>
                  <SelectItem value="finance">Finance</SelectItem>
                  <SelectItem value="education">Education</SelectItem>
                  <SelectItem value="retail">Retail</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="agentBehavior">AI Agent Behavior</Label>
              <Select value={formData.agentBehavior} onValueChange={(value) => setFormData({ ...formData, agentBehavior: value })}>
                <SelectTrigger>
                  <SelectValue placeholder="Select behavior" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="professional">Professional & Formal</SelectItem>
                  <SelectItem value="friendly">Friendly & Casual</SelectItem>
                  <SelectItem value="consultative">Consultative</SelectItem>
                  <SelectItem value="technical">Technical Expert</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label htmlFor="demoDuration">Demo Duration (Minutes)</Label>
              <Input
                id="demoDuration"
                type="number"
                value={formData.demoDuration}
                onChange={(e) => setFormData({ ...formData, demoDuration: e.target.value })}
              />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>AI Configuration</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="productDescription">Product / Service Description</Label>
              <Textarea
                id="productDescription"
                value={formData.productDescription}
                onChange={(e) => setFormData({ ...formData, productDescription: e.target.value })}
                placeholder="Describe the product or service..."
                rows={3}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="salesPoints">Key Sales Points</Label>
              <Textarea
                id="salesPoints"
                value={formData.salesPoints}
                onChange={(e) => setFormData({ ...formData, salesPoints: e.target.value })}
                placeholder="Enter key benefits and features..."
                rows={3}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="targetCustomers">Target Customers</Label>
              <Textarea
                id="targetCustomers"
                value={formData.targetCustomers}
                onChange={(e) => setFormData({ ...formData, targetCustomers: e.target.value })}
                placeholder="Describe ideal customer profile..."
                rows={3}
              />
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Generate Access Credentials</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="space-y-2">
              <Label>Username</Label>
              <div className="flex gap-2">
                <Input value={generatedAccess.username} readOnly placeholder="Generate username" />
                <Button variant="outline" onClick={handleGenerateUsername}>
                  <RefreshCw className="h-4 w-4" />
                </Button>
              </div>
            </div>

            <div className="space-y-2">
              <Label>Password</Label>
              <div className="flex gap-2">
                <Input value={generatedAccess.password} readOnly placeholder="Generate password" />
                <Button variant="outline" onClick={handleGeneratePassword}>
                  <RefreshCw className="h-4 w-4" />
                </Button>
              </div>
            </div>

            <div className="space-y-2">
              <Label>&nbsp;</Label>
              <Button className="w-full" onClick={handleGenerateDemoLink}>
                Generate Demo Link
              </Button>
            </div>
          </div>

          {generatedAccess.demoLink && (
            <Card className="bg-accent/10 border-2 border-accent">
              <CardContent className="pt-6 space-y-3">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm text-muted-foreground">Username</p>
                    <p className="font-mono">{generatedAccess.username}</p>
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => copyToClipboard(generatedAccess.username, "Username")}
                  >
                    <Copy className="h-4 w-4" />
                  </Button>
                </div>

                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm text-muted-foreground">Password</p>
                    <p className="font-mono">{generatedAccess.password}</p>
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => copyToClipboard(generatedAccess.password, "Password")}
                  >
                    <Copy className="h-4 w-4" />
                  </Button>
                </div>

                <div className="flex items-center justify-between">
                  <div className="flex-1 mr-4">
                    <p className="text-sm text-muted-foreground">Demo Access Link</p>
                    <p className="font-mono text-sm break-all">{generatedAccess.demoLink}</p>
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => copyToClipboard(generatedAccess.demoLink, "Demo link")}
                  >
                    <Copy className="h-4 w-4" />
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

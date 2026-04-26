import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { Label } from "../../components/ui/label";
import { Textarea } from "../../components/ui/textarea";
import { Button } from "../../components/ui/button";
import { Save } from "lucide-react";
import { toast } from "sonner";

export default function AIConfiguration() {
  const [config, setConfig] = useState({
    businessDescription: "Tetrax AI is a cutting-edge AI voice agent platform that helps businesses automate customer interactions with natural, intelligent conversations.",
    productsServices: "AI-powered voice agents for sales, customer support, and lead qualification. Features include real-time sentiment analysis, automatic call transcription, and lead scoring.",
    salesScript: "Welcome to [Company Name]! I'm an AI assistant here to help you learn about our products and services. How can I assist you today?",
    keyBenefits: "• 24/7 availability\n• Instant response times\n• Consistent quality\n• Scalable operations\n• Cost-effective solution\n• Natural conversations",
    commonQuestions: "Q: What industries do you serve?\nA: We serve technology, healthcare, finance, e-commerce, and many other industries.\n\nQ: How does the AI understand different accents?\nA: Our AI is trained on diverse datasets and uses advanced natural language processing.\n\nQ: Can I customize the AI's responses?\nA: Yes, you have full control over the AI's behavior and responses.",
    objectionHandling: "Price Concern: 'I understand budget is important. Our solution actually reduces costs by up to 60% compared to traditional methods.'\n\nTiming: 'I appreciate that. When would be a better time? We can schedule a quick 15-minute demo at your convenience.'\n\nNot Interested: 'I understand. May I ask what your current process is for handling customer calls? Perhaps I can share something that might be relevant.'",
  });

  const handleSave = () => {
    toast.success("AI configuration saved successfully!");
  };

  return (
    <div className="p-8 space-y-6">
      <div>
        <h1 className="text-3xl mb-2">AI Configuration</h1>
        <p className="text-muted-foreground">Configure the AI agent's knowledge base and behavior</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Business Information</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="businessDescription">Business Description</Label>
            <Textarea
              id="businessDescription"
              value={config.businessDescription}
              onChange={(e) => setConfig({ ...config, businessDescription: e.target.value })}
              rows={3}
              placeholder="Describe your business..."
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="productsServices">Products or Services</Label>
            <Textarea
              id="productsServices"
              value={config.productsServices}
              onChange={(e) => setConfig({ ...config, productsServices: e.target.value })}
              rows={4}
              placeholder="List your products and services..."
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Conversation Scripts</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="salesScript">Sales Script</Label>
            <Textarea
              id="salesScript"
              value={config.salesScript}
              onChange={(e) => setConfig({ ...config, salesScript: e.target.value })}
              rows={4}
              placeholder="Enter the opening script..."
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="keyBenefits">Key Benefits</Label>
            <Textarea
              id="keyBenefits"
              value={config.keyBenefits}
              onChange={(e) => setConfig({ ...config, keyBenefits: e.target.value })}
              rows={6}
              placeholder="List key benefits and features..."
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Knowledge Base</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="commonQuestions">Common Customer Questions</Label>
            <Textarea
              id="commonQuestions"
              value={config.commonQuestions}
              onChange={(e) => setConfig({ ...config, commonQuestions: e.target.value })}
              rows={8}
              placeholder="Enter frequently asked questions and answers..."
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="objectionHandling">Objection Handling Responses</Label>
            <Textarea
              id="objectionHandling"
              value={config.objectionHandling}
              onChange={(e) => setConfig({ ...config, objectionHandling: e.target.value })}
              rows={8}
              placeholder="Enter responses to common objections..."
            />
          </div>
        </CardContent>
      </Card>

      <div className="flex justify-end">
        <Button onClick={handleSave} size="lg">
          <Save className="h-5 w-5 mr-2" />
          Save Configuration
        </Button>
      </div>
    </div>
  );
}

import { useState } from "react";
import { useNavigate } from "react-router";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../components/ui/card";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Button } from "../components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { Bot, Shield, User } from "lucide-react";
import { authApi } from "../services/api";
import { toast } from "sonner";

export default function Login() {
  const navigate = useNavigate();
  const [credentials, setCredentials] = useState({ username: "", password: "" });
  const [loading, setLoading] = useState(false);

  const handleLogin = async (role: "admin" | "client") => {
    if (!credentials.username || !credentials.password) {
      toast.error("Please enter both username and password");
      return;
    }

    setLoading(true);
    try {
      const data = await authApi.login(credentials);
      localStorage.setItem("zoro_token", data.access_token);
      toast.success("Login successful!");
      
      if (role === "admin") {
        navigate("/admin");
      } else {
        navigate("/client");
      }
    } catch (err: any) {
      toast.error(err.message || "Authentication failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#0A0F1D] text-white flex items-center justify-center p-4 relative overflow-hidden">
      {/* Background Glow */}
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[500px] h-[500px] bg-[#1E6BFF]/20 rounded-full blur-[120px] pointer-events-none" />
      
      <div className="w-full max-w-md relative z-10">
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-20 h-20 bg-gradient-to-br from-[#1E6BFF] to-[#00D4FF] rounded-2xl mb-6 shadow-lg shadow-[#1E6BFF]/20 animate-pulse">
            <Bot className="h-10 w-10 text-white" />
          </div>
          <h1 className="text-5xl font-bold tracking-tight mb-2 bg-gradient-to-r from-white to-[#8A9BB5] bg-clip-text text-transparent">
            ZORO
          </h1>
          <p className="text-[#8A9BB5] text-lg">AI Classroom Orchestrator</p>
        </div>

        <Card className="bg-[#131827]/80 backdrop-blur-xl border-white/10 shadow-2xl">
          <CardHeader>
            <CardTitle className="text-2xl text-center">Sign In</CardTitle>
            <CardDescription className="text-center text-[#8A9BB5]">
              Secure access to classroom controls
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Tabs defaultValue="admin" className="w-full">
              <TabsList className="grid w-full grid-cols-2 bg-white/5 p-1 mb-6">
                <TabsTrigger 
                  value="admin" 
                  className="data-[state=active]:bg-[#1E6BFF] data-[state=active]:text-white transition-all"
                >
                  <Shield className="w-4 h-4 mr-2" />
                  Admin
                </TabsTrigger>
                <TabsTrigger 
                  value="client"
                  className="data-[state=active]:bg-[#1E6BFF] data-[state=active]:text-white transition-all"
                >
                  <User className="w-4 h-4 mr-2" />
                  Student
                </TabsTrigger>
              </TabsList>
              
              <div className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="username" className="text-sm font-medium text-[#8A9BB5]">Username</Label>
                  <Input
                    id="username"
                    type="text"
                    placeholder="admin_zoro"
                    className="bg-white/5 border-white/10 focus:border-[#1E6BFF] transition-colors"
                    value={credentials.username}
                    onChange={(e) => setCredentials({ ...credentials, username: e.target.value })}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="password" title="Enter your secure password" className="text-sm font-medium text-[#8A9BB5]">Password</Label>
                  <Input
                    id="password"
                    type="password"
                    placeholder="••••••••"
                    className="bg-white/5 border-white/10 focus:border-[#1E6BFF] transition-colors"
                    value={credentials.password}
                    onChange={(e) => setCredentials({ ...credentials, password: e.target.value })}
                  />
                </div>
                
                <TabsContent value="admin" className="mt-6 m-0">
                  <Button 
                    className="w-full h-12 bg-[#1E6BFF] hover:bg-[#1E6BFF]/80 text-white font-semibold transition-all disabled:opacity-50" 
                    onClick={() => handleLogin("admin")}
                    disabled={loading}
                  >
                    {loading ? "Authenticating..." : "Sign In as Admin"}
                  </Button>
                </TabsContent>
                
                <TabsContent value="client" className="mt-6 m-0">
                  <Button 
                    className="w-full h-12 bg-gradient-to-r from-[#1E6BFF] to-[#00D4FF] hover:opacity-90 text-white font-semibold transition-all disabled:opacity-50" 
                    onClick={() => handleLogin("client")}
                    disabled={loading}
                  >
                    {loading ? "Authenticating..." : "Sign In as Student"}
                  </Button>
                </TabsContent>
              </div>
            </Tabs>
          </CardContent>
        </Card>
        
        <p className="mt-8 text-center text-sm text-[#8A9BB5]">
          Powered by Zoro AI • v2.0.0
        </p>
      </div>
    </div>
  );
}

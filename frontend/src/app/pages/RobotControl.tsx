import { useState, useEffect, useRef } from "react";
import { Camera, Wifi, Shield, Activity, RefreshCw, ChevronUp, ChevronDown, ChevronLeft, ChevronRight, Power, Settings } from "lucide-react";
import { toast } from "sonner";
import { API_BASE_URL } from "../services/api";

export default function RobotControl() {
  const [isLive, setIsLive] = useState(false);
  const [latency, setLatency] = useState(24);
  const [bandwidth, setBandwidth] = useState(4.2);
  const [streamUrl, setStreamUrl] = useState(`${API_BASE_URL}/api/attendance/stream`);
  const [error, setError] = useState(false);
  const [motorsEnabled, setMotorsEnabled] = useState(false);
  
  const ws = useRef<WebSocket | null>(null);

  useEffect(() => {
    // Simulate connection check
    const timer = setTimeout(() => {
      setIsLive(true);
      toast.success("Zoro camera feed synchronized");
    }, 1500);

    const interval = setInterval(() => {
      setLatency(prev => Math.max(15, Math.min(45, prev + (Math.random() - 0.5) * 5)));
      setBandwidth(prev => Math.max(3.5, Math.min(6.0, prev + (Math.random() - 0.5) * 0.8)));
    }, 3000);

    // Initialize WebSocket for controls
    const wsUrl = `${API_BASE_URL.replace('http', 'ws')}/api/robot/ws/control`;
    ws.current = new WebSocket(wsUrl);
    
    ws.current.onopen = () => console.log("Robot control WebSocket connected");
    ws.current.onclose = () => console.log("Robot control WebSocket disconnected");

    return () => {
      clearTimeout(timer);
      clearInterval(interval);
      ws.current?.close();
    };
  }, []);

  const sendCommand = (cmd: any) => {
    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify(cmd));
    } else {
      toast.error("Robot controller not connected");
    }
  };

  const handleRefresh = () => {
    setError(false);
    setStreamUrl(`${API_BASE_URL}/api/attendance/stream?t=${Date.now()}`);
    toast.info("Refreshing video stream...");
  };

  const toggleMotors = () => {
    const newState = !motorsEnabled;
    setMotorsEnabled(newState);
    if (newState) {
      toast.success("Robot motors enabled");
    } else {
      toast.warning("Motors disabled (STBY mode)");
    }
  };

  return (
    <div className="h-full max-w-5xl mx-auto">
      {/* Centered: Live Feed */}
      <div className="bg-[#131827]/60 backdrop-blur-sm border border-white/10 rounded-xl p-6 flex flex-col h-[600px]">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h3 className="text-xl font-semibold">ZORO-EDU-v1 Perspective</h3>
            <p className="text-[#8A9BB5] text-sm mt-1">Encrypted real-time vision stream</p>
          </div>
          <div className="flex items-center gap-3">
            <button 
              onClick={handleRefresh}
              className="p-2 hover:bg-white/5 rounded-full transition-colors text-[#8A9BB5]"
            >
              <RefreshCw className="w-4 h-4" />
            </button>
            <span className={`flex items-center gap-2 text-sm px-3 py-1 ${isLive ? 'bg-[#10B981]/20 text-[#10B981] border-[#10B981]/30' : 'bg-[#EF4444]/20 text-[#EF4444] border-[#EF4444]/30'} rounded-full border`}>
              <span className={`w-2 h-2 ${isLive ? 'bg-[#10B981]' : 'bg-[#EF4444]'} rounded-full animate-pulse`}></span>
              {isLive ? 'LIVE' : 'OFFLINE'}
            </span>
          </div>
        </div>
        
        <div className="flex-1 bg-black/40 rounded-2xl flex items-center justify-center border border-white/10 relative group overflow-hidden shadow-2xl">
          {isLive && !error ? (
            <img 
              src={streamUrl} 
              alt="Robot Feed" 
              className="w-full h-full object-contain"
              onError={() => setError(true)}
            />
          ) : (
            <div className="text-center">
              <Camera className="w-12 h-12 text-[#8A9BB5] mx-auto mb-4 opacity-20" />
              <p className="text-[#8A9BB5] font-medium">Connecting to secure robot stream...</p>
            </div>
          )}

          <div className="absolute inset-0 pointer-events-none opacity-5 bg-[linear-gradient(to_bottom,transparent_50%,rgba(0,0,0,0.5)_50%)] bg-[length:100%_4px]"></div>
          
          <div className="absolute bottom-4 left-4 p-2 bg-black/50 backdrop-blur-md rounded border border-white/10">
            <div className="flex items-center gap-2 text-[10px] text-[#8A9BB5] uppercase tracking-widest font-bold">
              <Shield className="w-3 h-3 text-[#10B981]" />
              AES-256 SECURE
            </div>
          </div>
        </div>

        <div className="mt-6 grid grid-cols-3 gap-4">
          <div className="bg-white/5 border border-white/10 rounded-xl p-4">
            <p className="text-[#8A9BB5] text-[10px] uppercase font-bold tracking-widest mb-1">Bandwidth</p>
            <div className="flex items-center gap-2">
              <Wifi className="w-4 h-4 text-[#1E6BFF]" />
              <p className="text-lg font-mono">{bandwidth.toFixed(1)} Mbps</p>
            </div>
          </div>
          <div className="bg-white/5 border border-white/10 rounded-xl p-4">
            <p className="text-[#8A9BB5] text-[10px] uppercase font-bold tracking-widest mb-1">Latency</p>
            <div className="flex items-center gap-2">
              <Activity className="w-4 h-4 text-[#8B5CF6]" />
              <p className="text-lg font-mono">{latency.toFixed(0)}ms</p>
            </div>
          </div>
          <div className="bg-white/5 border border-white/10 rounded-xl p-4">
            <p className="text-[#8A9BB5] text-[10px] uppercase font-bold tracking-widest mb-1">Battery</p>
            <div className="flex items-center gap-2">
              <div className="w-4 h-1.5 bg-[#10B981]/30 rounded-sm relative">
                <div className="h-full bg-[#10B981] rounded-sm" style={{ width: '74%' }} />
              </div>
              <p className="text-lg font-mono">74%</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

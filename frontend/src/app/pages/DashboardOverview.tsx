import { useState, useEffect } from "react";
import { 
  Users, 
  TrendingUp, 
  BookOpen, 
  Power, 
  Battery, 
  MessageCircle, 
  Activity,
  Radio,
  Zap,
  Clock,
  Search,
  ArrowUp,
  ArrowDown,
  ArrowLeft,
  ArrowRight,
  ShieldAlert,
  Move
} from "lucide-react";
import { 
  AreaChart, 
  Area, 
  PieChart, 
  Pie, 
  Cell, 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip, 
  ResponsiveContainer 
} from "recharts";
import { toast } from "sonner";
import { useNavigate } from "react-router";
import { studentApi, robotApi, apiFetch } from "../services/api";

const topicCoverageData = [
  { name: "Physics", value: 35, color: "#1E6BFF" },
  { name: "Chemistry", value: 25, color: "#00D4FF" },
  { name: "Biology", value: 20, color: "#8B5CF6" },
  { name: "Math", value: 20, color: "#10B981" },
];

export default function DashboardOverview() {
  const navigate = useNavigate();
  const [batteryLevel, setBatteryLevel] = useState<any>(72);
  const [totalStudents, setTotalStudents] = useState(128);
  const [attendance, setAttendance] = useState<any>(90);
  const [activeModules, setActiveModules] = useState(24);
  const [isRobotOnline, setIsRobotOnline] = useState(true);
  
  // Robot Control State
  const [movement, setMovement] = useState({ forward: false, backward: false, left: false, right: false });
  const [speed, setSpeed] = useState(70);
  const [robotStatus, setRobotStatus] = useState<any>({ mode: 'idle', is_moving: false });
  const [ws, setWs] = useState<WebSocket | null>(null);
  
  const [attendanceData, setAttendanceData] = useState([
    { day: "Mon", attendance: 92 },
    { day: "Tue", attendance: 88 },
    { day: "Wed", attendance: 95 },
    { day: "Thu", attendance: 90 },
    { day: "Fri", attendance: 87 },
    { day: "Sat", attendance: 78 },
    { day: "Sun", attendance: 82 },
  ]);

  const [recentQueries, setRecentQueries] = useState([
    { id: 1, user: "Sarah J.", topic: "Newton's Laws", time: "2m ago" },
    { id: 2, user: "Mike C.", topic: "Photosynthesis", time: "5m ago" },
    { id: 3, user: "Emma D.", topic: "Periodic Table", time: "12m ago" },
  ]);

  const [systemLogs, setSystemLogs] = useState([
    { id: 1, event: "Face Model Synchronized", type: "success" },
    { id: 2, event: "Voice Pipeline: Active", type: "info" },
    { id: 3, event: "Battery optimization applied", type: "warning" },
  ]);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [studentRes, healthRes] = await Promise.all([
          studentApi.list({ page_size: 1 }),
          robotApi.getStatus().catch(() => ({ status: 'offline' }))
        ]);
        
        if (studentRes.total !== undefined) setTotalStudents(studentRes.total);
        setIsRobotOnline(healthRes.status === 'ok' || healthRes.status === 'online');
      } catch (err) {
        console.error("Dashboard fetch failed", err);
      }
    };

    fetchData();

    // Robot WebSocket Setup
    const socket = new WebSocket(`ws://${window.location.hostname}:8000/api/robot/ws/control`);
    socket.onopen = () => console.log("Robot WS Connected");
    socket.onmessage = (e) => setRobotStatus(JSON.parse(e.data));
    socket.onclose = () => console.log("Robot WS Disconnected");
    setWs(socket);

    const interval = setInterval(() => {
      setBatteryLevel((prev: any) => (Math.max(0, parseFloat(prev) - 0.01)).toFixed(1));
      setAttendance((prev: any) => (Math.min(100, Math.max(0, parseFloat(prev) + (Math.random() - 0.5)))).toFixed(1));
      
      if (Math.random() > 0.8) {
        const topics = ["Calculus", "World War II", "Cell Division"];
        const names = ["Alex K.", "Jessica L.", "David P."];
        const newQuery = {
          id: Date.now(),
          user: names[Math.floor(Math.random() * names.length)],
          topic: topics[Math.floor(Math.random() * topics.length)],
          time: "Just now"
        };
        setRecentQueries(prev => [newQuery, ...prev.slice(0, 4)]);
      }
    }, 5000);

    return () => {
      clearInterval(interval);
      socket.close();
    };
  }, []);

  // Send robot command when movement or speed changes
  useEffect(() => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ ...movement, speed }));
    }
  }, [movement, speed, ws]);

  const handleMove = (direction: string, active: boolean) => {
    setMovement(prev => ({ ...prev, [direction]: active }));
  };

  const handleStop = async () => {
    setMovement({ forward: false, backward: false, left: false, right: false });
    try {
      await apiFetch('/robot/stop', { method: 'POST' });
      toast.error("Emergency Stop Triggered");
    } catch (err) {
      console.error("Stop failed", err);
    }
  };

  const handleAction = (name: string, path?: string) => {
    if (path) {
      navigate(path);
      toast.info(`Opening ${name}`);
    } else {
      toast.success(`${name} updated`);
    }
  };

  return (
    <div className="space-y-6">
      {/* KPI Cards */}
      <div className="grid grid-cols-5 gap-4">
        <button 
          onClick={() => handleAction("Students", "/enrollment")}
          className="text-left bg-[#131827]/60 backdrop-blur-sm border border-white/10 rounded-xl p-5 hover:bg-white/5 transition-all group"
        >
          <div className="flex items-center justify-between">
            <div>
              <p className="text-[#8A9BB5] text-xs uppercase tracking-wider">Total Students</p>
              <h3 className="text-3xl font-bold mt-1">{totalStudents}</h3>
            </div>
            <div className="w-12 h-12 bg-[#1E6BFF]/10 rounded-lg flex items-center justify-center group-hover:scale-110 transition-transform border border-[#1E6BFF]/20">
              <Users className="w-6 h-6 text-[#1E6BFF]" />
            </div>
          </div>
        </button>

        <button 
          onClick={() => handleAction("Attendance", "/attendance")}
          className="text-left bg-[#131827]/60 backdrop-blur-sm border border-white/10 rounded-xl p-5 hover:bg-white/5 transition-all group"
        >
          <div className="flex items-center justify-between">
            <div>
              <p className="text-[#8A9BB5] text-xs uppercase tracking-wider">Attendance</p>
              <h3 className="text-3xl font-bold mt-1">{attendance}%</h3>
            </div>
            <div className="w-12 h-12 bg-[#10B981]/10 rounded-lg flex items-center justify-center group-hover:scale-110 transition-transform border border-[#10B981]/20">
              <TrendingUp className="w-6 h-6 text-[#10B981]" />
            </div>
          </div>
        </button>

        <button 
          onClick={() => handleAction("Syllabus", "/syllabus")}
          className="text-left bg-[#131827]/60 backdrop-blur-sm border border-white/10 rounded-xl p-5 hover:bg-white/5 transition-all group"
        >
          <div className="flex items-center justify-between">
            <div>
              <p className="text-[#8A9BB5] text-xs uppercase tracking-wider">Modules</p>
              <h3 className="text-3xl font-bold mt-1">{activeModules}</h3>
            </div>
            <div className="w-12 h-12 bg-[#8B5CF6]/10 rounded-lg flex items-center justify-center group-hover:scale-110 transition-transform border border-[#8B5CF6]/20">
              <BookOpen className="w-6 h-6 text-[#8B5CF6]" />
            </div>
          </div>
        </button>

        <div className="bg-[#131827]/60 backdrop-blur-sm border border-white/10 rounded-xl p-5">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-[#8A9BB5] text-xs uppercase tracking-wider">Power</p>
              <h3 className="text-3xl font-bold mt-1">{batteryLevel}%</h3>
            </div>
            <div className="w-12 h-12 bg-[#F59E0B]/10 rounded-lg flex items-center justify-center border border-[#F59E0B]/20">
              <Battery className="w-6 h-6 text-[#F59E0B]" />
            </div>
          </div>
        </div>

        <div className="bg-[#131827]/60 backdrop-blur-sm border border-white/10 rounded-xl p-5 border-l-4 border-l-[#1E6BFF]">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-[#8A9BB5] text-xs uppercase tracking-wider">Robot Mode</p>
              <h3 className="text-xl font-bold mt-1 uppercase tracking-tighter">{robotStatus.mode}</h3>
            </div>
            <div className={`w-12 h-12 ${isRobotOnline ? 'bg-[#10B981]/10' : 'bg-red-500/10'} rounded-lg flex items-center justify-center border ${isRobotOnline ? 'border-[#10B981]/20' : 'border-red-500/20'}`}>
              <Radio className={`w-6 h-6 ${isRobotOnline ? 'text-[#10B981]' : 'text-red-500'} ${isRobotOnline ? 'animate-pulse' : ''}`} />
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-4 gap-6">
        {/* Robot Command Center */}
        <div className="bg-gradient-to-br from-[#131827] to-[#1a2235] border border-[#1E6BFF]/30 rounded-2xl p-6 shadow-2xl shadow-[#1E6BFF]/5">
          <div className="flex items-center gap-3 mb-8">
            <div className="w-10 h-10 bg-[#1E6BFF]/20 rounded-xl flex items-center justify-center border border-[#1E6BFF]/30">
               <Move className="w-5 h-5 text-[#1E6BFF]" />
            </div>
            <div>
              <h3 className="font-bold text-lg leading-tight">Robot Command</h3>
              <div className="flex items-center gap-1.5 mt-0.5">
                <span className={`w-1.5 h-1.5 rounded-full ${isRobotOnline ? 'bg-[#10B981]' : 'bg-red-500'}`} />
                <span className="text-[10px] text-[#8A9BB5] uppercase tracking-widest">{isRobotOnline ? 'Online' : 'Offline'}</span>
              </div>
            </div>
          </div>

          {/* D-Pad */}
          <div className="flex flex-col items-center gap-2 mb-8">
            <button 
              onMouseDown={() => handleMove('forward', true)} 
              onMouseUp={() => handleMove('forward', false)}
              onMouseLeave={() => handleMove('forward', false)}
              className={`w-14 h-14 rounded-2xl flex items-center justify-center transition-all ${movement.forward ? 'bg-[#1E6BFF] text-white scale-90 shadow-lg shadow-[#1E6BFF]/40' : 'bg-white/5 text-[#8A9BB5] hover:bg-white/10 hover:text-white border border-white/10'}`}
            >
              <ArrowUp className="w-6 h-6" />
            </button>
            <div className="flex gap-2">
              <button 
                onMouseDown={() => handleMove('left', true)} 
                onMouseUp={() => handleMove('left', false)}
                onMouseLeave={() => handleMove('left', false)}
                className={`w-14 h-14 rounded-2xl flex items-center justify-center transition-all ${movement.left ? 'bg-[#1E6BFF] text-white scale-90 shadow-lg shadow-[#1E6BFF]/40' : 'bg-white/5 text-[#8A9BB5] hover:bg-white/10 hover:text-white border border-white/10'}`}
              >
                <ArrowLeft className="w-6 h-6" />
              </button>
              <button 
                onClick={handleStop}
                className="w-14 h-14 rounded-2xl flex items-center justify-center bg-red-500/20 text-red-500 border border-red-500/30 hover:bg-red-500 hover:text-white transition-all shadow-lg shadow-red-500/5 group"
              >
                <ShieldAlert className="w-6 h-6 group-hover:scale-110 transition-transform" />
              </button>
              <button 
                onMouseDown={() => handleMove('right', true)} 
                onMouseUp={() => handleMove('right', false)}
                onMouseLeave={() => handleMove('right', false)}
                className={`w-14 h-14 rounded-2xl flex items-center justify-center transition-all ${movement.right ? 'bg-[#1E6BFF] text-white scale-90 shadow-lg shadow-[#1E6BFF]/40' : 'bg-white/5 text-[#8A9BB5] hover:bg-white/10 hover:text-white border border-white/10'}`}
              >
                <ArrowRight className="w-6 h-6" />
              </button>
            </div>
            <button 
              onMouseDown={() => handleMove('backward', true)} 
              onMouseUp={() => handleMove('backward', false)}
              onMouseLeave={() => handleMove('backward', false)}
              className={`w-14 h-14 rounded-2xl flex items-center justify-center transition-all ${movement.backward ? 'bg-[#1E6BFF] text-white scale-90 shadow-lg shadow-[#1E6BFF]/40' : 'bg-white/5 text-[#8A9BB5] hover:bg-white/10 hover:text-white border border-white/10'}`}
            >
              <ArrowDown className="w-6 h-6" />
            </button>
          </div>

          {/* Speed Slider */}
          <div className="space-y-3 px-2">
            <div className="flex justify-between items-center">
               <span className="text-xs text-[#8A9BB5] uppercase font-bold tracking-widest">Motor Power</span>
               <span className="text-xs font-mono font-bold text-[#1E6BFF]">{speed}%</span>
            </div>
            <input 
              type="range" 
              min="20" 
              max="100" 
              value={speed} 
              onChange={(e) => setSpeed(parseInt(e.target.value))}
              className="w-full h-1.5 bg-white/10 rounded-lg appearance-none cursor-pointer accent-[#1E6BFF]"
            />
          </div>
          
          <div className="mt-8 grid grid-cols-2 gap-2">
             <div className="bg-white/5 rounded-xl p-3 border border-white/5">
                <p className="text-[10px] text-[#8A9BB5] uppercase mb-1">Left Motor</p>
                <p className="text-sm font-mono font-bold">{robotStatus.left_speed || 0}%</p>
             </div>
             <div className="bg-white/5 rounded-xl p-3 border border-white/5">
                <p className="text-[10px] text-[#8A9BB5] uppercase mb-1">Right Motor</p>
                <p className="text-sm font-mono font-bold">{robotStatus.right_speed || 0}%</p>
             </div>
          </div>
        </div>

        {/* Main Chart */}
        <div className="col-span-3 bg-[#131827]/60 backdrop-blur-sm border border-white/10 rounded-xl p-6">
          <div className="flex items-center justify-between mb-8">
            <div>
              <h3 className="text-lg font-semibold">Attendance Analytics</h3>
              <p className="text-xs text-[#8A9BB5] mt-1">Weekly engagement trends</p>
            </div>
            <div className="flex gap-2">
               <button className="px-3 py-1 bg-white/5 border border-white/10 rounded-lg text-xs hover:bg-white/10 transition-colors">7 Days</button>
               <button className="px-3 py-1 bg-[#1E6BFF]/10 text-[#1E6BFF] border border-[#1E6BFF]/20 rounded-lg text-xs">30 Days</button>
            </div>
          </div>
          <div className="h-[300px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={attendanceData}>
                <defs>
                  <linearGradient id="colorAttendance" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#1E6BFF" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#1E6BFF" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#ffffff10" vertical={false} />
                <XAxis dataKey="day" stroke="#8A9BB5" fontSize={12} tickLine={false} axisLine={false} />
                <YAxis stroke="#8A9BB5" fontSize={12} tickLine={false} axisLine={false} tickFormatter={(val) => `${val}%`} />
                <Tooltip 
                  contentStyle={{ backgroundColor: '#131827', border: '1px solid #ffffff20', borderRadius: '8px' }}
                  itemStyle={{ color: '#00D4FF' }}
                />
                <Area 
                  type="monotone" 
                  dataKey="attendance" 
                  stroke="#1E6BFF" 
                  strokeWidth={3}
                  fillOpacity={1} 
                  fill="url(#colorAttendance)" 
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Topic Distribution */}
        <div className="bg-[#131827]/60 backdrop-blur-sm border border-white/10 rounded-xl p-6">
          <h3 className="text-lg font-semibold mb-6">Subject Focus</h3>
          <div className="h-[200px] w-full relative">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={topicCoverageData}
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={80}
                  paddingAngle={5}
                  dataKey="value"
                >
                  {topicCoverageData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.color} />
                  ))}
                </Pie>
              </PieChart>
            </ResponsiveContainer>
            <div className="absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 text-center">
              <p className="text-2xl font-bold">78%</p>
              <p className="text-[10px] text-[#8A9BB5] uppercase">Coverage</p>
            </div>
          </div>
          <div className="mt-8 space-y-4">
            {topicCoverageData.map((item) => (
              <div key={item.name} className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-2.5 h-2.5 rounded-full" style={{backgroundColor: item.color}} />
                  <span className="text-sm text-[#8A9BB5]">{item.name}</span>
                </div>
                <span className="text-sm font-mono font-bold">{item.value}%</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-6">
        {/* Recent Queries */}
        <div className="col-span-2 bg-[#131827]/60 backdrop-blur-sm border border-white/10 rounded-xl p-6">
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-2">
              <MessageCircle className="w-5 h-5 text-[#10B981]" />
              <h3 className="text-lg font-semibold">Voice Agent Queries</h3>
            </div>
            <button 
              onClick={() => navigate("/queries")}
              className="text-xs text-[#1E6BFF] font-bold uppercase tracking-widest hover:underline"
            >
              View History
            </button>
          </div>
          <div className="space-y-4">
            {recentQueries.map((q) => (
              <div key={q.id} className="flex items-center justify-between p-4 bg-white/5 rounded-xl border border-white/5 hover:border-[#1E6BFF]/30 transition-all cursor-pointer group">
                <div className="flex items-center gap-4">
                  <div className="w-10 h-10 bg-gradient-to-br from-[#1E6BFF]/20 to-[#00D4FF]/20 rounded-lg flex items-center justify-center text-[#00D4FF] font-bold group-hover:scale-110 transition-transform">
                    {q.user[0]}
                  </div>
                  <div>
                    <h4 className="font-semibold text-sm">{q.user}</h4>
                    <p className="text-xs text-[#8A9BB5] mt-0.5">{q.topic}</p>
                  </div>
                </div>
                <div className="flex flex-col items-end gap-1">
                  <div className="flex items-center gap-1 text-[10px] text-[#8A9BB5]">
                    <Clock className="w-3 h-3" />
                    {q.time}
                  </div>
                  <span className="text-[10px] text-[#10B981] font-bold uppercase tracking-widest">Socratic Mode</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Intelligence Log */}
        <div className="bg-[#131827]/60 backdrop-blur-sm border border-white/10 rounded-xl p-6">
          <div className="flex items-center gap-2 mb-6">
            <Activity className="w-5 h-5 text-[#00D4FF]" />
            <h3 className="text-lg font-semibold">Intelligence Log</h3>
          </div>
          <div className="space-y-6">
            {systemLogs.map((log) => (
              <div key={log.id} className="relative pl-6 border-l border-white/10">
                <div className={`absolute left-[-5px] top-0 w-2.5 h-2.5 rounded-full ${
                  log.type === 'success' ? 'bg-[#10B981]' : 
                  log.type === 'warning' ? 'bg-[#F59E0B]' : 'bg-[#1E6BFF]'
                }`} />
                <p className="text-sm font-medium">{log.event}</p>
                <p className="text-[10px] text-[#8A9BB5] mt-1 font-mono uppercase tracking-widest">Logged: Just now</p>
              </div>
            ))}
            
            <div className="mt-8 p-4 bg-[#1E6BFF]/5 rounded-xl border border-[#1E6BFF]/10">
              <div className="flex items-center gap-3 mb-3">
                <Zap className="w-4 h-4 text-[#1E6BFF]" />
                <p className="text-xs font-bold text-[#1E6BFF] uppercase tracking-widest">Edge AI Active</p>
              </div>
              <p className="text-xs text-[#8A9BB5] leading-relaxed italic">
                "Zoro is currently monitoring engagement and optimizing motor duty cycles for extended classroom operation."
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

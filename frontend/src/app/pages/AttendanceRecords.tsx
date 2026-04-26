import { useState, useEffect } from "react";
import { ChevronLeft, ChevronRight, Download, User, Calendar, Loader2, Activity } from "lucide-react";
import { toast } from "sonner";
import { attendanceApi, API_BASE_URL } from "../services/api";

export default function AttendanceRecords() {
  const [loading, setLoading] = useState(true);
  const [records, setRecords] = useState<any[]>([]);
  const [date, setDate] = useState(new Date().toISOString().split('T')[0]);
  const [stats, setStats] = useState({ present: 0, absent: 0, late: 0, total: 0 });

  const fetchAttendance = async () => {
    setLoading(true);
    try {
      const data = await attendanceApi.getToday({ date: date });
      setRecords(data.items || []);
      
      const p = data.items.filter((r: any) => r.status === "present").length;
      const l = data.items.filter((r: any) => r.status === "late").length;
      const a = data.items.filter((r: any) => r.status === "absent").length;
      
      setStats({
        present: p,
        late: l,
        absent: a,
        total: data.total || data.items.length
      });
    } catch (err) {
      console.error("Failed to fetch attendance", err);
      toast.error("Failed to load attendance records");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAttendance();
  }, [date]);

  const handleExport = (format: string) => {
    const token = localStorage.getItem('zoro_token');
    const url = `${API_BASE_URL}/attendance/export/${format.toLowerCase()}?date=${date}&token=${token}`;
    
    // Using a direct download link
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', `attendance_${date}.${format.toLowerCase()}`);
    document.body.appendChild(link);
    link.click();
    link.remove();
    
    toast.success(`Exporting attendance as ${format}...`);
  };

  const handleDateChange = (days: number) => {
    const newDate = new Date(date);
    newDate.setDate(newDate.getDate() + days);
    setDate(newDate.toISOString().split('T')[0]);
  };

  return (
    <div className="space-y-6">
      {/* Date Picker and Summary */}
      <div className="bg-[#131827]/60 backdrop-blur-sm border border-white/10 rounded-xl p-6">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <button 
              onClick={() => handleDateChange(-1)}
              className="p-2 hover:bg-white/5 rounded-lg transition-colors border border-white/5"
            >
              <ChevronLeft className="w-5 h-5" />
            </button>
            <div className="flex items-center gap-2 px-4 py-2 bg-white/5 border border-white/10 rounded-lg">
              <Calendar className="w-4 h-4 text-[#1E6BFF]" />
              <input 
                type="date" 
                value={date} 
                onChange={(e) => setDate(e.target.value)}
                className="bg-transparent border-none text-sm outline-none cursor-pointer"
              />
            </div>
            <button 
              onClick={() => handleDateChange(1)}
              className="p-2 hover:bg-white/5 rounded-lg transition-colors border border-white/5"
            >
              <ChevronRight className="w-5 h-5" />
            </button>
            <button 
              onClick={() => setDate(new Date().toISOString().split('T')[0])}
              className="px-4 py-2 bg-[#1E6BFF]/10 text-[#1E6BFF] hover:bg-[#1E6BFF]/20 border border-[#1E6BFF]/20 rounded-lg text-sm transition-colors"
            >
              Today
            </button>
          </div>

          <div className="flex gap-3">
            <button 
              onClick={() => handleExport('Excel')}
              className="px-4 py-2 bg-[#10B981]/10 text-[#10B981] border border-[#10B981]/20 hover:bg-[#10B981]/20 rounded-lg text-sm flex items-center gap-2 transition-colors"
            >
              <Download className="w-4 h-4" />
              Excel
            </button>
            <button 
              onClick={() => handleExport('CSV')}
              className="px-4 py-2 bg-[#1E6BFF]/10 text-[#00D4FF] border border-[#1E6BFF]/20 hover:bg-[#1E6BFF]/20 rounded-lg text-sm flex items-center gap-2 transition-colors"
            >
              <Download className="w-4 h-4" />
              CSV
            </button>
          </div>
        </div>

        {/* Summary Bar */}
        <div className="grid grid-cols-4 gap-4">
          <div className="bg-[#10B981]/5 border border-[#10B981]/10 rounded-xl p-4">
            <p className="text-xs text-[#8A9BB5] uppercase tracking-wider mb-1">Present</p>
            <h3 className="text-2xl font-bold text-[#10B981]">{stats.present}</h3>
          </div>
          <div className="bg-[#EF4444]/5 border border-[#EF4444]/10 rounded-xl p-4">
            <p className="text-xs text-[#8A9BB5] uppercase tracking-wider mb-1">Absent</p>
            <h3 className="text-2xl font-bold text-[#EF4444]">{stats.absent}</h3>
          </div>
          <div className="bg-[#F59E0B]/5 border border-[#F59E0B]/10 rounded-xl p-4">
            <p className="text-xs text-[#8A9BB5] uppercase tracking-wider mb-1">Late</p>
            <h3 className="text-2xl font-bold text-[#F59E0B]">{stats.late}</h3>
          </div>
          <div className="bg-[#1E6BFF]/5 border border-[#1E6BFF]/10 rounded-xl p-4">
            <p className="text-xs text-[#8A9BB5] uppercase tracking-wider mb-1">Total Expected</p>
            <h3 className="text-2xl font-bold text-[#00D4FF]">{stats.total}</h3>
          </div>
        </div>
      </div>

      {/* Attendance Table */}
      <div className="bg-[#131827]/60 backdrop-blur-sm border border-white/10 rounded-xl p-6">
        <div className="flex items-center justify-between mb-6">
          <h3 className="text-lg font-semibold">Detailed Logs</h3>
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 bg-[#10B981] rounded-full animate-pulse" />
            <span className="text-[10px] text-[#8A9BB5] font-bold uppercase tracking-widest">Real-time Sync Active</span>
          </div>
        </div>

        <div className="overflow-x-auto min-h-[400px] relative">
          {loading ? (
            <div className="absolute inset-0 flex items-center justify-center bg-black/5 z-10 rounded-lg">
              <div className="flex flex-col items-center gap-2">
                <Loader2 className="w-8 h-8 text-[#1E6BFF] animate-spin" />
                <p className="text-sm text-[#8A9BB5]">Syncing with Zoro...</p>
              </div>
            </div>
          ) : null}

          <table className="w-full">
            <thead>
              <tr className="border-b border-white/10">
                <th className="text-left py-4 px-4 text-xs font-bold text-[#8A9BB5] uppercase tracking-wider">Student</th>
                <th className="text-left py-4 px-4 text-xs font-bold text-[#8A9BB5] uppercase tracking-wider">ID Code</th>
                <th className="text-left py-4 px-4 text-xs font-bold text-[#8A9BB5] uppercase tracking-wider">Section</th>
                <th className="text-left py-4 px-4 text-xs font-bold text-[#8A9BB5] uppercase tracking-wider">Time</th>
                <th className="text-left py-4 px-4 text-xs font-bold text-[#8A9BB5] uppercase tracking-wider">Confidence</th>
                <th className="text-right py-4 px-4 text-xs font-bold text-[#8A9BB5] uppercase tracking-wider">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {records.length > 0 ? (
                records.map((record) => (
                  <tr key={record.id} className="hover:bg-white/[0.02] transition-colors group">
                    <td className="py-4 px-4">
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 bg-gradient-to-br from-[#1E6BFF]/20 to-[#00D4FF]/20 rounded-full flex items-center justify-center border border-white/5 group-hover:border-[#1E6BFF]/30 transition-colors">
                          <User className="w-5 h-5 text-[#00D4FF]" />
                        </div>
                        <span className="font-medium text-sm">{record.student_name}</span>
                      </div>
                    </td>
                    <td className="py-4 px-4 text-sm text-[#8A9BB5] font-mono">{record.student_code}</td>
                    <td className="py-4 px-4 text-sm text-[#8A9BB5]">{record.class_section}</td>
                    <td className="py-4 px-4 text-sm text-[#8A9BB5]">
                      {new Date(record.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </td>
                    <td className="py-4 px-4">
                      <div className="flex items-center gap-3">
                        <div className="flex-1 bg-white/5 rounded-full h-1.5 min-w-[60px]">
                          <div
                            className="h-full bg-gradient-to-r from-[#1E6BFF] to-[#00D4FF] rounded-full"
                            style={{ width: `${(record.confidence || 0) * 100}%` }}
                          />
                        </div>
                        <span className="text-xs font-mono text-[#00D4FF]">
                          {((record.confidence || 0) * 100).toFixed(1)}%
                        </span>
                      </div>
                    </td>
                    <td className="py-4 px-4 text-right">
                      <span
                        className={`text-[10px] font-bold uppercase tracking-widest px-2 py-1 rounded-md ${
                          record.status === "present"
                            ? "bg-[#10B981]/10 text-[#10B981] border border-[#10B981]/20"
                            : record.status === "absent"
                            ? "bg-[#EF4444]/10 text-[#EF4444] border border-[#EF4444]/20"
                            : "bg-[#F59E0B]/10 text-[#F59E0B] border border-[#F59E0B]/20"
                        }`}
                      >
                        {record.status}
                      </span>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={6} className="py-20 text-center text-[#8A9BB5]">
                    <div className="flex flex-col items-center gap-2">
                      <div className="w-12 h-12 bg-white/5 rounded-full flex items-center justify-center border border-white/5 mb-2">
                        <Activity className="w-6 h-6 opacity-20" />
                      </div>
                      <p>No attendance records found for this date.</p>
                      <p className="text-xs">Zoro is standing by for detections.</p>
                    </div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Footer info */}
        {!loading && records.length > 0 && (
          <div className="flex items-center justify-between mt-8 pt-6 border-t border-white/10">
            <p className="text-xs text-[#8A9BB5]">
              System synchronized at {new Date().toLocaleTimeString()}
            </p>
            <div className="flex gap-2">
               <button className="px-4 py-2 bg-white/5 border border-white/10 rounded-lg text-xs hover:bg-white/10 transition-colors">
                 Previous Page
               </button>
               <button className="px-4 py-2 bg-[#1E6BFF]/10 text-[#1E6BFF] border border-[#1E6BFF]/20 rounded-lg text-xs hover:bg-[#1E6BFF]/20 transition-colors">
                 Next Page
               </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

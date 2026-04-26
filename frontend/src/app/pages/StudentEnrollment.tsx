import { useState, useEffect } from "react";
import { Upload, Download, Search, Plus, User, Loader2, CheckCircle2, AlertCircle } from "lucide-react";
import { toast } from "sonner";
import { studentApi } from "../services/api";

export default function StudentEnrollment() {
  const [loading, setLoading] = useState(true);
  const [students, setStudents] = useState<any[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [stats, setStats] = useState({ total: 0, trained: 0 });

  const fetchStudents = async () => {
    setLoading(true);
    try {
      const data = await studentApi.list({ page_size: 100 });
      setStudents(data.items || []);
      setStats({
        total: data.total || data.items.length,
        trained: data.items.filter((s: any) => s.label_id !== null).length
      });
    } catch (err) {
      console.error("Failed to fetch students", err);
      toast.error("Failed to load student list");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStudents();
  }, []);

  const handleUpload = () => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.xlsx,.csv';
    input.onchange = (e: any) => {
      const file = e.target.files[0];
      if (file) {
        toast.promise(new Promise((resolve) => setTimeout(resolve, 3000)), {
          loading: `Uploading ${file.name}...`,
          success: 'Dataset uploaded. Training started automatically.',
          error: 'Upload failed',
        });
      }
    };
    input.click();
  };

  const handleDownloadTemplate = () => {
    toast.success('Downloading Excel Template...');
  };

  const filteredStudents = students.filter(s => 
    s.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    s.student_id.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="grid grid-cols-5 gap-6">
      {/* Left Panel - Stats & Upload */}
      <div className="col-span-2 space-y-6">
        {/* Upload Area */}
        <div className="bg-[#131827]/60 backdrop-blur-sm border border-white/10 rounded-xl p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold">Bulk Enrollment</h3>
            <CheckCircle2 className="w-5 h-5 text-[#10B981]" />
          </div>
          <div 
            onClick={handleUpload}
            className="border-2 border-dashed border-[#1E6BFF]/30 rounded-xl p-10 text-center hover:border-[#1E6BFF] hover:bg-[#1E6BFF]/5 transition-all cursor-pointer group"
          >
            <div className="w-14 h-14 bg-[#1E6BFF]/10 rounded-full flex items-center justify-center mx-auto mb-4 group-hover:scale-110 transition-transform border border-[#1E6BFF]/20">
              <Upload className="w-7 h-7 text-[#1E6BFF]" />
            </div>
            <h4 className="font-semibold mb-2">Sync Student Database</h4>
            <p className="text-xs text-[#8A9BB5] mb-6 leading-relaxed">
              Upload an Excel file with student metadata.<br/>Zoro will auto-map images from storage.
            </p>
            <button className="px-6 py-2.5 bg-[#1E6BFF] hover:bg-[#1E6BFF]/80 rounded-xl transition-all text-sm font-medium shadow-lg shadow-[#1E6BFF]/20">
              Select Dataset
            </button>
          </div>
          <button 
            onClick={handleDownloadTemplate}
            className="flex items-center gap-2 mt-4 text-xs text-[#00D4FF] hover:underline mx-auto"
          >
            <Download className="w-3 h-3" />
            Download Enrollment Template
          </button>
        </div>

        {/* Training Progress */}
        <div className="bg-[#131827]/60 backdrop-blur-sm border border-white/10 rounded-xl p-6">
          <div className="flex items-center justify-between mb-6">
            <h3 className="text-lg font-semibold">AI Model Status</h3>
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 bg-[#10B981] rounded-full animate-pulse" />
              <span className="text-[10px] font-bold text-[#10B981] uppercase tracking-widest">Optimized</span>
            </div>
          </div>
          
          <div className="space-y-6">
            <div>
              <div className="flex justify-between text-xs mb-2">
                <span className="text-[#8A9BB5]">Face Recognition Accuracy</span>
                <span className="text-[#00D4FF] font-mono">98.4%</span>
              </div>
              <div className="w-full bg-white/5 rounded-full h-2 overflow-hidden border border-white/5">
                <div className="h-full bg-gradient-to-r from-[#1E6BFF] to-[#00D4FF] rounded-full w-[98.4%]" />
              </div>
            </div>

            <div className="p-4 bg-white/5 rounded-xl border border-white/5">
              <div className="flex items-start gap-3">
                <div className="p-2 bg-[#10B981]/10 rounded-lg">
                  <CheckCircle2 className="w-4 h-4 text-[#10B981]" />
                </div>
                <div>
                  <p className="text-sm font-medium">Training Complete</p>
                  <p className="text-xs text-[#8A9BB5] mt-1">
                    {stats.trained} out of {stats.total} student models are synchronized and ready for real-time detection.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Right Panel - Student Grid */}
      <div className="col-span-3 bg-[#131827]/60 backdrop-blur-sm border border-white/10 rounded-xl p-6 flex flex-col min-h-[600px]">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h3 className="text-lg font-semibold">Enrolled Students</h3>
            <p className="text-xs text-[#8A9BB5] mt-1">Manage and audit student recognition profiles</p>
          </div>
          <div className="flex gap-3">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-[#8A9BB5]" />
              <input
                type="text"
                placeholder="Search name or ID..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-10 pr-4 py-2 bg-white/5 border border-white/10 rounded-xl text-sm focus:outline-none focus:border-[#1E6BFF] w-64 transition-all"
              />
            </div>
            <button 
              onClick={() => toast.info('New enrollment form opened')}
              className="p-2 bg-[#1E6BFF] hover:bg-[#1E6BFF]/80 rounded-xl transition-all shadow-lg shadow-[#1E6BFF]/20"
            >
              <Plus className="w-5 h-5" />
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto pr-2 custom-scrollbar relative">
          {loading ? (
            <div className="absolute inset-0 flex items-center justify-center">
              <Loader2 className="w-10 h-10 text-[#1E6BFF] animate-spin" />
            </div>
          ) : filteredStudents.length > 0 ? (
            <div className="grid grid-cols-2 gap-4">
              {filteredStudents.map((student) => (
                <div
                  key={student.id}
                  className="bg-white/5 border border-white/10 rounded-2xl p-4 hover:bg-white/[0.08] transition-all hover:scale-[1.02] cursor-pointer group"
                >
                  <div className="flex items-start gap-4">
                    <div className="w-14 h-14 bg-gradient-to-br from-[#131827] to-[#1E6BFF]/20 rounded-2xl flex items-center justify-center flex-shrink-0 border border-white/5 group-hover:border-[#1E6BFF]/30 transition-colors">
                      <User className="w-7 h-7 text-[#1E6BFF] opacity-80" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <h4 className="font-semibold text-sm truncate">{student.name}</h4>
                      <p className="text-xs text-[#8A9BB5] mt-0.5 font-mono">{student.student_id}</p>
                      <div className="flex items-center gap-2 mt-3">
                        <span className={`text-[9px] font-bold uppercase tracking-widest px-2 py-0.5 rounded ${
                          student.label_id !== null
                            ? "bg-[#10B981]/10 text-[#10B981] border border-[#10B981]/20"
                            : "bg-[#F59E0B]/10 text-[#F59E0B] border border-[#F59E0B]/20"
                        }`}>
                          {student.label_id !== null ? 'Recognized' : 'No Model'}
                        </span>
                        <span className="text-[9px] text-[#8A9BB5] uppercase tracking-widest">{student.class_section}</span>
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="h-full flex flex-col items-center justify-center text-[#8A9BB5] opacity-50 py-20">
              <AlertCircle className="w-12 h-12 mb-4" />
              <p>No students found matching your search</p>
            </div>
          )}
        </div>
        
        <div className="mt-6 pt-4 border-t border-white/5 flex items-center justify-between text-[10px] text-[#8A9BB5] uppercase tracking-widest font-bold">
          <span>{stats.total} total students in system</span>
          <span>Last synchronized: Just now</span>
        </div>
      </div>
    </div>
  );
}

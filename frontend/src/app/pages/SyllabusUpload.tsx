import { Upload, FileText, FileSpreadsheet, Presentation, Trash2, Eye, ChevronRight, ChevronDown, Loader2 } from "lucide-react";
import { useState, useRef } from "react";
import { toast } from "sonner";
import { syllabusApi, robotApi } from "../services/api";
import { useEffect } from "react";

const uploadedModules = [
  {
    name: "Physics_Module_01.pdf",
    format: "PDF",
    date: "2026-04-15",
    topics: 12,
    status: "Active",
  },
  {
    name: "Chemistry_Basics.pptx",
    format: "PPTX",
    date: "2026-04-14",
    topics: 8,
    status: "Active",
  },
  {
    name: "Biology_DNA.docx",
    format: "DOCX",
    date: "2026-04-12",
    topics: 15,
    status: "Processing",
  },
  {
    name: "Mathematics_Calculus.pdf",
    format: "PDF",
    date: "2026-04-10",
    topics: 20,
    status: "Active",
  },
];

const topicTree = [
  {
    name: "Physics",
    topics: [
      "Newton's Laws of Motion",
      "Energy and Work",
      "Thermodynamics",
      "Electromagnetism",
    ],
  },
  {
    name: "Chemistry",
    topics: ["Atomic Structure", "Chemical Bonding", "Reactions", "Acids and Bases"],
  },
  {
    name: "Biology",
    topics: [
      "Cell Structure",
      "DNA Replication",
      "Photosynthesis",
      "Cellular Respiration",
      "Evolution",
    ],
  },
];

export default function SyllabusUpload() {
  const [expandedTopics, setExpandedTopics] = useState<string[]>(["Physics"]);
  const [isUploading, setIsUploading] = useState(false);
  const [quota, setQuota] = useState<any>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const fetchQuota = async () => {
      try {
        const data = await robotApi.getQuota("zoro2026-session"); // Default session for demo
        setQuota(data);
      } catch (err) {
        console.error("Failed to fetch quota", err);
      }
    };
    fetchQuota();
    const interval = setInterval(fetchQuota, 10000); // Refresh every 10s
    return () => clearInterval(interval);
  }, []);

  const toggleTopic = (name: string) => {
    setExpandedTopics((prev) =>
      prev.includes(name) ? prev.filter((t) => t !== name) : [...prev, name]
    );
  };

  const handleUploadClick = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    // Check size (50MB)
    if (file.size > 50 * 1024 * 1024) {
      toast.error("File is too large. Max 50MB allowed.");
      return;
    }

    const allowedExtensions = ['.pdf', '.docx', '.pptx', '.ppt', '.doc', '.txt', '.md'];
    const fileExtension = file.name.substring(file.name.lastIndexOf('.')).toLowerCase();

    if (!allowedExtensions.includes(fileExtension)) {
      toast.error(`Unsupported file type (${fileExtension}). Use PDF, DOCX, or PPTX.`);
      return;
    }

    setIsUploading(true);
    const toastId = toast.loading(`Uploading ${file.name}...`);

    try {
      const response = await syllabusApi.upload(file);
      if (response.success) {
        toast.success(response.message || "Syllabus uploaded and processed successfully!", { id: toastId });
      } else {
        toast.error(response.message || "Upload failed", { id: toastId });
      }
      // In a real app, we'd refresh the list here
    } catch (err: any) {
      toast.error(err.message || "Upload failed. Ensure backend is running.", { id: toastId });
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const handleDelete = (name: string) => {
    toast.error(`Deleted module: ${name}`);
  };

  const handleView = (name: string) => {
    toast.info(`Opening viewer for: ${name}`);
  };

  return (
    <div className="space-y-6">
      {/* Upload Zone */}
      <div className="bg-[#131827]/60 backdrop-blur-sm border border-white/10 rounded-xl p-8">
        <input 
          type="file" 
          ref={fileInputRef} 
          onChange={handleFileChange} 
          className="hidden" 
          accept=".pdf,.docx,.doc,.pptx,.ppt,.txt,.md"
        />
        <div 
          onClick={handleUploadClick}
          className={`border-2 border-dashed ${isUploading ? 'border-[#1E6BFF] bg-[#1E6BFF]/5' : 'border-[#1E6BFF]/50'} rounded-xl p-12 text-center hover:border-[#1E6BFF] transition-colors cursor-pointer group`}
        >
          <div className="w-16 h-16 bg-[#1E6BFF]/20 rounded-full flex items-center justify-center mx-auto mb-4 group-hover:scale-110 transition-transform">
            {isUploading ? (
              <Loader2 className="w-8 h-8 text-[#1E6BFF] animate-spin" />
            ) : (
              <Upload className="w-8 h-8 text-[#1E6BFF]" />
            )}
          </div>
          <h3 className="text-lg mb-2">
            {isUploading ? "Processing Document..." : "Upload Syllabus File"}
          </h3>
          <p className="text-[#8A9BB5] text-sm mb-4">
            Supports PDF, DOCX, PPTX, PPT — Max 50MB
          </p>
          <button 
            disabled={isUploading}
            className="px-6 py-2 bg-[#1E6BFF] hover:bg-[#1E6BFF]/80 rounded-lg transition-colors disabled:opacity-50"
          >
            {isUploading ? "Please wait..." : "Choose File"}
          </button>
        </div>

        {/* File Format Icons */}
        <div className="flex justify-center gap-6 mt-6">
          <div className="flex flex-col items-center gap-2">
            <div className="w-12 h-12 bg-[#EF4444]/20 rounded-lg flex items-center justify-center">
              <FileText className="w-6 h-6 text-[#EF4444]" />
            </div>
            <span className="text-xs text-[#8A9BB5]">PDF</span>
          </div>
          <div className="flex flex-col items-center gap-2">
            <div className="w-12 h-12 bg-[#1E6BFF]/20 rounded-lg flex items-center justify-center">
              <FileText className="w-6 h-6 text-[#1E6BFF]" />
            </div>
            <span className="text-xs text-[#8A9BB5]">Word</span>
          </div>
          <div className="flex flex-col items-center gap-2">
            <div className="w-12 h-12 bg-[#F59E0B]/20 rounded-lg flex items-center justify-center">
              <Presentation className="w-6 h-6 text-[#F59E0B]" />
            </div>
            <span className="text-xs text-[#8A9BB5]">PowerPoint</span>
          </div>
        </div>
      </div>

      {/* Quota & Limit Status */}
      {quota && quota.is_rag_active && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="bg-[#131827]/60 backdrop-blur-sm border border-[#10B981]/30 rounded-xl p-6">
            <div className="flex justify-between items-center mb-2">
              <h4 className="text-sm text-[#8A9BB5]">Student Knowledge Access</h4>
              <span className="text-xs text-[#10B981] bg-[#10B981]/10 px-2 py-0.5 rounded">Active</span>
            </div>
            <div className="text-2xl font-bold mb-1">{quota.inputs_remaining} / 10</div>
            <p className="text-xs text-[#8A9BB5]">Questions remaining for this session</p>
            <div className="w-full bg-white/5 h-1.5 rounded-full mt-3 overflow-hidden">
              <div 
                className="bg-[#10B981] h-full transition-all duration-500" 
                style={{ width: `${(quota.inputs_remaining / 10) * 100}%` }}
              />
            </div>
          </div>

          <div className="bg-[#131827]/60 backdrop-blur-sm border border-[#1E6BFF]/30 rounded-xl p-6">
            <h4 className="text-sm text-[#8A9BB5] mb-2">Zoro Explanation Quota</h4>
            <div className="text-2xl font-bold mb-1">{quota.outputs_remaining} / 20</div>
            <p className="text-xs text-[#8A9BB5]">Responses Zoro can provide from documents</p>
            <div className="w-full bg-white/5 h-1.5 rounded-full mt-3 overflow-hidden">
              <div 
                className="bg-[#1E6BFF] h-full transition-all duration-500" 
                style={{ width: `${(quota.outputs_remaining / 20) * 100}%` }}
              />
            </div>
          </div>

          <div className="bg-[#131827]/60 backdrop-blur-sm border border-[#F59E0B]/30 rounded-xl p-6">
            <h4 className="text-sm text-[#8A9BB5] mb-2">School-Wide Daily Limit</h4>
            <div className="text-2xl font-bold mb-1">{1000 - quota.total_rag_used} / 1000</div>
            <p className="text-xs text-[#8A9BB5]">Total document searches left today</p>
            <div className="w-full bg-white/5 h-1.5 rounded-full mt-3 overflow-hidden">
              <div 
                className="bg-[#F59E0B] h-full transition-all duration-500" 
                style={{ width: `${((1000 - quota.total_rag_used) / 1000) * 100}%` }}
              />
            </div>
          </div>
        </div>
      )}

      <div className="grid grid-cols-3 gap-4">
        {/* Uploaded Modules Table */}
        <div className="col-span-2 bg-[#131827]/60 backdrop-blur-sm border border-white/10 rounded-xl p-6">
          <h3 className="text-lg mb-4">Uploaded Modules</h3>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-white/10">
                  <th className="text-left py-3 px-2 text-sm text-[#8A9BB5]">
                    File Name
                  </th>
                  <th className="text-left py-3 px-2 text-sm text-[#8A9BB5]">
                    Format
                  </th>
                  <th className="text-left py-3 px-2 text-sm text-[#8A9BB5]">
                    Upload Date
                  </th>
                  <th className="text-left py-3 px-2 text-sm text-[#8A9BB5]">
                    Topics
                  </th>
                  <th className="text-left py-3 px-2 text-sm text-[#8A9BB5]">
                    Status
                  </th>
                  <th className="text-left py-3 px-2 text-sm text-[#8A9BB5]">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody>
                {uploadedModules.map((module, index) => (
                  <tr
                    key={index}
                    className={`border-b border-white/5 ${
                      index % 2 === 0 ? "bg-white/5" : ""
                    }`}
                  >
                    <td className="py-3 px-2 text-sm">{module.name}</td>
                    <td className="py-3 px-2">
                      <span
                        className={`text-xs px-2 py-1 rounded ${
                          module.format === "PDF"
                            ? "bg-[#EF4444]/20 text-[#EF4444]"
                            : module.format === "PPTX"
                            ? "bg-[#F59E0B]/20 text-[#F59E0B]"
                            : "bg-[#1E6BFF]/20 text-[#1E6BFF]"
                        }`}
                      >
                        {module.format}
                      </span>
                    </td>
                    <td className="py-3 px-2 text-sm text-[#8A9BB5]">
                      {module.date}
                    </td>
                    <td className="py-3 px-2 text-sm">{module.topics}</td>
                    <td className="py-3 px-2">
                      <span
                        className={`text-xs px-2 py-1 rounded ${
                          module.status === "Active"
                            ? "bg-[#10B981]/20 text-[#10B981]"
                            : "bg-[#F59E0B]/20 text-[#F59E0B]"
                        }`}
                      >
                        {module.status}
                      </span>
                    </td>
                    <td className="py-3 px-2">
                      <div className="flex gap-2">
                        <button 
                          onClick={() => handleView(module.name)}
                          className="p-1.5 hover:bg-white/5 rounded transition-colors"
                        >
                          <Eye className="w-4 h-4 text-[#00D4FF]" />
                        </button>
                        <button 
                          onClick={() => handleDelete(module.name)}
                          className="p-1.5 hover:bg-white/5 rounded transition-colors"
                        >
                          <Trash2 className="w-4 h-4 text-[#EF4444]" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>


        {/* Course Topic Tree */}
        <div className="bg-[#131827]/60 backdrop-blur-sm border border-white/10 rounded-xl p-6">
          <h3 className="text-lg mb-4">Course Topic Tree</h3>
          <div className="space-y-2">
            {topicTree.map((subject) => (
              <div key={subject.name}>
                <button
                  onClick={() => toggleTopic(subject.name)}
                  className="w-full flex items-center gap-2 p-2 hover:bg-white/5 rounded-lg transition-colors"
                >
                  {expandedTopics.includes(subject.name) ? (
                    <ChevronDown className="w-4 h-4 text-[#00D4FF]" />
                  ) : (
                    <ChevronRight className="w-4 h-4 text-[#8A9BB5]" />
                  )}
                  <span className="text-sm">{subject.name}</span>
                </button>
                {expandedTopics.includes(subject.name) && (
                  <div className="ml-6 mt-1 space-y-1">
                    {subject.topics.map((topic) => (
                      <div
                        key={topic}
                        className="flex items-center gap-2 p-2 text-sm text-[#8A9BB5]"
                      >
                        <div className="w-1.5 h-1.5 rounded-full bg-[#1E6BFF]" />
                        {topic}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

import { useState } from "react";
import { Search, User, FileText } from "lucide-react";

const queries = [
  {
    id: 1,
    student: "Sarah Johnson",
    question: "What is photosynthesis and why is it important?",
    answer:
      "Photosynthesis is the process by which plants convert light energy into chemical energy. During this process, plants use sunlight, water, and carbon dioxide to produce glucose and oxygen. It's crucial because it provides oxygen for breathing and forms the base of most food chains on Earth.",
    time: "2 min ago",
    source: "Module 3 — Photosynthesis.pdf",
    status: "answered",
  },
  {
    id: 2,
    student: "Mike Chen",
    question: "Can you explain Newton's first law of motion?",
    answer:
      "Newton's first law of motion states that an object at rest stays at rest and an object in motion stays in motion with the same speed and in the same direction unless acted upon by an unbalanced force. This is also known as the law of inertia.",
    time: "5 min ago",
    source: "Module 1 — Physics Basics.pdf",
    status: "answered",
  },
  {
    id: 3,
    student: "Emma Davis",
    question: "How does DNA replication work in cells?",
    answer:
      "DNA replication is the process by which a double-stranded DNA molecule is copied to produce two identical DNA molecules. It involves unwinding the DNA helix, separating the two strands, and using each strand as a template to synthesize a new complementary strand.",
    time: "12 min ago",
    source: "Module 5 — Cellular Biology.pdf",
    status: "answered",
  },
  {
    id: 4,
    student: "Alex Kumar",
    question: "What are the main elements in the periodic table?",
    answer: "",
    time: "15 min ago",
    source: "",
    status: "unanswered",
  },
  {
    id: 5,
    student: "Jessica Lee",
    question: "Explain the water cycle",
    answer:
      "The water cycle is the continuous movement of water on, above, and below Earth's surface. It includes evaporation, condensation, precipitation, and collection. Water evaporates from oceans and land, forms clouds, falls as rain or snow, and returns to bodies of water.",
    time: "18 min ago",
    source: "Module 2 — Earth Science.pdf",
    status: "answered",
  },
  {
    id: 6,
    student: "David Park",
    question: "What is the difference between mitosis and meiosis?",
    answer:
      "Mitosis is cell division that produces two identical daughter cells with the same number of chromosomes as the parent cell. Meiosis produces four daughter cells with half the number of chromosomes, used for sexual reproduction.",
    time: "25 min ago",
    source: "Module 5 — Cell Division.pdf",
    status: "answered",
  },
];

export default function QueryTranscripts() {
  const [selectedQuery, setSelectedQuery] = useState(queries[0]);
  const [activeTab, setActiveTab] = useState("all");

  const filteredQueries =
    activeTab === "all"
      ? queries
      : activeTab === "answered"
      ? queries.filter((q) => q.status === "answered")
      : activeTab === "unanswered"
      ? queries.filter((q) => q.status === "unanswered")
      : queries.filter((q) => q.status === "flagged");

  return (
    <div className="space-y-6">
      {/* Filter Tabs and Search */}
      <div className="bg-[#131827]/60 backdrop-blur-sm border border-white/10 rounded-xl p-4">
        <div className="flex items-center justify-between">
          <div className="flex gap-2">
            <button
              onClick={() => setActiveTab("all")}
              className={`px-4 py-2 rounded-lg text-sm transition-colors ${
                activeTab === "all"
                  ? "bg-[#1E6BFF] text-white"
                  : "bg-white/5 text-[#8A9BB5] hover:bg-white/10"
              }`}
            >
              All Queries
            </button>
            <button
              onClick={() => setActiveTab("answered")}
              className={`px-4 py-2 rounded-lg text-sm transition-colors ${
                activeTab === "answered"
                  ? "bg-[#1E6BFF] text-white"
                  : "bg-white/5 text-[#8A9BB5] hover:bg-white/10"
              }`}
            >
              Answered
            </button>
            <button
              onClick={() => setActiveTab("unanswered")}
              className={`px-4 py-2 rounded-lg text-sm transition-colors ${
                activeTab === "unanswered"
                  ? "bg-[#1E6BFF] text-white"
                  : "bg-white/5 text-[#8A9BB5] hover:bg-white/10"
              }`}
            >
              Unanswered
            </button>
            <button
              onClick={() => setActiveTab("flagged")}
              className={`px-4 py-2 rounded-lg text-sm transition-colors ${
                activeTab === "flagged"
                  ? "bg-[#1E6BFF] text-white"
                  : "bg-white/5 text-[#8A9BB5] hover:bg-white/10"
              }`}
            >
              Flagged
            </button>
          </div>
          <div className="relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-[#8A9BB5]" />
            <input
              type="text"
              placeholder="Search queries..."
              className="pl-10 pr-4 py-2 bg-white/5 border border-white/10 rounded-lg text-sm focus:outline-none focus:border-[#1E6BFF]"
            />
          </div>
        </div>
      </div>

      {/* Split Layout */}
      <div className="grid grid-cols-5 gap-4">
        {/* Left Panel - Query List */}
        <div className="col-span-2 bg-[#131827]/60 backdrop-blur-sm border border-white/10 rounded-xl p-4">
          <h3 className="text-lg mb-3">Live Session Log</h3>
          <div className="space-y-2 max-h-[700px] overflow-y-auto pr-2">
            {filteredQueries.map((query) => (
              <button
                key={query.id}
                onClick={() => setSelectedQuery(query)}
                className={`w-full text-left p-4 rounded-lg transition-colors ${
                  selectedQuery.id === query.id
                    ? "bg-[#1E6BFF]/20 border border-[#1E6BFF]"
                    : "bg-white/5 hover:bg-white/10 border border-transparent"
                }`}
              >
                <div className="flex items-start gap-3">
                  <div className="w-8 h-8 bg-gradient-to-br from-[#1E6BFF] to-[#00D4FF] rounded-full flex items-center justify-center flex-shrink-0">
                    <User className="w-4 h-4" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex justify-between items-start mb-1">
                      <p className="text-sm truncate">{query.student}</p>
                      <span className="text-xs text-[#8A9BB5] flex-shrink-0 ml-2">
                        {query.time}
                      </span>
                    </div>
                    <p className="text-sm text-[#8A9BB5] line-clamp-2">
                      {query.question}
                    </p>
                    <div className="flex items-center gap-2 mt-2">
                      {query.status === "answered" ? (
                        <span className="text-xs px-2 py-0.5 bg-[#10B981]/20 text-[#10B981] rounded-full">
                          Answered
                        </span>
                      ) : (
                        <span className="text-xs px-2 py-0.5 bg-[#F59E0B]/20 text-[#F59E0B] rounded-full">
                          Unanswered
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* Right Panel - Query Detail */}
        <div className="col-span-3 bg-[#131827]/60 backdrop-blur-sm border border-white/10 rounded-xl p-6">
          <h3 className="text-lg mb-4">Query Details</h3>
          {selectedQuery && (
            <div className="space-y-4">
              <div className="flex items-center gap-3 pb-4 border-b border-white/10">
                <div className="w-10 h-10 bg-gradient-to-br from-[#1E6BFF] to-[#00D4FF] rounded-full flex items-center justify-center">
                  <User className="w-5 h-5" />
                </div>
                <div>
                  <p className="text-sm">{selectedQuery.student}</p>
                  <p className="text-xs text-[#8A9BB5]">{selectedQuery.time}</p>
                </div>
              </div>

              <div>
                <h4 className="text-sm text-[#8A9BB5] mb-2">Question</h4>
                <div className="p-4 bg-white/5 border border-white/10 rounded-lg">
                  <p className="text-sm">{selectedQuery.question}</p>
                </div>
              </div>

              {selectedQuery.answer ? (
                <>
                  <div>
                    <h4 className="text-sm text-[#8A9BB5] mb-2">ZORO's Answer</h4>
                    <div className="p-4 bg-[#1E6BFF]/10 border border-[#1E6BFF]/30 rounded-lg">
                      <p className="text-sm leading-relaxed">{selectedQuery.answer}</p>
                    </div>
                  </div>

                  {selectedQuery.source && (
                    <div className="flex items-center gap-2 p-3 bg-white/5 border border-white/10 rounded-lg">
                      <FileText className="w-4 h-4 text-[#00D4FF] flex-shrink-0" />
                      <div>
                        <p className="text-xs text-[#8A9BB5]">Source</p>
                        <p className="text-sm text-[#00D4FF]">{selectedQuery.source}</p>
                      </div>
                    </div>
                  )}
                </>
              ) : (
                <div className="p-8 text-center bg-white/5 border border-white/10 rounded-lg">
                  <p className="text-[#8A9BB5]">This query has not been answered yet.</p>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

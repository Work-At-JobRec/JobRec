import { useEffect, useState } from "react";
import Navbar from "../components/Navbar.jsx";
import LocationBar from "../components/LocationBar.jsx";
import JobCard from "../components/JobCard.jsx";
import { ChevronDownIcon, FunnelIcon } from "../components/Icons.jsx";
import { fetchJobs } from "../api/jobs.js";

export default function Jobs() {
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [jobs, setJobs] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchJobs()
      .then(setJobs)
      .catch((err) => {
        console.error(err);
        setError("Couldn't load jobs. Is the backend running?");
      });
  }, []);

  return (
    <div className="min-h-screen bg-white">
      <Navbar />
      <main className="max-w-[1400px] mx-auto px-6 pb-16">
        <h1 className="text-center text-[56px] font-bold mt-24 mb-16">Here are the Best Jobs For You:</h1>

        <div className="max-w-[1000px] mx-auto">
          <LocationBar />
          <button
            type="button"
            onClick={() => setFiltersOpen((open) => !open)}
            className="mt-3 inline-flex items-center gap-3 bg-black text-white text-xl font-bold rounded-2xl px-5 py-2.5"
          >
            <FunnelIcon className="w-6 h-6" />
            Filters
            <ChevronDownIcon className={`w-5 h-5 transition-transform ${filtersOpen ? "rotate-180" : ""}`} />
          </button>
          {filtersOpen && <p className="mt-3 text-lg text-[#8a8a8a]">Filters coming soon.</p>}
        </div>

        <hr className="border-0 border-t-[1.5px] border-black mt-3 mb-6" />

        <div className="flex flex-col gap-8 px-12">
          {error && <p className="text-2xl">{error}</p>}
          {!error && !jobs && <p className="text-2xl text-[#8a8a8a]">Loading jobs…</p>}
          {jobs?.length === 0 && <p className="text-2xl">No jobs found yet.</p>}
          {jobs?.map((job) => (
            <JobCard key={job.id} job={job} />
          ))}
        </div>
      </main>
    </div>
  );
}

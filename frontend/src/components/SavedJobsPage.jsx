import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import Navbar from "./Navbar.jsx";
import JobCard from "./JobCard.jsx";
import { fetchSavedJobs } from "../api/savedJobs.js";
import { useAuthenticatedUser } from "../hooks/useAuthenticatedUser.ts";

// A page listing one of the user's saved job lists ("bookmarks" or "applied"),
// with the same cards as the Jobs page.
export default function SavedJobsPage({ list, title, emptyMessage }) {
  const [jobs, setJobs] = useState(null);
  const [error, setError] = useState(null);
  const { getAccessTokenSilently, isAuthenticated, isLoading } = useAuthenticatedUser();

  useEffect(() => {
    if (isLoading) return;
    if (!isAuthenticated) {
      setError("Sign in to see your jobs.");
      return;
    }
    setError(null);
    getAccessTokenSilently()
      .then((token) => fetchSavedJobs(list, token))
      .then(setJobs)
      .catch((err) => {
        console.error(err);
        setError("Couldn't load your jobs. Is the backend running?");
      });
  }, [list, isLoading, isAuthenticated, getAccessTokenSilently]);

  return (
    <div className="min-h-screen bg-white">
      <Navbar />
      <main className="max-w-[1400px] mx-auto px-6 pb-16">
        <h1 className="text-center text-[56px] font-bold mt-24 mb-16">{title}</h1>

        <div className="flex flex-col gap-8 px-12">
          {error && <p className="text-2xl">{error}</p>}
          {!error && !jobs && <p className="text-2xl text-[#8a8a8a]">Loading jobs…</p>}
          {jobs?.length === 0 && (
            <div role="status" className="flex flex-col items-center text-center py-24">
              <p className="m-0 text-[34px] font-bold">{emptyMessage}</p>
              <Link
                to="/jobs"
                className="mt-6 bg-[#E066A3] hover:bg-[#d4508f] text-white text-2xl font-bold rounded-3xl px-12 py-2 transition-colors no-underline"
              >
                Top Jobs for you
              </Link>
            </div>
          )}
          {jobs?.map((job) => (
            <JobCard key={job.id} job={job} />
          ))}
        </div>
      </main>
    </div>
  );
}

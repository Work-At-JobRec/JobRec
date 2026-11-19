import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import Navbar from "../components/Navbar.jsx";
import JobCard from "../components/JobCard.jsx";
import { fetchBookmarks } from "../api/bookmarks.js";
import { useAuthenticatedUser } from "../hooks/useAuthenticatedUser.ts";

export default function Bookmarks() {
  const [jobs, setJobs] = useState(null);
  const [error, setError] = useState(null);
  const { getAccessTokenSilently, isAuthenticated, isLoading } = useAuthenticatedUser();

  useEffect(() => {
    if (isLoading) return;
    if (!isAuthenticated) {
      setError("Sign in to see your bookmarks.");
      return;
    }
    setError(null);
    getAccessTokenSilently()
      .then(fetchBookmarks)
      .then(setJobs)
      .catch((err) => {
        console.error(err);
        setError("Couldn't load your bookmarks. Is the backend running?");
      });
  }, [isLoading, isAuthenticated, getAccessTokenSilently]);

  return (
    <div className="min-h-screen bg-white">
      <Navbar />
      <main className="max-w-[1400px] mx-auto px-6 pb-16">
        <h1 className="text-center text-[56px] font-bold mt-24 mb-16">Your Bookmarked Jobs:</h1>

        <div className="flex flex-col gap-8 px-12">
          {error && <p className="text-2xl">{error}</p>}
          {!error && !jobs && <p className="text-2xl text-[#8a8a8a]">Loading bookmarks…</p>}
          {jobs?.length === 0 && (
            <div role="status" className="flex flex-col items-center text-center py-24">
              <p className="text-[34px] font-bold leading-snug">No bookmarks yet.</p>
              <p className="mt-6 text-xl text-[#5a5a5a] max-w-[640px]">
                Open a job from{" "}
                <Link to="/jobs" className="font-bold text-black underline underline-offset-4 hover:text-[#E75A8F]">
                  your recommendations
                </Link>{" "}
                and press Bookmark to save it here.
              </p>
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

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import Navbar from "../components/Navbar.jsx";
import EmptyJobsState from "../components/EmptyJobsState.jsx";
import LocationBar from "../components/LocationBar.jsx";
import JobCard from "../components/JobCard.jsx";
import { fetchJobs } from "../api/jobs.js";
import { useAuthenticatedUser } from "../hooks/useAuthenticatedUser.ts";

export default function Jobs() {
  const [location, setLocation] = useState("");
  const [appliedLocation, setAppliedLocation] = useState("");
  const [jobs, setJobs] = useState(null);
  const [error, setError] = useState(null);
  const { getAccessTokenSilently, isAuthenticated, isLoading } = useAuthenticatedUser();

  useEffect(() => {
    if (isLoading) return;
    if (!isAuthenticated) {
      setJobs(null);
      setError("Sign in to see recommendations");
      return;
    }

    let cancelled = false;
    setJobs(null);
    setError(null);
    const loadJobs = async () => {
      try {
        const accessToken = await getAccessTokenSilently();
        const results = await fetchJobs(accessToken, { location: appliedLocation });
        if (!cancelled) setJobs(results);
      } catch (err) {
        console.error(err);
        if (!cancelled) setError("Couldn't load jobs. Please try again.");
      }
    };
    loadJobs();
    return () => { cancelled = true; };
  }, [getAccessTokenSilently, isLoading, isAuthenticated, appliedLocation]);

  const applyLocation = (event) => {
    event.preventDefault();
    setAppliedLocation(location.trim());
  };

  const clearLocation = () => {
    setLocation("");
    setAppliedLocation("");
  };

  return (
    <div className="min-h-screen bg-white">
      <Navbar />
      <main className="page-zoom max-w-[1400px] mx-auto px-6 pb-16">
        <h1 className="text-center text-[56px] font-bold mt-24 mb-16">Here are the Best Jobs For You:</h1>

        <form onSubmit={applyLocation} role="search" className="max-w-[1000px] mx-auto flex flex-wrap items-center gap-4">
          <LocationBar location={location} onLocationChange={setLocation} />
          <button
            type="submit"
            className="rounded-2xl bg-black px-5 py-2.5 text-xl font-bold text-white hover:bg-[#E75A8F]"
          >
            Search Area
          </button>
          {(location || appliedLocation) && (
            <button
              type="button"
              onClick={clearLocation}
              className="text-lg text-[#8a8a8a] underline underline-offset-4 hover:text-[#E75A8F]"
            >
              Clear Location
            </button>
          )}
        </form>

        {appliedLocation && (
          <p role="status" className="mx-auto mt-5 max-w-[1000px] text-lg text-[#5a5a5a]">
            Showing recommendations for: <strong>{appliedLocation}</strong>
          </p>
        )}

        <hr className="border-0 border-t-[1.5px] border-black mt-6 mb-6" />

        <div className="flex flex-col gap-8 px-12" aria-live="polite">
          {error && <p className="text-2xl">{error}</p>}
          {!error && !jobs && <p className="text-2xl text-[#8a8a8a]">Loading jobs…</p>}
          {jobs?.length === 0 && (
            <EmptyJobsState>
              {appliedLocation ? (
                <p>
                  No matching jobs were found for <strong>{appliedLocation}</strong>.{" "}
                  <button type="button" className="underline font-bold" onClick={clearLocation}>
                    Clear Location
                  </button>{" "}
                  or search a different city.
                </p>
              ) : (
                <p>
                  Try{" "}
                  <Link to="/search" className="font-bold text-black underline underline-offset-4 hover:text-[#E75A8F]">
                    searching with different filters
                  </Link>{" "}
                  or{" "}
                  <Link to="/profile" className="font-bold text-black underline underline-offset-4 hover:text-[#E75A8F]">
                    updating your resume
                  </Link>{" "}
                  so we can find better matches.
                </p>
              )}
            </EmptyJobsState>
          )}
          {jobs?.map((job) => (
            <JobCard key={job.id} job={job} />
          ))}
        </div>
      </main>
    </div>
  );
}

import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import Navbar from "../components/Navbar.jsx";
import LocationBar from "../components/LocationBar.jsx";
import { ClockIcon, DollarIcon, FlagIcon, PinIcon, PushpinIcon } from "../components/Icons.jsx";
import { compatibilityColor, fetchJob } from "../api/jobs.js";

function Requirement({ text, skill, met }) {
  return (
    <li className="text-2xl my-2">
      {text}{" "}
      <span className={`rounded-full px-2 ${met ? "bg-[#DDF7D5]" : "bg-[#F8D4D4]"}`}>{skill}</span>{" "}
      <span className="font-bold">{met ? "✓" : "✗"}</span>
    </li>
  );
}

export default function JobDetail() {
  const { id } = useParams();
  // undefined = still loading, null = not found
  const [job, setJob] = useState(undefined);
  const [error, setError] = useState(null);

  useEffect(() => {
    setJob(undefined);
    setError(null);
    fetchJob(id)
      .then(setJob)
      .catch((err) => {
        console.error(err);
        setError("Couldn't load this job. Is the backend running?");
      });
  }, [id]);

  return (
    <div className="min-h-screen bg-white">
      <Navbar />
      <main className="max-w-[1100px] mx-auto px-6 pb-16">
        <h1 className="text-center text-[56px] font-bold mt-16 mb-10">Here are the Best Jobs For You:</h1>
        <div className="flex justify-center">
          <LocationBar />
        </div>

        <Link to="/jobs" className="inline-block mt-10 mb-3 text-lg text-[#8a8a8a] hover:text-[#E75A8F] no-underline">
          ← Back to all jobs
        </Link>

        {error ? (
          <p className="text-2xl">{error}</p>
        ) : job === undefined ? (
          <p className="text-2xl text-[#8a8a8a]">Loading job…</p>
        ) : job === null ? (
          <p className="text-2xl">We couldn't find that job.</p>
        ) : (
          <article className="zoom-in border-[1.5px] border-black rounded-2xl bg-[#fcfcfc] px-10 py-8">
            <header className="flex flex-wrap items-baseline gap-x-8 gap-y-2">
              <h2 className="m-0 text-[40px] font-bold">{job.title}</h2>
              <span className="text-[30px]">{job.company}</span>
              {job.compatibility != null && (
                <span className="ml-auto text-[30px] font-bold">
                  Compatibility:{" "}
                  <span className={`font-normal ${compatibilityColor(job.compatibility)}`}>{job.compatibility}%</span>
                </span>
              )}
            </header>

            <ul className="m-0 mt-6 p-0 list-none flex flex-wrap justify-between gap-4 text-2xl text-[#8a8a8a] px-4">
              {job.location && (
                <li className="flex items-center gap-3">
                  <PinIcon className="w-7 h-7" />
                  {job.location}
                </li>
              )}
              {job.jobType && (
                <li className="flex items-center gap-3">
                  <ClockIcon className="w-7 h-7" />
                  {job.jobType}
                </li>
              )}
              {job.salary && (
                <li className="flex items-center gap-3">
                  <DollarIcon className="w-9 h-7" />
                  {job.salary}
                </li>
              )}
              {job.postedAgo && (
                <li className="flex items-center gap-3">
                  <PushpinIcon className="w-7 h-7" />
                  {job.postedAgo}
                </li>
              )}
            </ul>

            <section className="px-12 mt-8">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <h3 className="m-0 text-[36px] font-bold">Role Description</h3>
                <button
                  type="button"
                  className="inline-flex items-center gap-3 bg-black text-white text-2xl font-bold rounded-full px-6 py-2"
                >
                  <FlagIcon className="w-7 h-7" />
                  Report Listing
                </button>
              </div>
              <p className="text-2xl mt-4">{job.description}</p>

              {job.requirements.length > 0 && (
                <>
                  <h4 className="m-0 mt-8 text-2xl font-bold">Requirements:</h4>
                  <ul className="mt-2 pl-8 list-disc">
                    {job.requirements.map((req) => (
                      <Requirement key={req.skill} {...req} />
                    ))}
                  </ul>
                </>
              )}

              <div className="flex justify-center mt-12">
                <a
                  href={job.applicationUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="bg-[#E066A3] hover:bg-[#d4508f] text-white text-[28px] font-bold rounded-3xl px-20 py-4 transition-colors no-underline"
                >
                  Apply Now
                </a>
              </div>
            </section>
          </article>
        )}
      </main>
    </div>
  );
}

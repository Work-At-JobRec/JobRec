import { useEffect, useState, useCallback } from "react";
import { Link, useParams } from "react-router-dom";
import Navbar from "../components/Navbar.jsx";
import LocationBar from "../components/LocationBar.jsx";
import { ClockIcon, DollarIcon, FlagIcon, PinIcon, PushpinIcon } from "../components/Icons.jsx";
import { compatibilityColor, fetchJob, reportJob } from "../api/jobs.js";
import { useAuthenticatedUser } from "../hooks/useAuthenticatedUser.ts";
import ReportListingModal from "../components/ReportListingModal.jsx";

// Remembers which jobs this browser has reported so the button stays "Report Listed".
// Once the backend stores reports, the job API could return a `reported` flag instead.
const REPORTED_KEY = "reportedJobs";

function loadReported() {
  try {
    return JSON.parse(localStorage.getItem(REPORTED_KEY)) || [];
  } catch {
    return [];
  }
}

function saveReported(id) {
  try {
    const ids = loadReported();
    if (!ids.includes(id)) localStorage.setItem(REPORTED_KEY, JSON.stringify([...ids, id]));
  } catch {
    // Storage unavailable; the button still updates for this visit.
  }
}

function Requirement({ text, skill, met }) {
  return (
    <li className="text-2xl my-2">
      {text}{" "}
      <span className={`rounded-full px-2 ${met ? "bg-[#DDF7D5]" : "bg-[#F8D4D4]"}`}>{skill}</span>{" "}
      <span className="font-bold">{met ? "✓" : "✗"}</span>
    </li>
  );
}

// Scraped descriptions are plain text: short lines ending in ":" are section
// headings and lines starting with "- " are bullets.
function Description({ text }) {
  const blocks = [];
  for (const raw of (text || "").split("\n")) {
    const line = raw.trim();
    if (!line) continue;
    if (line.startsWith("- ")) {
      const last = blocks[blocks.length - 1];
      if (last?.type === "list") last.items.push(line.slice(2));
      else blocks.push({ type: "list", items: [line.slice(2)] });
    } else if (line.endsWith(":") && line.length <= 80) {
      blocks.push({ type: "heading", text: line });
    } else {
      blocks.push({ type: "paragraph", text: line });
    }
  }

  return (
    <div className="text-2xl mt-4">
      {blocks.map((block, i) =>
        block.type === "heading" ? (
          <h4 key={i} className="m-0 mt-6 font-bold">{block.text}</h4>
        ) : block.type === "list" ? (
          <ul key={i} className="mt-2 pl-8 list-disc">
            {block.items.map((item, j) => (
              <li key={j} className="my-1">{item}</li>
            ))}
          </ul>
        ) : (
          <p key={i} className="mt-3">{block.text}</p>
        )
      )}
    </div>
  );
}

export default function JobDetail() {
  const { id } = useParams();
  // undefined = still loading, null = not found
  const [job, setJob] = useState(undefined);
  const [error, setError] = useState(null);
  const [reporting, setReporting] = useState(false);
  const [reported, setReported] = useState(() => loadReported().includes(id));
  const { getAccessTokenSilently, isAuthenticated, isLoading } = useAuthenticatedUser();


  const fetchJob_wrapper = useCallback(async () => {
    const accessToken = await getAccessTokenSilently();
    fetchJob(id, accessToken)
      .then(setJob)
      .catch((err) => {
        console.error(err);
        setError("Couldn't load this job. Is the backend running?");
      });
  }, [id, fetchJob]);

  useEffect(() => {
    setJob(undefined);
    setError(null);
    setReported(loadReported().includes(id));
    if (isLoading) return;
    if (!isAuthenticated) {
      setError("Sign in to view this job.");
      return;
    }
    fetchJob_wrapper();
  }, [id, isLoading, isAuthenticated]);

  return (
    <div className="min-h-screen bg-white">
      <Navbar />
      <main className="page-zoom max-w-[1100px] mx-auto px-6 pb-16">
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
                  disabled={reported}
                  onClick={() => setReporting(true)}
                  className={`inline-flex items-center gap-3 text-white text-2xl font-bold rounded-full px-6 py-2 transition-colors ${
                    reported ? "bg-[#E066A3] cursor-default" : "bg-black hover:bg-[#E066A3]"
                  }`}
                >
                  <FlagIcon className="w-7 h-7" />
                  {reported ? "Report Listed" : "Report Listing"}
                </button>
              </div>
              <Description text={job.description} />

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

      {reporting && (
        <ReportListingModal
          onSubmit={async (report) => {
            await reportJob(id, report, await getAccessTokenSilently());
            saveReported(id);
            setReported(true);
          }}
          onClose={() => setReporting(false)}
        />
      )}
    </div>
  );
}

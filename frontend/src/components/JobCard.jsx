import { Link } from "react-router-dom";
import { ClockIcon, DollarIcon, PinIcon } from "./Icons.jsx";
import { compatibilityColor } from "../api/jobs.js";

// One job in a results list; links to its detail page.
export default function JobCard({ job }) {
  return (
    <Link
      to={`/jobs/${job.id}`}
      className="grid md:grid-cols-[1.1fr_1fr_1fr] grid-cols-1 gap-4 items-center border-[1.5px] border-black rounded-xl bg-[#fcfcfc] px-12 py-4 shadow-sm text-black no-underline transition-transform duration-200 hover:scale-[1.01] hover:shadow-md"
    >
      <div>
        <h2 className="m-0 text-[34px] font-bold leading-tight">{job.title}</h2>
        <p className="m-0 text-2xl">{job.company}</p>
        <p className="m-0 mt-1 text-xl text-[#8a8a8a]">{job.postedAgo ?? "Date Posted Unknown"}</p>
      </div>

      <ul className="m-0 p-0 list-none flex flex-col gap-3 text-xl text-[#8a8a8a]">
        {job.location && (
          <li className="flex items-center gap-4">
            <PinIcon className="w-7 h-7 text-[#8a8a8a]" />
            {job.location}
          </li>
        )}
        {job.jobType && (
          <li className="flex items-center gap-4">
            <ClockIcon className="w-7 h-7 text-[#8a8a8a]" />
            {job.jobType}
          </li>
        )}
        {job.salary && (
          <li className="flex items-center gap-4">
            <DollarIcon className="w-8 h-6 text-[#8a8a8a]" />
            {job.salary}
          </li>
        )}
      </ul>

      {job.compatibility != null && (
        <div className="flex items-center md:justify-end gap-12 text-2xl font-bold">
          <span>Compatibility:</span>
          <span className={compatibilityColor(job.compatibility)}>{job.compatibility}%</span>
        </div>
      )}
    </Link>
  );
}
